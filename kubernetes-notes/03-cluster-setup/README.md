# 03 — Kubernetes Cluster Setup on Ubuntu

## 1. Which tool, when?

| Tool | What it is | Best for | Not for |
|------|-----------|----------|---------|
| **kubectl** | CLI client for the API | every interaction | — |
| **kind** | Kubernetes **in Docker** containers (each node = container) | fast local multi-node clusters, CI, networking labs, testing CNIs | performance testing, LoadBalancer realism |
| **Minikube** | single/multi-node local cluster (Docker, KVM, VirtualBox drivers) with add-ons | beginners, add-ons (`ingress`, `metrics-server`), LoadBalancer via `minikube tunnel` | multi-node realism |
| **kubeadm** | official tool to bootstrap a real cluster on machines/VMs | learning real admin, CKA prep, on-prem | managed cloud |
| **containerd** | container runtime used by kubelet | real nodes | — |
| **Docker Engine** | builds images; runs kind/Minikube nodes | dev workstation | as K8s runtime (dockershim removed) |
| **Helm** | package manager for K8s | installing add-ons/apps | — |
| k3s / k0s / MicroK8s | lightweight distributions | edge, homelab | — |
| EKS / AKS / GKE | managed control plane | production in cloud | — |

Recommended path: **kind** for most labs in this handbook, **kubeadm** once to learn real setup,
**EKS** for chapter 15.

---

## 2. Install kubectl on Ubuntu (official `pkgs.k8s.io` repo)

> ⚠️ The old `apt.kubernetes.io` / `packages.cloud.google.com` repositories were frozen in 2023.
> Use `pkgs.k8s.io`. Each **minor version has its own repo**, so you change the URL to upgrade.

```bash
K8S_MINOR=v1.36        # check https://kubernetes.io/releases/ for the current minor version
sudo apt-get update
sudo apt-get install -y apt-transport-https ca-certificates curl gnupg
sudo mkdir -p -m 755 /etc/apt/keyrings          # sudo: writing to system directories
curl -fsSL https://pkgs.k8s.io/core:/stable:/${K8S_MINOR}/deb/Release.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg
echo "deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/${K8S_MINOR}/deb/ /" \
  | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt-get install -y kubectl
kubectl version --client          # prints Client Version: v1.36.x and Kustomize version
```

Quality-of-life setup (no sudo needed — your own shell files):

```bash
echo 'source <(kubectl completion bash)' >> ~/.bashrc
echo 'alias k=kubectl' >> ~/.bashrc
echo 'complete -o default -F __start_kubectl k' >> ~/.bashrc
source ~/.bashrc
```

**Version skew rule:** kubectl is supported within **±1 minor** of the API server.

