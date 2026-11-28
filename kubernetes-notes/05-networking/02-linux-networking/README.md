# 05.02 — Linux Networking Internals

> Everything a CNI plugin does, you can do by hand with `ip`, `bridge`, `iptables`/`nft`.
> In this chapter you will **build a mini Kubernetes Pod network by hand**: namespaces = Pods,
> veth = Pod interfaces, a bridge = `cni0`, NAT = egress masquerade, DNAT = a Service, and VXLAN = the
> overlay between nodes.

All labs need root because they change kernel network state (`CAP_NET_ADMIN`). Run them in a
**throwaway VM** (Multipass) — not on your laptop with Docker if you can avoid it, because Docker installs
iptables rules (FORWARD policy DROP) that interfere. Where that matters, it is called out.

```bash
multipass launch 24.04 --name netlab --cpus 2 --memory 2G
multipass shell netlab
sudo apt update && sudo apt install -y iproute2 bridge-utils iptables nftables tcpdump conntrack curl python3
```

---

## 1. Kernel network stack in 60 seconds

```text
 user space:   app ── socket() / connect() / send()
 ─────────────────────────── syscalls ────────────────────────────────
 kernel:       socket layer (TCP/UDP state, buffers)
                    │
               IP layer: routing table lookup, netfilter hooks, conntrack
                    │
               neighbour (ARP) → qdisc (traffic control) → driver
                    │
               NIC (physical) or virtual device (veth, bridge, vxlan, tun)
 ingress path: NIC → (XDP eBPF) → driver → (tc ingress eBPF) → netfilter PREROUTING → routing → INPUT/FORWARD
```

Each **network namespace** has its own copy of: interfaces, IP addresses, routing tables, ARP table,
netfilter rules, conntrack table (zones), sockets and `/proc/sys/net` settings.

### Sockets basics

A socket is identified by the 5-tuple **(protocol, src IP, src port, dst IP, dst port)**. A listening
socket bound to `0.0.0.0:80` accepts on all addresses *of its namespace*. That is why every Pod can listen on
port 80 without conflict: they're in different namespaces.

```bash
ss -tlnp                      # listening TCP sockets in this namespace
sudo ip netns exec red ss -tlnp   # listening sockets inside netns "red"
```

---

## 2. Lab A — two "Pods" connected by a veth pair

```text
   netns red                       netns blue
  ┌───────────────┐              ┌───────────────┐
  │ veth-red      │◄════════════►│ veth-blue     │
  │ 10.0.0.1/24   │  veth pair   │ 10.0.0.2/24   │
  └───────────────┘              └───────────────┘
```

```bash
sudo ip netns add red                                   # creates /run/netns/red (a bind-mounted ns)
sudo ip netns add blue
ip netns list
sudo ip link add veth-red type veth peer name veth-blue  # create the virtual cable (both ends in host ns)
sudo ip link set veth-red netns red                     # move one end into red
sudo ip link set veth-blue netns blue
sudo ip -n red  addr add 10.0.0.1/24 dev veth-red       # -n red = run in netns red
sudo ip -n blue addr add 10.0.0.2/24 dev veth-blue
sudo ip -n red  link set veth-red up
sudo ip -n blue link set veth-blue up
sudo ip -n red  link set lo up
sudo ip netns exec red ping -c 2 10.0.0.2               # works
sudo ip -n red route                                    # 10.0.0.0/24 dev veth-red proto kernel scope link
sudo ip -n red neigh                                    # blue's MAC learned via ARP
```

**Packet path:** red's kernel sees `10.0.0.2` is on-link via `veth-red` → ARPs → sends frame into
`veth-red` → it pops out of `veth-blue` in blue's namespace → blue's stack replies.

Watch it:

```bash
sudo ip netns exec blue tcpdump -ni veth-blue -e    # -e prints MAC addresses
# in another shell:
sudo ip netns exec red ping -c 1 10.0.0.2
# ARP, Request who-has 10.0.0.2 tell 10.0.0.1 ... ARP, Reply 10.0.0.2 is-at ... ICMP echo request/reply
```

Clean up: `sudo ip netns del red; sudo ip netns del blue` (deleting a namespace destroys its veth end,
which destroys the pair).

---

## 3. Lab B — a bridge, a gateway and internet access (this IS a node's Pod network)

