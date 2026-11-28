# 07 — Configuration & Secrets

## 1. Why externalise configuration

Twelve-factor rule: **the same image runs in dev, staging and prod; only configuration changes**. Baking config or passwords
into images forces rebuilds and leaks secrets into registries.

| Object | For | Stored as | Size limit |
|--------|-----|-----------|-----------|
| ConfigMap | non-sensitive config (URLs, flags, files) | plain text in etcd | 1 MiB |
| Secret | sensitive data (passwords, tokens, keys, certs) | **base64** in etcd (encrypt at rest!) | 1 MiB |

> ⚠️ base64 is **encoding, not encryption**. Anyone who can `get secrets` in a namespace can read them.

---

## 2. ConfigMaps

```bash
kubectl create configmap app-config \
  --from-literal=LOG_LEVEL=info \
  --from-literal=FEATURE_X=true \
  --from-file=nginx.conf=./nginx.conf \
  --dry-run=client -o yaml > app-config.yaml
# --from-file=KEY=PATH → key "nginx.conf" whose value is the file's content
kubectl create configmap env-file --from-env-file=app.env   # KEY=VALUE lines
```

```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: app-config }
data:
  LOG_LEVEL: "info"
  FEATURE_X: "true"
  application.yaml: |
    server:
      port: 8080
    cache:
      ttlSeconds: 60
immutable: false          # true = can't change (protects prod, reduces API watch load); recreate to update
```

### Consuming config — four ways

```yaml
apiVersion: v1
kind: Pod
metadata: { name: config-demo }
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "env | grep -E 'LOG|FEAT|MODE'; cat /etc/app/application.yaml; sleep 3600"]
      env:
        - name: LOG_LEVEL                 # 1) single key → env var
          valueFrom:
            configMapKeyRef: { name: app-config, key: LOG_LEVEL }
        - name: MODE                      # plain value
          value: "production"
      envFrom:                            # 2) all keys → env vars (keys must be valid env names)
        - configMapRef: { name: app-config }
          prefix: CFG_
      volumeMounts:
        - name: config                    # 3) keys → files
          mountPath: /etc/app
          readOnly: true
      args: ["--log-level=$(LOG_LEVEL)"]  # 4) env var expansion into args
  volumes:
    - name: config
      configMap:
        name: app-config
        items:                            # optional: pick keys and file names
          - { key: application.yaml, path: application.yaml }
```

### Updates — what refreshes and what doesn't

| Consumption | Updated automatically? |
|-------------|----------------------|
| env / envFrom | ❌ only at container start → restart Pods (`kubectl rollout restart`) |
| volume mount | ✅ eventually (kubelet sync, ~1 min; atomic symlink swap) — app must re-read the file |
| volume with `subPath` | ❌ never |
| immutable ConfigMap | ❌ by design |

Production pattern: put a **hash of the config** in a Pod template annotation (Helm:
`checksum/config: {{ include (print $.Template.BasePath "/configmap.yaml") . | sha256sum }}`) so config changes trigger a rollout.
Or name ConfigMaps with content hashes (Kustomize `configMapGenerator` does this) for safe rollbacks.

---

## 3. Secrets

### Types

| Type | Use |
|------|-----|
| `Opaque` | generic key/values |
| `kubernetes.io/tls` | `tls.crt` + `tls.key` (Ingress/Gateway) |
| `kubernetes.io/dockerconfigjson` | image pull credentials |
| `kubernetes.io/basic-auth`, `ssh-auth` | conventions |
| `kubernetes.io/service-account-token` | ⚠️ legacy long-lived SA tokens — prefer projected tokens |

```bash
kubectl create secret generic db-cred --from-literal=username=app --from-literal=password='S3cr3t!'
kubectl get secret db-cred -o yaml                       # data: base64 values
kubectl get secret db-cred -o jsonpath='{.data.password}' | base64 -d; echo
kubectl create secret tls web-tls --cert=tls.crt --key=tls.key
```

```yaml
apiVersion: v1
kind: Secret
metadata: { name: db-cred }
type: Opaque
stringData:                  # write plain text; API stores it base64 in .data
  username: app
  password: "S3cr3t!"
```

> Never commit Secret YAML with real values to Git. Use Sealed Secrets, SOPS, or External Secrets (below).

