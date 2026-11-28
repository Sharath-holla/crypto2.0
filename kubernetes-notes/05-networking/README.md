# 05 — Kubernetes Networking (Roadmap)

Networking is where most real Kubernetes incidents happen and where interviews go deepest. This
chapter builds understanding **bottom-up**: you first learn how packets move in Linux, then how
Kubernetes uses exactly those primitives.

```text
 Layer of understanding                          Sub-chapter
 ───────────────────────────────────────────────────────────────────────
 IP, CIDR, ARP, routing, DNS, TCP/UDP             01-networking-basics
 netns, veth, bridge, netfilter, conntrack, VXLAN 02-linux-networking
 Pod network model, Pod IP assignment, flows      03-pod-networking
 CNI spec, IPAM, Flannel/Calico/Cilium            04-cni
 Services, EndpointSlices, Service types          05-services
 kube-proxy: iptables / IPVS / nftables / eBPF    06-kube-proxy
 CoreDNS, ndots, search domains                   07-dns-coredns
 Ingress, Gateway API, TLS                        08-ingress-gateway
 NetworkPolicy                                    09-network-policies
 BGP, MTU, Multus, eBPF, mTLS, mesh networking    10-advanced-networking
 Istio                                            11-istio-service-mesh
 Systematic troubleshooting                       12-troubleshooting
```

## The four Kubernetes networking problems

| # | Problem | Solved by |
|---|---------|-----------|
| 1 | Container ↔ container in the same Pod | shared network namespace → `localhost` |
| 2 | Pod ↔ Pod (same or different node) | **CNI plugin** (flat Pod network) |
| 3 | Pod ↔ Service (stable virtual IP, load balancing) | **Services + kube-proxy/eBPF + CoreDNS** |
| 4 | External ↔ Service | **NodePort / LoadBalancer / Ingress / Gateway** |

## The whole picture on one page

```text
 Internet
    │
    ▼
 Cloud/External Load Balancer (L4)  ──or──  NodePort on every node
    │
    ▼
 Ingress / Gateway controller Pod (L7: host, path, TLS termination)
    │   resolves backend Service → EndpointSlice → Pod IPs
    ▼
 Service ClusterIP 10.96.x.x  (virtual IP; DNAT by iptables/nftables/IPVS/eBPF on the node)
    │
    ▼
 Pod IP 10.244.y.z  (routed by CNI: veth → bridge/route → overlay or direct route → node → veth)
    │
    ▼
 Container process listening on containerPort
```

Keep this diagram in mind while reading every sub-chapter.

## Lab cluster for this whole chapter

Most labs use a 3-node **kind** cluster. Some labs (Calico/Cilium, NetworkPolicy) recreate it without
the default CNI. Install the toolbox image once you have a cluster:

```bash
kind create cluster --config ../03-cluster-setup/kind-multinode.yaml   # see chapter 03 §4.3 (save the YAML there)
kubectl run netshoot --image=nicolaka/netshoot --restart=Never -- sleep infinity
kubectl exec -it netshoot -- bash     # has ip, ss, tcpdump, dig, curl, iperf3, nft, iptables…
```
