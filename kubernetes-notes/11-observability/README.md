# 11 — Observability

## 1. The three (four) pillars

| Signal | Question it answers | Tools |
|--------|--------------------|-------|
| **Metrics** | "Is something wrong? How much?" (numbers over time) | Prometheus, Grafana, Alertmanager, metrics-server |
| **Logs** | "What exactly happened?" (events/text) | Fluent Bit, Grafana Alloy, Loki, Elasticsearch/OpenSearch |
| **Traces** | "Where did the time go across services?" | OpenTelemetry, Tempo, Jaeger |
| Events/profiles | K8s events, continuous profiling | `kubectl get events`, event exporters, Pyroscope |

```text
            Apps (OTel SDK / /metrics) ── Nodes (node-exporter) ── kubelet/cAdvisor ── kube-state-metrics ── control plane
                 │ metrics (pull)                 │ logs (stdout → /var/log/pods)         │ traces (OTLP push)
                 ▼                                ▼                                        ▼
            Prometheus ──alerts──► Alertmanager → Slack/PagerDuty         Fluent Bit / Alloy → Loki      OTel Collector → Tempo/Jaeger
                 └────────────────────────────── Grafana (dashboards + explore + correlations) ───────────────────────┘
```

## 2. Built-in views

```bash
kubectl top nodes; kubectl top pods -A               # needs metrics-server (chapter 09)
kubectl get events -A --sort-by=.lastTimestamp
kubectl logs deploy/web --all-containers --since=10m --timestamps
kubectl logs -l app=web --prefix --max-log-requests=10 -f
kubectl describe node <node> | grep -A8 Conditions
kubectl get --raw /metrics | head                    # API server metrics
kubectl get --raw "/api/v1/nodes/<node>/proxy/metrics/cadvisor" | head   # container metrics from kubelet
```

### Web UIs

> ⚠️ The **`kubernetes/dashboard`** project has been **archived** and is no longer maintained. SIG UI recommends **Headlamp**.
> Other options: k9s (terminal), Lens/Freelens, cloud consoles.

```bash
helm repo add headlamp https://kubernetes-sigs.github.io/headlamp/ && helm repo update
helm install headlamp headlamp/headlamp -n kube-system
kubectl -n kube-system create token headlamp --duration=1h     # login token (the chart's SA; scope RBAC appropriately)
kubectl -n kube-system port-forward svc/headlamp 8080:80       # open http://localhost:8080
```

## 3. Metrics sources

| Component | Metrics | Example |
|-----------|---------|---------|
| **node-exporter** (DaemonSet) | node CPU, memory, disk, network, filesystem | `node_cpu_seconds_total`, `node_filesystem_avail_bytes` |
| **cAdvisor** (in kubelet) | per-container usage | `container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`, `container_cpu_cfs_throttled_periods_total` |
| **kube-state-metrics** | object state from the API | `kube_pod_status_phase`, `kube_deployment_status_replicas_available`, `kube_pod_container_status_restarts_total` |
| Control plane | API latency, etcd, scheduler | `apiserver_request_duration_seconds`, `etcd_disk_wal_fsync_duration_seconds` |
| Applications | business + RED metrics | `http_requests_total`, `http_request_duration_seconds` |

**RED** (services): Rate, Errors, Duration. **USE** (resources): Utilisation, Saturation, Errors.

## 4. Prometheus + Grafana + Alertmanager (kube-prometheus-stack)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts && helm repo update
helm install kps prometheus-community/kube-prometheus-stack -n monitoring --create-namespace \
  --set grafana.adminPassword='change-me-lab' \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false
kubectl -n monitoring get pods
kubectl -n monitoring port-forward svc/kps-grafana 3000:80 &              # http://localhost:3000  admin / change-me-lab
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9090 &   # http://localhost:9090
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-alertmanager 9093 &
```

(Service names include the release name; check `kubectl -n monitoring get svc`.)

The two `...NilUsesHelmValues=false` flags make Prometheus pick up **all** ServiceMonitors/PodMonitors, not only ones labelled
with the release — otherwise your app monitors are silently ignored (classic gotcha).

What you get: Prometheus Operator (CRDs: `Prometheus`, `ServiceMonitor`, `PodMonitor`, `PrometheusRule`, `Alertmanager`),
node-exporter, kube-state-metrics, ~30 Grafana dashboards ("Kubernetes / Compute Resources / Namespace (Pods)"…), and default
alert rules.

### Scrape your app with a ServiceMonitor

```yaml
apiVersion: v1
kind: Service
metadata:
  name: web
  labels: { app: web }
