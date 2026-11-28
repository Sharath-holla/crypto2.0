# 05.11 — Istio Service Mesh

## 1. What a service mesh is and why it exists

With dozens of microservices, every team re-implements retries, timeouts, TLS, metrics and tracing — inconsistently.
A **service mesh** moves these concerns out of application code into the **network layer**, using proxies that intercept
service-to-service traffic, managed centrally.

| Capability | Without mesh | With mesh |
|------------|-------------|-----------|
| Encryption in transit | each app configures TLS | automatic **mTLS** |
| Service identity & authz | IP-based NetworkPolicy | identity-based (SPIFFE/ServiceAccount) L7 policies |
| Retries/timeouts/circuit breaking | libraries per language | config (VirtualService/DestinationRule) |
| Canary / traffic splitting | replica ratios | precise % weights, header routing |
| Golden metrics & tracing | instrument every app | proxy emits metrics + trace spans automatically |

When **not** to use one: few services, small team, latency-critical paths where sidecar overhead matters, or when Gateway API
+ NetworkPolicy + app libraries are enough. A mesh adds real operational complexity.

---

## 2. Istio architecture

```text
                       ┌───────────── Control plane ──────────────┐
                       │ istiod                                    │
                       │  • Pilot: watches K8s + Istio CRDs →      │
                       │    pushes config to proxies via xDS (gRPC)│
                       │  • Citadel/CA: issues workload certs      │
                       │  • injection webhook                      │
                       └──────────────┬────────────────────────────┘
                                      │ xDS (LDS/RDS/CDS/EDS/SDS)
  ┌──────────────── Data plane ───────▼───────────────────────────────────────────┐
  │ Sidecar mode:  [app]⇄[Envoy sidecar] ══mTLS══ [Envoy sidecar]⇄[app]           │
  │ Ambient mode:  [app] → ztunnel (node, L4 mTLS/HBONE) ══► (waypoint Envoy for L7) │
  │ Edge:          istio-ingressgateway / Gateway API gateway (Envoy Deployment)   │
  └────────────────────────────────────────────────────────────────────────────────┘
```

| | Control plane | Data plane |
|--|--------------|-----------|
| What | istiod | Envoy sidecars / ztunnel / waypoints / gateways |
| Job | compute config, distribute certs | actually forward/inspect/encrypt traffic |
| Failure impact | no new config; existing traffic keeps flowing | traffic affected |

**Envoy** is a high-performance L4/L7 proxy configured dynamically by **xDS APIs**: Listeners (LDS), Routes (RDS),
Clusters (CDS), Endpoints (EDS), Secrets/certs (SDS).

### Sidecar injection and traffic capture

1. Label namespace `istio-injection=enabled` (or revision label `istio.io/rev=<rev>`).
2. On Pod creation, the **mutating admission webhook** adds the `istio-proxy` container (as a native sidecar on recent
   Kubernetes) and an `istio-init` init container (or uses the **Istio CNI** plugin, avoiding `NET_ADMIN` in Pods).
3. iptables rules in the Pod's netns redirect outbound TCP to Envoy port **15001** and inbound to **15006**.
4. Envoy applies routing/policy, originates mTLS to the remote Envoy, which delivers to the app on localhost.

```text
 app → connect(reviews:9080) → iptables OUTPUT REDIRECT → Envoy:15001 → route (VirtualService) → pick endpoint (EDS)
     → mTLS (cert via SDS) → remote Pod: iptables PREROUTING → Envoy:15006 → authz (AuthorizationPolicy) → app:9080
```

### Ambient mode (GA since Istio 1.24)

- **ztunnel** DaemonSet: L4 mTLS, identity, L4 authz, telemetry. Traffic tunneled with **HBONE** (HTTP CONNECT over mTLS, port 15008).
- **Waypoint** proxies (Envoy, per namespace or service) only where L7 features are needed.
- Pros: no sidecars (less resource use, no restarts to upgrade proxies). Enable with `istio.io/dataplane-mode=ambient`
  on a namespace.

---

## 3. Install Istio (lab: kind, ≥ 8 GB RAM)

```bash
curl -L https://istio.io/downloadIstio | sh -        # downloads latest release into ./istio-<version>
cd istio-*/ && export PATH=$PWD/bin:$PATH
istioctl x precheck                                  # checks cluster compatibility
istioctl install --set profile=demo -y               # demo profile: istiod + ingress & egress gateways, high trace sampling
kubectl -n istio-system get pods,svc
kubectl label namespace default istio-injection=enabled
kubectl get crd | grep istio.io
istioctl version
```

Profiles: `default` (production starting point), `demo` (learning), `minimal`, `ambient`. For production prefer Helm charts
(`base`, `istiod`, `gateway`) or the operator-free `istioctl` with an IstioOperator file under Git.

### Deploy the Bookinfo sample

