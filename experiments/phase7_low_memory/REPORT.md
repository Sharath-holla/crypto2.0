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
