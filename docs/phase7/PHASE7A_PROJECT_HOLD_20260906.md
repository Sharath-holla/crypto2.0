# Crypto 2.0 — Phase 7A Project Hold

Owner: Sharath N. S.

Hold assessment: 2026-09-06T17:51:28.5058664Z

Status: **PROJECT_HOLD**

## 1. Hold Decision

Crypto 2.0 is voluntarily paused because repeated real Fold-1 attempts consumed material VM time before producing the first durable model/report. The immediate engineering blocker is slow, opaque Fold-1 data/matrix preparation with no reusable pre-training checkpoint. This is **not a model failure**: no Fold-1 specification completed, no model qualified, and model quality is not yet evaluable.

The hold prohibits training, Fold-1 resume, Fold 2, Phase 8, paper trading, live trading, and Binance order placement. The VM must remain terminated until new explicit owner authorization.

## 2. Current Project State

| Phase | State |
| --- | --- |
| Phases 1–4.1 | Complete and immutable |
| Phase 5 and Phase 5 hardening | Complete and immutable; all original/hardened artifacts preserved |
| Phase 6 research | Complete and isolated; artifacts preserved |
| Phase 7 local implementation | Complete; canonical scientific framework preserved |
| Phase 7A CORE20 PRIMARY | On hold after Gold completion and incomplete Fold 1 |
| Fold 1 | `STARTED_NOT_COMPLETE`; 0/48 reports; zero serialized models |
| Folds 2–16 | Not started |
| Phase 7.5 | Not started |
| Phase 8 | Not started |
| Paper trading | Not started |
| Live trading | Not started |

## 3. Current Infrastructure

- GCP project: `crypto-ai-trading-506300`
- VM: `crypto-phase7`
- Zone: `asia-south1-a`
- Machine type: `e2-standard-16`
- VM status: `TERMINATED`
- Last control-plane start: 2026-09-06T12:15:23.665Z
- Last control-plane stop: 2026-09-06T16:19:37.995Z
- Automatic restart-on-failure: disabled during hold
- Hold metadata: `phase7-auto-resume=false`, `phase7-stop-reason=project_hold_20260906`, `phase7-stop-status=PROJECT_HOLD`
- Attached boot disk: `crypto-phase7`, 250 GB, `pd-balanced`, `READY`, read/write attached to the stopped VM
- Disk auto-delete: `true`; deleting the VM would delete this disk, so VM deletion is prohibited without separate owner approval
- GCS bucket: `gs://crypto-ai-data-83921`

No managed instance groups exist. A regional resource policy named `default-schedule-1` exists, but the VM has no attached resource policy. Cloud Scheduler was not enabled. The prior Codex monitors were deleted, and no local Codex automation definitions remained at hold verification. No replacement monitoring was created.

Stopping the VM removes active VM compute charges but does not remove persistent-disk or GCS storage charges. A billing-verified monthly disk amount was not obtained and is not estimated here.

## 4. Current Git State

- Branch at hold assessment: `main`
- HEAD before the hold-documentation commit: `be3a164f3fe283885dff1e3a201dbac2dfc303af`
- `origin/main` before the hold-documentation commit: `be3a164f3fe283885dff1e3a201dbac2dfc303af`
- Last validated scientific/operational source commit: `be3a164f3fe283885dff1e3a201dbac2dfc303af`
- Last validated source fingerprint: `ad1aac9508b0b15e9230e06122f4d7fcdf56bf1baab75a9de1a49f1c2894e67d`
- Optimizer commit: `8cdd0b1399a95d0c15bc586603f60ce93b8c3f8e`
- Phase 7A runner commit: `bee3771226ade2daee9cca7f4de535dc72dc50f9`
- Core20 materialization commit: `812f41a3b33500eb4896579c2a23f80bb5b5712c`
- Acquisition-resume commit: `35f20d6bb179c3c9546abd1278097033e104432b`
- Missing-archive fix: `0894e6c8c8ab059f78eeb108c9e1aced0e676214`
- HTF coverage fix: `88af25f21e771bec177394b87e6211e34e8f7df4`
- Post-delisting lifecycle fix: `be3a164f3fe283885dff1e3a201dbac2dfc303af`

The final archival manifest records the final hold commit because a Git commit cannot embed its own object ID. The annotated tag `phase7a-hold-20260906` resolves the final frozen source state.

