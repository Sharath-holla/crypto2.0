# Phase 7 training observer: metrics, units and semantics

Written by Claude (2026-11-08, pre-RunPod hardening). Code: `src/crypto_ai/phase7/training_metrics.py`
(LightGBM callback + telemetry), `training_observer.py` (diagnostics, health, formatting),
`action_metrics.py` (LONG/SHORT definitions), `regression_diagnostics.py` (correlations, IC),
`fit_boundary.py` (fail-closed invariants). Tests: `tests/phase7/test_training_observer_diagnostics.py`.

## 1. What the observer is (and is not)

The primary model is a **regressor** of the forward return. The observer *watches* a fit; it never
steers one.

| Property | Value |
|---|---|
| Rows it can see | TRAIN (loss only) and VALIDATION. Never Cal-A, Cal-B, TEST, July or August. |
| Early stopping | LightGBM's built-in `l2` on VALIDATION (first metric, `first_metric_only=True`). Unchanged. |
| Selection | None. Every record carries `selection_eligible=false`, `independent_evidence=false`. |
| Failure policy | A monitoring failure degrades monitoring (`telemetry_status=DEGRADED`, `diagnostics_status=UNAVAILABLE:*` / `DISABLED_AFTER_REPEATED_ERRORS`); it never fails, alters or completes a fit. |
| Authority | The canonical result ledger. Telemetry is never authoritative. |

Proof by test: `test_diagnostics_never_change_the_fit_or_early_stopping` fits the same data with no
observer and with diagnostics at 1 bps and 50 bps thresholds; `best_iteration_` and every prediction
are bit-identical, and the observer's best round equals LightGBM's.

## 2. Metric classes

* `DEVELOPMENT_METRIC`: train/validation RMSE, MAE, best round, rounds since best, generalization gap.
  Validation already drives early stopping, so these are not independent.
* `DESCRIPTIVE_VALIDATION_DIAGNOSTIC`: Pearson, Spearman, directional accuracy, cross-sectional IC,
  prediction distribution, LONG/SHORT precision/recall/F1, coverage. Descriptive only.
* Never emitted during training: TEST metrics of any kind, PnL, Sharpe, threshold performance.

## 3. Exact metrics shown on the console (every `PHASE7_METRICS_EVERY` rounds, default 25)

| Name | Formula | Split | Units | Frequency | Early stop? | Selection? | Evidence? | Reading |
|---|---|---|---|---|---|---|---|---|
| train RMSE | sqrt(mean((p-y)^2)), unweighted | TRAIN | target units | every check | no | no | no | should fall while learning |
| validation RMSE | same | VALIDATION | target units | every check | **its square (l2) is the stopping metric** | no | no | falling = still generalising; rising while train falls = overfitting |
| validation MAE | mean(abs(p-y)) | VALIDATION | target units | every check | no | no | no | robust error level |
| gap | (val RMSE - train RMSE) / train RMSE | both | ratio | every check | no | no | no | no universal "overfit" value; watch the trend. Train and validation periods differ in volatility |
| best validation RMSE / round / rounds since best | strict-improvement tracking on every round | VALIDATION | target units, rounds | every check | mirrors LightGBM | no | no | rounds since best near `early_stopping_rounds` (50) = stop soon |
| Pearson | linear correlation p vs y | VALIDATION sample | unitless | every check | no | no | no | ~0 = no linear relationship |
| Spearman | Pearson of average ranks | VALIDATION sample | unitless | every check | no | no | no | ~0 = little monotonic ranking signal |
| direction | share of non-zero actuals whose sign the prediction matches; zero prediction = miss | VALIDATION sample | fraction | every check | no | no | no | 0.5 = coin flip; >0.5 is not proof of tradability |
| xs-IC | mean over timestamps (>= 5 assets) of per-timestamp Spearman(p, y) | VALIDATION sample (whole timestamps) | unitless | every 4th check | no | no | no | > 0 = some cross-sectional ordering signal, not proof of profit |
| prediction mean/std/range, std as % of target std, finite % | over finite predictions | VALIDATION sample | target units | every check | no | no | no | std collapsing toward 0 = model predicting ~the mean |
| LONG / SHORT precision, recall, F1, predicted count, support | section 4 | VALIDATION sample | raw-return events | every check | no | no | no | section 6 |
| action coverage / NO_TRADE % / action hit-rate | section 4 | VALIDATION sample | fraction | every check | no | no | no | share of rows that would act at the fixed diagnostic threshold |
| RSS / available RAM / free disk | process RSS, container-aware available RAM, `shutil.disk_usage` of the log dir | n/a | GiB | every check | no | no | no | operational |

"VALIDATION sample": all Validation rows when there are at most `monitor_max_rows` (250,000);
otherwise a fixed-seed sample of **whole timestamps** (seed 20261108), so each sampled cross-section is
complete. The final end-of-fit snapshot uses the same rows with the best-iteration model.

## 4. LONG / SHORT event diagnostics (precise semantics)

