# 09 — Autoscaling

```text
 Pods  ── HPA: more/fewer replicas (horizontal)
       ── VPA: bigger/smaller requests (vertical)
       ── KEDA: event-driven HPA (queues, cron, scale to zero)
 Nodes ── Cluster Autoscaler: add/remove nodes in node groups
       ── Karpenter: provision right-sized nodes directly (AWS, Azure)
 Data  ── Metrics Server (resource metrics API), Prometheus Adapter / KEDA (custom & external metrics APIs)
```

| | HPA | VPA | Cluster Autoscaler | Karpenter |
|--|-----|-----|--------------------|-----------|
| Scales | replicas | requests/limits | nodes in pre-defined groups | nodes chosen per pending Pods |
| Trigger | metrics vs target | historical usage | Pending Pods / underutilised nodes | Pending Pods / consolidation |
| Built-in | ✅ | add-on | add-on | add-on |
| Typical use | stateless services | right-sizing, batch | any cloud | AWS/Azure, cost-optimised fleets |

---

## 1. Metrics Server

Collects CPU/memory from each kubelet (`/metrics/resource`) every ~15 s and serves the `metrics.k8s.io` API. It's for
**autoscaling and `kubectl top`, not for monitoring history** (use Prometheus).

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# kind/minikube kubelets use self-signed certs → allow insecure TLS for the lab ONLY:
kubectl -n kube-system patch deploy metrics-server --type=json \
  -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n kube-system rollout status deploy metrics-server
kubectl top nodes
kubectl top pods -A --sort-by=memory
kubectl get --raw /apis/metrics.k8s.io/v1beta1/nodes | head -c 300
```

---

## 2. Horizontal Pod Autoscaler (HPA)

### How it works

Every 15 s the HPA controller computes:

```text
 desiredReplicas = ceil( currentReplicas × currentMetricValue / targetValue )
 e.g. 4 replicas at 90% CPU, target 60% → ceil(4 × 90/60) = 6
```

- CPU/memory **utilisation is relative to requests** → Pods **must have requests**.
- Multiple metrics → computes each and takes the **max**.
- 10 % tolerance band prevents flapping; scale-down uses a **stabilisation window** (default 300 s).
- Unready/starting Pods are handled conservatively.

### YAML (`autoscaling/v2`)

```yaml
apiVersion: autoscaling/v2              # ⚠️ v2beta1/v2beta2 removed
kind: HorizontalPodAutoscaler
metadata: { name: web }
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: web
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target: { type: Utilization, averageUtilization: 60 }
    - type: Resource
      resource:
        name: memory
        target: { type: AverageValue, averageValue: 400Mi }
    - type: Pods                         # custom per-Pod metric (needs a custom metrics adapter)
      pods:
        metric: { name: http_requests_per_second }
        target: { type: AverageValue, averageValue: "100" }
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - { type: Percent, value: 100, periodSeconds: 15 }   # at most double every 15 s
        - { type: Pods, value: 4, periodSeconds: 15 }
      selectPolicy: Max
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - { type: Percent, value: 20, periodSeconds: 60 }    # shrink slowly
```

### Lab — CPU-based scaling

```bash
kubectl create deployment php-apache --image=registry.k8s.io/hpa-example
kubectl set resources deploy php-apache --requests=cpu=200m --limits=cpu=500m
kubectl expose deploy php-apache --port=80
kubectl autoscale deploy php-apache --cpu-percent=50 --min=1 --max=10   # imperative HPA
kubectl get hpa php-apache -w &
# Generate load in another terminal:
kubectl run load --rm -it --image=busybox:1.36 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://php-apache; done"
# TARGETS cpu: 250%/50% → REPLICAS climbs to ~5-7. Stop the load (Ctrl+C) → after ~5 min it scales back to 1.
kubectl describe hpa php-apache          # Events: "New size: 4; reason: cpu resource utilization (percentage of request) above target"
```

### Memory-based scaling caveat

Many runtimes (JVM, Go, Node) don't release memory after load drops → memory HPA scales up and **never down**. Prefer CPU,
request rate, queue depth, or latency for scaling; use memory as a safety metric.

### Custom and external metrics

| API | Provided by | Example |
|-----|-------------|---------|
| `metrics.k8s.io` | metrics-server | CPU, memory |
| `custom.metrics.k8s.io` | Prometheus Adapter, KEDA | per-Pod RPS from Prometheus |
| `external.metrics.k8s.io` | KEDA, cloud adapters | SQS queue length, Kafka lag |

**KEDA** (event-driven autoscaling) is the most common way today:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: { name: worker }
spec:
  scaleTargetRef: { name: worker }          # Deployment
  minReplicaCount: 0                        # scale to zero when idle
  maxReplicaCount: 50
  triggers:
    - type: prometheus
      metadata:
        serverAddress: http://prometheus-operated.monitoring:9090
        query: sum(rate(http_requests_total{app="worker"}[1m]))
        threshold: "100"
    - type: aws-sqs-queue
      authenticationRef: { name: keda-aws }
      metadata: { queueURL: https://sqs.us-east-1.amazonaws.com/123456789012/jobs, queueLength: "20", awsRegion: us-east-1 }
```

