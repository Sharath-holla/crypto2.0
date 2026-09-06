# Fold-1 Matrix Preparation Bottleneck

## Verified observations

- The final healthy Fold-1 worker ran approximately 3h45m42s before its authorized graceful stop.
- Across interrupted attempts, approximately 6h21m of real Fold-1 pipeline compute occurred.
- Fold-1 output remained 0/48 reports, zero serialized models, no fold summary.
- CPU was active, memory rose within the available envelope, disk remained healthy, and surviving
  logs showed no NaN, OOM, data-loader, storage, or scientific-identity failure.
- Interruptions forced preparation to restart; elapsed compute was not cumulative progress.

This evidence does not identify one exact hot function. The root performance substage remains
**UNKNOWN / NOT VERIFIED**.

## Suspected pre-estimator stages to measure

1. Partitioned Gold Dataset discovery/scan and column projection.
2. Fold time and symbol filtering.
3. Point-in-time membership and fold-active cross-sectional rebinding.
4. Actual-label purge, embargo, and TRAIN/Validation/Cal-A/Cal-B slicing.
5. Horizon/target/feature finite-row filtering.
6. Arrow combine/copy and Arrow→NumPy matrix conversion.
7. Architecture input preparation, cluster/tier descriptors, and time to first estimator fit.

Do not state that any item is the bottleneck until profiles prove it. Existing in-memory reuse and
thread optimizations reduce repeated work inside one uninterrupted process, but no checkpoint
survives process/VM interruption.

## Required engineering outcome

- Add low-overhead timers, rows/bytes, CPU, peak RSS, read throughput, and cache-hit reporting for
  every stage above.
- Identify serial/single-core, I/O, allocation/copy, and memory-pressure time separately.
- Design a prepared-matrix artifact with explicit TRAIN/Validation/Cal-A/Cal-B arrays, selected row
  keys, ordered columns, target and metadata.
- Bind its identity to source/Gold hashes, config/source fingerprint, run, universe, view, fold,
  horizon, target, feature order, timing, purge/embargo, preprocessing and dependency/schema versions.
- Write to a temporary location, fsync/close as appropriate, validate counts/hashes, then publish
  atomically. Incomplete preparation must not mark a spec or fold complete.
- Benchmark memory-mapped/local Parquet/Arrow IPC/NumPy persistence tradeoffs on the existing disk.
- Prove cached and uncached row keys, arrays, finite masks, estimator identity, predictions and
  reports are scientifically identical under defined deterministic tolerances.
- Test crash-before-publish, corrupt cache, identity mismatch, partial files, resume, and duplicate
  worker behavior.

Do not reduce Core20, folds, features, horizons, models, purge, embargo, or `NO_TRADE` simply to make
the run fit. After the fix, run one Fold 1 only under a newly approved budget and measure end-to-end
time before the owner decides on folds 2–16.