Consuming is identical to ConfigMaps (`secretKeyRef`, `secretRef`, `secret:` volume). Prefer **volume mounts** over env vars:
env vars leak via `/proc/<pid>/environ`, crash dumps, child processes and debug endpoints. Secret volumes are **tmpfs**
(never written to node disk).

```yaml
volumes:
  - name: creds
    secret:
      secretName: db-cred
      defaultMode: 0400        # file permissions
```

---

## 4. Downward API and projected volumes

```yaml
env:
  - name: POD_NAME
    valueFrom: { fieldRef: { fieldPath: metadata.name } }
  - name: POD_IP
    valueFrom: { fieldRef: { fieldPath: status.podIP } }
  - name: MEM_LIMIT
    valueFrom: { resourceFieldRef: { containerName: app, resource: limits.memory } }
volumes:
  - name: all-in-one
    projected:
      sources:
        - configMap: { name: app-config }
        - secret: { name: db-cred }
        - downwardAPI:
            items: [{ path: labels, fieldRef: { fieldPath: metadata.labels } }]
        - serviceAccountToken:              # short-lived, audience-bound token (auto-rotated)
            audience: vault
            expirationSeconds: 3600
            path: vault-token
```

---

## 5. Secret management and encryption at rest

### Who can read Secrets?

- Anyone with RBAC `get/list/watch` on secrets in the namespace (**`list` returns values too**).
- Anyone who can **create Pods** in the namespace (they can mount any Secret there).
- Node kubelets (only Secrets for their Pods, enforced by the Node authorizer).
- Anyone with etcd or etcd backup access → hence encryption at rest.

### Encryption at rest (self-managed clusters)

```yaml
# /etc/kubernetes/enc/encryption-config.yaml  (on every control-plane node, root-only)
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources: ["secrets"]
    providers:
      - kms:                          # ✅ best: envelope encryption with an external KMS (KMS v2)
          apiVersion: v2
          name: aws-kms
          endpoint: unix:///var/run/kmsplugin/socket.sock
      - aescbc:                       # local key alternative (key lives on the node)
          keys:
            - name: key1
              secret: REPLACE_WITH_BASE64_32_BYTE_KEY   # generate: head -c 32 /dev/urandom | base64
      - identity: {}                  # fallback to read old unencrypted data
```

Add `--encryption-provider-config=/etc/kubernetes/enc/encryption-config.yaml` to the kube-apiserver static Pod manifest (and mount
the directory), then rewrite existing Secrets so they get encrypted:

```bash
kubectl get secrets -A -o json | kubectl replace -f -
# verify on control plane: value in etcd should start with k8s:enc:
sudo ETCDCTL_API=3 etcdctl --cacert=/etc/kubernetes/pki/etcd/ca.crt --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key get /registry/secrets/default/db-cred | hexdump -C | head
```

EKS encrypts etcd volumes by default and also supports **envelope encryption of Secrets with AWS KMS** (on by default for new
clusters on recent platform versions).

### External secret management

| Tool | How |
|------|-----|
| **External Secrets Operator** | `ExternalSecret` CR syncs from AWS Secrets Manager/SSM, Vault, GCP, Azure into K8s Secrets |
| **Secrets Store CSI Driver** | mounts secrets from a vault directly as files (optionally syncs to K8s Secret) |
| **HashiCorp Vault Agent injector** | sidecar fetches/renews secrets |
| **Sealed Secrets** | encrypt with controller's public key → safe to commit; controller decrypts in-cluster |
| **SOPS** (+ age/KMS) | encrypt YAML values in Git; decrypt in CI/Argo CD/Flux |

External Secrets example:

```yaml
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata: { name: aws-sm, namespace: shop }
spec:
  provider:
    aws:
      service: SecretsManager
      region: us-east-1
      auth:
        jwt:
          serviceAccountRef: { name: external-secrets-sa }   # IRSA / Pod Identity, no static keys
---
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata: { name: db-cred, namespace: shop }
spec:
  refreshInterval: 1h
  secretStoreRef: { name: aws-sm, kind: SecretStore }
  target: { name: db-cred }                       # K8s Secret to create/maintain
  data:
    - secretKey: password
      remoteRef: { key: prod/shop/db, property: password }
```

