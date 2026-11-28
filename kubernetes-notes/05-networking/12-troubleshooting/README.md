# 05.12 — Kubernetes Networking Troubleshooting Playbook

## 1. The systematic workflow

Always debug **from the outside in, layer by layer**, and change one thing at a time.

```text
 1. Define precisely:   who → what (name/IP:port) → symptom (refused / timeout / DNS error / 5xx / slow)
 2. Objects:            Pods Ready? Service selector → EndpointSlice has addresses? Ingress/Route accepted?
 3. DNS:                does the name resolve, to the expected IP?
 4. L3/L4 path:         Pod IP reachable directly? Service VIP? NodePort? From same node vs other node?
 5. Policy:             NetworkPolicy / mesh AuthorizationPolicy / security groups
 6. Node dataplane:     CNI agent, routes, tunnels, kube-proxy rules, conntrack, MTU
 7. Packets:            tcpdump at each hop until you find where packets stop
```

### Command kit

```bash
kubectl get pods -A -o wide                                   # status, IP, node
kubectl get services -A
kubectl get endpointslices -A
kubectl describe pod <pod-name>                               # events: probes, sandbox/CNI errors
kubectl logs <pod-name> [-c container] [--previous]
kubectl exec -it <pod-name> -- sh
kubectl get nodes -o wide
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl debug -it <pod> --image=nicolaka/netshoot --target=<container>    # tools for distroless Pods (shares netns)
kubectl debug node/<node> -it --image=nicolaka/netshoot                   # host netns shell on a node (host fs at /host)
# inside Pod / node:
ip addr; ip route; ip neigh; ss -tulpn
tcpdump -ni any host <ip> and port <port>
curl -v --max-time 5 http://<target>
dig <name>; dig @<dns-ip> <name>
```

### Interpret the symptom first

| Symptom | Means | Look at |
|---------|-------|---------|
| `Could not resolve host` / NXDOMAIN | DNS | name, namespace, CoreDNS, egress policy to DNS |
| `Connection refused` | reached the IP, nothing listening / REJECT | targetPort, app bind address, Service without endpoints |
| `Connection timed out` | packets dropped | NetworkPolicy, SG/firewall, routing, CNI, MTU (for large payloads) |
| `No route to host` | ICMP unreachable/ARP failure | routes, Pod gone, node down |
| HTTP 502/503/504 from proxy | proxy reached, upstream bad | endpoints, upstream health, timeouts |
| Works sometimes | one bad backend/node | per-endpoint tests, per-node tests |

### Reusable test Pods

```bash
kubectl run tmp-shell --rm -it --image=nicolaka/netshoot -- bash                       # in current namespace
kubectl run tmp-shell --rm -it --image=nicolaka/netshoot --overrides='{"spec":{"nodeName":"lab-worker2"}}' -- bash   # pin to a node
```

---

## 2. Issue playbooks

Each entry: **Symptoms → Causes → Diagnosis steps (commands + expected output) → Fix → Prevention.**

### 2.1 Pod cannot communicate with another Pod

- **Symptoms:** `curl <pod-ip>:<port>` times out; same-node works but cross-node doesn't (or vice versa).
- **Causes:** CNI agent down on a node; missing routes/tunnel; firewall blocking overlay ports; NetworkPolicy; app bound to
  127.0.0.1; MTU.
- **Diagnosis:**
  ```bash
  kubectl get pods -o wide                                     # note both Pods' IPs and nodes
  kubectl exec A -- ping -c2 <B-ip>                            # L3 test (ICMP may be blocked by policy)
  kubectl exec A -- curl -sv -m3 <B-ip>:<port>
  kubectl exec B -- ss -tlnp                                   # expect LISTEN 0.0.0.0:<port> or *:<port> — NOT 127.0.0.1
  kubectl get pods -n kube-system -o wide | grep -E 'calico|cilium|flannel|aws-node'   # agent Running on both nodes?
  kubectl debug node/<nodeA> -it --image=nicolaka/netshoot -- ip route                  # route for B's Pod CIDR exists?
  # watch where packets stop: on node A's eth0 then node B's eth0 (overlay: udp port 8472/4789)
  kubectl debug node/<nodeB> -it --image=nicolaka/netshoot -- tcpdump -ni any host <A-ip>
  ```
  Expected healthy: SYN seen leaving A's node and arriving at B's node, SYN-ACK returning.
