# 08 — Scheduling & Resource Management

## 1. Requests vs limits

```yaml
resources:
  requests:            # GUARANTEED minimum; used by the SCHEDULER to place the Pod
    cpu: 250m
    memory: 256Mi
  limits:              # MAXIMUM; enforced by the KERNEL (cgroups) at runtime
    cpu: "1"
    memory: 512Mi
```

| | Requests | Limits |
|--|----------|--------|
| Used by | scheduler (fit), kubelet eviction ranking, cgroup `cpu.weight` | cgroup `cpu.max`, `memory.max` |
| CPU exceeded | — | **throttled** (slower, not killed) |
| Memory exceeded | may be evicted under node pressure if above request | **OOMKilled** (exit 137) |
| Omitted | defaults from LimitRange, else 0 (requests default to limits if only limits are set) | unlimited |

### Units

| CPU | Meaning |
|-----|---------|
| `1` | 1 vCPU/core (1000 millicores) |
| `500m` | half a core |
| `100m` | 10 % of a core |

| Memory | Meaning |
|--------|---------|
| `Mi`, `Gi` | binary: 1 Mi = 1,048,576 bytes ✅ use these |
| `M`, `G` | decimal: 1 M = 1,000,000 bytes |
| ⚠️ `m` | milli-bytes! `512m` memory = 0.512 bytes — a classic typo |

Production guidance:
- **Always set memory requests and limits** (often equal for predictability).
- **Set CPU requests**; many teams **omit CPU limits** for latency-sensitive services to avoid CFS throttling, relying on
  requests for fair sharing. If you set them, monitor `container_cpu_cfs_throttled_periods_total`.
- Right-size from real usage (VPA recommendations, Prometheus p95/p99).

### In-place resize

Pod resources can be changed **without restarting** the Pod on recent versions (in-place Pod vertical scaling, GA in v1.35):

```bash
kubectl patch pod web --subresource resize --patch '{"spec":{"containers":[{"name":"web","resources":{"requests":{"cpu":"500m"},"limits":{"cpu":"1"}}}]}}'
kubectl get pod web -o jsonpath='{.status.containerStatuses[0].resources}'
```

`resizePolicy` per resource chooses `NotRequired` (live) or `RestartContainer` (e.g. memory for JVMs).

---

## 2. QoS classes

| Class | Rule | Eviction order under node pressure |
|-------|------|------------------------------------|
| **Guaranteed** | every container has CPU & memory requests == limits | last |
| **Burstable** | at least one request/limit set, not Guaranteed | middle (those most over their request first) |
| **BestEffort** | no requests/limits at all | first |

```bash
kubectl get pod web -o jsonpath='{.status.qosClass}'
```

Also affects `oom_score_adj`: BestEffort Pods are the kernel OOM killer's first choice.

---

## 3. ResourceQuota and LimitRange (namespace guardrails)

```yaml
apiVersion: v1
kind: ResourceQuota
metadata: { name: team-a-quota, namespace: team-a }
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.memory: 40Gi
    pods: "50"
    services.loadbalancers: "2"
    persistentvolumeclaims: "10"
    requests.storage: 200Gi
    count/deployments.apps: "20"
---
apiVersion: v1
kind: LimitRange
metadata: { name: defaults, namespace: team-a }
spec:
  limits:
    - type: Container
      default:            { cpu: 500m, memory: 256Mi }   # default LIMITS
      defaultRequest:     { cpu: 100m, memory: 128Mi }   # default REQUESTS
      max:                { cpu: "2",  memory: 2Gi }
      min:                { cpu: 50m,  memory: 32Mi }
    - type: PersistentVolumeClaim
      max: { storage: 50Gi }
```

```bash
kubectl describe resourcequota -n team-a          # Used vs Hard
kubectl describe limitrange -n team-a
```

With a CPU/memory quota present, Pods **without** requests/limits are **rejected** (`must specify requests.cpu`) — that's why
quotas are paired with a LimitRange that injects defaults.

---

## 4. Placement controls

### 4.1 nodeSelector (simple)

```bash
kubectl label node lab-worker disktype=ssd
```

```yaml
spec:
  nodeSelector:
    disktype: ssd
    kubernetes.io/arch: amd64      # well-known labels: kubernetes.io/os, topology.kubernetes.io/zone, node.kubernetes.io/instance-type
```

### 4.2 Node affinity (expressive)

