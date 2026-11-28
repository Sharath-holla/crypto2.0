# 05.01 — Networking Basics

## 1. The layered model (what you actually need)

| Layer (TCP/IP) | OSI # | Unit | Address | Linux/K8s examples |
|----------------|-------|------|---------|--------------------|
| Application | 7 | message | URL, hostname | HTTP, gRPC, DNS; Ingress/Gateway, Istio |
| Transport | 4 | segment / datagram | port | TCP, UDP; Services, NodePort, kube-proxy |
| Internet | 3 | packet | IP address | routing, Pod IPs, NetworkPolicy, Calico BGP |
| Link | 2 | frame | MAC address | Ethernet, ARP, bridges, VXLAN inner frame |
| Physical | 1 | bits | — | NIC, cable, virtual NIC |

Each layer **encapsulates** the one above:

```text
[ Ethernet hdr (MACs) | IP hdr (src/dst IP) | TCP hdr (src/dst port) | HTTP data ] FCS
```

"L4 load balancer" = looks at IP+port only. "L7 load balancer" = understands HTTP (host, path, headers).

---

## 2. IP addresses and IPv4

An IPv4 address is **32 bits**, written as 4 octets: `192.168.1.10` = `11000000.10101000.00000001.00001010`.

An address has a **network part** and a **host part**; the **subnet mask / prefix length** says where the
split is.

### 2.1 Public vs private

| Range (RFC 1918) | CIDR | Size |
|------------------|------|------|
| 10.0.0.0 – 10.255.255.255 | 10.0.0.0/8 | 16.7 M |
| 172.16.0.0 – 172.31.255.255 | 172.16.0.0/12 | 1 M |
| 192.168.0.0 – 192.168.255.255 | 192.168.0.0/16 | 65 k |

Other special ranges: `127.0.0.0/8` loopback, `169.254.0.0/16` link-local (cloud metadata
`169.254.169.254`), `100.64.0.0/10` carrier-grade NAT (used by some CNIs / EKS custom networking),
`0.0.0.0/0` "everything" (default route).

Private IPs are not routable on the internet → reaching the internet requires **NAT**.
Pod IPs and Service IPs in Kubernetes are almost always private.

### 2.2 IPv6 in one paragraph

128-bit addresses (`fd00:10:244::5`), no broadcast, uses NDP instead of ARP. Kubernetes supports
**dual-stack** (Pods and Services get IPv4 + IPv6). Same concepts, bigger numbers.

---

## 3. CIDR notation and subnetting

**CIDR** `a.b.c.d/n` = the first `n` bits are the network.

| Prefix | Mask | Addresses | Usable hosts* | Typical use |
|--------|------|-----------|---------------|-------------|
| /8 | 255.0.0.0 | 16,777,216 | — | huge private space |
| /12 | 255.240.0.0 | 1,048,576 | — | default K8s Service CIDR `10.96.0.0/12` |
| /16 | 255.255.0.0 | 65,536 | 65,534 | cluster Pod CIDR `10.244.0.0/16`, AWS VPC |
| /20 | 255.255.240.0 | 4,096 | 4,094 | AWS subnet |
| /24 | 255.255.255.0 | 256 | 254 | per-node Pod CIDR (Flannel/kubeadm default) |
| /26 | 255.255.255.192 | 64 | 62 | Calico IPAM block default |
| /28 | 255.255.255.240 | 16 | 14 | small subnet / EKS prefix delegation (/28 per ENI slot) |
| /30 | 255.255.255.252 | 4 | 2 | point-to-point link |
| /32 | 255.255.255.255 | 1 | 1 | a single host route (Calico routes each Pod as /32) |

\*Usable = total − network address − broadcast address (on traditional subnets). Clouds often reserve more
(AWS reserves 5 per subnet).

**Formula:** addresses = 2^(32 − prefix).

### 3.1 Worked example: `192.168.10.77/26`

1. /26 → block size = 2^(32−26) = 64. Mask = 255.255.255.192.
2. Blocks in the last octet: 0, 64, 128, 192. 77 falls in **64–127**.
3. Network = `192.168.10.64`, Broadcast = `192.168.10.127`.
4. Usable hosts = `.65` to `.126` (62 hosts).

### 3.2 Worked example: Kubernetes Pod CIDR split

