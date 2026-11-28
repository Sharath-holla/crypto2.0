# 16 — Kubernetes Projects (Beginner → Production)

Each project builds on the previous chapters. Do them in order, type the files yourself, and keep everything in a Git repo
(`k8s-projects/`). Projects 1–3 run on **kind** locally; project 4 runs on **EKS** (costs money — clean up).

| # | Level | You practise |
|---|-------|--------------|
| 1 | Beginner | Pods, Deployments, Services, ConfigMaps, probes |
| 2 | Intermediate | building an image, StatefulSet + PVC, Secrets, Jobs, Ingress |
| 3 | Advanced | three tiers, NetworkPolicies, resource limits, HPA, Prometheus monitoring |
| 4 | Production | Helm, GitHub Actions → ECR, Argo CD, EKS, ALB + TLS, Karpenter/HPA, observability, security policies |

---

## Project 1 — Nginx with Pods, Services and ConfigMaps (beginner)

### Architecture

```text
 laptop ── kubectl port-forward / NodePort 30080 ──► Service web (NodePort)
                                                        │ selector app=web
                                         ┌──────────────┼──────────────┐
                                     Pod web-1       Pod web-2       Pod web-3
                                     nginx:1.27  ← ConfigMap "web-content" (index.html) + "web-nginx-conf" (default.conf)
```

### Steps

```bash
kind create cluster --name p1
kubectl create namespace p1 && kubectl config set-context --current --namespace=p1
mkdir -p ~/k8s-projects/p1 && cd ~/k8s-projects/p1
```

`01-configmaps.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: web-content }
data:
  index.html: |
    <!doctype html>
    <html><body>
      <h1>Project 1 — served by Kubernetes</h1>
      <p>Pod: <!--# echo var="hostname" --></p>
    </body></html>
---
apiVersion: v1
kind: ConfigMap
metadata: { name: web-nginx-conf }
data:
  default.conf: |
    server {
      listen 80;
      ssi on;                                  # lets index.html print the Pod hostname ($hostname is built in)
      location / { root /usr/share/nginx/html; index index.html; }
      location /healthz { access_log off; return 200 "ok\n"; }
    }
```

`02-deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  labels: { app: web }
spec:
  replicas: 3
  selector: { matchLabels: { app: web } }
  template:
    metadata:
      labels: { app: web }
    spec:
      containers:
        - name: nginx
          image: nginx:1.27
          ports: [{ name: http, containerPort: 80 }]
          readinessProbe: { httpGet: { path: /healthz, port: http }, periodSeconds: 5 }
          livenessProbe:  { httpGet: { path: /healthz, port: http }, initialDelaySeconds: 5, periodSeconds: 10 }
          resources:
            requests: { cpu: 50m, memory: 32Mi }
            limits: { memory: 64Mi }
          volumeMounts:
            - { name: content, mountPath: /usr/share/nginx/html }
            - { name: conf, mountPath: /etc/nginx/conf.d }
      volumes:
        - name: content
          configMap: { name: web-content }
        - name: conf
          configMap: { name: web-nginx-conf }
```

`03-service.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata: { name: web }
spec:
  type: NodePort
  selector: { app: web }
  ports:
    - { name: http, port: 80, targetPort: http, nodePort: 30080 }
```

```bash
kubectl apply -f .
kubectl get all
kubectl get endpointslices -l kubernetes.io/service-name=web
kubectl port-forward svc/web 8080:80 &
for i in 1 2 3 4 5; do curl -s localhost:8080 | grep Pod; done      # different Pod names (new connection each time)
NODE_IP=$(kubectl get node p1-control-plane -o jsonpath='{.status.addresses[0].address}')
curl -s http://$NODE_IP:30080/healthz                                 # NodePort works from the host (kind on Linux)
```

### Exercises

1. Change `index.html` in the ConfigMap; wait ~1 min; reload (volume updates live).
2. `kubectl rollout restart deploy/web` and watch zero-downtime replacement with `kubectl get pods -w`.
3. Delete a Pod; watch the ReplicaSet replace it.
4. Break the readiness path (`/healthz-bad`), apply, observe the rollout stall and the Service keep old Pods; `rollout undo`.
5. Scale to 5; check EndpointSlices.

Cleanup: `kind delete cluster --name p1`.

---

## Project 2 — Django + PostgreSQL with PVC, Secrets and Ingress (intermediate)

### Architecture

```text
 browser ─► localhost:80 ─► kind node :30080 ─► Traefik (Ingress controller) ─host: django.local─► Service django:80
                                                                                                 │
                                                                    Deployment django (2 replicas, gunicorn :8000)
                                                                     │ env from ConfigMap + Secret
                                                                     ▼
                                       Service postgres (headless) ─► StatefulSet postgres-0 ─► PVC data-postgres-0 (local-path)
                                       Job django-migrate (runs `manage.py migrate` before/at deploy)
```

### 2.1 Cluster

Use the kind config from chapter 03 §4.3 (host ports 80/443 → node 30080/30443), name it `p2`:

