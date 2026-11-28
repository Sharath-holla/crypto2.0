# 00 — Linux Prerequisites for Kubernetes

> **Goal:** understand the Linux features Kubernetes is built on. A container is not a magic box:
> it is a normal Linux process wrapped in **namespaces** (what it can see), **cgroups** (what it can
> use), a **root filesystem** (what files it has) and **capabilities/seccomp** (what it may do).
> Kubernetes simply automates creating and wiring those processes across many machines.

```text
 ┌────────────────────── What a "container" really is ───────────────────────┐
 │                                                                            │
 │   ordinary Linux process (PID 12345 on the host)                           │
 │      + namespaces   → private view: PID, net, mount, UTS, IPC, user, cgroup│
 │      + cgroups      → limits: CPU, memory, PIDs, I/O                       │
 │      + rootfs       → overlayfs layers from the image                      │
 │      + security     → capabilities, seccomp, AppArmor/SELinux              │
 │                                                                            │
 └────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Linux architecture and processes

### 1.1 Kernel space vs user space

```text
 ┌──────────────────────────────────────────────────────────┐
 │ User space: bash, nginx, kubelet, containerd, your app   │
 ├───────────────────── system calls ───────────────────────┤
 │ Kernel: scheduler, memory, VFS, network stack, netfilter,│
 │         namespaces, cgroups, drivers, eBPF               │
 ├──────────────────────────────────────────────────────────┤
 │ Hardware: CPU, RAM, disk, NIC                            │
 └──────────────────────────────────────────────────────────┘