Cluster Pod CIDR `10.244.0.0/16`, per-node `/24` (`--node-cidr-mask-size=24`):

- Number of node subnets = 2^(24−16) = **256 nodes max**.
- Each node: 256 addresses → ~254 Pods (kubelet default max is 110 Pods/node anyway).
- node1 `10.244.0.0/24`, node2 `10.244.1.0/24`, node3 `10.244.2.0/24` …

If you need 1000 nodes, use `/14` Pod CIDR or a `/25` per-node mask (128 IPs, still > 110 Pods).

### 3.3 Overlaps — the #1 design mistake

Pod CIDR, Service CIDR, node/VPC CIDR, VPN/office ranges and peered VPCs **must not overlap**.
Overlap = packets go to the wrong place, silently.

```bash
sudo apt install -y ipcalc
ipcalc 192.168.10.77/26
python3 -c "import ipaddress as i; print(i.ip_network('10.244.0.0/16').overlaps(i.ip_network('10.96.0.0/12')))"
# False → good (10.96.0.0/12 covers 10.96.0.0–10.111.255.255)
```

### 3.4 Practice problems (answers below)

1. How many addresses in `/22`?
2. Network and broadcast of `10.0.13.200/21`?
3. Split `10.10.0.0/16` into four equal subnets.
4. Does `172.20.0.0/16` overlap `172.16.0.0/12`?
5. Smallest prefix holding 500 hosts?
6. Service CIDR `10.96.0.0/12`. Is `10.100.5.5` inside?
7. Pod CIDR `/16`, node mask `/25`. Max nodes and IPs per node?

<details><summary>Answers</summary>

1. 2^10 = 1024.
2. /21 → block size 8 in the 3rd octet: 0,8,16 → 13 in 8–15 → network `10.0.8.0`, broadcast `10.0.15.255`.
3. `/18` each: `10.10.0.0/18`, `10.10.64.0/18`, `10.10.128.0/18`, `10.10.192.0/18`.
4. Yes — 172.16.0.0/12 covers 172.16.0.0–172.31.255.255.
5. /23 (512 addresses, 510 usable).
6. Yes — the /12 range is 10.96.0.0–10.111.255.255.
7. 2^(25−16) = 512 nodes, 128 IPs per node.
</details>

---

## 4. MAC addresses and ARP

- **MAC address**: 48-bit L2 address (`02:42:ac:11:00:02`). Only meaningful on the **local link**.
- **ARP** answers "who has IP 10.244.1.5? tell 10.244.1.1" → maps IP → MAC on the same L2 segment.

```text
 Pod A wants 10.244.1.6 (same subnet)
  1. Check ARP cache (ip neigh) → miss
  2. Broadcast: ARP who-has 10.244.1.6
  3. Pod B replies: 10.244.1.6 is-at 0a:58:0a:f4:01:06
  4. Send frame to that MAC
 Different subnet? → ARP for the GATEWAY's MAC instead, send frame to the gateway.
```

```bash
ip neigh                     # ARP/neighbour cache: IP, interface, MAC, state (REACHABLE, STALE, FAILED)
sudo ip neigh flush dev eth0 # clear (sudo: modifies kernel tables)
sudo tcpdump -ni eth0 arp    # watch ARP requests/replies
```

Calico uses a trick: every Pod's default gateway is `169.254.1.1`, and the host veth answers ARP for it
with **proxy ARP** — so all Pod traffic goes to the host to be routed.

---

## 5. Routing and the default gateway

The **routing table** tells the kernel where to send a packet based on the **longest prefix match**.

```bash
ip route
# default via 192.168.1.1 dev eth0 proto dhcp metric 100      ← default gateway: anything not matched below
# 10.244.1.0/24 via 192.168.1.12 dev eth0                      ← Pods on node2 reachable via node2 (direct routing)
# 10.244.0.0/24 dev cni0 proto kernel scope link src 10.244.0.1 ← local Pods on the bridge
# 192.168.1.0/24 dev eth0 proto kernel scope link src 192.168.1.11

ip route get 10.244.1.7       # ask the kernel: which route/interface/source would be used?
ip route get 8.8.8.8
```

Longest prefix match example: destination `10.244.1.7` matches both `default (0.0.0.0/0)` and
`10.244.1.0/24` → `/24` is longer → wins.