- **Fix:** restart/repair CNI agent; open UDP 8472/4789, TCP 179, IP proto 4 between nodes; disable cloud source/dest check
  for routed modes; fix app bind address; adjust policy.
- **Prevent:** CNI health alerts (e.g. `cilium-health`), infra-as-code security groups, connectivity tests in CI
  (`cilium connectivity test`, synthetic probes).

### 2.2 Service cannot reach Pods

- **Symptoms:** Pod IP works, Service name/VIP doesn't; or `connection refused` via Service.
- **Causes:** selector mismatch; Pods not Ready; wrong `targetPort`; Service in other namespace; kube-proxy broken.
- **Diagnosis:**
  ```bash
  kubectl get svc web -o wide                                    # SELECTOR column
  kubectl get pods -l app=web --show-labels                      # do labels match?
  kubectl get endpointslices -l kubernetes.io/service-name=web   # ENDPOINTS empty → selector/readiness problem
  kubectl describe svc web | grep -E 'TargetPort|Endpoints'
  kubectl get pod <web-pod> -o jsonpath='{.spec.containers[*].ports}'
  kubectl exec tmp -- curl -sv -m3 <pod-ip>:<targetPort>         # backend itself OK?
  kubectl exec tmp -- curl -sv -m3 web:80                        # via Service
  ```
- **Fix:** align selector/labels; fix readiness probe; set `targetPort` to the real container port or its name.
- **Prevent:** named ports, Helm/Kustomize templates sharing labels, readiness probes reviewed, `kubeconform` + policy checks.

### 2.3 DNS resolution failure

- **Symptoms:** `could not resolve host`, `i/o timeout` on port 53, apps slow at startup.
- **Causes:** CoreDNS down/overloaded; kube-dns no endpoints; NetworkPolicy blocking 53; upstream DNS unreachable; loop;
  ndots/search misuse; wrong namespace in name.
- **Diagnosis:**
  ```bash
  kubectl exec tmp -- cat /etc/resolv.conf                       # nameserver 10.96.0.10, search …, ndots:5
  kubectl exec tmp -- dig kubernetes.default.svc.cluster.local   # status NOERROR + 10.96.0.1 expected
  kubectl -n kube-system get pods -l k8s-app=kube-dns
  kubectl -n kube-system logs -l k8s-app=kube-dns --tail=30      # "plugin/loop: Loop … detected", "i/o timeout" to upstream
  kubectl get endpointslices -n kube-system -l kubernetes.io/service-name=kube-dns
  kubectl exec tmp -- dig @<coredns-pod-ip> kubernetes.default.svc.cluster.local   # bypasses kube-proxy
  kubectl exec tmp -- dig @<coredns-pod-ip> google.com           # external forwarding works?
  kubectl get networkpolicy -n <app-ns>                          # egress deny without DNS allow?
  ```
- **Fix:** scale/restart CoreDNS; allow egress UDP+TCP 53 to kube-dns; fix Corefile `forward`; kubelet resolvConf for
  systemd-resolved; use FQDNs.
- **Prevent:** ≥2 replicas + PDB + anti-affinity, NodeLocal DNSCache, CoreDNS SERVFAIL/latency alerts, DNS rule in every
  default-deny template.

### 2.4 Ingress / Gateway not working

- **Symptoms:** 404, 503, TLS errors, no external address.
- **Causes:** no controller; wrong `ingressClassName`; Host mismatch; route not attached; backend has no endpoints; cert
  Secret missing; LB pending.
- **Diagnosis:**
  ```bash
  kubectl get ingressclass; kubectl get ingress -A               # ADDRESS populated?
  kubectl describe ingress <name>                                # backends + events
  kubectl get gateway,httproute -A
  kubectl get httproute <name> -o jsonpath='{.status.parents[*].conditions}' | jq   # Accepted / ResolvedRefs
  curl -sv -H "Host: shop.example.com" http://<lb-ip>/            # bypass DNS
  curl -sv --resolve shop.example.com:443:<lb-ip> https://shop.example.com/   # correct SNI
  kubectl logs -n <controller-ns> deploy/<controller> --tail=50
  kubectl get endpointslices -l kubernetes.io/service-name=<backend>
  ```
