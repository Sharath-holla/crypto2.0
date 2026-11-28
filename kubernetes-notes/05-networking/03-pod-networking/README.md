# 05.03 — Kubernetes Pod Networking Model & Packet Flows

## 1. The Kubernetes network model (the rules every CNI must satisfy)

1. **Every Pod gets its own unique, cluster-wide IP address.**
2. **Pods can talk to all other Pods on any node without NAT** — the source IP the receiver sees is the sender's real Pod IP.
3. **Agents on a node** (kubelet, system daemons) can talk to all Pods on that node.
4. Pods in the host network can talk to all Pods.
5. Containers in the same Pod share the network namespace and talk over `localhost`.

Kubernetes **does not implement** this itself. It defines the rules; a **CNI plugin** builds the network using Linux
primitives (namespaces, veth, bridges, routes, tunnels, eBPF).

Why "no NAT between Pods"? It makes the network look like a flat set of VMs: apps see true peer IPs, NetworkPolicy can
match source IPs, port collisions disappear, and service discovery is simple.

---

## 2. The CIDRs you must know

```text
 Node network (underlay)     192.168.1.0/24 or VPC 10.0.0.0/16     → real node IPs
 Cluster Pod CIDR            10.244.0.0/16  (--cluster-cidr)       → all Pod IPs
   └─ per-node Pod CIDR      10.244.N.0/24  (node.spec.podCIDR)    → Pods on node N
 Service CIDR                10.96.0.0/12   (--service-cluster-ip-range) → virtual IPs, never on any interface
```

