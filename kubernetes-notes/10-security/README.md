# 10 — Kubernetes Security

## 1. The 4C model and attack surface

```text
 Cloud (IAM, network, KMS)  →  Cluster (API server, RBAC, admission, etcd)  →  Container (image, runtime, securityContext)  →  Code
```

Typical attack chain: vulnerable app → shell in container → reads mounted SA token / cloud metadata → uses over-privileged RBAC
or IAM → creates privileged Pod → escapes to node → owns cluster. Every section below breaks one link.

---

## 2. Authentication and authorization flow

```text
 request → AuthN (who are you?)       x509 client certs, ServiceAccount tokens (JWT), OIDC (SSO), webhook (EKS IAM)
         → AuthZ (may you do this?)   Node authorizer, RBAC, webhook — any "allow" wins, default deny
         → Admission                  mutate/validate (PSA, ValidatingAdmissionPolicy, webhooks like Kyverno/Gatekeeper)
```

Kubernetes has **no User objects** — users come from certificates/OIDC/cloud IAM. ServiceAccounts **are** API objects.

---

## 3. RBAC

| Object | Scope | Purpose |
|--------|-------|---------|
| `Role` | namespace | permissions within one namespace |
| `ClusterRole` | cluster | cluster-scoped resources (nodes, PVs) or reusable permissions for any namespace |
| `RoleBinding` | namespace | grant a Role **or ClusterRole** to subjects in one namespace |
| `ClusterRoleBinding` | cluster | grant a ClusterRole across all namespaces |

Subjects: `User`, `Group`, `ServiceAccount`. Verbs: `get list watch create update patch delete deletecollection` (+ special:
`impersonate`, `bind`, `escalate`, `use`, subresources like `pods/exec`, `pods/log`).

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata: { name: pod-reader, namespace: dev }
rules:
  - apiGroups: [""]                     # "" = core group (pods, services, configmaps)
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "patch"]
    resourceNames: ["web"]              # only this object
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata: { name: alice-pod-reader, namespace: dev }
subjects:
  - kind: User
    name: alice                          # from cert CN / OIDC claim
    apiGroup: rbac.authorization.k8s.io
  - kind: Group
    name: dev-team
    apiGroup: rbac.authorization.k8s.io
  - kind: ServiceAccount
    name: ci-bot
    namespace: dev
roleRef:                                 # immutable
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

Built-in ClusterRoles: `cluster-admin`, `admin` (namespace admin), `edit`, `view`. **Aggregated** ClusterRoles combine rules via
labels (CRD authors add `rbac.authorization.k8s.io/aggregate-to-view: "true"`).

### Lab — create a user with a client certificate and test RBAC

```bash
kubectl create namespace dev
openssl genrsa -out alice.key 2048
openssl req -new -key alice.key -out alice.csr -subj "/CN=alice/O=dev-team"     # CN = username, O = group
cat <<EOF | kubectl apply -f -
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata: { name: alice }
spec:
  request: $(base64 -w0 alice.csr)
  signerName: kubernetes.io/kube-apiserver-client
  expirationSeconds: 86400
  usages: ["client auth"]
EOF
kubectl certificate approve alice
kubectl get csr alice -o jsonpath='{.status.certificate}' | base64 -d > alice.crt
kubectl config set-credentials alice --client-certificate=alice.crt --client-key=alice.key --embed-certs=true
kubectl config set-context alice@lab --cluster=$(kubectl config view --minify -o jsonpath='{.clusters[0].name}') --user=alice --namespace=dev

kubectl --context alice@lab get pods                   # Forbidden
kubectl create role pod-reader -n dev --verb=get,list,watch --resource=pods
kubectl create rolebinding alice-read -n dev --role=pod-reader --user=alice
kubectl --context alice@lab get pods                   # works (No resources found)
kubectl --context alice@lab get secrets                # Forbidden
kubectl auth can-i list pods -n dev --as alice         # yes — impersonation test as admin
kubectl auth can-i --list -n dev --as alice
kubectl auth can-i create pods --as system:serviceaccount:dev:default -n dev
```

### Dangerous permissions (privilege escalation paths)

| Permission | Why dangerous |
|-----------|---------------|
| `create pods` (any workload) | mount any Secret/SA in the namespace, run privileged if admission allows |
| `get/list secrets` | read all credentials |
| `pods/exec`, `nodes/proxy` | run commands in containers / on kubelets |
| `escalate`, `bind` on roles | grant yourself more |
| `impersonate` | act as anyone |
| `*` on `*` | cluster-admin |
| `patch` on namespaces/nodes labels | bypass PSA labels or scheduling restrictions |

---

## 4. ServiceAccounts