Version `action_diagnostics_v1_raw_decimal_inclusive_thresholds`. All comparisons are in **raw decimal
returns** (`0.0005` = 5 bps). Thresholds are predeclared in `configs/phase7/hardening_v1.toml` before
any Validation result is seen and are never optimised:

* `training_diagnostic_event_threshold_bps = 5.0` (E)
* `training_diagnostic_prediction_threshold_bps = 5.0` (P)

The 5 bps default carries over the previously predeclared `fixed_threshold_bps`. It is a *diagnostic*
event size, deliberately below the 11/14/20 bps static cost stress: these diagnostics measure
directional event detection, not profitability.

```
LONG event   actual_raw    >= +E        SHORT event   actual_raw    <= -E
LONG action  predicted_raw >= +P        SHORT action  predicted_raw <= -P
NO_TRADE     every other row
LONG  TP = LONG action & LONG event;  FP = LONG action & not LONG event;  FN = not LONG action & LONG event
precision = TP / LONG actions;  recall = TP / LONG events (= support);  F1 = 2TP / (2TP + FP + FN)
SHORT is the mirror image. A SHORT event in a LONG-action row is a LONG false positive.
action coverage = (LONG + SHORT actions) / valid rows;  NO_TRADE = 1 - coverage
action hit-rate = sign matches among action rows whose actual return is non-zero
macro F1 = mean(LONG F1, SHORT F1), only when both are defined
```

* Ties exactly on a threshold count (inclusive).
* Thresholds must be finite and > 0, so an exact `0.0` return or prediction is never an event or an
  action, and LONG / SHORT can never overlap.
* Rows where either value is non-finite are excluded and counted (`action_rows_excluded_non_finite`).
* MCC / balanced accuracy are not reported: with three action states and two independently defined
  event sides they would need an extra pre-registered class mapping to be meaningful.

## 5. Units: normalized-target models (MR-28 fix)

For `target_type != raw` the model predicts `raw / max(|ex_ante_volatility_scale|, floor)`. Before any
bps threshold is applied, predictions are converted back to raw with the **same** divisor the forward
transform used (`action_metrics.effective_scale_vector`, the vectorised twin of
`targets.effective_normalization_scale`). The divisor is always positive, so the conversion cannot flip
a sign. A unit guard checks, row by row, that `y_fit * divisor == raw_future_return`; a mismatch
(misaligned rows, or a raw/normalised mix-up) disables the diagnostics with
`UNAVAILABLE:TARGET_UNIT_MISMATCH` instead of printing wrong numbers. Tested for scale > floor, == floor,
< floor, == 0 and negative.

RMSE / MAE / correlations / IC are in **target units** (they describe the fitted objective);
LONG / SHORT diagnostics are always in **raw** units. The console labels both.

The old pooled `fixed_precision` / `fixed_recall` LightGBM metrics are removed: they applied a
bps-labelled threshold to normalised values and had to coerce undefined values to `0.0` because a
LightGBM metric must be a float. `hardening.fixed_threshold_precision_recall` is kept as LEGACY only.

## 6. Undefined values

A ratio with a zero denominator is `null` in JSON with a `*_status = NOT_DEFINED` and a reason
(`NO_PREDICTED_LONG_ACTIONS`, `NO_ACTUAL_SHORT_EVENTS`, ...), and `N/A` on the console. It is never
`0.0`. A `0.0` that is printed is a genuine zero (for example, actions were taken and none were right).
Support counts are always printed next to the ratios. Correlations of constant inputs, fewer than two
rows, or an IC with too few assets per timestamp are likewise `null`/`N/A`.

## 7. Telemetry (append-only JSONL, schema `training_telemetry_v1`)

One file per fit attempt: `<log_root>/<run_identity>/<fold>/<spec>/fit-<attempt_id>.jsonl`, fsynced per
record. Events: `FIT_STARTED` (attempt number, prior attempts, `resumed_after_incomplete_attempt`),
`DIAGNOSTICS_BOUND` (definitions, settings, row counts), `FIT_METRICS`, `TRAINING_TELEMETRY`,
`VALIDATION_DIAGNOSTICS`, `DIAGNOSTICS_ERROR`, `FIT_FINISHED` (training summary) or `FIT_FAILED`.

`TRAINING_TELEMETRY` (class `DEVELOPMENT_METRIC`): timestamp, check_id (`attempt:iteration`, unique),
iteration, round_limit, elapsed_seconds, spec_id, fold_id, architecture, target, horizon, backend,
train_rmse, validation_rmse, validation_mae, train_l2, validation_l2, best_iteration,
best_validation_score, rounds_since_best, relative_generalization_gap, learning_rate, cpu_threads,
train_rows, validation_rows, feature_count, rss_bytes, effective_memory_available, disk_free_bytes,
health, telemetry_status, diagnostics_status.