```bash
# kind-multinode.yaml is in 03-cluster-setup/ of these notes — adjust the path
sed 's/^name: lab/name: p2/' ../03-cluster-setup/kind-multinode.yaml > kind-p2.yaml
kind create cluster --config kind-p2.yaml
helm repo add traefik https://traefik.github.io/charts && helm repo update
helm install traefik traefik/traefik -n traefik --create-namespace \
  --set service.type=NodePort --set ports.web.nodePort=30080 --set ports.websecure.nodePort=30443
kubectl create namespace p2 && kubectl config set-context --current --namespace=p2
```

### 2.2 The Django application

```text
p2/app/
├── Dockerfile
├── requirements.txt
├── manage.py
├── mysite/{__init__.py, settings.py, urls.py, wsgi.py}
└── visits/{__init__.py, models.py, views.py, migrations/{__init__.py, 0001_initial.py}}
```

```bash
mkdir -p ~/k8s-projects/p2/app/{mysite,visits/migrations} && cd ~/k8s-projects/p2/app
touch mysite/__init__.py visits/__init__.py visits/migrations/__init__.py
```

`requirements.txt`:

```text
Django>=5.2,<5.3
gunicorn>=23,<24
psycopg[binary]>=3.2,<4
```

`manage.py`:

```python
#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)
```

`mysite/settings.py` — all configuration comes from the environment (12-factor):

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]                    # from a Secret — fail fast if missing
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",")

INSTALLED_APPS = ["visits"]
MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "mysite.urls"
WSGI_APPLICATION = "mysite.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ["POSTGRES_DB"],
        "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"],
        "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGGING = {"version": 1, "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")}}
```

`mysite/urls.py`:

```python
from django.urls import path
from visits import views

urlpatterns = [
    path("", views.index),
    path("healthz", views.healthz),   # liveness: process is up
    path("readyz", views.readyz),     # readiness: DB reachable
]
```

`mysite/wsgi.py`:

```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
application = get_wsgi_application()
```

`visits/models.py`:

```python
from django.db import models


class Visit(models.Model):
    created = models.DateTimeField(auto_now_add=True)
```

`visits/migrations/0001_initial.py`:

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="Visit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
```

`visits/views.py`:

```python
import socket

from django.db import connection
from django.http import HttpResponse, JsonResponse

from .models import Visit


def index(request):
    Visit.objects.create()
    return JsonResponse({"visits": Visit.objects.count(), "served_by": socket.gethostname()})


def healthz(request):
    return HttpResponse("ok")


def readyz(request):
    with connection.cursor() as cur:
        cur.execute("SELECT 1")
    return HttpResponse("ready")
```

`Dockerfile`:

```dockerfile
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --uid 10001 --no-create-home --system app
USER 10001
EXPOSE 8000
# exec form → gunicorn is PID 1 and receives SIGTERM for graceful shutdown
CMD ["gunicorn", "mysite.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "--graceful-timeout", "20"]
```

```bash
docker build -t django-visits:0.1.0 .
kind load docker-image django-visits:0.1.0 --name p2
```

### 2.3 Kubernetes manifests (`~/k8s-projects/p2/k8s/`)

`00-secret.yaml` — generated, **not committed to Git**:

```bash
mkdir -p ../k8s && cd ../k8s
kubectl create secret generic django-secrets \
  --from-literal=DJANGO_SECRET_KEY="$(openssl rand -base64 48)" \
  --from-literal=POSTGRES_PASSWORD="$(openssl rand -base64 24)" \
  --dry-run=client -o yaml > 00-secret.yaml
echo "00-secret.yaml" >> .gitignore
```

`01-configmap.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: django-config }
data:
  POSTGRES_DB: visits
  POSTGRES_USER: django
  POSTGRES_HOST: postgres
  DJANGO_ALLOWED_HOSTS: "django.local,localhost"
  LOG_LEVEL: INFO
```

`02-postgres.yaml`:

```yaml
apiVersion: v1
kind: Service
metadata: { name: postgres }
spec:
  clusterIP: None                   # headless: stable DNS for the StatefulSet
  selector: { app: postgres }
  ports: [{ name: pg, port: 5432 }]
---
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: postgres }
spec:
  serviceName: postgres
  replicas: 1
  selector: { matchLabels: { app: postgres } }
  template:
    metadata: { labels: { app: postgres } }
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: postgres
          image: postgres:17
          ports: [{ name: pg, containerPort: 5432 }]
          env:
            - name: POSTGRES_DB
              valueFrom: { configMapKeyRef: { name: django-config, key: POSTGRES_DB } }
            - name: POSTGRES_USER
              valueFrom: { configMapKeyRef: { name: django-config, key: POSTGRES_USER } }
            - name: POSTGRES_PASSWORD
              valueFrom: { secretKeyRef: { name: django-secrets, key: POSTGRES_PASSWORD } }
            - name: PGDATA
              value: /var/lib/postgresql/data/pgdata      # subdirectory: the mount root contains lost+found on some disks
          readinessProbe:
            exec: { command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\""] }
            periodSeconds: 5
          resources:
            requests: { cpu: 100m, memory: 256Mi }
            limits: { memory: 512Mi }
          volumeMounts:
            - { name: data, mountPath: /var/lib/postgresql/data }
  volumeClaimTemplates:
    - metadata: { name: data }
      spec:
        accessModes: ["ReadWriteOnce"]
        resources: { requests: { storage: 1Gi } }
```

