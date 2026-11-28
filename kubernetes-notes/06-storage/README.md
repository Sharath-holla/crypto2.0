# 06 — Kubernetes Storage

## 1. Why storage needs special handling

A container's writable layer disappears when the container is recreated (chapter 00 §5). Pods move between nodes. So
Kubernetes separates **"what storage the app needs"** from **"where the storage comes from"**.

```text
 Pod ──uses──► PersistentVolumeClaim (PVC: "I need 10Gi RWO, class gp3")     ← developer
                     │ bound 1:1
                     ▼
               PersistentVolume (PV: an actual disk/share)                    ← created by admin or dynamically
                     ▲ provisioned by
               StorageClass (gp3 / standard / fast-ssd) → CSI driver → cloud/storage API
```

## 2. Volume types

| Type | Lifetime | Use |
|------|----------|-----|
| `emptyDir` | Pod lifetime (survives container restarts) | scratch space, sharing files between containers; `medium: Memory` = tmpfs |
| `hostPath` | node | node agents (logs, `/var/run/containerd`) — ⚠️ security risk, ties Pod to node |
| `configMap` / `secret` / `downwardAPI` / `projected` | object | config files, credentials, Pod metadata, SA tokens |
| `persistentVolumeClaim` | independent of Pod | databases, uploads |
| `ephemeral` (generic ephemeral volume) | Pod lifetime but CSI-provisioned | per-Pod scratch disk with a StorageClass |
| `image` (newer) | Pod lifetime | mount an OCI image/artifact read-only (e.g. ML models) |
| ⚠️ in-tree cloud volumes (`awsElasticBlockStore`, `gcePersistentDisk`, `azureDisk`) | — | removed/migrated to CSI — use CSI drivers |

```yaml
apiVersion: v1
kind: Pod
metadata: { name: volumes-demo }
spec:
  containers:
    - name: app
      image: busybox:1.36
      command: ["sh", "-c", "echo hi > /scratch/a; cat /scratch/a; sleep 3600"]
      volumeMounts:
        - { name: scratch, mountPath: /scratch }
        - { name: cache, mountPath: /cache }
  volumes:
    - name: scratch
      emptyDir: { sizeLimit: 500Mi }        # evicted if exceeded
    - name: cache
      emptyDir: { medium: Memory, sizeLimit: 64Mi }   # counts against the container memory limit
```

```bash
kubectl apply -f volumes-demo.yaml
kubectl exec volumes-demo -- df -h /scratch /cache
# On the node, emptyDir lives in /var/lib/kubelet/pods/<pod-uid>/volumes/kubernetes.io~empty-dir/scratch
```

`hostPath` example (read-only, typed):

```yaml
volumes:
  - name: varlog
    hostPath:
      path: /var/log
      type: Directory          # DirectoryOrCreate, File, Socket, …; validates what's there
```

---

## 3. PersistentVolumes and PersistentVolumeClaims

### Access modes

| Mode | Short | Meaning | Typical backends |
|------|-------|---------|------------------|
| ReadWriteOnce | RWO | read-write by **one node** (many Pods on that node) | EBS, Azure Disk, PD, local |
| ReadWriteOncePod | RWOP | read-write by **one Pod** in the cluster | CSI block disks |
| ReadOnlyMany | ROX | read-only by many nodes | NFS, snapshots |
| ReadWriteMany | RWX | read-write by many nodes | NFS, EFS, Azure Files, CephFS |

### Reclaim policies

| Policy | When the PVC is deleted |
|--------|------------------------|
| `Delete` | PV **and the underlying disk** are deleted (default for dynamic provisioning) |
| `Retain` | PV becomes `Released`; data kept; admin must clean up/reuse manually |
| ⚠️ `Recycle` | deprecated (basic scrub) |

### PV/PVC lifecycle

`Available` → `Bound` → (PVC deleted) → `Released` → deleted or manually reclaimed. `Failed` if reclamation fails.
PVC phases: `Pending` → `Bound` (→ `Lost` if the PV disappears).

### Static provisioning lab