- **Fix:** install/correct controller class; fix hostnames; attach route to correct listener/namespace (`allowedRoutes`,
  `ReferenceGrant`); fix Secret; fix backend.
- **Prevent:** synthetic HTTPS checks per hostname, cert expiry alerts (cert-manager metrics), CI validation of routes.

### 2.5 Pod IP unavailable (Pod stuck `ContainerCreating`, no IP)

- **Symptoms:** `kubectl get pod -o wide` shows `<none>` IP; events `FailedCreatePodSandBox`.
- **Causes:** CNI not ready; IPAM exhausted; AWS ENI/IP limits; leaked host-local reservations.
- **Diagnosis:**
  ```bash
  kubectl describe pod <pod> | tail -20
  # "failed to setup network for sandbox: plugin type=\"calico\" failed (add): ..."   or
  # "failed to assign an IP address to container" (aws-node)  or  "no IP addresses available in range set"
  kubectl get nodes -o custom-columns=N:.metadata.name,PODCIDR:.spec.podCIDR
  kubectl debug node/<node> -it --image=busybox:1.36 -- ls /host/var/lib/cni/networks/   # host-local reservations
  kubectl -n kube-system logs ds/aws-node -c aws-node --tail=50       # EKS
  calicoctl ipam show --show-blocks                                   # Calico
  ```
- **Fix:** repair CNI agent; free leaked IPs (CNI GC / restart agent); larger Pod CIDR; EKS prefix delegation / larger instance
  types / secondary CIDR.
- **Prevent:** IP capacity dashboards and alerts (e.g. `awscni_assigned_ip_addresses` vs total), right-sized CIDRs at design time.

### 2.6 CNI failure (node `NotReady`)

- **Symptoms:** `NetworkReady=false reason:NetworkPluginNotReady message:cni plugin not initialized`.
- **Causes:** no CNI installed; CNI Pod crash-looping on that node; config file missing/duplicated; wrong binary arch.
- **Diagnosis:**
  ```bash
  kubectl describe node <node> | grep -A5 Conditions
  kubectl get pods -A -o wide --field-selector spec.nodeName=<node>
  kubectl logs -n <cni-ns> <cni-pod-on-node> --all-containers --tail=50
  # on node:
  ls -l /etc/cni/net.d/ /opt/cni/bin/
  journalctl -u containerd -u kubelet --since "15 min ago" | grep -i cni
  ```
- **Fix:** install/repair CNI; remove stale configs from previous CNIs; restart containerd/kubelet after config fix.
- **Prevent:** golden node images, DaemonSet tolerations for all taints, upgrade CNI with tested procedures.

### 2.7 NetworkPolicy blocking traffic

- **Symptoms:** timeouts after a policy rollout; only some sources fail.
- **Diagnosis:**
  ```bash
  kubectl get networkpolicy -n <dst-ns>; kubectl get networkpolicy -n <src-ns>
  kubectl describe networkpolicy -n <ns> <name>
  kubectl get pods -n <ns> --show-labels; kubectl get ns --show-labels
  hubble observe --to-pod <ns>/<pod> --verdict DROPPED        # Cilium shows "Policy denied"
  # Calico: enable flow logs / use calicoctl; or temporarily apply an allow-all policy to confirm
  ```
- **Fix:** add the missing allow (both egress of source and ingress of destination; correct Pod ports; AND/OR selector shape).
- **Prevent:** policy tests in CI (e.g. `cyclonus`, `netassert`), staged rollouts, flow-log analysis before default-deny.

### 2.8 Node connectivity issue

- **Symptoms:** a whole node's Pods unreachable; node `NotReady`/`Unknown`; `kubectl logs/exec` to Pods on that node fails.
- **Causes:** node network down; kubelet can't reach API server; security group change; firewall (ufw) enabled; route table.
- **Diagnosis:**
  ```bash
  kubectl get nodes -o wide; kubectl describe node <node>       # Lease renewTime stale?
  # from another node / bastion:
  ping <node-ip>; nc -zv <node-ip> 10250; nc -zv <api-server> 6443
  # on the node:
  systemctl status kubelet; journalctl -u kubelet -n 50
  ip route; sudo ufw status; sudo iptables -S INPUT | head
  ```