## 5. Dataset State

- Discovery: 507/507 complete.
- Acquisition: complete.
- Data checkpoint: valid.
- Data checkpoint SHA-256: `d7bb7e99dda07ec62cd493a3c06951d6dae230f340c065b9bd42bd2423a99c0f`.
- Data manifest SHA-256: `e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0`.
- Candle checkpoints: all 60 required Core20 × 5m/12h/1d checkpoint sets were validated before Gold/training preparation.
- Gold: 7/7 complete and scientifically validated.
- Gold partitions: 138.
- Gold rows: 50,352,548.
- Gold dataset ID: `gold-phase7-0cbf2910e8d96c9d19826598`.
- Gold August rows: zero in the validation scan.
- Gold GCS search: no object matched the dataset ID or a Gold checkpoint at hold time.
- Gold storage conclusion: **GOLD PRESERVED ON PERSISTENT DISK**.

The Gold disk prefix is `/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/`. Its checkpoint is expected at `/home/nssharath123/crypto2.0/local_artifacts/phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/gold.json`. The VM was not started to extract a checkpoint hash; the exact current Gold checkpoint SHA-256 is therefore `UNKNOWN` and must be revalidated during a future authorized resume.

### Checkpoint inventory

| Item | Status | Durable path/evidence | Hash | Creation/validation time |
| --- | --- | --- | --- | --- |
| Registry checkpoint | Complete | Persistent disk under `local_artifacts/phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/`; source registry lineage also in canonical GCS backup | Current Phase 7A hash inaccessible while stopped; canonical backup registry hash is recorded in its manifest | UNKNOWN |
| Universe checkpoint | Complete | Persistent disk run/checkpoint roots; realized Core20 recorded in GCS pretraining/status manifests | Core20 hash `f71cdf65d161466037b34420` | UNKNOWN |
| Discovery checkpoints | 507/507 complete | Canonical persistent disk state and `.../backup-phase7-cc550.../local_artifacts/phase7/checkpoints/.../discovery/` in GCS | Per-file SHA-256 values in backup manifest | Backup created 2026-09-04T04:44:36.816513Z |
| Acquisition/data checkpoint | Complete, valid | `/home/nssharath123/crypto2.0/local_artifacts/phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/data.json` | `d7bb7e99...99c0f` | Revalidated before final Fold-1 attempt; exact time UNKNOWN |
| Data manifest | Complete, valid | `/home/nssharath123/crypto2.0/local_artifacts/phase7/phase7a-core20-primary-93f987736b1a79d26b773957/data/data_manifest.json` | `e6532a8b...59dd0` | Revalidated before final Fold-1 attempt; exact time UNKNOWN |
| 5m/12h/1d checkpoints | 60 validated | Persistent disk, referenced by data checkpoint/manifest | Individual hashes recorded on disk; not accessible without VM start | Revalidated before Gold/training; exact time UNKNOWN |
| Gold checkpoint | 7/7 complete | Persistent disk `.../checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/gold.json` | UNKNOWN while VM stopped | UNKNOWN |
| Gold manifest/partitions | Complete | Persistent disk Gold prefix above | File hashes bound by Gold checkpoint; exact values inaccessible while stopped | UNKNOWN |
| Fold 1 | Started, incomplete | Run state/logs on persistent disk | No completed report/model hashes | Last stopped 2026-09-06T16:19:14Z |
| Scientific identities | Preserved | Git config/contracts, GCS pretraining manifest, disk checkpoints | Config `93f987...`; source fingerprint `ad1aac...` | Multiple; see timeline |

## 6. Core20

1. BTCUSDT
2. ETHUSDT
3. ZRXUSDT
4. NEOUSDT
5. FLMUSDT
6. KNCUSDT
7. ONTUSDT
8. BLZUSDT
9. HNTUSDT
10. UNIUSDT
11. TRXUSDT
12. KSMUSDT
13. COMPUSDT
14. IOTAUSDT
15. STORJUSDT
16. OMGUSDT
17. ZECUSDT
18. FILUSDT
19. BCHUSDT
20. DOGEUSDT

`XPINUSDT` was not added. HNTUSDT was not removed after its later delisting because Core20 membership is point-in-time and must remain survivorship-bias protected.

## 7. Scientific Contract

