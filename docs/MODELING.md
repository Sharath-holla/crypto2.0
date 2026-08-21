# Phase 3 Baseline Modeling

Phase 3 measures predictive behavior only. Its outputs are not an execution-aware backtest and contain no fees, spread, slippage, funding, orders, positions, PnL, Sharpe ratio, drawdown, or profitability claim.

## Chronological development split

Gold rows are strictly ordered by `feature_time`. The default split derives timestamp boundaries at approximately 70%/15%/15% for train, validation, and development test. Explicit UTC validation/test boundaries are also supported.

Before fitting:

- training rows with `label_end_time >= validation_start` are purged;
- validation rows with `label_end_time >= test_start` are purged;
- test data is never used for model fitting, scaler/preprocessing fitting, early stopping, feature selection, model selection, hyperparameter selection, or threshold selection;
- the full feature schema, finite values, target type, timestamp order, and non-empty splits are checked.

This is a development split, not the later sacred final holdout or complete walk-forward framework.

## Models

| Model | Definition |
| --- | --- |
| `zero` | Predict zero for every observation. |
| `historical_mean` | Predict the training-set target mean; validation/test targets are never consulted. |
| `momentum` | Predict `return_1h` directly. |
| `mean_reversion` | Predict `-ema20_distance` directly. |
| `ridge` | Training-only `StandardScaler` followed by regularized Ridge regression. |
| `lightgbm` | Conservative `LGBMRegressor`; validation-only early stopping, fixed seed, single-thread deterministic settings, gain and validation permutation importance. |

Model artifacts store the exact ordered feature schema, model/version, hyperparameters, random seed, dataset/feature/label versions, train/validation periods, training-only scaler parameters where applicable, and library versions. Reloaded artifacts must reproduce predictions and reject missing, extra, reordered, NaN, or infinite inputs.

## Metrics and outputs

Validation and development-test outputs include MAE, RMSE, R², directional accuracy, Pearson information coefficient, and Spearman/rank information coefficient. Constant predictors receive `null` correlation rather than a misleading number.

Test predictions are divided into ten rank-ordered prediction buckets. Each bucket reports count, predicted and realized mean return, prediction range, and directional hit rate. These are research-signal statistics, not strategy returns.

For LightGBM, gain importance and validation-set permutation importance using negative MAE are stored in both `models/lightgbm.metadata.json` and `metrics/lightgbm.json`. These describe fitted-model behavior and are not causal importance.

Every deterministic experiment directory contains:

```text
local_artifacts/experiments/<experiment-id>/
    experiment.json
    comparison.json
    comparison.csv
    models/<model>.joblib
    models/<model>.metadata.json
    predictions/<model>.parquet
    metrics/<model>.json
```

Experiment identity hashes the Gold dataset version, research configuration, model list, and experiment code version. Artifact output paths do not affect the identity. An identical rerun reuses the complete experiment instead of overwriting predictions.

## Commands

```powershell
uv run crypto-ai build-dataset --config configs/datasets/btcusdt_5m_july_2026.toml

uv run crypto-ai train `
  --dataset-manifest data/gold/training_sets/gold-19425b0820c974247b73fbe0/manifest.json `
  --config configs/models/baseline_v1.toml

uv run crypto-ai train `
  --dataset-manifest data/gold/training_sets/gold-19425b0820c974247b73fbe0/manifest.json `
  --config configs/models/lightgbm_v1.toml

uv run crypto-ai evaluate `
  --experiment local_artifacts/experiments/experiment-5f0f09b3ee131bddba69a0b1/experiment.json
```

## Main Model V2

Phase 4 uses deterministic LightGBM regression and unchanged Label V1. Every
ablation uses the same Gold V2 timestamps and purged 70/15/15 split. Validation
alone controls early stopping; development test is read only after fitting.

The cumulative plan is A0 Phase 3 baseline, A1 price/trend, A2
momentum/volatility, A3 volume, A4 taker pressure, A5 funding, A6 basis, A7 open
interest, and A8 Regime V1/time plus final redundancy pruning. A6/A7 are visibly
omitted when validated overlapping datasets are unavailable.

Artifacts contain the bundle and exact schema, validation/test predictions,
regression/directional/rank metrics, prediction buckets, gain/split/permutation
importance, regime and pressure diagnostics, and the redundancy audit. Feature
importance describes fitted behavior, not causal importance.

## Main Model V2.1 experiment control

Phase 4.1 keeps LightGBM regression and Label V1. It runs one deterministic,
conservative configuration (`seed=42`, learning rate `0.02`, at most 500 trees,
validation early stopping) and performs no hyperparameter search. The 70/15/15
chronological split purges label overlap at both boundaries; test remains
evaluation-only.

The core family runs L0 Phase 3 baseline, L1 price/trend, L2 plus
momentum/volatility, L3 plus volume, L4 plus taker flow, and L5 plus causal
regime/time after deterministic redundancy pruning. The derivatives family
runs D0 core, D1 plus funding, D2 plus aligned mark/index/basis, and D3 plus OI
only if OI legitimately exists. All members of one family share the exact row
identity, split, target, seed, and model parameters. Metrics across the two
different samples are descriptive and are not used as a feature-value claim.

Artifacts include gain, split, and validation permutation importance, moving
block-bootstrap intervals, yearly and regime diagnostics, taker-flow deciles,
and funding buckets derived from training thresholds. Importance from a model
without reliable OOS skill is fitted-model behavior, not proof of predictivity.

## Phase 5 fixed-candidate control

Phase 5 freezes L0 (13 features), L5 (46), matched derivatives-range D0 (46),
and D2 (55). Their ordered schemas are hashed before fitting. The Phase 4.1
LightGBM configuration and seed remain fixed, with validation-only early
stopping and no hyperparameter search.

Each rolling fold adds a distinct calibration segment between validation and
test. Identity and linear calibration candidates are fitted and selected using
calibration rows only. A small predeclared edge-threshold grid is also selected
using calibration-only economics; if 30 calibration trades are unavailable,
`NO_TRADE` is a valid frozen policy. Test becomes available only after model,
calibrator, and policy identities are frozen. A first-fold shuffled-label
negative control shuffles training targets only and cannot be selected.

Pooled test metrics are retrospective walk-forward OOS diagnostics. Moving
block intervals, year/fold/regime stability, feature drift, and prediction
stability are required before qualification. No Phase 5 model result is a live
signal or prospective-holdout result.

## Phase 5.1 calibration ownership

Phase 5.1 leaves the 24/3/3/3 outer geometry, Label V1, candidate feature
hashes, LightGBM bundles, hyperparameters, and validation-only early stopping
unchanged. It performs no model fit. Each saved model predicts Cal-A and Cal-B:
Cal-A fits and selects the small identity/linear calibrator set; Cal-B alone
selects the unchanged edge threshold after a timestamp purge and 60-minute
embargo. Saved TEST raw predictions are recalibrated only after both artifacts
are frozen. TEST cannot influence calibration, threshold, early stopping,
features, hyperparameters, or model selection.

Qualification status (`PASS`/`FAIL`) is deterministic and separate from
evidence interpretation (`NEGATIVE`, `INCONCLUSIVE`, `WEAK_POSITIVE`, or
`PROMISING_UNVALIDATED`). This separation cannot upgrade a candidate or change
the frozen qualification gates.