`03-migrate-job.yaml`:

```yaml
apiVersion: batch/v1
kind: Job
metadata: { name: django-migrate }
spec:
  backoffLimit: 6                   # retries while Postgres is still starting
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: migrate
          image: django-visits:0.1.0
          command: ["python", "manage.py", "migrate", "--noinput"]
          envFrom:
            - configMapRef: { name: django-config }
            - secretRef: { name: django-secrets }
```

`04-django.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: django }
spec:
  replicas: 2
  selector: { matchLabels: { app: django } }
  template:
    metadata: { labels: { app: django } }
    spec:
      securityContext: { runAsNonRoot: true, seccompProfile: { type: RuntimeDefault } }
      containers:
        - name: django
          image: django-visits:0.1.0
          imagePullPolicy: IfNotPresent
          ports: [{ name: http, containerPort: 8000 }]
          envFrom:
            - configMapRef: { name: django-config }
            - secretRef: { name: django-secrets }
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
              httpHeaders: [{ name: Host, value: localhost }]   # must be in ALLOWED_HOSTS
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
              httpHeaders: [{ name: Host, value: localhost }]
            initialDelaySeconds: 10
          lifecycle:
            preStop: { sleep: { seconds: 5 } }
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits: { memory: 256Mi }
---
apiVersion: v1
kind: Service
metadata: { name: django }
spec:
  selector: { app: django }
  ports: [{ name: http, port: 80, targetPort: http }]
```

`05-ingress.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata: { name: django }
spec:
  ingressClassName: traefik
  rules:
    - host: django.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend: { service: { name: django, port: { name: http } } }
```

### 2.4 Deploy and verify

```bash
kubectl apply -f 00-secret.yaml -f 01-configmap.yaml -f 02-postgres.yaml
kubectl rollout status sts/postgres
kubectl apply -f 03-migrate-job.yaml && kubectl wait --for=condition=complete job/django-migrate --timeout=180s
kubectl logs job/django-migrate                    # "Applying visits.0001_initial... OK"
kubectl apply -f 04-django.yaml -f 05-ingress.yaml
kubectl rollout status deploy/django
curl -s -H "Host: django.local" http://localhost/; echo      # {"visits": 1, "served_by": "django-..."}
curl -s -H "Host: django.local" http://localhost/; echo      # visits: 2
echo "127.0.0.1 django.local" | sudo tee -a /etc/hosts      # sudo: /etc/hosts is root-owned; then open http://django.local
```

### 2.5 Prove persistence and resilience

```bash
kubectl delete pod postgres-0 && kubectl rollout status sts/postgres
curl -s -H "Host: django.local" http://localhost/; echo      # count continues — data on the PVC survived
kubectl get pvc                                             # data-postgres-0 Bound
kubectl scale deploy django --replicas=0; curl -s -o /dev/null -w '%{http_code}\n' -H "Host: django.local" http://localhost/   # 503/404 from Traefik
kubectl scale deploy django --replicas=2
```

### 2.6 Troubleshooting drill

| Break this | Expected symptom | Find it with |
|-----------|------------------|--------------|
| Wrong `POSTGRES_HOST` | django Pods 0/1 Ready (readyz fails) | `kubectl logs`, `describe pod` |
| Delete Secret | `CreateContainerConfigError` | events |
| Remove `django.local` from ALLOWED_HOSTS | HTTP 400 via Ingress | app logs `DisallowedHost` |
| PVC with non-existent StorageClass | postgres-0 Pending | `describe pvc` |

Cleanup: `kind delete cluster --name p2`.

---

## Project 3 — Three-tier app with NetworkPolicies, limits, HPA and monitoring (advanced)

### Architecture

```text
                       ┌──────────────────── namespace: shop (PSA baseline, default-deny NetworkPolicies) ────────────────────┐
 browser ─► Traefik ──►│ frontend (nginx-unprivileged, 2 replicas) ── /api/* ──► backend (Flask API, HPA 2-8) ──► postgres (STS) │
 (ns traefik)          │        ▲ allow from ns traefik:8080          allow from frontend:5000       allow from backend:5432     │
                       │                                               ▲ allow from ns monitoring:5000 (/metrics)                 │
                       └───────────────────────────────────────────────┼──────────────────────────────────────────────────────────┘
                                                                Prometheus (kube-prometheus-stack, ns monitoring) → Grafana
```

### 3.1 Cluster with an enforcing CNI

```bash
cat > kind-p3.yaml <<'EOF'
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: p3
networking:
  disableDefaultCNI: true
  podSubnet: "192.168.0.0/16"
nodes:
  - role: control-plane
    extraPortMappings:
      - { containerPort: 30080, hostPort: 80 }
  - role: worker
  - role: worker
EOF
kind create cluster --config kind-p3.yaml
helm repo add traefik https://traefik.github.io/charts
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts && helm repo update
CALICO_VERSION=v3.30.3
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/tigera-operator.yaml
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/custom-resources.yaml
kubectl wait --for=condition=Available tigerastatus/calico --timeout=300s
# Add-ons
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
kubectl -n kube-system patch deploy metrics-server --type=json -p='[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
helm install traefik traefik/traefik -n traefik --create-namespace --set service.type=NodePort --set ports.web.nodePort=30080
helm install kps prometheus-community/kube-prometheus-stack -n monitoring --create-namespace \
  --set grafana.adminPassword='change-me-lab' \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
kubectl create namespace shop
kubectl label namespace shop pod-security.kubernetes.io/enforce=baseline pod-security.kubernetes.io/warn=restricted
kubectl config set-context --current --namespace=shop
```

