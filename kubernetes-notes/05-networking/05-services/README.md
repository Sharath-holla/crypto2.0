# 05.05 — Kubernetes Services Deep Dive

## 1. Why Services exist

Pods are cattle: they're recreated on rollouts, evictions, and node failures, and **each new Pod gets a new IP**.
Clients can't chase changing IPs. A **Service** gives a **stable virtual IP (ClusterIP) and DNS name** in front of a
**dynamic set of Pods chosen by a label selector**, and load-balances across them.

```text
          client Pod
              │  http://web.shop.svc.cluster.local  →  DNS → 10.96.45.10 (ClusterIP, stable)
              ▼
     ┌──────────────────┐   selector app=web
     │ Service "web"    │──────────────────────┐
     │ 10.96.45.10:80   │                      │ EndpointSlice controller keeps this list current
     └──────────────────┘                      ▼
                                 EndpointSlice: 10.244.1.5:8080 (ready), 10.244.2.9:8080 (ready),
                                                10.244.3.4:8080 (not ready → excluded)
     kube-proxy/eBPF on every node programs:  10.96.45.10:80 → one of the ready endpoints (DNAT)
```

The ClusterIP is **virtual**: it is not assigned to any interface and doesn't answer ping (in iptables/nftables mode).
It exists only as NAT rules / eBPF map entries on every node.

---

## 2. Anatomy of a Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: shop
spec:
  type: ClusterIP                 # ClusterIP | NodePort | LoadBalancer | ExternalName
  selector:
    app: web                      # Pods with this label (in the same namespace) become endpoints
  ports:
    - name: http                  # name required when >1 port; used by Ingress/Gateway/Istio
      protocol: TCP               # TCP | UDP | SCTP
      port: 80                    # Service port (what clients connect to)
      targetPort: http            # Pod port: number or the containerPort NAME (lets you change ports safely)
      appProtocol: http           # hint for gateways/meshes (http, h2c, grpc, kubernetes.io/ws…)
  sessionAffinity: None           # or ClientIP
  internalTrafficPolicy: Cluster  # Local = only endpoints on the same node as the client
  ipFamilyPolicy: SingleStack     # PreferDualStack / RequireDualStack
```

| Field | Meaning |
|-------|---------|
| `port` | port on the ClusterIP |
| `targetPort` | port on the Pod (defaults to `port`) |
| `nodePort` | port on every node (NodePort/LoadBalancer types), 30000–32767 |
| `containerPort` (in Pod) | documentation + name for `targetPort`; **not required** for traffic to work |

---

## 3. Endpoints vs EndpointSlices

| | ⚠️ `v1 Endpoints` | ✅ `discovery.k8s.io/v1 EndpointSlice` |
|--|-------------------|---------------------------------------|
| Status | deprecated (v1.33), still mirrored | the source of truth for kube-proxy/CoreDNS/meshes |
| Size | one object with ALL endpoints (≤1000) | many slices, default ≤100 endpoints each |
| Update cost | whole object rewritten and sent to every node on any change | only the changed slice |
| Extra data | ready only | `ready`, `serving`, `terminating`, `nodeName`, `zone`, `hints` |

```bash
kubectl get endpointslices -n shop -l kubernetes.io/service-name=web
kubectl get endpointslice -n shop <name> -o yaml
```

```yaml
addressType: IPv4
endpoints:
  - addresses: ["10.244.1.5"]
    conditions: { ready: true, serving: true, terminating: false }
    nodeName: lab-worker
    zone: us-east-1a
ports:
  - name: http
    port: 8080
    protocol: TCP
```

`ready=false, serving=true, terminating=true` = Pod is shutting down but still able to serve — used for graceful
connection draining (kube-proxy falls back to serving-terminating endpoints if no ready ones exist).

**Services without a selector:** create the Service with no `selector` and manage an EndpointSlice yourself (label
`kubernetes.io/service-name: <svc>`) to point a stable name at e.g. an external database IP.

---

## 4. Service types

### 4.1 ClusterIP (default) — internal only

```text
 client Pod 10.244.1.5 → 10.96.45.10:80
   [node of client] OUTPUT/PREROUTING: DNAT 10.96.45.10:80 → 10.244.2.9:8080 (random/consistent choice)
   → normal Pod-to-Pod routing (CNI) → backend Pod sees src 10.244.1.5 (client IP preserved)
   ← reply: conntrack reverses: src 10.244.2.9:8080 → 10.96.45.10:80
