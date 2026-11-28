# 05.07 — Kubernetes DNS and CoreDNS

## 1. Why DNS is central

Apps find Services by **name**, not IP. CoreDNS is a cluster add-on (Deployment `coredns` in `kube-system`, Service
`kube-dns`, usually ClusterIP `10.96.0.10`) that answers for the `cluster.local` zone and forwards everything else.

```text
 Pod (/etc/resolv.conf → nameserver 10.96.0.10)
   │ UDP/53 query "web.shop.svc.cluster.local A?"
   ▼
 Service kube-dns 10.96.0.10 ──kube-proxy DNAT──► CoreDNS Pod
   │  plugin chain: errors → health → ready → kubernetes (cluster.local) → prometheus → forward → cache → loop → reload
   │      kubernetes plugin answers from its in-memory cache of Services/EndpointSlices (watches the API)
   │      other names → forward to upstream (node's /etc/resolv.conf or configured resolvers)
   ▼
 answer 10.96.45.10 (TTL 30s)
```

---

## 2. DNS records Kubernetes creates

| Object | Record | Example |
|--------|--------|---------|
| ClusterIP Service | A/AAAA → ClusterIP | `web.shop.svc.cluster.local → 10.96.45.10` |
| Headless Service | A/AAAA → each ready Pod IP | `db-headless.shop.svc.cluster.local → 10.244.1.5, 10.244.2.9` |
| StatefulSet Pod (via headless) | A per Pod | `db-0.db-headless.shop.svc.cluster.local → 10.244.1.5` |
| Named Service port | SRV | `_pg._tcp.db-headless.shop.svc.cluster.local` |
| ExternalName | CNAME | `ext.shop.svc.cluster.local → kubernetes.io.` |
| Pod (if `pods insecure/verified`) | A by dashed IP | `10-244-1-5.shop.pod.cluster.local` |
| Pod with `hostname` + `subdomain` | A | `myhost.mysub.shop.svc.cluster.local` (needs headless Service `mysub`) |

General form: **`<service>.<namespace>.svc.<cluster-domain>`**.

---

## 3. Pod DNS configuration: resolv.conf, search domains, ndots

kubelet writes each Pod's `/etc/resolv.conf`:

```text
search shop.svc.cluster.local svc.cluster.local cluster.local
nameserver 10.96.0.10
options ndots:5
```

### How names are expanded

`ndots:5` = "if the name has **fewer than 5 dots**, try the search domains **first**".

Query `web` from namespace `shop` (0 dots → search list first):

1. `web.shop.svc.cluster.local` ✅ found → done.

Query `web.other` (1 dot):

1. `web.other.shop.svc.cluster.local` ❌ NXDOMAIN
2. `web.other.svc.cluster.local` ✅

Query `api.github.com` (2 dots < 5) — **wasteful**:

1. `api.github.com.shop.svc.cluster.local` ❌
2. `api.github.com.svc.cluster.local` ❌
3. `api.github.com.cluster.local` ❌
4. `api.github.com` ✅ — 4 queries (×2 for A + AAAA = 8) for one lookup.

Mitigations: use a trailing dot (`api.github.com.`), lower `ndots` via `dnsConfig`, enable NodeLocal DNSCache,
CoreDNS `autopath` plugin.

### dnsPolicy

| `dnsPolicy` | Behaviour |
|-------------|-----------|
| `ClusterFirst` (default) | cluster DNS; non-cluster names forwarded upstream |
| `ClusterFirstWithHostNet` | needed for `hostNetwork: true` Pods to still use cluster DNS |
| `Default` | inherit node's resolv.conf (no cluster names!) |
| `None` | everything from `dnsConfig` |

```yaml
apiVersion: v1
kind: Pod
metadata: { name: dns-tuned }
spec:
  dnsPolicy: ClusterFirst
  dnsConfig:
    options:
      - name: ndots
        value: "2"                 # external names with ≥2 dots resolve directly
      - name: single-request-reopen  # glibc: avoid A/AAAA conntrack race
  containers:
    - name: c
      image: nicolaka/netshoot
      command: ["sleep", "infinity"]
```

---

## 4. CoreDNS architecture and configuration

```bash
kubectl -n kube-system get deploy coredns
kubectl -n kube-system get svc kube-dns
kubectl -n kube-system get cm coredns -o yaml
```