### 3.2 Backend API (Flask)

`p3/backend/app.py`:

```python
import os
import socket
import time

import psycopg
from flask import Flask, Response, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = Flask(__name__)
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "code"])
LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["path"])
DSN = (f"host={os.environ['DB_HOST']} dbname={os.environ['DB_NAME']} "
       f"user={os.environ['DB_USER']} password={os.environ['DB_PASSWORD']} connect_timeout=3")


def db():
    return psycopg.connect(DSN)


def init_db(retries=30):
    for _ in range(retries):
        try:
            with db() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS items (id serial PRIMARY KEY, name text NOT NULL)")
            return
        except psycopg.OperationalError:
            time.sleep(2)              # DB not ready yet — readiness probe keeps us out of rotation
    raise SystemExit("database unavailable")


@app.before_request
def start_timer():
    request.start = time.perf_counter()


@app.after_request
def record(resp):
    if request.path != "/metrics":
        LATENCY.labels(request.path).observe(time.perf_counter() - request.start)
        REQUESTS.labels(request.method, request.path, resp.status_code).inc()
    return resp


@app.get("/api/items")
def list_items():
    with db() as conn:
        rows = conn.execute("SELECT id, name FROM items ORDER BY id DESC LIMIT 50").fetchall()
    return jsonify(items=[{"id": r[0], "name": r[1]} for r in rows], served_by=socket.gethostname())


@app.post("/api/items")
def add_item():
    name = (request.get_json(silent=True) or {}).get("name", "").strip()[:100]
    if not name:
        return jsonify(error="name required"), 400
    with db() as conn:
        conn.execute("INSERT INTO items (name) VALUES (%s)", (name,))
    return jsonify(ok=True), 201


@app.get("/api/burn")
def burn():
    # CPU load generator for the HPA lab
    end = time.perf_counter() + 0.2
    while time.perf_counter() < end:
        pass
    return jsonify(ok=True)


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/readyz")
def readyz():
    with db() as conn:
        conn.execute("SELECT 1")
    return "ready"


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


init_db()
```

`p3/backend/requirements.txt`:

```text
flask>=3.1,<4
gunicorn>=23,<24
psycopg[binary]>=3.2,<4
prometheus-client>=0.22,<1
```

`p3/backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
USER 10001
EXPOSE 5000
# 1 worker + threads keeps prometheus_client metrics in a single process
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--access-logfile", "-"]
```

```bash
cd ~/k8s-projects/p3/backend && docker build -t shop-backend:0.1.0 . && kind load docker-image shop-backend:0.1.0 --name p3
```

### 3.3 Manifests (`p3/k8s/`)

`db.yaml` (Secret generated as in project 2, name `db-cred`, keys `DB_USER`, `DB_PASSWORD`):

```bash
kubectl create secret generic db-cred --from-literal=DB_USER=shop --from-literal=DB_PASSWORD="$(openssl rand -base64 24)"
```

```yaml
apiVersion: v1
kind: Service
metadata: { name: postgres, labels: { app: postgres, tier: db } }
spec:
  clusterIP: None
  selector: { app: postgres }
  ports: [{ name: pg, port: 5432 }]
---
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: postgres }
spec:
  serviceName: postgres
  replicas: 1
  selector: { matchLabels: { app: postgres } }
  template:
    metadata: { labels: { app: postgres, tier: db } }
    spec:
      containers:
        - name: postgres
          image: postgres:17
          env:
            - { name: POSTGRES_DB, value: shop }
            - name: POSTGRES_USER
              valueFrom: { secretKeyRef: { name: db-cred, key: DB_USER } }
            - name: POSTGRES_PASSWORD
              valueFrom: { secretKeyRef: { name: db-cred, key: DB_PASSWORD } }
            - { name: PGDATA, value: /var/lib/postgresql/data/pgdata }
          ports: [{ name: pg, containerPort: 5432 }]
          readinessProbe: { exec: { command: ["sh", "-c", "pg_isready -U \"$POSTGRES_USER\" -d shop"] }, periodSeconds: 5 }
          resources: { requests: { cpu: 100m, memory: 256Mi }, limits: { memory: 512Mi } }
          volumeMounts: [{ name: data, mountPath: /var/lib/postgresql/data }]
  volumeClaimTemplates:
    - metadata: { name: data }
      spec: { accessModes: ["ReadWriteOnce"], resources: { requests: { storage: 1Gi } } }
```

