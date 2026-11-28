# 05.06 — kube-proxy Internals

## 1. Why kube-proxy exists

A Service ClusterIP is just an idea in the API. *Something* on every node must turn
"connect to 10.96.45.10:80" into "connect to 10.244.2.9:8080". That's kube-proxy's job.

- Runs on **every node** (DaemonSet, `hostNetwork: true`, privileged for `NET_ADMIN`).
- **Watches** the API for `Service` and `EndpointSlice` changes (informers).
- **Programs the kernel** (iptables, nftables or IPVS). It is **not in the packet path** in these modes — the kernel does
  the forwarding; kube-proxy only writes rules.
- Exposes health on `:10256/healthz` and metrics on `:10249/metrics` (`/proxyMode` tells you the mode).

```text
 API server ──watch Services/EndpointSlices──► kube-proxy (each node)
                                                   │ computes desired rules
                                                   ▼
                              iptables-restore / nft -f / ipvs netlink   (sync loop, rate-limited)
                                                   │
                         kernel netfilter / IPVS: DNAT, SNAT, load-balancing for every packet
```

## 2. Modes

| Mode | Status | Data structure | Scale behaviour |
|------|--------|----------------|-----------------|
| `iptables` | ✅ default on Linux | linear chains per Service/endpoint | rule count O(services × endpoints); resync of large tables is slow |
| `nftables` | ✅ GA v1.33 | verdict **maps** (hash lookups) | much faster updates and lookups; requires kernel ≥ 5.13 |
| `ipvs` | ⚠️ deprecated v1.35 | kernel L4 load balancer + ipset | good scale, but feature gaps and divergent behaviour |
| `kernelspace` | Windows | HNS | — |
| (none) — eBPF replacement | Cilium, Calico eBPF | eBPF maps at tc/socket hooks | best scale, no conntrack dependence for LB |

```bash
kubectl -n kube-system get cm kube-proxy -o yaml | grep -E 'mode:|clusterCIDR'
# On a node:
curl -s localhost:10249/proxyMode; echo            # iptables | nftables | ipvs
kubectl -n kube-system logs ds/kube-proxy | grep -i 'Using .* Proxier'
```

---

## 3. iptables mode in detail

### 3.1 Chain structure

```text
 PREROUTING (nat)  ─┐                  OUTPUT (nat) ─┐   (locally generated, e.g. hostNetwork Pods)
                    └──► KUBE-SERVICES ◄─────────────┘
                             │ match dst 10.96.45.10/32 tcp dpt:80
                             ▼
                        KUBE-SVC-ABCDEF  (one per Service port)
                             │ -m statistic --mode random --probability 0.333 → KUBE-SEP-1
                             │ -m statistic --mode random --probability 0.5   → KUBE-SEP-2
                             │                                                → KUBE-SEP-3
                             ▼
                        KUBE-SEP-1  (one per endpoint)
                             │ if src is the endpoint itself (hairpin) → KUBE-MARK-MASQ
                             │ DNAT --to-destination 10.244.1.5:8080
                             ▼
                        routing → CNI → Pod
 POSTROUTING ──► KUBE-POSTROUTING: if packet has mark 0x4000 → MASQUERADE (SNAT to node IP)
 Node ports: KUBE-SERVICES last rule → KUBE-NODEPORTS → KUBE-EXT-ABCDEF → (mark masq unless Local) → KUBE-SVC-…
```

Why probabilities 1/3, 1/2, 1? Rules are tried in order: first endpoint chosen with p=1/3; if not, second with p=1/2 of
the remaining 2/3 = 1/3; else third = 1/3. Uniform random.

### 3.2 Read real rules

```bash
docker exec -it lab-worker bash          # or SSH to a kubeadm node
iptables-save -t nat | grep -c KUBE      # how many rules
iptables -t nat -L KUBE-SERVICES -n | head
SVC_IP=10.96.45.10                       # replace with: kubectl get svc web -o jsonpath='{.spec.clusterIP}'
iptables-save -t nat | grep "$SVC_IP"
# -A KUBE-SERVICES -d 10.96.45.10/32 -p tcp -m comment --comment "svc-lab/web cluster IP" -m tcp --dport 80 -j KUBE-SVC-XXXX
iptables-save -t nat | grep -A4 '^-A KUBE-SVC-XXXX'
# -A KUBE-SVC-XXXX ! -s 10.244.0.0/16 -d 10.96.45.10/32 ... -j KUBE-MARK-MASQ   ← traffic from outside Pod CIDR gets SNAT
# -A KUBE-SVC-XXXX ... -m statistic --mode random --probability 0.33333333349 -j KUBE-SEP-AAAA
iptables-save -t nat | grep -A3 '^-A KUBE-SEP-AAAA'
# -A KUBE-SEP-AAAA -s 10.244.1.5/32 ... -j KUBE-MARK-MASQ
# -A KUBE-SEP-AAAA -p tcp ... -m tcp -j DNAT --to-destination 10.244.1.5:8080
iptables -t nat -L KUBE-POSTROUTING -n -v
iptables -t filter -L KUBE-FORWARD -n      # allows conntrack ESTABLISHED, drops INVALID
iptables-save -t filter | grep 'has no endpoints'   # Services with zero endpoints get REJECT rules
```