- **Fix:** restore network/SG rules (10250 from control plane, overlay ports between nodes), restart kubelet; replace node.
- **Prevent:** node problem detector, auto-repair (managed node groups), SG changes via reviewed IaC.

### 2.9 kube-proxy issues

- **Symptoms:** Service VIPs fail on specific nodes; new Services don't work; endpoints correct.
- **Diagnosis:**
  ```bash
  kubectl -n kube-system get pods -l k8s-app=kube-proxy -o wide
  kubectl -n kube-system logs <kube-proxy-pod-on-node> --tail=50
  curl -s <node-ip>:10256/healthz                               # lastUpdated recent?
  # on node, per dataplane (see 05.06 §6):
  iptables-save -t nat | grep <svc-ip>        # iptables mode
  nft list map ip kube-proxy service-ips      # nftables mode
  ipvsadm -Ln -t <svc-ip>:<port>              # ipvs mode
  lsmod | grep br_netfilter; sysctl net.ipv4.ip_forward
  ```
- **Fix:** restart kube-proxy; fix module/sysctls; resolve iptables backend conflicts; for scale move to nftables/eBPF.
- **Prevent:** monitor `kubeproxy_sync_proxy_rules_last_timestamp_seconds`, consistent node images.

### 2.10 Connection timeout

- **Causes:** something **drops** packets: NetworkPolicy, SG/NACL, wrong routes, overlay blocked, `externalTrafficPolicy: Local`
  node without endpoints, conntrack full, MTU (large payloads only).
- **Diagnosis:** narrow the hop: Pod IP vs Service vs NodePort vs LB; same node vs other node; tcpdump at source veth, source
  node eth0, destination node eth0, destination veth. The last place you see the SYN is just before the drop.
  ```bash
  kubectl exec tmp -- curl -sv -m5 <target>          # "Connection timed out after 5000 ms"
  dmesg | grep -iE 'conntrack|drop'                  # on nodes
  ```
- **Fix/Prevent:** as per the layer identified; explicit timeouts and retries in clients to fail fast.

### 2.11 Connection refused

- **Causes:** process not listening on that port / listening on localhost; wrong `targetPort`; Service with **no endpoints**
  (kube-proxy REJECT); container crashed; sidecar/mesh port mismatch.
- **Diagnosis:**
  ```bash
  kubectl get endpointslices -l kubernetes.io/service-name=<svc>
  kubectl exec <pod> -- ss -tlnp                     # or: kubectl debug ... -- ss -tlnp
  kubectl logs <pod> --previous
  ```
- **Fix:** bind `0.0.0.0`; correct ports; fix crash.
- **Prevent:** named ports, readiness probes on the serving port, contract tests.

### 2.12 MTU problems

- **Symptoms:** ping and small requests work; TLS handshakes, large JSON, `git clone`, image pulls via Pods hang.
- **Diagnosis:**
  ```bash
  kubectl exec A -- cat /sys/class/net/eth0/mtu            # e.g. 1500 on VXLAN = wrong (should be ≤1450)
  kubectl exec A -- ping -M do -s 1472 -c2 <B-ip>          # fails?
  kubectl exec A -- ping -M do -s 1400 -c2 <B-ip>          # works? → MTU issue confirmed
  kubectl debug node/<n> -it --image=nicolaka/netshoot -- tcpdump -ni any 'icmp[icmptype]==3 and icmp[icmpcode]==4'   # frag-needed
  ```
- **Fix:** set CNI MTU = underlay − overhead (Calico/Cilium config), restart Pods; allow ICMP type 3 code 4; MSS clamping on VPNs.
- **Prevent:** document underlay MTU per environment; test large payloads in connectivity checks.

### 2.13 Packet loss