`backend.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: backend }
spec:
  replicas: 2
  selector: { matchLabels: { app: backend } }
  template:
    metadata: { labels: { app: backend, tier: api } }
    spec:
      automountServiceAccountToken: false
      securityContext: { runAsNonRoot: true, runAsUser: 10001, seccompProfile: { type: RuntimeDefault } }
      topologySpreadConstraints:
        - { maxSkew: 1, topologyKey: kubernetes.io/hostname, whenUnsatisfiable: ScheduleAnyway, labelSelector: { matchLabels: { app: backend } } }
      containers:
        - name: api
          image: shop-backend:0.1.0
          ports: [{ name: http, containerPort: 5000 }]
          env:
            - { name: DB_HOST, value: postgres }
            - { name: DB_NAME, value: shop }
          envFrom: [{ secretRef: { name: db-cred } }]
          readinessProbe: { httpGet: { path: /readyz, port: http }, periodSeconds: 5 }
          livenessProbe: { httpGet: { path: /healthz, port: http }, initialDelaySeconds: 10, periodSeconds: 10 }
          resources:
            requests: { cpu: 100m, memory: 128Mi }   # HPA % is relative to this request
            limits: { cpu: 500m, memory: 256Mi }
          securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
          volumeMounts: [{ name: tmp, mountPath: /tmp }]
      volumes: [{ name: tmp, emptyDir: {} }]
---
apiVersion: v1
kind: Service
metadata: { name: backend, labels: { app: backend } }
spec:
  selector: { app: backend }
  ports: [{ name: http, port: 5000, targetPort: http }]
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: backend }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: backend }
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource: { name: cpu, target: { type: Utilization, averageUtilization: 60 } }
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata: { name: backend }
spec:
  minAvailable: 1
  selector: { matchLabels: { app: backend } }
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata: { name: backend }
spec:
  selector: { matchLabels: { app: backend } }
  endpoints: [{ port: http, path: /metrics, interval: 15s }]
```

`frontend.yaml`:

```yaml
apiVersion: v1
kind: ConfigMap
metadata: { name: frontend }
data:
  default.conf: |
    server {
      listen 8080;
      location / { root /usr/share/nginx/html; index index.html; }
      location /api/ { proxy_pass http://backend:5000; proxy_set_header Host $host; }
      location /healthz { return 200 "ok\n"; }
    }
  index.html: |
    <!doctype html><html><body>
    <h1>Shop</h1>
    <input id="n" placeholder="item"><button onclick="add()">Add</button>
    <ul id="l"></ul><small id="s"></small>
    <script>
      async function load(){const r=await fetch('/api/items');const j=await r.json();
        document.getElementById('l').innerHTML=j.items.map(i=>'<li>'+i.name+'</li>').join('');
        document.getElementById('s').textContent='served by '+j.served_by;}
      async function add(){await fetch('/api/items',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({name:document.getElementById('n').value})});load();}
      load();
    </script></body></html>
---
apiVersion: apps/v1
kind: Deployment
metadata: { name: frontend }
spec:
  replicas: 2
  selector: { matchLabels: { app: frontend } }
  template:
    metadata: { labels: { app: frontend, tier: web } }
    spec:
      automountServiceAccountToken: false
      containers:
        - name: nginx
          image: nginxinc/nginx-unprivileged:1.27
          ports: [{ name: http, containerPort: 8080 }]
          readinessProbe: { httpGet: { path: /healthz, port: http } }
          resources: { requests: { cpu: 50m, memory: 32Mi }, limits: { cpu: 200m, memory: 64Mi } }
          volumeMounts:
            - { name: conf, mountPath: /etc/nginx/conf.d/default.conf, subPath: default.conf }
            - { name: conf, mountPath: /usr/share/nginx/html/index.html, subPath: index.html }
      volumes: [{ name: conf, configMap: { name: frontend } }]
---
apiVersion: v1
kind: Service
metadata: { name: frontend }
spec:
  selector: { app: frontend }
  ports: [{ name: http, port: 80, targetPort: http }]
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata: { name: shop }
spec:
  ingressClassName: traefik
  rules:
    - host: shop.local
      http:
        paths: [{ path: /, pathType: Prefix, backend: { service: { name: frontend, port: { name: http } } } }]
```

`netpol.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: default-deny }
spec:
  podSelector: {}
  policyTypes: ["Ingress", "Egress"]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: allow-dns }
spec:
  podSelector: {}
  policyTypes: ["Egress"]
  egress:
    - to:
        - namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: kube-system } }
          podSelector: { matchLabels: { k8s-app: kube-dns } }
      ports: [{ protocol: UDP, port: 53 }, { protocol: TCP, port: 53 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: frontend }
spec:
  podSelector: { matchLabels: { app: frontend } }
  policyTypes: ["Ingress", "Egress"]
  ingress:
    - from: [{ namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: traefik } } }]
      ports: [{ port: 8080 }]
  egress:
    - to: [{ podSelector: { matchLabels: { app: backend } } }]
      ports: [{ port: 5000 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: backend }
spec:
  podSelector: { matchLabels: { app: backend } }
  policyTypes: ["Ingress", "Egress"]
  ingress:
    - from: [{ podSelector: { matchLabels: { app: frontend } } }]
      ports: [{ port: 5000 }]
    - from:
        - namespaceSelector: { matchLabels: { kubernetes.io/metadata.name: monitoring } }
          podSelector: { matchLabels: { app.kubernetes.io/name: prometheus } }
      ports: [{ port: 5000 }]
  egress:
    - to: [{ podSelector: { matchLabels: { app: postgres } } }]
      ports: [{ port: 5432 }]
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata: { name: postgres }
spec:
  podSelector: { matchLabels: { app: postgres } }
  policyTypes: ["Ingress"]
  ingress:
    - from: [{ podSelector: { matchLabels: { app: backend } } }]
      ports: [{ port: 5432 }]
```