spec:
  selector: { app: web }
  ports:
    - { name: metrics, port: 9113, targetPort: 9113 }
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata: { name: web }
spec:
  selector:
    matchLabels: { app: web }           # selects the Service
  endpoints:
    - port: metrics                     # Service port NAME
      interval: 30s
      path: /metrics
```

Check **Status → Targets** in Prometheus: target `UP`.

### PromQL you'll use daily

```promql
# CPU cores used per Pod in a namespace
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="shop", container!=""}[5m]))
# Memory working set vs limit (%)
100 * sum by (pod) (container_memory_working_set_bytes{namespace="shop", container!=""})
    / sum by (pod) (kube_pod_container_resource_limits{namespace="shop", resource="memory"})
# Restarting containers
increase(kube_pod_container_status_restarts_total[1h]) > 3
# HTTP error ratio
sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
# p95 latency from a histogram
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))
# CPU throttling ratio
sum by (pod) (rate(container_cpu_cfs_throttled_periods_total[5m])) / sum by (pod) (rate(container_cpu_cfs_periods_total[5m]))
# Node disk will fill within 4h
predict_linear(node_filesystem_avail_bytes{fstype!~"tmpfs"}[6h], 4*3600) < 0
```

### Alert rule

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata: { name: web-alerts }
spec:
  groups:
    - name: web
      rules:
        - alert: WebHighErrorRate
          expr: |
            sum(rate(http_requests_total{app="web",code=~"5.."}[5m]))
              / sum(rate(http_requests_total{app="web"}[5m])) > 0.05
          for: 10m                                # must be true for 10 min (avoid noise)
          labels: { severity: page }
          annotations:
            summary: "web 5xx > 5% for 10m"
            runbook_url: https://runbooks.example.com/web-errors
```

### Alertmanager routing (values snippet)

```yaml
alertmanager:
  config:
    route:
      receiver: default
      group_by: ["alertname", "namespace"]
      routes:
        - matchers: ['severity="page"']
          receiver: pagerduty
    receivers:
      - name: default
        slack_configs:
          - api_url_file: /etc/alertmanager/secrets/slack/url    # mount from a Secret, never inline
            channel: "#alerts"
      - name: pagerduty
        pagerduty_configs:
          - routing_key_file: /etc/alertmanager/secrets/pd/key
```

Alertmanager handles grouping, deduplication, silences and inhibition (e.g. suppress Pod alerts when the node is down).

Production: remote-write to long-term storage (Thanos, Mimir, Amazon Managed Prometheus), retention/cardinality limits, HA pairs.

## 5. Logging

Containers log to **stdout/stderr** → container runtime writes to `/var/log/pods/<ns>_<pod>_<uid>/<container>/0.log` (kubelet
rotates at 10 MiB by default). A **node agent** (DaemonSet) tails these files, enriches with Kubernetes metadata, and ships them.

> ⚠️ Promtail is end-of-life — use **Grafana Alloy**, **Fluent Bit**, or the **OpenTelemetry Collector**.

### Loki (single-binary lab) + Fluent Bit

`loki-values.yaml`:

```yaml
deploymentMode: SingleBinary
loki:
  auth_enabled: false
  commonConfig: { replication_factor: 1 }
  storage: { type: filesystem }
  schemaConfig:
    configs:
      - from: "2024-04-01"
        store: tsdb
        object_store: filesystem
        schema: v13
        index: { prefix: loki_index_, period: 24h }
singleBinary: { replicas: 1 }
backend: { replicas: 0 }
read: { replicas: 0 }
write: { replicas: 0 }
chunksCache: { enabled: false }
resultsCache: { enabled: false }
```

```bash
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add fluent https://fluent.github.io/helm-charts && helm repo update
helm install loki grafana/loki -n monitoring -f loki-values.yaml
```

`fluent-bit-values.yaml`:

```yaml
config:
  outputs: |
    [OUTPUT]
        Name        loki
        Match       kube.*
        Host        loki-gateway.monitoring.svc.cluster.local
        Port        80
        Labels      job=fluent-bit
        Label_keys  $kubernetes['namespace_name'],$kubernetes['pod_name'],$kubernetes['container_name']
        Auto_kubernetes_labels off
```

```bash
helm install fluent-bit fluent/fluent-bit -n monitoring -f fluent-bit-values.yaml
kubectl -n monitoring logs ds/fluent-bit | tail
```

In Grafana: **Connections → Data sources → Loki**, URL `http://loki-gateway.monitoring.svc.cluster.local`. Explore with LogQL:

```logql
{namespace_name="shop"} |= "error"
sum by (pod_name) (rate({namespace_name="shop"} |= "timeout" [5m]))
{container_name="api"} | json | status >= 500 | line_format "{{.method}} {{.path}} {{.status}}"
```

