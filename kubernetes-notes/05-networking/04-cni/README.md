# 05.04 — CNI: Container Network Interface

## 1. What CNI is and why Kubernetes needs it

**CNI** is a CNCF specification + libraries for configuring network interfaces in Linux network namespaces.
A **CNI plugin** is simply an **executable** that the container runtime runs with a command (`ADD`, `DEL`…), some
environment variables and a JSON config on stdin. It returns a JSON result on stdout.

Why: networks differ wildly (cloud VPCs, BGP datacentres, overlays, eBPF). Kubernetes stays out of it and defines only
the model (05.03); CNI is the pluggable contract that lets any vendor implement it.

```text
 kubelet ──CRI──► containerd ──exec──► /opt/cni/bin/<plugin>  (reads /etc/cni/net.d/*.conflist)
                                         │ ├─ creates veth / interfaces
                                         │ ├─ calls IPAM plugin for an IP
                                         │ └─ sets routes, sysctls
                                         └─ returns JSON result → containerd → kubelet (Pod IP)
 Many CNIs also run a DaemonSet AGENT (calico-node, cilium-agent, flanneld) that programs routes, tunnels,
 policies and BGP across nodes — the binary handles per-Pod setup, the agent handles cluster-wide state.
```

| Responsibility | Done by |
|----------------|---------|
| Create Pod interface (veth), move into netns | CNI main plugin (bridge, ptp, calico, cilium-cni) |
| Allocate/release IPs | IPAM plugin (host-local, calico-ipam, Cilium agent, aws-vpc ENI IPAM) |
| Inter-node connectivity (routes, tunnels, BGP) | CNI agent DaemonSet |
| NetworkPolicy enforcement | CNI agent (Calico Felix, Cilium eBPF, kube-network-policies…) — **Flannel alone does not** |
| Port mapping (`hostPort`) | `portmap` chained plugin |
| Bandwidth shaping | `bandwidth` chained plugin |

---

## 2. CNI spec essentials

**Commands** (spec v1.x):