### 3.4 Deploy and verify

```bash
cd ~/k8s-projects/p3/k8s
kubectl apply -f db.yaml && kubectl rollout status sts/postgres
kubectl apply -f backend.yaml -f frontend.yaml && kubectl rollout status deploy/backend deploy/frontend
curl -s -H "Host: shop.local" -X POST -H 'Content-Type: application/json' -d '{"name":"apple"}' http://localhost/api/items
curl -s -H "Host: shop.local" http://localhost/api/items; echo
kubectl apply -f netpol.yaml
curl -s -H "Host: shop.local" http://localhost/api/items; echo          # still works through allowed paths
# Prove isolation
kubectl run probe --image=nicolaka/netshoot --restart=Never -- sleep 3600
kubectl exec probe -- nc -zvw3 postgres 5432 || echo "BLOCKED: random Pod cannot reach the DB"
FE=$(kubectl get pod -l app=frontend -o name | head -1)
kubectl exec $FE -- sh -c 'wget -qO- -T3 http://postgres:5432 || echo BLOCKED: frontend cannot reach DB'
```

### 3.5 Autoscaling test

```bash
kubectl get hpa backend -w &
kubectl run load --image=busybox:1.36 --restart=Never --labels=app=frontend -- \
  sh -c 'while true; do wget -qO- http://backend:5000/api/burn >/dev/null; done'
# label app=frontend so the NetworkPolicies allow it to reach the backend
# watch replicas climb toward 8; then:
kubectl delete pod load        # after ~5 min stabilisation, replicas return to 2
```

### 3.6 Monitoring

```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80 &
kubectl -n monitoring port-forward svc/kps-kube-prometheus-stack-prometheus 9090 &
# Prometheus → Status → Targets: serviceMonitor/shop/backend UP (NetworkPolicy allows the scrape)
```

PromQL for a Grafana dashboard:

```promql
sum by (code) (rate(http_requests_total{namespace="shop"}[1m]))                          # RPS by status code
histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{namespace="shop"}[5m])))  # p95
kube_horizontalpodautoscaler_status_current_replicas{namespace="shop"}                     # replicas
sum by (pod) (rate(container_cpu_usage_seconds_total{namespace="shop",container="api"}[1m]))
```

Add an alert (`PrometheusRule`) for 5xx ratio > 5% for 5 min (chapter 11 §4).

Cleanup: `kind delete cluster --name p3`.

---

## Project 4 — Production-style deployment on EKS (Helm, CI/CD, LB, TLS, observability, autoscaling, security)

> 💸 Uses billable AWS resources. Budget alert first; full cleanup at the end.

### Architecture

```text
 Developer ─PR─► GitHub repo "shop" (app code + Helm chart)
                   │ GitHub Actions (OIDC → IAM role, no keys): test → build → Trivy → push to ECR (immutable SHA tags)
                   │                                           → commit image tag to GitOps repo "shop-gitops" (envs/prod)
                   ▼
           GitHub repo "shop-gitops"  ◄─── Argo CD (in EKS) watches & syncs (auto-sync, self-heal, prune)
                                                │
 Internet ─► Route 53 shop.example.com ─► ALB (HTTPS 443, ACM cert, HTTP→HTTPS redirect, WAF optional)
                                                │ target-type ip (VPC CNI Pod IPs)
          ┌───────────── EKS cluster (private subnets, 3 AZs) ───────────────────────────────────────────┐
          │ ns shop (PSA restricted, default-deny NetworkPolicies)                                          │
          │   frontend Deployment ─► backend Deployment (HPA, PDB, topology spread) ─► Amazon RDS PostgreSQL │
          │   secrets from AWS Secrets Manager via External Secrets (Pod Identity)                           │
          │ ns monitoring: kube-prometheus-stack (+ Loki/Fluent Bit)   ns kube-system: AWS LB Controller,       │
          │ Karpenter (nodes, Spot + on-demand)   ns argocd: Argo CD   ns external-secrets                     │
          └─────────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Platform setup (once)

1. **Cluster**: create with eksctl as in chapter 15 §5 (3 AZs, private nodes, `authenticationMode: API`, add-ons incl. Pod Identity
   Agent, VPC CNI with network policy enabled).
2. **AWS Load Balancer Controller** (chapter 15 §5).
3. **Karpenter** (follow the official "Getting Started with Karpenter" for your version) with a NodePool allowing Spot + on-demand,
   arm64 + amd64, and `consolidationPolicy: WhenEmptyOrUnderutilized`.
4. **metrics-server**: `eksctl create addon --cluster lab --name metrics-server` (or the upstream manifest).
5. **kube-prometheus-stack** + Loki/Fluent Bit (chapter 11) or Amazon Managed Prometheus/Grafana.
6. **External Secrets Operator**:
   ```bash
   helm repo add external-secrets https://charts.external-secrets.io
   helm install external-secrets external-secrets/external-secrets -n external-secrets --create-namespace
   ```
7. **Argo CD** (chapter 14 §5).
8. **ACM certificate** for `shop.example.com` (DNS validation in Route 53) — note its ARN.
9. **RDS PostgreSQL** in private subnets (Multi-AZ for prod), security group allowing 5432 **from the node/Pod security group**;
   store credentials in Secrets Manager `prod/shop/db` (`{"username": "...", "password": "...", "host": "..."}`).
10. **ECR repository** with tag immutability and scan on push:
    ```bash
    aws ecr create-repository --repository-name shop-backend --image-tag-mutability IMMUTABLE \
      --image-scanning-configuration scanOnPush=true
    ```
11. **GitHub OIDC → IAM role** for CI: create an IAM OIDC identity provider for `token.actions.githubusercontent.com`, and a role
    `gha-shop-ecr-push` whose trust policy allows `repo:<org>/shop:ref:refs/heads/main` and whose permissions allow ECR push to
    `shop-backend` only.

### 4.2 Helm chart (`shop/chart/`) — key templates

Start with `helm create chart` and adapt (chapter 12). Values highlight:

```yaml
# chart/values.yaml
image:
  repository: 111122223333.dkr.ecr.us-east-1.amazonaws.com/shop-backend
  tag: ""                                   # set by GitOps repo per env