KEDA creates and manages an HPA under the hood.

---

## 3. Vertical Pod Autoscaler (VPA)

Recommends (and optionally applies) requests based on observed usage. Components: **Recommender**, **Updater** (evicts Pods to
apply new values), **Admission controller** (sets requests on new Pods).

```bash
git clone --depth 1 https://github.com/kubernetes/autoscaler.git
cd autoscaler/vertical-pod-autoscaler && ./hack/vpa-up.sh      # installs CRDs + components (needs openssl for webhook certs)
```

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata: { name: web-vpa }
spec:
  targetRef: { apiVersion: apps/v1, kind: Deployment, name: web }
  updatePolicy:
    updateMode: "Off"          # Off = recommend only (safe start) | Initial | Recreate | InPlaceOrRecreate (newer, uses in-place resize)
  resourcePolicy:
    containerPolicies:
      - containerName: "*"
        minAllowed: { cpu: 50m, memory: 64Mi }
        maxAllowed: { cpu: "2", memory: 2Gi }
        controlledResources: ["cpu", "memory"]
```

```bash
kubectl describe vpa web-vpa     # Recommendation: Target / Lower Bound / Upper Bound per container
```

> ⚠️ Don't let VPA and HPA both act on **the same metric** (CPU/memory) for the same workload — they fight. Common combo:
> HPA on RPS/custom metrics + VPA on CPU/memory, or VPA in `Off` mode for right-sizing insight.

---

## 4. Cluster Autoscaler (CA)

```text
 Pod Pending (FailedScheduling: Insufficient cpu)
   → CA simulates: "would a new node from node group X fit it?" → increases ASG/MIG/VMSS desired size
   → new node joins → scheduler places Pod
 Scale-down: node utilisation (by requests) < 50% for 10 min AND its Pods can move elsewhere → drain → remove