The frozen experiment retains Binance USD-M only; 5m primary data; 54 native A6 features; `multiasset_targets_v2`; 15m/30m/60m/120m horizons; G0/C0/P0/H0; 48 PRIMARY A6 specifications; 16 walk-forward folds; CORE-only Phase 7A; `open[i+2]`; purge using actual `label_end_time`; 120-minute embargo; Cal-A/Cal-B discipline; train-only preprocessing; NO_TRADE; existing cost assumptions; lifecycle awareness; point-in-time universe construction; and survivorship protection.

The EXPANDING view, six A0–A5 feature ablations, and four HTF controls remain deferred. No fold, feature, target, horizon, timing, purge, embargo, cost, or NO_TRADE rule was reduced or changed by this hold.

## 8. Holdout State

- August: `LOCKED_UNUSED`
- `used=false`
- `evaluation_authorized=false`
- July 2026: unused exclusion buffer

No hold operation accessed or evaluated August data.

## 9. Bugs Found and Fixed

### A. Completed acquisition resume

Repeated recovery previously risked unnecessary reacquisition. Commit `35f20d6` made completed symbol acquisitions reusable after identity validation.

### B. Missing official derivative archives

Some Binance derivative archive files genuinely do not exist. Commit `0894e6c` records missing source data explicitly and continues only where the existing contract permits. It does not synthesize candles or index-price rows.

### C. Full-range HTF checkpoint contamination

Short discovery/Core-selection 1d evidence was incorrectly reusable as strict full-range acquisition evidence. BCHUSDT therefore appeared to start 1d history at 2021-10-03 even though official history existed from 2020-01-01. Commit `88af25f` separated discovery-window evidence from full-range coverage identity. Pre-listing boundary behavior remains explicit and interior gaps still fail closed.

### D. Post-delisting lifecycle defect

HNTUSDT Gold construction requested a 2025 window after its validated lifecycle ended in May 2024. The loader recognized wholly pre-listing absence but treated wholly post-delisting absence as an error. Commit `be3a164` applies `requested_window ∩ validated_lifecycle`: pre-listing/post-delisting absence is lifecycle absence, partial overlap loads only the intersection, and missing active-period data fails closed. There is no HNT-specific hack.

### E. Fold-1 launcher defects

One launch path assumed `/usr/bin/time` without validating its presence. Another constructed an incorrect systemd Python invocation by combining interpreters incorrectly. The corrected operational pattern validates required binaries, invokes the environment via `uv run python`, creates authority only after worker health is proven, and uses independent deadline enforcement. These were operational launch failures, not scientific failures.

### F. Gold finalization/resume incident tooling

The one-shot recovery helper also exposed a path-prefix/finalization issue and later refused a valid 7/7 state because it was intentionally scoped to an earlier 5/7 recovery boundary. Full Gold checkpoint and file hashes were validated before bypassing that obsolete helper and entering Fold 1 directly. The one-shot scripts contain expired deadlines and are retained only as local/archive evidence.

## 10. Fold-1 Attempts

The exact session ledger is in `PHASE7A_RUNTIME_COST_LEDGER.md`. Across interrupted attempts, approximately 6h21m of real Fold-1 pipeline compute occurred, but no attempt reached the first durable report/model. A final four-hour window ran one healthy logical worker from 12:32:41Z, with productive authority from 12:33:23.222339Z. CPU remained active, memory rose within safe bounds, disk remained healthy, and no NaN/OOM/data-loader/storage traceback appeared. The graceful stop fired at 16:19:14Z and the VM reached `TERMINATED` at 16:19:37.995Z.

Results at hold:

- Fold-1 reports: 0/48
- Serialized Fold-1 models: 0
- Completed folds: 0/16
- Fold 2: not started
- Qualification: not yet evaluable

## 11. Current Fold-1 Blocker

**OPEN ENGINEERING BLOCKER — FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING**

Fold 1 spends hours scanning Gold and constructing/filtering/alignment matrices before producing a durable estimator artifact. There is no reusable intra-fold prepared-matrix checkpoint and insufficient substage observability. Interruptions repeat the work, so elapsed compute is not cumulative scientific progress.

The next investigation must time Gold scanning, fold filtering, alignment, matrix construction, CPU utilization, memory, and time to first estimator; then add an atomic scientifically identity-safe prepared-matrix cache.

## 12. Models

