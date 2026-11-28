# 04 — Workloads & Controllers

```text
 Deployment ──owns──► ReplicaSet ──owns──► Pods        stateless apps, rolling updates
 StatefulSet ───────────────────────────► Pods (+PVCs) stable identity & storage
 DaemonSet ─────────────────────────────► 1 Pod per node
 CronJob ──owns──► Job ──owns──► Pods                  run to completion, on a schedule
```

| Controller | Pod identity | Scaling | Storage | Typical use |
|------------|-------------|---------|---------|-------------|
| Deployment | random (`web-7d9f-x2k`) | any order | shared or none | web, APIs, workers |
| StatefulSet | ordinal (`db-0`, `db-1`) | ordered | **per-Pod PVC** | databases, Kafka, ZooKeeper |
| DaemonSet | one per node | follows nodes | usually hostPath | log agents, CNI, node exporters |
| Job | random | parallelism/completions | any | migrations, batch |
| CronJob | — | creates Jobs | any | backups, reports |
| ReplicaSet | random | count only | — | used by Deployments, rarely directly |

---

## 1. Pods

### 1.1 What and why

A **Pod** is one or more containers that share a **network namespace** (one IP, `localhost` between them),
**IPC/UTS** namespaces, and **volumes**. It is scheduled as a unit onto one node. Pods are **ephemeral**:
they are never "moved" — a new Pod with a new IP replaces the old one.

### 1.2 Annotated Pod YAML

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: web
  labels:
    app: web
spec:
  restartPolicy: Always            # Always (default) | OnFailure | Never
  terminationGracePeriodSeconds: 30
  containers:
    - name: nginx
      image: nginx:1.27            # pin a tag (or a digest @sha256:...) — never rely on latest
      imagePullPolicy: IfNotPresent
      ports:
        - name: http
          containerPort: 80        # informational + used by named-port references
      resources:
        requests: { cpu: 100m, memory: 64Mi }   # used for scheduling
        limits:   { memory: 128Mi }             # enforced by cgroups
      readinessProbe:              # "can I receive traffic?"
        httpGet: { path: /, port: http }
        periodSeconds: 5
      livenessProbe:               # "am I stuck? restart me"
        httpGet: { path: /, port: http }
        initialDelaySeconds: 10
        periodSeconds: 10
        failureThreshold: 3
      lifecycle:
        preStop:                   # runs BEFORE SIGTERM; gives load balancers time to drain
          sleep: { seconds: 5 }    # native sleep action (older clusters: exec: ["sh","-c","sleep 5"])
```

```bash
kubectl apply -f pod.yaml
kubectl get pod web -o wide              # IP, node
kubectl describe pod web                 # events at the bottom are the #1 debugging tool
kubectl logs web [-c nginx] [-f] [--previous]   # --previous = logs of the crashed instance
kubectl exec -it web -- sh
kubectl port-forward pod/web 8080:80     # localhost:8080 → Pod:80 through the API server
kubectl delete pod web
```

### 1.3 Pod lifecycle: phases, conditions, container states

| Phase | Meaning |
|-------|---------|
| `Pending` | accepted, but not all containers started (scheduling, image pull, volume) |
| `Running` | bound to a node, ≥1 container running |
| `Succeeded` | all containers exited 0 and won't restart |
| `Failed` | all terminated, ≥1 failed |
| `Unknown` | node unreachable |

Conditions (`kubectl get pod -o jsonpath='{.status.conditions}'`): `PodScheduled`,
`PodReadyToStartContainers`, `Initialized`, `ContainersReady`, `Ready`.

Container states: `Waiting` (reason: `ContainerCreating`, `ImagePullBackOff`, `CrashLoopBackOff`),
`Running`, `Terminated` (reason `Completed`, `Error`, `OOMKilled`, with exit code).

```text
 Pending ──scheduled──► init containers (in order) ──► app containers start ──► Running
                                                                                  │
                                          readiness passes ──► Ready=True ──► gets Service traffic
                                                                                  │
                         delete ──► Terminating ──► preStop ──► SIGTERM ──► (grace) ──► SIGKILL
