# 14 — CI/CD, GitOps & Production Deployment

## 1. The big picture

```text
 Developer ─push─► App repo (code + Dockerfile + chart)
                     │  CI (GitHub Actions / Jenkins / GitLab CI)
                     │   1. lint + unit tests
                     │   2. build image (BuildKit), tag with git SHA
                     │   3. scan (Trivy), SBOM, sign (cosign)
                     │   4. push to registry (ECR / GHCR / Harbor)
                     │   5. update desired state: bump image tag in the GitOps repo (PR or commit)
                     ▼
                  GitOps repo (Helm values / Kustomize overlays per env)
                     │  CD = Argo CD or Flux running IN the cluster (pull model)
                     ▼
                  Cluster: sync → rollout (rolling / blue-green / canary) → health checks → (auto) rollback
```

| | Push-based CD (CI runs `kubectl/helm`) | Pull-based GitOps (Argo CD/Flux) |
|--|----------------------------------------|----------------------------------|
| Cluster credentials | stored in CI (risk) | stay inside cluster |
| Drift detection | none | continuous, auto-heal |
| Audit trail | CI logs | Git history = deployment history |
| Rollback | rerun old pipeline | `git revert` |
| Multi-cluster | many credentials | each cluster pulls |

**GitOps principles:** declarative, versioned & immutable in Git, pulled automatically, continuously reconciled.

## 2. Image registries and tagging

- Tag images with **immutable git SHA** (`api:3f9c2ab`) + optional SemVer; never deploy `latest`.
- Enable registry immutability (ECR "tag immutability") and lifecycle policies (expire old untagged images).
- Pull credentials: node IAM role (ECR), `imagePullSecrets`, or registry mirrors/pull-through caches (avoid Docker Hub rate limits).

## 3. CI with GitHub Actions (build, scan, push, update GitOps repo)

`.github/workflows/ci.yaml` in the app repo:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
  packages: write          # push to GHCR
  id-token: write          # OIDC for cosign keyless signing / AWS role assumption

env:
  IMAGE: ghcr.io/${{ github.repository_owner }}/shop-api

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.meta.outputs.tag }}
    steps:
      - uses: actions/checkout@v4

      - name: Unit tests
        run: |
          python -m pip install -r requirements.txt
          python -m pytest -q

      - id: meta
        run: echo "tag=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"

      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        if: github.event_name == 'push'
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build (and push on main)
        uses: docker/build-push-action@v6
        with:
          context: .
          push: ${{ github.event_name == 'push' }}
          tags: ${{ env.IMAGE }}:${{ steps.meta.outputs.tag }}
          provenance: true
          sbom: true
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Scan image
        if: github.event_name == 'push'
        uses: aquasecurity/trivy-action@0.33.1      # pin actions to a version or commit SHA
        with:
          image-ref: ${{ env.IMAGE }}:${{ steps.meta.outputs.tag }}
          severity: CRITICAL,HIGH
          ignore-unfixed: true
          exit-code: "1"

      - name: Lint Helm chart
        run: |
          helm lint chart/
          helm template shop chart/ -f chart/values-prod.yaml > /tmp/rendered.yaml

  promote-dev:
    if: github.event_name == 'push'
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Bump image tag in GitOps repo
        env:
          GH_TOKEN: ${{ secrets.GITOPS_REPO_TOKEN }}     # fine-grained token or GitHub App with write to the gitops repo only
          TAG: ${{ needs.build.outputs.tag }}
        run: |
          git clone "https://x-access-token:${GH_TOKEN}@github.com/example-org/shop-gitops.git"
          cd shop-gitops
          yq -i ".image.tag = \"${TAG}\"" envs/dev/values.yaml      # yq is preinstalled on GitHub-hosted runners
          git config user.name "ci-bot"; git config user.email "ci-bot@users.noreply.github.com"
          git commit -am "dev: shop-api ${TAG}"
          git push