`traceroute`/`tracepath` show each router hop:

```bash
traceroute -n 8.8.8.8         # -n: don't resolve names (faster)
tracepath -n 10.0.0.12        # also discovers path MTU
mtr -n 8.8.8.8                # continuous traceroute + loss stats
```

---

## 6. DNS

DNS maps names → records. Resolution path from an app:

```text
app → libc resolver (/etc/nsswitch.conf: files then dns) → /etc/hosts → /etc/resolv.conf nameserver
    → recursive resolver → root (.) → TLD (.com) → authoritative (example.com) → answer (cached by TTL)
```

| Record | Meaning | K8s example |
|--------|---------|-------------|
| A / AAAA | name → IPv4 / IPv6 | `web.shop.svc.cluster.local → 10.96.12.4` |
| CNAME | alias | ExternalName Service |
| SRV | service + port | `_http._tcp.web.shop.svc.cluster.local` |
| PTR | IP → name | reverse lookups |
| NS / SOA | delegation / zone info | CoreDNS is authoritative for `cluster.local` |

```bash
dig example.com                 # full answer: QUESTION, ANSWER, TTL, server used, query time
dig +short example.com A
dig @1.1.1.1 example.com        # ask a specific server
dig +trace example.com          # follow delegation from root
dig -x 8.8.8.8 +short           # reverse
nslookup example.com
```