```bash
kubectl apply -f samples/bookinfo/platform/kube/bookinfo.yaml
kubectl get pods            # each Pod shows 2/2 → app + istio-proxy
kubectl exec deploy/ratings-v1 -c ratings -- curl -s productpage:9080/productpage | grep -o "<title>.*</title>"
# Edge: use Kubernetes Gateway API (Istio's recommended way)
kubectl get crd gateways.gateway.networking.k8s.io >/dev/null 2>&1 || \
  kubectl apply -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/standard-install.yaml
kubectl apply -f samples/bookinfo/gateway-api/bookinfo-gateway.yaml
kubectl wait --for=condition=programmed gtw bookinfo-gateway
kubectl port-forward svc/bookinfo-gateway-istio 8080:80 &
curl -s http://localhost:8080/productpage | grep -o "<title>.*</title>"
```

```text
 Bookinfo:  productpage(v1) → details(v1)
                            → reviews(v1 no stars | v2 black stars | v3 red stars) → ratings(v1)
```

---

## 4. Traffic management

### 4.1 DestinationRule — define subsets and policies for a destination

```yaml
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata:
  name: reviews
spec:
  host: reviews                       # the Kubernetes Service
  trafficPolicy:
    loadBalancer: { simple: LEAST_REQUEST }
    connectionPool:                   # circuit breaker part 1: limit concurrency
      tcp: { maxConnections: 100 }
      http: { http1MaxPendingRequests: 10, maxRequestsPerConnection: 10 }
    outlierDetection:                 # circuit breaker part 2: eject failing endpoints
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
  subsets:                            # named groups of Pods by label
    - { name: v1, labels: { version: v1 } }
    - { name: v2, labels: { version: v2 } }
    - { name: v3, labels: { version: v3 } }
```

### 4.2 VirtualService — how requests are routed

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata:
  name: reviews
spec:
  hosts: ["reviews"]
  http:
    - match:                                  # header-based routing: tester sees v2
        - headers:
            end-user: { exact: jason }
      route:
        - destination: { host: reviews, subset: v2 }
    - route:                                  # canary: 90/10 split for everyone else
        - destination: { host: reviews, subset: v1 }
          weight: 90
        - destination: { host: reviews, subset: v3 }
          weight: 10
      timeout: 3s                             # overall request timeout
      retries:
        attempts: 3
        perTryTimeout: 1s
        retryOn: 5xx,reset,connect-failure,refused-stream
```

```bash
kubectl apply -f samples/bookinfo/networking/destination-rule-all.yaml
kubectl apply -f reviews-vs.yaml              # the VirtualService above
for i in $(seq 1 20); do curl -s http://localhost:8080/productpage | grep -c 'color="red"'; done | sort | uniq -c   # ~10% red stars
```

### 4.3 Canary deployment flow

1. Deploy `reviews-v3` with label `version: v3` (same Service selects all versions).
2. Add subset v3 to DestinationRule.
3. VirtualService weights 95/5 → watch error rate & latency in Grafana/Kiali → 75/25 → 50/50 → 0/100.
4. Roll back instantly by setting weight back to 100/0.
Automate with **Argo Rollouts** or **Flagger** (analysis using Prometheus metrics).

### 4.4 Fault injection (chaos testing)

```yaml
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata: { name: ratings }
spec:
  hosts: ["ratings"]
  http:
    - fault:
        delay: { percentage: { value: 50 }, fixedDelay: 5s }
        abort: { percentage: { value: 10 }, httpStatus: 500 }
      route:
        - destination: { host: ratings, subset: v1 }
```

### 4.5 Gateways

| | Istio `Gateway` + `VirtualService` | Kubernetes Gateway API (`Gateway` + `HTTPRoute`) |
|--|-------------------------------------|--------------------------------------------------|
| API group | `networking.istio.io` | `gateway.networking.k8s.io` |
| Status | supported | ✅ recommended by Istio for new setups (also for mesh routing via GAMMA) |

---

## 5. Security: mTLS and authorization

```yaml
# Enforce mTLS for the whole mesh (put in the root namespace, istio-system)
apiVersion: security.istio.io/v1
kind: PeerAuthentication
metadata:
  name: default
  namespace: istio-system
spec:
  mtls:
    mode: STRICT              # PERMISSIVE (default) accepts plaintext too — use during migration
---
# Only productpage's ServiceAccount may call reviews, and only GET
apiVersion: security.istio.io/v1
kind: AuthorizationPolicy
metadata:
  name: reviews-allow-productpage
  namespace: default
spec:
  selector:
    matchLabels: { app: reviews }
  action: ALLOW
  rules:
    - from:
        - source:
            principals: ["cluster.local/ns/default/sa/bookinfo-productpage"]
      to:
        - operation:
            methods: ["GET"]
