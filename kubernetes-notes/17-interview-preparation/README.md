# 17 — Interview Preparation (Consolidated)

Every chapter ends with 10 questions. This chapter adds: a **rapid-fire bank** across topics, **scenario drills** with model
answers, **whiteboard walkthroughs**, a **command cheat sheet**, and a **mock interview plan**.

---

## 1. How to answer Kubernetes interview questions

1. **Define** in one sentence ("A Service is a stable virtual IP and DNS name in front of a changing set of Pods").
2. **Explain the mechanism** ("The EndpointSlice controller tracks ready Pods matching the selector; kube-proxy programs DNAT…").
3. **Give a production example / trade-off** ("We use `externalTrafficPolicy: Local` on our NLB to preserve client IPs for rate limiting").
4. For troubleshooting: **say the commands you'd run, in order**, and what output would confirm each hypothesis.

---

## 2. Rapid-fire bank (answer in ≤ 2 sentences)

### Fundamentals & architecture
1. What runs on a control-plane node? — API server, etcd, scheduler, controller-manager (+ cloud-controller-manager).
2. Which component talks to etcd? — Only the API server.
3. What is a Pod? — Smallest deployable unit; containers sharing network namespace and volumes.
4. Why the pause container? — Holds the Pod's namespaces so containers can restart without losing the IP.
5. What does kubelet do? — Node agent that runs Pods via CRI, probes, mounts volumes, reports status.
6. How is a node detected as dead? — Its Lease isn't renewed within the grace period → `Unknown` → NoExecute taint → eviction.
7. What happened to dockershim? — Removed in v1.24; kubelet uses CRI runtimes (containerd/CRI-O).
8. Imperative vs declarative? — Commands vs desired-state files applied idempotently.
9. What is server-side apply? — API server computes merges and tracks field ownership per manager.
10. What is a static Pod? — Defined by a manifest file on the node, run directly by kubelet.

### Workloads
11. Deployment vs StatefulSet vs DaemonSet? — Stateless replicas / stable identity + storage / one per node.
12. maxSurge vs maxUnavailable? — Extra Pods allowed vs Pods allowed to be unavailable during rollout.
13. CrashLoopBackOff first steps? — `kubectl logs --previous`, `describe pod` (exit code, OOMKilled), check config/secrets.
14. Readiness vs liveness? — Remove from traffic vs restart container.
15. Native sidecar? — Init container with `restartPolicy: Always`; starts before and stops after app containers.
16. Job vs CronJob? — Run to completion vs scheduled Jobs.
17. PodDisruptionBudget? — Limits voluntary evictions to keep minimum availability.
18. Exit code 137? — SIGKILL; commonly OOMKilled.

### Networking
19. Kubernetes networking model? — Unique Pod IPs, Pod-to-Pod without NAT, implemented by CNI.
20. What does CNI do? — Runtime executes plugin to create Pod interfaces, assign IPs (IPAM), set routes.
21. Service types? — ClusterIP, NodePort, LoadBalancer, ExternalName; headless via `clusterIP: None`.
22. How does kube-proxy implement Services? — Programs iptables/nftables/IPVS DNAT from Services + EndpointSlices.
23. Why can't you ping a ClusterIP? — Virtual IP only matched by port-specific NAT rules (except IPVS mode).
24. What is an EndpointSlice? — Scalable list of backend addresses with readiness/topology for a Service.
25. Service FQDN? — `<svc>.<ns>.svc.cluster.local`.
26. ndots:5 issue? — External names try search domains first → extra DNS queries/latency.
27. Ingress vs Gateway API? — Gateway API is role-oriented, more expressive, portable; Ingress is frozen.
28. NetworkPolicy default? — All allowed until a policy selects a Pod; then only allowed traffic passes.
29. Overlay vs direct routing? — Encapsulate Pod packets between nodes vs route Pod CIDRs natively.
30. VXLAN port? — UDP 4789 (IANA); Linux/Flannel/Cilium default 8472.
31. externalTrafficPolicy Local? — Preserve client IP, only local endpoints, no SNAT/extra hop.
32. What is conntrack? — Kernel flow table storing NAT state; exhaustion drops packets.
33. Calico vs Cilium vs Flannel? — L3/BGP + policy / eBPF + L7 + observability / simple overlay, no policy.
34. What is a service mesh? — Proxies adding mTLS, traffic control, telemetry for east-west traffic.

