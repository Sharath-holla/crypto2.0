# Transfer guide — Mac → private GCS → Claude Code VM (NOT executed yet)

No Binance download. Your originals under `/Users/cortex/Crypto2Data` are only READ; the upload
folder is made of hard links (no copy) and nothing is ever deleted from the originals.

## The exact set (smallest valid set, verified 2026-11-13)

Committed reference: `docs/reviews/evidence_combined_closure_20261108/runpod_data_only_manifest.json`

| Check | Value |
|---|---|
| Files | **2,777** (records = listed files = unique paths) |
| Bytes | **10,998,003,736** (≈ 11.0 GB) |
| File-list SHA-256 | `5ebe6f7a60565afa4be6a6bd1d27855e9a3fec52959c94160cfe0277a01905b3` |
| Gold partitions + manifest | 139 files (`crypto2-persistent/data/gold/...`) |
| Feature-context sidecar | 140 files (`feature_context_sidecar_v3/`, incl. `manifest.json`, `SIDECAR_COMPLETE`) |
| Silver descriptors, market, exclusions, reconciliation, quality, bronze manifests | remainder |
| Stage checkpoints / registry artifacts | 4 + 9 files (`crypto2-persistent/phase7/...`) |
| Per-file SHA-256 | present for all 2,777 |

Why not fewer files or per-batch transfer: the production loader verifies the SHA-256 of
EVERY Gold partition named in the Gold manifest and refuses to run if one is missing; the
descriptor loader needs the Silver descriptor inputs. A partial manifest would misrepresent the
dataset, so the full verified set is transferred once and batching happens inside the VM
(see `BATCH_STAGING_PLAN.md`). 11 GB fits the VM's disk with the measured budget.

## Costs (estimates; confirm in your billing console)

| Item | Approx. |
|---|---|
| Upload (ingress) | free |
| Storage, 11 GB Standard | ≈ USD 0.22–0.26 / month (delete afterwards) |
| ~2,800 write operations | ≈ USD 0.02 |
| VM download (internet egress) | ≈ USD 1.32–2.53 **per full download** (`transfer_set.py plan`) |
| Service account, IAM | free |

A new session that must re-download pays the egress again. No VM or other paid resource.

## Permissions (least privilege)

* Upload: your own `gcloud` login on the Mac.
* VM: service account `crypto2-claude-reader`, no key file, IAM conditions limited to two
  prefixes: READ `phase7-transfer-20261113/` and `phase7-results/`; CREATE-ONLY under
  `phase7-results/` (it can never overwrite or delete an object, and cannot touch any other
  prefix or resource). You mint a **1-hour** token by impersonation and paste it ONLY into
  Claude's secure credential card for `storage.googleapis.com` (never chat, files or commits).
* Results go to the private bucket, not GitHub: **the repository is public.**

## Mac commands (tomorrow, after Stage A approval)

Get the scripts without touching your main checkout (a separate worktree):

```bash
git -C /Users/cortex/Projects/crypto2.0 fetch origin experiment/phase7-cloud-training-prep
```

```bash
git -C /Users/cortex/Projects/crypto2.0 worktree add /Users/cortex/Projects/crypto2.0-cloudprep origin/experiment/phase7-cloud-training-prep
```

```bash
cd /Users/cortex/Projects/crypto2.0-cloudprep
```

1. Dry run (verifies the file list SHA and the SHA-256 of all 2,777 source files; creates nothing):

```bash
bash scripts/cloud/mac_upload_transfer_set.sh
```

2. Upload (hard-link mirror → `gcloud storage rsync`; re-run the same command to resume):

```bash
bash scripts/cloud/mac_upload_transfer_set.sh --execute
```

3. Read-only access — print first, then apply:

```bash
bash scripts/cloud/mac_setup_reader_access.sh
```

```bash
bash scripts/cloud/mac_setup_reader_access.sh --execute
```

4. When Claude shows the credential card, generate the token and paste it only into the card:

```bash
gcloud auth print-access-token --impersonate-service-account=crypto2-claude-reader@crypto-ai-trading-506300.iam.gserviceaccount.com
```

5. After the experiment (removes access; optionally storage):

```bash
bash scripts/cloud/mac_setup_reader_access.sh --cleanup
```

## VM side (Claude, tomorrow)

```bash
uv run python scripts/cloud/transfer_set.py plan --root /home/user/crypto2data/staging
```

```bash
uv run python scripts/cloud/transfer_set.py fetch --root /home/user/crypto2data/staging --bucket crypto-ai-data-83921 --prefix phase7-transfer-20261113 --execute
```

```bash
uv run python scripts/cloud/transfer_set.py verify --root /home/user/crypto2data/staging --record /home/user/crypto2run/evidence/transfer_verification.json
```

`fetch` downloads by exact object name (no listing), resumes partial files with HTTP Range,
verifies every file's SHA-256 before an atomic rename, logs progress to
`/home/user/crypto2data/staging/.transfer-state/progress.jsonl`, refuses to start if the disk
margin is unsafe, and skips already-verified files on re-run (idempotent).