`dig` output keys: `status: NOERROR` (ok) / `NXDOMAIN` (name doesn't exist) / `SERVFAIL` (server problem);
`ANSWER SECTION` with TTL; `SERVER:` which resolver answered.

---

## 7. TCP vs UDP and ports

| | TCP | UDP |
|--|-----|-----|
| Connection | yes (3-way handshake) | no |
| Reliability | retransmits, ordered | none |
| Use | HTTP/1-2, gRPC, DBs, SSH | DNS, VXLAN, QUIC/HTTP3, metrics (StatsD), WireGuard |
| K8s gotcha | conntrack entries per connection | DNS over UDP + conntrack races → 5 s timeouts |

TCP handshake and teardown:

```text
Client                Server
  SYN  ──────────────►          (client: SYN_SENT)
       ◄────────────── SYN-ACK
  ACK  ──────────────►          ESTABLISHED
  ... data ...
  FIN  ──────────────►          (FIN_WAIT / CLOSE_WAIT / TIME_WAIT states)
```

Failure signatures you must recognise:

| Observation | Meaning |
|-------------|---------|
| **Connection refused** (RST back immediately) | host reachable, **nothing listening** on that port (or wrong port/targetPort) |
| **Connection timed out** (SYN, no reply) | packets **dropped**: firewall, NetworkPolicy, routing, security group, dead host |
| **No route to host** | ICMP unreachable / no ARP reply |
| Connection reset mid-stream | app crashed, proxy idle timeout, conntrack table full |

**Ports:** 0–1023 well-known (need `CAP_NET_BIND_SERVICE` to bind), 1024–49151 registered,
32768–60999 Linux ephemeral (`sysctl net.ipv4.ip_local_port_range`), 30000–32767 Kubernetes NodePorts.

```bash
ss -tulpn                       # listening sockets (-p needs sudo to see other users' processes)
ss -tn state established        # current TCP connections
ss -s                           # summary counts
sudo lsof -i :8080              # who owns port 8080
nc -zv 10.0.0.12 6443           # quick TCP port check (netcat)
```

---

## 8. HTTP and HTTPS

- HTTP request: method, path, headers (`Host:` is what L7 routing uses), body.
- HTTPS = HTTP inside **TLS**. TLS handshake: client hello (with **SNI** = hostname) → server certificate →
  key exchange → encrypted session. **SNI** lets one IP serve many TLS hostnames (Ingress relies on it).

```bash
curl -v http://example.com              # -v shows request/response headers
curl -sI https://kubernetes.io          # -I headers only, -s silent
curl -H "Host: app.example.com" http://<ingress-ip>/   # fake host header to test L7 routing
curl --resolve app.example.com:443:<ip> https://app.example.com/   # force DNS for TLS/SNI tests
curl -k https://self-signed.local       # -k skip cert verification (testing only!)
openssl s_client -connect kubernetes.io:443 -servername kubernetes.io </dev/null | openssl x509 -noout -subject -dates
curl -w '%{time_namelookup} %{time_connect} %{time_appconnect} %{time_total}\n' -o /dev/null -s https://kubernetes.io
```

The last line breaks latency into DNS, TCP connect, TLS handshake and total — invaluable for "it's slow".

---

## 9. Network interfaces, bridges, NAT, firewall, packet flow

| Concept | One-line definition | Linux object |
|---------|--------------------|--------------|
| Interface | something that sends/receives packets | `eth0`, `lo`, `vethX`, `cni0`, `flannel.1`, `tunl0`, `cilium_host` |
| Bridge | software L2 switch | `ip link add br0 type bridge` |
| NAT | rewrite src/dst address | iptables/nft `nat` table, conntrack |
| Firewall | allow/deny rules | netfilter filter hooks, cloud security groups |

Packet flow through a Linux host (simplified netfilter hooks):

```text
              incoming packet
                   │
             ┌─────▼─────┐
             │PREROUTING │  ← DNAT happens here (Service ClusterIP → Pod IP)
             └─────┬─────┘
          routing decision: for me or forward?
         ┌─────────┴─────────┐
   ┌─────▼────┐        ┌─────▼────┐
   │  INPUT   │        │ FORWARD  │  ← Pod-to-Pod traffic on a node passes here
   └─────┬────┘        └─────┬────┘
   local process             │
   ┌─────▼────┐              │
   │  OUTPUT  │ ← DNAT for locally-generated traffic to a Service
   └─────┬────┘              │
         └────────┬──────────┘
            ┌─────▼──────┐
            │POSTROUTING │  ← SNAT / MASQUERADE (Pod → internet uses node IP)
            └─────┬──────┘
             outgoing packet
```

---

## 10. Hands-on lab: practise on your Ubuntu host

```bash
ip -br addr                     # brief: interface, state, addresses
ip link show                    # MAC, MTU, state (UP/DOWN, LOWER_UP = cable/peer present)
ip route; ip route get 1.1.1.1
ip neigh
ping -c 3 1.1.1.1               # ICMP reachability (may be blocked in some clouds)
traceroute -n 1.1.1.1
dig kubernetes.io +short
ss -tulpn
sudo tcpdump -ni any -c 20 'port 53'   # -n no name lookup, -i any all interfaces, -c 20 stop after 20
# in another terminal: dig example.com → you'll see the query and answer packets
sudo tcpdump -ni any -c 10 'tcp port 443 and tcp[tcpflags] & tcp-syn != 0'   # only SYN packets
```

How to read a tcpdump line:

```text
10:01:02.123 eth0 Out IP 192.168.1.11.51234 > 1.1.1.1.53: 4242+ A? example.com. (29)
             │    │      └ src ip.port          └ dst ip.port  └ DNS id, A query
             │    └ direction (with -i any)
             └ interface
```

---

## Interview questions

1. **What is CIDR?** Notation `/n` giving the number of network bits; replaces classful addressing.
2. **How many IPs in a /24 and a /16?** 256 and 65,536.
3. **Why must Pod CIDR not overlap the VPC/LAN?** The kernel would route Pod-bound traffic to the LAN (or vice
   versa) — silent misrouting.
4. **What does ARP do?** Resolves IPv4 → MAC on the local L2 segment.
5. **What is a default gateway?** Router used for destinations with no more specific route.
6. **Longest prefix match?** Most specific matching route wins.
7. **Refused vs timeout?** Refused: reached host, nothing listening. Timeout: packets dropped somewhere.
8. **TCP vs UDP for DNS?** Usually UDP; TCP for large responses/zone transfers; Kubernetes DNS issues often
   relate to UDP + conntrack.
9. **What is SNI?** Hostname sent in TLS ClientHello so a server can pick the right certificate.
10. **What is NAT and where is it used in K8s?** Address rewriting: DNAT for Services, SNAT/masquerade for
    Pod egress to the internet and some NodePort paths.

**Scenario:** "curl to a Service hangs." → Timeout ⇒ think drops: NetworkPolicy, no endpoints with
`externalTrafficPolicy` quirks, CNI routes, security groups. "Refused" ⇒ wrong targetPort or app not listening.

**Follow-ups:** Explain TIME_WAIT and ephemeral port exhaustion behind NAT. How does path MTU discovery work
and why do ICMP blocks break it?