```

- **All containers on a node share one kernel.** That is why a container image built for Linux
  cannot run natively on a Windows kernel, and why a kernel bug can affect every container on a node.
- Programs ask the kernel for things using **system calls** (`open`, `clone`, `socket`, `mount`…).
  Container security tools (seccomp) work by filtering system calls.

### 1.2 Processes, PID and PPID

Every running program is a **process** with:

| Field | Meaning |
|-------|---------|
| PID | Process ID, unique number |
| PPID | Parent PID — the process that started it |
| UID/GID | Which user/group it runs as |
| State | `R` running, `S` sleeping, `D` uninterruptible I/O, `Z` zombie, `T` stopped |

PID 1 (`systemd` on Ubuntu) is the ancestor of all processes. It also **adopts orphans** and
**reaps zombies**. Inside a container, *your application* is often PID 1 — which matters for
signals (see §2).

```bash
ps -ef | head                   # -e every process, -f full format (UID PID PPID C STIME TTY TIME CMD)
ps -eo pid,ppid,user,stat,%cpu,%mem,cmd --sort=-%mem | head   # custom columns, sorted by memory
pstree -p | head -30            # tree of processes with PIDs (package: psmisc)
cat /proc/1/status | head       # every process has a directory in /proc/<pid>
ls -l /proc/$$/ns               # namespaces of your current shell ($$ = current shell PID)
```

`ps -ef` output explained:

```text
UID   PID  PPID  C STIME TTY   TIME     CMD
root    1     0  0 09:01 ?     00:00:03 /sbin/init
root  812     1  0 09:01 ?     00:01:10 /usr/bin/containerd
```

- `PPID 1` for containerd → it was started by systemd.
- `TTY ?` → a daemon, no terminal attached.

### 1.3 Process management

```bash
sleep 300 &              # run in background, prints job number and PID
jobs                     # background jobs of this shell
fg %1                    # bring job 1 to foreground (Ctrl+Z suspends, bg resumes in background)
nice -n 10 tar czf /tmp/x.tgz /etc   # start with lower priority (higher nice = nicer to others)
renice -n 5 -p <pid>     # change priority of a running process
```

---

## 2. Signals and process termination

A **signal** is a small asynchronous message to a process.

| Signal | Number | Default action | Can be caught? | Kubernetes relevance |
|--------|--------|----------------|----------------|----------------------|
| SIGTERM | 15 | terminate | yes | Sent first when a Pod is deleted → graceful shutdown |
| SIGKILL | 9 | kill immediately | **no** | Sent after `terminationGracePeriodSeconds` (default 30s) |
| SIGINT | 2 | terminate | yes | Ctrl+C |
| SIGHUP | 1 | terminate | yes | Many daemons reload config on SIGHUP |
| SIGCHLD | 17 | ignore | yes | Parent notified a child exited (zombie reaping) |
| SIGSTOP | 19 | stop | **no** | Pause |

```bash
sleep 1000 &
kill -TERM $!            # $! = PID of last background job; politely ask to stop
kill -l                  # list all signal names
kill -9 <pid>            # last resort: cannot be caught, no cleanup happens
pkill -f "python app.py" # kill by matching full command line
```

### The PID 1 problem in containers

The kernel treats PID 1 specially: **signals without an installed handler are ignored for PID 1**.
If your app is PID 1 and does not handle SIGTERM, `kubectl delete pod` waits the full 30 seconds,
then SIGKILLs it.

Common causes and fixes:

| Cause | Fix |
|-------|-----|
| `CMD npm start` → shell/npm is PID 1 and doesn't forward signals | Use exec form: `CMD ["node", "server.js"]` |
| Shell script entrypoint | End with `exec "$@"` or `exec myapp` |
| App spawns children and never reaps zombies | Use a tiny init: `tini`, `dumb-init`, or `docker run --init` / `shareProcessNamespace` |

---

## 3. systemd, services and daemons

A **daemon** is a background process (no terminal). On Ubuntu, **systemd** is PID 1 and manages
daemons as **units**. On a Kubernetes node, `containerd` and `kubelet` are systemd services.

```bash
systemctl status kubelet                 # is it running? recent log lines; main PID
sudo systemctl restart containerd        # sudo: changing system services needs root
sudo systemctl enable --now containerd   # enable = start at boot; --now = also start immediately
systemctl list-units --type=service --state=running
systemctl cat kubelet                    # show the unit file and drop-ins
sudo systemctl daemon-reload             # re-read unit files after editing them
journalctl -u kubelet -f                 # follow logs of a unit (-f like tail -f)
journalctl -u containerd --since "10 min ago" --no-pager
journalctl -p err -b                     # only errors since this boot
```

`systemctl status` output explained:

```text
● kubelet.service - kubelet: The Kubernetes Node Agent
     Loaded: loaded (/usr/lib/systemd/system/kubelet.service; enabled; preset: enabled)
    Drop-In: /usr/lib/systemd/system/kubelet.service.d
             └─10-kubeadm.conf          ← kubeadm adds flags here
     Active: active (running) since ...  ← "activating (auto-restart)" = crash loop
   Main PID: 1234 (kubelet)
```

> **Why it matters:** "node NotReady" is very often "kubelet or containerd service is dead".
> The first commands on a broken node are `systemctl status kubelet containerd` and
> `journalctl -u kubelet`.

A minimal unit file:

```ini
# /etc/systemd/system/demo.service
[Unit]
Description=Demo daemon
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 -m http.server 8080
Restart=always          # systemd restarts it if it dies — like a tiny ReplicaSet of 1
User=nobody