```yaml
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:     # HARD rule
      nodeSelectorTerms:                                # terms are ORed; expressions inside a term are ANDed
        - matchExpressions:
            - key: topology.kubernetes.io/zone
              operator: In                              # In, NotIn, Exists, DoesNotExist, Gt, Lt
              values: ["us-east-1a", "us-east-1b"]
    preferredDuringSchedulingIgnoredDuringExecution:    # SOFT preference with weight 1-100
      - weight: 80
        preference:
          matchExpressions:
            - { key: node.kubernetes.io/instance-type, operator: In, values: ["m7i.large"] }
```

"IgnoredDuringExecution" = already-running Pods are **not** evicted if labels change later.

### 4.3 Pod affinity and anti-affinity

```yaml
affinity:
  podAntiAffinity:                   # spread replicas: never two web Pods on the same node
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchLabels: { app: web }
        topologyKey: kubernetes.io/hostname
  podAffinity:                       # co-locate with cache in the same zone (lower latency)
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 50
        podAffinityTerm:
          labelSelector:
            matchLabels: { app: redis }
          topologyKey: topology.kubernetes.io/zone
```

`topologyKey` defines the "domain": hostname = node, zone = AZ. Hard anti-affinity with more replicas than nodes → extra Pods
stay **Pending**. Pod (anti-)affinity is expensive in big clusters; prefer topology spread constraints.

### 4.4 Taints and tolerations

**Taints repel** Pods from nodes; **tolerations allow** (not force) Pods onto tainted nodes.

```bash
kubectl taint nodes lab-worker2 dedicated=gpu:NoSchedule
kubectl taint nodes lab-worker2 dedicated=gpu:NoSchedule-     # remove (trailing minus)
kubectl describe node lab-worker2 | grep Taints
```

| Effect | Meaning |
|--------|---------|
| `NoSchedule` | new Pods without toleration aren't scheduled there |
| `PreferNoSchedule` | try to avoid |
| `NoExecute` | also **evicts** running Pods without toleration (after `tolerationSeconds`) |

```yaml
tolerations:
  - key: dedicated
    operator: Equal          # or Exists (any value)
    value: gpu
    effect: NoSchedule
nodeSelector:                # toleration + selector = "run ONLY on gpu nodes" (dedicated node pattern)
  dedicated: gpu
```

Built-in taints: `node-role.kubernetes.io/control-plane:NoSchedule`, `node.kubernetes.io/not-ready:NoExecute`,
`node.kubernetes.io/unreachable:NoExecute` (Pods tolerate these for 300 s by default), `node.kubernetes.io/disk-pressure`,
`memory-pressure`, `unschedulable`.

### 4.5 Topology spread constraints

```yaml
topologySpreadConstraints:
  - maxSkew: 1                               # max difference in Pod count between any two zones
    topologyKey: topology.kubernetes.io/zone
    whenUnsatisfiable: DoNotSchedule         # or ScheduleAnyway (soft)
    labelSelector:
      matchLabels: { app: web }
    minDomains: 3                            # require spreading across at least 3 zones
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway
    labelSelector:
      matchLabels: { app: web }
```

The scheduler only enforces spread **at scheduling time**; use the **descheduler** to rebalance later.

| Tool | Best for |
|------|----------|
| nodeSelector | simple "must have label" |
| nodeAffinity | complex/soft node rules |
| podAntiAffinity | strict "not together" |
| topologySpread | even distribution across zones/nodes |
| taints/tolerations | reserving nodes (GPU, system, spot) |

---

## 5. PriorityClasses and preemption

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata: { name: business-critical }
value: 100000                  # higher = more important (system-cluster-critical is 2000000000)
globalDefault: false
preemptionPolicy: PreemptLowerPriority   # or Never (wait in queue but don't evict others)
description: "Customer-facing APIs"
```

```yaml
spec:
  priorityClassName: business-critical
```

When a high-priority Pod can't be scheduled, the scheduler finds a node where **evicting lower-priority Pods** makes room
(respecting PDBs as best effort), evicts them (graceful), and nominates the node (`status.nominatedNodeName`).
Use priority to protect critical workloads and to let batch jobs soak up spare capacity.

---

## 6. How the scheduler decides

```text
 Scheduling queue (sorted by priority)
   → PreFilter → Filter (per node, parallel):
        NodeUnschedulable, NodeName, TaintToleration, NodeAffinity, NodePorts,
        NodeResourcesFit (requests ≤ allocatable − already requested), VolumeBinding/Zone/Limits,
        PodTopologySpread, InterPodAffinity
   → if 0 nodes: PostFilter = preemption
   → PreScore → Score (0–100 each, weighted):
        NodeResourcesFit (LeastAllocated by default → spread; MostAllocated → bin-pack),
        NodeResourcesBalancedAllocation, ImageLocality, InterPodAffinity, NodeAffinity preferred,
        TaintToleration PreferNoSchedule, PodTopologySpread
   → Reserve → Permit → PreBind (bind volumes) → Bind
