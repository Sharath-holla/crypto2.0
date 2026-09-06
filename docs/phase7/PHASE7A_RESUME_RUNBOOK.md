# Phase 7A Resume Runbook

> **DO NOT IMMEDIATELY RUN ALL 16 FOLDS.**

This runbook applies only after the owner explicitly lifts the project hold and grants a new compute/runtime budget. Starting the VM for training, resuming Fold 1, or enabling monitoring is not authorized by this document.

## Required resume sequence

1. Inspect `main`, `origin/main`, the annotated tag `phase7a-hold-20260906`, and the hold manifest. Require an explainable, clean tracked worktree.
2. Inspect the GCP control plane before starting anything. Confirm the existing VM and its 250 GB `pd-balanced` disk still exist, and identify any changed cost or scheduling state.
3. If owner authorization includes starting the VM, start only `crypto-phase7`; do not create or resize compute.
4. Confirm zero stale workers, timers, services, or tmux sessions before enabling one intended worker.
5. Validate the Phase 7A data checkpoint with repository code. Its expected SHA-256 is `d7bb7e99dda07ec62cd493a3c06951d6dae230f340c065b9bd42bd2423a99c0f`; the corresponding data-manifest SHA-256 is `e6532a8b6fe7246621530738b713c6529b538d219802ba77f3f3a4dad6959dd0`.
6. Validate Gold 7/7 rather than trusting file presence. Expected identity: `gold-phase7-0cbf2910e8d96c9d19826598`, 138 partitions, 50,352,548 rows. Verify the checkpoint's file list, hashes, manifest identity, and half-open cutoff.
7. Verify the prospective holdout remains `LOCKED_UNUSED`, `used=false`, and `evaluation_authorized=false`. Scan Gold timestamps and require zero rows at or beyond `2026-08-01T00:00:00Z`; preserve July as unused.
8. Investigate the Fold-1 preparation bottleneck before rerunning training.
9. Add substage timing for Gold scanning, row filtering, joins/alignment, target materialization, train/validation slicing, preprocessing, matrix construction, and first estimator fit.
10. Add a scientifically safe prepared-matrix checkpoint/cache. Its identity must bind at least configuration, source fingerprint, run/universe, view, fold, horizon, target, feature set/order, purge/embargo boundaries, preprocessing contract, and library/schema version. Writes must be atomic and independently validated before reuse.
11. Benchmark preparation alone and confirm invalid/incomplete caches cannot report `COMPLETE`.
12. Run exactly one real Fold 1 under a newly approved deadline with independent guest and control-plane shutdown guards.
13. Measure preparation, model fitting, calibration, thresholding, OOS economics, peak RAM, disk, and CPU separately.
14. Calculate a conservative folds 2–16 runtime and cost estimate from the completed Fold 1.
15. Stop and present the estimate. The owner decides whether folds 2–16 continue.

## Data reuse rules

- **Do not rebuild Gold unless checkpoint validation fails.**
- Do not rerun discovery or acquisition unless immutable identity validation proves a required artifact missing or corrupt.
- Never synthesize missing candles, derivative rows, or index data.
- Respect lifecycle intersection: pre-listing and post-delisting absence are legitimate; missing data inside an active validated lifecycle fails closed.
- Keep HNTUSDT because the Core20 is point-in-time and survivorship protected. Do not force XPINUSDT into Core20.
- Do not reuse a cache across incompatible fold, view, horizon, target, feature, universe, timing, or preprocessing identities.

## Scientific invariants

Resume must retain Binance USD-M, 5m primary data, the realized Core20, 54 A6 native features, `multiasset_targets_v2`, 15/30/60/120m horizons, G0/C0/P0/H0, 48 PRIMARY A6 specifications, 16 walk-forward folds, CORE-only Phase 7A, `open[i+2]`, actual `label_end_time` purge, 120-minute embargo, train-only preprocessing, Cal-A/Cal-B discipline, NO_TRADE, existing cost assumptions, point-in-time universe construction, lifecycle awareness, survivorship protection, July exclusion, and August `LOCKED_UNUSED`.

The EXPANDING view, six A0–A5 feature ablations, and four HTF controls remain deferred. Phase 8, paper trading, live trading, and Binance order placement remain unauthorized.

## Operational launch lessons

- Use the environment's Python executable directly through `uv run python`; do not pass one Python interpreter as the script argument of another systemd Python invocation.
- Verify `/usr/bin/time` exists before making it part of a worker command, or use a validated fallback. A missing observability utility must fail in preflight, not consume the scientific runtime window.
- Create runtime authority only after the worker and supervisor are observably healthy. Never reuse an expired authority or hard-coded one-shot deadline.
- Maintain exactly one logical worker. A supervisor must distinguish a missing worker, a successfully completed Fold-1 boundary, and a budget stop; none may create a false `COMPLETE` state.

## Resume boundary map

| Boundary | Current status | Reuse action |
| --- | --- | --- |
| Registry | Complete | Validate and reuse |
| Universe/Core20 | Complete | Validate and reuse |
| Discovery 507/507 | Complete | Validate immutable lineage and reuse |
| Acquisition/data | Complete | Validate checkpoint/hash and reuse |
| 60 candle datasets (20 × 5m/12h/1d) | Validated | Reuse; no reacquisition |
| Gold 7/7 | Complete | Validate 138 partitions and reuse |
| Fold preparation/prepared matrices | Missing | First engineering priority |
| Fold 1 reports/models | 0/48; zero models | Rerun only after preparation fix |
| Folds 2–16 | Not started | Owner decision after measured Fold 1 |

## Fail-closed conditions

Stop safely if any identity mismatch, invalid checkpoint, August access, interior active-lifecycle gap, duplicate worker, NaN/OOM/storage error, watchdog failure, false-COMPLETE risk, or deadline violation is observed. Preserve evidence and require new owner approval for scientific or infrastructure changes.
