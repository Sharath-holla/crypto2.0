# 05.10 — Advanced Kubernetes Networking

## 1. Overlay vs underlay — choosing a design

```text
 UNDERLAY (physical/VPC): routes node IPs.  OVERLAY: Pod packets tunneled between nodes.

 Option A  Overlay everywhere          Pod pkt ─► [VXLAN/Geneve/IPIP] ─► underlay ─► decap
 Option B  Direct routing, same L2     node routes: PodCIDR(nodeX) via nodeX-IP
 Option C  BGP-advertised Pod CIDRs    nodes peer with ToR routers; fabric routes Pod IPs natively
 Option D  Cloud-native IPs            Pods get VPC IPs (AWS VPC CNI, Azure CNI, GKE VPC-native)
 Option E  Hybrid (CrossSubnet)        direct within a subnet, encapsulate across subnets
```

| Criterion | Overlay | BGP / direct | Cloud-native IPs |
|-----------|---------|--------------|------------------|
| Infra team involvement | none | high (routers, BGP) | cloud API quotas |
| Performance | encapsulation cost, lower MTU | line rate | line rate |
| Pod IPs reachable from outside | no | yes (if advertised) | yes (within VPC) |
| IP consumption | private, plentiful | plan ranges | consumes VPC IPs |
| Troubleshooting | decode tunnels | standard routing | cloud tools (VPC flow logs) |

## 2. Encapsulation types

| | VXLAN | IP-in-IP | Geneve | WireGuard |
|--|-------|----------|--------|-----------|
| Header | UDP + 8B VXLAN (L2 frame inside) | IP proto 4 (L3 inside) | UDP 6081 + TLV options | UDP 51820 + crypto |
| Overhead | 50 B | 20 B | 50 B+ | 60 B (v4) |
| Cloud friendliness | ✅ UDP passes most networks | ⚠️ proto 4 blocked in some clouds (Azure) | ✅ | ✅ |
| Encryption | no | no | no | yes |
| Used by | Flannel, Calico, Cilium | Calico | Cilium, OVN-Kubernetes | Calico, Cilium, Flannel |

## 3. BGP in Kubernetes

**BGP** (Border Gateway Protocol, TCP 179) lets routers exchange routes. With Calico (BIRD) or Cilium BGP control plane:

```text
       ToR router A (AS 65000)                    ToR router B (AS 65000)
          ▲ iBGP/eBGP peering                        ▲
   ┌──────┴───────┐                           ┌──────┴───────┐
   │ node1 AS65001│ advertises 192.168.0.0/26 │ node2 AS65001│ advertises 192.168.0.64/26
   └──────────────┘                           └──────────────┘
 Result: any machine in the datacentre can route to Pod IPs; also used to advertise Service/LoadBalancer IPs (MetalLB BGP,
 Calico service IP advertisement, Cilium LB-IPAM + BGP).
```

Concepts: **AS number**, **peering** (full mesh for small clusters; route reflectors for large), **ECMP** (equal-cost
multi-path for spreading LoadBalancer traffic across nodes).

```bash
# Calico
kubectl get bgpconfigurations,bgppeers
calicoctl node status            # peers and state "Established"
# Cilium
cilium bgp peers
cilium bgp routes advertised ipv4 unicast
```

## 4. MTU — getting it right

Rule: **Pod MTU = underlay MTU − encapsulation overhead** (− encryption overhead).

```bash
kubectl exec <pod> -- cat /sys/class/net/eth0/mtu
ip link show eth0                                   # on node
kubectl get felixconfiguration default -o yaml | grep -i mtu      # Calico (operator auto-detects by default)
kubectl -n kube-system get cm cilium-config -o yaml | grep -i mtu
# probe: largest unfragmented ping across nodes (payload = MTU − 28)
kubectl exec <pod> -- ping -M do -s 1422 -c 2 <pod-on-other-node>
```

AWS: VPC supports 9001 jumbo frames inside the VPC, but traffic through IGW/VPN/peering is 1500 → PMTUD must work.

## 5. Network bottlenecks and packet drops

