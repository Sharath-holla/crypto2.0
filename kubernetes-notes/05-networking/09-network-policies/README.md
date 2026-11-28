# 05.09 — Network Policies & Network Security

## 1. The default: everything can talk to everything

Out of the box, any Pod can connect to any Pod in any namespace, and to the internet. One compromised Pod can scan and
attack the whole cluster (databases, the metrics endpoint of other apps, cloud metadata). **NetworkPolicy** is the built-in
L3/L4 firewall for Pods.

> **NetworkPolicy is enforced by the CNI plugin.** The API server happily stores policies even when nothing enforces them.
> Flannel alone ignores them. Calico, Cilium, Antrea, kube-router, AWS VPC CNI (network policy agent), Azure NPM/Cilium,
> GKE Dataplane V2 enforce them.

---

## 2. How policy evaluation works

1. A policy **selects Pods** (`podSelector`) in **its namespace**. `{}` = all Pods in the namespace.
2. `policyTypes` says which directions it governs: `Ingress`, `Egress`, or both.
3. A Pod selected by **at least one** policy for a direction becomes **isolated** for that direction: only traffic
   **explicitly allowed** by some policy is permitted.
4. Pods not selected by any policy remain **fully open**.
5. Policies are **additive (union of allows)**. There is **no deny rule** and **no ordering** in the standard API.
6. For a connection A → B to work: A's egress must allow it (if A is egress-isolated) **AND** B's ingress must allow it
   (if B is ingress-isolated).
7. Reply traffic of allowed connections is allowed automatically (stateful, via conntrack).

```text
           ┌──────── egress check on A's policies ────────┐   ┌──── ingress check on B's policies ────┐
 Pod A ────┤ A egress-isolated? → must match an egress rule ├──►┤ B ingress-isolated? → must match ingress ├──► Pod B
           └───────────────────────────────────────────────┘   └───────────────────────────────────────────┘
```

### Selectors inside rules

```yaml
ingress:
  - from:
      - podSelector: { matchLabels: { app: frontend } }            # Pods in the SAME namespace as the policy
      - namespaceSelector: { matchLabels: { team: payments } }     # ALL Pods in matching namespaces
      - namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: monitoring } }
        podSelector: { matchLabels: { app: prometheus } }          # ⚠️ same list item = AND (prometheus Pods IN monitoring)
      - ipBlock:
          cidr: 10.0.0.0/16
          except: ["10.0.5.0/24"]
    ports:
      - { protocol: TCP, port: 8080 }
      - { protocol: TCP, port: 9000, endPort: 9100 }               # port range
```

> ⚠️ **The most common mistake:** `- namespaceSelector: ...` and `  podSelector: ...` in the **same** list item = AND.
> Two separate `-` items = OR. A single misplaced dash can open your database to the whole cluster.

Every namespace automatically has the label `kubernetes.io/metadata.name: <name>` — use it to select namespaces by name.

### ipBlock notes

- Meant for traffic **outside** the cluster. Pod IPs are ephemeral; don't use ipBlock for Pods.
- Traffic that was SNATed/DNATed may not show the IP you expect (e.g. LoadBalancer → NodePort SNAT hides client IP from
  ingress policies; use `externalTrafficPolicy: Local` or LB IP-mode).

---

## 3. Lab setup — cluster with an enforcing CNI

```bash
# kind with Calico (05.04 §6.1) — or Cilium. Then:
kubectl create namespace np
kubectl -n np create deployment web --image=nginx:1.27
kubectl -n np expose deployment web --port=80
kubectl -n np create deployment db --image=nginx:1.27      # pretend database on port 80
kubectl -n np expose deployment db --port=80
kubectl -n np run frontend --image=nicolaka/netshoot --labels=app=frontend -- sleep infinity
kubectl -n np run attacker --image=nicolaka/netshoot --labels=app=attacker -- sleep infinity
kubectl create namespace other
kubectl -n other run outsider --image=nicolaka/netshoot -- sleep infinity

# helper: test function
t() { kubectl -n "$1" exec "$2" -- curl -s -o /dev/null -m 3 -w "$2 -> $3: %{http_code}\n" "$3" || echo "$2 -> $3: BLOCKED"; }
t np frontend web; t np attacker db; t other outsider web.np     # all 200 — no policies yet
```

### Lab 1 — default deny all ingress and egress

```yaml
# 01-default-deny.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: np
spec:
  podSelector: {}                 # every Pod in namespace np
  policyTypes: ["Ingress", "Egress"]
  # no ingress/egress rules → nothing allowed
```