```

### 1.4 Restart policies and probes

| `restartPolicy` | Container exits 0 | Exits non-zero | Used by |
|-----------------|-------------------|----------------|---------|
| Always | restart | restart | Deployments, StatefulSets, DaemonSets (required) |
| OnFailure | done | restart | Jobs |
| Never | done | done | Jobs, debugging |

Restarts use exponential back-off (10 s, 20 s, 40 s … capped at 5 min) → `CrashLoopBackOff`.

| Probe | Failure action | Use for |
|-------|----------------|---------|
| `startupProbe` | kill & restart; disables other probes until it succeeds | slow-starting apps |
| `livenessProbe` | kill & restart | deadlocks |
| `readinessProbe` | remove from Service endpoints | warming up, overload, dependency down |

Probe types: `httpGet`, `tcpSocket`, `exec`, `grpc`.

> ⚠️ **Never make liveness depend on external dependencies** (DB down → all Pods restart in a loop →
> outage gets worse). Liveness should check only "is this process healthy?".

### 1.5 Image pull policy

| Policy | Behaviour | Default when |
|--------|-----------|--------------|
| `IfNotPresent` | pull only if not on the node | tag is not `latest` |
| `Always` | check registry every start (uses cache if digest unchanged) | tag is `latest` or omitted |
| `Never` | never pull | — |

Private registries: create a `docker-registry` Secret and reference it via `imagePullSecrets`
(or attach it to the ServiceAccount).

```bash
kubectl create secret docker-registry regcred --docker-server=registry.example.com \
  --docker-username=ci --docker-password="$REG_TOKEN"
```

### 1.6 Init containers, sidecars, multi-container Pods

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: app-with-helpers
spec:
  volumes:
    - name: shared
      emptyDir: {}
  initContainers:
    # 1) Classic init container: runs to completion BEFORE app containers, in order
    - name: wait-for-db
      image: busybox:1.36
      command: ["sh", "-c", "until nc -z postgres 5432; do echo waiting; sleep 2; done"]
    # 2) Native sidecar (GA v1.33): an init container with restartPolicy: Always.
    #    Starts before app containers, keeps running alongside them, stops AFTER them.
    - name: log-shipper
      image: busybox:1.36
      restartPolicy: Always
      command: ["sh", "-c", "tail -F /var/log/app/app.log"]
      volumeMounts:
        - { name: shared, mountPath: /var/log/app }
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "while true; do date >> /var/log/app/app.log; sleep 2; done"]
      volumeMounts:
        - { name: shared, mountPath: /var/log/app }
```

| Pattern | Example |
|---------|---------|
| **Sidecar** | log shipper, Envoy proxy, config reloader |
| **Ambassador** | local proxy to a remote DB (`localhost:5432` → cloud SQL) |
| **Adapter** | converts app metrics/logs to a standard format |
| **Init** | DB migrations, wait-for-dependency, fetch config/certs |

Why native sidecars matter: old-style sidecars (just another container) broke **Jobs** (the Job never
finished because the sidecar kept running) and started in random order. Native sidecars fix both.

### 1.7 Static Pods

Files in `/etc/kubernetes/manifests/` on a node are run directly by kubelet (no scheduler). The API shows a
read-only **mirror Pod** named `<name>-<nodename>`. Deleting the mirror Pod does nothing — delete the file.

### 1.8 Termination and graceful shutdown

```text
 kubectl delete pod
   1. API sets deletionTimestamp → Pod shows Terminating
   2. In parallel:
        a. EndpointSlice controller removes Pod from Services (marks endpoint terminating)
        b. kubelet runs preStop hook, then sends SIGTERM to PID 1 of each container
   3. Wait up to terminationGracePeriodSeconds (counts preStop time too)
   4. SIGKILL anything still running; Pod object removed
```

Because (a) and (b) race, a Pod may still receive a few requests after SIGTERM. The common fix is a short
`preStop` sleep and an app that finishes in-flight requests on SIGTERM.

```bash
kubectl delete pod web --grace-period=0 --force   # ⚠️ only for stuck Pods; may leave the container running on a dead node
```

---

## 2. ReplicaSets

Keeps **N identical Pods** running that match a selector. It uses `ownerReferences` to own Pods and will
**adopt** orphan Pods that match its selector (a classic surprise). You almost never create ReplicaSets
yourself — Deployments do.

```yaml
apiVersion: apps/v1
kind: ReplicaSet
metadata:
  name: rs-demo
spec:
  replicas: 3
  selector:
    matchLabels: { app: rs-demo }
  template:
    metadata:
      labels: { app: rs-demo }       # must match selector
    spec:
      containers:
        - name: c
          image: nginx:1.27
```