```text
                         host (root namespace) = "the node"
  netns red                ┌──────────────────────────────────────────┐
 ┌──────────────┐          │   br0 10.0.0.1/24  (= cni0 / docker0)     │
 │ eth0         │◄═veth═══►│ vr ──┐                                    │
 │ 10.0.0.2     │          │      ├── bridge ports                     │
 └──────────────┘          │ vb ──┘                                    │        Internet
 netns blue                │                                           │ eth0 ──► (router)
 ┌──────────────┐          │ routing + ip_forward + MASQUERADE         │ (node IP)
 │ eth0 10.0.0.3│◄═veth═══►│                                           │
 └──────────────┘          └──────────────────────────────────────────┘
```

```bash
# Namespaces ("Pods")
sudo ip netns add red; sudo ip netns add blue

# Bridge ("cni0") with the gateway IP
sudo ip link add br0 type bridge
sudo ip addr add 10.0.0.1/24 dev br0
sudo ip link set br0 up

# For each Pod: veth pair, one end in the Pod named eth0, other end attached to the bridge
for ns in red blue; do
  sudo ip link add v-$ns type veth peer name eth0 netns $ns   # create pair with peer directly in the ns
  sudo ip link set v-$ns master br0                           # plug host end into the bridge
  sudo ip link set v-$ns up
  sudo ip -n $ns link set eth0 up
  sudo ip -n $ns link set lo up
done
sudo ip -n red  addr add 10.0.0.2/24 dev eth0
sudo ip -n blue addr add 10.0.0.3/24 dev eth0
sudo ip -n red  route add default via 10.0.0.1            # default gateway = bridge IP (like a Pod)
sudo ip -n blue route add default via 10.0.0.1

bridge link                     # v-red and v-blue are ports of br0
bridge fdb show br br0 | head   # MAC table learned by the bridge

sudo ip netns exec red ping -c 2 10.0.0.3     # Pod→Pod same node: via bridge (L2)
sudo ip netns exec red ping -c 2 10.0.0.1     # Pod→host (gateway)
```

> **Docker-host gotcha:** if Docker is installed, `br_netfilter` is loaded and the iptables `FORWARD` policy
> is `DROP`, so bridged red↔blue traffic is dropped. Fix for the lab:
> `sudo iptables -I FORWARD -i br0 -j ACCEPT; sudo iptables -I FORWARD -o br0 -j ACCEPT`.

### Give the "Pods" internet access (Pod → external)

```bash
sudo sysctl -w net.ipv4.ip_forward=1           # let the host route between interfaces
# SNAT: packets from 10.0.0.0/24 leaving via any interface other than br0 get the host's IP
sudo iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -o br0 -j MASQUERADE
sudo ip netns exec red ping -c 2 1.1.1.1
sudo conntrack -L -p icmp                       # see the NAT translation: src=10.0.0.2 ... reply dst=<host-ip>
```

Packet flow for `red → 1.1.1.1`:

