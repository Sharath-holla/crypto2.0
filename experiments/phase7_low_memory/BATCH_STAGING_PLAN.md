# Batch staging plan — prepare the ORIGINAL full fold in chronological batches

Implemented and equivalence-tested on 2026-11-13 (`src/crypto_ai/phase7/staged_fold.py`).
Opt-in: `PHASE7_MEMORY_PROFILE=low_memory` **and** `PHASE7_STAGING_DAYS ∈ {1, 3, 7, 14, 30}`.
Unset → the previous code path. No training semantics change: LightGBM still fits ONCE on the
complete fold (see "Incremental fitting" below).

## What a "batch" is in this project

The friend's workflow (load a slice → process → save → free → next) maps onto this project as:

```
verified Gold (all 2,777 files present, every partition SHA-256 checked first)
  → for each calendar YEAR in the fold window       (Parquet I/O unit: symbol=<S>/year=<Y>, 1 row group/file)
      read that year's rows for one horizon, all symbols, column groups, sorted (feature_time, symbol)
      → for each half-open N-day window inside the year (aligned to train_start)
          filter to the fold's frozen eligible symbols
          bind cross-sectional context from the SAME window of the feature-only sidecar
          assign rows to TRAIN / Validation / Cal-A / Cal-B / TEST, purge by actual label_end_time, embargo
          append kept rows to per-segment Arrow IPC files on local disk
      release the year
  → fold-level checks (segment sizes, holdout, Cal-A/Cal-B separation) + identical purge/embargo report
  → per target: finite filter streamed to IPC, float64 matrices in row blocks to .npy memmaps
  → prepared cache published (files adopted by rename) → read-only reload digest == uncached digest
  → LightGBM fits the complete fold from the cache (unchanged)
```

## Why this is exact (feature continuity)

| Concern | Handling |
|---|---|
| Rolling lookbacks, warm-ups, lags | Computed during the Gold build over full history and stored as columns. Staging never recomputes a feature, so no lookback is truncated and no carry-over state is needed. |
| HTF (12h/1d) context, labels, horizons | Already in Gold (as-of joins, `label_end_time`). Untouched. |
| Cross-symbol dependencies | Context is grouped strictly by `feature_time` (`cross_section.py`). A window contains every symbol at each of its timestamps, and its context rows come from the same window of the all-horizon sidecar (M-01 preserved). |
| Symbol eligibility | Frozen once per fold at `train_end` (point in time), before any window; late-listed symbols keep their original behaviour. |
| Chronological order | Years and windows processed in time order; rows inside a year sorted by `(feature_time, symbol)`; appended in that order. |
| Batch boundaries / duplicates | Half-open `[start, end)` windows partition `[train_start, test_end)`; windows are cut at year boundaries. Tested for 5 h, 1, 3, 7, 30 days. |
| Purge / embargo | Per-row predicates against fixed fold boundaries (actual `label_end_time`, 120 min embargo); counts are summed into the same report structure as Phase 5. |
| Timezone / candle alignment | All timestamps are UTC microseconds from Gold; windows are UTC. |
| Missing intervals | Nothing is filled; a missing interval simply has no rows. Post-TRAIN gap gating is the unchanged `fold_membership`. |
| Non-finite features | Same finite filter (all selected features + target finite), streamed. |
| Data identity | The full Gold manifest is verified before any read. No reduced manifest exists or is created. |

## Choosing the batch size

Measured (synthetic Fold 0, preparation only, no fit):

| Mode | Peak anonymous memory | Slice time |
|---|---|---|
| Unstaged low-memory | 8.83 GiB | 56 s |
| 30-day windows | 4.99 GiB | 47 s |
| 7-day windows | 4.97 GiB | 44 s |

The memory floor is set by the **one-year Parquet read unit**, not the window: smaller windows
only add per-window binding calls. Recommendation: **30 days** (default in
`scripts/cloud/session_env.sh`); 7 days is equally valid. 1–3 days are supported for audits.
Reading less than a year per I/O would require re-partitioning Gold (a new data artifact needing
its own approval); it is not proposed.

## Equivalence evidence

* `tests/phase7/test_low_memory_equivalence.py::test_batch_staged_preparation_equals_standard_without_fitting`
  (5 h / 1 d / 3 d / 7 d / 30 d): tables (all columns, order, NaN bits), report, eligibility,
  `.npy` matrix bytes, cached-vs-uncached digest — identical to the standard path.
* `results/staged_compare_*.json`: full scale across the 2020/2021/2022 year boundaries,
  identical digests (synthetic membership stub, see the script header).
* Arrow cache files are logically identical; their record-batch layout (and so file SHA-256) can
  differ from an unstaged cache. The qualification digest is layout-independent.

## Incremental fitting (NOT activated)

Calling LightGBM on week 1, then week 2 (`init_model`) or `Booster.refit` is a different
algorithm: continued training adds trees fitted to later residuals with earlier trees frozen
(histogram bins come from the first chunk), and `refit` only re-estimates leaf values on fixed
tree structures. Neither reproduces a single fit on the full fold, so predictions, early
stopping, calibration and model identity would change. That would be a new, versioned research
experiment requiring separate approval. It is not needed: the binned training set is ~0.65 GiB
and training from the read-only cache measured ≤ 2 GiB.
