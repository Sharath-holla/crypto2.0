# 12 — Helm

## 1. What Helm is and why

Real apps need 10–30 YAML objects that differ slightly per environment. **Helm** is the Kubernetes package manager:

| Term | Meaning |
|------|---------|
| **Chart** | a package: templates + default values + metadata |
| **Values** | configuration inputs (`values.yaml`, `-f prod.yaml`, `--set`) |
| **Release** | an installed instance of a chart in a namespace (`helm install shop ./chart`) |
| **Revision** | each install/upgrade/rollback of a release (stored for rollback) |
| **Repository** | an index of charts over HTTP, or an **OCI registry** (ECR, GHCR, Docker Hub) |

### Architecture

```text
 helm CLI (client only — no Tiller since Helm 3)
   1. load chart + merge values (chart defaults ← parent chart ← -f files ← --set)
   2. render templates (Go templates + Sprig functions) → plain YAML
   3. send to the API server with YOUR kubeconfig credentials (RBAC applies)
   4. store release record as a Secret in the release namespace: sh.helm.release.v1.<name>.v<revision>
```

> ⚠️ Helm 2's in-cluster **Tiller** is long gone. **Helm 4** (released Nov 2025) keeps the same core workflow
> (`install/upgrade/rollback`, charts `apiVersion: v2`) and adds things like server-side apply support and a new plugin system;
> Helm 3 remains supported for a transition period. Commands in this chapter work on both.

## 2. Install Helm

```bash
curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 | bash   # or get-helm-3
# Script installs to /usr/local/bin with sudo. Prefer reading scripts before piping to bash:
#   curl -fsSLo get-helm.sh https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-4 && less get-helm.sh && bash get-helm.sh
helm version
```

## 3. Using charts

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update                                           # refresh indexes
helm search repo prometheus                                # search added repos
helm search hub nginx                                      # search Artifact Hub
helm show values prometheus-community/prometheus | less    # all configurable values
helm install mon prometheus-community/prometheus -n monitoring --create-namespace --version 27.x.x -f my-values.yaml
helm list -A                                               # releases in all namespaces
helm status mon -n monitoring
helm get values mon -n monitoring                          # values you supplied
helm get manifest mon -n monitoring | less                 # rendered YAML actually applied
helm upgrade mon prometheus-community/prometheus -n monitoring -f my-values.yaml --atomic --timeout 10m
helm history mon -n monitoring
helm rollback mon 1 -n monitoring                          # back to revision 1 (creates a new revision)
helm uninstall mon -n monitoring                           # removes resources (not CRDs, not PVCs from StatefulSets)
# OCI registries (no "repo add" needed):
helm install eg oci://docker.io/envoyproxy/gateway-helm --version v1.5.0 -n envoy-gateway-system --create-namespace
helm pull oci://ghcr.io/example/charts/shop --version 1.2.0
```

Flags worth knowing: `--atomic` (roll back automatically on failure; called `--rollback-on-failure` in Helm 4), `--wait`,
`--timeout`, `--dry-run=server`, `--reuse-values` (⚠️ surprising merges — prefer passing full values files), `--install` on
upgrade (`helm upgrade --install` = idempotent deploy for CI).

Note: Bitnami moved most free images/charts behind a commercial offering in 2025 (old images under `bitnamilegacy`). Prefer
upstream/project-maintained charts.

## 4. Create your own chart

```bash
helm create shop
tree shop
```

```text
shop/
├── Chart.yaml            # name, version (chart), appVersion (app), dependencies
├── values.yaml           # defaults
├── values.schema.json    # (optional, recommended) JSON Schema validation for values
├── charts/               # dependency charts (vendored by `helm dependency update`)
├── templates/
│   ├── _helpers.tpl      # named templates (labels, names)
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml / httproute.yaml
│   ├── hpa.yaml
│   ├── serviceaccount.yaml
│   ├── NOTES.txt         # printed after install
│   └── tests/test-connection.yaml
└── .helmignore
```

### Chart.yaml

```yaml
apiVersion: v2
name: shop
description: Shop web application
type: application        # or library (helpers only)
version: 0.3.0           # CHART version — bump on every chart change (SemVer)
appVersion: "1.4.2"      # app/image version (informational; often the default image tag)
dependencies:
  - name: postgresql-ha-example        # example dependency
    version: "~1.2.0"
    repository: "oci://registry.example.com/charts"
    condition: postgresql.enabled      # toggle via values
```

### values.yaml

```yaml
replicaCount: 2
image:
  repository: ghcr.io/example/shop
  tag: ""                 # defaults to .Chart.AppVersion
  pullPolicy: IfNotPresent
service:
  type: ClusterIP
  port: 80
  targetPort: 8080
resources:
  requests: { cpu: 100m, memory: 128Mi }
  limits: { memory: 256Mi }
autoscaling:
  enabled: false
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 60
env: {}
config:
  LOG_LEVEL: info
ingress:
  enabled: false
  className: ""
  host: shop.example.com
