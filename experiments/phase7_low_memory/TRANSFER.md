# Fold-0 data transfer: Mac → private GCS → Claude Code VM

No Binance download. Your original dataset is only **read**; nothing in `/Users/cortex/Crypto2Data`
is modified or deleted.

## What is transferred (smallest valid set)

The already-verified Phase 7 data-only list (committed in this repository):
`docs/reviews/evidence_combined_closure_20261108/runpod_data_only_files.txt`
(SHA-256 `5ebe6f7a60565afa4be6a6bd1d27855e9a3fec52959c94160cfe0277a01905b3`):
**2,777 files / 10,998,003,736 bytes** — all 139 Gold files, the feature-context sidecar (140 files),
Silver descriptors, market/exclusion/reconciliation metadata, registry artifacts and the four stage
checkpoints. Fewer files is not valid: the production loader verifies the SHA-256 of **every** Gold
partition named in the Gold manifest and refuses to run if one is missing; that safeguard is kept.
July 2026 and the August holdout are not opened by Fold 0; the loader already refuses lineages
that touched them.

## Costs (estimates; GCS list prices, verify for your bucket's region)

| Item | Approx. cost |
|---|---|
| Upload from Mac (ingress) | free |
| Storage, 11 GB Standard | ≈ $0.22–0.26 per month (delete afterwards to stop it) |
| ~2,800 upload operations | ≈ $0.02 |
| Download to the VM (internet egress, ~11 GB) | ≈ $1.30–2.60 **per full download** (free only if the VM happens to be in the same Google region) |
| Service account / IAM | free |

A new cloud session needs a new download (another ≈ $1.30–2.60). No VM, disk or other paid
resource is created.

## Permissions (least privilege)

* Upload: your own `gcloud` login on the Mac (you already own the bucket).
* VM download: a new **read-only service account** limited by an IAM condition to the
  `phase7-transfer-20261113/` prefix. You mint a **1-hour token** for it and paste it only into the
  secure credential card Claude shows (never into chat). The token cannot write, delete, list
  other prefixes, or touch any other Google Cloud resource. Remove access afterwards (step 6).

## Mac commands (run in Terminal, in order)

```bash
export STAGE="/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107"
export LIST="/Users/cortex/Crypto2Data/reports/combined-local-closure-20261108T073250Z/runpod_data_only_files.txt"
export MIRROR="/Users/cortex/Crypto2Data/upload-fold0-20261113"
export BUCKET="gs://crypto-ai-data-83921"
export PREFIX="phase7-transfer-20261113"
export PROJECT="crypto-ai-trading-506300"
export SA="crypto2-claude-reader@${PROJECT}.iam.gserviceaccount.com"
```

1. Check the list is the verified one (must print `5ebe6f7a…b3`):

```bash
shasum -a 256 "$LIST"
```

2. Build an upload folder of **hard links** to exactly the 2,777 listed files (no extra disk space,
   no copy, originals untouched):

```bash
mkdir -p "$MIRROR" && cd "$STAGE" && cpio -pdl "$MIRROR" < "$LIST" && find "$MIRROR" -type f | wc -l
```

   It must print `2777`.

3. Upload (resumable: if interrupted, run the same command again; finished files are skipped and
   every object is integrity-checked by gcloud):

```bash
gcloud storage rsync --recursive "$MIRROR" "$BUCKET/$PREFIX"
```

4. Create the read-only service account and limit it to the prefix (needs uniform bucket-level
   access, which `gcloud storage buckets describe "$BUCKET"` shows as `uniform_bucket_level_access: true`):

```bash
gcloud iam service-accounts create crypto2-claude-reader --project="$PROJECT" --display-name="Crypto2 read-only Fold-0 transfer"
```

```bash
gcloud storage buckets add-iam-policy-binding "$BUCKET" --member="serviceAccount:$SA" --role="roles/storage.objectViewer" --condition="expression=resource.name.startsWith(\"projects/_/buckets/crypto-ai-data-83921/objects/phase7-transfer-20261113/\"),title=phase7-fold0-transfer-only"
```

```bash
gcloud iam service-accounts add-iam-policy-binding "$SA" --project="$PROJECT" --member="user:$(gcloud config get-value account)" --role="roles/iam.serviceAccountTokenCreator"
```

5. When Claude shows the credential card for `storage.googleapis.com`, generate a 1-hour token and
   paste it **only into the card**:

```bash
gcloud auth print-access-token --impersonate-service-account="$SA"
```

6. After the experiment (cleanup, stops storage charges and access):

```bash
gcloud storage rm --recursive "$BUCKET/$PREFIX"
```

```bash
gcloud iam service-accounts delete "$SA" --project="$PROJECT"
```

```bash
rm -rf "$MIRROR"
```

(`rm -rf "$MIRROR"` removes only the hard links; the original files stay.)

## VM side (Claude)

Downloads each listed object by exact name (no bucket listing), writes to a staging directory
outside the repository, verifies **size and SHA-256 of all 2,777 files against the committed
manifest** `runpod_data_only_manifest.json`, then verifies the Gold manifest/checkpoints and the six
recorded identities (`GOLD_MANIFEST_SHA a1420277…`, `SIDECAR_SHA ea5f25a2…`) before any use.