| Term | Where configured | Who uses it |
|------|------------------|-------------|
| Cluster CIDR (Pod CIDR) | kubeadm `podSubnet`, controller-manager `--cluster-cidr` | CNI IPAM, kube-proxy `clusterCIDR` (masquerade decisions) |
| Node Pod CIDR | controller-manager `--allocate-node-cidrs` → `node.spec.podCIDR` (or CNI's own IPAM, e.g. Calico blocks) | host-local IPAM, Flannel |
| Service CIDR | kube-apiserver `--service-cluster-ip-range` (also `ServiceCIDR` objects, GA v1.33) | ClusterIP allocation |
| Node network | your infrastructure | node IPs, NodePorts |

```bash
kubectl get nodes -o custom-columns=NAME:.metadata.name,PODCIDR:.spec.podCIDR,IP:.status.addresses[0].address
kubectl cluster-info dump | grep -m1 -E -- '--cluster-cidr|--service-cluster-ip-range'
kubectl get servicecidrs        # newer clusters: Service CIDR as an API object (can be extended live)
```

> Note: some CNIs ignore `node.spec.podCIDR`. **AWS VPC CNI** gives Pods real VPC IPs from the node's ENIs;
> **Calico** allocates /26 blocks on demand; **Cilium** supports `kubernetes`, `cluster-pool`, and cloud IPAM modes.

---

## 3. How a Pod receives an IP address (step by step)

```mermaid
sequenceDiagram
    participant K as kubelet
    participant R as containerd (CRI)
    participant P as pause container / netns
    participant C as CNI plugin (/opt/cni/bin/X)
    participant I as IPAM plugin
    K->>R: RunPodSandbox(pod metadata)
    R->>P: create pause container → new network namespace /var/run/netns/cni-xxxx
    R->>C: exec plugin, env CNI_COMMAND=ADD, CNI_NETNS=..., CNI_IFNAME=eth0, stdin=JSON config
    C->>C: create veth pair, move one end into netns as eth0
    C->>I: request IP (host-local / calico-ipam / cilium agent)
    I-->>C: 10.244.1.7/24, gateway 10.244.1.1
    C->>C: assign IP, add routes inside Pod + host route/bridge attach
    C-->>R: JSON result {interfaces, ips, routes, dns}
    R-->>K: sandbox ready (Pod IP)
    K->>K: start init + app containers in that netns; report status.podIP
```

1. kubelet asks the runtime for a **Pod sandbox**.
2. The runtime starts the **pause** container, which owns a new **network namespace**.
3. The runtime reads the first config in `/etc/cni/net.d/` and **executes** the plugin binary from `/opt/cni/bin/` with
   `CNI_COMMAND=ADD`.
4. The plugin creates the interface, calls **IPAM** for an address, sets routes, returns the result.
5. kubelet starts app containers that **join** the same netns and writes `status.podIP(s)`.
6. On Pod deletion: `CNI_COMMAND=DEL` releases the IP and removes interfaces.

---

## 4. Inside a Pod and on the node

Inside a Pod:

```bash
kubectl exec netshoot -- ip addr show eth0
# 3: eth0@if12: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
#     inet 10.244.1.7/24 ...        ← "@if12" = the peer veth is interface index 12 in the host namespace
kubectl exec netshoot -- ip route
# default via 10.244.1.1 dev eth0   (bridge-style CNI)   or   default via 169.254.1.1 dev eth0 (Calico)
kubectl exec netshoot -- cat /sys/class/net/eth0/iflink     # 12
```

On the node (kind: `docker exec -it lab-worker bash`; real node: SSH):

```bash
ip -o link | grep '^12:'          # 12: vethab12cd@if3 ... ← host end of that Pod's veth
ip route | grep 10.244
# kindnet/ptp style:   10.244.1.7 dev vethab12cd scope host    (one /32 route per local Pod)
#                      10.244.2.0/24 via 172.18.0.4 dev eth0   (whole Pod CIDR of another node via its node IP)
# flannel style:       10.244.1.0/24 dev cni0 ... (local bridge)  10.244.2.0/24 via 10.244.2.0 dev flannel.1 onlink
# calico style:        10.244.1.7 dev cali1234 scope link       blackhole 10.244.1.0/26 proto bird
crictl pods; crictl inspectp <pod-id> | grep -A3 '"network"'   # netns path
```

---

## 5. The six communication scenarios

### 5.1 Pod → Pod, same node

```text
 node1
 ┌──────────────────────────────────────────────────────────────┐
 │ PodA 10.244.1.5          PodB 10.244.1.6                     │
 │ eth0 ═══veth═══ vethA ─┐      ┌─ vethB ═══veth═══ eth0        │
 │                        └ cni0 ┘   (bridge CNI: L2 switch)     │
 │            or:  vethA → host routing table → vethB  (ptp/Calico: L3) │
 └──────────────────────────────────────────────────────────────┘
```

1. PodA sends to 10.244.1.6. Bridge CNI: same /24 → ARP → frame through vethA → `cni0` switches it to vethB.
   Routed CNI (Calico/kindnet): default route → host → host route `10.244.1.6 dev vethB` → vethB.
2. With `br_netfilter`, the bridged packet still passes netfilter (policies, Service reverse-NAT).
3. No encapsulation, no NAT.

### 5.2 Pod → Pod, different nodes

**(a) Overlay (VXLAN, e.g. Flannel default, Calico VXLAN mode, Cilium tunnel mode):**

```text
 node1 192.168.1.11                                   node2 192.168.1.12
 PodA 10.244.1.5                                      PodC 10.244.2.9
  │ eth0 → veth → host routing:                         ▲
  │ "10.244.2.0/24 via flannel.1"                        │ veth → eth0
  ▼                                                     │
 flannel.1 (VTEP) encapsulates:                        flannel.1 decapsulates
 [IP 192.168.1.11→192.168.1.12 | UDP 8472 | VXLAN | inner IP 10.244.1.5→10.244.2.9]
  │                                                     ▲
  └────────────── eth0 ═══ underlay network ═══ eth0 ───┘
```

**(b) Direct routing (Flannel `host-gw`, Calico BGP no-encap, kindnet, Cilium native routing, cloud routes):**

```text
 node1 route: 10.244.2.0/24 via 192.168.1.12 dev eth0
 packet leaves node1 UNCHANGED: [IP 10.244.1.5 → 10.244.2.9], dst MAC = node2's MAC
 requirement: nodes share an L2 segment, OR the underlay routers know Pod routes (BGP / VPC route tables)
```

**(c) Native VPC IPs (AWS VPC CNI, Azure CNI):** Pods have real VPC addresses, the VPC fabric routes them directly.

| | Overlay | Direct routing | Cloud-native IPs |
|--|---------|----------------|------------------|
| Underlay must know Pod IPs | no | yes (L2 or BGP/routes) | yes (it's the VPC) |
| Overhead | encapsulation, lower MTU | none | none |
| Works across subnets/clouds | ✅ | needs BGP/routes | within VPC |
| Debug visibility | must decode tunnel | plain IP | plain IP |

### 5.3 Pod → host (its own node)

PodA → node IP 192.168.1.11: default route → gateway (bridge IP / 169.254.1.1) → host receives on veth/bridge → `INPUT`
chain → local process. To another node's IP: routed out the node's `eth0` — usually **not** masqueraded (source stays Pod IP)
inside the cluster CIDR rules, depending on CNI.

### 5.4 Host → Pod

The node has routes to every local Pod (bridge connected route or /32 per veth). `curl 10.244.1.5` on the node → `OUTPUT` →
route → veth → Pod. This is how kubelet runs HTTP probes.

### 5.5 Pod → external (internet)

```text
 PodA 10.244.1.5 → 142.250.0.1
  → node1 routing: default via VPC router
  → POSTROUTING: destination not in cluster CIDR → MASQUERADE: src 10.244.1.5 → 192.168.1.11 (node IP)
  → (cloud) NAT gateway may SNAT again to a public IP
  ← reply → conntrack restores dst 10.244.1.5 → veth → PodA
```

Consequences: external firewalls see **node IPs** (or NAT gateway IP), not Pod IPs. Want stable egress IPs? Use an
**egress gateway** (Cilium/Calico/Istio) or a NAT gateway with a fixed EIP.

### 5.6 External → Pod

Pod IPs are normally **not reachable from outside**. External traffic enters through:

- `NodePort` (node IP:30000-32767 → DNAT → Pod),
- `LoadBalancer` (cloud LB → NodePort or directly to Pod IPs in "IP mode"),
- `Ingress`/`Gateway` controller (L7 proxy Pod),
- `hostPort`/`hostNetwork` (rare).

Covered in [05.05 Services](../05-services/README.md) and [05.08 Ingress/Gateway](../08-ingress-gateway/README.md).

---

## 6. Lab — inspect Pod networking on kind

```bash
# 1) Pods on two different nodes
kubectl create deployment pinger --image=nicolaka/netshoot --replicas=3 -- sleep infinity
kubectl get pods -l app=pinger -o wide          # note IPs and NODE column
A=$(kubectl get pods -l app=pinger -o jsonpath='{.items[0].metadata.name}')
B_IP=$(kubectl get pods -l app=pinger -o jsonpath='{.items[1].status.podIP}')
B_NODE=$(kubectl get pods -l app=pinger -o jsonpath='{.items[1].spec.nodeName}')

# 2) Inside Pod A
kubectl exec $A -- ip -br addr
kubectl exec $A -- ip route
kubectl exec $A -- ping -c 3 $B_IP              # Pod → Pod, no NAT
kubectl exec $A -- traceroute -n $B_IP          # hops: own node → other node → Pod (direct routing in kind)

# 3) On the node hosting Pod B: watch packets arrive with the REAL source Pod IP
docker exec -it $B_NODE bash -c "apt-get >/dev/null 2>&1; which tcpdump || (apt-get update -qq && apt-get install -y -qq tcpdump)"
docker exec -it $B_NODE tcpdump -ni eth0 icmp -c 4 &
kubectl exec $A -- ping -c 2 $B_IP
# IP 10.244.1.5 > 10.244.2.9: ICMP echo request   ← Pod IPs on the node's eth0 = direct routing, no overlay

# 4) Node routing table: how does traffic find the other node?
docker exec $B_NODE ip route
# 10.244.1.0/24 via 172.18.0.3 dev eth0     ← kindnet installs routes to every other node's Pod CIDR
# 10.244.2.9 dev vethXXXX scope host        ← local Pods

# 5) Map Pod eth0 → host veth
IDX=$(kubectl exec $A -- cat /sys/class/net/eth0/iflink)
A_NODE=$(kubectl get pod $A -o jsonpath='{.spec.nodeName}')
docker exec $A_NODE ip -o link | grep "^$IDX:"

# 6) Pod → external: see masquerade
kubectl exec $A -- curl -s -o /dev/null -w '%{http_code}\n' https://kubernetes.io
docker exec $A_NODE iptables -t nat -S | grep -i masq | head

kubectl delete deployment pinger
```

With Flannel or Calico VXLAN you would run `tcpdump -ni eth0 udp port 8472` (or 4789) and see encapsulated packets
instead — try it in [05.04](../04-cni/README.md).

---

## 7. Production considerations

- **IP capacity planning**: Pods per node × nodes, plus surge during rollouts. AWS VPC CNI consumes VPC IPs → use
  prefix delegation or a secondary CIDR (`100.64.0.0/10`).
- **MTU**: set correctly for overlay/WireGuard; mismatch = mysterious hangs.
- **Preserve source IP** where needed (Pod-to-Pod is preserved; external traffic depends on `externalTrafficPolicy`).
- **Egress**: decide masquerade rules (`ip-masq-agent`, Calico `natOutgoing`), egress gateways for allow-listed IPs.
- **Dual-stack**: plan IPv6 early; supported by all major CNIs.

---

## Interview questions

1. **State the Kubernetes networking model.** Unique IP per Pod; Pods reach all Pods without NAT; nodes reach Pods;
   implemented by CNI.
2. **How does a Pod get an IP?** kubelet → CRI creates sandbox netns → runtime executes CNI ADD → IPAM allocates → plugin
   configures veth/routes → IP returned.
3. **What's the pause container's networking role?** Owns the netns so app containers can restart without losing the IP.
4. **Same-node Pod-to-Pod path?** veth → bridge or host routes → peer veth; no encapsulation.
5. **Cross-node path with VXLAN?** Route to VTEP → encapsulate in UDP between node IPs → decapsulate → route to Pod veth.
6. **Overlay vs direct routing trade-offs?** Overlay works anywhere but adds overhead/MTU; direct routing is faster but
   requires L2 adjacency or BGP/cloud routes.
7. **Why can't I reach a Pod IP from my laptop?** Pod CIDR is internal/unadvertised; use Service/Ingress or port-forward.
8. **What IP does an external API see from my Pod?** Usually the node IP (masquerade) or NAT gateway IP.
9. **What is node.spec.podCIDR?** The Pod range allocated to that node by the controller-manager, used by some IPAMs.
10. **What does `eth0@if12` mean?** The interface's veth peer has ifindex 12 in the host namespace.

**Scenario:** Pods on node A can't reach Pods on node B, but same-node works. → Inter-node routes/tunnel broken: CNI agent
down on a node, firewall/security group blocking VXLAN UDP 8472/4789 or BGP TCP 179/IP-in-IP proto 4, source/dest check on
cloud instances, MTU.

**Follow-ups:** How does AWS VPC CNI attach ENIs and secondary IPs? What changes with IPv6/dual-stack? How do you
preserve client source IP end-to-end?