```yaml
apiVersion: v1
kind: PersistentVolume
metadata: { name: pv-manual }
spec:
  capacity: { storage: 1Gi }
  accessModes: ["ReadWriteOnce"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: manual
  hostPath: { path: /tmp/pv-manual }     # lab only (single node); real clusters use CSI
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: pvc-manual }
spec:
  storageClassName: manual               # must match the PV's class
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 500Mi } }   # PV ≥ request is fine; you get the whole 1Gi
---
apiVersion: v1
kind: Pod
metadata: { name: writer }
spec:
  containers:
    - name: c
      image: busybox:1.36
      command: ["sh", "-c", "date >> /data/log; cat /data/log; sleep 3600"]
      volumeMounts: [{ name: d, mountPath: /data }]
  volumes:
    - name: d
      persistentVolumeClaim: { claimName: pvc-manual }
```

```bash
kubectl apply -f static.yaml
kubectl get pv,pvc                 # STATUS Bound, CLAIM default/pvc-manual
kubectl delete pod writer && kubectl apply -f static.yaml && sleep 5 && kubectl logs writer   # two dates → data persisted
kubectl delete pvc pvc-manual; kubectl get pv pv-manual   # Released (Retain) — data still there
```

---

## 4. StorageClass and dynamic provisioning

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"   # PVCs without storageClassName use this
provisioner: ebs.csi.aws.com             # CSI driver name
parameters:                              # driver-specific
  type: gp3
  encrypted: "true"
  iops: "3000"
reclaimPolicy: Delete
allowVolumeExpansion: true               # lets you increase PVC size later
volumeBindingMode: WaitForFirstConsumer  # create the disk in the zone where the Pod gets scheduled
```

`volumeBindingMode`:

| Mode | Behaviour |
|------|-----------|
| `Immediate` | provision as soon as the PVC is created — may pick a zone where the Pod can't run |
| `WaitForFirstConsumer` | wait until a Pod using it is scheduled → topology-correct (✅ use for zonal disks) |

### Dynamic provisioning lab (kind ships `local-path-provisioner` as default class `standard`)

```bash
kubectl get storageclass
# NAME                 PROVISIONER             RECLAIMPOLICY   VOLUMEBINDINGMODE
# standard (default)   rancher.io/local-path   Delete          WaitForFirstConsumer
cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: data }
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 1Gi } }
EOF
kubectl get pvc data                    # Pending: "waiting for first consumer to be created before binding"
kubectl run user --image=busybox:1.36 --overrides='{"spec":{"volumes":[{"name":"d","persistentVolumeClaim":{"claimName":"data"}}],"containers":[{"name":"user","image":"busybox:1.36","command":["sleep","3600"],"volumeMounts":[{"name":"d","mountPath":"/data"}]}]}}'
kubectl get pvc data -w                 # Bound
kubectl get pv                          # dynamically created pvc-<uid>
kubectl describe pv $(kubectl get pvc data -o jsonpath='{.spec.volumeName}') | grep -A3 -E 'Node Affinity|Source'
```

### Expansion

```bash
kubectl patch pvc data -p '{"spec":{"resources":{"requests":{"storage":"2Gi"}}}}'
kubectl get pvc data -o jsonpath='{.status.conditions}'   # FileSystemResizePending → resized online (CSI dependent)
```

Shrinking is **not** supported.

---

## 5. CSI — Container Storage Interface

```text
 kube-controller / external sidecars (in the CSI controller Deployment):
   external-provisioner  → CreateVolume / DeleteVolume
   external-attacher     → ControllerPublishVolume (attach disk to node)
   external-resizer, external-snapshotter
 CSI node plugin (DaemonSet on each node), called by kubelet:
   NodeStageVolume (format + mount to global path) → NodePublishVolume (bind-mount into Pod dir)
```

```bash
kubectl get csidrivers
kubectl get csinodes -o yaml | grep -A3 drivers      # which drivers are on which node, attach limits
kubectl get volumeattachments                        # disk attached to which node
```

Popular drivers: AWS EBS CSI / EFS CSI, Azure Disk/File, GCE PD, Ceph RBD/CephFS (Rook), Longhorn, OpenEBS, NFS CSI,
Portworx, vSphere CSI.

### Snapshots

```yaml
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata: { name: data-snap }
spec:
  volumeSnapshotClassName: csi-snapclass
  source: { persistentVolumeClaimName: data }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: data-restore }