`VALIDATION_DIAGNOSTICS` (class `DESCRIPTIVE_VALIDATION_DIAGNOSTIC`): validation_pearson,
validation_spearman, validation_directional_accuracy, prediction_mean/std/min/max/q01..q99,
finite_prediction_fraction, prediction_near_zero_fraction, xs_* fields, long_/short_ precision,
recall, f1, *_status, *_reason, support, predicted_count, TP/FP/FN, action_coverage,
no_trade_coverage, action_hit_rate, macro_f1, thresholds, units, diagnostic_rows / total / subsampled.

Resume: a new attempt always writes a new file and never appends to an old one, so rounds cannot be
duplicated inside a file; `FIT_STARTED` lists earlier attempts and whether they reached
`FIT_FINISHED`. A telemetry write failure prints one `TELEMETRY_DEGRADED` line and the fit continues;
no telemetry record can mark a model complete (completion is the ledger + receipts).

The training report (`phase7b.training_observer`) carries only the deterministic part of the
end-of-fit summary (`training_observer.report_view`); attempt ids, log names, timings, resource
flags and telemetry I/O status stay in the JSONL so that a rerun reproduces the same report.

## 8. Health labels (heuristic)

Per check, classified `HARD_FAILURE` / `WARNING` / `INFORMATIONAL`: `NON_FINITE_METRICS`,
`NON_FINITE_PREDICTIONS` (hard: invariant violations, and the post-fit boundary also fails closed),
`TRAIN_VALIDATION_GAP_HIGH`, `PREDICTIONS_NEAR_CONSTANT`, `PREDICTION_VARIANCE_COLLAPSE`,
`OVERFITTING_PATTERN`, `MEMORY_PRESSURE`, `DISK_PRESSURE` (warnings), `VALIDATION_LOSS_IMPROVING`,
`VALIDATION_LOSS_PLATEAU` (informational). End of fit: one of `LEARNING_SIGNAL_PRESENT`,
`WEAK_LEARNING_SIGNAL`, `NO_CLEAR_VALIDATION_IMPROVEMENT`, `SEVERE_GENERALIZATION_GAP`,
`PREDICTION_COLLAPSE`, `INSUFFICIENT_DATA`, always with the numbers and thresholds that produced it.
All thresholds (`health_*`) are configurable operational heuristics: not tuned, not significance
tests, never used to stop, select or tune a fit.

## 9. Settings and identity

| Setting | Class | Unit | Identity effect |
|---|---|---|---|
| `training_diagnostic_event_threshold_bps`, `training_diagnostic_prediction_threshold_bps` | DIAGNOSTIC_DEFINITION | bps of raw return | experiment-control identity only |
| `monitor_*`, `health_*`, `console_*`, `PHASE7_METRICS_EVERY`, log location | MONITORING | rows / checks / ratio / GiB / rounds | none |
| `fixed_threshold_bps`, `metric_max_rows` | LEGACY (unused) | | none |
| `baseline_*` | BASELINE | | experiment-control identity |
| LightGBM parameters (`[models]` in the research TOML) | MODEL | | configuration hash -> model and checkpoint identity (and, conservatively, the prepared-cache key) |

No hardening setting enters the prepared-matrix identity (tested). `observer` modules are not in
`PREPARATION_SOURCE_FILES`. The resolved monitoring settings (value, default, unit, class, source) are
written to `DIAGNOSTICS_BOUND` and to the training report (`resolved_monitor_settings`).

## 10. Interpreting what you see (beginner guide)

* Train and validation RMSE both falling: still learning.
* Train falling, validation rising (and `OVERFITTING_PATTERN`): generalisation is deteriorating; early
  stopping will keep the best round, so nothing needs to be done during the run.
* Validation flat for many rounds (`rounds since best` climbing to 50): plateau; early stopping ends it.
* Validation RMSE only marginally below the zero-predictor RMSE is normal for return forecasting; the
  end-of-fit label and the post-fit baselines (zero, TRAIN-mean, matched Ridge) give the comparison.
* Spearman / IC near zero: little ranking signal. Positive IC: some cross-sectional ordering signal,
  **not** proof of profit.
* Prediction std a tiny % of target std: the model is close to predicting the mean; expected early in a
  fit at learning rate 0.02, worrying only if it persists to the best round.
* High precision, low recall: the few actions it takes are often right, but it misses most events.
* High recall, low precision: it catches many events but acts too often.
* `N/A` precision with `predicted 0`: the model never crossed the diagnostic threshold; that is not a
  zero score.
* High directional accuracy with no net expectancy is common and is not tradability. Economics are
  `NOT QUALIFIED DURING TRAINING`; funding is `NOT_MODELLED`.

## 11. Cost

Measured on a synthetic 109-feature fixture (single thread); see the pre-RunPod review report for the
numbers. The in-fit prediction is a full LightGBM `predict` at the current iteration on at most
250,000 Validation rows, once per check (every 25 rounds by default), and allocates only the prediction
vector (the sample matrix is copied once per estimator). Cross-sectional IC is vectorised and
computed every 4th check.