```

The DNAT happens **on the client's node**. No proxy hop.

### 4.2 NodePort — every node's IP:port

```text
 external client 203.0.113.7 → nodeA:31080
   nodeA PREROUTING: DNAT → backend Pod (maybe on nodeB)
   externalTrafficPolicy: Cluster (default) → also SNAT src → nodeA IP (so the reply returns via nodeA)
        ⇒ any node works, even load spread, but CLIENT IP IS LOST and an extra hop may occur
   externalTrafficPolicy: Local → only Pods on nodeA are used, NO SNAT
        ⇒ client IP preserved, no extra hop, but nodes without local Pods drop the traffic
          (LBs use healthCheckNodePort to avoid those nodes)
```

```yaml
apiVersion: v1
kind: Service
metadata: { name: web-np }
spec:
  type: NodePort
  selector: { app: web }
  externalTrafficPolicy: Cluster
  ports:
    - port: 80
      targetPort: 8080
      nodePort: 30080            # optional; auto-assigned if omitted
```

A NodePort Service **also** has a ClusterIP.

### 4.3 LoadBalancer — an external load balancer

The Service controller (cloud-controller-manager, AWS Load Balancer Controller, MetalLB, cloud-provider-kind…) provisions
an external LB and writes its address to `status.loadBalancer.ingress`.

```text
 Internet → Cloud LB (public IP/DNS) ─┬─ "instance" targets: LB → nodeX:NodePort → DNAT → Pod   (extra hop, SNAT unless Local)
                                      └─ "IP" targets:       LB → Pod IP directly               (needs VPC-routable Pod IPs, e.g. AWS VPC CNI)
```

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web-lb
  annotations:
    # Provider-specific behaviour lives in annotations, e.g. AWS Load Balancer Controller:
    service.beta.kubernetes.io/aws-load-balancer-type: external
    service.beta.kubernetes.io/aws-load-balancer-nlb-target-type: ip
    service.beta.kubernetes.io/aws-load-balancer-scheme: internet-facing
spec:
  type: LoadBalancer
  loadBalancerClass: service.k8s.aws/nlb    # pick which controller implements it
  selector: { app: web }
  externalTrafficPolicy: Local
  loadBalancerSourceRanges: ["203.0.113.0/24"]   # restrict client IPs
  ports:
    - port: 443
      targetPort: 8443
```

A LoadBalancer Service has a ClusterIP **and** NodePorts (unless `allocateLoadBalancerNodePorts: false`).
Each LoadBalancer Service usually costs one cloud LB — for many HTTP apps, use one Ingress/Gateway instead.

### 4.4 ExternalName — DNS alias

```yaml
apiVersion: v1
kind: Service
metadata: { name: payments-db }
spec:
  type: ExternalName
  externalName: mydb.abc123.us-east-1.rds.amazonaws.com
```

CoreDNS answers `payments-db.<ns>.svc.cluster.local` with a **CNAME**. No ClusterIP, no proxying, no ports. Caveats: TLS
hostname verification sees the *original* name; HTTP Host headers don't change.

### 4.5 Headless Service — `clusterIP: None`

No virtual IP, no kube-proxy rules. DNS returns **A records for every ready Pod**, and with StatefulSets, per-Pod names
(`db-0.db-headless.ns.svc.cluster.local`). Used for StatefulSets, client-side load balancing (gRPC), and service discovery
by clustered apps (Kafka, Cassandra, Elasticsearch). `publishNotReadyAddresses: true` includes unready Pods (bootstrap
of clusters).

### 4.6 Comparisons

| | ClusterIP | NodePort | LoadBalancer |
|--|-----------|----------|--------------|
| Reachable from | inside cluster | node IP:port (anyone who can reach nodes) | external LB address |
| Includes | — | ClusterIP | ClusterIP + NodePort |
| Port range | any | 30000–32767 | any on LB |
| Cost | free | free | a cloud LB each |
| Use | internal services | dev, bare metal, behind your own LB | production external L4 |

| | Headless | ClusterIP |
|--|---------|-----------|
| Virtual IP | none | yes |
| DNS returns | all Pod IPs | one VIP |
| Load balancing | client-side | kernel/eBPF per connection |
| Per-Pod DNS | yes (StatefulSet) | no |

---

## 5. Service discovery