Useful plugins (via [krew](https://krew.sigs.k8s.io/)): `kubectx`/`kubens` (switch contexts/namespaces),
`stern` (multi-Pod logs), `neat` (clean YAML). Also try `k9s` (terminal UI).

---

## 3. Install Docker Engine (for kind/Minikube and building images)

```bash
# Remove distro packages that conflict (safe if not installed)
for p in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do sudo apt-get remove -y $p; done

sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Let your user talk to the Docker socket without sudo.
# Security note: membership of the docker group is root-equivalent on this machine.
sudo usermod -aG docker "$USER"
newgrp docker                      # or log out and back in
docker run --rm hello-world
```

---

## 4. kind — Kubernetes in Docker

### 4.1 Install

```bash
KIND_VERSION=v0.30.0   # check https://github.com/kubernetes-sigs/kind/releases
ARCH=$(dpkg --print-architecture)          # amd64 or arm64
curl -Lo ./kind "https://kind.sigs.k8s.io/dl/${KIND_VERSION}/kind-linux-${ARCH}"
chmod +x ./kind
sudo mv ./kind /usr/local/bin/kind        # sudo: /usr/local/bin is root-owned
kind version
```

### 4.2 Single-node cluster

```bash
kind create cluster --name dev           # pulls kindest/node image, creates one container
kubectl cluster-info --context kind-dev
kubectl get nodes
docker ps --filter name=dev-control-plane   # the "node" is just a container
```

### 4.3 Multi-node cluster (used throughout this handbook)

`kind-multinode.yaml`:

```yaml
# kind config: 1 control plane + 2 workers
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: lab
networking:
  podSubnet: "10.244.0.0/16"        # Pod CIDR (default)
  serviceSubnet: "10.96.0.0/12"     # Service CIDR (default)
  # disableDefaultCNI: true         # uncomment to install Calico/Cilium yourself (chapter 05.04)
  # kubeProxyMode: "iptables"       # iptables | nftables | ipvs | none
nodes:
  - role: control-plane
    kubeadmConfigPatches:
      - |
        kind: InitConfiguration
        nodeRegistration:
          kubeletExtraArgs:
            node-labels: "ingress-ready=true"
    extraPortMappings:              # expose host ports 80/443 → node, for Ingress/Gateway labs
      - containerPort: 30080
        hostPort: 80
        protocol: TCP
      - containerPort: 30443
        hostPort: 443
        protocol: TCP
  - role: worker
  - role: worker
```

```bash
kind create cluster --config kind-multinode.yaml
kubectl get nodes -o wide
# NAME                STATUS   ROLES           VERSION   INTERNAL-IP
# lab-control-plane   Ready    control-plane   v1.3x.x   172.18.0.3
# lab-worker          Ready    <none>          v1.3x.x   172.18.0.2
# lab-worker2         Ready    <none>          v1.3x.x   172.18.0.4
```

- `INTERNAL-IP` comes from the Docker network `kind` (a Linux bridge on your host — `ip addr show` will
  show a `br-xxxx` interface).
- To pin a Kubernetes version: `kind create cluster --image kindest/node:v1.3x.y@sha256:...`
  (digests are listed in the kind release notes).

### 4.4 Loading local images into kind

```bash
docker build -t myapp:dev .
kind load docker-image myapp:dev --name lab   # copies the image into every node's containerd
# In YAML use image: myapp:dev and imagePullPolicy: IfNotPresent (never "latest", which forces Always)
```

---

## 5. Minikube

```bash
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube && rm minikube-linux-amd64
minikube start --driver=docker --cpus=4 --memory=6g          # single node
minikube start -p multi --driver=docker --nodes=3            # -p = profile (separate cluster)
minikube addons list
minikube addons enable metrics-server
minikube service <svc-name> --url                            # URL for a NodePort service
minikube tunnel                                              # gives LoadBalancer Services an IP (keep running)
minikube dashboard                                           # web UI
minikube ssh                                                 # shell on the node
minikube stop && minikube delete --all
```

| | kind | Minikube |
|--|------|----------|
| Startup speed | very fast | fast |
| Multi-node | excellent | supported |
| Add-ons | install yourself (Helm) | built-in `addons` |
| LoadBalancer | via cloud-provider-kind or MetalLB | `minikube tunnel` |
| CI usage | very common | less common |

---

## 6. kubeadm — a real 3-node cluster

### 6.1 Topology

```text
  cp1   10.0.0.10   control plane (apiserver, etcd, scheduler, controller-manager)
  w1    10.0.0.11   worker
  w2    10.0.0.12   worker
  Pod CIDR 192.168.0.0/16 (Calico default) — must NOT overlap node network or Service CIDR
  Service CIDR 10.96.0.0/12 (default)
```

Create 3 Ubuntu 24.04 VMs (2 vCPU / 2 GB+ each; control plane needs ≥ 2 vCPU), e.g. with Multipass:

```bash
sudo snap install multipass
for n in cp1 w1 w2; do multipass launch 24.04 --name $n --cpus 2 --memory 3G --disk 20G; done
multipass list            # note IPs
multipass shell cp1
```

### 6.2 Run on **all three nodes**

```bash
# 1) Unique hostname + MAC + product_uuid per node (clones often duplicate these)
hostnamectl; ip link; sudo cat /sys/class/dmi/id/product_uuid

# 2) Swap off (kubelet default expects no swap)
sudo swapoff -a
sudo sed -i '/ swap / s/^/#/' /etc/fstab

# 3) Kernel modules and sysctls (see chapter 00 §11)
cat <<'EOF' | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF
sudo modprobe overlay && sudo modprobe br_netfilter
cat <<'EOF' | sudo tee /etc/sysctl.d/99-kubernetes.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sudo sysctl --system

# 4) containerd (from Docker's apt repo: package containerd.io — set up the repo as in §3 first)
sudo apt-get install -y containerd.io
containerd config default | sudo tee /etc/containerd/config.toml >/dev/null   # replaces the stub that disables CRI
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml
grep -n SystemdCgroup /etc/containerd/config.toml        # must show "true"; add it under the runc options section if absent
sudo systemctl restart containerd && sudo systemctl enable containerd
sudo crictl --runtime-endpoint unix:///run/containerd/containerd.sock info >/dev/null && echo "CRI OK"

# 5) kubeadm, kubelet, kubectl from pkgs.k8s.io (repo setup as in §2)
sudo apt-get install -y kubelet kubeadm kubectl
sudo apt-mark hold kubelet kubeadm kubectl    # prevent accidental upgrades via apt upgrade
sudo systemctl enable --now kubelet           # it will crash-loop until kubeadm init/join — that's normal
```

Why each step:

| Step | Reason |
|------|--------|
| unique hostname/MAC/UUID | node identity; duplicates break registration |
| swap off | predictable memory accounting/eviction |
| br_netfilter + sysctls | Service rules must see bridged traffic; node must forward |
| `SystemdCgroup = true` | kubelet (kubeadm default `cgroupDriver: systemd`) and runtime must match |
| `apt-mark hold` | Kubernetes upgrades must follow the kubeadm upgrade procedure |

Firewall ports (if `ufw` is enabled): control plane 6443, 2379-2380, 10250, 10257, 10259;
workers 10250, 10256 (kube-proxy health), 30000-32767; plus your CNI ports (Calico: BGP TCP 179,
VXLAN UDP 4789, IP-in-IP protocol 4; Flannel: UDP 8472; Cilium: UDP 8472, TCP 4240).

### 6.3 Initialise the control plane (on `cp1`)

Use a config file (`kubeadm.k8s.io/v1beta4`, the current kubeadm config API):

```yaml
# kubeadm-config.yaml
apiVersion: kubeadm.k8s.io/v1beta4
kind: InitConfiguration
localAPIEndpoint:
  advertiseAddress: 10.0.0.10        # cp1 IP
nodeRegistration:
  criSocket: unix:///run/containerd/containerd.sock
---
apiVersion: kubeadm.k8s.io/v1beta4
kind: ClusterConfiguration
kubernetesVersion: stable             # or an exact v1.36.x
controlPlaneEndpoint: "10.0.0.10:6443"  # use a DNS name/LB VIP if you will add more control planes
networking:
  podSubnet: 192.168.0.0/16
  serviceSubnet: 10.96.0.0/12
---
apiVersion: kubelet.config.k8s.io/v1beta1
kind: KubeletConfiguration
cgroupDriver: systemd
```

```bash
sudo kubeadm config images pull              # pre-pull control plane images (optional)
sudo kubeadm init --config kubeadm-config.yaml
```

What `kubeadm init` does (phases): preflight checks → generate PKI in `/etc/kubernetes/pki` →
write kubeconfigs → write static Pod manifests → wait for API server → upload config → mark control
plane (taint `node-role.kubernetes.io/control-plane:NoSchedule`) → bootstrap token → CoreDNS and
kube-proxy add-ons. At the end it prints a `kubeadm join ...` command — **save it**.

```bash
# Give your normal user a kubeconfig (admin.conf is root-only)
mkdir -p $HOME/.kube
sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
kubectl get nodes        # cp1 NotReady — no CNI yet
kubectl get pods -n kube-system   # coredns Pending — waiting for Pod network
```

### 6.4 Install a CNI (Calico via the Tigera operator)

```bash
CALICO_VERSION=v3.30.3   # check https://github.com/projectcalico/calico/releases
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/tigera-operator.yaml
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/custom-resources.yaml
# custom-resources.yaml defaults to pool 192.168.0.0/16 — must match podSubnet
watch kubectl get pods -n calico-system
kubectl get nodes        # cp1 Ready
```

### 6.5 Join workers (on `w1`, `w2`)

```bash
sudo kubeadm join 10.0.0.10:6443 --token <token> --discovery-token-ca-cert-hash sha256:<hash>
# Lost the command or token expired (24 h)? On cp1:
sudo kubeadm token create --print-join-command
```

### 6.6 Verify

```bash
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl run t --image=busybox:1.36 --rm -it --restart=Never -- nslookup kubernetes.default
kubectl create deployment verify --image=nginx:1.27 --replicas=3
kubectl expose deployment verify --port=80
kubectl run c --image=curlimages/curl --rm -it --restart=Never -- curl -s verify | head -4
kubectl delete deployment,svc verify
sudo kubeadm certs check-expiration       # on cp1
```

### 6.7 Upgrade outline (one minor at a time)

1. Change apt repo to the next minor, `apt-mark unhold kubeadm`, install new kubeadm.
2. `sudo kubeadm upgrade plan` → `sudo kubeadm upgrade apply v1.3x.y` on first control plane.
3. `kubectl drain cp1 --ignore-daemonsets`, upgrade kubelet/kubectl, restart kubelet, `kubectl uncordon cp1`.
4. Workers: `sudo kubeadm upgrade node`, then drain → upgrade kubelet → uncordon, one at a time.

---

## 7. kubeconfig and contexts

`~/.kube/config` has three lists joined by **contexts**:

```yaml
apiVersion: v1
kind: Config
clusters:                         # WHERE: API server URL + CA
  - name: kind-lab
    cluster:
      server: https://127.0.0.1:39211
      certificate-authority-data: <base64 CA>
users:                            # WHO: credentials (client cert, token, or exec plugin)
  - name: kind-lab
    user:
      client-certificate-data: <base64>
      client-key-data: <base64>
contexts:                         # cluster + user + default namespace
  - name: kind-lab
    context:
      cluster: kind-lab
      user: kind-lab
      namespace: default
current-context: kind-lab
```

```bash
kubectl config get-contexts                  # * marks the current one
kubectl config use-context kind-dev          # switch cluster
kubectl config current-context
kubectl config set-context --current --namespace=shop
kubectl config view --minify                 # only the current context (secrets redacted)
export KUBECONFIG=~/.kube/config:~/.kube/eks-prod.yaml    # merge several files
kubectl config view --flatten > ~/.kube/merged.yaml       # write a merged file
kubectl --context kind-lab get nodes          # one-off context
```

Safety tips: colour your prompt with the current context (kube-ps1), keep production kubeconfigs in a
separate file, and prefer exec-based short-lived credentials (EKS `aws eks get-token`, OIDC).

---

## 8. Delete clusters safely

```bash
# kind / minikube — throwaway
kind get clusters
kind delete cluster --name lab
minikube delete -p multi

# kubeadm — remove a worker gracefully
kubectl drain w2 --ignore-daemonsets --delete-emptydir-data   # evict Pods respecting PodDisruptionBudgets
kubectl delete node w2
# on w2:
sudo kubeadm reset -f
sudo rm -rf /etc/cni/net.d $HOME/.kube        # kubeadm reset does NOT clean CNI config
sudo iptables -F && sudo iptables -t nat -F && sudo iptables -t mangle -F && sudo iptables -X   # or nft flush ruleset
sudo ipvsadm --clear 2>/dev/null || true
```

`drain` = `cordon` (mark unschedulable) + evict Pods. DaemonSet Pods are ignored because their
controller would recreate them immediately.

---

## Common mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Node `NotReady`, "cni plugin not initialized" | no CNI installed | install Calico/Flannel/Cilium |
| kubelet crash-loops before init | normal | run `kubeadm init/join` |
| kubelet: "misconfiguration: kubelet cgroup driver" | driver mismatch | `SystemdCgroup = true` |
| `kubeadm init` preflight: swap | swap enabled | `swapoff -a` |
| Pods can't reach Services on new node | `br_netfilter` not loaded | §6.2 step 3 |
| Pod CIDR overlaps LAN | bad `podSubnet` | rebuild with non-overlapping CIDR |
| `x509: certificate has expired` | 1-year certs | `kubeadm certs renew all` + restart static Pods |
| kind cluster fails "too many open files" | inotify limits | `sudo sysctl fs.inotify.max_user_watches=524288 fs.inotify.max_user_instances=512` |

---

## Interview questions

1. **kind vs Minikube vs kubeadm?** kind: nodes as Docker containers, great for CI/multi-node labs; Minikube:
   beginner-friendly local cluster with add-ons; kubeadm: bootstraps real clusters on machines.
2. **What does `kubeadm init` do?** Preflight, certs, kubeconfigs, static Pod manifests, bootstrap token,
   CoreDNS + kube-proxy.
3. **Why does a fresh kubeadm node show NotReady?** No CNI plugin yet.
4. **Why must cgroup drivers match?** Two managers of the same cgroup tree cause instability; use systemd for both.
5. **Why disable swap?** Historically memory accounting/eviction assumed no swap; swap is now supported
   but must be configured deliberately.
6. **What is a kubeconfig context?** A named cluster + user + namespace combination.
7. **How do you add a worker later?** `kubeadm token create --print-join-command` and run it on the node.
8. **What is `kubectl drain`?** Cordon + evict Pods (respecting PDBs) before maintenance.
9. **Version skew policy?** kubelet up to 3 minors older than API server; kubectl ±1; upgrade control plane first,
   one minor at a time.
10. **How do you back up a kubeadm cluster?** etcd snapshot + `/etc/kubernetes/pki` + manifests in Git.

**Scenario:** After a reboot, a worker is NotReady. → `systemctl status kubelet containerd`, swap re-enabled
in fstab?, modules not loaded?, disk full?

**Follow-ups:** How would you make a highly available control plane with kubeadm (stacked vs external
etcd, LB VIP, `--upload-certs`)? How do bootstrap tokens and TLS bootstrapping work?