```bash
kubectl apply -f 01-default-deny.yaml
t np frontend web          # BLOCKED — even DNS fails now:
kubectl -n np exec frontend -- nslookup web   # ";; connection timed out; no servers could be reached"
```

### Lab 2 — allow DNS egress (always needed with egress deny)

```yaml
# 02-allow-dns.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: np
spec:
  podSelector: {}
  policyTypes: ["Egress"]
  egress:
    - to:
        - namespaceSelector:
            matchLabels: { kubernetes.io/metadata.name: kube-system }
          podSelector:
            matchLabels: { k8s-app: kube-dns }      # AND: CoreDNS Pods in kube-system
      ports:
        - { protocol: UDP, port: 53 }
        - { protocol: TCP, port: 53 }               # large responses / retries use TCP
```

```bash
kubectl apply -f 02-allow-dns.yaml
kubectl -n np exec frontend -- nslookup web        # resolves now
t np frontend web                                  # still BLOCKED (no app rules yet)
```

Note: policies match the **post-DNAT** destination (CoreDNS Pod IP/port 53), so select the CoreDNS Pods, not the
kube-dns ClusterIP. (NodeLocal DNSCache listens on a link-local IP on the node → needs an ipBlock rule for `169.254.20.10/32`.)

### Lab 3 — allow traffic within the namespace

```yaml
# 03-allow-same-namespace.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-same-namespace
  namespace: np
spec:
  podSelector: {}
  policyTypes: ["Ingress", "Egress"]
  ingress:
    - from:
        - podSelector: {}         # any Pod in THIS namespace
  egress:
    - to:
        - podSelector: {}
```

```bash
kubectl apply -f 03-allow-same-namespace.yaml
t np frontend web; t np attacker db             # 200 (same namespace)
t other outsider web.np                         # BLOCKED (different namespace)
kubectl -n np delete networkpolicy allow-same-namespace   # remove for the next, stricter labs
```

### Lab 4 — allow only frontend → web, and only web → db

```yaml
# 04-app-rules.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: web-allow-frontend, namespace: np }
spec:
  podSelector: { matchLabels: { app: web } }
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector: { matchLabels: { app: frontend } }
      ports: [{ protocol: TCP, port: 80 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: frontend-egress-web, namespace: np }
spec:
  podSelector: { matchLabels: { app: frontend } }
  policyTypes: ["Egress"]
  egress:
    - to:
        - podSelector: { matchLabels: { app: web } }
      ports: [{ protocol: TCP, port: 80 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: db-allow-web, namespace: np }
spec:
  podSelector: { matchLabels: { app: db } }
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector: { matchLabels: { app: web } }
      ports: [{ protocol: TCP, port: 80 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: web-egress-db, namespace: np }
spec:
  podSelector: { matchLabels: { app: web } }
  policyTypes: ["Egress"]
  egress:
    - to:
        - podSelector: { matchLabels: { app: db } }
      ports: [{ protocol: TCP, port: 80 }]
```

```bash
kubectl apply -f 04-app-rules.yaml
t np frontend web          # 200
t np frontend db           # BLOCKED (frontend egress only to web; db ingress only from web)
t np attacker web          # BLOCKED
WEB=$(kubectl -n np get pod -l app=web -o name | head -1)
kubectl -n np exec $WEB -- curl -s -o /dev/null -m 3 -w '%{http_code}\n' db   # 200
```

### Lab 5 — allow from a specific Pod in another namespace (monitoring)

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-prometheus-scrape, namespace: np }
spec:
  podSelector: {}
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - namespaceSelector:
            matchLabels: { kubernetes.io/metadata.name: monitoring }
          podSelector:
            matchLabels: { app.kubernetes.io/name: prometheus }
      ports: [{ protocol: TCP, port: 9113 }]
```

### Lab 6 — restrict outbound traffic (egress to the internet)

```yaml
# 06-egress.yaml — allow web to call only a payments API range on 443, plus nothing else outside
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: web-egress-external, namespace: np }
spec:
  podSelector: { matchLabels: { app: web } }
  policyTypes: ["Egress"]
  egress:
    - to:
        - ipBlock:
            cidr: 203.0.113.0/24          # partner API (example range)
      ports: [{ protocol: TCP, port: 443 }]
    - to:
        - ipBlock:
            cidr: 0.0.0.0/0
            except:
              - 169.254.169.254/32         # never allow cloud metadata (credential theft)
              - 10.0.0.0/8
              - 172.16.0.0/12
              - 192.168.0.0/16
      ports: [{ protocol: TCP, port: 443 }]   # remove this whole rule for strict allow-listing
