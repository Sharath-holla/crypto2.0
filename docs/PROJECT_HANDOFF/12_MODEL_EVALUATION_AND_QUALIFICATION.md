# Model Evaluation and Qualification

## Metrics actually implemented for Phase 7

Phase 7 is a regression experiment. `regression_metrics` reports count, MAE, RMSE, R²,
directional accuracy, Pearson IC, Spearman IC, and prediction/actual mean and standard deviation.
Reports include micro pooled metrics, equal-symbol macro means, per-symbol, per-cluster, TRAIN-end
age buckets, native coverage, matched-architecture coverage, and timestamp-level cross-sectional
Spearman IC (mean/median/positive fraction). Asset and time contribution concentration are also
reported.

Classification metrics—precision, recall, F1, ROC-AUC, PR-AUC, and Brier score—are **not applicable
to the current continuous-return Phase 7A model and are not calculated**. Progress-report fields
for them are null placeholders. Calibration here compares continuous prediction calibrators and
reliability buckets; it is not probabilistic-classification calibration.

## Economics actually implemented

Reports contain threshold choice/`NO_TRADE`, trade count, gross return, configured costs, net
return, summed net return, expectancy, fixed/adaptive cost stress, and asset/time concentration.
The progress schema has placeholders for win rate, profit factor, Sharpe, Sortino, max drawdown,
Calmar, and funding, but Phase 7 `economics.py` does **not** currently compute those fields. Do not
claim they are Phase 7 qualification evidence unless future code implements and tests them.

Coin, fold, horizon, architecture, age/coverage, and cross-sectional stability are evaluated from
the eventual report set. Accuracy alone cannot establish tradability: a candidate must clear
costs with adequate trade and coverage breadth without relying on a small number of symbols,
periods, or folds.

## Current qualification

**Qualified profitable model: NONE.** This means no model can yet be assessed, not that Phase 7A
models failed. Fold 1 is incomplete (0/48), no models are serialized, no fold/OOS scorecard exists,
and no qualification decision is possible.
