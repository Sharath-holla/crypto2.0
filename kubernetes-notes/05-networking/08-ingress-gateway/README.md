# 05.08 — Ingress and Gateway API

## 1. Why Ingress exists

`LoadBalancer` Services are **L4** and usually cost **one cloud LB per Service**. For 30 HTTP microservices you want **one**
entry point that routes by **hostname and path**, terminates **TLS**, and maybe does redirects, rate limits, auth.
That's an **L7 reverse proxy** running inside the cluster, configured by Kubernetes objects.

```text
 Internet
    ↓  DNS: shop.example.com → LB address
 External Load Balancer (L4, cloud NLB / MetalLB / NodePort)
    ↓  TCP 443
 Ingress / Gateway controller Pods (Envoy, NGINX, Traefik, HAProxy…)   ← terminates TLS, reads Host + path
    ↓  chooses backend Service by rules, then (usually) picks a Pod IP from its EndpointSlice directly
 Kubernetes Service  (used for discovery; many controllers bypass the ClusterIP and send straight to Pod IPs)
    ↓
 EndpointSlice  (ready Pod IPs)
    ↓
 Pod  (receives HTTP; X-Forwarded-For carries the client IP)
```

| | Service (LoadBalancer) | Ingress | Gateway API |
|--|-----------------------|---------|-------------|
| Layer | L4 | L7 HTTP(S) | L4 + L7 (HTTP, gRPC, TLS, TCP, UDP) |
| Routing | port only | host + path | host, path, headers, query, method, weights |
| TLS | pass-through / LB | termination | termination, passthrough, backend TLS |
| Role separation | — | one object | GatewayClass (infra) / Gateway (ops) / Routes (devs) |
| Portability | high | low (annotations differ per controller) | high (expressive spec + conformance tests) |
| Status | stable | stable but **frozen** (no new features) | ✅ the future, GA since v1.0 |

**An Ingress object does nothing on its own.** You must install an **Ingress controller** that watches Ingress objects and
configures its proxy.

> ⚠️ **ingress-nginx retirement:** the community `kubernetes/ingress-nginx` controller was retired by SIG Network
> (best-effort maintenance ended March 2026; no more releases or security fixes). Existing installs keep running, but plan a
> migration to **Gateway API** (Envoy Gateway, NGINX Gateway Fabric, Istio, Cilium, Traefik, Kong, cloud gateways) or another
> maintained Ingress controller. F5's *NGINX Ingress Controller* (`nginx/kubernetes-ingress`) is a different, separately
> maintained project. The `ingress2gateway` tool converts Ingress manifests to Gateway API.

---

## 2. Ingress resource

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: shop
  namespace: shop
  annotations:
    # controller-specific features go in annotations (not portable!)
    traefik.ingress.kubernetes.io/router.entrypoints: websecure
spec:
  ingressClassName: traefik           # which controller handles this (replaces the old kubernetes.io/ingress.class annotation)
  tls:
    - hosts: ["shop.example.com"]
      secretName: shop-tls            # Secret type kubernetes.io/tls with tls.crt / tls.key
  rules:
    - host: shop.example.com          # host-based routing
      http:
        paths:
          - path: /api                # path-based routing
            pathType: Prefix          # Prefix | Exact | ImplementationSpecific
            backend:
              service:
                name: api
                port: { number: 8080 }
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend
                port: { name: http }
  defaultBackend:                     # anything not matched
    service: { name: frontend, port: { number: 80 } }
```

`pathType: Prefix` matches by path *elements*: `/api` matches `/api`, `/api/`, `/api/v1`, but **not** `/apix`.
Longest match wins.

---

## 3. Gateway API

```text
 GatewayClass "eg"          ← cluster-scoped, provided by infra/platform team: "which controller"
     ▲
 Gateway "public" (ns infra) ← listeners: HTTP :80, HTTPS :443 with cert, allowedRoutes from namespaces
     ▲ parentRefs
 HTTPRoute "shop" (ns shop)  ← owned by app team: hostnames, matches, filters, backendRefs (+ weights)
     │
 Service "api", Service "frontend"
