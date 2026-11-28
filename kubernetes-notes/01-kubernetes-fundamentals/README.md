# 01 — Kubernetes Fundamentals

## 1. What is Kubernetes and why is it needed?

**Kubernetes (K8s)** is an open-source **container orchestrator**: you tell it *what* you want
running ("3 copies of my API, reachable at port 80, with 512 MiB RAM each"), and it continuously
makes the cluster match that description across many machines.

Running containers with `docker run` on one server works until you need:

| Problem with plain containers | What Kubernetes provides |
|-------------------------------|--------------------------|
| Server dies → app is down | Self-healing: reschedules Pods to healthy nodes |
| Manual placement on servers | Scheduler places Pods based on resources/rules |
| Traffic spikes | Horizontal autoscaling |
| Deploying new versions without downtime | Rolling updates and rollbacks |
| Containers keep changing IPs | Services with stable virtual IPs + DNS |
| Config/passwords baked into images | ConfigMaps and Secrets |
| Storage tied to one host | PersistentVolumes + CSI drivers |
| Every team scripts things differently | One declarative API for everything |

### Container orchestration

Orchestration = automating **placement, networking, scaling, health, updates, and configuration**
of containers across a fleet.

### History in one table

| Year | Event |
|------|-------|
| 2003–2014 | Google runs containers internally with **Borg** (and later Omega) |
| 2014 | Google open-sources Kubernetes (Greek: "helmsman") |
| 2015 | v1.0; donated to the new **CNCF** |
| 2016–2018 | Wins the "orchestrator war" vs Docker Swarm and Mesos; EKS/AKS/GKE |
| 2019+ | CRDs and Operators make it a platform for building platforms |
| 2022 | dockershim removed (v1.24) — containerd/CRI-O become the norm |
| 2023+ | Gateway API GA, native sidecars, nftables kube-proxy, in-place Pod resize, Dynamic Resource Allocation for GPUs/AI |

### Use cases

Microservices, internal developer platforms, batch/ML training jobs, CI runners, edge clusters
(K3s), data platforms (Spark, Kafka via operators), AI inference serving.

### Advantages and limitations

| Advantages | Limitations |
|------------|-------------|
| Portable across clouds and on-prem | Steep learning curve |
| Self-healing, autoscaling | Operational complexity (upgrades, certs, CNI, etcd) |
| Huge ecosystem (Helm, operators) | Overkill for one small app |
| Declarative, GitOps-friendly | Networking/storage debugging is hard |
| Strong multi-tenancy primitives | Stateful workloads need care |
| Vendor-neutral API | Costs can grow silently (idle nodes, oversized requests) |

---

## 2. Monolith vs microservices

```text
 Monolith                                Microservices
 ┌───────────────────────────┐          ┌──────┐  ┌────────┐  ┌────────┐
 │ UI + Orders + Payments +  │          │  UI  │→ │ Orders │→ │Payments│
 │ Users  (one process, one  │          └──────┘  └────────┘  └────────┘
 │ deploy, one DB)           │                ↘   ┌───────┐
 └───────────────────────────┘                    │ Users │  (each: own deploy, scale, DB)
                                                  └───────┘
```

| | Monolith | Microservices |
|--|----------|---------------|
| Deploy | all at once | independently |
| Scale | whole app | per service |
| Failure blast radius | whole app | one service (if designed well) |
| Complexity | in code | in network/operations |
| Fits K8s? | yes (1 Deployment) | yes — K8s shines here |

Kubernetes does not *require* microservices; it just makes running many services manageable.

---

## 3. Comparisons

### Docker vs Kubernetes

| | Docker (Engine) | Kubernetes |
|--|-----------------|------------|
| Scope | build & run containers on **one host** | orchestrate containers across **many hosts** |
| Unit | container | Pod (1+ containers) |
| Healing | `--restart` policy on one host | reschedules on other nodes |
| Networking | bridge per host | flat cluster-wide Pod network + Services |
| Relationship | Docker builds the **image** | Kubernetes runs the image (via containerd) |

They are complementary: you still use `docker build` (or BuildKit, Buildah, Kaniko) to make images.

### Kubernetes vs Docker Compose vs Docker Swarm

| | Docker Compose | Docker Swarm | Kubernetes |
|--|---------------|--------------|------------|
| Hosts | single | multi | multi |
| Learning curve | very low | low | high |
| Autoscaling | no | no native HPA | yes (HPA/VPA/Cluster Autoscaler) |
| Ecosystem | small | small, little active development | massive |
| Config format | `compose.yaml` | compose-like stack files | many API objects (YAML) |
| Best for | local dev, small single-host apps | simple clusters | production platforms at any scale |

---

## 4. Architecture at a glance