spec:
  dataSource: { name: data-snap, kind: VolumeSnapshot, apiGroup: snapshot.storage.k8s.io }
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 1Gi } }
```

Requires snapshot CRDs + snapshot controller + a driver supporting snapshots. For whole-app backup use **Velero**.

---

## 6. Stateful storage in practice

- StatefulSet `volumeClaimTemplates` give each replica its own PVC (`data-db-0`, …) — chapter 04 §4.
- Zonal disks pin Pods to a zone. If a zone fails, those Pods can't move → replicate at the **app level** across zones.
- Prefer managed databases (RDS, Cloud SQL) or a mature **operator** (CloudNativePG, Strimzi) over hand-rolled StatefulSets.
- Set `fsGroup` so non-root containers can write to the volume:

```yaml
securityContext:
  runAsUser: 1000
  fsGroup: 2000                     # volume files get group 2000 and group-writable
  fsGroupChangePolicy: OnRootMismatch   # avoid slow recursive chown on big volumes
```

---

## 7. Storage troubleshooting

| Symptom | Cause | Diagnose / fix |
|---------|-------|----------------|
| PVC `Pending` | no default StorageClass; class name typo; WaitForFirstConsumer (normal until a Pod exists); CSI controller down; quota | `kubectl describe pvc`; `kubectl get sc`; CSI controller logs |
| Pod `ContainerCreating`: `FailedAttachVolume` / `Multi-Attach error` | RWO disk still attached to old node (node died) | wait for detach timeout (~6 min) or remove stale `VolumeAttachment` after confirming node is gone |
| `FailedMount` timeout | node plugin issue, wrong FS, NFS unreachable | `kubectl describe pod`, `journalctl -u kubelet`, CSI node logs |
| Permission denied writing | non-root user, volume owned by root | `fsGroup`, initContainer chown |
| Pod Pending: `volume node affinity conflict` | disk in zone A, Pod forced to zone B | WaitForFirstConsumer, matching affinity |
| Disk full | app logs/data growth | expand PVC, alerts on `kubelet_volume_stats_available_bytes` |
| Data lost after `helm uninstall` | reclaimPolicy Delete | Retain for critical data, backups |

```bash
kubectl describe pvc <pvc>
kubectl get events --field-selector involvedObject.name=<pvc>
kubectl -n kube-system logs deploy/ebs-csi-controller -c csi-provisioner --tail=50
kubectl get volumeattachments | grep <pv>
```

---

## Interview questions

1. **PV vs PVC?** PV = actual storage resource; PVC = a request for storage that binds to a PV.
2. **What is a StorageClass?** A template for dynamic provisioning: provisioner, parameters, reclaim policy, binding mode.
3. **RWO vs RWX vs RWOP?** One node read-write / many nodes read-write / exactly one Pod read-write.
4. **Delete vs Retain?** Delete removes the disk with the PVC; Retain keeps it for manual recovery.
5. **Why WaitForFirstConsumer?** Creates the volume in the zone where the Pod is scheduled.
6. **emptyDir vs hostPath?** emptyDir is per-Pod scratch deleted with the Pod; hostPath mounts a node path (risky, node-bound).
7. **What is CSI?** Standard plugin interface for storage vendors, replacing in-tree drivers.
8. **How do StatefulSets get per-Pod storage?** volumeClaimTemplates create one PVC per ordinal that sticks to it.
9. **Multi-Attach error — what happened?** An RWO volume is still attached to another node.
10. **How to back up PVCs?** CSI VolumeSnapshots and/or Velero; app-consistent DB backups.

**Scenario:** "Postgres Pod Pending after node failure in zone A." → EBS volume is zonal; no capacity in zone A → add nodes in zone A
or restore from snapshot elsewhere; design for app-level replication.

**Follow-ups:** How do CSI attach limits per node affect scheduling? What is volume populator/`dataSourceRef`? How does local PV
differ from hostPath?
