# Kubernetes Handbook — Beginner to Advanced (Ubuntu / Linux)

A structured, hands-on Kubernetes handbook written for someone who already knows Linux basics,
Docker, and some DevOps, and wants to become fluent in Kubernetes for real production work and
technical interviews.

> **Networking is the highest-priority subject** in this handbook. Chapter `05-networking/` is
> twelve sub-chapters long and goes from IP addressing all the way to eBPF, service mesh and a
> full troubleshooting playbook.

---

## How to use these notes

1. Work through the chapters **in order**. Each chapter assumes the earlier ones.
2. Every chapter has the same shape:
   - **Concepts** — what it is, why it exists, how it works internally.
   - **Hands-on labs** — copy/paste commands for Ubuntu, with the expected output explained.
   - **Production notes** — what changes when you do it for real.
   - **Common mistakes & troubleshooting**.
   - **Interview questions** — 10 questions with simple answers, plus scenario and follow-up questions.
3. Type the commands yourself instead of pasting whole blocks. Break things on purpose and fix them.
4. Tick the checkboxes below as you go (they render as real checkboxes on GitHub).

### Lab environment you need

| Item | Recommended |
|------|-------------|
| OS | Ubuntu 22.04 or 24.04 LTS (laptop, VM, or WSL2-free bare Linux) |
| CPU / RAM | 4 vCPU, 8 GB RAM minimum (16 GB for observability + Istio labs) |
| Disk | 40 GB free |
| Tools | `docker`, `kubectl`, `kind`, `helm` (installed in chapter 03) |
| Optional | `minikube`, 3 Ubuntu VMs for `kubeadm` (Multipass/VirtualBox/KVM), an AWS account for EKS |

### Conventions used in every file

```bash
# Lines starting with "#" inside a code block are explanations, not commands.
kubectl get pods          # a command you type
```

- `<pod-name>` means "replace with your value".
- `$` prompts are **not** shown so you can copy commands cleanly.
- `sudo` is used **only** when root is required, and the reason is stated.
- Version numbers appear as shell variables (for example `K8S_MINOR=v1.36`). Always check the
  official release page for the current version before installing.
- ⚠️ marks a **deprecated or retired** approach. ✅ marks the modern replacement.

---

## Learning order and progress tracker

### Part 1 — Foundations
- [ ] [00 — Linux prerequisites for Kubernetes](00-linux-prerequisites/README.md)
- [ ] [01 — Kubernetes fundamentals](01-kubernetes-fundamentals/README.md)
- [ ] [02 — Architecture deep dive](02-architecture/README.md)
- [ ] [03 — Cluster setup on Linux (kind, Minikube, kubeadm)](03-cluster-setup/README.md)
- [ ] [04 — Workloads & controllers](04-workloads/README.md)

### Part 2 — Networking (top priority)
- [ ] [05.01 — Networking basics (IP, CIDR, subnetting, ARP, DNS, TCP/UDP)](05-networking/01-networking-basics/README.md)
- [ ] [05.02 — Linux networking internals (netns, veth, bridges, netfilter, VXLAN)](05-networking/02-linux-networking/README.md)
- [ ] [05.03 — Kubernetes pod networking model & packet flows](05-networking/03-pod-networking/README.md)
- [ ] [05.04 — CNI deep dive (Flannel, Calico, Cilium)](05-networking/04-cni/README.md)
- [ ] [05.05 — Services deep dive](05-networking/05-services/README.md)
- [ ] [05.06 — kube-proxy internals (iptables, IPVS, nftables, eBPF)](05-networking/06-kube-proxy/README.md)
- [ ] [05.07 — DNS & CoreDNS](05-networking/07-dns-coredns/README.md)
- [ ] [05.08 — Ingress & Gateway API](05-networking/08-ingress-gateway/README.md)
- [ ] [05.09 — Network Policies](05-networking/09-network-policies/README.md)
- [ ] [05.10 — Advanced networking (BGP, MTU, Multus, eBPF, mTLS)](05-networking/10-advanced-networking/README.md)
- [ ] [05.11 — Istio service mesh](05-networking/11-istio-service-mesh/README.md)
- [ ] [05.12 — Networking troubleshooting playbook](05-networking/12-troubleshooting/README.md)

### Part 3 — Running real applications
- [ ] [06 — Storage](06-storage/README.md)
- [ ] [07 — Configuration & Secrets](07-configuration/README.md)
- [ ] [08 — Scheduling & resource management](08-scheduling/README.md)
- [ ] [09 — Autoscaling](09-autoscaling/README.md)

### Part 4 — Operating clusters
- [ ] [10 — Security](10-security/README.md)
- [ ] [11 — Observability](11-observability/README.md)
- [ ] [12 — Helm](12-helm/README.md)
- [ ] [13 — Kubernetes API, CRDs & Operators](13-api-crds-operators/README.md)
- [ ] [14 — CI/CD & GitOps](14-cicd-gitops/README.md)
- [ ] [15 — Cloud Kubernetes (EKS focus, AKS, GKE)](15-cloud-eks/README.md)

