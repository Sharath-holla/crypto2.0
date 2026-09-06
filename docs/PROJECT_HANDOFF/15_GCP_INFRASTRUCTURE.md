# GCP Infrastructure

## Verified inventory

A read-only `gcloud` check on 2026-09-06 confirmed:

| Resource | Value |
| --- | --- |
| Project | `crypto-ai-trading-506300` |
| VM | `crypto-phase7` |
| Zone | `asia-south1-a` |
| Status | **TERMINATED** |
| Machine | `e2-standard-16` (16 vCPU; prior guest observations approximately 62–64 GiB RAM) |
| OS image | Ubuntu Minimal 24.04 LTS |
| Boot disk | `crypto-phase7`, 250 GB, `pd-balanced`, `READY`, read/write attached |
| Disk deletion behavior | `autoDelete=true`; deleting the VM would delete the only current Gold disk |
| Service account | `crypto-phase7-vm@crypto-ai-trading-506300.iam.gserviceaccount.com` |
| GCS bucket | `gs://crypto-ai-data-83921`, region `ASIA-SOUTH1` |
| VM repository | `/home/nssharath123/crypto2.0` |
| Automatic restart | false |
| Hold metadata | `phase7-auto-resume=false`, reason `project_hold_20260906`, status `PROJECT_HOLD` |

No credential/private key is documented. The service-account email is an identity, not a secret.

## Roles of resources

The VM supplies Linux CPU/RAM for heavy multi-year PyArrow/LightGBM work that must not run on the
laptop. Its boot persistent disk holds the repository, runtime checkpoints, acquired data, and the
only current Phase 7A Gold dataset. GCS stores durable Phase 7 backups, per-file manifests,
pretraining/status evidence, and project-hold archives; current Phase 7A Gold was not found there.

The VM can remain stopped while its disk and GCS objects persist. Stopping removes active VM
compute usage but not storage charges. Exact billing rates/costs are **UNKNOWN / NOT VERIFIED**.
Do not delete the VM/disk or bucket, resize/create resources, or start compute without owner
authorization and a current cost review.

At hold verification there was no attached instance schedule/resource policy, no managed instance
group, Cloud Scheduler was disabled, automatic restart was false, and no Codex monitor remained.
Recheck after a year because cloud state, IAM, APIs, prices, and retention may change.
