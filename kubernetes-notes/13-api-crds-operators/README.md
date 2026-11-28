# 13 — Kubernetes API, CRDs & Operators

## 1. The API in depth

Kubernetes is **an API server plus controllers**. Everything — kubectl, Helm, Argo CD, the scheduler — is a client of the same
REST API.

| Concept | Meaning | Example |
|---------|---------|---------|
| **Group** | family of related kinds | core (`""`), `apps`, `batch`, `networking.k8s.io`, `rbac.authorization.k8s.io` |
| **Version** | maturity of the API | `v1alpha1` (off by default, may change) → `v1beta1` → `v1` (stable) |
| **Kind** | object type (CamelCase) | `Deployment` |
| **Resource** | URL plural (lowercase) | `deployments` |
| **GVK / GVR** | Group-Version-Kind / Group-Version-Resource | `apps/v1, Kind=Deployment` / `apps/v1/deployments` |
| **Subresource** | special endpoint | `/status`, `/scale`, `/log`, `/exec`, `/eviction`, `/binding`, `/resize` |

### Discovery

```bash
kubectl api-resources -o wide                 # resources with verbs and short names
kubectl api-versions
kubectl get --raw /apis | jq '.groups[].name' | head
kubectl get --raw /apis/apps/v1 | jq '.resources[].name'
kubectl get --raw /openapi/v3 | jq '.paths | keys | length'   # OpenAPI schemas (kubectl explain uses these)
kubectl explain deployment.spec.template.spec.containers.resources
```

### Talk to the API with curl

```bash
kubectl proxy --port=8001 &                   # authenticated local proxy using your kubeconfig
curl -s localhost:8001/api/v1/namespaces/default/pods | jq '.items[].metadata.name'
curl -s localhost:8001/apis/apps/v1/namespaces/default/deployments/web | jq '.status'
curl -s -X PATCH -H 'Content-Type: application/merge-patch+json' \
  -d '{"spec":{"replicas":3}}' localhost:8001/apis/apps/v1/namespaces/default/deployments/web/scale
```

### Watch mechanism

```bash
curl -s "localhost:8001/api/v1/namespaces/default/pods?watch=1&resourceVersion=0"
# streams JSON lines: {"type":"ADDED","object":{...}} {"type":"MODIFIED",...} {"type":"DELETED",...}
kubectl get pods -w --output-watch-events
```

- Every object has a `resourceVersion` (etcd revision). A watch says "send changes after RV X".
- If the RV is too old (compacted), the server returns **410 Gone** → client must re-list.
- **Optimistic concurrency**: an update with a stale `resourceVersion` fails with **409 Conflict** → re-read and retry.

### Apply semantics

| | Client-side apply | **Server-side apply** (✅) |
|--|-------------------|------------------------|
| Merge computed by | kubectl (last-applied annotation) | API server |
| Ownership | none | `managedFields` per field manager |
| Conflicts | silent overwrites | explicit conflict errors (`--force-conflicts` to take ownership) |

```bash
kubectl apply --server-side -f deploy.yaml --field-manager=team-a
kubectl get deploy web -o yaml --show-managed-fields | less
```

### Admission (recap)

Mutating webhooks/policies → schema validation → validating webhooks/policies (chapter 10). CRDs participate too.

---

## 2. Custom Resource Definitions (CRDs)

A **CRD** teaches the API server a new kind. The API server then stores, validates (OpenAPI schema + CEL rules), versions and
serves it — with RBAC, watch, kubectl support — for free. A CRD alone does nothing; a **controller** gives it behaviour.

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: websites.demo.example.com          # <plural>.<group>
spec:
  group: demo.example.com
  scope: Namespaced
  names:
    kind: Website
    plural: websites
    singular: website
    shortNames: ["ws"]
  versions:
    - name: v1alpha1
      served: true
      storage: true                         # exactly one version is the storage version
      subresources:
        status: {}                          # enables /status (spec and status updated separately)
        scale:                              # enables kubectl scale / HPA
          specReplicasPath: .spec.replicas
          statusReplicasPath: .status.replicas
      additionalPrinterColumns:
        - { name: Replicas, type: integer, jsonPath: .spec.replicas }
        - { name: Ready, type: string, jsonPath: '.status.conditions[?(@.type=="Ready")].status' }
        - { name: Age, type: date, jsonPath: .metadata.creationTimestamp }
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: ["html"]
              x-kubernetes-validations:                 # CEL validation rules
                - rule: "self.replicas <= 10"
                  message: "replicas must be <= 10"
              properties:
                html:     { type: string, maxLength: 10000 }
                replicas: { type: integer, minimum: 1, default: 1 }
            status:
              type: object
              properties:
                replicas: { type: integer }
                conditions:
                  type: array
                  items:
                    type: object
                    properties:
                      type:    { type: string }
                      status:  { type: string }
                      reason:  { type: string }
                      message: { type: string }