```

Key point: the scheduler uses **requests**, not actual usage. A node at 10 % real CPU can be "full" if requests add up.

```bash
kubectl describe node lab-worker | sed -n '/Allocatable/,/Events/p'   # Allocatable + "Allocated resources" (requests/limits %)
kubectl get pods -A -o wide --field-selector spec.nodeName=lab-worker
```

Allocatable = Capacity − kube-reserved − system-reserved − eviction threshold.

---

## 7. Scheduling failures — diagnose

```bash
kubectl get pods --field-selector=status.phase=Pending
kubectl describe pod <pod> | grep -A10 Events
# FailedScheduling  0/3 nodes are available: 1 node(s) had untolerated taint {node-role.kubernetes.io/control-plane: },
#   2 Insufficient memory. preemption: 0/3 nodes are available: 3 No preemption victims found for incoming pod.
```

| Message fragment | Fix |
|------------------|-----|
| `Insufficient cpu/memory` | lower requests, add nodes (Cluster Autoscaler/Karpenter), free capacity |
| `untolerated taint` | add toleration or use other nodes |
| `didn't match Pod's node affinity/selector` | fix labels/affinity |
| `didn't match pod anti-affinity rules` | more nodes or soften rule |
| `node(s) didn't match pod topology spread constraints` | more zones/nodes, ScheduleAnyway |
| `pod has unbound immediate PersistentVolumeClaims` | fix PVC/StorageClass |
| `volume node affinity conflict` | zone mismatch for PV |
| `Too many pods` | max Pods per node reached (110 default, or ENI IP limit on EKS) |
| `exceeded quota` (at create time, not scheduling) | ResourceQuota |

### Lab

```bash
kubectl create deployment big --image=nginx:1.27 --replicas=3
kubectl set resources deploy big --requests=cpu=50,memory=1Gi     # 50 CPUs — impossible
kubectl get pods -l app=big; kubectl describe pod -l app=big | grep FailedScheduling
kubectl set resources deploy big --requests=cpu=100m,memory=64Mi
kubectl taint nodes lab-worker team=a:NoSchedule; kubectl taint nodes lab-worker2 team=a:NoSchedule
kubectl rollout restart deploy big; kubectl get pods -l app=big -o wide   # Pending (control-plane also tainted)
kubectl patch deploy big --type=json -p='[{"op":"add","path":"/spec/template/spec/tolerations","value":[{"key":"team","operator":"Equal","value":"a","effect":"NoSchedule"}]}]'
kubectl get pods -l app=big -o wide                                       # scheduled on tainted workers
kubectl taint nodes lab-worker team-; kubectl taint nodes lab-worker2 team-
kubectl delete deploy big
```

---

## Interview questions

1. **Requests vs limits?** Requests reserve capacity for scheduling; limits cap usage at runtime.
2. **CPU limit vs memory limit exceeded?** CPU throttles; memory OOM-kills.
3. **QoS classes?** Guaranteed (req=lim all), Burstable, BestEffort — determines eviction order.
4. **ResourceQuota vs LimitRange?** Quota caps namespace totals; LimitRange sets per-object defaults/min/max.
5. **Taint vs toleration?** Taint on node repels; toleration on Pod permits scheduling onto it.
6. **Node affinity vs nodeSelector?** Affinity supports operators, OR terms and soft preferences.
7. **Pod anti-affinity use case?** Keep replicas on different nodes/zones for HA.
8. **Topology spread constraints vs anti-affinity?** Spread controls skew evenly and scales better; anti-affinity is all-or-nothing.
9. **What is preemption?** Evicting lower-priority Pods to schedule a higher-priority one.
10. **Why is a Pod Pending when nodes look idle?** Scheduler uses requests; requested capacity is exhausted, or taints/affinity block it.

**Scenario:** Latency spikes every few seconds with low average CPU. → CPU throttling due to tight CPU limits; check throttling
metrics, raise/remove limits.

**Follow-ups:** How does the scheduler score with `MostAllocated` for bin-packing? What is the descheduler? How do scheduler
profiles/plugins work?