```

Promotion to staging/prod = a **pull request** in the GitOps repo (review + approval) changing `envs/prod/values.yaml`.

For **ECR**, replace the login step with `aws-actions/configure-aws-credentials` (OIDC role, no static keys) +
`aws-actions/amazon-ecr-login` (chapter 16 project 4).

## 4. Jenkins (alternative CI) with Kubernetes agents

```groovy
// Jenkinsfile — agents run as Pods via the Kubernetes plugin
pipeline {
  agent {
    kubernetes {
      yaml '''
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: buildkit
      image: moby/buildkit:v0.24.0-rootless
      command: ["cat"]
      tty: true
    - name: tools
      image: alpine/helm:3.18.4
      command: ["cat"]
      tty: true
'''
    }
  }
  environment { IMAGE = "registry.example.com/shop-api" }
  stages {
    stage('Test')  { steps { sh 'echo run tests here' } }
    stage('Build') {
      steps {
        container('buildkit') {
          sh 'buildctl-daemonless.sh build --frontend dockerfile.v0 --local context=. --local dockerfile=. --output type=image,name=$IMAGE:$GIT_COMMIT,push=true'
        }
      }
    }
    stage('Helm lint') { steps { container('tools') { sh 'helm lint chart/' } } }
  }
}
```

Never mount the node's Docker socket into CI Pods (root on the node). Use rootless BuildKit, Kaniko-style builders, or a remote builder.

## 5. Argo CD

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-server
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
kubectl -n argocd port-forward svc/argocd-server 8443:443 &      # https://localhost:8443  user: admin
# CLI
curl -sSL -o argocd https://github.com/argoproj/argo-cd/releases/latest/download/argocd-linux-amd64
sudo install -m 555 argocd /usr/local/bin/argocd && rm argocd
argocd login localhost:8443 --username admin --insecure
```

`Application` (one app, one env):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: shop-dev
  namespace: argocd
  finalizers: ["resources-finalizer.argocd.argoproj.io"]   # delete app → delete its resources
spec:
  project: default
  source:
    repoURL: https://github.com/example-org/shop-gitops.git
    targetRevision: main
    path: chart                        # Helm chart in the gitops repo (or a chart from a Helm/OCI repo)
    helm:
      valueFiles: ["../envs/dev/values.yaml"]
  destination:
    server: https://kubernetes.default.svc
    namespace: shop-dev
  syncPolicy:
    automated:
      prune: true                      # delete resources removed from Git
      selfHeal: true                   # revert manual kubectl changes (drift)
    syncOptions: ["CreateNamespace=true", "ServerSideApply=true"]
    retry:
      limit: 5
      backoff: { duration: 10s, factor: 2, maxDuration: 3m }
```

```bash
kubectl apply -f shop-dev-app.yaml
argocd app list; argocd app get shop-dev
argocd app diff shop-dev
argocd app history shop-dev
argocd app rollback shop-dev <history-id>     # temporary; with auto-sync, prefer git revert
```

Scale to many apps/envs/clusters with **ApplicationSet** (generators: list, git directories, clusters) and the
**app-of-apps** pattern. Sync waves/hooks (`argocd.argoproj.io/sync-wave`) order CRDs → operators → apps.

## 6. Flux (alternative GitOps)

```bash
curl -s https://fluxcd.io/install.sh | sudo bash      # installs flux CLI (read the script first)
flux check --pre
flux bootstrap github --owner=example-org --repository=fleet --branch=main --path=clusters/dev --personal
```

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata: { name: shop, namespace: flux-system }
spec:
  interval: 1m
  url: https://github.com/example-org/shop-gitops
  ref: { branch: main }
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata: { name: shop-dev, namespace: flux-system }
spec:
  interval: 5m
  sourceRef: { kind: GitRepository, name: shop }
  path: ./envs/dev
  prune: true
  targetNamespace: shop-dev
```

Flux also has `HelmRelease` and image automation (watch registry → commit new tag).

| | Argo CD | Flux |
|--|---------|------|
| UI | rich web UI | CLI-first (UIs via add-ons) |
| Model | Application CRs | GitRepository + Kustomization/HelmRelease |
| Multi-tenancy | Projects, SSO, RBAC | K8s RBAC/namespaces |
| Image automation | Argo CD Image Updater | built-in controllers |

## 7. Deployment strategies

| Strategy | How | Pros | Cons |
|----------|-----|------|------|
| **Recreate** | stop all old, start new | simple, no version mix | downtime |
| **Rolling** (default) | replace Pods gradually (maxSurge/maxUnavailable) | no downtime, cheap | both versions serve at once; slow rollback of bad release |
| **Blue-green** | full new stack (green) alongside old (blue); switch traffic at once | instant switch/rollback, test before cutover | 2× resources; DB schema compat |
| **Canary** | send small % to new version, increase while metrics are healthy | lowest blast radius, data-driven | needs traffic splitting + metrics |
| A/B, shadow | route by user/header; mirror traffic | experiments, safe testing | complexity |

### Blue-green with plain Services

```bash
# web-blue (version=blue) and web-green (version=green) Deployments exist; Service selects one:
kubectl patch svc web -p '{"spec":{"selector":{"app":"web","version":"green"}}}'   # cut over
kubectl patch svc web -p '{"spec":{"selector":{"app":"web","version":"blue"}}}'    # instant rollback
```