1. **DNS** (preferred): `web`, `web.shop`, `web.shop.svc.cluster.local`; SRV: `_http._tcp.web.shop.svc.cluster.local`.
2. **Environment variables** injected at Pod start: `WEB_SERVICE_HOST`, `WEB_SERVICE_PORT` — only for Services that existed
   **before** the Pod started; disable with `enableServiceLinks: false` in big namespaces.

---

## 6. Load balancing and session affinity

- Balancing is **per connection**, not per request. A long-lived HTTP/2 or gRPC connection sticks to one Pod → uneven load.
  Fix: client-side LB via headless Service, or an L7 proxy/mesh that balances per request.
- iptables mode: random selection with probabilities; IPVS: round-robin/least-conn etc.; nftables: random via numgen map;
  Cilium: random or Maglev consistent hashing.
- `sessionAffinity: ClientIP` pins a client IP to one endpoint (default timeout 10800 s via
  `sessionAffinityConfig.clientIP.timeoutSeconds`). Behind SNAT all clients look the same — beware.

### Traffic locality

| Setting | Effect |
|---------|--------|
| `internalTrafficPolicy: Local` | in-cluster clients only use endpoints on their own node (node-local agents) |
| `externalTrafficPolicy: Local` | external traffic only to local endpoints, preserves client IP |
| `trafficDistribution: PreferClose` (newer: `PreferSameZone`, `PreferSameNode`) | prefer endpoints in the same zone/node — cuts cross-AZ cost |

---

## 7. Hands-on labs (kind multi-node cluster)

### Lab 1 — ClusterIP and endpoints

```bash
kubectl create namespace svc-lab
kubectl config set-context --current --namespace=svc-lab
kubectl create deployment web --image=registry.k8s.io/e2e-test-images/agnhost:2.53 --replicas=3 -- /agnhost netexec --http-port=8080
# agnhost netexec: /hostname returns the Pod name — perfect for seeing load balancing
kubectl expose deployment web --port=80 --target-port=8080
kubectl get svc web                                   # TYPE ClusterIP, CLUSTER-IP 10.96.x.x, PORT 80/TCP
kubectl get endpointslices -l kubernetes.io/service-name=web
kubectl run client --image=nicolaka/netshoot --restart=Never -- sleep infinity
kubectl exec client -- sh -c 'for i in $(seq 1 9); do curl -s web/hostname; echo; done'   # different Pod names
kubectl exec client -- ping -c1 -W1 web               # no reply: ClusterIP is virtual (iptables/nftables mode)
kubectl scale deploy web --replicas=1
kubectl get endpointslices -l kubernetes.io/service-name=web -w   # endpoints shrink live
```

### Lab 2 — readiness controls endpoints

```bash
kubectl patch deploy web --type=json -p='[{"op":"add","path":"/spec/template/spec/containers/0/readinessProbe","value":{"httpGet":{"path":"/healthz-missing","port":8080},"periodSeconds":2}}]'
kubectl get pods -w                                     # new Pods 0/1 Ready, old Pod kept (rollout blocked)
kubectl rollout undo deploy web
```

### Lab 3 — NodePort and externalTrafficPolicy

```bash
kubectl scale deploy web --replicas=2
kubectl expose deployment web --name=web-np --type=NodePort --port=80 --target-port=8080
NP=$(kubectl get svc web-np -o jsonpath='{.spec.ports[0].nodePort}')
NODE_IP=$(kubectl get node lab-worker -o jsonpath='{.status.addresses[0].address}')
curl -s http://$NODE_IP:$NP/clientip; echo     # client IP = a node IP (SNAT with Cluster policy)
kubectl patch svc web-np -p '{"spec":{"externalTrafficPolicy":"Local"}}'
for n in lab-control-plane lab-worker lab-worker2; do
  ip=$(kubectl get node $n -o jsonpath='{.status.addresses[0].address}')
  echo -n "$n: "; curl -s -m 2 http://$ip:$NP/clientip || echo "timeout (no local endpoint)"; echo
done                                             # only nodes hosting a web Pod answer; real client IP shown
```

### Lab 4 — LoadBalancer with MetalLB (bare metal / kind)