### Storage & config
35. PV vs PVC vs StorageClass? — Storage / claim / provisioning template.
36. RWO vs RWX? — One node vs many nodes read-write.
37. WaitForFirstConsumer? — Provision volume after scheduling, in the right zone.
38. ConfigMap vs Secret? — Non-sensitive vs sensitive (base64, encrypt at rest).
39. How do env vars from ConfigMaps update? — They don't; restart Pods (volumes update).
40. Encrypt Secrets at rest? — EncryptionConfiguration with KMS provider (managed: cloud KMS envelope encryption).

### Scheduling & scaling
41. Requests vs limits? — Scheduling reservation vs runtime cap.
42. QoS classes? — Guaranteed, Burstable, BestEffort (eviction order).
43. Taints vs affinity? — Taints repel from nodes; affinity attracts Pods to nodes/Pods.
44. Topology spread? — Even distribution across zones/nodes with maxSkew.
45. HPA formula? — `ceil(current × metric/target)`.
46. HPA shows `<unknown>`? — metrics-server missing or no resource requests.
47. Cluster Autoscaler vs Karpenter? — Node group resizing vs direct right-sized instance provisioning + consolidation.

### Security
48. RBAC objects? — Role, ClusterRole, RoleBinding, ClusterRoleBinding.
49. PSP replacement? — Pod Security Admission (privileged/baseline/restricted).
50. Least-privilege container? — non-root, drop ALL caps, no privilege escalation, read-only rootfs, seccomp RuntimeDefault.
51. Why is `create pods` powerful? — Can mount any Secret/SA in the namespace.
52. Pods → AWS? — EKS Pod Identity/IRSA, never static keys.
53. ValidatingAdmissionPolicy? — CEL-based validation in the API server.

### Ops & ecosystem
54. Helm release history stored where? — Secrets in the release namespace.
55. GitOps? — Git is the source of truth; in-cluster agent pulls and reconciles.
56. Canary vs blue-green? — Gradual weighted shift vs full instant switch.
57. Operator? — CRDs + controller encoding operational knowledge.
58. Finalizer? — Blocks deletion until a controller cleans up.
59. Metrics Server vs Prometheus? — Autoscaling resource metrics vs full monitoring/alerting.
60. etcd backup? — `etcdctl snapshot save` (+ test restore).

---

## 3. Scenario drills (practise out loud)

### S1 — "Users report the site is down."
1. Scope: all users/paths? `curl -sv https://site` from outside — DNS, TLS, HTTP code.
2. Edge: LB health (`kubectl get svc/ingress/gateway`, cloud console target health), controller Pods/logs.
3. Backend: `kubectl get endpointslices` for the backend Service — empty? → Pods not Ready (`describe`, probes, logs).
4. Recent change? `kubectl rollout history`, Argo CD history → roll back first, debug after.
5. Dependencies: DB, DNS (`dig` from a Pod), external APIs.
6. Communicate, mitigate (rollback/scale), then root-cause and postmortem.

### S2 — "Pod stuck Pending."
`kubectl describe pod` → FailedScheduling message: insufficient resources (autoscaler? quotas? requests too big), taints,
affinity/spread, PVC binding/zone, max Pods per node/IP exhaustion. Fix accordingly.

### S3 — "Service A gets intermittent timeouts calling B."
Per-endpoint test (curl each Pod IP) → one bad Pod/node? Node-level: conntrack stats, kube-proxy sync, CNI agent health, MTU for
large payloads. DNS 5 s delays? Check client timeouts/retries, HTTP keep-alive and connection reuse to terminated Pods.

### S4 — "Deployment rollout stuck."
`kubectl rollout status` → `describe deploy` (ProgressDeadlineExceeded) → new Pods ImagePullBackOff / CrashLoop / not Ready /
Pending (no capacity for surge). `rollout undo`; fix image/config/probes/requests.