```

```bash
kubectl apply -f website-crd.yaml
kubectl api-resources | grep website
kubectl explain website.spec
cat <<'EOF' | kubectl apply -f -
apiVersion: demo.example.com/v1alpha1
kind: Website
metadata: { name: hello }
spec:
  html: "<h1>Hello from a Custom Resource</h1>"
  replicas: 2
EOF
kubectl get ws                              # custom columns appear
kubectl patch ws hello --type merge -p '{"spec":{"replicas":20}}'   # rejected by CEL rule
```

Versioning CRDs: add `v1beta1`, keep both `served`, use a **conversion webhook** if schemas differ, migrate storage version.

---

## 3. Controllers and the reconciliation pattern

```text
           ┌─────────── Informer (client-go) ────────────┐
 API ──LIST+WATCH──► Reflector ──► DeltaFIFO ──► Indexer (local cache)
                                         │
                                         └─► event handlers → enqueue key "ns/name"
                                                                │
                                                     Workqueue (rate-limited, deduplicated)
                                                                │
                                                     Reconcile(key):
                                                        1. read desired state from cache
                                                        2. read actual state (owned objects)
                                                        3. create/update/delete to converge
                                                        4. update .status (conditions, observedGeneration)
                                                        5. return error → requeue with back-off
```

Principles:

- **Level-triggered, not edge-triggered**: reconcile from current state every time; don't depend on seeing every event.
- **Idempotent**: running reconcile twice yields the same result.
- **Informers/caches** prevent hammering the API server; **SharedInformers** share one watch per type.
- **Leader election** so only one replica reconciles.
- Report progress via `status.conditions` and `status.observedGeneration` (= the `metadata.generation` last processed).

## 4. Owner references and garbage collection

```yaml
metadata:
  name: web-7d9f
  ownerReferences:
    - apiVersion: apps/v1
      kind: Deployment
      name: web
      uid: 1b2c...                         # must match the owner's UID
      controller: true                     # the managing controller
      blockOwnerDeletion: true
```

When the owner is deleted, the **garbage collector** deletes dependents:

| Propagation | Behaviour |
|-------------|-----------|
| `Background` (default) | owner deleted immediately, dependents cleaned up afterwards |
| `Foreground` | dependents deleted first; owner waits with `foregroundDeletion` finalizer |
| `Orphan` | dependents kept (ownerReferences removed) |

```bash
kubectl delete deployment web --cascade=orphan      # keep ReplicaSets/Pods
kubectl get rs -o jsonpath='{.items[*].metadata.ownerReferences}'
```

Owner references must be within the same namespace (or a cluster-scoped owner).

## 5. Finalizers

A finalizer is a string in `metadata.finalizers` that **blocks deletion** until a controller removes it — used to clean up
external resources (cloud LBs, DNS records, PV volumes, database users).

```text
 kubectl delete → API sets deletionTimestamp (object still exists, "Terminating")
               → controller sees deletionTimestamp, performs cleanup, removes its finalizer
               → when finalizers list is empty → object actually deleted
```

```bash
kubectl create configmap fz --from-literal=a=b
kubectl patch configmap fz -p '{"metadata":{"finalizers":["demo.example.com/cleanup"]}}'
kubectl delete configmap fz --wait=false
kubectl get configmap fz -o jsonpath='{.metadata.deletionTimestamp}'; echo   # set, but still exists
kubectl patch configmap fz --type=json -p='[{"op":"remove","path":"/metadata/finalizers"}]'   # "controller" done
kubectl get configmap fz                                                       # gone
```

> Stuck `Terminating` namespace/object = a finalizer whose controller is gone or failing. Find out **why** before force-removing
> finalizers — removing them can leak cloud resources. Check: `kubectl get ns <ns> -o yaml` (status.conditions lists remaining
> resources/finalizers); often an unavailable APIService (`kubectl get apiservices | grep False`).

## 6. Operators

An **Operator** = CRDs + a controller encoding **operational knowledge** (install, upgrade, backup, failover, scaling) for a
specific application. "A human SRE in software."

| Operator | Manages |
|----------|---------|
| CloudNativePG | PostgreSQL clusters, failover, backups to S3, PITR |
| Strimzi | Kafka clusters, topics, users |
| Prometheus Operator | Prometheus/Alertmanager from CRDs |
| cert-manager | certificates |
| Argo CD / Flux | GitOps |
| Crossplane / ACK (AWS Controllers for Kubernetes) | cloud infrastructure as K8s resources |
| Karpenter | nodes |

Capability levels (Operator Framework): basic install → seamless upgrades → full lifecycle (backup/restore) → deep insights →
auto-pilot (auto-tuning, auto-scaling, auto-healing).

### Example: using an operator (CloudNativePG)

```bash
CNPG_VERSION=1.27.0   # check releases
kubectl apply --server-side -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.27/releases/cnpg-${CNPG_VERSION}.yaml
cat <<'EOF' | kubectl apply -f -
apiVersion: postgresql.cnpg.io/v1
kind: Cluster
metadata: { name: pg }
spec:
  instances: 3              # 1 primary + 2 streaming replicas, automatic failover
  storage: { size: 1Gi }