- **Symptoms:** retries, latency spikes, TCP retransmits, intermittent 5xx.
- **Diagnosis:**
  ```bash
  kubectl exec A -- mtr -n -c 100 -r <B-ip>                 # per-hop loss
  # nodes:
  ip -s link show eth0                                      # RX/TX dropped / errors increasing?
  nstat -az | grep -Ei 'TcpRetransSegs|ListenDrops|ListenOverflows'
  ethtool -S eth0 | grep -Ei 'drop|allowance'               # cloud PPS/bandwidth allowance exceeded
  conntrack -S                                              # insert_failed / drop
  cat /proc/net/softnet_stat                                # 2nd column = backlog drops
  ```
- **Fix:** scale instance/network type, spread traffic, raise conntrack/backlog limits, fix noisy neighbour, increase app
  listen backlog (`somaxconn`).
- **Prevent:** node network dashboards (node-exporter), alerts on retransmits and drops.

### 2.14 CoreDNS issues (performance/stability)

- **Symptoms:** occasional 5 s lookups, SERVFAIL bursts, CoreDNS OOM/CPU throttling.
- **Diagnosis:**
  ```bash
  kubectl -n kube-system top pods -l k8s-app=kube-dns
  kubectl -n kube-system describe pod -l k8s-app=kube-dns | grep -A3 'Last State'    # OOMKilled?
  kubectl -n kube-system port-forward deploy/coredns 9153 &  curl -s localhost:9153/metrics | grep -E 'coredns_dns_requests_total|rcode="SERVFAIL"|cache_(hits|misses)'
  conntrack -S | grep insert_failed                         # on nodes: UDP race indicator
  ```
- **Fix:** scale replicas (cluster-proportional-autoscaler), raise resources, enable NodeLocal DNSCache, reduce ndots, fix
  slow upstream.
- **Prevent:** capacity planning, SLO alerts on DNS latency.

---

## 3. Packet-path checklist for "client → Service → Pod" across nodes

```text
[ ] client Pod resolves name → ClusterIP                      (dig)
[ ] client Pod egress allowed (NetworkPolicy)                 (describe netpol)
[ ] client node has DNAT rule for ClusterIP:port              (iptables/nft/cilium service list)
[ ] DNAT picks a backend Pod IP (EndpointSlice ready)          (conntrack -L -d VIP)
[ ] client node routes to backend Pod CIDR                     (ip route get <pod-ip>)
[ ] overlay/underlay passes (UDP 8472/4789 or BGP routes)      (tcpdump on both node eth0)
[ ] backend node delivers to Pod veth                          (tcpdump on veth / lxc / cali)
[ ] backend ingress policy allows                              (hubble/flow logs)
[ ] app listens on targetPort on 0.0.0.0                       (ss -tlnp)
[ ] reply path symmetric, conntrack un-NATs                    (tcpdump shows SYN-ACK)
```

---

## Interview questions

1. **Walk me through debugging "service A can't reach service B".** DNS → endpoints → Pod IP direct → Service VIP → policy →
   node dataplane → tcpdump per hop.
2. **Refused vs timeout — what does each tell you?** Refused: reached a host with nothing listening/REJECT; timeout: dropped.
3. **How do you debug a distroless Pod's network?** `kubectl debug --target` ephemeral container or `nsenter -n` on the node.
4. **Service has no endpoints — causes?** Selector mismatch, Pods not Ready, wrong namespace.
5. **Large requests hang, small ones work — likely cause?** MTU/PMTUD blackhole.
6. **DNS works by Pod IP of CoreDNS but not via 10.96.0.10 — what's wrong?** Service dataplane (kube-proxy/eBPF) or kube-dns
   endpoints.
7. **Intermittent 5 s DNS delays?** conntrack race on UDP; NodeLocal DNSCache / single-request-reopen.
8. **Node NotReady with CNI message?** CNI agent/config missing on that node.
9. **How do you find where packets are dropped?** tcpdump at successive hops; counters; Hubble/pwru for drop reasons.
10. **One node can't reach Services, others can.** That node's kube-proxy/eBPF agent, br_netfilter/ip_forward, iptables backend.

**Follow-ups:** How would you build automated network health checks for a cluster? How do you troubleshoot asymmetric routing
with multiple ENIs (policy routing, `ip rule`)?