Best practices: structured JSON logs, include trace IDs, don't log secrets/PII, keep label cardinality low in Loki (no user IDs
as labels).

## 6. OpenTelemetry and distributed tracing

**OpenTelemetry (OTel)** = vendor-neutral APIs/SDKs + **Collector** for metrics, logs and traces (OTLP protocol, gRPC 4317 /
HTTP 4318). A **trace** is a tree of **spans**; context propagates via the W3C `traceparent` header.

```text
 frontend span ──► api span ──► db span            (same trace_id, parent/child span_ids)
 SDK in each app → OTLP → OTel Collector (receivers → processors: batch, k8sattributes → exporters) → Tempo/Jaeger
```

```bash
helm install tempo grafana/tempo -n monitoring                                  # trace backend (lab)
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts && helm repo update
helm install otel-collector open-telemetry/opentelemetry-collector -n monitoring -f otel-values.yaml
```

`otel-values.yaml`:

```yaml
mode: deployment
image:
  repository: otel/opentelemetry-collector-k8s
config:
  receivers:
    otlp:
      protocols:
        grpc: { endpoint: 0.0.0.0:4317 }
        http: { endpoint: 0.0.0.0:4318 }
  processors:
    batch: {}
  exporters:
    otlp/tempo:
      endpoint: tempo.monitoring.svc.cluster.local:4317
      tls: { insecure: true }            # lab only
  service:
    pipelines:
      traces:
        receivers: [otlp]
        processors: [batch]
        exporters: [otlp/tempo]
```

Apps set `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector-opentelemetry-collector.monitoring:4317` and
`OTEL_SERVICE_NAME=api`. The **OpenTelemetry Operator** can auto-instrument Java/Python/Node/.NET/Go Pods via an annotation
(`instrumentation.opentelemetry.io/inject-python: "true"`). Add Tempo as a Grafana data source and link logs ↔ traces by trace ID.

## 7. Application metrics

Expose `/metrics` with a Prometheus client library (or OTel metrics → Collector → Prometheus remote write). Instrument:
request count by route/status, latency histograms, queue depth, business KPIs. Avoid high-cardinality labels (user IDs, full URLs).

## 8. Troubleshooting observability

| Problem | Check |
|---------|-------|
| Target missing in Prometheus | ServiceMonitor selector matches Service labels? port **name** correct? namespaceSelector? Prometheus `serviceMonitorSelector` |
| Target DOWN | NetworkPolicy blocking scrape, wrong path/port, TLS |
| Grafana "No data" | data source URL, time range, metric/label names |
| Prometheus OOM | cardinality explosion → `topk(10, count by (__name__)({__name__=~".+"}))` |
| No logs in Loki | Fluent Bit errors (`kubectl logs ds/fluent-bit`), output host, parser, Loki rejects (rate limits, old timestamps) |
| Broken traces | missing context propagation, sampling, Collector pipeline exporters |
| `kubectl top` errors | metrics-server Pod/APIService (`kubectl get apiservice v1beta1.metrics.k8s.io`) |

---

## Interview questions

1. **Metrics vs logs vs traces?** Aggregated numbers over time / detailed events / request paths across services.
2. **What does kube-state-metrics provide vs cAdvisor?** Object state from the API vs container resource usage.
3. **What is a ServiceMonitor?** Prometheus Operator CRD telling Prometheus which Services/ports to scrape.
4. **How do container logs get collected?** stdout → node log files → DaemonSet agent tails/enriches → backend.
5. **Why is metrics-server not a monitoring solution?** In-memory, short-term, resource metrics only — for autoscaling/top.
6. **What is Alertmanager for?** Routing, grouping, deduplicating and silencing alerts.
7. **RED vs USE?** Service-level (Rate, Errors, Duration) vs resource-level (Utilisation, Saturation, Errors).
8. **What is OpenTelemetry?** Vendor-neutral standard and tooling for telemetry with the OTLP protocol and Collector.
9. **What breaks distributed traces?** Not propagating trace context headers between services.
10. **What is cardinality and why does it matter?** Number of unique label combinations; too high exhausts Prometheus/Loki memory.

**Scenario:** Pods restart but nobody noticed for a day. → Add alerts on `kube_pod_container_status_restarts_total`, OOMKilled
reasons, and SLO-based error/latency alerts routed to on-call.

**Follow-ups:** How would you scale Prometheus for 50 clusters (Thanos/Mimir, remote write)? Pull vs push trade-offs? Tail-based
vs head-based sampling?