EOF
kubectl get cluster pg -w
kubectl get pods -l cnpg.io/cluster=pg -L role     # primary / replica
kubectl get svc | grep pg                          # pg-rw (primary), pg-ro (replicas), pg-r
kubectl delete pod pg-1                            # if it was primary, operator promotes a replica
```

### Build your own

| Framework | Language |
|-----------|----------|
| **Kubebuilder** / controller-runtime | Go (most common) |
| Operator SDK | Go, Ansible, Helm |
| kopf | Python |
| kube-rs | Rust |
| Java Operator SDK | Java |
| Metacontroller | any language via webhooks |

Minimal Python operator with **kopf** that turns `Website` into a Deployment + ConfigMap + Service:

```python
# website_operator.py  —  pip install kopf kubernetes ; run locally: kopf run website_operator.py --verbose
import kopf
import kubernetes

@kopf.on.create("demo.example.com", "v1alpha1", "websites")
@kopf.on.update("demo.example.com", "v1alpha1", "websites")
def reconcile(spec, name, namespace, body, patch, **_):
    labels = {"app": f"website-{name}"}
    cm = {
        "apiVersion": "v1", "kind": "ConfigMap",
        "metadata": {"name": f"website-{name}", "labels": labels},
        "data": {"index.html": spec["html"]},
    }
    deploy = {
        "apiVersion": "apps/v1", "kind": "Deployment",
        "metadata": {"name": f"website-{name}", "labels": labels},
        "spec": {
            "replicas": spec.get("replicas", 1),
            "selector": {"matchLabels": labels},
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "containers": [{
                        "name": "nginx", "image": "nginx:1.27",
                        "volumeMounts": [{"name": "html", "mountPath": "/usr/share/nginx/html"}],
                    }],
                    "volumes": [{"name": "html", "configMap": {"name": f"website-{name}"}}],
                },
            },
        },
    }
    for obj in (cm, deploy):
        kopf.adopt(obj, owner=body)               # sets ownerReferences → GC on delete
    core = kubernetes.client.CoreV1Api()
    apps = kubernetes.client.AppsV1Api()
    _apply(lambda: core.create_namespaced_config_map(namespace, cm),
           lambda: core.replace_namespaced_config_map(cm["metadata"]["name"], namespace, cm))
    _apply(lambda: apps.create_namespaced_deployment(namespace, deploy),
           lambda: apps.patch_namespaced_deployment(deploy["metadata"]["name"], namespace, deploy))
    patch.status["replicas"] = spec.get("replicas", 1)
    patch.status["conditions"] = [{"type": "Ready", "status": "True", "reason": "Reconciled", "message": "ok"}]

def _apply(create, update):
    try:
        create()
    except kubernetes.client.exceptions.ApiException as e:
        if e.status != 409:                       # 409 = already exists → update instead
            raise
        update()
```

```bash
python3 -m venv ~/venvs/kopf && source ~/venvs/kopf/bin/activate
pip install kopf kubernetes
kopf run website_operator.py --verbose &          # uses your kubeconfig
kubectl apply -f hello-website.yaml               # the Website from §2
kubectl get ws,deploy,cm -l app=website-hello
kubectl port-forward deploy/website-hello 8080:80 & curl -s localhost:8080
kubectl delete ws hello                           # owned objects garbage-collected
```

In production, package the operator as a Deployment with its own ServiceAccount + least-privilege ClusterRole, leader election,
metrics, and tests (envtest).

---

## Interview questions

1. **What is a CRD?** An extension that adds a new resource type to the API server with schema validation.
2. **CRD vs Operator?** CRD defines data; an operator is a controller (plus CRDs) that acts on it with domain knowledge.
3. **What is reconciliation?** Continuously driving actual state toward the desired spec, idempotently.
4. **What is an informer?** client-go component that lists/watches, caches objects locally and delivers events to handlers.
5. **Why level-triggered?** Events can be missed; reconciling from full current state is robust.
6. **What are finalizers?** Deletion blockers allowing controllers to clean up before the object disappears.
7. **What are owner references?** Links from dependents to owners enabling garbage collection.
8. **What is `resourceVersion` used for?** Watches (resume points) and optimistic concurrency (409 on conflicts).
9. **Server-side apply advantage?** Field ownership and conflict detection between multiple managers.
10. **How does `kubectl explain` know CRD fields?** From the CRD's OpenAPI schema published by the API server.

**Scenario:** A namespace is stuck in `Terminating` for days. → Inspect namespace status conditions; find resources with finalizers
or an unavailable aggregated APIService; fix/remove the broken controller or API, then let deletion finish.

**Follow-ups:** How do conversion webhooks work? What is API aggregation (APIService) vs CRDs? How do you avoid hot loops and
thundering herds in controllers (rate-limited workqueues, predicates, generation-changed filters)?