```bash
kubectl apply -f rs.yaml
kubectl get rs rs-demo        # DESIRED CURRENT READY
kubectl delete pod -l app=rs-demo --wait=false; kubectl get pods -l app=rs-demo
kubectl scale rs rs-demo --replicas=5
```

| ReplicaSet | ⚠️ ReplicationController |
|------------|-------------------------|
| set-based selectors | equality only |
| managed by Deployments | legacy, don't use |

---

## 3. Deployments

### 3.1 What, why, how

A **Deployment** manages ReplicaSets to give you **declarative updates, rolling updates and rollback**.
Changing the Pod template creates a **new ReplicaSet** (named by a hash of the template:
`pod-template-hash` label) and gradually shifts replicas from old to new.

```text
 v1 RS (3) ─┐                 maxSurge=1, maxUnavailable=0
            │ step1: new RS 1, old 3   (4 total, never below 3 ready)
            │ step2: new RS 1 ready → old 2
            │ step3: new RS 2, old 2 → new ready → old 1 ...
 v2 RS (3) ◄┘ end: new 3, old 0 (old RS kept with 0 replicas for rollback)
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  labels: { app: web }
spec:
  replicas: 3
  revisionHistoryLimit: 5          # how many old ReplicaSets to keep for rollback
  progressDeadlineSeconds: 300     # mark rollout failed if no progress in 5 min
  minReadySeconds: 5               # a Pod must be Ready this long to count as available
  selector:
    matchLabels: { app: web }      # immutable after creation
  strategy:
    type: RollingUpdate            # or Recreate (kill all, then start new — causes downtime)
    rollingUpdate:
      maxSurge: 25%                # extra Pods allowed above replicas during update
      maxUnavailable: 0            # never drop below desired ready count
  template:
    metadata:
      labels: { app: web }
    spec:
      containers:
        - name: web
          image: nginx:1.27
          ports: [{ containerPort: 80 }]
          readinessProbe:
            httpGet: { path: /, port: 80 }
          resources:
            requests: { cpu: 50m, memory: 64Mi }
            limits: { memory: 128Mi }
```

### 3.2 Rolling updates and rollbacks — lab

```bash
kubectl apply -f deploy.yaml
kubectl rollout status deploy/web
kubectl set image deploy/web web=nginx:1.28        # triggers a rollout
kubectl annotate deploy/web kubernetes.io/change-cause="nginx 1.28" --overwrite
kubectl rollout status deploy/web
kubectl get rs -l app=web                          # old RS at 0, new RS at 3
kubectl rollout history deploy/web
kubectl set image deploy/web web=nginx:does-not-exist   # bad release
kubectl rollout status deploy/web --timeout=60s    # stalls: new Pods ImagePullBackOff, old Pods still serve (maxUnavailable=0)
kubectl rollout undo deploy/web                    # back to previous revision
kubectl rollout undo deploy/web --to-revision=1
kubectl rollout pause deploy/web                   # batch several changes...
kubectl set resources deploy/web -c web --limits=memory=256Mi
kubectl rollout resume deploy/web                  # ...then roll once
kubectl rollout restart deploy/web                 # restart all Pods (e.g. to pick up a new Secret)
kubectl scale deploy/web --replicas=5
```

### 3.3 Common Deployment failures

| Symptom | Cause | Diagnose |
|---------|-------|----------|
| `ImagePullBackOff` / `ErrImagePull` | wrong tag, private registry, rate limits | `describe pod` events |
| `CrashLoopBackOff` | app exits, bad config, missing env | `logs --previous`, exit code |
| Pods Running but 0/1 Ready | readiness probe failing | `describe pod`, probe path/port |
| Rollout stuck "waiting for rollout to finish" | new Pods never Ready, `ProgressDeadlineExceeded` | `rollout status`, `describe deploy` |
| `OOMKilled` (exit 137) | memory limit too low / leak | `describe pod` Last State |
| `CreateContainerConfigError` | missing ConfigMap/Secret key | events |
| Pending | no resources, taints, PVC | `describe pod` FailedScheduling |

Exit codes: `0` ok, `1` app error, `126/127` command not executable/not found, `137` SIGKILL (often OOM),
`139` segfault, `143` SIGTERM.

---

## 4. StatefulSets

### 4.1 What and why

For apps needing **stable network identity**, **stable per-Pod storage**, and **ordered** startup/shutdown.