> A Service with **no endpoints** gets an explicit **REJECT** rule → clients see **connection refused** immediately
> (not a timeout). Great diagnostic hint.

### 3.3 DNAT, SNAT and conntrack in this flow

| Step | What | Where |
|------|------|-------|
| DNAT | dst VIP:port → PodIP:targetPort | first packet in PREROUTING/OUTPUT; conntrack remembers |
| SNAT (MASQUERADE) | src → node IP | only for marked packets: external NodePort traffic (Cluster policy), hairpin, traffic from outside clusterCIDR |
| Reverse NAT | reply src PodIP → VIP | conntrack, automatically |

```bash
conntrack -L -d 10.96.45.10
# tcp 6 86397 ESTABLISHED src=10.244.2.3 dst=10.96.45.10 sport=40112 dport=80 src=10.244.1.5 dst=10.244.2.3 sport=8080 dport=40112 [ASSURED]
```

---

## 4. nftables mode

Structure (table `ip kube-proxy` and `ip6 kube-proxy`):

```text
 chain nat-prerouting / nat-output → jump services
 chain services:
     ip daddr . meta l4proto . th dport vmap @service-ips        ← ONE hash lookup for all ClusterIPs
     fib daddr type local ip daddr . ... vmap @service-nodeports
 map service-ips { 10.96.45.10 . tcp . 80 : goto service-XXXX-svc-lab/web/tcp/http, ... }
 chain service-XXXX-svc-lab/web/tcp/http:
     ip saddr != 10.244.0.0/16 jump mark-for-masquerade
     numgen random mod 3 vmap { 0 : goto endpoint-AAA, 1 : goto endpoint-BBB, 2 : goto endpoint-CCC }
 chain endpoint-AAA: ip saddr 10.244.1.5 jump mark-for-masquerade ; meta l4proto tcp dnat to 10.244.1.5:8080
```

```bash
# kind cluster in nftables mode: add to the kind config →  networking: { kubeProxyMode: "nftables" }
docker exec lab-worker nft list tables              # table ip kube-proxy, table ip6 kube-proxy
docker exec lab-worker nft list map ip kube-proxy service-ips
docker exec lab-worker nft list chain ip kube-proxy services
docker exec lab-worker nft list table ip kube-proxy | grep -A6 'chain service-.*web'
```

Why it scales: lookups use maps instead of walking thousands of rules, and updates are incremental transactions.

Differences to know: NodePorts are only accepted on the node's **primary** IPs by default
(`--nodeport-addresses primary`); localhost NodePorts (`127.0.0.1:NodePort`) are not supported.

---

## 5. IPVS mode (⚠️ deprecated) — for existing clusters

```text
 kube-ipvs0 (dummy interface) holds ALL ClusterIPs as local addresses → packets are "for this host" → IPVS hooks INPUT
 IPVS virtual server 10.96.45.10:80 rr → real servers 10.244.1.5:8080, 10.244.2.9:8080 (masq/NAT forwarding)
 iptables + ipset still used for masquerade and filtering
```

```bash
ip addr show kube-ipvs0
sudo ipvsadm -Ln                 # -L list, -n numeric: virtual servers and real servers with weights/conns
sudo ipvsadm -Ln --stats
sudo ipset list | head
```

Schedulers: `rr`, `lc`, `dh`, `sh`, `sed`, `nq`. Because ClusterIPs are real local addresses, you **can ping** a ClusterIP in
IPVS mode (a common interview gotcha). Migration path: move to `nftables` (or eBPF).

---

## 6. Which inspection command for which dataplane