```

### templates/_helpers.tpl

```gotemplate
{{- define "shop.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "shop.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "shop.labels" -}}
{{ include "shop.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}
```

### templates/configmap.yaml and deployment.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "shop.fullname" . }}
  labels: {{- include "shop.labels" . | nindent 4 }}
data:
  {{- range $k, $v := .Values.config }}
  {{ $k }}: {{ $v | quote }}
  {{- end }}
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "shop.fullname" . }}
  labels: {{- include "shop.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}       # let HPA own replicas when enabled
  {{- end }}
  selector:
    matchLabels: {{- include "shop.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels: {{- include "shop.selectorLabels" . | nindent 8 }}
      annotations:
        # roll Pods when config changes
        checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}
    spec:
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: {{ .Values.service.targetPort }}
          envFrom:
            - configMapRef:
                name: {{ include "shop.fullname" . }}
          {{- with .Values.env }}
          env:
            {{- range $name, $value := . }}
            - name: {{ $name }}
              value: {{ $value | quote }}
            {{- end }}
          {{- end }}
          readinessProbe:
            httpGet: { path: /healthz, port: http }
          resources: {{- toYaml .Values.resources | nindent 12 }}
```

Template essentials:

| Syntax | Meaning |
|--------|---------|
| `{{ .Values.x }}` | value lookup; `.Release.Name`, `.Release.Namespace`, `.Chart.Version`, `.Capabilities.KubeVersion` |
| `{{- ... -}}` | trim whitespace left/right |
| `if / else / with / range` | control flow (`with` changes `.` scope) |
| `include "name" .` + `nindent N` | reuse named template, indent correctly |
| `toYaml`, `quote`, `default`, `required "msg" .Values.x`, `tpl` | common functions |
| `lookup` | read live cluster objects (empty during `helm template`) |

### Develop and test

```bash
helm lint ./shop
helm template shop ./shop -f values-prod.yaml | less        # render locally
helm template shop ./shop | kubeconform -strict -summary     # schema-validate rendered output
helm install shop ./shop -n shop --create-namespace --dry-run=server --debug
helm install shop ./shop -n shop --create-namespace
helm test shop -n shop                                        # runs Pods annotated helm.sh/hook: test
helm upgrade shop ./shop -n shop --set replicaCount=4
helm rollback shop -n shop
helm package ./shop                                           # shop-0.3.0.tgz
helm push shop-0.3.0.tgz oci://ghcr.io/example/charts         # after `helm registry login ghcr.io`
```

### Environment overrides

```text
values.yaml            # defaults
values-dev.yaml        # replicaCount: 1, resources small
values-prod.yaml       # replicaCount: 3, autoscaling.enabled: true, ingress.enabled: true
helm upgrade --install shop ./shop -n shop -f values-prod.yaml --set image.tag=$GIT_SHA
```

Precedence (low → high): chart `values.yaml` → parent chart values → `-f` files in order → `--set`/`--set-string`/`--set-file`.

## 5. Dependencies

```bash
helm dependency update ./shop      # downloads into charts/, writes Chart.lock
helm dependency list ./shop
```

Parent values for a subchart go under its name: `postgresql-ha-example: { auth: { ... } }`. `global:` values are visible to all
subcharts.

## 6. Hooks

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "shop.fullname" . }}-migrate
  annotations:
    "helm.sh/hook": pre-upgrade,pre-install      # also: post-install, pre-delete, post-delete, pre-rollback, post-rollback, test
    "helm.sh/hook-weight": "0"                    # order among hooks
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrate
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          command: ["python", "manage.py", "migrate"]
```

Hook resources are **not** part of the release manifest (not deleted on uninstall unless a delete policy says so).
Migrations must be backward compatible (old Pods still running during rolling update).

## 7. Customisation patterns and alternatives

| Need | Approach |
|------|----------|
| Small env differences | values files |
| Patch a third-party chart's output | `helm template` + Kustomize, or Helm `--post-renderer` |
| No templating at all | **Kustomize** (`kubectl apply -k`), overlays per env |
| GitOps | Argo CD / Flux render Helm charts declaratively (chapter 14) |

| | Helm | Kustomize |
|--|------|-----------|
| Model | templates + values | patches over plain YAML |
| Packaging/versioning | ✅ charts, repos, OCI | ❌ |
| Release history/rollback | ✅ | ❌ (Git is history) |
| Learning curve | Go templates | simpler |

## 8. Common mistakes

- Not bumping chart `version` → caches/registries serve old content.
- Indentation bugs (use `nindent`, `toYaml`), quoting numbers-as-strings (`quote`).
- `--reuse-values` + new chart defaults → unexpected merges.
- Secrets in `values.yaml` committed to Git → use External Secrets / SOPS (`helm-secrets`).
- Stuck release `another operation (install/upgrade/rollback) is in progress` → `helm history`, then `helm rollback` to the last
  good revision (as a last resort, delete the pending release Secret).
- CRDs in `crds/` are installed once and **never upgraded** by Helm — manage CRD upgrades separately.
- Changing immutable fields (Deployment selector labels) → upgrade fails; never change selector labels in helpers.

---

## Interview questions

1. **What is Helm?** Kubernetes package manager: charts (templates + values) installed as versioned releases.
2. **Chart vs release vs repository?** Package / installed instance / place to store charts.
3. **Where does Helm 3+ store release state?** As Secrets in the release namespace.
4. **How do you roll back?** `helm rollback <release> <revision>`.
5. **Value precedence?** Chart defaults < parent < `-f` files (in order) < `--set`.
6. **What are hooks?** Annotated resources run at lifecycle points (pre-install, pre-upgrade, test…), e.g. DB migrations.
7. **`version` vs `appVersion`?** Chart package version vs application version.
8. **How do you validate a chart?** `helm lint`, `helm template | kubeconform`, values schema, `--dry-run=server`, `helm test`.
9. **How do you force Pods to restart when a ConfigMap changes?** checksum annotation in the Pod template.
10. **Helm vs Kustomize?** Templating + packaging + releases vs patch-based overlays on plain YAML.

**Scenario:** `helm upgrade` failed halfway and now every upgrade says "another operation is in progress". → Check
`helm history`, roll back to last deployed revision; investigate failing resource; use `--atomic` in CI.

**Follow-ups:** How does Helm compute the diff/patch it applies (three-way merge; server-side apply in Helm 4)? How do library charts
work? How would you sign and verify charts (provenance, cosign for OCI)?
