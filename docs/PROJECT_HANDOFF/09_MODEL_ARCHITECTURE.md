# Model Architecture

## Common estimator

All Phase 7A architectures use `lightgbm.LGBMRegressor(objective="regression")` with deterministic
column-wise fitting, seed 42, Validation early stopping, and the hyperparameters frozen in
`research_core20_primary_v1.toml`. Inputs are finite rows from the ordered A6 schema; outputs are
continuous expected returns (normalized predictions are converted back to raw units before
economics).

| Architecture | Meaning | Estimators and coverage |
| --- | --- | --- |
| G0 | Global pooled | One model over all eligible symbols; optional explicit TRAIN-frozen symbol one-hot; symbol-balanced or unbalanced control |
| C0 | Cluster | TRAIN-only StandardScaler/K-means descriptors assign symbols; one estimator per eligible cluster; missing/ineligible clusters expose coverage gaps |
| P0 | Per coin | One estimator per symbol only after TRAIN ≥20,000, Validation ≥2,000, and Cal-A ≥2,000 rows; Cal-B cannot create/remove estimators |
| H0 | Hybrid | Global estimate plus adequately supported symbol residual correction, else cluster correction, else global fallback |

For G0/H0, previously unseen symbol identity maps to all-zero known levels when explicit symbol ID
is enabled. Clusters, symbol levels, row gates, liquidity tiers, and correction support are frozen
from pre-TEST data. H0 may reuse a G0 global estimator only when feature, target, weighting,
symbol-ID, cluster, and level identities match exactly.

## Calibration and decision policy

Validation owns LightGBM early stopping and H0 residual structure. Cal-A compares identity and
linear calibration using only Cal-A. Cal-B chooses a fixed threshold from 2/4/6/8/10 bps at global,
cluster, or per-coin granularity after configured costs; fewer than 30 candidate trades yields no
threshold and therefore `NO_TRADE`. TEST is released only after model, calibrator, threshold,
universe, and schema identities freeze.

## Verified execution optimizations

Commit `8cdd0b1` added prepared architecture inputs so Arrow→NumPy conversion is shared across
architectures for an identical fold/target/schema. `training.py` uses Arrow-native finite filters;
partitioned Gold is scanned as an Arrow Dataset; C0/P0 independent estimators use a bounded
`ThreadPoolExecutor`; threads are allocated so outer workers and per-estimator LightGBM threads do
not oversubscribe the logical CPU budget; H0 can reuse compatible G0; futures resolve in canonical
job order. `save_model` writes joblib to a unique temporary file then `os.replace`s it and refuses
overwrite, preserving deterministic artifact behavior.

These optimizations do not supply the missing durable prepared-matrix checkpoint. The historical
synthetic workload benchmark quantified possible improvements but is not a real Fold-1 runtime.
The only real observation is 0/48 reports after the attempts described in
[21_FOLD1_PREPARATION_BOTTLENECK.md](21_FOLD1_PREPARATION_BOTTLENECK.md).