```

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata:
  name: eg
spec:
  controllerName: gateway.envoyproxy.io/gatewayclass-controller
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: public
  namespace: infra
spec:
  gatewayClassName: eg
  listeners:
    - name: http
      protocol: HTTP
      port: 80
      allowedRoutes:
        namespaces: { from: All }        # or Selector with namespace labels
    - name: https
      protocol: HTTPS
      port: 443
      hostname: "*.example.com"
      tls:
        mode: Terminate
        certificateRefs:
          - kind: Secret
            name: wildcard-example-com
      allowedRoutes:
        namespaces: { from: All }
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: shop
  namespace: shop
spec:
  parentRefs:
    - name: public
      namespace: infra
      sectionName: https                 # attach to the HTTPS listener only
  hostnames: ["shop.example.com"]
  rules:
    - matches:
        - path: { type: PathPrefix, value: /api }
          headers:
            - name: x-canary
              value: "true"
      backendRefs:
        - name: api-v2
          port: 8080
    - matches:
        - path: { type: PathPrefix, value: /api }
      backendRefs:                        # weighted traffic split (canary)
        - { name: api,    port: 8080, weight: 90 }
        - { name: api-v2, port: 8080, weight: 10 }
      timeouts:
        request: 10s
    - matches:
        - path: { type: PathPrefix, value: / }
      backendRefs:
        - { name: frontend, port: 80 }
---
# Redirect HTTP → HTTPS on the plain listener
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: https-redirect
  namespace: shop
spec:
  parentRefs:
    - { name: public, namespace: infra, sectionName: http }
  hostnames: ["shop.example.com"]
  rules:
    - filters:
        - type: RequestRedirect
          requestRedirect: { scheme: https, statusCode: 301 }
```

Other route kinds: `GRPCRoute` (GA), `TLSRoute`, `TCPRoute`, `UDPRoute` (experimental channel).
Cross-namespace references to Services/Secrets need a **`ReferenceGrant`** in the target namespace — a security feature.

---

## 4. TLS, HTTPS and certificates

- **TLS termination at the proxy**: the controller holds the cert (Secret `kubernetes.io/tls`), decrypts, routes, and talks
  HTTP (or re-encrypts) to Pods.