Every Pod runs as a ServiceAccount (`default` if unspecified). The kubelet mounts a **projected, short-lived, audience-bound token**
at `/var/run/secrets/kubernetes.io/serviceaccount/token` (auto-rotated, ~1 h, bound to the Pod's lifetime).

```yaml
apiVersion: v1
kind: ServiceAccount
metadata: { name: api, namespace: shop }
automountServiceAccountToken: false      # most apps never call the K8s API — don't give them a token
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: api, namespace: shop }
spec:
  selector: { matchLabels: { app: api } }
  template:
    metadata: { labels: { app: api } }
    spec:
      serviceAccountName: api
      automountServiceAccountToken: false
      containers: [{ name: api, image: ghcr.io/example/api:1.0.0 }]
```

```bash
kubectl create token api -n shop --duration=10m          # mint a short-lived token (e.g. for testing)
```

⚠️ Since v1.24 no long-lived token Secrets are auto-created. Don't create `kubernetes.io/service-account-token` Secrets unless
truly needed.

Cloud identity for Pods (no static keys): **EKS Pod Identity** / IRSA, GKE Workload Identity, Azure Workload Identity.

---

## 5. Pod Security Standards and Pod Security Admission

⚠️ **PodSecurityPolicy was removed in v1.25.** Replacement: built-in **Pod Security Admission (PSA)** enforcing the
**Pod Security Standards**:

| Level | Allows |
|-------|--------|
| `privileged` | everything |
| `baseline` | blocks known escalations: privileged, hostNetwork/PID/IPC, hostPath, added dangerous capabilities, hostPorts |
| `restricted` | baseline + must run as non-root, drop ALL capabilities, `allowPrivilegeEscalation: false`, seccomp RuntimeDefault, restricted volume types |

Configured with **namespace labels**:

```bash
kubectl label namespace shop \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/warn=restricted \
  pod-security.kubernetes.io/audit=restricted
kubectl -n shop run bad --image=nginx:1.27            # rejected/warned: violates restricted (runs as root, no seccomp…)
kubectl label --dry-run=server --overwrite ns --all pod-security.kubernetes.io/enforce=baseline   # preview impact cluster-wide
```

Modes: `enforce` (reject), `audit` (audit log annotation), `warn` (kubectl warning). Roll out with warn/audit first.

---

## 6. SecurityContext, capabilities, privileged containers

```yaml
apiVersion: v1
kind: Pod
metadata: { name: hardened }
spec:
  securityContext:                        # Pod-level
    runAsNonRoot: true
    runAsUser: 10001
    runAsGroup: 10001
    fsGroup: 10001
    seccompProfile: { type: RuntimeDefault }   # blocks ~dangerous syscalls
  hostUsers: false                        # user namespaces: root in container ≠ root on host (newer clusters)
  containers:
    - name: app
      image: nginxinc/nginx-unprivileged:1.27   # listens on 8080, runs as non-root
      ports: [{ containerPort: 8080 }]
      securityContext:                    # container-level (overrides Pod-level)
        allowPrivilegeEscalation: false   # no setuid gaining privileges (no_new_privs)
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
          # add: ["NET_BIND_SERVICE"]     # only if binding <1024 as non-root
        privileged: false
      volumeMounts:
        - { name: tmp, mountPath: /tmp }  # writable scratch since rootfs is read-only
  volumes:
    - name: tmp
      emptyDir: {}
```

```bash
kubectl apply -f hardened.yaml
kubectl exec hardened -- id                         # uid=10001
kubectl exec hardened -- sh -c 'touch /etc/x'      # Read-only file system
kubectl exec hardened -- grep -E 'Cap(Eff|Bnd)' /proc/1/status   # 0000000000000000 = no capabilities
```

**`privileged: true`** = all capabilities + all devices + no seccomp/AppArmor confinement ≈ root on the node. Only for low-level
infrastructure (some CNI/CSI agents). Same for `hostPID`, `hostNetwork`, `hostPath: /`.

---

## 7. Admission controllers and admission policies

Built-in admission plugins (enabled by default): `NamespaceLifecycle`, `LimitRanger`, `ServiceAccount`, `DefaultStorageClass`,
`ResourceQuota`, `PodSecurity`, `NodeRestriction`, `MutatingAdmissionWebhook`, `ValidatingAdmissionWebhook`,
`ValidatingAdmissionPolicy`…

### ValidatingAdmissionPolicy (GA v1.30) — CEL rules in-process, no webhook to run

```yaml
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicy
metadata: { name: require-image-tag-and-registry }
spec:
  failurePolicy: Fail
  matchConstraints:
    resourceRules:
      - apiGroups: ["apps"]
        apiVersions: ["v1"]
        operations: ["CREATE", "UPDATE"]
        resources: ["deployments"]
  validations:
    - expression: >-
        object.spec.template.spec.containers.all(c,
          c.image.startsWith('ghcr.io/example/') && !c.image.endsWith(':latest') && c.image.contains(':'))
      message: "Images must come from ghcr.io/example/ and use a pinned, non-latest tag."
---
apiVersion: admissionregistration.k8s.io/v1
kind: ValidatingAdmissionPolicyBinding
metadata: { name: require-image-tag-and-registry }
spec:
  policyName: require-image-tag-and-registry
  validationActions: ["Deny"]             # or Warn / Audit for rollout
  matchResources:
    namespaceSelector:
      matchLabels: { env: prod }
```

**MutatingAdmissionPolicy** (CEL-based mutation) is newer (beta). For richer policy (generate resources, image verification,
mutate), use **Kyverno** or **OPA Gatekeeper** (webhooks).

---

## 8. Image security (supply chain)

1. **Minimal base images**: distroless, Chainguard/Wolfi, `-slim`, scratch for Go.
2. **Scan**: Trivy/Grype in CI and in registry; fail on critical CVEs with fixes.
   ```bash
   trivy image --severity HIGH,CRITICAL --ignore-unfixed nginx:1.27
   trivy k8s --report summary cluster        # scan running workloads and misconfigs
   ```
3. **Pin by digest** in production: `image: ghcr.io/example/api@sha256:...`.
4. **Sign and verify**: Sigstore `cosign sign`, verify at admission (Kyverno `verifyImages`, policy-controller).
5. **SBOMs and provenance** (SLSA): `syft`, `docker buildx --sbom --provenance`.
6. **Private registries** with pull secrets or node IAM (ECR), restricted registries via policy.
7. **No secrets in images**; non-root `USER` in Dockerfile.

---

## 9. Secrets security (recap from chapter 07)

KMS encryption at rest, least-privilege RBAC on secrets, external secret stores, volume mounts over env vars, rotation,
audit logging of secret access.

## 10. Network security (recap)

Default-deny NetworkPolicies + DNS allow ([05.09](../05-networking/09-network-policies/README.md)), block cloud metadata
(`169.254.169.254`; on EKS set IMDSv2 hop limit 1), mTLS via mesh, private API endpoint, restrict NodePorts/LBs with
`loadBalancerSourceRanges` and security groups.

## 11. Runtime security

| Control | Tool |
|---------|------|
| Syscall filtering | seccomp `RuntimeDefault` / custom profiles (Security Profiles Operator) |
| MAC | AppArmor (Ubuntu): `securityContext.appArmorProfile: { type: RuntimeDefault }`; SELinux on RHEL |
| Detection | **Falco** (eBPF syscall rules: "shell spawned in container", "write below /etc"), Tetragon (Cilium) |
| Sandboxed runtimes | gVisor (`runsc`), Kata Containers via `RuntimeClass` for untrusted workloads |
| Node hardening | CIS benchmarks (`kube-bench`), minimal OS (Bottlerocket, Talos, Flatcar), patch cadence |
| Audit | API server audit policy → SIEM |

```yaml
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata: { name: gvisor }
handler: runsc            # Pods with runtimeClassName: gvisor run in a user-space kernel sandbox
```

---

## 12. Cluster hardening checklist

- [ ] API server private or IP-restricted; anonymous auth off; audit logging on
- [ ] etcd encrypted, TLS, not reachable from nodes/Pods
- [ ] RBAC least privilege; no `cluster-admin` for humans day-to-day; SSO via OIDC
- [ ] PSA `restricted` (or `baseline` minimum) on app namespaces
- [ ] Admission policies: trusted registries, no `latest`, resource limits required, no privileged
- [ ] `automountServiceAccountToken: false` by default
- [ ] Default-deny NetworkPolicies
- [ ] Images scanned, signed, pinned
- [ ] Secrets in KMS/external store
- [ ] Runtime detection (Falco) and node hardening (kube-bench)
- [ ] Regular upgrades (supported minor versions)

---

## Interview questions

1. **Role vs ClusterRole; RoleBinding vs ClusterRoleBinding?** Namespace vs cluster scope; a RoleBinding can grant a ClusterRole
   within one namespace.
2. **How do users authenticate?** Certificates, OIDC tokens, cloud IAM webhooks — there are no User objects.
3. **What replaced PodSecurityPolicy?** Pod Security Admission with privileged/baseline/restricted levels via namespace labels.
4. **What does `allowPrivilegeEscalation: false` do?** Sets no_new_privs so processes can't gain privileges (setuid).
5. **Why drop ALL capabilities?** Minimises kernel privileges available to an attacker.
6. **Why is `create pods` sensitive?** Pods can mount any Secret/SA in the namespace and potentially run privileged.
7. **What is ValidatingAdmissionPolicy?** In-process CEL validation rules — policy without running a webhook.
8. **How do Pods get cloud permissions safely?** Workload identity (EKS Pod Identity/IRSA) instead of static keys.
9. **How to secure the supply chain?** Scan, sign (cosign), verify at admission, pin digests, SBOMs.
10. **What is Falco?** Runtime threat detection based on kernel syscall events.

**Scenario:** A pentester got a shell in a Pod and listed all Secrets. → The Pod's SA had broad RBAC; fix: dedicated SAs, no token
automount, least-privilege roles, NetworkPolicy, PSA restricted, audit.

**Follow-ups:** How does the NodeRestriction admission plugin limit kubelets? How do user namespaces change container escape risk?
How would you detect privilege escalation via audit logs?