```bash
METALLB_VERSION=v0.15.2   # check releases
kubectl apply -f https://raw.githubusercontent.com/metallb/metallb/${METALLB_VERSION}/config/manifests/metallb-native.yaml
kubectl wait -n metallb-system --for=condition=Ready pod -l app=metallb --timeout=180s
docker network inspect kind -f '{{(index .IPAM.Config 0).Subnet}}'    # e.g. 172.18.0.0/16
cat <<'EOF' | kubectl apply -f -
apiVersion: metallb.io/v1beta1
kind: IPAddressPool
metadata: { name: kind-pool, namespace: metallb-system }
spec:
  addresses: ["172.18.255.200-172.18.255.250"]   # unused range inside the kind Docker subnet
---
apiVersion: metallb.io/v1beta1
kind: L2Advertisement
metadata: { name: l2, namespace: metallb-system }
spec:
  ipAddressPools: ["kind-pool"]
EOF
kubectl expose deployment web --name=web-lb --type=LoadBalancer --port=80 --target-port=8080
kubectl get svc web-lb -w                     # EXTERNAL-IP 172.18.255.200
curl -s http://172.18.255.200/hostname; echo
ip neigh | grep 172.18.255.200                # MetalLB L2 mode answered ARP for the VIP from one node
```

MetalLB L2 mode: one node "owns" the VIP and replies to ARP (failover on node loss). BGP mode: nodes advertise the VIP to
routers for true multi-node ECMP load balancing.

### Lab 5 — headless and ExternalName

```bash
kubectl expose deployment web --name=web-headless --cluster-ip=None --port=80 --target-port=8080
kubectl exec client -- dig +short web-headless.svc-lab.svc.cluster.local     # several Pod IPs
kubectl exec client -- dig +short web.svc-lab.svc.cluster.local              # one ClusterIP
kubectl create service externalname ext --external-name=kubernetes.io
kubectl exec client -- dig ext.svc-lab.svc.cluster.local | grep -A2 'ANSWER SECTION'   # CNAME kubernetes.io.
```

### Lab 6 — session affinity

```bash
kubectl patch svc web -p '{"spec":{"sessionAffinity":"ClientIP"}}'
kubectl exec client -- sh -c 'for i in $(seq 1 5); do curl -s web/hostname; echo; done'    # same Pod each time
```

Cleanup: `kubectl delete namespace svc-lab; kubectl config set-context --current --namespace=default`.

---

## 8. Common failures

| Symptom | Likely cause | Check |
|---------|-------------|-------|
| `curl svc` → connection refused | wrong `targetPort` / app listens on 127.0.0.1 | `kubectl get endpointslices`, `kubectl exec pod -- ss -tlnp` |
| timeout, no endpoints | selector doesn't match Pod labels, Pods not Ready | `kubectl get pods --show-labels`, `describe svc` (Endpoints: <none>) |
| works by Pod IP, not Service IP | kube-proxy down/misconfigured, br_netfilter missing | kube-proxy logs, iptables/nft rules |
| LoadBalancer `EXTERNAL-IP <pending>` forever | no LB controller (bare metal) / controller lacks IAM | install MetalLB / check AWS LB Controller logs |
| NodePort works on some nodes only | `externalTrafficPolicy: Local` | expected; or firewall/SG |
| uneven load with gRPC | per-connection balancing | headless + client LB, or mesh |
| Service in another namespace not found | used short name | `svc.otherns` |

---

## Interview questions

1. **Why do we need Services?** Stable IP/DNS and load balancing over changing Pod IPs.
2. **How does a Service find its Pods?** Label selector → EndpointSlice controller lists ready Pod IPs.
3. **ClusterIP vs NodePort vs LoadBalancer?** Internal VIP / plus port on all nodes / plus external LB.
4. **What is a headless Service?** `clusterIP: None`; DNS returns Pod IPs; used with StatefulSets/client-side LB.
5. **What is ExternalName?** A DNS CNAME to an external name, no proxying.
6. **port vs targetPort vs nodePort?** Service port / Pod port / port opened on each node.
7. **externalTrafficPolicy Local vs Cluster?** Local preserves client IP and avoids extra hops but only uses local endpoints;
   Cluster spreads evenly but SNATs.
8. **Why can't I ping a ClusterIP?** It's a virtual IP implemented only as DNAT rules for the defined ports.
9. **Endpoints vs EndpointSlices?** Slices are sharded, scalable, carry topology and terminating state; Endpoints is deprecated.
10. **Why is gRPC traffic unbalanced across Pods?** Long-lived HTTP/2 connections; kube-proxy balances per connection.

**Scenario:** "The Service has no endpoints." → Compare `kubectl get svc -o yaml` selector with `kubectl get pods --show-labels`;
check readiness; namespace mismatch.

**Follow-ups:** How does topology-aware routing decide hints? How does MetalLB BGP mode differ from L2 mode? What happens to
existing connections when a backend Pod is deleted?
