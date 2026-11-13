# Phase 7A low-memory investigation — measured evidence (2026-11-13)

Status: **EXPERIMENTAL / NOT A RESEARCH FREEZE.** Synthetic data only. No market data was read,
no real model was trained, and the production 64 GiB guard was not modified or bypassed.

## Host (measured)

Claude Code cloud VM: Ubuntu 24.04 x86_64, 4 vCPU Xeon 2.30 GHz, 15 GiB RAM (~13 GiB usable,
no swap), no GPU, ~30 GB writable disk. Linux software gate
(`scripts/closure/verify_linux_external.sh`) passed: 1,471 tests, Ruff clean, filesystem probe PASS
(after `git fetch --unshallow`; a shallow clone fails 6 history-anchored tests).

## Method

`benchmark/schema_probe.py` builds a tiny real Gold through the production feature/target/gold
pipeline to capture the exact schema (`results/gold_schema.json`; 75 columns, + 55 HTF = 130).
`benchmark/gen_gold.py` writes SYNTHETIC Gold with that schema at the measured Fold-0/60m scale:
20 Core20 names, 4,922,887 rows (7 late-start symbols reproduce the measured TRAIN count), 1%
scattered non-finite values in two columns so the finite filter copies as on real data.
`benchmark/prep.py` runs the production functions (`_load_fold_rows`, `bind_fold_cross_sectional_context`,
`slice_hardened_fold`, `_prepare_training_segments`, `PreparedDataCache.write`, `fit_architecture` G0)
and samples VmRSS/RssAnon every 5 ms. `benchmark/patches.py` applies candidate optimizations at
runtime only. `benchmark/train_from_cache.py` measures the read-only (mmap) training process.

## Results

| Run | Peak anon | Peak RSS | Outcome |
|---|---|---|---|
| Unmodified production path, full Fold 0 | n/a | >13 GiB | **OOM-killed (exit 137)** twice, in context binding |
| Unmodified, 3 / 5 / 8 symbols | 3.54 / 6.32 / 9.63 GiB | | linear extrapolation to Fold 0: **~24.9 GiB** |
| Patched, full Fold 0 (prep + cache write + G0 fit + predict) | **11.15 GiB** | 13.27 GiB | completed, 206 s |
| Patched + spill + memmap matrices, worst case (20 full symbols, 5,783,040 rows) | **10.56 GiB** | 13.23 GiB | completed |
| Training from read-only mmap cache, Fold 0 | 1.98 GiB | 9.29 GiB | fit 0.98 GiB anon; 0.428 s/round |
| Training from cache, worst case | 1.71 GiB | 10.36 GiB | 0.459 s/round |

Equivalence (patched vs unmodified, 3/5/8 symbols, plus spill and memmap-matrix variants): every
prepared table column/value/order, TEST table, purge/embargo report, float64 matrix and G0
Cal-A/Cal-B/TEST prediction digest is **IDENTICAL** (`results/eq*`, `results/scale_*`).
Full-scale equivalence cannot run on this VM because the unmodified path OOMs.

## Verified memory causes (unmodified code)

1. `training._load_fold_rows`: `to_table` + `sort_by` full copy; mimalloc retains freed pages
   (5.18 GiB table, 11.35 GiB RSS).
2. `phase7.folds._filter_symbols`: per-row Python list and full `filter` copy even when all
   symbols are eligible.
3. `phase5.folds._range/_prepare_previous/_embargo`: `filter` copies of contiguous ranges.
4. Raw fold table still referenced during slicing; zero-copy slices pin parent buffers.
5. `training._finite`: copy when non-finite rows are scattered (unavoidable; interleaved symbols).
6. Dense float64 matrices duplicate the 109 feature columns (3.1-3.8 GiB).
7. `features.attach_fold_context` / `build_fold_context_table`: Python object arrays (~3 GiB transient).

Not bottlenecks: LightGBM binned data (~0.65 GiB), context sidecar (0.31 GiB), pandas (unused).

## Remaining observations

- Column-wise memmap filling took 589 s (strided writes); row-block filling is required.
- Disk becomes binding: one prepared cache ~8.3-9.9 GB, spill ~6-9 GB, real data ~11 GB.
- The 64 GiB floor is an explicit owner policy (`run_contract.smoke_resource_errors`), not derived.

## Implementation (2026-11-13, owner-approved experimental branch)

Opt-in profile `PHASE7_MEMORY_PROFILE=low_memory` (default `standard` = original code paths):

| Technique | Where |
|---|---|
| Column-group fold read, one shared stable sort index | `low_memory.read_sorted_fold_rows` via `training._load_fold_rows` |
| Zero-copy contiguous selection (`slice`, else `filter`) | `low_memory.filter_rows`, `finite_rows` |
| Vectorized symbol filter, unchanged table when all eligible | `low_memory.filter_symbols` via `folds._filter_symbols` |
| Phase 7 zero-copy twin of the Phase 5 hardened slicer (Phase 5 untouched) | `low_memory.slice_hardened_fold` via `folds.slice_multiasset_fold` |
| Arrow pool release; raw fold table dropped after slicing | `low_memory.release_unused_memory`, `training` load path |
| Fold segments spilled to local IPC and memory-mapped; spill deleted on horizon change/exit | `spill_fold`, `discard_spilled`, `spill_session` |
| Row-block float64 `.npy` memmap matrices (589 s → 15 s) | `low_memory.build_matrix` via `models._matrix` |
| Matrices adopted into the cache by rename; compact string columns → byte-identical cache files | `prepared_cache.write` |
| Sequential execution (one worker) and cache reuse between specifications | unchanged existing admission/cache design |
| Sequential cache release with manifest receipts; measured disk plan | `low_memory_disk` (`plan`, `release`) |

Admission: the standard 64 GiB/8 CPU/150 GB floor is unchanged. The low-memory profile needs
>=13 GiB effective (cgroup-aware) RAM, >=4 CPUs, free cache-filesystem space (14 GiB prepare,
2 GiB train), its own owner approval binding, and for training a `VALIDATED` cached-vs-uncached
record (`low_memory_validation`) bound to the current scientific/preparation digests.

Full-scale synthetic measurement of the COMMITTED code (`results/repo_profile_*.json`):

| Fold shape | Peak anon | Peak RSS | Extra disk peak | Cached vs uncached |
|---|---|---|---|---|
| Fold 0 (4,922,887 rows) | 8.81 GiB | 12.94 GiB | 14.4 GB | IDENTICAL |
| All 20 symbols full window (5,783,040 rows) | 10.34 GiB | 13.25 GiB | 17.1 GB | IDENTICAL |

The remaining peak is cross-sectional context binding (Python string objects in `features.py`),
which was deliberately left unchanged. Freeze record:
`configs/contracts/phase7a_low_memory_experiment_freeze_v1.json`.