1. red: route default via 10.0.0.1 → ARP for 10.0.0.1 → frame to br0.
2. Host receives on br0 (destination MAC is br0's) → it's an L3 packet for someone else → `FORWARD`.
3. Routing: default route via host `eth0`.
4. `POSTROUTING` MASQUERADE: src 10.0.0.2 → host IP; conntrack records the mapping.
5. Reply arrives to host IP → conntrack reverses: dst host IP → 10.0.0.2 → forwarded to br0 → red.

That's exactly how a Pod reaches the internet on most CNIs (Calico's `natOutgoing`, Flannel's `ipMasq`,
kindnet, AWS VPC CNI's SNAT for non-VPC destinations).

---

## 4. Lab C — port forwarding with DNAT (a hand-made Service / NodePort)

```bash
# Web server in red on port 80
sudo ip netns exec red python3 -m http.server 80 >/dev/null 2>&1 &
# DNAT: anything arriving at 10.0.0.1:8080 (the "virtual IP") → red:80
sudo iptables -t nat -A PREROUTING -d 10.0.0.1 -p tcp --dport 8080 -j DNAT --to-destination 10.0.0.2:80
sudo ip netns exec blue curl -s -o /dev/null -w '%{http_code}\n' http://10.0.0.1:8080    # 200
sudo conntrack -L -p tcp --dport 8080
# tcp ESTABLISHED src=10.0.0.3 dst=10.0.0.1 sport=... dport=8080  src=10.0.0.2 dst=10.0.0.3 sport=80 ...
#     └ original direction                                         └ expected reply (post-DNAT)
```

### Why `br_netfilter` matters (the classic Kubernetes reason)

blue → 10.0.0.1:8080 is DNATed to red. **red replies directly to blue across the bridge** (same L2 segment).
If bridged frames bypass netfilter, conntrack never un-NATs the reply → blue receives a reply from `10.0.0.2:80`
for a connection it opened to `10.0.0.1:8080` → it sends RST → connection fails.

With `net.bridge.bridge-nf-call-iptables=1` (module `br_netfilter`), bridged frames go through netfilter,
conntrack rewrites the reply source back to `10.0.0.1:8080`, and it works. Pods on the same node talking via a
ClusterIP are exactly this case — that's why kubeadm insists on it.

```bash
lsmod | grep br_netfilter; sysctl net.bridge.bridge-nf-call-iptables
```

**Hairpin:** red calling its *own* service VIP gets DNATed back to itself — the packet must leave and re-enter
through the same bridge port. Linux bridges need `hairpin_mode` on that port (`bridge link set dev v-red hairpin on`);
kubelet/CNI configure this ("hairpinMode": true in bridge CNI config).

### The same DNAT with nftables

```bash
sudo nft add table ip lab
sudo nft add chain ip lab prerouting '{ type nat hook prerouting priority dstnat; }'
sudo nft add rule ip lab prerouting ip daddr 10.0.0.1 tcp dport 9090 dnat to 10.0.0.2:80
sudo nft list table ip lab
sudo ip netns exec blue curl -s -o /dev/null -w '%{http_code}\n' http://10.0.0.1:9090
sudo nft delete table ip lab
```

| | iptables | nftables |
|--|----------|----------|
| Status | legacy userspace (on Ubuntu `iptables` is `iptables-nft` backend) | modern replacement |
| Structure | fixed tables/chains | user-defined tables, chains, **sets and maps** |
| Scale | linear rule lists | maps give O(1)-ish lookups (why kube-proxy nftables mode scales better) |
| Atomic updates | `iptables-restore` | whole-ruleset transactions |
| Inspect | `iptables-save`, `iptables -t nat -L -n -v` | `nft list ruleset` |

```bash
iptables --version     # "iptables v1.8.x (nf_tables)" = nft backend; "(legacy)" = old x_tables
```

> ⚠️ Mixing `iptables-legacy` and `iptables-nft` on one node creates two invisible rule sets. Kubernetes
> components detect which mode the host uses; don't switch by hand.

---

## 5. Netfilter, iptables and conntrack in depth

### 5.1 Tables and chains

| Table | Purpose | Chains |
|-------|---------|--------|
| `raw` | skip conntrack (`NOTRACK`) | PREROUTING, OUTPUT |
| `mangle` | modify headers, set marks | all five |
| `nat` | DNAT/SNAT (only the **first packet** of a connection is evaluated; conntrack handles the rest) | PREROUTING, INPUT, OUTPUT, POSTROUTING |
| `filter` | accept/drop | INPUT, FORWARD, OUTPUT |

```bash
sudo iptables -t nat -L -n -v --line-numbers    # -L list, -n numeric, -v counters (pkts/bytes!)
sudo iptables -t filter -S FORWARD              # -S print as commands
sudo iptables -Z                                # zero counters, then reproduce traffic and re-check -v
sudo iptables -t raw -I PREROUTING -p icmp -j TRACE   # packet tracing; view with: sudo xtables-monitor --trace
```

Counters (`-v`) are the best tool to answer "is this rule being hit?".

### 5.2 conntrack

The connection tracker remembers each flow and its NAT mapping; states: `NEW`, `ESTABLISHED`, `RELATED`,
`INVALID`.

```bash
sudo conntrack -L | head
sudo conntrack -C                                # current entry count
sysctl net.netfilter.nf_conntrack_max            # table size limit
sudo conntrack -S                                # per-CPU stats: insert_failed, drop → trouble
sudo dmesg | grep -i conntrack                   # "nf_conntrack: table full, dropping packet"
sudo conntrack -D -d 10.96.0.10                  # delete entries (e.g. stale UDP DNS flows)
```

Kubernetes problems caused by conntrack:

- **Table full** on busy nodes → random drops. Raise `nf_conntrack_max` (kube-proxy sets it from `conntrack.maxPerCore`).
- **DNS 5-second delays**: parallel A/AAAA UDP queries from the same socket race on conntrack insert
  (`insert_failed`). Fixes: NodeLocal DNSCache, `single-request-reopen`, newer kernels.
- **Stale UDP entries** after a backend Pod changes → kube-proxy flushes conntrack for UDP Services.

---

## 6. MTU and encapsulation

**MTU** = largest IP packet an interface sends without fragmentation (Ethernet 1500, AWS VPC jumbo 9001).

Encapsulation adds headers, so the inner packet must be smaller:

| Encapsulation | Overhead (IPv4) | Pod MTU on a 1500 network |
|---------------|-----------------|--------------------------|
| none (direct routing) | 0 | 1500 |
| IP-in-IP | 20 | 1480 |
| VXLAN | 50 | 1450 |
| Geneve | 50+ (options) | ≤1450 |
| WireGuard | 60 (v4) / 80 (v6) | 1420 (Calico/Cilium default) |

Symptom of wrong MTU: **small requests work, large ones hang** (TLS handshakes with big certs, `kubectl exec` OK
but file downloads stall). Because PMTU discovery depends on ICMP "fragmentation needed", which firewalls often drop.

```bash
ip link show eth0 | grep -o 'mtu [0-9]*'
ping -M do -s 1472 10.0.0.12     # -M do: don't fragment; 1472 + 28 (IP+ICMP headers) = 1500
ping -M do -s 1423 10.244.1.5    # find the largest size that passes through the overlay
tracepath -n 10.244.1.5          # shows pmtu
```

---

## 7. Overlay vs underlay, VXLAN

- **Underlay** = the real network between nodes (VPC, datacenter switches). It routes **node IPs** only.
- **Overlay** = a virtual network on top. Pod packets are **encapsulated** in node-to-node packets so the
  underlay never needs to know Pod IPs.

```text
 Pod A 10.244.0.5 on node1 (192.168.100.1)  ──►  Pod B 10.244.1.7 on node2 (192.168.100.2)

 inner:  [ Eth | IP 10.244.0.5 → 10.244.1.7 | TCP | data ]
 VXLAN:  [ Eth node1→node2 | IP 192.168.100.1 → 192.168.100.2 | UDP dst 4789/8472 | VXLAN VNI | inner frame ]
```

- **VTEP** (VXLAN Tunnel Endpoint) = the vxlan interface on each node (`flannel.1`, `vxlan.calico`, `cilium_vxlan`).
- **VNI** = 24-bit network ID (like a VLAN number, 16 M of them).
- The VTEP needs to know "MAC of remote VTEP → which node IP" — the CNI programs that in the FDB/ARP tables
  (Flannel does it from node annotations; no multicast needed).
- Port: IANA **4789**; Linux kernel default and Flannel/Cilium use **8472**.

### Lab D — build a VXLAN overlay between two "nodes"

We simulate two nodes as namespaces `node1` and `node2` joined by an underlay veth.

```bash
sudo ip netns add node1; sudo ip netns add node2
sudo ip link add u1 type veth peer name u2
sudo ip link set u1 netns node1; sudo ip link set u2 netns node2
sudo ip -n node1 addr add 192.168.100.1/24 dev u1; sudo ip -n node1 link set u1 up
sudo ip -n node2 addr add 192.168.100.2/24 dev u2; sudo ip -n node2 link set u2 up

# VXLAN interface on each "node": VNI 42, UDP 4789, explicit remote (unicast, no multicast)
sudo ip -n node1 link add vxlan42 type vxlan id 42 local 192.168.100.1 remote 192.168.100.2 dstport 4789 dev u1
sudo ip -n node2 link add vxlan42 type vxlan id 42 local 192.168.100.2 remote 192.168.100.1 dstport 4789 dev u2
sudo ip -n node1 addr add 10.244.0.1/16 dev vxlan42; sudo ip -n node1 link set vxlan42 up
sudo ip -n node2 addr add 10.244.1.1/16 dev vxlan42; sudo ip -n node2 link set vxlan42 up

ip -n node1 -d link show vxlan42        # -d details: vxlan id 42 remote ... dstport 4789, mtu 1450 (auto)

# Capture on the UNDERLAY while pinging an OVERLAY address
sudo ip netns exec node1 tcpdump -ni u1 -c 4 udp port 4789 &
sudo ip netns exec node1 ping -c 2 10.244.1.1
# IP 192.168.100.1.xxxxx > 192.168.100.2.4789: VXLAN, flags [I] (0x08), vni 42
# IP 10.244.0.1 > 10.244.1.1: ICMP echo request          ← the inner packet, decoded by tcpdump
```

You just saw **encapsulation** (outer UDP 4789 between node IPs) and the **inner Pod-to-Pod packet**.
Flannel's VXLAN backend is this plus automation: it creates `flannel.1`, a route
`10.244.1.0/24 via 10.244.1.0 dev flannel.1 onlink`, and static ARP/FDB entries per remote node.

Clean up: `sudo ip netns del node1; sudo ip netns del node2`.

---

## 8. Host networking

A Pod with `hostNetwork: true` uses the **node's network namespace**: no veth, the node's IP, binds node ports
directly. Used by: kube-proxy, CNI agents, some ingress controllers, node-exporter. Downsides: port conflicts,
bypasses NetworkPolicy in most CNIs, larger attack surface.

```bash
kubectl run hn --image=nicolaka/netshoot --overrides='{"spec":{"hostNetwork":true}}' --restart=Never -- sleep 3600
kubectl exec hn -- ip -br addr     # you see the node's eth0, cni0, veths...
kubectl delete pod hn
```

---

## 9. DNS resolution process on Linux (inside a Pod too)

1. App calls `getaddrinfo("web")`.
2. glibc reads `/etc/nsswitch.conf` → `hosts: files dns`.
3. `/etc/hosts` checked (kubelet manages it in Pods).
4. `/etc/resolv.conf`: `nameserver`, `search` list, `options ndots:N`.
5. If the name has fewer dots than `ndots`, search domains are appended first.
6. UDP query (TCP on truncation) to the nameserver; A and AAAA usually in parallel.

musl (Alpine) differs: queries search domains in parallel and historically lacked TCP fallback — a common source of
"works on Debian image, fails on Alpine". Details in [05.07](../07-dns-coredns/README.md).

---

## 10. Inspection cheat sheet

| Question | Command |
|----------|---------|
| Which namespaces exist? | `ip netns list` (only named ones), `lsns -t net` (all, incl. containers) |
| Run in a container's netns | `sudo nsenter -t <pid> -n <cmd>` |
| Which bridge is a veth on? | `bridge link`, `ip link show master cni0` |
| Find a Pod's host-side veth | in Pod: `cat /sys/class/net/eth0/iflink` → on host: `ip -o link \| grep "^<N>:"` |
| Interfaces with details | `ip -d link show <if>` |
| Route decision | `ip route get <dst> [from <src> iif <if>]` |
| Policy routing | `ip rule`, `ip route show table all` (AWS VPC CNI and Cilium use extra tables) |
| NAT rules | `iptables -t nat -S`, `nft list ruleset` |
| Tracked flows | `conntrack -L` |
| Packets | `tcpdump -ni <if> -e host <ip>` |
| Drops | `ip -s link show <if>` (RX/TX dropped), `nstat -az \| grep -i drop`, `dropwatch`, `pwru` (eBPF) |

---

## Interview questions

1. **What is a network namespace?** An isolated copy of the network stack: interfaces, routes, firewall, sockets.
2. **What is a veth pair and how does a Pod use it?** Two connected virtual NICs; one end is the Pod's `eth0`, the other
   is on the host attached to a bridge or routed.
3. **Bridge vs router?** Bridge forwards L2 frames by MAC within a segment; a router forwards L3 packets between subnets.
4. **Why does Kubernetes need `br_netfilter`?** So bridged Pod-to-Pod traffic passes through netfilter for Service
   DNAT/reverse-NAT and policies.
5. **DNAT vs SNAT?** DNAT changes destination (Service VIP → Pod). SNAT/MASQUERADE changes source (Pod → node IP for egress).
6. **What is conntrack and why does it matter?** Kernel flow table storing NAT state; table exhaustion and races cause drops
   and DNS delays.
7. **What is VXLAN?** L2-over-UDP encapsulation with a 24-bit VNI, used for overlay Pod networks.
8. **Overlay vs underlay?** Underlay is the physical/VPC network; overlay is a virtual network tunneled over it.
9. **Why do MTU issues show as "large requests hang"?** Encapsulated packets exceed the path MTU and get dropped when
   ICMP fragmentation-needed is blocked.
10. **iptables vs nftables?** nftables is the modern framework with sets/maps and atomic updates; iptables-nft is a
    compatibility layer on top of it.

**Scenario:** A new node joins; Pods on it can reach other Pods by IP but not via ClusterIP when the backend is on the same
node. → `br_netfilter` not loaded / `bridge-nf-call-iptables=0`.

**Follow-ups:** Walk through the netfilter hooks a Pod-to-Service packet traverses. How would you trace a packet through
iptables (`TRACE`, `xtables-monitor`, `pwru`)? What does `ip rule` policy routing do in the AWS VPC CNI?
