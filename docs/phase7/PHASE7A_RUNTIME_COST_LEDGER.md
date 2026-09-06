# Crypto 2.0 — Phase 7A Runtime and Cost Ledger

## Scope and evidence rules

This ledger records only runtime facts supported by Git history, durable GCS status, local incident records, and control-plane timestamps. No billing amount is inferred from VM duration. GCP billing-export data was not queried, and no owner-reported currency amount was available.

| Session | Purpose | VM start (UTC) | Productive start (UTC) | Stop (UTC) | Productive runtime | Overhead | Outcome | Gold progress | Fold progress | Reason stopped |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Canonical Phase 7 backup | Preserve discovery/acquisition evidence | UNKNOWN | UNKNOWN | 2026-09-04T04:44:36.816513Z backup creation | UNKNOWN | UNKNOWN | Backup complete | Gold not included | Not started | Backup completed |
| Initial Phase 7A window | Registry, universe, acquisition, Gold | 2026-09-04/05, exact time UNKNOWN | UNKNOWN | 2026-09-05T20:12:16.441969Z worker failure; report at 20:12:33.891561Z | 69,239.939018 seconds cumulative authority elapsed at report, not all productive compute | UNKNOWN | BLOCKED | 5/7 atomic chunks, 100 partitions | Not started | HNTUSDT post-delisting lifecycle defect |
| Post-lifecycle recovery | Validate the general lifecycle fix and finish Gold | UNKNOWN | UNKNOWN | UNKNOWN | 2,126.012797 seconds for the 2025 validation chunk | UNKNOWN | Recovery succeeded | 2025 chunk passed; later Gold reached 7/7 | Not started | Continued under owner authority |
| First corrected Fold-1 authority | Gold completion and Fold 1 only | 2026-09-06, exact boot UNKNOWN | 2026-09-06T05:55:06.785Z authority start | UNKNOWN | UNKNOWN | 6,846.423 seconds failed-launch overhead recorded separately | Interrupted | Gold completed during recovery sequence | 0/48 | Launcher/session problems and later manual interruption |
| Earlier Fold-1 attempts, aggregate | Real Fold-1 data/matrix preparation | 2026-09-06T09:06Z (reported) | UNKNOWN | 2026-09-06T11:42Z (reported) | Approximately 2h35m, derived only from the approximately 6h21m aggregate less the final 3h45m42s attempt | UNKNOWN | Manually stopped | 7/7 preserved | 0/48, 0 models | Owner manually stopped VM |
| Final four-hour Fold-1-only window | Real Fold-1 preparation under a hard boundary | 2026-09-06T12:15:39Z | Worker 12:32:41Z; productive authority 12:33:23.222339Z | Graceful event 16:19:14Z; VM terminated 16:19:37.995Z | Approximately 3h45m42s | 1,064.222339 seconds preflight/launch overhead | Budget stop, safe | 7/7 unchanged | 0/48, 0 models | Graceful deadline reached before first durable model/report |
| Project hold | Freeze, inventory, documentation, backup | VM not started | Not applicable | Hold verified from 2026-09-06T17:51:28.5058664Z | 0 VM compute | Local/control-plane work only | PROJECT_HOLD | 7/7 preserved | Fold 1 incomplete; Fold 2 not started | Owner decision |

## Aggregates

- Known real Fold-1 pipeline compute across interrupted attempts: approximately **6h21m**.
- Final attempt productive runtime: approximately **3h45m42s**.
- Earlier attempt productive runtime inferred from the aggregate: approximately **2h35m**; individual boundaries are not fully recoverable from the accessible evidence.
- Explicitly recorded failed-launch overhead: **6,846.423 seconds (1h54m06.423s)**.
- Final-window preflight overhead: **1,064.222339 seconds (17m44.222s)**.
- These intervals did not produce cumulative scientific progress because Fold-1 matrix preparation had no durable substage checkpoint.

## Cost status

- Owner-reported cost: **NOT DOCUMENTED**.
- Billing-verified compute cost: **NOT AVAILABLE**.
- Persistent-disk storage: the 250 GB `pd-balanced` boot disk remains provisioned and can continue incurring storage charges while the VM is stopped.
- GCS storage: preserved objects continue incurring storage charges according to their storage class and use; no objects were deleted or duplicated except the intentionally small hold archive.