### Canary with Argo Rollouts

```bash
kubectl create namespace argo-rollouts
kubectl apply -n argo-rollouts -f https://github.com/argoproj/argo-rollouts/releases/latest/download/install.yaml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout                          # replaces the Deployment
metadata: { name: shop-api }
spec:
  replicas: 5
  selector: { matchLabels: { app: shop-api } }
  template:
    metadata: { labels: { app: shop-api } }
    spec:
      containers:
        - name: api
          image: ghcr.io/example/shop-api:3f9c2ab
          ports: [{ containerPort: 8080 }]
  strategy:
    canary:
      canaryService: shop-api-canary   # Services managed by Rollouts
      stableService: shop-api-stable
      trafficRouting:
        plugins:
          argoproj-labs/gatewayAPI:     # or istio / nginx / alb / traefik
            httpRoute: shop-api
            namespace: shop
      steps:
        - setWeight: 10
        - pause: { duration: 5m }
        - analysis:
            templates: [{ templateName: success-rate }]
        - setWeight: 50
        - pause: { duration: 10m }
        - setWeight: 100
---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata: { name: success-rate }
spec:
  metrics:
    - name: success-rate
      interval: 1m
      count: 5
      successCondition: result[0] >= 0.99
      failureLimit: 1                   # failure → automatic abort and rollback to stable
      provider:
        prometheus:
          address: http://kps-kube-prometheus-stack-prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{app="shop-api",code!~"5.."}[2m]))
            / sum(rate(http_requests_total{app="shop-api"}[2m]))
```

```bash
kubectl argo rollouts get rollout shop-api --watch      # kubectl plugin
kubectl argo rollouts promote shop-api
kubectl argo rollouts abort shop-api
```

(Without a traffic router, Rollouts approximates weights with replica counts.)

## 8. Rollback strategies

| Level | Action |
|-------|--------|
| GitOps (preferred) | `git revert <commit>` in the GitOps repo → Argo/Flux syncs old version |
| Progressive delivery | automatic abort on failed analysis |
| Helm | `helm rollback <release> <rev>` |
| Deployment | `kubectl rollout undo deploy/<name>` (drift if GitOps auto-heal is on — Git wins) |
| Feature flags | turn off the feature without redeploying |
| Database | expand/contract migrations so the previous version still works; never couple a destructive migration with a deploy |

## 9. End-to-end pipeline checklist

- [ ] Tests, lint, `helm lint`/`kubeconform`, policy checks (Kyverno CLI/Conftest) on PRs
- [ ] Image built reproducibly, tagged by SHA, scanned, signed, SBOM attached
- [ ] Registry immutability; admission verifies signatures in prod
- [ ] GitOps repo per env with PR-based promotion and CODEOWNERS
- [ ] Argo CD/Flux auto-sync + self-heal; notifications to chat
- [ ] Readiness probes, PDBs, resource requests in every chart
- [ ] Canary/blue-green with automated metric analysis for critical services
- [ ] Documented rollback runbook; tested regularly

---

## Interview questions

1. **What is GitOps?** Git as the single source of truth for desired state, reconciled by an in-cluster agent (pull model).
2. **Push vs pull CD?** CI applies with cluster creds vs agent pulls from Git; pull keeps creds in-cluster and fixes drift.
3. **Argo CD self-heal and prune?** Revert manual drift; delete resources removed from Git.
4. **Why tag images with git SHA?** Immutable, traceable, reproducible deployments; easy rollback.
5. **Blue-green vs canary?** Full switch between two stacks vs gradual percentage shift with metric checks.
6. **How does Argo Rollouts roll back automatically?** AnalysisTemplate queries metrics; failure aborts and returns traffic to stable.
7. **How do you promote between environments?** PRs changing image tags/values in env-specific GitOps paths.
8. **How do you keep secrets out of GitOps repos?** External Secrets, Sealed Secrets, SOPS.
9. **How should CI authenticate to AWS?** OIDC federation to an IAM role (no long-lived keys).
10. **How do you handle DB migrations in rolling deploys?** Backward-compatible expand/contract migrations, run as Jobs/hooks.

**Scenario:** Someone hot-fixed prod with `kubectl edit`; Argo CD reverted it and the bug returned. → That's self-heal working; the
fix must go through Git (PR), possibly expedited.

**Follow-ups:** How would you structure ApplicationSets for 50 clusters? How do sync waves order CRDs and workloads? How would you
handle progressive delivery across multiple clusters/regions?