No completed Fold-1 model exists. No qualified profitable model exists. Model qualification is impossible until Fold 1 completes. This hold records incomplete training, not negative model performance.

## 13. Cost / Runtime History

Known productive Fold-1 runtime is approximately 6h21m across interrupted attempts. Explicit failed-launch overhead of 6,846.423 seconds and final-window preflight overhead of 1,064.222339 seconds are recorded separately. No GCP billing value and no owner-reported currency amount were available, so neither is invented.

## 14. Cloud State and GCS Inventory

VM `crypto-phase7` is terminated. Its persistent disk remains attached/preserved. GCS objects were listed without downloading multi-GB datasets.

| Prefix/object | Size / modified | Purpose and identity |
| --- | --- | --- |
| `gs://crypto-ai-data-83921/artifacts/phase7/backup-phase7-cc550337f1f4ee4654124bf6-20260904T044426Z/` | Phase 7 artifact inventory reports 3,366 objects and 4,521,445,733 bytes (4.21 GiB) including the two small Phase 7A prefixes; backup dominates total | Canonical Phase 7 backup for run `phase7-cc550337f1f4ee4654124bf6`; includes registry/discovery checkpoints, manifests, configs, diagnostics, and compressed run log; large raw/Silver parquet intentionally excluded |
| `.../backup_manifest.json` | 767,197 bytes; 2026-09-04T04:46:44Z | Per-file paths, sizes, SHA-256 values, exclusions, Git identity |
| `gs://crypto-ai-data-83921/artifacts/phase7/phase7a-core20-primary-93f987736b1a79d26b773957/pretraining/` | 4 objects; 5,190 bytes; latest 2026-09-05T02:28:13Z | Pretraining manifest, old runtime authorities, guest stop script; durable historical evidence, not active authority |
| `gs://crypto-ai-data-83921/artifacts/phase7/overnight/phase7a-core20-primary-93f987736b1a79d26b773957/overnight_fold1_status.json` | 3,666 bytes; 2026-09-05T20:12:40Z | HNT lifecycle incident status; earlier than the final Gold/Fold attempts |
| `gs://crypto-ai-data-83921/data/gold/training_sets/gold-19425b0820c974247b73fbe0/` | Size not enumerated | Existing non-Phase7A training set; identity does not match Phase 7A Gold |
| Phase 7A Gold dataset ID search | No matching GCS object | Confirms Gold is preserved on the persistent disk, not GCS, at hold time |

No GCS objects, snapshots, disk data, or VM resources were deleted.

## 15. What Must Not Be Redone

On resume, do not redo discovery, acquisition, the 60 validated candle datasets, or valid Gold 7/7 unless repository checkpoint validation proves corruption or an identity mismatch. Do not treat simple file presence as validation, and do not invent missing hashes while the disk is offline.

## 16. Resume Priority

First profile and checkpoint/cache Fold-1 prepared matrices. Then complete one real Fold 1 and measure actual end-to-end runtime. Only then estimate folds 2–16 and ask the owner whether cost/runtime justify continuation.

## 17. Future Phases

- Fold 2–16: `NOT_STARTED`
- Phase 7.5: `NOT_STARTED`
- Phase 8: `NOT_STARTED`
- Paper trading: `NOT_STARTED`
- Live trading: `NOT_STARTED`

## 18. Operational Code Preservation Decision

Reusable general controls are already committed under `scripts/`: the Phase 7A worker, VM supervisor, Fold-1 feasibility gate, control-plane watchdog, and log rotation. The untracked `.codex_phase7_overnight_guard/` executables embed fixed usernames, run IDs, expired timestamps, and incident-only assumptions. Committing them as launch tools would be unsafe. Their reusable lessons are incorporated in the resume runbook and architecture snapshot; the small incident report is copied into the local/GCS reports archive. PID/state files, transient logs, runtime authorities, patches, SSH data, and credentials are intentionally not committed.

## 19. Dormant Safety State

- VM: `TERMINATED`
- Guest research workers: 0 by termination state
- Training: not running
- Monitoring: off
- Automatic training/auto-resume: off
- Automatic restart-on-failure: off
- Fold 2: not started
- August: `LOCKED_UNUSED`

Future engineers must treat the persistent disk as both the only current Phase 7A Gold location and a continuing storage-cost source. Do not delete the VM because its boot disk has auto-delete enabled.