| Bottleneck | Detect | Fix |
|-----------|--------|-----|
| conntrack table full | `dmesg \| grep conntrack`, `conntrack -S` | raise `nf_conntrack_max`; eBPF dataplane |
| SNAT port exhaustion (many connections to one external IP) | `conntrack -S` `insert_failed`; NAT gateway `ErrorPortAllocation` | connection pooling, more egress IPs, NAT gateway scaling |
| iptables rule explosion | slow kube-proxy syncs | nftables mode or eBPF |
| NIC/ENI PPS limits (cloud) | ENA `bw_in_allowance_exceeded`, `pps_allowance_exceeded` (`ethtool -S eth0`) | bigger instances, spread load |
| Single-flow throughput | iperf3 tests | multiple flows, MTU, offloads |
| DNS amplification | CoreDNS QPS | NodeLocal DNSCache, ndots |
| softirq CPU saturation | `top` %si, `/proc/softirqs` | RSS/RPS, eBPF/XDP |

```bash
ip -s link show eth0                      # RX/TX errors, dropped, overruns
nstat -az | grep -Ei 'drop|retrans|overflow'
ss -ti dst <ip>                            # per-connection RTT, retransmits, cwnd
kubectl run iperf-s --image=networkstatic/iperf3 -- -s
kubectl run iperf-c --image=networkstatic/iperf3 --rm -it --restart=Never -- -c <iperf-s-pod-ip> -t 10 -P 4
# eBPF drop tracing (node, root): pwru traces a packet through kernel functions and shows where it's dropped
sudo pwru --output-tuple 'host 10.244.1.5 and tcp port 8080'
```

## 6. CNI troubleshooting checklist

1. CNI DaemonSet Pod Running and Ready on **that** node?
2. `/etc/cni/net.d/` has exactly the expected config; binaries present.
3. IPAM has free addresses.
4. Node routes / tunnel interfaces exist for every other node.
5. Required ports open between nodes (UDP 8472/4789, TCP 179, proto 4, UDP 51820, Cilium TCP 4240 health).
6. Cloud: source/destination check disabled for non-VPC-native routing; security groups.
7. MTU consistent.
8. Agent logs: `calico-node`, `cilium-agent`, `aws-node`, `kube-flannel`.

```bash
cilium status; cilium-health status        # Cilium node-to-node health matrix
kubectl -n calico-system exec ds/calico-node -c calico-node -- calico-node -felix-live -bird-live
kubectl -n kube-system logs ds/aws-node -c aws-node | tail
```

## 7. Multus and multiple network interfaces

Default: one Pod, one interface (`eth0`). **Multus** is a "meta-plugin" that calls the default CNI for `eth0` and **extra CNI
plugins for `net1`, `net2`…** — needed for telco/NFV (SR-IOV, DPDK), storage networks, or separating data/management traffic.

```yaml
apiVersion: k8s.cni.cncf.io/v1
kind: NetworkAttachmentDefinition
metadata:
  name: storage-net
spec:
  config: |
    {
      "cniVersion": "1.0.0",
      "type": "macvlan",
      "master": "eth1",
      "mode": "bridge",
      "ipam": { "type": "whereabouts", "range": "10.50.0.0/24" }
    }
---
apiVersion: v1
kind: Pod
metadata:
  name: multi-nic
  annotations:
    k8s.v1.cni.cncf.io/networks: storage-net       # attach as net1
spec:
  containers:
    - { name: c, image: nicolaka/netshoot, command: ["sleep", "infinity"] }
```

```bash
kubectl exec multi-nic -- ip -br addr     # eth0 (cluster network) + net1 10.50.0.x (macvlan)
kubectl get pod multi-nic -o jsonpath='{.metadata.annotations.k8s\.v1\.cni\.cncf\.io/network-status}'
```

Secondary interfaces are **not** handled by Services/NetworkPolicy/kube-proxy.

## 8. eBPF and Cilium

**eBPF** = safe, verified programs loaded into the kernel at hooks (XDP at the NIC driver, tc ingress/egress, socket
`connect`/`sendmsg`, kprobes, tracepoints). Programs share state via **eBPF maps** (hash tables, LRU, LPM tries).

```text
 Traditional:  packet → netfilter chains (linear rules) → conntrack → routing → veth
 Cilium eBPF:  packet → XDP/tc program: lookup identity in map → policy map verdict → LB map (Service→backend)
                       → redirect straight to the destination veth (bpf_redirect_peer), skipping most of the stack
```

Benefits: O(1) map lookups, no iptables explosion, socket-level LB, DSR, Maglev, fine-grained observability (Hubble),
transparent encryption, bandwidth manager (EDT), BIG TCP.

### kube-proxy replacement

```bash
cilium install --set kubeProxyReplacement=true --set k8sServiceHost=<api-server-ip> --set k8sServicePort=6443
kubectl -n kube-system exec ds/cilium -- cilium-dbg status | grep KubeProxyReplacement   # True
kubectl -n kube-system exec ds/cilium -- cilium-dbg bpf lb list | head
sudo bpftool prog show | head; sudo bpftool map show | head      # on node: loaded eBPF programs/maps
```