```

```bash
kubectl apply -f peer-auth.yaml -f authz.yaml
# A Pod without a sidecar can no longer talk plaintext to mesh workloads:
kubectl create ns legacy && kubectl -n legacy run curl --image=curlimages/curl --restart=Never -- sleep 3600
kubectl -n legacy exec curl -- curl -s -m 3 reviews.default:9080/reviews/0 || echo "rejected (no mTLS)"
istioctl x describe pod $(kubectl get pod -l app=reviews,version=v1 -o jsonpath='{.items[0].metadata.name}')
istioctl proxy-config secret deploy/productpage-v1 | head     # workload cert, validity
```

`RequestAuthentication` validates end-user JWTs at the edge or per workload.

---

## 6. Observability

```bash
kubectl apply -f samples/addons/prometheus.yaml -f samples/addons/grafana.yaml \
              -f samples/addons/kiali.yaml -f samples/addons/jaeger.yaml     # demo-grade addons
istioctl dashboard kiali         # service graph with live traffic, mTLS locks, error rates
istioctl dashboard grafana       # Istio mesh/service/workload dashboards
istioctl dashboard jaeger        # traces (apps must propagate trace headers: traceparent / x-b3-*)
```

Metrics emitted by every proxy: `istio_requests_total` (labels: source, destination, response_code),
`istio_request_duration_milliseconds`, `istio_tcp_sent_bytes_total`. Golden signals per service without code changes.

> Tracing caveat: the proxy creates spans, but **applications must forward trace headers** from incoming to outgoing requests,
> otherwise traces are broken into fragments.

---

## 7. Debugging Istio

```bash
istioctl analyze -A                                 # static config validation (typos, missing subsets, conflicts)
istioctl proxy-status                               # is every proxy SYNCED with istiod?
istioctl proxy-config routes deploy/productpage-v1 --name 9080 -o json | less
istioctl proxy-config clusters deploy/productpage-v1 | grep reviews
istioctl proxy-config endpoints deploy/productpage-v1 --cluster "outbound|9080|v1|reviews.default.svc.cluster.local"
kubectl logs deploy/reviews-v1 -c istio-proxy | tail     # access logs (enable via meshConfig.accessLogFile=/dev/stdout)
kubectl exec deploy/productpage-v1 -c istio-proxy -- pilot-agent request GET stats | grep upstream_rq_5xx
```

| Symptom | Cause |
|---------|-------|
| `503 UH` / `no healthy upstream` | subset labels match no Pods, outlier ejection |
| `503 NR` (no route) | VirtualService host mismatch |
| `upstream connect error ... reset` with STRICT mTLS | client without sidecar / PeerAuthentication conflict |
| `RBAC: access denied` (403) | AuthorizationPolicy |
| Pod 1/2 Ready | sidecar can't reach istiod, or app port not declared |
| Job never completes | old-style sidecar (fixed by native sidecars on K8s ≥ 1.29 with Istio support) |
| Protocol mis-detection | name Service ports `http-*`, `grpc-*` or set `appProtocol` |

---

## 8. Real-world use cases

- **Zero-trust east-west**: STRICT mTLS + AuthorizationPolicy deny-by-default per namespace — common in fintech/PCI.
- **Progressive delivery**: Flagger + Istio weights with automatic rollback on SLO breach.
- **Resilience**: timeouts/retries/circuit breakers to stop cascading failures; fault injection in staging game days.
- **Multi-cluster**: single mesh across clusters/regions with locality-aware failover.
- **Egress control**: route external calls through an egress gateway with TLS origination and allow-lists.

Cleanup: `kubectl delete -f samples/bookinfo/platform/kube/bookinfo.yaml; istioctl uninstall --purge -y; kubectl delete ns istio-system legacy`.

---

## Interview questions

1. **What is a service mesh?** Infrastructure layer of proxies providing mTLS, traffic control and telemetry for service-to-service calls.
2. **Istio control plane vs data plane?** istiod computes/distributes config and certs; Envoy/ztunnel proxies carry traffic.
3. **How does sidecar injection work?** A mutating webhook adds the Envoy container; iptables (init or CNI) redirect traffic to it.
4. **VirtualService vs DestinationRule?** VirtualService = how to route (matches, weights, retries, timeouts); DestinationRule =
   policies for the destination after routing (subsets, LB, connection pools, outlier detection, TLS).
5. **How do you do a canary in Istio?** Subsets by version label + weighted routes, gradually shifted while watching metrics.
6. **PERMISSIVE vs STRICT mTLS?** PERMISSIVE accepts both mTLS and plaintext (migration); STRICT only mTLS.
7. **How are workload identities issued?** istiod CA issues short-lived SPIFFE certs tied to ServiceAccounts, delivered via SDS.
8. **What is a circuit breaker in Istio?** connectionPool limits + outlierDetection ejecting unhealthy endpoints.
9. **What is ambient mode?** Sidecar-less data plane: ztunnel for L4 mTLS per node, optional waypoint proxies for L7.
10. **Why are my traces broken?** The app doesn't propagate trace context headers.

**Scenario:** After enabling STRICT mTLS, a legacy namespace can't reach services. → Inject sidecars/ambient there, or use a
namespace-level PERMISSIVE PeerAuthentication temporarily.

**Follow-ups:** Explain xDS and what each discovery service carries. Sidecar vs ambient trade-offs. How does locality failover work?