Default Corefile (kubeadm), annotated:

```text
.:53 {                                  # serve all zones on port 53
    errors                              # log errors
    health { lameduck 5s }              # :8080/health; keep serving 5s during shutdown
    ready                               # :8181/ready — readiness probe
    kubernetes cluster.local in-addr.arpa ip6.arpa {   # authoritative for cluster zone + reverse zones
       pods insecure                    # answer Pod A records by dashed IP without verification
       fallthrough in-addr.arpa ip6.arpa  # unknown reverse lookups go to next plugin
       ttl 30
    }
    prometheus :9153                    # metrics
    forward . /etc/resolv.conf {        # everything else → upstream from the NODE's resolv.conf
       max_concurrent 1000
    }
    cache 30                            # cache answers up to 30s
    loop                                # detect forwarding loops and crash loudly
    reload                              # pick up ConfigMap changes automatically
    loadbalance                         # randomise order of A records
}
```

### Customisations

```text
# Stub domain: send corp.example.com to on-prem DNS
corp.example.com:53 {
    errors
    cache 30
    forward . 10.0.0.53 10.0.0.54
}
```

```text
# Rewrite: legacy name → Service
rewrite name legacy-db.example.com postgres.shop.svc.cluster.local
```

Apply with `kubectl -n kube-system edit cm coredns`; the `reload` plugin applies it in ~30 s (check logs for `Reloading`).

### DNS caching layers

| Layer | Notes |
|-------|-------|
| App/runtime | JVM caches forever by default in some configs (`networkaddress.cache.ttl`) |
| libc | glibc doesn't cache (unless nscd); musl doesn't |
| NodeLocal DNSCache | DaemonSet on every node at link-local IP `169.254.20.10`, uses TCP upstream to CoreDNS — avoids conntrack races, cuts latency |
| CoreDNS `cache` | shared cache per CoreDNS Pod |

---

## 5. Hands-on labs

### Lab 1 — resolve Services from Pods

```bash
kubectl create namespace dns-lab
kubectl -n dns-lab create deployment web --image=nginx:1.27
kubectl -n dns-lab expose deployment web --port=80
kubectl -n dns-lab run t --image=nicolaka/netshoot --restart=Never -- sleep infinity
kubectl -n dns-lab exec t -- cat /etc/resolv.conf
kubectl -n dns-lab exec t -- nslookup web
kubectl -n dns-lab exec t -- dig +short web.dns-lab.svc.cluster.local
kubectl -n dns-lab exec t -- dig +search web                     # dig ignores search list unless +search
kubectl -n dns-lab exec t -- dig +short kube-dns.kube-system.svc.cluster.local
kubectl -n dns-lab exec t -- dig -x $(kubectl -n dns-lab get svc web -o jsonpath='{.spec.clusterIP}') +short  # PTR
kubectl -n dns-lab exec t -- dig SRV _http._tcp.web.dns-lab.svc.cluster.local +short   # port name "80"? see note
```

Note: `kubectl expose` names the port only if you pass `--name`; SRV records require a **named port**.

### Lab 2 — watch the ndots expansion

```bash
kubectl -n dns-lab exec t -- sh -c 'tcpdump -ni eth0 -c 12 port 53 & sleep 1; curl -s -o /dev/null https://kubernetes.io; sleep 2'
# you'll see kubernetes.io.dns-lab.svc.cluster.local, .svc.cluster.local, .cluster.local → NXDOMAIN, then kubernetes.io
kubectl -n dns-lab exec t -- sh -c 'tcpdump -ni eth0 -c 4 port 53 & sleep 1; curl -s -o /dev/null https://kubernetes.io./; sleep 2'
# trailing dot → single direct query pair
```

### Lab 3 — debug DNS with the official dnsutils Pod

```bash
kubectl apply -f https://k8s.io/examples/admin/dns/dnsutils.yaml
kubectl exec -it dnsutils -- nslookup kubernetes.default
# Server: 10.96.0.10  Address: 10.96.0.10#53   Name: kubernetes.default.svc.cluster.local  Address: 10.96.0.1
```

### Lab 4 — troubleshoot CoreDNS