`k8sServiceHost` is needed because without kube-proxy, nothing implements the `kubernetes` Service VIP until Cilium is up.

## 9. North-south vs east-west traffic

| | North-south | East-west |
|--|-------------|-----------|
| Direction | in/out of the cluster | between services inside |
| Entry points | LB, Ingress/Gateway, egress gateway, NAT GW | Services, Pod IPs |
| Controls | WAF, TLS at edge, rate limiting, DDoS protection | NetworkPolicy, mTLS, L7 AuthZ |
| Typical tools | cloud LB + Gateway API | service mesh, CNI policy |

## 10. Traffic encryption and mTLS

| Method | Layer | Identity | Notes |
|--------|-------|----------|-------|
| WireGuard (Calico/Cilium) | L3 node-to-node | node | transparent, encrypts all Pod traffic between nodes; no per-service auth |
| IPsec (Cilium) | L3 | node | FIPS-friendly |
| **mTLS via service mesh** | L4/L7 per connection | **workload (SPIFFE ID from ServiceAccount)** | encryption + authentication + authorization |
| App-level TLS | L7 | app certs | most work for developers |

**mTLS** = both sides present certificates. In meshes each workload gets a short-lived cert with a SPIFFE identity
(`spiffe://cluster.local/ns/shop/sa/api`), rotated automatically, enabling policies like "only `frontend` SA may call `api`".

```bash
cilium install --set encryption.enabled=true --set encryption.type=wireguard
kubectl -n kube-system exec ds/cilium -- cilium-dbg encrypt status
```

## 11. Service mesh networking (how traffic is captured)

```text
 Sidecar mode (Istio classic, Linkerd):
   app container → iptables REDIRECT (set up by istio-init or the Istio CNI plugin) → Envoy sidecar :15001 (outbound)
     → mTLS → remote Envoy :15006 (inbound) → app
 Ambient mode (Istio, GA 1.24): no sidecars.
   ztunnel (per-node DaemonSet) does L4 mTLS (HBONE tunnel, HTTP CONNECT over mTLS on port 15008)
   optional waypoint proxy (Envoy per namespace/service) for L7 policies and routing
 Cilium mesh: eBPF + per-node Envoy for L7, optional mutual authentication
```

Costs of sidecars: extra CPU/memory per Pod, latency (two extra proxy hops), startup ordering (solved by native sidecars).
Details in [05.11](../11-istio-service-mesh/README.md).

## 12. Egress control patterns

- **Egress gateway** (Cilium/Calico/Istio): route selected Pods' outbound traffic through specific nodes with fixed IPs so partners
  can allow-list them.
- **NAT gateway per AZ** (cloud) for stable public egress IPs.
- **Explicit proxy** (Squid/Envoy) with FQDN allow-lists for compliance.

---

## Interview questions

1. **Overlay vs underlay?** Underlay routes node IPs; overlay tunnels Pod traffic over it.
2. **VXLAN vs IP-in-IP?** VXLAN carries L2 frames in UDP (50 B, cloud-friendly); IP-in-IP carries L3 in IP proto 4 (20 B,
   sometimes blocked).
3. **What does BGP give Kubernetes?** Native routing of Pod/Service IPs into the datacentre network without encapsulation.
4. **Why does MTU matter for overlays?** Headers reduce the space for payload; mismatches cause silent large-packet drops.
5. **What is eBPF?** Sandboxed kernel programs at hooks enabling fast packet processing and observability.
6. **How does Cilium replace kube-proxy?** eBPF Service maps at socket/tc level instead of iptables DNAT.
7. **What is Multus?** A meta-CNI enabling multiple interfaces per Pod.
8. **North-south vs east-west?** Edge traffic vs internal service-to-service traffic.
9. **WireGuard vs mTLS?** WireGuard encrypts node-to-node without workload identity; mTLS gives per-workload identity +
   authz.
10. **What is conntrack exhaustion and how do you fix it?** Table full → drops; raise limits, reduce connections, use eBPF.

**Scenario:** Throughput between Pods on different nodes is 40% lower than node-to-node. → Encapsulation overhead and MTU,
offloads disabled for VXLAN, CPU softirq; test with direct routing or native routing mode.

**Follow-ups:** How do route reflectors scale BGP? What is DSR and why does it preserve client IP? How does Istio ambient's
HBONE work?