### Part 5 — Build and prove it
- [ ] [16 — Projects (beginner → production)](16-projects/README.md)
  - [ ] Project 1 — Nginx with Pods, Services, ConfigMaps
  - [ ] Project 2 — Django + PostgreSQL + PVC + Secrets + Ingress
  - [ ] Project 3 — Three-tier app with NetworkPolicies, HPA, monitoring
  - [ ] Project 4 — Production-style on EKS with Helm, CI/CD, TLS, observability
- [ ] [17 — Interview preparation (consolidated)](17-interview-preparation/README.md)

---

## Suggested schedule (part-time, ~1.5 h/day)

| Week | Chapters | Milestone |
|------|----------|-----------|
| 1 | 00, 01 | You can explain namespaces/cgroups and write a Deployment YAML from memory |
| 2 | 02, 03 | You have a kind cluster and a 3-node kubeadm cluster |
| 3 | 04 | You can debug CrashLoopBackOff, rollouts, Jobs |
| 4–6 | 05.01 – 05.06 | You can trace a packet from Pod → Service → Pod on paper and with `tcpdump` |
| 7 | 05.07 – 05.09 | DNS, Ingress/Gateway and NetworkPolicy labs done |
| 8 | 05.10 – 05.12 | Istio canary lab done; you can work the troubleshooting playbook |
| 9 | 06, 07, 08 | Stateful app with PVC + Secrets, scheduling rules |
| 10 | 09, 10 | HPA lab, RBAC lab, Pod Security |
| 11 | 11, 12, 13 | Prometheus/Grafana up; your own Helm chart; a CRD |
| 12 | 14, 15 | GitOps pipeline, EKS cluster |
| 13–14 | 16, 17 | All four projects, mock interviews |

---

## Version and currency notes (read once)

Kubernetes ships three minor releases per year and each minor is supported for about 14 months.
Important "things that changed" that older tutorials get wrong:

| Topic | Old / deprecated | Current |
|-------|------------------|---------|
| Runtime | ⚠️ dockershim (removed in v1.24) | ✅ containerd or CRI-O via CRI |
| Package repo | ⚠️ `apt.kubernetes.io` / `packages.cloud.google.com` (frozen 2023) | ✅ `pkgs.k8s.io` |
| Pod security | ⚠️ PodSecurityPolicy (removed v1.25) | ✅ Pod Security Admission + ValidatingAdmissionPolicy |
| Endpoints | ⚠️ `v1 Endpoints` (deprecated v1.33) | ✅ `discovery.k8s.io/v1 EndpointSlice` |
| kube-proxy | ⚠️ IPVS mode (deprecated v1.35) | ✅ iptables (default) or nftables (GA v1.33) |
| Sidecars | ad-hoc extra containers | ✅ native sidecars: init container with `restartPolicy: Always` (GA v1.33) |
| Ingress controller | ⚠️ community `ingress-nginx` (retired March 2026) | ✅ Gateway API + a maintained controller (Envoy Gateway, NGINX Gateway Fabric, Traefik, Cilium, Istio…) |
| cgroups | ⚠️ cgroup v1 (kubelet refuses it by default in recent releases) | ✅ cgroup v2 + systemd driver |
| Weave Net | ⚠️ unmaintained since 2024 | ✅ Calico / Cilium / Flannel |
| Dashboard | ⚠️ `kubernetes/dashboard` archived | ✅ Headlamp (SIG UI), Lens, k9s |
| Log shipping | ⚠️ Promtail (EOL) | ✅ Grafana Alloy, Fluent Bit, OpenTelemetry Collector |
| EKS auth | ⚠️ `aws-auth` ConfigMap | ✅ EKS access entries; Pod Identity (or IRSA) for workloads |
| HPA API | ⚠️ `autoscaling/v2beta2` | ✅ `autoscaling/v2` |

When in doubt, check: <https://kubernetes.io/docs/reference/using-api/deprecation-guide/>.

---

## Directory map

```text
kubernetes-notes/
├── README.md                      ← you are here
├── 00-linux-prerequisites/
├── 01-kubernetes-fundamentals/
├── 02-architecture/
├── 03-cluster-setup/
├── 04-workloads/
├── 05-networking/
│   ├── README.md                  ← networking roadmap
│   ├── 01-networking-basics/
│   ├── 02-linux-networking/
│   ├── 03-pod-networking/
│   ├── 04-cni/
│   ├── 05-services/
│   ├── 06-kube-proxy/
│   ├── 07-dns-coredns/
│   ├── 08-ingress-gateway/
│   ├── 09-network-policies/
│   ├── 10-advanced-networking/
│   ├── 11-istio-service-mesh/
│   └── 12-troubleshooting/
├── 06-storage/
├── 07-configuration/
├── 08-scheduling/
├── 09-autoscaling/
├── 10-security/
├── 11-observability/
├── 12-helm/
├── 13-api-crds-operators/
├── 14-cicd-gitops/
├── 15-cloud-eks/
├── 16-projects/
└── 17-interview-preparation/
```
