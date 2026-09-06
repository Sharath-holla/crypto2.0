# Phase 7A Architecture Snapshot

## Experiment boundary

Phase 7A is the separate `CORE20_PRIMARY` experiment identified by `phase7a-core20-primary-93f987736b1a79d26b773957`. It reuses immutable discovery lineage from canonical Phase 7 run `phase7-cc550337f1f4ee4654124bf6`. It does not replace or alter the full Phase 7 experiment.

## Data and model flow

```text
Binance USD-M official archives/API
        |
        v
Immutable Bronze + checksums/manifests
        |
        v
Validated Silver + lifecycle/coverage evidence
        |
        +--> point-in-time registry and discovery (507/507)
        |            |
        |            v
        |      deterministic Core20 + fold membership
        |
        v
Gold features + multiasset_targets_v2
  7/7 chunks, 138 partitions, 50,352,548 rows
        |
        v
Fold datasets and purged/embargoed splits
        |
        v
Prepared matrices  <--- MISSING DURABLE CHECKPOINT BOUNDARY
        |
        v
G0 / C0 / P0 / H0 LightGBM estimators
        |
        v
Cal-A / Cal-B calibration and threshold selection
        |
        v
Out-of-sample predictions, NO_TRADE, and research economics
```

## Scientific timing and identity

- Primary venue/data: Binance USD-M perpetual futures, 5m.
- Features: 54 native A6 features.
- Targets: `multiasset_targets_v2`, 15m/30m/60m/120m.
- Architectures: G0, C0, P0, H0.
- Primary specification set: 48 A6 specifications.
- Validation: 16 walk-forward folds, CORE view only for Phase 7A.
- Entry timing: `open[i+2]`.
- Leakage controls: purge by actual `label_end_time`, 120-minute embargo, train-only preprocessing, separated Cal-A/Cal-B.
- Economics: existing costs and NO_TRADE behavior unchanged.
- Universe: point-in-time, lifecycle-aware, survivorship protected.
- July excluded; August permanently `LOCKED_UNUSED` with evaluation unauthorized.

## Durable boundaries

| Stage | Durable boundary | Current state | Location |
| --- | --- | --- | --- |
| Registry | Checkpoint + registry artifact | Complete | Persistent disk under `local_artifacts/phase7/checkpoints/...` and run artifact root; older canonical backup also in GCS |
| Universe | Checkpoint + Core20/fold membership | Complete | Persistent disk; immutable discovery lineage represented in GCS backup |
| Discovery | Per-symbol interval checkpoints | 507/507 complete | Canonical persistent disk state; 2026-09-04 GCS backup includes checkpoint evidence |
| Acquisition | Data checkpoint + manifest + 60 candle datasets | Complete/valid | Persistent disk; checkpoint SHA-256 and manifest SHA-256 recorded durably |
| Gold | Checkpoint + manifest + partition hashes | 7/7 complete | Persistent disk only at hold time |
| Fold preparation | None | **Missing** | No reusable matrix cache or substage checkpoint |
| Fold model/spec | Per-spec report/model after completion | 0/48 | No completed artifact |
| Fold | Canary/Fold summary | Not complete | No completed Fold 1 summary |

## Current storage identities

- Data checkpoint SHA-256: `d7bb7e99dda07ec62cd493a3c06951d6dae230f340c065b9bd42bd2423a99c0f`.
- Data manifest SHA-256: `e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0`.
- Gold dataset ID: `gold-phase7-0cbf2910e8d96c9d19826598`.
- Gold disk prefix: `/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/`.
- Gold checkpoint: `/home/nssharath123/crypto2.0/local_artifacts/phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/gold.json`.
- Gold checkpoint SHA-256: unavailable from the stopped-VM control plane; must be revalidated on future authorized resume.

## Missing boundary and required design

The expensive sequence between validated Gold and the first estimator has no durable, scientifically identified checkpoint. Interruptions therefore repeat Gold scans, filtering, fold slicing, alignment, and matrix construction. A future cache must be content-addressed and bind all scientific identities that affect rows or columns. It must write atomically, store source hashes and row/column metadata, validate before reuse, and never mark the train stage complete merely because preparation completed.

## Operational controls

Tracked reusable controls are in `scripts/run_phase7a_worker.sh`, `scripts/phase7a_vm_supervisor.py`, `scripts/phase7a_feasibility_gate.py`, and `scripts/phase7a_control_plane_watchdog.ps1`. One-shot incident scripts under `.codex_phase7_overnight_guard/` embed expired deadlines and fixed runtime identities; they are evidence, not canonical launch tooling.