```text
                         ┌───────────────── Control plane ─────────────────┐
  kubectl / CI / UI ───► │ kube-apiserver ◄──► etcd                       │
                         │      ▲  ▲                                       │
                         │      │  └── kube-scheduler                      │
                         │      └───── kube-controller-manager             │
                         │             cloud-controller-manager (cloud)    │
                         └──────┬──────────────────────────────────────────┘
                                │ HTTPS (watch / update)
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
  ┌── Worker node 1 ──┐  ┌── Worker node 2 ──┐  ┌── Worker node 3 ──┐
  │ kubelet           │  │ kubelet           │  │ kubelet           │
  │ kube-proxy        │  │ kube-proxy        │  │ kube-proxy        │
  │ containerd        │  │ containerd        │  │ containerd        │
  │ CNI plugin        │  │ CNI plugin        │  │ CNI plugin        │
  │ [Pod][Pod][Pod]   │  │ [Pod][Pod]        │  │ [Pod]             │
  └───────────────────┘  └───────────────────┘  └───────────────────┘
```

| Term | Meaning |
|------|---------|
| **Cluster** | control plane + nodes managed as one system |
| **Node** | a machine (VM or bare metal) that runs Pods |
| **Pod** | smallest deployable unit: one or more containers sharing network + storage |
| **Container** | a process from an image, running inside a Pod |
| **Control plane** | the "brain": API, state store, scheduler, controllers |
| **Worker node** | the "muscle": runs your workloads |

Details in [chapter 02](../02-architecture/README.md).

---

## 5. Desired state, reconciliation, declarative vs imperative

**Desired state** = what you wrote in YAML (`spec`). **Actual state** = what is really happening
(`status`). **Controllers** run **reconciliation loops**:

```text
        ┌─────────────────────────────────────────────┐
        │  loop forever:                              │
        │    desired = read spec from API server      │
        │    actual  = observe the world              │
        │    if actual != desired: take one action    │
        │    write status                             │
        └─────────────────────────────────────────────┘
```

Example: Deployment wants 3 replicas; a node dies and only 2 Pods remain → the ReplicaSet controller
sees 2 ≠ 3 and creates one more Pod. Nobody had to page an engineer.

| Imperative | Declarative |
|-----------|-------------|
| "Do this action now" | "This is how it should be" |
| `kubectl run`, `kubectl create deployment`, `kubectl scale`, `kubectl expose` | `kubectl apply -f app.yaml` |
| Quick experiments, exam speed, generating YAML | Production, Git, reviews, GitOps |
| Hard to reproduce | Version-controlled, repeatable, idempotent |

Best of both: use imperative commands to **generate** YAML, then manage it declaratively:

```bash
kubectl create deployment web --image=nginx:1.27 --replicas=3 --dry-run=client -o yaml > web.yaml
# --dry-run=client: don't send to the cluster; -o yaml: print the object
kubectl apply -f web.yaml
```

---

## 6. The Kubernetes API

Everything in Kubernetes is an **API object** stored in etcd and served by the **kube-apiserver**
over HTTPS (REST + watch). `kubectl` is just an API client.

```bash
kubectl api-resources                  # every resource type, short names, API group, namespaced?
kubectl api-versions                   # group/version pairs served
kubectl explain deployment.spec.strategy --recursive   # built-in field documentation
kubectl get pods -v=8                  # -v=8 shows the actual HTTP requests kubectl makes
kubectl get --raw /api/v1/namespaces/default/pods | head -c 400
```

URL shape:

```text
/api/v1/namespaces/{ns}/pods/{name}                       ← core group ("v1")
/apis/apps/v1/namespaces/{ns}/deployments/{name}          ← named group "apps"
/apis/networking.k8s.io/v1/namespaces/{ns}/ingresses
```

---

## 7. YAML fundamentals

```yaml
# Comments start with #
key: value                 # mapping (dictionary)
number: 3
quoted: "08"               # quote strings that look like numbers/booleans ("yes", "on", "08")
list:                      # sequence
  - item1
  - item2
nested:
  child:
    grandchild: true
multiline_literal: |       # keeps newlines (good for config files, scripts)
  line 1
  line 2
multiline_folded: >        # folds newlines into spaces
  long text
  continues here
---                        # document separator: several objects in one file
```

Rules: **spaces only, never tabs**; indentation defines structure; list items under a key are indented
consistently. Validate with `kubectl apply --dry-run=server -f file.yaml` (server-side validation
against the real schema) or tools like `kubeconform`, `yamllint`.

---

## 8. Kubernetes object structure

```yaml
apiVersion: apps/v1          # API group/version that defines this kind
kind: Deployment             # object type
metadata:                    # identity: who is this object?
  name: web
  namespace: shop
  labels:                    # key/values for selection and grouping
    app.kubernetes.io/name: web
    app.kubernetes.io/part-of: shop
  annotations:               # non-identifying metadata for tools/humans
    owner: team-payments
spec:                        # DESIRED state — you write this
  replicas: 3
  selector:
    matchLabels:
      app.kubernetes.io/name: web
  template:
    metadata:
      labels:
        app.kubernetes.io/name: web
    spec:
      containers:
        - name: nginx
          image: nginx:1.27
status:                      # ACTUAL state — written by controllers; never write it yourself
  readyReplicas: 3
```