| Guarantee | How |
|-----------|-----|
| Stable names | `db-0`, `db-1`, `db-2` |
| Stable DNS | `db-0.db-headless.ns.svc.cluster.local` via a **headless Service** |
| Stable storage | `volumeClaimTemplates` → PVC `data-db-0` follows `db-0` forever |
| Ordering | `OrderedReady`: create 0→N, delete N→0 (or `Parallel`) |

```yaml
apiVersion: v1
kind: Service
metadata:
  name: db-headless
spec:
  clusterIP: None                 # headless: DNS returns Pod IPs, gives per-Pod records
  selector: { app: db }
  ports: [{ port: 5432, name: pg }]
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: db
spec:
  serviceName: db-headless        # required: the governing headless Service
  replicas: 3
  podManagementPolicy: OrderedReady
  updateStrategy:
    type: RollingUpdate
    rollingUpdate:
      partition: 0                # >0 = only ordinals >= partition are updated (canary for stateful apps)
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain           # keep PVCs when the StatefulSet is deleted (safe default)
    whenScaled: Retain
  selector:
    matchLabels: { app: db }
  template:
    metadata:
      labels: { app: db }
    spec:
      containers:
        - name: postgres
          image: postgres:17
          env:
            - name: POSTGRES_PASSWORD
              value: "lab-only-change-me"      # use a Secret in real life (chapter 07)
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata
          ports: [{ containerPort: 5432, name: pg }]
          volumeMounts:
            - name: data
              mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        resources:
          requests:
            storage: 1Gi
```

```bash
kubectl apply -f sts.yaml
kubectl get pods -l app=db -w                       # db-0 → Ready → db-1 → db-2
kubectl get pvc                                     # data-db-0, data-db-1, data-db-2
kubectl run dns --image=busybox:1.36 --rm -it --restart=Never -- nslookup db-0.db-headless
kubectl delete pod db-1; kubectl get pods -l app=db # db-1 returns with SAME name and SAME PVC
kubectl scale sts db --replicas=1                   # deletes db-2 then db-1; PVCs remain
```

**Important:** a StatefulSet does **not** make your database replicate or fail over. Postgres replication,
leader election, and backups are the app's/operator's job (CloudNativePG, Zalando, Percona operators).

Common failures: PVC Pending (no StorageClass/default), Pod stuck because a lower ordinal is not Ready,
volume stuck attached to a dead node (multi-attach error).

---

## 5. DaemonSets

Runs **one Pod on every (matching) node**, adding Pods automatically as nodes join.

Use: CNI agents (calico-node, cilium), kube-proxy, log collectors (Fluent Bit), node-exporter, CSI node plugins.

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-agent
  namespace: kube-system
spec:
  selector:
    matchLabels: { app: node-agent }
  updateStrategy:
    type: RollingUpdate
    rollingUpdate: { maxUnavailable: 1 }
  template:
    metadata:
      labels: { app: node-agent }
    spec:
      tolerations:                         # also run on control-plane nodes
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
      containers:
        - name: agent
          image: busybox:1.36
          command: ["sh", "-c", "while true; do echo $(hostname) on $NODE; sleep 30; done"]
          env:
            - name: NODE
              valueFrom: { fieldRef: { fieldPath: spec.nodeName } }   # Downward API
          volumeMounts:
            - { name: varlog, mountPath: /var/log, readOnly: true }
      volumes:
        - name: varlog
          hostPath: { path: /var/log }
```

```bash
kubectl apply -f ds.yaml
kubectl get ds -n kube-system node-agent      # DESIRED = number of nodes
kubectl get pods -n kube-system -l app=node-agent -o wide
```

Common failures: Pods missing on some nodes due to taints (add tolerations) or `nodeSelector`.

---

## 6. Jobs

Run Pods **to completion**.

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: pi
spec:
  completions: 5               # total successful Pods needed
  parallelism: 2               # run at most 2 at once
  backoffLimit: 4              # retries before marking Failed
  activeDeadlineSeconds: 600   # hard time limit for the whole Job
  ttlSecondsAfterFinished: 3600  # auto-delete Job & Pods 1h after finishing
  completionMode: NonIndexed   # Indexed gives each Pod JOB_COMPLETION_INDEX (0..4) for sharding work
  podFailurePolicy:            # don't retry on known non-retriable exit codes
    rules:
      - action: FailJob
        onExitCodes: { containerName: pi, operator: In, values: [42] }
  template:
    spec:
      restartPolicy: Never     # Never or OnFailure (Always not allowed)
      containers:
        - name: pi
          image: perl:5.40
          command: ["perl", "-Mbignum=bpi", "-wle", "print bpi(200)"]
```