replicaCount: 3
resources:
  requests: { cpu: 200m, memory: 256Mi }
  limits: { memory: 512Mi }
autoscaling: { enabled: true, minReplicas: 3, maxReplicas: 20, targetCPUUtilizationPercentage: 60 }
pdb: { minAvailable: 2 }
podSecurityContext: { runAsNonRoot: true, runAsUser: 10001, seccompProfile: { type: RuntimeDefault } }
securityContext: { allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: { drop: ["ALL"] } }
ingress:
  enabled: true
  host: shop.example.com
  certificateArn: arn:aws:acm:us-east-1:111122223333:certificate/REPLACE
externalSecret:
  enabled: true
  remoteKey: prod/shop/db
serviceMonitor: { enabled: true }
networkPolicy: { enabled: true }
```

`chart/templates/ingress.yaml`:

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "shop.fullname" . }}
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP":80},{"HTTPS":443}]'
    alb.ingress.kubernetes.io/ssl-redirect: "443"
    alb.ingress.kubernetes.io/certificate-arn: {{ .Values.ingress.certificateArn | quote }}
    alb.ingress.kubernetes.io/ssl-policy: ELBSecurityPolicy-TLS13-1-2-2021-06
    alb.ingress.kubernetes.io/healthcheck-path: /readyz
    alb.ingress.kubernetes.io/group.name: public
spec:
  ingressClassName: alb
  rules:
    - host: {{ .Values.ingress.host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "shop.fullname" . }}
                port: { name: http }
{{- end }}
```

`chart/templates/externalsecret.yaml`:

```yaml
{{- if .Values.externalSecret.enabled }}
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: {{ include "shop.fullname" . }}-db
spec:
  refreshInterval: 1h
  secretStoreRef: { name: aws-secrets-manager, kind: ClusterSecretStore }
  target: { name: {{ include "shop.fullname" . }}-db }
  data:
    - { secretKey: DB_USER,     remoteRef: { key: {{ .Values.externalSecret.remoteKey }}, property: username } }
    - { secretKey: DB_PASSWORD, remoteRef: { key: {{ .Values.externalSecret.remoteKey }}, property: password } }
    - { secretKey: DB_HOST,     remoteRef: { key: {{ .Values.externalSecret.remoteKey }}, property: host } }
{{- end }}
```

The `ClusterSecretStore` (platform-owned) authenticates with a ServiceAccount that has a **Pod Identity association** to an IAM
role allowing `secretsmanager:GetSecretValue` on `prod/shop/*` only.

Also template: Deployment (with checksum annotation, probes, topology spread across zones), Service, HPA, PDB, ServiceMonitor,
NetworkPolicies (from project 3, with ingress allowed from the VPC CIDR to the backend port because ALB IP targets connect from
ALB ENIs, and egress to the RDS endpoint CIDR on 5432 plus HTTPS to AWS APIs if needed).

Namespace (created by the platform, in the GitOps repo):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: shop
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
```

### 4.3 CI: GitHub Actions → ECR → GitOps repo

`.github/workflows/release.yaml` (in `shop`):

```yaml
name: release
on:
  push:
    branches: [main]
permissions:
  contents: read
  id-token: write                          # OIDC to AWS
env:
  AWS_REGION: us-east-1
  ECR_REPO: shop-backend