- **TLS passthrough**: proxy routes by SNI without decrypting (Gateway `TLSRoute`, `mode: Passthrough`) — the Pod holds the cert.
- **cert-manager** automates certificates (Let's Encrypt ACME, private CA, Vault) and renews them.

```bash
# Self-signed cert for labs
openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
  -keyout tls.key -out tls.crt -subj "/CN=shop.local" -addext "subjectAltName=DNS:shop.local,DNS:*.shop.local"
kubectl create secret tls shop-tls --cert=tls.crt --key=tls.key
```

cert-manager in production:

```bash
helm repo add jetstack https://charts.jetstack.io && helm repo update
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true
```

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform-team@example.com          # use a team mailbox
    privateKeySecretRef: { name: letsencrypt-account }
    solvers:
      - http01:
          gatewayHTTPRoute:                    # solve HTTP-01 via Gateway API (or ingress: {ingressClassName: ...})
            parentRefs: [{ name: public, namespace: infra, kind: Gateway }]
```

Then annotate the Gateway with `cert-manager.io/cluster-issuer: letsencrypt` (Gateway support must be enabled in
cert-manager), or create a `Certificate` object explicitly.

---

## 5. Lab A — Ingress with Traefik on kind

Uses the kind cluster from chapter 03 (host ports 80/443 → node ports 30080/30443 on the control-plane container).

```bash
helm repo add traefik https://traefik.github.io/charts && helm repo update
helm install traefik traefik/traefik -n traefik --create-namespace \
  --set service.type=NodePort \
  --set ports.web.nodePort=30080 \
  --set ports.websecure.nodePort=30443
kubectl -n traefik get pods,svc
kubectl get ingressclass                         # "traefik"

# Two demo apps
kubectl create namespace ing-lab
kubectl -n ing-lab create deployment app1 --image=registry.k8s.io/e2e-test-images/agnhost:2.53 -- /agnhost netexec --http-port=8080
kubectl -n ing-lab create deployment app2 --image=registry.k8s.io/e2e-test-images/agnhost:2.53 -- /agnhost netexec --http-port=8080
kubectl -n ing-lab expose deployment app1 --port=80 --target-port=8080
kubectl -n ing-lab expose deployment app2 --port=80 --target-port=8080

cat <<'EOF' | kubectl apply -f -
# Traefik-specific Middleware: strip /one and /two before forwarding (path rewriting is NOT part of the Ingress spec)
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata: { name: strip, namespace: ing-lab }
spec:
  stripPrefix:
    prefixes: ["/one", "/two"]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: demo
  namespace: ing-lab
  annotations:
    traefik.ingress.kubernetes.io/router.middlewares: ing-lab-strip@kubernetescrd   # <namespace>-<name>@kubernetescrd
spec:
  ingressClassName: traefik
  rules:
    - host: app1.local
      http:
        paths:
          - { path: /, pathType: Prefix, backend: { service: { name: app1, port: { number: 80 } } } }
    - host: apps.local
      http:
        paths:
          - { path: /one, pathType: Prefix, backend: { service: { name: app1, port: { number: 80 } } } }
          - { path: /two, pathType: Prefix, backend: { service: { name: app2, port: { number: 80 } } } }
EOF
kubectl -n ing-lab get ingress demo

curl -s -H "Host: app1.local" http://localhost/hostname; echo          # host-based
curl -s -H "Host: apps.local" http://localhost/one/hostname; echo      # path-based → app1 Pod name
curl -s -H "Host: apps.local" http://localhost/two/hostname; echo      # path-based → app2 Pod name
curl -s -o /dev/null -w '%{http_code}\n' -H "Host: nope.local" http://localhost/   # 404 from Traefik
```

Note: without the Middleware the backend would receive the **full path** (`/two/hostname`). Path rewriting is
controller-specific with Ingress (annotations/CRDs); Gateway API has a portable `URLRewrite` filter.

**Trace the flow:** `curl localhost:80` → Docker port mapping → control-plane container :30080 → kube-proxy NodePort DNAT →
Traefik Pod → Traefik reads `Host`/path → picks an app Pod IP from EndpointSlices → Pod.

```bash
kubectl -n traefik logs deploy/traefik | tail       # access/config logs
```

### Add TLS

```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 30 -keyout tls.key -out tls.crt \
  -subj "/CN=app1.local" -addext "subjectAltName=DNS:app1.local"
kubectl -n ing-lab create secret tls app1-tls --cert=tls.crt --key=tls.key
kubectl -n ing-lab patch ingress demo --type=merge -p '{"spec":{"tls":[{"hosts":["app1.local"],"secretName":"app1-tls"}]}}'
curl -sk --resolve app1.local:443:127.0.0.1 https://app1.local/hostname; echo
openssl s_client -connect 127.0.0.1:443 -servername app1.local </dev/null 2>/dev/null | openssl x509 -noout -subject
```

---

## 6. Lab B — Gateway API with Envoy Gateway

Needs a LoadBalancer implementation (MetalLB from [05.05 Lab 4](../05-services/README.md)) or use port-forward.

```bash
EG_VERSION=v1.5.0     # check https://gateway.envoyproxy.io/ releases; the chart also installs Gateway API CRDs
helm install eg oci://docker.io/envoyproxy/gateway-helm --version ${EG_VERSION} -n envoy-gateway-system --create-namespace
kubectl wait -n envoy-gateway-system deploy/envoy-gateway --for=condition=Available --timeout=5m
kubectl get crd | grep gateway.networking.k8s.io

cat <<'EOF' | kubectl apply -f -
apiVersion: gateway.networking.k8s.io/v1
kind: GatewayClass
metadata: { name: eg }
spec: { controllerName: gateway.envoyproxy.io/gatewayclass-controller }
---
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata: { name: lab-gw, namespace: ing-lab }
spec:
  gatewayClassName: eg
  listeners:
    - { name: http, protocol: HTTP, port: 80 }
---
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: { name: split, namespace: ing-lab }
spec:
  parentRefs: [{ name: lab-gw }]
  hostnames: ["split.local"]
  rules:
    - backendRefs:
        - { name: app1, port: 80, weight: 80 }
        - { name: app2, port: 80, weight: 20 }
EOF
kubectl -n ing-lab get gateway lab-gw          # PROGRAMMED True, ADDRESS from MetalLB
kubectl -n ing-lab describe httproute split    # Status: Accepted, ResolvedRefs
GW_IP=$(kubectl -n ing-lab get gateway lab-gw -o jsonpath='{.status.addresses[0].value}')
for i in $(seq 1 20); do curl -s -H "Host: split.local" http://$GW_IP/hostname; echo; done | sort | uniq -c   # ~16 app1 / ~4 app2
kubectl -n envoy-gateway-system get pods,svc   # Envoy proxy Deployment + LoadBalancer Service created for the Gateway
```

No LoadBalancer? `kubectl -n envoy-gateway-system port-forward svc/<envoy-svc-name> 8888:80` then curl `localhost:8888`.

Cleanup: `kubectl delete ns ing-lab; helm -n traefik uninstall traefik; helm -n envoy-gateway-system uninstall eg`.

---

## 7. External traffic flow in the cloud (EKS example)

```text
 client → Route 53 (shop.example.com ALIAS) → AWS NLB/ALB (created by AWS Load Balancer Controller)
        → target type "ip": directly to Gateway/Ingress controller Pod IPs (VPC CNI)   [no NodePort hop]
        → controller Pod → app Pod IPs
 Client IP: NLB preserves it (IP targets with client IP preservation / proxy protocol); ALB adds X-Forwarded-For.
```

With **AWS ALB** you can skip an in-cluster proxy entirely: the AWS Load Balancer Controller turns `Ingress` objects
(class `alb`) — and Gateway API in newer versions — directly into ALB rules.

---

## 8. Common problems

| Symptom | Cause | Check |
|---------|-------|-------|
| 404 from controller for every request | Host header mismatch, wrong `ingressClassName`, Route not attached | `describe ingress`, HTTPRoute `status.parents` |
| 503 / "no healthy upstream" | Service has no ready endpoints / wrong port | `kubectl get endpointslices` |
| Ingress has no ADDRESS | controller not installed, LB pending | controller Pods/Service |
| TLS shows default/fake certificate | Secret missing/wrong namespace, SNI mismatch | `openssl s_client -servername` |
| Client IP is a node IP | SNAT on NodePort hop | `externalTrafficPolicy: Local`, proxy protocol, `X-Forwarded-For` |
| Large uploads fail (413) | proxy body size limits | controller-specific settings |
| WebSockets/gRPC break | timeouts/HTTP2 settings | `appProtocol`, GRPCRoute, timeouts |
| HTTPRoute `Accepted: False NotAllowedByListeners` | namespace not allowed by Gateway `allowedRoutes` | adjust Gateway |

---

## Interview questions

1. **Ingress vs Service?** Service is L4 discovery/LB; Ingress is L7 HTTP routing rules implemented by a controller.
2. **What is an Ingress controller?** A proxy deployment that watches Ingress objects and configures itself.
3. **Why is Gateway API replacing Ingress?** Role-oriented, expressive (headers, weights, gRPC/TCP), portable without
   annotations, conformance-tested.
4. **Gateway API resources?** GatewayClass, Gateway, HTTPRoute/GRPCRoute/TLSRoute…, ReferenceGrant.
5. **Host vs path routing?** Route on the `Host` header (virtual hosts) vs on the URL path prefix.
6. **TLS termination vs passthrough?** Proxy decrypts vs forwards encrypted traffic by SNI.
7. **How are certs renewed automatically?** cert-manager with an ACME issuer (HTTP-01/DNS-01).
8. **Does the controller send traffic to the ClusterIP?** Most send directly to Pod IPs from EndpointSlices.
9. **What happened to ingress-nginx?** Retired by SIG Network (maintenance ended March 2026); migrate to Gateway API or
   another maintained controller.
10. **How do you do a canary at the edge?** Weighted `backendRefs` in an HTTPRoute (or header-based match).

**Scenario:** "Our Ingress returns 503 after deploy." → New Pods not Ready or Service selector/port changed; check endpoints
and controller logs.

**Follow-ups:** How does SNI-based routing work? What is ReferenceGrant protecting against? How do you preserve client IP
through an NLB (proxy protocol v2)?