```bash
kubectl apply -f job.yaml
kubectl get jobs -w                         # COMPLETIONS 0/5 → 5/5
kubectl logs job/pi                         # logs of one of its Pods
kubectl describe job pi
kubectl create job oneoff --image=busybox:1.36 -- echo hello   # imperative
```

---

## 7. CronJobs

Creates Jobs on a cron schedule.

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
spec:
  schedule: "30 2 * * *"         # min hour dom month dow → 02:30 every day
  timeZone: "Asia/Kolkata"       # IANA zone (GA since v1.27); otherwise controller-manager's zone (UTC usually)
  concurrencyPolicy: Forbid      # Allow | Forbid (skip if previous still running) | Replace
  startingDeadlineSeconds: 300   # if missed by >5 min (controller down), skip
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: busybox:1.36
              command: ["sh", "-c", "echo backing up at $(date)"]
```

```bash
kubectl apply -f cron.yaml
kubectl get cronjob
kubectl create job manual-run --from=cronjob/nightly-backup   # test it now
kubectl patch cronjob nightly-backup -p '{"spec":{"suspend":true}}'   # pause
```

| | Job | CronJob | Deployment |
|--|-----|---------|------------|
| Ends? | yes | creates ending Jobs | no, runs forever |
| restartPolicy | Never/OnFailure | Never/OnFailure | Always |

Common failures: wrong timezone assumptions, overlapping runs (use `Forbid`), Jobs piling up (set history
limits/TTL), scripts that exit 0 on failure.

---

## 8. Replica management and disruption

- `kubectl scale` or HPA changes `replicas`.
- **PodDisruptionBudget** protects availability during voluntary disruptions (drain, upgrades):

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-pdb
spec:
  minAvailable: 2          # or maxUnavailable: 1
  selector:
    matchLabels: { app: web }
```

`kubectl drain` will refuse to evict Pods that would violate the PDB (and keep retrying).

---

## Troubleshooting flow for any workload

```bash
kubectl get pods -o wide                     # status, restarts, node
kubectl describe pod <pod>                   # events: scheduling, pulls, probes, OOM
kubectl logs <pod> -c <container> --previous # crash reason
kubectl get events --sort-by=.lastTimestamp
kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[*].lastState}'
kubectl debug -it <pod> --image=busybox:1.36 --target=<container>   # ephemeral debug container sharing PID ns
kubectl rollout status/history deploy/<name>
```

---

## Interview questions

1. **Deployment vs StatefulSet?** Deployment: interchangeable Pods, random names, shared/no storage.
   StatefulSet: stable names, DNS, per-Pod PVCs, ordered operations.
2. **Why do we rarely create ReplicaSets directly?** Deployments manage them and add rollouts/rollback.
3. **How does a rolling update work?** New ReplicaSet scaled up and old scaled down within maxSurge/maxUnavailable,
   gated by readiness.
4. **Liveness vs readiness vs startup?** Restart if stuck / remove from traffic / protect slow starts.
5. **What is CrashLoopBackOff?** Container repeatedly crashes; kubelet restarts with growing back-off.
6. **Init container vs sidecar?** Init runs to completion before app; native sidecar (`restartPolicy: Always`
   init container) runs alongside the app for its lifetime.
7. **What is a DaemonSet used for?** One Pod per node: networking, logging, monitoring agents.
8. **How do you run a task every night?** CronJob with `concurrencyPolicy: Forbid`, `timeZone`, history limits.
9. **What happens on `kubectl delete pod`?** Terminating → endpoints removed + preStop → SIGTERM → grace → SIGKILL.
10. **What is a PodDisruptionBudget?** Minimum availability guarantee for voluntary evictions.

**Scenario:** After a deploy, error rates spike for ~2 seconds per Pod replacement. → Pods receive traffic
after SIGTERM / before ready: add readiness probe, `preStop` sleep, graceful shutdown handling, `minReadySeconds`.

**Follow-ups:** How does `pod-template-hash` work? Why does a StatefulSet need a headless Service?
How do Indexed Jobs help parallel batch processing? What is `podFailurePolicy`?
