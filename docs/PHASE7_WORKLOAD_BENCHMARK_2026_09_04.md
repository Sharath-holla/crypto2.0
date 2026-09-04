# Phase 7 workload benchmark — 2026-09-04

## Scope and safety

The benchmark ran on the existing `crypto-phase7` Linux VM (16 logical CPUs,
62 GiB RAM) at the canonical Phase 7 configuration hash
`cc550337f1f4ee4654124bf6`. It exercised production Phase 7 model code with the
full 20-symbol data shape: 210,240 TRAIN rows per symbol, 52,560 VALIDATION rows
per symbol, and all 54 A6 features. Values were deterministic synthetic values,
because the research Gold dataset and retrospective fold memberships have not
yet been built. No research pipeline, holdout data, checkpoint, or live-trading
entry point was invoked.

## Exact workload composition

The configuration creates 58 experiment specifications:

- Four horizons times two target forms creates eight horizon/target cells.
- Each cell has G0, C0, P0, and H0 architecture specifications, plus the G0
  explicit-symbol-ID and G0 unbalanced controls: `8 * 6 = 48`.
- Six A0-A5 feature ablations and four higher-timeframe controls add 10.
- Architecture totals are G0=34, C0=8, P0=8, and H0=8.

Sixteen retrospective folds times two research views times 58 specifications
produces exactly `16 * 2 * 58 = 1,856` model bundles.

For `N` eligible symbols and four frozen TRAIN-only clusters, one fold/view has
`34*1 + 8*4 + 8*N + 8*1 = 74 + 8N` logical estimators. Therefore:

- 20 eligible symbols: 234 per fold/view and 7,488 if both views have 20.
- CORE20 plus an EXPANDING30 view: `16 * (234 + 314) = 8,768`.
- The absolute 30-symbol ceiling in both views: `16 * 2 * 314 = 10,048`.

The 10,048 figure is a ceiling, not the known realized count. Exact realized
membership depends on the eligibility decisions in each fold, which do not
exist until the Gold/fold build runs.

## Matched benchmark result

| Architecture | Baseline seconds | Optimized seconds | Speedup |
|---|---:|---:|---:|
| G0 | 333.018 | 91.022 | 3.66x |
| C0 | 506.441 | 80.592 | 6.28x |
| P0 | 530.039 | 87.487 | 6.06x |
| H0 | 384.971 | 19.618 | 19.62x |
| Total model wall time | 1,754.469 | 278.719 | 6.29x |

Model wall time fell by 84.1%. Peak resident memory rose from about 7.39 GiB to
9.38 GiB (1.27x), still well inside the VM's memory envelope. The optimized run
used 31.642 seconds to construct the synthetic Arrow tables and 6.420 seconds
to prepare shared NumPy arrays; those setup costs are separate from the model
total above.

This four-architecture sample is a matched hot-path benchmark, not a promise of
whole-run duration. A simple architecture-count-weighted extrapolation drops
from 201.7 to 40.9 hours for a hypothetical all-A6, 20-symbol, 32-fold/view run,
or 4.94x. Real feature ablations, changing fold memberships, checkpoint skips,
I/O, calibration, economics, and artifact serialization will change that total.

## Execution changes

- Arrow columns convert directly to NumPy instead of materializing Python
  lists, and finite-row filtering stays in Arrow compute.
- One Arrow Dataset object is reused across fold/horizon scans.
- Filtered segments and feature/target NumPy matrices are prepared once per
  fold/view/horizon/target/feature set and reused by all compatible specs.
- Independent C0 cluster and P0 symbol fits run in a bounded four-worker pool;
  each estimator retains the configured four LightGBM threads.
- Single G0/H0 global fits can use the pooled 16-CPU budget.
- H0 reuses the scientifically identical balanced A6 G0 estimator and still
  calculates and emits its own hybrid corrections, bundle, metadata, and
  artifacts. No model specification is removed.
- Completion order never changes serialization order, checkpoint boundaries
  remain per specification, and scheduling provenance is recorded separately
  from scientific model identity.

H0 reuse leaves all logical estimator and bundle counts unchanged. It avoids
256 duplicate physical global fits at the absolute ceiling: 10,048 logical
estimators correspond to at most 9,792 physical fit calls after reuse.

## Verification

- Linux complete suite: 576 passed in 74.40 seconds.
- Ruff lint and formatting: clean across `src`, `tests`, and `scripts`.
- New regression asserts the immutable 58 / 1,856 / 10,048 composition.
- Serial versus parallel C0/P0 predictions are bit-for-bit identical and retain
  the same scientific model identities.
- Four-thread versus pooled-thread G0 predictions are bit-for-bit identical.
- Fresh-fit versus G0-reused H0 predictions are bit-for-bit identical and retain
  the same scientific model identity.
- The optimized full-shape run preserved every baseline best iteration for G0,
  C0, P0, and H0.