```bash
kubectl -n kube-system get pods -l k8s-app=kube-dns -o wide       # Running? Ready? Restarts?
kubectl -n kube-system logs -l k8s-app=kube-dns --tail=50
kubectl get endpointslices -n kube-system -l kubernetes.io/service-name=kube-dns   # CoreDNS Pods present?
kubectl -n dns-lab exec t -- dig @10.96.0.10 web.dns-lab.svc.cluster.local         # via Service VIP
COREDNS_IP=$(kubectl -n kube-system get pod -l k8s-app=kube-dns -o jsonpath='{.items[0].status.podIP}')
kubectl -n dns-lab exec t -- dig @$COREDNS_IP web.dns-lab.svc.cluster.local         # bypass Service: isolates kube-proxy issues
# Turn on query logging temporarily: add "log" to the Corefile server block
kubectl -n kube-system edit cm coredns
kubectl -n kube-system logs -l k8s-app=kube-dns -f
```

### Lab 5 — break and fix: NetworkPolicy blocking DNS

See [05.09](../09-network-policies/README.md) — a default-deny egress policy without a DNS allow rule is the most
common "DNS broke after we added policies" incident.

Cleanup: `kubectl delete ns dns-lab; kubectl delete pod dnsutils`.

---

## 6. Cluster DNS failures — causes and fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| All lookups time out | CoreDNS down / kube-dns has no endpoints / kube-proxy broken | check Pods, endpoints, kube-proxy |
| `CrashLoopBackOff` with "Loop ... detected" | node resolv.conf points to `127.0.0.53` (systemd-resolved) and CoreDNS forwards to itself | kubelet `resolvConf: /run/systemd/resolve/resolv.conf` or `forward . 8.8.8.8` |
| Cluster names work, external names fail | upstream unreachable, egress blocked | test `dig @<upstream>` from a node |
| Intermittent 5 s delays | conntrack race on parallel UDP A/AAAA | NodeLocal DNSCache, `single-request-reopen`, kernel updates |
| Works on Debian image, fails on Alpine | musl resolver differences (search, TCP) | use FQDN with trailing dot, newer musl, or glibc-based images |
| High CoreDNS CPU, latency | ndots:5 amplification, too few replicas | lower ndots, autopath, scale CoreDNS (cluster-proportional-autoscaler) |
| NXDOMAIN for other namespace Service | used short name | use `svc.namespace` |
| DNS fails only after NetworkPolicy | egress to kube-dns UDP+TCP 53 not allowed | add allow rule |

Production: ≥2 CoreDNS replicas with anti-affinity and a PDB, NodeLocal DNSCache on large clusters, alerts on
`coredns_dns_responses_total{rcode="SERVFAIL"}` and latency histograms.

---

## Interview questions

1. **What is the FQDN of a Service?** `<svc>.<ns>.svc.cluster.local`.
2. **What does `ndots:5` do?** Names with fewer than 5 dots try search domains first — causes extra queries for external names.
3. **How does CoreDNS know Service IPs?** The `kubernetes` plugin watches Services/EndpointSlices via the API.
4. **What does a headless Service return in DNS?** A records for each ready Pod (plus per-Pod names for StatefulSets).
5. **Why might CoreDNS crash-loop with a loop error?** Upstream points back to itself, often `127.0.0.53` from systemd-resolved.
6. **What is NodeLocal DNSCache?** Per-node caching DNS agent that reduces latency and conntrack issues.
7. **dnsPolicy for hostNetwork Pods?** `ClusterFirstWithHostNet`.
8. **How to forward a corporate domain to on-prem DNS?** Add a stub server block with `forward` in the Corefile.
9. **What's the Service IP of DNS?** The `kube-dns` Service (typically the 10th IP of the Service CIDR, e.g. 10.96.0.10).
10. **How do you test whether DNS or kube-proxy is the issue?** Query the CoreDNS Pod IP directly vs the Service VIP.

**Scenario:** After adding default-deny NetworkPolicies, all apps fail with "unknown host". → Allow egress UDP/TCP 53 to
`kube-system` CoreDNS Pods.

**Follow-ups:** How does the `autopath` plugin reduce queries? How would you expose split-horizon DNS for Ingress hostnames
(ExternalDNS)? Why should DNS allow TCP 53 as well as UDP?