---

## 6. Best practices

1. No secrets in images, Git, env files in repos, or Helm values committed in plain text.
2. RBAC: avoid granting `list secrets`; separate namespaces per team/app.
3. Encrypt at rest with KMS; restrict etcd and backup access.
4. Mount as files, read-only, minimal `defaultMode`; avoid logging config dumps.
5. Short-lived credentials (projected SA tokens, workload identity: EKS Pod Identity/IRSA) instead of static keys.
6. Rotate secrets; design apps to reload (watch files) or roll Pods on change (Reloader controller, checksum annotations).
7. `immutable: true` for configs that shouldn't change in place.
8. Validate config in CI (schema, policy).

---

## Lab — config end to end

```bash
kubectl create namespace cfg
kubectl -n cfg create configmap web-html --from-literal=index.html='<h1>Hello v1</h1>'
kubectl -n cfg create secret generic api-key --from-literal=key=abc123
cat <<'EOF' | kubectl -n cfg apply -f -
apiVersion: apps/v1
kind: Deployment
metadata: { name: web }
spec:
  replicas: 1
  selector: { matchLabels: { app: web } }
  template:
    metadata: { labels: { app: web } }
    spec:
      containers:
        - name: nginx
          image: nginx:1.27
          env:
            - name: API_KEY
              valueFrom: { secretKeyRef: { name: api-key, key: key } }
          volumeMounts:
            - { name: html, mountPath: /usr/share/nginx/html }
            - { name: secret, mountPath: /etc/secret, readOnly: true }
      volumes:
        - { name: html, configMap: { name: web-html } }
        - { name: secret, secret: { secretName: api-key, defaultMode: 0400 } }
EOF
kubectl -n cfg exec deploy/web -- curl -s localhost                  # Hello v1
kubectl -n cfg exec deploy/web -- sh -c 'echo $API_KEY; ls -l /etc/secret; mount | grep secret'   # tmpfs
kubectl -n cfg create configmap web-html --from-literal=index.html='<h1>Hello v2</h1>' --dry-run=client -o yaml | kubectl -n cfg apply -f -
sleep 70; kubectl -n cfg exec deploy/web -- curl -s localhost        # Hello v2 without restart (volume)
kubectl -n cfg create secret generic api-key --from-literal=key=zzz999 --dry-run=client -o yaml | kubectl -n cfg apply -f -
kubectl -n cfg exec deploy/web -- sh -c 'echo $API_KEY'              # still abc123 (env not refreshed)
kubectl -n cfg rollout restart deploy/web && kubectl -n cfg rollout status deploy/web
kubectl -n cfg exec deploy/web -- sh -c 'echo $API_KEY'              # zzz999
kubectl delete ns cfg
```

---

## Interview questions

1. **ConfigMap vs Secret?** Both key/value config; Secrets are for sensitive data, base64-encoded, tmpfs-mounted, with tighter
   handling — but not encrypted unless encryption at rest is enabled.
2. **Is a Secret encrypted?** Not by default; base64 only. Enable KMS/aescbc encryption at rest.
3. **Env var vs volume?** Env set once at start; volumes refresh (except subPath) and avoid env leakage.
4. **How do Pods pick up ConfigMap changes?** Volumes update eventually; env needs restart; use checksum annotations/Reloader.
5. **How to store secrets in Git safely?** Sealed Secrets or SOPS; or keep them in a vault with External Secrets.
6. **Who can read Secrets?** RBAC get/list/watch, anyone who can create Pods in the namespace, etcd access.
7. **What is an immutable ConfigMap?** Cannot be updated; protects against accidental change and reduces watch load.
8. **What is the Downward API?** Exposes Pod metadata/resources to containers via env or files.
9. **Why prefer projected SA tokens?** Short-lived, audience-bound, auto-rotated vs legacy permanent tokens.
10. **Size limit?** 1 MiB per object.

**Scenario:** A developer ran `kubectl get secret -o yaml` and pasted it into a ticket. → Rotate the credential immediately,
audit RBAC, move to external secrets.

**Follow-ups:** How does KMS v2 envelope encryption work (DEK per object encrypted by KEK)? How would you rotate the
encryption key?