```

```bash
kubectl apply -f 06-egress.yaml
kubectl -n np exec $WEB -- curl -s -o /dev/null -m 5 -w '%{http_code}\n' https://kubernetes.io   # allowed (443 public)
kubectl -n np exec $WEB -- curl -s -m 3 http://169.254.169.254/ || echo "metadata BLOCKED"
```

FQDN-based egress (`api.stripe.com` rather than IPs) is **not** in the standard API — use Cilium `toFQDNs`, Calico
DNS policies, or an egress proxy/gateway.

Cleanup: `kubectl delete ns np other`.

---

## 4. Debugging policies

```bash
kubectl get networkpolicy -A
kubectl describe networkpolicy -n np web-allow-frontend      # human-readable: "Allowing ingress traffic: From PodSelector app=frontend"
kubectl get pods -n np --show-labels                         # do labels really match?
kubectl get ns --show-labels                                 # namespace labels for namespaceSelector
# Calico:
kubectl get networkpolicies.projectcalico.org -A; calicoctl get networkpolicy -o yaml
# Cilium: see drops with reasons
hubble observe --namespace np --verdict DROPPED
kubectl -n kube-system exec ds/cilium -- cilium-dbg policy get
```

Systematic approach: (1) is the CNI enforcing? (2) list policies selecting the **source** Pod (egress) and the
**destination** Pod (ingress); (3) check labels/namespace labels; (4) check ports are the **Pod's** ports, not Service ports;
(5) DNS allowed?

---

## 5. Limitations of standard NetworkPolicy

| Limitation | Workaround |
|-----------|-----------|
| No explicit deny / priority | Calico GlobalNetworkPolicy, Cilium CiliumClusterwideNetworkPolicy, **AdminNetworkPolicy / BaselineAdminNetworkPolicy** (SIG Network API for cluster admins) |
| No L7 (HTTP path/method) | Cilium L7 policy, Istio AuthorizationPolicy |
| No FQDN egress | Cilium/Calico DNS policies, egress gateway |
| No node/host traffic rules | Calico HostEndpoints, Cilium host policies |
| No logging in the API | CNI flow logs (Hubble, Calico) |
| hostNetwork Pods usually not covered | avoid hostNetwork |

---

## 6. Production network security scenarios

1. **Multi-tenant cluster:** default-deny per namespace (applied by a policy engine like Kyverno on namespace creation) +
   allow DNS + allow same namespace + explicit cross-namespace allows. Admin-level baseline policies ensure tenants can't
   remove the deny.
2. **PCI database:** DB ingress only from the payments API on 5432; payments egress only to DB + specific PSP IPs; deny
   metadata; mTLS via mesh for encryption in transit.
3. **Ransomware/lateral movement containment:** egress default-deny limits a compromised Pod's ability to scan or exfiltrate.
4. **Monitoring:** allow Prometheus namespace to scrape metrics ports cluster-wide.
5. **Ingress controller:** app namespaces allow ingress only from the gateway namespace on app ports.

Layers of network security: cloud security groups/NACLs (node level) → NetworkPolicy (Pod L3/L4) → mesh AuthorizationPolicy
(L7 + identity) → app authn/authz.

---

## Interview questions

1. **What is a NetworkPolicy?** A namespaced resource defining allowed ingress/egress traffic for selected Pods (L3/L4).
2. **Who enforces it?** The CNI plugin; without a supporting CNI it has no effect.
3. **What makes a Pod isolated?** Being selected by any policy with that policyType.
4. **How do multiple policies combine?** Union of allow rules; no deny, no order.
5. **AND vs OR in `from`?** Same list item = AND; separate items = OR.
6. **Why does DNS break after a default-deny egress policy?** Egress to CoreDNS on UDP/TCP 53 isn't allowed — add it.
7. **How do you allow traffic from another namespace?** `namespaceSelector` (optionally combined with `podSelector`).
8. **Can you write deny rules?** Not in NetworkPolicy; use AdminNetworkPolicy or CNI-specific policies.
9. **Should you use ipBlock for Pods?** No — Pod IPs change; use selectors. ipBlock is for external CIDRs.
10. **Do policies use Service ports or Pod ports?** Pod (target) ports — policies apply after DNAT.

**Scenario:** "We applied policies but traffic still flows." → CNI doesn't enforce (Flannel), or a broader policy allows it,
or the Pod uses hostNetwork.

**Follow-ups:** How does Cilium's identity-based enforcement differ from IP-based iptables enforcement? How would you roll out
default-deny without an outage (audit/log mode, Hubble flow analysis, staged policies)?