```

Blocks scale-down: Pods with local storage (unless allowed), PDBs that can't be satisfied, Pods not backed by a controller,
`cluster-autoscaler.kubernetes.io/safe-to-evict: "false"`, kube-system Pods without PDB.

```bash
kubectl -n kube-system logs deploy/cluster-autoscaler | grep -E 'scale-up|scale_down|Unschedulable' | tail
kubectl get cm -n kube-system cluster-autoscaler-status -o yaml
```

Requirements on AWS: node groups (ASGs) with tags `k8s.io/cluster-autoscaler/enabled` and
`k8s.io/cluster-autoscaler/<cluster>`, IAM permissions, CA version matching the Kubernetes minor.

---

## 5. Karpenter (AWS-first, also Azure)

Instead of scaling fixed node groups, Karpenter looks at Pending Pods' requirements (CPU, memory, arch, zone, capacity type,
GPUs) and **launches the cheapest instance types that fit**, within seconds. It also **consolidates**: replaces under-used nodes
with fewer/cheaper ones.

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata: { name: general }
spec:
  template:
    spec:
      nodeClassRef: { group: karpenter.k8s.aws, kind: EC2NodeClass, name: default }
      requirements:
        - { key: karpenter.sh/capacity-type, operator: In, values: ["spot", "on-demand"] }
        - { key: kubernetes.io/arch, operator: In, values: ["amd64", "arm64"] }
        - { key: karpenter.k8s.aws/instance-category, operator: In, values: ["c", "m", "r"] }
        - { key: karpenter.k8s.aws/instance-generation, operator: Gt, values: ["5"] }
      expireAfter: 720h                      # recycle nodes monthly (patching)
  limits: { cpu: "1000", memory: 4000Gi }    # cap total provisioned capacity
  disruption:
    consolidationPolicy: WhenEmptyOrUnderutilized
    consolidateAfter: 1m
---
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata: { name: default }
spec:
  role: KarpenterNodeRole-my-cluster
  amiSelectorTerms: [{ alias: al2023@latest }]       # pin a version in production
  subnetSelectorTerms: [{ tags: { karpenter.sh/discovery: my-cluster } }]
  securityGroupSelectorTerms: [{ tags: { karpenter.sh/discovery: my-cluster } }]
```

| | Cluster Autoscaler | Karpenter |
|--|--------------------|-----------|
| Unit | node group (ASG) | individual instances |
| Instance choice | fixed per group | dynamic, many types |
| Speed | minutes | typically < 1 min |
| Consolidation | basic scale-down | active bin-packing replacement |
| Spot handling | via mixed ASGs | native, interruption handling via SQS |

EKS **Auto Mode** runs Karpenter-based node management for you.

---

## 6. Production considerations

1. **Requests must be accurate** — HPA math and node autoscaling both depend on them.
2. **Readiness probes + fast startup** — new replicas only help once Ready; slow JVMs need startupProbes and earlier scaling.
3. **Headroom**: scale before saturation (60–70 % target), or keep spare capacity with low-priority "placeholder" Pods that get
   preempted (overprovisioning pattern).
4. **PDBs + graceful shutdown** so scale-down and consolidation don't cause errors.
5. **Limit max replicas/nodes** to cap cost and protect dependencies (databases have connection limits!).
6. **Scale on the right signal**: queue depth for workers, RPS/latency for APIs.
7. **Test** autoscaling with load tests (k6, Locust) before relying on it.
8. **Spot capacity**: diversify instance types, handle 2-minute interruption notices.

---

## Interview questions

1. **How does HPA calculate replicas?** `ceil(current × currentMetric/target)`, max across metrics, with tolerance and stabilisation.
2. **Why does HPA show `<unknown>` targets?** metrics-server missing/failing or Pods lack resource requests.
3. **HPA vs VPA?** More replicas vs bigger Pods; avoid both on the same metric.
4. **What does Cluster Autoscaler react to?** Pending unschedulable Pods (scale up) and underutilised nodes (scale down).
5. **Karpenter vs Cluster Autoscaler?** Karpenter provisions right-sized instances directly and consolidates; CA resizes node groups.
6. **What is KEDA?** Event-driven autoscaler (queues, Prometheus, cron) that can scale to zero by driving an HPA.
7. **Why is memory a poor HPA metric?** Many runtimes don't free memory, so scale-down never happens.
8. **What blocks CA scale-down?** PDBs, local storage, unmanaged Pods, safe-to-evict=false annotations.
9. **How to prevent flapping?** Stabilisation windows and scale policies in `behavior`.
10. **Metrics Server vs Prometheus?** Metrics Server: short-term resource metrics for autoscaling; Prometheus: full monitoring with history.

**Scenario:** Traffic spike, HPA scaled to max but latency still high and Pods Pending. → Node capacity exhausted; node autoscaler
too slow/not configured or hitting account limits; add overprovisioning, check CA/Karpenter logs and instance quotas.

**Follow-ups:** How does HPA handle Pods that aren't Ready yet? How does Karpenter handle Spot interruptions? Predictive scaling options?