| Dataplane | Find Service rules | Endpoints/backends | Counters / live |
|-----------|-------------------|--------------------|-----------------|
| iptables | `iptables-save -t nat \| grep <svc-ip>` | `KUBE-SEP-*` chains | `iptables -t nat -L <chain> -n -v` |
| nftables | `nft list map ip kube-proxy service-ips` | `nft list chain ip kube-proxy endpoint-*` | add `counter` / `nft monitor trace` |
| IPVS | `ipvsadm -Ln -t <vip>:<port>` | real servers in same output | `ipvsadm -Ln --stats/--rate` |
| Cilium eBPF | `cilium-dbg service list` | `cilium-dbg bpf lb list` | `hubble observe`, `cilium-dbg monitor` |
| Calico eBPF | `calico-node -bpf nat dump` | same | `calico-node -bpf conntrack dump` |
| All | `conntrack -L -d <vip>` (not for Cilium-LB'd flows w/ socket LB) | | |

> **Don't run `iptables` commands to debug a Cilium kube-proxy-free cluster** — Services aren't there. And on nftables-mode
> nodes, `iptables-save` shows only legacy/other rules, not kube-proxy's.

---

## 7. kube-proxy alternatives and eBPF dataplanes

| | kube-proxy iptables/nftables | Cilium kube-proxy replacement | Calico eBPF |
|--|-----------------------------|-------------------------------|-------------|
| LB location | netfilter per packet (first packet + conntrack) | eBPF at socket `connect()` (socket LB) and tc | eBPF at tc |
| Source IP preservation for NodePort | needs `Local` | DSR mode preserves it with even spread | DSR supported |
| Consistent hashing | no | Maglev | — |
| Observability | counters | Hubble | flow logs |

**Socket-level LB:** for Pod→Service traffic, Cilium rewrites the destination at `connect()` time, so packets on the wire
already go to the Pod IP — no per-packet NAT at all.

---

## 8. Lab — follow a Service through the kernel

```bash
kubectl create deployment echo --image=registry.k8s.io/e2e-test-images/agnhost:2.53 --replicas=2 -- /agnhost netexec --http-port=8080
kubectl expose deployment echo --port=80 --target-port=8080
kubectl run c --image=nicolaka/netshoot --restart=Never -- sleep infinity
VIP=$(kubectl get svc echo -o jsonpath='{.spec.clusterIP}')
C_NODE=$(kubectl get pod c -o jsonpath='{.spec.nodeName}')

# 1) Rules on the CLIENT's node (DNAT happens there)
docker exec $C_NODE iptables-save -t nat | grep -E "$VIP|KUBE-SVC" | head

# 2) Counters before/after a request
CHAIN=$(docker exec $C_NODE iptables-save -t nat | grep "$VIP" | grep -o 'KUBE-SVC-[A-Z0-9]*' | head -1)
docker exec $C_NODE iptables -t nat -L $CHAIN -n -v
kubectl exec c -- curl -s $VIP/hostname; echo
docker exec $C_NODE iptables -t nat -L $CHAIN -n -v      # one KUBE-SEP counter incremented

# 3) conntrack entry showing the translation
docker exec $C_NODE conntrack -L -d $VIP 2>/dev/null

# 4) tcpdump inside the client Pod: you see the VIP...
kubectl exec c -- timeout 5 tcpdump -ni eth0 -c 4 tcp port 80 or tcp port 8080 &
kubectl exec c -- curl -s $VIP/hostname >/dev/null
# ...on the node's veth/eth0 after DNAT you'd see the Pod IP:8080

# 5) Delete all endpoints → REJECT rule
kubectl scale deploy echo --replicas=0
kubectl exec c -- curl -sv --max-time 3 $VIP 2>&1 | grep -iE 'refused|timed'
docker exec $C_NODE iptables-save -t filter | grep "has no endpoints"
kubectl scale deploy echo --replicas=2
```

---

## 9. Troubleshooting kube-proxy

```bash
kubectl -n kube-system get pods -l k8s-app=kube-proxy -o wide
kubectl -n kube-system logs <kube-proxy-pod> | tail -50       # sync errors, "Failed to execute iptables-restore"
curl -s <node-ip>:10256/healthz                                # on node; lastUpdated timestamp
curl -s localhost:10249/metrics | grep -E 'sync_proxy_rules_(duration|last_timestamp)'
```

| Problem | Cause |
|---------|-------|
| New Services don't work on one node | kube-proxy crashed / can't reach API server on that node |
| Rules sync takes many seconds | huge iptables tables → move to nftables or eBPF |
| Intermittent drops under load | conntrack table full (`nf_conntrack: table full`) |
| NodePort fails on nftables nodes via 127.0.0.1 | unsupported by design |
| Service works only from some Pods | stale rules; mixed iptables-legacy/nft backends |

---

## Interview questions

1. **What does kube-proxy do?** Watches Services/EndpointSlices and programs kernel rules for VIP → Pod load balancing.
2. **Is kube-proxy in the data path?** Not in iptables/nftables/IPVS modes — the kernel forwards packets.
3. **Explain iptables chains for a Service.** KUBE-SERVICES → KUBE-SVC (random probability per endpoint) → KUBE-SEP (DNAT);
   KUBE-POSTROUTING masquerades marked packets.
4. **Why nftables over iptables?** Map-based lookups and incremental atomic updates scale far better.
5. **Status of IPVS mode?** Deprecated in v1.35; migrate to nftables or eBPF.
6. **When is traffic SNATed?** NodePort/LB traffic with `externalTrafficPolicy: Cluster`, hairpin traffic, sources outside the
   cluster CIDR.
7. **Why does a Service with no endpoints return "connection refused"?** kube-proxy installs a REJECT rule.
8. **How can a cluster run without kube-proxy?** An eBPF dataplane (Cilium/Calico eBPF) implements Services instead.
9. **Can you ping a ClusterIP?** No in iptables/nftables mode; yes in IPVS mode (VIPs on kube-ipvs0).
10. **What is conntrack's role?** Stores the NAT decision so subsequent packets and replies are translated consistently.

**Scenario:** Service intermittently times out on one node only. → Check that node's kube-proxy logs/sync timestamps, conntrack
stats (`insert_failed`, `drop`), and whether rules match other nodes.

**Follow-ups:** How does kube-proxy handle UDP conntrack after endpoint changes? What is Maglev hashing and DSR? How do
`terminating`/`serving` endpoint conditions affect kube-proxy?