[Install]
WantedBy=multi-user.target
```

---

## 4. CPU, RAM, disk and resource monitoring

```bash
top                       # live view; press 1 = per-CPU, M = sort by memory, P = by CPU, q = quit
htop                      # friendlier top (sudo apt install htop)
free -h                   # -h human readable
uptime                    # load average over 1, 5, 15 minutes
nproc                     # number of CPUs
vmstat 1 5                # every 1s, 5 times: run queue, swap, io, cpu
iostat -xz 1              # disk utilisation (package: sysstat)
df -h                     # filesystem usage
df -i                     # inode usage — "disk full" with free space often means inodes are exhausted
du -sh /var/lib/containerd/* | sort -h   # what is eating disk on a node
```

`free -h` explained:

```text
               total   used   free   shared  buff/cache  available
Mem:            15Gi   6.1Gi  1.2Gi  300Mi      8.0Gi      8.9Gi
Swap:             0B      0B     0B
```

- **available** is the number that matters (free + reclaimable cache).
- Kubernetes historically required **swap off**; since v1.28+ swap support exists (`NodeSwap`,
  `LimitedSwap`), but most clusters still disable it. kubeadm will warn if swap is on.

**Kubernetes connection:** kubelet watches node memory, disk and PID pressure. When thresholds
(eviction signals like `memory.available<100Mi`, `nodefs.available<10%`) are crossed, the node gets
`MemoryPressure`/`DiskPressure` conditions and kubelet **evicts Pods**.

---

## 5. Filesystem, mounts, partitions

```bash
lsblk                     # block devices and partitions as a tree
lsblk -f                  # with filesystem type and UUID
sudo fdisk -l             # partition tables (sudo: reads raw devices)
mount | column -t | head  # what is mounted where
findmnt /                 # nicer view of one mount
cat /proc/mounts
sudo mount -t tmpfs -o size=50m tmpfs /mnt   # mount a RAM filesystem (sudo: mounting needs CAP_SYS_ADMIN)
sudo umount /mnt
```

Important directories on a Kubernetes node:

| Path | What lives there |
|------|------------------|
| `/var/lib/kubelet/` | kubelet state, Pod volumes (`pods/<uid>/volumes/...`) |
| `/var/lib/containerd/` | images and container snapshots (overlayfs layers) |
| `/var/log/pods/`, `/var/log/containers/` | container logs (symlinks used by log agents) |
| `/etc/kubernetes/` | kubeconfigs, PKI certs, static Pod manifests |
| `/etc/cni/net.d/` | CNI config | 
| `/opt/cni/bin/` | CNI plugin binaries |
| `/run/containerd/containerd.sock` | CRI socket kubelet talks to |

### Overlay filesystem (how image layers work)

```text
  container view ( merged )   ← what the process sees as "/"
        ▲
  upperdir  (read-write, per container, deleted with the container)
  lowerdir  (read-only image layers: layer3:layer2:layer1)
```

```bash
mkdir -p /tmp/ov/{lower,upper,work,merged}
echo "from image" > /tmp/ov/lower/a.txt
sudo mount -t overlay overlay -o lowerdir=/tmp/ov/lower,upperdir=/tmp/ov/upper,workdir=/tmp/ov/work /tmp/ov/merged
echo "changed" | sudo tee /tmp/ov/merged/a.txt
cat /tmp/ov/lower/a.txt   # still "from image" → lower layer untouched
ls /tmp/ov/upper          # a.txt copied up → copy-on-write
sudo umount /tmp/ov/merged
```

This is why **writing to a container's filesystem is lost when the container is recreated** — and
why Kubernetes has volumes.

---

## 6. Permissions and ownership

```bash
ls -l /etc/kubernetes/admin.conf     # -rw------- root root → only root may read the admin kubeconfig
id                                   # your uid, gid, groups
sudo chown $USER:$USER ~/.kube/config
chmod 600 ~/.kube/config             # kubeconfig contains credentials: owner read/write only
stat file.txt
```

| Notation | Meaning |
|----------|---------|
| `rwx` = 4+2+1 | read, write, execute |
| `chmod 750` | owner rwx, group r-x, others none |
| setuid `s` | run as file owner — dangerous in containers |

**Kubernetes connection:** `securityContext.runAsUser`, `runAsGroup`, `fsGroup` (group ownership
for volumes) and `readOnlyRootFilesystem` are just these Linux concepts expressed in YAML.

**Capabilities** split root's power into pieces (`CAP_NET_ADMIN`, `CAP_SYS_ADMIN`,
`CAP_NET_BIND_SERVICE`…). Containers get a reduced default set; production Pods should
`drop: ["ALL"]` and add only what they need.

```bash
getpcaps $$                           # capabilities of current shell (package: libcap2-bin)
grep Cap /proc/self/status
capsh --decode=00000000a80425fb       # decode a capability bitmask
```

---

## 7. Linux namespaces

A **namespace** gives a process its own private copy of some global resource.

| Namespace | Isolates | Kubernetes use |
|-----------|----------|----------------|
| **PID** | process ID numbers | Container sees its app as PID 1 |
| **Network (net)** | interfaces, IPs, routes, iptables, ports | **Each Pod gets one net namespace**, shared by all its containers |
| **Mount (mnt)** | mount table | Container's own root filesystem and volumes |
| **IPC** | System V IPC, POSIX message queues | Shared within a Pod |
| **UTS** | hostname, domain name | Pod hostname = Pod name |
| **User** | UID/GID mapping | `hostUsers: false` → root in container ≠ root on host |
| **Cgroup** | view of cgroup tree | Container sees its own cgroup as root |
| Time | clock offsets | rarely used |

```text
  Pod "web"  (one network namespace, shared)
  ┌───────────────────────────────────────────┐
  │ pause container  ← holds the namespaces   │
  │ nginx container  ─┐ share net + IPC + UTS │
  │ sidecar container ┘ (own mnt + PID by     │
  │                      default)             │
  │ eth0 10.244.1.5                           │
  └───────────────────────────────────────────┘
```

The **pause** (sandbox) container exists only to hold the Pod's namespaces open, so app containers
can crash and restart without the Pod losing its IP.

### Lab 7.1 — create namespaces with `unshare`

```bash
# New UTS namespace: changing hostname does not affect the host
sudo unshare --uts bash -c 'hostname container-demo; hostname'
hostname                               # host name unchanged

# New PID + mount namespace with its own /proc
sudo unshare --pid --fork --mount-proc bash
ps -ef                                 # only bash and ps; bash is PID 1
exit

# Network namespace: only a loopback, which is DOWN
sudo unshare --net bash -c 'ip addr'
```

- `sudo` is needed because creating most namespaces requires `CAP_SYS_ADMIN` (user namespaces are
  the exception: `unshare --user --map-root-user` works without root on Ubuntu unless restricted
  by AppArmor policy).
- `--fork` makes `unshare` fork so the child becomes PID 1 in the new PID namespace.
- `--mount-proc` remounts `/proc` so `ps` sees the new PID namespace.

### Lab 7.2 — enter a container's namespaces with `nsenter`

```bash
docker run -d --name web nginx
PID=$(docker inspect -f '{{.State.Pid}}' web)   # host PID of the container's PID 1
echo $PID
sudo ls -l /proc/$PID/ns                        # namespace inode numbers
sudo nsenter -t $PID -n ip addr                 # -n: enter ONLY the network namespace, use host tools
sudo nsenter -t $PID -n ss -tlnp                # nginx listening on :80 inside the container
sudo nsenter -t $PID -u hostname                # -u: UTS namespace
sudo nsenter -t $PID -m -p ps -ef 2>/dev/null || echo "image may lack ps"  # mount+pid ns use container's binaries
docker rm -f web
```

> **Interview gold:** `nsenter -n` lets you debug a Pod's network with the *host's* `tcpdump`, `ss`
> and `ip` — even if the container image is distroless and has no shell.

---

## 8. Linux cgroups (v1 vs v2)

**Control groups** limit and account for resources of a group of processes.

| Feature | cgroup v1 | cgroup v2 |
|---------|-----------|-----------|
| Hierarchy | one tree **per controller** (cpu, memory…) | **single unified tree** |
| Mount | `/sys/fs/cgroup/<controller>/` | `/sys/fs/cgroup/` (`cgroup2fs`) |
| Memory | `memory.limit_in_bytes` | `memory.max`, `memory.high`, PSI pressure info |
| CPU | `cpu.cfs_quota_us`, `cpu.shares` | `cpu.max`, `cpu.weight` |
| Status in K8s | ⚠️ maintenance mode; recent kubelets refuse to start on v1 by default | ✅ required for MemoryQoS, better OOM handling, swap |
| Ubuntu | ≤ 20.04 default | ✅ 22.04+ default |

```bash
stat -fc %T /sys/fs/cgroup/          # "cgroup2fs" = v2, "tmpfs" = v1
cat /sys/fs/cgroup/cgroup.controllers
systemd-cgls | head -40              # cgroup tree as systemd sees it
systemd-cgtop                        # top-like view per cgroup
```

### How Kubernetes uses cgroups

```text
/sys/fs/cgroup/kubepods.slice/
  ├── kubepods-burstable.slice/
  │     └── kubepods-burstable-pod<uid>.slice/
  │           └── cri-containerd-<id>.scope   ← one container
  ├── kubepods-besteffort.slice/
  └── kubepods-pod<uid>.slice/                ← Guaranteed QoS Pods
```

- `resources.limits.memory: 256Mi` → `memory.max = 268435456`. Exceeding it → kernel **OOM kill**
  → container status `OOMKilled`, exit code 137 (128 + 9).
- `resources.limits.cpu: 500m` → `cpu.max = 50000 100000` (50 ms per 100 ms period) → exceeding it
  causes **throttling**, not killing.
- `resources.requests.cpu` → `cpu.weight` (relative share when CPU is contended).

### Lab 8.1 — limit memory with a cgroup by hand (v2)

```bash
sudo mkdir /sys/fs/cgroup/demo
echo 50M | sudo tee /sys/fs/cgroup/demo/memory.max
echo 0   | sudo tee /sys/fs/cgroup/demo/memory.swap.max
# Put the current shell into the cgroup, then allocate 100 MB
sudo bash -c 'echo $$ > /sys/fs/cgroup/demo/cgroup.procs; python3 -c "a=bytearray(100*1024*1024)"'
# → "Killed"  — exactly what an OOMKilled container experiences
cat /sys/fs/cgroup/demo/memory.events          # oom_kill counter incremented
sudo rmdir /sys/fs/cgroup/demo
```

**systemd vs cgroupfs driver:** kubelet and the container runtime **must use the same cgroup driver**.
On systemd hosts use `systemd` for both (kubeadm default). A mismatch causes unstable nodes.

---

## 9. Container runtime fundamentals and isolation

```text
 kubectl → kube-apiserver → kubelet ──CRI (gRPC)──► containerd ──► containerd-shim-runc-v2 ──► runc
                                                       │                                     │
                                                       │ pulls image, unpacks layers          │ creates namespaces,
                                                       │ (snapshotter: overlayfs)             │ cgroups, pivot_root,
                                                       ▼                                     ▼ then exec()s your app
                                               /var/lib/containerd                    your process
```

| Layer | Example | Job |
|-------|---------|-----|
| High-level runtime | containerd, CRI-O | images, snapshots, lifecycle, CRI API for kubelet |
| Shim | containerd-shim-runc-v2 | keeps container alive if containerd restarts; collects exit code |
| Low-level (OCI) runtime | runc, crun, gVisor `runsc`, Kata | actually creates the isolated process |
| OCI specs | image-spec, runtime-spec | standard formats so tools interoperate |

Isolation layers in a container:

1. Namespaces (visibility)
2. cgroups (resource limits)
3. Capabilities dropped
4. seccomp filter (blocks dangerous syscalls; `RuntimeDefault` profile)
5. AppArmor (Ubuntu) / SELinux (RHEL) MAC policy
6. Read-only rootfs, non-root user, user namespaces

Inspect with containerd tools on a node:

```bash
sudo crictl ps                 # CRI-level view: what kubelet sees (sudo: socket owned by root)
sudo crictl pods
sudo crictl inspect <container-id> | less
sudo ctr -n k8s.io containers list   # containerd's own CLI; Kubernetes uses the "k8s.io" namespace
```

---

## 10. Linux networking primitives (preview — full depth in chapter 05)

### 10.1 Interfaces, bridges, veth pairs

```text
   netns "red"                         host (root netns)                        netns "blue"
 ┌────────────┐                    ┌──────────────────────┐                   ┌────────────┐
 │ eth0       │◄═══ veth pair ════►│ veth-red   br0       │◄═══ veth pair ═══►│ eth0       │
 │ 10.0.0.2   │                    │   └──── bridge ────┘ │                   │ 10.0.0.3   │
 └────────────┘                    │ 10.0.0.1 (gateway)   │                   └────────────┘
                                   └──────────────────────┘
```

- **veth pair**: a virtual cable; a packet entering one end exits the other. One end goes in the
  Pod's namespace (`eth0`), the other stays on the host (`vethXXXX`, `caliXXXX`, `lxcXXXX`).
- **bridge**: a virtual switch (`cni0`, `docker0`). Learns MAC addresses, forwards frames.

```bash
ip addr                         # interfaces and addresses
ip -br link                     # brief link list
ip route                        # routing table
ip neigh                        # ARP/neighbour cache
bridge link                     # which interfaces are attached to bridges
ss -tulpn                       # -t tcp -u udp -l listening -p process -n numeric
```

### 10.2 Routing, NAT and netfilter

- **Routing table** decides *where* a packet goes next.
- **NAT** rewrites addresses: **SNAT/MASQUERADE** (Pod → internet uses node IP), **DNAT**
  (Service ClusterIP → Pod IP).
- **netfilter** is the kernel hook framework; **iptables** and **nftables** are user-space tools that
  program it. kube-proxy uses them to implement Services.

```bash
sudo iptables -t nat -L -n -v | head -40     # sudo: reading netfilter tables needs CAP_NET_ADMIN
sudo iptables-save | grep KUBE | head
sudo nft list ruleset | head -50
sudo conntrack -L | head                     # tracked connections (package: conntrack)
sysctl net.ipv4.ip_forward                   # must be 1 on Kubernetes nodes
```

### 10.3 DNS resolution

```bash
cat /etc/resolv.conf             # nameserver + search domains
resolvectl status                # systemd-resolved (Ubuntu uses stub 127.0.0.53)
dig kubernetes.io +short
nslookup kubernetes.io
getent hosts kubernetes.io       # uses NSS (/etc/nsswitch.conf) like real apps do
```

> ⚠️ Ubuntu's `/etc/resolv.conf` points to `127.0.0.53`. If kubelet passed that file to Pods, Pods
> would try to reach a loopback address inside their own namespace. kubelet therefore uses
> `/run/systemd/resolve/resolv.conf` (kubeadm configures `resolvConf` automatically). A classic
> CoreDNS loop/crash cause.

### 10.4 Overlay networking (preview)

An **overlay** wraps a Pod packet inside another packet (e.g. VXLAN over UDP 4789/8472) so Pods on
different nodes can talk even if the physical network knows nothing about Pod IPs.

```text
 [ outer Ethernet | outer IP node1→node2 | UDP 8472 | VXLAN VNI | inner Ethernet | inner IP pod→pod | data ]
```

---

## 11. Kernel modules and sysctls Kubernetes needs

```bash
lsmod | grep -E 'overlay|br_netfilter|vxlan|ip_vs|nf_conntrack'
sudo modprobe overlay          # overlayfs for container layers
sudo modprobe br_netfilter     # lets iptables see bridged traffic
cat <<'EOF' | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

cat <<'EOF' | sudo tee /etc/sysctl.d/99-kubernetes.conf
net.bridge.bridge-nf-call-iptables  = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward                 = 1
EOF
sudo sysctl --system           # apply all sysctl files
```

| Setting | Why Kubernetes needs it |
|---------|-------------------------|
| `overlay` | container image layers |
| `br_netfilter` + `bridge-nf-call-iptables=1` | traffic between Pods on the same bridge must pass through iptables so Service DNAT works |
| `ip_forward=1` | node must route packets between Pod veths, other nodes, and outside |

---

## 12. Mapping: Linux concept → Kubernetes feature

| Linux | Kubernetes |
|-------|------------|
| Process | Container |
| Group of processes sharing net/IPC/UTS namespaces | **Pod** |
| systemd `Restart=always` | Controller restarting Pods |
| cgroup `memory.max`, `cpu.max` | `resources.limits` |
| cgroup `cpu.weight` | `resources.requests.cpu` |
| OOM killer | `OOMKilled` |
| SIGTERM → SIGKILL | `terminationGracePeriodSeconds` |
| Network namespace + veth + bridge/route | CNI plugin |
| iptables/nftables DNAT | Service (kube-proxy) |
| Mount namespace + bind mounts | Volumes |
| UID, capabilities, seccomp | `securityContext` |
| `/etc/resolv.conf` | Pod `dnsPolicy` / `dnsConfig` |
| journald | `journalctl -u kubelet` for node debugging |

---

## Common mistakes

1. Thinking containers are VMs — they share the host kernel.
2. Shell-form `CMD` → app is not PID 1 → slow, ungraceful shutdowns.
3. Forgetting `br_netfilter` / `ip_forward` → Services silently fail on new nodes.
4. Mismatched cgroup driver between kubelet and containerd.
5. Ignoring inodes: `df -h` shows space, but `df -i` is 100%.
6. Debugging a distroless container by trying `kubectl exec` — use `nsenter` or `kubectl debug`.

---

## Interview questions

1. **What is a container at the Linux level?**
   A normal process isolated with namespaces, limited with cgroups, given its own root filesystem
   (overlayfs), and restricted with capabilities/seccomp/AppArmor.
2. **Which namespaces do containers in the same Pod share?**
   Network, IPC and UTS by default (held by the pause container). Mount is separate per container;
   PID is separate unless `shareProcessNamespace: true`.
3. **What happens when a container exceeds its memory limit vs its CPU limit?**
   Memory → the kernel OOM-kills it (exit 137, `OOMKilled`). CPU → it is throttled, not killed.
4. **Difference between SIGTERM and SIGKILL?**
   SIGTERM can be caught for cleanup; SIGKILL cannot. Kubernetes sends SIGTERM, waits the grace
   period, then SIGKILL.
5. **Why might a Pod take exactly 30 seconds to terminate?**
   The app (often as PID 1) ignores SIGTERM, so kubelet waits the default 30 s grace period and then
   SIGKILLs it. Fix signal handling or use exec-form CMD / an init like tini.
6. **cgroup v1 vs v2?** v2 is a single unified hierarchy with better memory control and pressure
   metrics; Kubernetes is moving to v2-only.
7. **What is a veth pair?** A virtual Ethernet cable with two ends; used to connect a Pod's network
   namespace to the host.
8. **Why does Kubernetes need `net.ipv4.ip_forward=1`?** The node acts as a router between Pod
   interfaces, other nodes and external networks.
9. **What does `nsenter -t <pid> -n` do?** Runs a command in the network namespace of that process,
   using host binaries — great for debugging Pods.
10. **What is the pause container?** A tiny container that creates and holds the Pod's shared
    namespaces so app containers can restart without losing the Pod's IP.

**Scenario:** *A node shows `NotReady`.* → SSH in, `systemctl status kubelet containerd`,
`journalctl -u kubelet -n 100`, check disk (`df -h`, `df -i`), memory (`free -h`), and certificates.

**Follow-ups:** How does `runc` create a container (clone with namespace flags, cgroup setup,
pivot_root, exec)? What is a user namespace and why does `hostUsers: false` improve security?