| Command | When |
|---------|------|
| `ADD` | Pod sandbox created — attach to network, return IPs |
| `DEL` | Pod sandbox removed — release IPs, delete interfaces (must be idempotent) |
| `CHECK` | runtime verifies the network is still as expected |
| `VERSION` | report supported spec versions |
| `STATUS` (v1.1) | is the plugin ready to accept ADDs? (kubelet's `NetworkReady`) |
| `GC` (v1.1) | clean up leaked attachments |

**Environment variables** passed to the plugin:
`CNI_COMMAND`, `CNI_CONTAINERID`, `CNI_NETNS` (path like `/var/run/netns/cni-1234`), `CNI_IFNAME` (`eth0`),
`CNI_PATH` (`/opt/cni/bin`), `CNI_ARGS` (e.g. `K8S_POD_NAMESPACE=default;K8S_POD_NAME=web`).

**Files on every node:**

```bash
ls /etc/cni/net.d/       # config; runtime uses the FIRST file in lexical order (10-calico.conflist, 05-cilium.conflist…)
ls /opt/cni/bin/         # plugin binaries: bridge, host-local, loopback, portmap, calico, cilium-cni, flannel …
```

---

## 3. Configuration files, chaining and IPAM

A `.conflist` is a **chain** of plugins executed in order on ADD (reverse order on DEL). Each receives the previous
result (`prevResult`).

```json
{
  "cniVersion": "1.0.0",
  "name": "mynet",
  "plugins": [
    {
      "type": "bridge",               // main plugin: Linux bridge + veth
      "bridge": "cni0",
      "isGateway": true,              // give cni0 the gateway IP, make it the Pods' default route
      "ipMasq": true,                 // MASQUERADE traffic leaving the Pod subnet
      "hairpinMode": true,            // allow a Pod to reach itself via a Service VIP
      "ipam": {
        "type": "host-local",         // IPAM: allocate from a local range, state in /var/lib/cni/networks/mynet/
        "ranges": [[{ "subnet": "10.244.1.0/24", "gateway": "10.244.1.1" }]],
        "routes": [{ "dst": "0.0.0.0/0" }]
      }
    },
    { "type": "portmap", "capabilities": { "portMappings": true } },   // chained: hostPort support (DNAT)
    { "type": "bandwidth", "capabilities": { "bandwidth": true } }     // chained: tc rate limits from Pod annotations
  ]
}
```

(JSON doesn't allow comments — remove them before using this file.)

**IPAM types:**

| IPAM | How it works | Used by |
|------|--------------|---------|
| `host-local` | allocates from a per-node range, stores reservations as files on the node | bridge, ptp, Flannel, kindnet |
| `dhcp` | asks a DHCP server | macvlan setups |
| `static` | fixed IPs | Multus secondary networks |
| `calico-ipam` | allocates **/26 blocks** per node on demand from IPPools (stored in the datastore), can borrow | Calico |
| Cilium IPAM | modes: `kubernetes` (node.spec.podCIDR), `cluster-pool`, `eni`, `azure`, `multi-pool` | Cilium |
| AWS VPC CNI (ipamd) | secondary IPs / /28 prefixes on ENIs | EKS |
| Whereabouts | cluster-wide IPAM for secondary networks | Multus |

---

## 4. Lab — run a CNI plugin by hand (no Kubernetes!)

This is exactly what containerd does for every Pod.

```bash
CNI_PLUGINS_VERSION=v1.8.0     # check https://github.com/containernetworking/plugins/releases
sudo mkdir -p /opt/cni/bin
curl -sL https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-amd64-${CNI_PLUGINS_VERSION}.tgz \
  | sudo tar xz -C /opt/cni/bin
ls /opt/cni/bin

cat > /tmp/mynet.conf <<'EOF'
{
  "cniVersion": "1.0.0",
  "name": "mynet",
  "type": "bridge",
  "bridge": "cni-lab0",
  "isGateway": true,
  "ipMasq": true,
  "ipam": { "type": "host-local", "subnet": "10.123.0.0/24", "routes": [{ "dst": "0.0.0.0/0" }] }
}
EOF

sudo ip netns add pod1                         # what the runtime would create for the pause container
sudo CNI_COMMAND=ADD CNI_CONTAINERID=pod1 CNI_NETNS=/var/run/netns/pod1 CNI_IFNAME=eth0 CNI_PATH=/opt/cni/bin \
  /opt/cni/bin/bridge < /tmp/mynet.conf
```

Output (the CNI **result**):

```json
{
  "cniVersion": "1.0.0",
  "interfaces": [
    { "name": "cni-lab0", "mac": "..." },                       // bridge on host
    { "name": "veth1a2b3c4d", "mac": "..." },                   // host end
    { "name": "eth0", "mac": "...", "sandbox": "/var/run/netns/pod1" }   // Pod end
  ],
  "ips": [{ "interface": 2, "address": "10.123.0.2/24", "gateway": "10.123.0.1" }],
  "routes": [{ "dst": "0.0.0.0/0" }],
  "dns": {}
}
```

Verify and inspect:

```bash
sudo ip -n pod1 addr show eth0           # 10.123.0.2/24
sudo ip -n pod1 route                    # default via 10.123.0.1
ip addr show cni-lab0                    # 10.123.0.1/24 on the host bridge
bridge link | grep cni-lab0
sudo ls /var/lib/cni/networks/mynet/     # host-local IPAM reservation file "10.123.0.2"
sudo iptables -t nat -S | grep -i cni    # ipMasq rules created by the plugin
sudo ip netns exec pod1 ping -c1 10.123.0.1

# Tear down exactly as the runtime would on Pod deletion
sudo CNI_COMMAND=DEL CNI_CONTAINERID=pod1 CNI_NETNS=/var/run/netns/pod1 CNI_IFNAME=eth0 CNI_PATH=/opt/cni/bin \
  /opt/cni/bin/bridge < /tmp/mynet.conf
sudo ip netns del pod1; sudo ip link del cni-lab0
```

---

## 5. Major network plugins

### 5.1 Flannel

```text
 node1                                         node2
 Pod ─veth─ cni0 (bridge) ─ routing ─ flannel.1 ═VXLAN UDP 8472═ flannel.1 ─ routing ─ cni0 ─veth─ Pod
 flanneld (DaemonSet): reads node.spec.podCIDR, writes VTEP MAC + public IP as node annotations,
                       programs routes + ARP/FDB entries for every other node.
```

- **Backends:** `vxlan` (default), `host-gw` (direct routes; nodes must share L2), `wireguard`, `udp` (⚠️ debug only).
- **Pros:** simplest, tiny, reliable. **Cons:** **no NetworkPolicy** (pair with Calico = "Canal", or a policy agent),
  limited observability, few advanced features.
- **Use:** labs, small clusters, edge (K3s ships Flannel by default).

### 5.2 Calico

```text
 node1                                                   node2
 Pod ─veth(caliXXX)─► host routing table ─► [BGP route learned: 192.168.2.0/26 via node2]
     default gw 169.254.1.1 (proxy ARP)      ├─ no-encap: plain IP over L2/BGP fabric
                                             ├─ IP-in-IP (proto 4, tunl0)
                                             └─ VXLAN (UDP 4789, vxlan.calico)
 Components: calico-node DaemonSet (Felix = programs routes/policy; BIRD = BGP; confd),
             Typha (fan-out cache for big clusters), calico-kube-controllers, Tigera operator, calicoctl/kubectl CRDs.
```

- **Pure L3**: no bridge; each Pod gets a `/32` route to its `cali*` veth.
- **Encapsulation modes:** `Never` (BGP), `IPIP`, `VXLAN`, and `CrossSubnet` (encapsulate only across subnets — popular in AWS).
- **Dataplanes:** iptables, nftables, **eBPF** (can replace kube-proxy), VPP, Windows.
- **Policy:** full Kubernetes NetworkPolicy + Calico `NetworkPolicy`/`GlobalNetworkPolicy` (ordering, deny, L7 with
  Envoy, host endpoints).
- **Pros:** proven at scale, BGP peering with datacentre routers (Pod IPs routable outside the cluster), rich policy.
- **Cons:** BGP concepts to learn; more moving parts than Flannel.
- **Use:** on-prem/bare metal with BGP, enterprise policy needs, EKS/AKS policy add-on.

### 5.3 Cilium

```text
 Pod ─veth(lxcXXX)─ eBPF programs attached at tc/XDP hooks on veth & NIC
       ├─ identity-based policy (labels → numeric identity, enforced in eBPF maps)
       ├─ Service load balancing in eBPF (kube-proxy replacement, socket-level LB, Maglev, DSR)
       ├─ routing: tunnel (VXLAN 8472 / Geneve 6081) or native routing (+BGP control plane)
       └─ Hubble: flow visibility from eBPF events
 cilium-agent DaemonSet, cilium-operator, Envoy (L7 policy, Gateway API/Ingress), optional mesh features.
```

- **Pros:** high performance at scale (no iptables chains), L3–L7 policy, DNS-aware egress policy (`toFQDNs`),
  WireGuard/IPsec encryption, Gateway API, Cluster Mesh (multi-cluster), deep observability with Hubble.
- **Cons:** needs a modern kernel; more complex to debug if you don't know eBPF (`cilium` and `bpftool` CLIs help).
- **Use:** large/modern clusters; default dataplane for GKE Dataplane V2 and AKS (Azure CNI powered by Cilium);
  available on EKS.

### 5.4 Weave Net — ⚠️ historical

Mesh overlay (fast datapath via kernel VXLAN, encryption, its own IPAM). Weaveworks shut down in 2024 and the project is
**no longer maintained** — don't use it in new clusters; migrate existing ones to Calico/Cilium.

### 5.5 Comparison

| | Flannel | Calico | Cilium | Weave (legacy) |
|--|---------|--------|--------|----------------|
| Model | L2 bridge + overlay | L3 routing | eBPF | L2 overlay mesh |
| Encapsulation | VXLAN / host-gw / WireGuard | none / IPIP / VXLAN | VXLAN / Geneve / native | VXLAN / sleeve |
| BGP | no | yes (BIRD) | yes (BGP control plane) | no |
| NetworkPolicy | ❌ | ✅ + extended | ✅ + L7 + FQDN | ✅ basic |
| kube-proxy replacement | no | eBPF mode | ✅ | no |
| Encryption | WireGuard backend | WireGuard | WireGuard / IPsec | NaCl |
| Observability | minimal | flow logs (enterprise), Calico Whisker | Hubble | basic |
| Complexity | very low | medium | medium–high | low |
| Status | active | active | active (CNCF graduated) | unmaintained |

Cloud defaults: **EKS** → Amazon VPC CNI (Pods get VPC IPs; NetworkPolicy via its built-in agent or Calico/Cilium);
**AKS** → Azure CNI (overlay or Cilium-powered); **GKE** → VPC-native with Dataplane V2 (Cilium).

---

## 6. Labs — install CNIs on kind

`kind-nocni.yaml`:

```yaml
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: cni
networking:
  disableDefaultCNI: true       # don't install kindnet
  podSubnet: "192.168.0.0/16"   # Calico default pool (use 10.244.0.0/16 for Flannel)
nodes:
  - role: control-plane
  - role: worker
  - role: worker
```

```bash
kind create cluster --config kind-nocni.yaml
kubectl get nodes        # NotReady — "container runtime network not ready: cni plugin not initialized"
kubectl get pods -n kube-system   # coredns Pending
```

### 6.1 Calico

```bash
CALICO_VERSION=v3.30.3   # check releases
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/tigera-operator.yaml
kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/${CALICO_VERSION}/manifests/custom-resources.yaml
kubectl get tigerastatus -w         # wait until calico shows AVAILABLE True
kubectl get pods -n calico-system -o wide
kubectl get nodes                   # Ready

kubectl get ippools -o yaml         # cidr 192.168.0.0/16, blockSize 26, encapsulation VXLANCrossSubnet (operator default)
kubectl create deployment p --image=nicolaka/netshoot --replicas=3 -- sleep infinity
kubectl get pods -o wide
docker exec cni-worker ip route | grep -E 'cali|vxlan|blackhole'
#  192.168.x.y dev caliXXXX scope link           ← /32 per local Pod
#  blackhole 192.168.x.0/26 proto 80              ← this node's IPAM block
#  192.168.z.0/26 via 192.168.z.0 dev vxlan.calico onlink   ← other node's block via VXLAN (or via node IP if no encap)
docker exec cni-worker ls /etc/cni/net.d/
kubectl exec deploy/p -- ip route    # default via 169.254.1.1 dev eth0  (proxy-ARP gateway)
```

To see encapsulation: all kind nodes share one Docker subnet, so `CrossSubnet` sends **unencapsulated**. Force VXLAN:

```bash
kubectl patch ippool default-ipv4-ippool --type merge -p '{"spec":{"vxlanMode":"Always"}}'
docker exec cni-worker2 sh -c 'apt-get update -qq && apt-get install -y -qq tcpdump >/dev/null; tcpdump -ni eth0 -c 4 udp port 4789' &
kubectl exec <pod-on-worker> -- ping -c 2 <pod-ip-on-worker2>
```

### 6.2 Cilium (with kube-proxy replacement)

```bash
kind delete cluster --name cni
# kind-nocni.yaml + under networking:  kubeProxyMode: "none"   (Cilium will handle Services)
kind create cluster --config kind-nocni.yaml

CILIUM_CLI_VERSION=$(curl -s https://raw.githubusercontent.com/cilium/cilium-cli/main/stable.txt)
curl -L --fail --remote-name-all https://github.com/cilium/cilium-cli/releases/download/${CILIUM_CLI_VERSION}/cilium-linux-amd64.tar.gz{,.sha256sum}
sha256sum --check cilium-linux-amd64.tar.gz.sha256sum
sudo tar xzvfC cilium-linux-amd64.tar.gz /usr/local/bin    # sudo: install into /usr/local/bin
rm cilium-linux-amd64.tar.gz{,.sha256sum}

cilium install --set kubeProxyReplacement=true --set ipam.mode=kubernetes
cilium status --wait
cilium connectivity test               # 50+ end-to-end checks (takes several minutes)
kubectl -n kube-system exec ds/cilium -- cilium-dbg status --verbose | head -40
kubectl -n kube-system exec ds/cilium -- cilium-dbg service list        # Services in eBPF maps (no iptables!)
kubectl -n kube-system exec ds/cilium -- cilium-dbg endpoint list       # Pods with identity numbers

cilium hubble enable --ui
cilium hubble port-forward &           # then install hubble CLI, or open the UI:
cilium hubble ui
hubble observe --namespace default --follow   # live flows: FORWARDED / DROPPED with reason
```

### 6.3 Flannel

On kind, Flannel's CNI delegates to the standard `bridge` plugin, which the kind node image does not ship. Copy it in
first (on kubeadm nodes the `kubernetes-cni` package already provides it):

```bash
kind delete cluster --name cni
sed -i 's#192.168.0.0/16#10.244.0.0/16#' kind-nocni.yaml && kind create cluster --config kind-nocni.yaml
for n in $(kind get nodes --name cni); do
  docker exec $n sh -c "curl -sL https://github.com/containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/cni-plugins-linux-amd64-${CNI_PLUGINS_VERSION}.tgz | tar xz -C /opt/cni/bin ./bridge ./host-local ./portmap"
done
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
kubectl get pods -n kube-flannel -o wide
docker exec cni-worker ip -d link show flannel.1   # vxlan id 1 ... dstport 8472
docker exec cni-worker ip route                    # 10.244.x.0/24 via 10.244.x.0 dev flannel.1 onlink
docker exec cni-worker bridge fdb show dev flannel.1   # remote VTEP MAC → node IP
kubectl get node cni-worker -o yaml | grep flannel.alpha.coreos.com   # backend-data (VTEP MAC), public-ip
```

---

## 7. CNI troubleshooting

| Symptom | Check |
|---------|-------|
| Node `NotReady`: "cni plugin not initialized" | `/etc/cni/net.d/` empty? CNI DaemonSet Pods running on that node? |
| Pods stuck `ContainerCreating`: "failed to setup network for sandbox" | `kubectl describe pod` → error from plugin; `journalctl -u containerd`; CNI agent logs |
| "failed to allocate for range" / no IPs | IPAM exhausted: `/var/lib/cni/networks/*` leaks, Calico `calicoctl ipam check`, AWS ENI limits |
| Two CNI configs present | the lexically first file wins — remove leftovers from a previous CNI |
| Cross-node traffic fails | tunnel port blocked (UDP 8472/4789, proto 4, TCP 179), cloud source/dest check, MTU |
| After CNI migration Pods unreachable | old Pods still on old network — restart them; flush old iptables rules |

```bash
kubectl get pods -n kube-system -o wide | grep -Ei 'calico|cilium|flannel|aws-node'
kubectl logs -n calico-system ds/calico-node -c calico-node --tail=50
kubectl -n kube-system logs ds/cilium --tail=50
journalctl -u containerd | grep -i cni | tail
ls -l /etc/cni/net.d /opt/cni/bin
```

---

## Interview questions

1. **What is CNI?** A spec where the runtime executes plugin binaries with ADD/DEL + JSON config to set up Pod networking.
2. **Where are CNI configs and binaries?** `/etc/cni/net.d/` and `/opt/cni/bin/`.
3. **What is IPAM?** IP address management — the delegated plugin that allocates and frees Pod IPs.
4. **What is plugin chaining?** A conflist running several plugins in order (e.g. main + portmap + bandwidth), each getting
   the previous result.
5. **Does Flannel support NetworkPolicy?** No; combine with Calico (Canal) or another policy engine.
6. **Calico vs Cilium?** Calico: L3 routing/BGP with iptables/nftables/eBPF dataplanes and mature policy. Cilium: eBPF-native,
   identity-based L3–L7 policy, kube-proxy replacement, Hubble observability.
7. **Why might a Pod stay in ContainerCreating?** CNI ADD failing: plugin not ready, IPAM exhaustion, misconfig.
8. **What is the role of the CNI DaemonSet agent?** Cluster-wide state: routes/tunnels/BGP, policy programming, IPAM blocks.
9. **What happens if two CNI config files exist?** The runtime uses the first in lexical order — often the wrong one.
10. **How do Pods get VPC IPs on EKS?** AWS VPC CNI's ipamd attaches ENIs and assigns secondary IPs/prefixes to Pods.

**Scenario:** Pods on newly added nodes get IPs but can't reach other nodes' Pods, Calico VXLAN mode. → Security group missing UDP 4789
between nodes; or MTU; check `calico-node` readiness and `ip route` on the new node.

**Follow-ups:** How does Calico's block-based IPAM borrow IPs? How does Cilium's identity-based policy avoid per-IP rules?
What does CNI `GC` solve?