### S5 — "Node NotReady."
SSH/`kubectl debug node`: `systemctl status kubelet containerd`, `journalctl -u kubelet`, disk/inodes, memory, certs, CNI.
Workloads auto-move after ~5 min; cordon/drain; replace node if needed.

### S6 — "Memory keeps growing, Pods OOMKilled."
Confirm `OOMKilled` + limits; graph `container_memory_working_set_bytes`; leak vs undersized; JVM/Go runtime settings
(`-XX:MaxRAMPercentage`, `GOMEMLIMIT`); right-size, fix leak, VPA recommendations.

### S7 — "After enabling default-deny NetworkPolicies, everything broke."
DNS egress missing; ingress-controller namespace not allowed; monitoring scrape blocked; Pod ports vs Service ports; roll out with
flow logs (Hubble/Calico) first.

### S8 — "Our EKS cluster can't create new Pods: failed to assign IP."
Subnet/ENI exhaustion → prefix delegation, bigger subnets/secondary CIDR, instance types; check `aws-node` logs.

### S9 — "A secret was leaked in a Git commit."
Rotate immediately (assume compromised), revoke tokens, remove from history (and accept it's still compromised), move to External
Secrets/SOPS, add secret scanning in CI.

### S10 — "Design a highly available production platform."
Multi-AZ managed control plane, ≥3 AZ node spread, Karpenter, PDBs + topology spread, GitOps, Gateway API + cloud LB, CNI with
policy, mesh if mTLS/L7 needed, managed DB, observability stack with SLO alerts, backups (Velero/RDS), security baseline (PSA,
admission policies, image signing, workload identity), cost controls.

---

## 4. Whiteboard walkthroughs to master

1. **`kubectl apply` → running Pod** (chapter 02 §3): API → etcd → controllers → scheduler → kubelet → CRI → CNI → probes → endpoints.
2. **Packet from Pod A (node1) to Service → Pod B (node2)**: DNS → DNAT on node1 (KUBE-SVC/SEP or nft map) → route to node2's Pod CIDR
   (VXLAN or direct) → node2 → veth → Pod B → reply un-NAT by conntrack.
3. **Internet → Pod via Ingress/Gateway**: DNS → LB → (NodePort DNAT or IP target) → controller Pod (TLS, host/path) → backend Pod IP.
4. **Pod → internet**: default route → node → MASQUERADE to node IP → NAT gateway → internet.
5. **Rolling update with readiness gates and graceful shutdown.**
6. **HPA + Cluster Autoscaler/Karpenter interaction during a traffic spike.**
7. **GitOps release flow from commit to production with rollback.**

---

## 5. Command cheat sheet

```bash
# context & discovery
kubectl config get-contexts; kubectl config use-context <ctx>; kubectl config set-context --current --namespace=<ns>
kubectl api-resources; kubectl explain <kind>.<field> --recursive
# inspect
kubectl get pods -A -o wide; kubectl get all -n <ns>; kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl describe pod <p>; kubectl logs <p> -c <c> --previous -f; kubectl top pods -A --sort-by=cpu
kubectl get pod <p> -o yaml; kubectl get pods -o jsonpath='{.items[*].status.podIP}'
kubectl get pods -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName,IP:.status.podIP
# debug
kubectl exec -it <p> -- sh; kubectl debug -it <p> --image=nicolaka/netshoot --target=<c>
kubectl debug node/<n> -it --image=nicolaka/netshoot; kubectl port-forward svc/<s> 8080:80
kubectl run tmp --rm -it --image=nicolaka/netshoot -- bash
# networking
kubectl get svc,endpointslices -n <ns>; kubectl get ingress,gateway,httproute -A; kubectl get networkpolicy -A
# rollouts
kubectl rollout status|history|undo|restart deploy/<d>; kubectl set image deploy/<d> <c>=<img>
kubectl scale deploy/<d> --replicas=N; kubectl autoscale deploy/<d> --cpu-percent=60 --min=2 --max=10
# generate YAML fast
kubectl create deploy web --image=nginx:1.27 --dry-run=client -o yaml
kubectl expose deploy web --port=80 --target-port=8080 --dry-run=client -o yaml
kubectl create job j --image=busybox:1.36 --dry-run=client -o yaml -- echo hi
kubectl create cronjob c --image=busybox:1.36 --schedule="*/5 * * * *" --dry-run=client -o yaml -- date
# RBAC
kubectl auth can-i <verb> <resource> --as <user|system:serviceaccount:ns:sa> -n <ns>
kubectl create role|rolebinding|clusterrole|clusterrolebinding ...
# nodes
kubectl cordon|uncordon|drain <n> --ignore-daemonsets --delete-emptydir-data; kubectl taint nodes <n> k=v:NoSchedule[-]
# node-level (SSH)
systemctl status kubelet containerd; journalctl -u kubelet -f; crictl ps; crictl logs <id>
ip addr; ip route; ip neigh; ss -tulpn; iptables-save -t nat | grep KUBE; nft list ruleset; conntrack -L; tcpdump -ni any port 53
```

---

## 6. Common mistakes interviewers probe for

- Confusing Linux namespaces with Kubernetes namespaces.
- Saying "kube-proxy forwards traffic" (it programs the kernel).
- Using liveness probes that check dependencies.
- No resource requests → poor scheduling, broken HPA.
- Believing Secrets are encrypted by default.
- Thinking NetworkPolicies work without a supporting CNI.
- Forgetting DNS when writing egress policies.
- Treating StatefulSets as automatic database HA.
- `latest` tags and mutable images in production.
- Skipping PDBs, then a node drain takes a service down.
- Recommending deprecated tools (PSP, dockershim, `apt.kubernetes.io`, Weave, community ingress-nginx for new builds).

---

## 7. Advanced follow-up topics (senior level)

- etcd performance tuning, compaction/defragmentation, disaster recovery restore steps.
- API Priority and Fairness; watch cache; large-cluster limits (5,000 nodes / 150,000 Pods guidance).
- kube-proxy nftables vs eBPF performance; Maglev, DSR, socket LB.
- Multi-cluster: Cluster API, Cilium ClusterMesh, Istio multi-primary, Karmada, multi-cluster Services (MCS API).
- Dynamic Resource Allocation (DRA) for GPUs; scheduling AI workloads (Kueue, gang scheduling).
- Supply chain: SLSA levels, Sigstore policy-controller, in-toto attestations.
- Writing controllers: informers, workqueues, idempotency, status conditions, finalizers, envtest.
- Zero-downtime cluster upgrades: surge node groups, blue-green clusters, API deprecation scanning (`pluto`, `kubent`).

---

## 8. Mock interview plan (2 weeks)

| Day | Focus | Exercise |
|-----|-------|----------|
| 1 | Architecture | Draw §4.1 from memory; explain each component in 60 s |
| 2 | Workloads | Write Deployment/StatefulSet/Job YAML without docs (use `kubectl explain` only) |
| 3–4 | Networking | Draw §4.2–4.4; run labs 05.05/05.06 and narrate packet flow |
| 5 | DNS + policy | Break DNS with a policy and fix it, timed |
| 6 | Troubleshooting | Partner breaks your kind cluster (wrong selector, bad image, taint, policy); fix in < 10 min each |
| 7 | Storage/config | PVC + Secret + ConfigMap app from scratch |
| 8 | Scheduling/scaling | Pending-Pod drills; HPA lab |
| 9 | Security | RBAC user + PSA restricted + hardened Pod |
| 10 | Observability | Write 5 PromQL queries and 2 alerts from memory |
| 11 | Helm/GitOps | Package project 3 as a chart; deploy via Argo CD |
| 12 | Cloud | Explain EKS networking, IAM, LB controller, cost levers |
| 13 | System design | S10 in 30 minutes, whiteboard |
| 14 | Full mock | 60 min: 20 rapid-fire + 2 scenarios + 1 design + 1 live debug |

Good luck — and keep breaking clusters on purpose. That's where the real learning happens.