| Field | Written by | Notes |
|-------|-----------|-------|
| `apiVersion`, `kind` | you | determines schema |
| `metadata.name` | you | unique per kind per namespace |
| `metadata.uid`, `resourceVersion`, `creationTimestamp` | API server | `resourceVersion` enables optimistic concurrency and watches |
| `spec` | you | desired state |
| `status` | controllers | observed state (`/status` subresource) |

---

## 9. Labels, selectors, annotations

**Labels** identify and group; **selectors** query them. This is how Services find Pods,
Deployments own ReplicaSets, NetworkPolicies pick targets, and scheduling rules match nodes.

```bash
kubectl get pods -l app=web                       # equality selector
kubectl get pods -l 'env in (prod,staging)'       # set-based selector
kubectl get pods -l 'app=web,tier!=cache'
kubectl get pods --show-labels
kubectl label pod web-abc env=prod                # add a label
kubectl label pod web-abc env-                    # remove label (trailing minus)
kubectl annotate deploy web kubernetes.io/change-cause="bump to 1.27"
```

| | Labels | Annotations |
|--|--------|-------------|
| Purpose | identify/select | attach arbitrary metadata |
| Used by selectors | ✅ | ❌ |
| Size | small (63-char values) | can be large (256 KiB total) |
| Examples | `app`, `tier`, `env`, `version` | build SHA, contact, ingress controller options, `kubectl.kubernetes.io/last-applied-configuration` |

Recommended labels: `app.kubernetes.io/name`, `instance`, `version`, `component`, `part-of`, `managed-by`.

---

## 10. Namespaces

A **namespace** is a virtual cluster partition for names, RBAC, quotas, and policies.
(Not the same as a Linux namespace!)

```bash
kubectl get namespaces
kubectl create namespace dev
kubectl get pods -n kube-system              # system components
kubectl get pods -A                          # all namespaces
kubectl config set-context --current --namespace=dev   # change default namespace for your context
kubectl api-resources --namespaced=false     # cluster-scoped kinds (Node, PV, ClusterRole, Namespace…)
```

Default namespaces:

| Namespace | Purpose |
|-----------|---------|
| `default` | where objects go if you specify none |
| `kube-system` | control plane add-ons (CoreDNS, kube-proxy, CNI) |
| `kube-public` | readable by everyone (cluster-info) |
| `kube-node-lease` | node heartbeat `Lease` objects |

Namespaces do **not** isolate network traffic by themselves — you need NetworkPolicies.

---

## Lab — first contact (needs any cluster from chapter 03, e.g. `kind create cluster`)

```bash
kubectl cluster-info                       # API server address, CoreDNS
kubectl get nodes -o wide                  # node IPs, OS, kernel, runtime
kubectl create namespace lab01
kubectl -n lab01 create deployment web --image=nginx:1.27 --replicas=2
kubectl -n lab01 get deploy,rs,pods -o wide      # Deployment → ReplicaSet → Pods
kubectl -n lab01 delete pod -l app=web --wait=false
kubectl -n lab01 get pods -w               # -w watch: new Pods appear (reconciliation in action)
kubectl -n lab01 get deploy web -o yaml | less   # see spec vs status
kubectl delete namespace lab01             # deletes everything inside it
```

---

## Common mistakes

- Selector labels in a Deployment not matching template labels (rejected by API).
- Editing objects with `kubectl edit` in production instead of Git → drift.
- Using `latest` image tag → unpredictable rollouts.
- Assuming namespaces are a security boundary without RBAC + NetworkPolicy + quotas.
- Tabs in YAML; unquoted `yes/no/on/off`.

---

## Interview questions

1. **What problem does Kubernetes solve?** Automates running containers across many machines:
   scheduling, healing, scaling, networking, updates, configuration.
2. **What is a Pod and why not schedule containers directly?** A Pod groups tightly-coupled containers
   that share network/IPC and volumes; it's the atomic scheduling unit.
3. **Desired vs actual state?** `spec` vs `status`; controllers reconcile actual toward desired.
4. **Declarative vs imperative?** Declarative describes the end state (`apply`), imperative issues
   commands (`create`, `scale`). Production uses declarative + Git.
5. **What is a reconciliation loop?** A controller's endless observe → compare → act cycle.
6. **Labels vs annotations?** Labels are selectable identifiers; annotations are non-selectable metadata.
7. **What is a namespace used for?** Name scoping, RBAC, quotas, policies; not network isolation.
8. **Docker vs Kubernetes?** Docker builds/runs containers on one host; Kubernetes orchestrates many hosts.
9. **What are `apiVersion` and `kind`?** They identify the schema (group/version) and type of the object.
10. **Who writes `status`?** Controllers/kubelet via the status subresource — never users.

**Scenario:** "We have one VM running a docker-compose app. Should we move to Kubernetes?" — Only if you
need multi-host HA, autoscaling, many services/teams, or a platform; otherwise a managed PaaS or
Compose may be cheaper and simpler.

**Follow-ups:** How does `resourceVersion` give optimistic concurrency? What is server-side apply and
field ownership (`managedFields`)?