jobs:
  build-push:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.vars.outputs.tag }}
    steps:
      - uses: actions/checkout@v4
      - id: vars
        run: echo "tag=${GITHUB_SHA::7}" >> "$GITHUB_OUTPUT"
      - name: Test
        run: |
          pip install -r backend/requirements.txt pytest
          pytest -q backend/tests
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/gha-shop-ecr-push
          aws-region: ${{ env.AWS_REGION }}
      - id: ecr
        uses: aws-actions/amazon-ecr-login@v2
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: backend
          platforms: linux/amd64,linux/arm64          # Graviton-ready for Karpenter arm64 nodes
          push: true
          tags: ${{ steps.ecr.outputs.registry }}/${{ env.ECR_REPO }}:${{ steps.vars.outputs.tag }}
          provenance: true
          sbom: true
      - uses: aquasecurity/trivy-action@0.33.1
        with:
          image-ref: ${{ steps.ecr.outputs.registry }}/${{ env.ECR_REPO }}:${{ steps.vars.outputs.tag }}
          severity: CRITICAL
          ignore-unfixed: true
          exit-code: "1"
      - name: Lint chart
        run: helm lint chart/ && helm template t chart/ >/dev/null
  promote:
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - name: Open PR in GitOps repo bumping prod tag
        env:
          GH_TOKEN: ${{ secrets.GITOPS_TOKEN }}          # GitHub App/fine-grained token scoped to shop-gitops
          TAG: ${{ needs.build-push.outputs.tag }}
        run: |
          git clone "https://x-access-token:${GH_TOKEN}@github.com/example-org/shop-gitops.git" && cd shop-gitops
          git checkout -b "release-${TAG}"
          yq -i ".image.tag = \"${TAG}\"" envs/prod/values.yaml
          git -c user.name=ci-bot -c user.email=ci-bot@users.noreply.github.com commit -am "prod: shop-backend ${TAG}"
          git push origin "release-${TAG}"
          gh pr create --repo example-org/shop-gitops --title "Release shop-backend ${TAG}" --body "Automated release" --base main
```

Merging the PR = deploying to production (reviewed, auditable, revertible).

### 4.4 CD: Argo CD Application

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: { name: shop-prod, namespace: argocd }
spec:
  project: default
  sources:
    - repoURL: https://github.com/example-org/shop.git        # chart
      targetRevision: main
      path: chart
      helm:
        valueFiles: ["$values/envs/prod/values.yaml"]
    - repoURL: https://github.com/example-org/shop-gitops.git # values
      targetRevision: main
      ref: values
  destination: { server: https://kubernetes.default.svc, namespace: shop }
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: ["ServerSideApply=true"]
```

Pin the chart `targetRevision` to a tag for prod in a mature setup.

### 4.5 DNS

Create a Route 53 alias record `shop.example.com → <ALB DNS name>` (or install **ExternalDNS** with a Pod Identity role scoped to
the hosted zone; it creates records from the Ingress host automatically).

### 4.6 Verify

```bash
argocd app get shop-prod                                  # Synced / Healthy
kubectl -n shop get deploy,hpa,pdb,ingress,externalsecret
curl -sI https://shop.example.com | head -3               # HTTP/2 200, valid TLS (ACM)
curl -sI http://shop.example.com | grep -i location       # redirect to https
kubectl -n shop get pods -o wide                          # spread across zones / nodes
kubectl get nodeclaims                                    # Karpenter-provisioned nodes (Spot/On-Demand, arch)
```

Load test (k6 from your laptop) and watch: HPA adds Pods → Pending Pods → Karpenter adds nodes → Grafana RPS/latency stable.

### 4.7 Production checklist

- [ ] Multi-AZ nodes, topology spread, PDBs, ≥3 replicas
- [ ] Readiness/liveness/startup probes, graceful shutdown (`preStop`, SIGTERM handling)
- [ ] Requests set from measured usage; HPA + Karpenter limits
- [ ] PSA restricted, non-root, read-only rootfs, dropped capabilities, no SA token automount
- [ ] Default-deny NetworkPolicies; RDS SG restricted; IMDSv2 hop limit 1
- [ ] Secrets only from Secrets Manager via External Secrets + Pod Identity
- [ ] Immutable SHA images, scanned, (signed + verified at admission)
- [ ] TLS everywhere at the edge (ACM), HTTP→HTTPS redirect, modern TLS policy
- [ ] Dashboards: RED metrics, saturation; alerts routed to on-call; logs centralised
- [ ] GitOps with PR-based promotion; rollback = `git revert`; runbooks
- [ ] Backups: RDS automated backups + PITR; Velero for cluster objects if needed
- [ ] Cost: Spot for stateless, Graviton, shared ALB (`group.name`), VPC endpoints

### 4.8 Cleanup

```bash
argocd app delete shop-prod --cascade              # removes Ingress → controller deletes the ALB
kubectl get ingress -A                             # wait until empty
# delete Karpenter-provisioned nodes (delete NodePools), then:
eksctl delete cluster -f eks-lab.yaml
# delete RDS instance (final snapshot if you want), ECR repo, Secrets Manager secret, ACM cert, Route 53 records, IAM roles/policies
```

---

## Interview talking points from these projects

- Explain **every hop** of a request in project 3/4 (DNS → ALB → Pod IP → Service discovery → NetworkPolicy → DB).
- Why StatefulSet + PVC locally but RDS in production (managed backups, failover, patching).
- How you'd do a zero-downtime schema migration with rolling updates.
- How the CI pipeline avoids long-lived cloud credentials (OIDC) and the cluster avoids CI credentials (GitOps pull).
- How HPA and Karpenter interact, and what happens if requests are wrong.
- What you'd monitor and alert on, and why (SLOs: availability and latency).
