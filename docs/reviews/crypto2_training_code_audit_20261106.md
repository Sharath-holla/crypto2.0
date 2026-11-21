> **Independent audit update:** The earlier audit below is preserved from concurrent commit
> `c249e28`. The appended independent source trace, executed evidence and verdict supersede
> conflicting earlier assertions. No production code was changed by this audit.

# Crypto 2.0: training-code audit (2026-11-06)

Audited tip: `687e697` on `fix/phase7a-final-scientific-hardening-20261106`. Labels: CODE-VERIFIED =
read in source this session or earlier sessions of this engagement; INFERENCE; OPINION. I did not
execute training and the Mac test runner was offline, so nothing here is TEST-EXECUTED on the tip.

## Verdict: TRAINING_CODE_CORRECT_WITH_MINOR_ISSUES (with three stated limits)
Limits: (1) never run end-to-end on real data in this audit; (2) M-01 edge size not measured;
(3) not every one of the 109 feature formulas was re-derived line by line (HTF completeness and
target timing were).

## Timing (CODE-VERIFIED, `phase7/targets.py`, `phase6/labels.py`)
- `feature_time = open_time[i] + 5m` (= open of bar i+1; bar i is complete).
- `entry_offset = 1 + decision_latency_bars` -> entry at `open[i+2]` for the default of 1 latency bar;
  a hard check requires `entry_time == feature_time + 5m`.
- `label_end = open[i + entry_offset + steps]`; raw return `open[label_end] / open[entry] - 1`.
- Rows need `consecutive >= target_offset` bars (no label across a gap) and `label_end < cutoff`.
- Horizons 15/30/60/120 min = 3/6/12/24 steps. Embargo 120 min; purge uses `label_end_time`.
Assessment: matches the stated formula. Entry one full bar after the decision is conservative
against realistic API latency (seconds). Residual: fills at the open price with no spread/queue
effects other than the flat tier costs.

## What enters each stage
| Stage | Rows | Owner of the data |
| --- | --- | --- |
| LightGBM fit | Train only | Train |
| Early stopping + (H0) correction | Validation | Validation (H0 shares it: L-04, documented) |
| Calibrator | Cal-A (method picked on last 25% of Cal-A, refit on all) | Cal-A |
| Thresholds | Cal-B, non-overlapping per-symbol policy, min 30 trades | Cal-B |
| Final metrics | Test, released once under a frozen identity | Test |
Test access is logged and the frozen identity is re-derived before release (CODE-VERIFIED, M-02).

## LightGBM parameters (CODE-VERIFIED in `config.ModelConfig`, `models.lightgbm_estimator_parameters`)
Reference: [LightGBM Parameters Tuning](https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html) (LEVEL B).
| Parameter | Value | Rating | Comment |
| --- | --- | --- | --- |
| objective | regression (L2) | QUESTIONABLE | Squared loss is dominated by heavy-tailed returns; no winsorisation was verified. Huber/clipped target is a candidate ablation, not a blocker |
| boosting | gbdt (default) | DEFAULT_BUT_ACCEPTABLE | |
| learning_rate | 0.02 | GOOD | Small step suits noisy targets |
| n_estimators | 500 (max 2000) | QUESTIONABLE | With lr 0.02 the cap may bind before the validation optimum on easy folds; early stopping decides |
| num_leaves | 31 | DEFAULT_BUT_ACCEPTABLE | |
| max_depth | -1 | DEFAULT_BUT_ACCEPTABLE | |
| min_child_samples | 100 | **POOR for this data size** (INFERENCE) | Millions of low-SNR rows; 100 samples per leaf lets leaves fit noise. Typical guidance for noisy tabular data is far larger; treat as a sensitivity axis |
| subsample / freq | 0.9 / 1 | GOOD | |
| colsample_bytree | 0.9 | DEFAULT_BUT_ACCEPTABLE | Many correlated features; 0.5-0.7 would add diversity (sensitivity axis) |
| reg_alpha / reg_lambda | 0.1 / 1.0 | QUESTIONABLE | Weak for noisy returns |
| early_stopping_rounds | 50 | GOOD | with lr 0.02 reasonable; first_metric_only on L2 |
| seed | `random_state=42` only | QUESTIONABLE | One seed hides variance; bagging/feature seeds derive from it |
| deterministic / force_col_wise | CPU only | GOOD | GPU path is "scientifically, not bitwise" reproducible and records it |
| max_bin, min_gain_to_split, min_sum_hessian | defaults | DEFAULT_BUT_ACCEPTABLE | |
| categorical / monotone constraints | none; symbol-id only as an ablation | GOOD | |
| sample weights | optional symbol-balanced weights | UNJUSTIFIED until compared | exists as a compare option |
Not claimed: that these values are wrong. Hyperparameters were not tuned and no evidence says they are optimal.

## Findings specific to the training path
1. (MEDIUM) One seed per spec; seed variance is invisible. 2. (MEDIUM) L-04: H0 correction fit on the early-stopping set. 3. (MEDIUM) M-01 residual: rows removed by Gold's label inner join near series ends are not counted. 4. (LOW) results table lacks seed, fit seconds, best iteration columns. 5. (LOW) CPU vs GPU equivalence untested. 6. (INFO) Source-hash cache identity means any further code edit invalidates caches: freeze code before the first paid run.

## Model choice (OPINION, with evidence in the literature file)
Keep LightGBM as the primary model family, and add a Ridge baseline (already in the code) and
a simple cross-sectional-rank baseline. Do not add deep sequence models before a baseline signal exists.


---

# Independent training-code assessment

**Verdict: TRAINING_CODE_HAS_MATERIAL_RISKS.** The isolated default CPU G0 fitting/timing sequence is
coherent, and the synthetic contract suite passes. That does not certify data-dependent context
completeness, resume compatibility of added controls, statistical selection or economic validity.
It would overstate the evidence to call the whole training/evaluation system correct with only
minor issues. Nothing found demonstrates that all prior phases or the G0 regression algorithm
must be discarded.

Evidence is **CODE-VERIFIED** for the source trace and **DATA-VERIFIED (SYNTHETIC)** for computations.
Scientific code at `687e697530bdaecd9d981b3541a7bb60182925ff` did not change through documentation
commit `c249e285248c12d6d97e1a9be3d4c4625b37f258`. The starting HEAD was `0eb9296`; concurrent
commits `d3c8da7` and `687e697` incorporated working-tree monitoring/metrics changes and a resource
estimator. See the evidence source snapshot for file hashes. This is a function/block trace of the
active critical path, not a claim every legacy line in the repository is proven correct.

## Exact path: architecture-G0-A6-60m-raw

```text
crypto-ai phase7-research (cli.main)                         [generic route]
  -> pipeline.run_phase7_cloud(stage=train)
     -> _load_stage_state -> _fold_descriptors
     -> training.run_phase7_training -> owned_run lease
        -> _run_phase7_training_owned
           -> _load_gold_manifest -> resolve_training_scope
           -> load_payload closure / PreparedDataCache.load
              MISS: _load_fold_rows(horizon=60)
                    _load_fold_context_source(all four horizons)
                    slice_multiasset_fold
                    _prepare_training_segments
                    cache.write / open_published
           -> _run_one
              -> fit_architecture(G0, prepared_inputs)
                 -> symbol_balanced_weights
                 -> _fit -> _estimator -> LGBMRegressor
                    -> fit_with_device_evidence -> estimator.fit
              -> model.predict(Cal-A) -> fit_calibrator
              -> model.predict(Cal-B) -> calibrator.apply -> select_cal_b_thresholds
              -> freeze(model + calibrator + thresholds)
              -> release_test -> finite TEST -> predict -> raw evaluation
              -> build_oos_trades -> fixed/adaptive stress
              -> validation baselines + signal/trade diagnostics
              -> save_model -> receipt -> registry -> immutable report -> CSV
           -> checkpoint.complete -> fold/experiment summaries
```

The canonical Phase7A script dispatches to the same scientific code with `scope=phase7a`; exactly
48 A6 primary specs, CORE only. `benchmark_one_spec.py` / `phase7a.select_one_spec` selects the named
spec and first canonical fold in isolated BENCHMARK_ONLY artifacts. A pilot horizon/target filter
in hardening.py still selects six architecture/control variants, **not one model**. Do not confuse
one horizon×target pilot with the requested one-spec smoke. The generic CLI's admission is weaker
than the newer Phase7A/benchmark script (IA-11).

## Ownership and line-level contracts

| Function/block / approximate lines | Exactly what enters and leaves | Time/row contract | Leakage, failure and identity assessment |
| --- | --- | --- | --- |
| `training._load_gold_manifest`, 389–408 | Manifest path -> resolved file records | Requires locked holdout flags, July false; hashes all listed partitions | Hashes verify matching bytes; no proof the list is complete. Stronger byte/schema validator is a separate preflight prerequisite. |
| `_load_fold_rows`, 425–453 | Manifest/Arrow Dataset/plan/horizon -> sorted Arrow table | `[train_start,test_end)`, one horizon; partition-year pruning; sort feature_time,symbol | Loads later segments physically before fit; ownership is maintained by subsequent slicing, not physical read isolation. |
| `_load_fold_context_source`, 456–483 | All four horizon projections -> unique symbol,time feature context | No label values projected; same outer fold interval | Original preview count/hash must agree before fold membership filtering. Detects partial union omissions; IA-05 limits remain. |
| `universe.latest_descriptors`, 240–251; `select_fold_active_universe`, 565–709 | Registry + all descriptors -> cutoff-known active members/hash | Only as_of<=TRAIN end; known TRAIN-history gap gate | Post-TRAIN gaps do not remove hard symbols from past membership; later gaps stop the fold. Actual archive completeness unknown. |
| `folds.slice_multiasset_fold`, 269–432 | One-horizon table + context + PIT metadata -> five segments, mapping/tiers | Bind active-symbol context; slice; actual endpoint purge; 120m later-segment gap | Duplicate feature keys rejected during binding. Typed later-gap error is a defect, never INELIGIBLE. |
| `phase5.slice_hardened_fold`, 241–354 | Eligible table/plan -> Train,Val,Cal-A,Cal-B,Test | Cal midpoint by elapsed UTC time; prior label_end strictly < next raw boundary | TEST has no next fold-local segment purge, but generated labels must stay before global cutoff. Per-fold TEST periods do not overlap; roles across folds do. |
| `_finite`, 505–512 | Table, ordered feature names, target -> all-finite rows | Selected features plus selected target only; null becomes false | Does not fill missing features; does condition evaluation population on availability of target. Counts preserved. No extra target-column names in A6. |
| `_prepare_training_segments`, 515–558 | Fold + A6 + raw_future_return -> four filtered tables + X/y/symbols | Asserts FOLD_ACTIVE_SYMBOLS for pre-TEST segments; preserves row order | TEST prefilter row count inspected, no TEST predictions/selection; matrix-boundary checkpoint exists in current code. |
| `models._matrix`, 46–59; `prepare_architecture_inputs`, 76–101 | Arrow columns -> float64 N×109 arrays, aligned y/symbol vectors | Preallocated column-by-column; numeric arrays checked finite | No model-facing global scaler. Symbol levels, where used, derive from TRAIN. |
| `models.symbol_balanced_weights`, 104–113 | TRAIN symbols -> inverse-count weights normalized to mean 1 | No return magnitudes or future rows | Same total fit weight per TRAIN symbol; rationale is equal-symbol estimand, not guaranteed optimality. |
| `fit_architecture`, 333–524 | Train/Val/config/prepared inputs -> global estimator for G0 | Raw target; primary G0 balanced=true, explicit_symbol_id=false | Prepared names, shapes and symbol lengths checked. Normal G0 does not consume Cal-A labels or Cal-B. P0 uses Cal-A counts for eligibility, an explicit design distinction. |
| `_fit`, 142–199; `backend.lightgbm_estimator_parameters`, 88–128 | X/y, optional weights, Val X/y -> fitted estimator | Default squared loss; Validation L2 early stopping; no shuffle in row assembly | LightGBM constructs internal Dataset/binning via sklearn wrapper. No manual fit of a scaler on Val/Test. Optional abort depends on Validation; added hardening semantics not resume-bound. |
| `training_metric_scope` / `display_metrics`, 46–85 | Existing training/eval predictions -> metrics/log callback | Train/Val only; no repeated model.predict per boosting iteration | First L2 metric remains stopping criterion; normalized-target bps diagnostics mislabeled (IA-18). |
| `model.predict`, models.py 290–330 | Segment -> predicted vector and coverage bool | Same ordered features; G0 covers all finite rows | C0/P0 uncovered predictions are NaN with coverage false; covered nonfinite predictions fail. |
| `phase5.fit_calibrator`, 78–143 | Covered Cal-A prediction,target vectors -> identity or affine map | Fit candidates; choose on final quarter row slice; refit all Cal-A | No Cal-B/Test used; internal split not timestamp/purge safe (IA-13). Method chosen by MAE, affine coefficients by least squares. |
| `_to_raw_predictions`, 653–666 | Calibrated target-unit values + stored scale -> raw return | Raw path is identity | Floored normalization inverse mismatch only affects normalized path (IA-17). |
| `economics.select_cal_b_thresholds`, 120–196 | Cal-B raw predictions/outcomes + frozen tiers/clusters -> thresholds | Same non-overlap policy as TEST; five thresholds, >=30 trades, maximize mean net expectancy, higher threshold wins tie | No model or calibrator refitting; all-negative eligible candidates still produce a threshold (IA-15). G0 global, C0/H0 cluster, P0 per coin. |
| `_frozen_test_identity_components`, 697–704; `fold.release_test`, 89–135 | Frozen components -> audited TEST release | Re-derive digest, record consumer and range | Allows repeated same-identity access. Does not prove no external caller touched _test; ledger measures that API, not all possible data reads. |
| `_run_one`, 1179–1318 | Filtered TEST predictions -> errors, IC, trades, stresses, report | Predictions calibrated with pre-TEST objects; all metrics in raw units | No code feedback from TEST into fit/threshold found. Human post-result adaptation is outside this guard. |
| `_run_one`, 1338–1367; `save_model`, 626–640 | Bundle/report -> joblib/receipt/JSON/CSV | Save refuses existing file; temp+fsync+replace; hashes included | Native booster lives inside joblib. CSV and report/checkpoint are not one atomic transaction (IA-20). |
| Training loop resume, 1813–1920 | Completed checkpoint/report/model -> reuse or error | Checks scientific input identity, report identity, receipt and model bytes | Strong main source checks; hardening module/active settings omitted (IA-04). |
| `_report_stage`, pipeline.py 712–771 | Complete per-fold reports -> retrospective scorecard | Mean macro TEST Spearman, mean coverage, total trades, average estimator complexity | Explicitly sets qualified_model=NONE, model_qualification_performed=false. No implemented automated final champion approval. Separate hardening CLI ranks Validation. |

No future target, entry/exit timestamp, MFE/MAE or helper lineage column is in the mechanically
enumerated 109 A6 inputs. Float64 conversion is explicit at the feature/research boundary; Bronze
market decimals remain exact. Arrow finite filtering and stable sorting preserve symbol/label
alignment. Joins: feature keys are unique; targets are unique per symbol,time,horizon; Gold intentionally
replicates each feature row across available horizons. This is not 50M independent observations.

## LightGBM settings and classification

Values below were checked against `backend.py`, config and installed LightGBM **4.7.0**. The installed
`LGBMRegressor.fit` signature accepts `eval_X` and `eval_y`; this audit inspected the signature rather
than assuming the older wrapper API. Official references: [estimator API](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRegressor.html),
[parameters](https://lightgbm.readthedocs.io/en/stable/Parameters.html),
[tuning](https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html),
[early stopping](https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.early_stopping.html).
Classifications are **OPINION/RECOMMENDATION**, not measured optimality judgments.

| Parameter | Effective setting | Classification | Assessment |
| --- | --- | --- | --- |
| objective / metric | regression / default L2 | GOOD | Valid expected-return baseline; supplement with robust/decision metrics rather than assuming L2 yields alpha. |
| boosting_type | gbdt default | DEFAULT_BUT_ACCEPTABLE | Ordinary baseline. |
| num_leaves | 31 | DEFAULT_BUT_ACCEPTABLE | Capacity limit, not unlimited trees. |
| max_depth | -1 | QUESTIONABLE | Leaves still cap capacity; unlimited path depth warrants later sensitivity, not a claim trees are certainly too deep. |
| learning_rate | .02 | GOOD | Conservative starting step; not empirically selected. |
| n_estimators | 500 ceiling | UNJUSTIFIED | Monitor cap-binding. The config validator's allowable maximum does not make the actual run 2000 trees. |
| min_data_in_leaf / min_child_samples | 100 | QUESTIONABLE | Not independent effective sample size; cannot call POOR solely because there are millions of correlated rows. |
| min_sum_hessian_in_leaf / min_child_weight | .001 default | DEFAULT_BUT_ACCEPTABLE | Record as an explicit effective default. |
| feature_fraction / colsample_bytree | .9 | DEFAULT_BUT_ACCEPTABLE | Mild feature subsampling. |
| bagging_fraction / subsample | .9 | DEFAULT_BUT_ACCEPTABLE | Active because frequency is nonzero; does not decorrelate financial labels for inference. |
| bagging_freq / subsample_freq | 1 | GOOD | Sampling enabled. |
| lambda_l1 / reg_alpha | .1 | UNJUSTIFIED | No evidence of optimality; loss/target scale affects penalty meaning. |
| lambda_l2 / reg_lambda | 1 | UNJUSTIFIED | Same caveat; raw/normalized comparisons change effective regularization. |
| max_bin | 255 default | DEFAULT_BUT_ACCEPTABLE | GPU speed advice is not authorization to alter frozen bins. |
| min_gain_to_split / min_split_gain | 0 default | DEFAULT_BUT_ACCEPTABLE | No verified failure from this default. |
| verbosity | -1 | GOOD | Observer/telemetry supply actionable logs, but retain errors. |
| seed / random_state | 42 | GOOD | One reference seed; sensitivity is later evidence, not missing default seeding. |
| feature_fraction_seed | derived via main seed; not separately set | DEFAULT_BUT_ACCEPTABLE | Record resolved booster settings if qualifying exact binaries. |
| bagging_seed | derived via main seed; not separately set | DEFAULT_BUT_ACCEPTABLE | Separate seed experiments only under a registered plan. |
| data_random_seed | derived via main seed; not separately set | DEFAULT_BUT_ACCEPTABLE | Main seed lower priority if a future explicit component seed is supplied. |
| deterministic / force_col_wise | true / true on CPU | GOOD | Reproducibility is scoped to compatible binaries/environment; no cross-machine bitwise guarantee. |
| num_threads / n_jobs | ComputeBudget-resolved; G0 can use pooled worker×thread budget | GOOD | Not simply always four threads; verify container-visible limits. |
| device_type | cpu unless env override | GOOD for CPU; QUESTIONABLE operational GPU override | GPU path attests actual device, but approval ladder is not enforced at fit admission. |
| GPU double accumulation | gpu_use_dp=true for OpenCL | GOOD | Separate CUDA implementation; equivalence still requires measured evidence. |
| categorical features | none; optional TRAIN-known one-hot symbols | DEFAULT_BUT_ACCEPTABLE | No arbitrary numeric symbol encoding in primary G0. |
| monotone_constraints | absent | DEFAULT_BUT_ACCEPTABLE | No empirically justified monotonic return restriction is established. |
| sample weights | inverse TRAIN symbol count, mean 1 | GOOD for equal-symbol estimand | Compare unbalanced control on identical rows; weights do not use future returns. |
| stopping | 50 rounds, first_metric_only=true, min_delta default 0 | DEFAULT_BUT_ACCEPTABLE | Training eval set ignored by LightGBM stopping. Best iteration is saved; Val is development, not an untouched statistical test. |

No setting is proven optimal or proven too shallow/deep from source alone. A measured small
pre-TEST sensitivity study may help later, but is not necessary to run dozens of variants before a
basic engineering smoke. Model choice and objective alternatives are compared in the main report.

## Independently reconstructed target timing

For source candle `i=30`, source open=02:30 UTC, completed feature=02:35, entry=02:40 (`i+2`):

| Horizon | Steps | Entry | Label end | Expected raw return (synthetic) |
| --- | ---: | --- | --- | ---: |
| 15m | 3 | 02:40 | 02:55 | -0.0000470338779887 |
| 30m | 6 | 02:40 | 03:10 | -0.0001488680601731 |
| 60m | 12 | 02:40 | 03:40 | -0.0004916533672892 |
| 120m | 24 | 02:40 | 04:40 | -0.0014856645338033 |

Every value equals `opens[32+steps]/opens[32]-1` within 1e-15 absolute tolerance. Source date is
2021-01-01; no forbidden market period was read. No interpolation or fabricated real market rows
were used: these are explicitly synthetic unit-probe inputs. Entry timing is causal in the bar
model; an execution-price guarantee is not inferred.

Normalized label uses a causal **5m-return standard deviation over 288 rows**, despite the name
`daily_volatility`. It is not an annualized/daily-horizon standard deviation. Scaling all horizons
by that same historical scale is a valid target transformation but is not a horizon-specific risk
forecast. Raw targets remain a sensible first baseline.

## Metric definitions and edge behavior

MAE=`mean(abs(pred-actual))`; RMSE=`sqrt(mean(error²))`; R² uses centered actual SSE denominator,
returning None at zero target variance. This R² is not out-of-sample skill versus zero: the separate
`lightgbm_skill_vs_zero` is `1 - RMSE_model/RMSE_zero`, not `1 - MSE_model/MSE_zero`.
Pearson/Spearman return None at constant inputs or fewer than two samples; rank ties are averaged.
Empty/nonfinite vectors raise. All-zero actual direction returns 0.0 by explicit convention and is
counted; treat that case as no directional evidence. Reliability-bucket hit rate still counts
zero/zero matches, so it differs from the main zero-excluding directional score.

Cross-sectional IC groups exact feature timestamps, requires >=3 distinct symbols, discards
nonfinite pairs, averages tied ranks and then averages valid timestamps equally. Constant groups
are omitted, and there is no standard error/dependence correction. Feature cross-sectional
percentiles instead break ties by stable source order (not average rank). That is a deterministic
semantic choice with possible arbitrary symbol-order structure, not a future leak.

For LONG event `E_L={actual_raw > round_trip_cost}` and frozen signal
`S_L={pred_raw*10000 >= cost_bps + threshold_bps}`: TP=|S_L∩E_L|, FP=|S_L∩¬E_L|,
FN=|¬S_L∩E_L|, TN=|¬S_L∩¬E_L| on finite covered rows. SHORT mirrors signs. Precision=TP/(TP+FP),
recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN). Specificity=TN/(TN+FP), balanced accuracy=(recall+specificity)/2,
MCC=(TP·TN-FP·FN)/sqrt((TP+FP)(TP+FN)(TN+FP)(TN+FN)); undefined denominators must remain undefined.
The last three are not currently reported by this path. These are two one-v-rest **signal-level**
events, not a natural three-class “true no-trade” label and not executed trade precision after
non-overlap. Hit rate, coverage, expectancy, cost stress and concentration are more directly
interpretable for this exploratory execution policy. Do not optimize F1 as proof of returns.

Trade win rate excludes exactly-zero net returns. Profit factor returns None with no losses
(including all wins); one-trade/constant-return per-trade Sharpe is None. Drawdown is additive and
ordered by exit, not a mark-to-market funded portfolio. Sortino and Calmar are not implemented in
this Phase7 path. The reports' fixed-policy stress maintains the same IDs, a useful safeguard.

## All 109 production inputs: formula-level inventory

Source: phase7/features.py and phase6/features.py `_higher_timeframe_values`, including the
underlying baseline EMA/RSI helpers. The list below is generated in exact `production_a6_model_columns`
order and checked against the source schema. It describes formulas, not measured feature value
coverage or importance. Physical producer order differs from model A6 grouping order.

Conventions: C/O/H/L = completed source candle values; Q = quote volume; N = trade count; B = taker
buy quote volume; r_k=C/C_lag(k)-1; s_n = sample std (ddof=1) of completed log returns; m_n = full
window mean; z_n=(value-m_n)/std_n. EMA seeded with the first full-window mean; RSI uses Wilder-style
recursive gain/loss means. All windows include the current **completed** candle and past only.
Ratios require finite, nonzero denominators; insufficient history/invalid denominators remain NaN
and the selected A6 row is removed rather than filled. HTF geometric ratios can be nonfinite and
are likewise rejected downstream. Native rolling transforms reset at candle gaps, except pair
statistics' observed-row windows (IA-22). No time/calendar, order-book, open-interest, sentiment or
size/market-cap feature is secretly present in this inventory.

**Availability rules shared by every row:** N5 native rows use data completed by `feature_time =
source open+5m`. X5 cross-section is exact-time across frozen eligible symbols; missing/nonfinite
members are excluded per statistic, no forward/back fill. A5 anchor features join an exact-time
completed BTC/ETH row. H12/H24 use the last completed direct 12h/1d candle with
`availability=open+interval <= feature_time < valid_until=open+2*interval`; no unfinished candle's
final OHLCV is joined. D5 derivatives use their source availability (funding event; mark/index
close), stale funding >24h or mark/index >5m becomes missing. Maximum age is a context
observability assumption, not synthesized candles. Lookback below is in **source bars**, unless
specified otherwise. Warm-up additionally requires source existence, contiguous history, finite
values and all component warm-ups; recursive EMA state depends on its seed history.

| # | Feature | Family / timing rule | Formula / lookback and warm-up |
| ---: | --- | --- | --- |
| 1 | `return_5m` | return / N5 | C/C_lag(1)-1; needs 2 bars |
| 2 | `return_15m` | return / N5 | C/C_lag(3)-1; needs 4 bars |
| 3 | `return_30m` | return / N5 | C/C_lag(6)-1; needs 7 bars |
| 4 | `return_1h` | return / N5 | C/C_lag(12)-1; needs 13 bars |
| 5 | `return_4h` | return / N5 | C/C_lag(48)-1; needs 49 bars |
| 6 | `range_pct` | range / N5 | (H-L)/O; current bar |
| 7 | `body_pct` | price / N5 | (C-O)/O; current bar |
| 8 | `atr14_pct` | volatility / N5 | mean14(max(H-L,abs(H-C_prev),abs(L-C_prev)))/C; 14 valid TRs |
| 9 | `ema20_distance_pct` | trend / N5 | C/EMA20(C)-1; 20-bar seed |
| 10 | `realized_volatility_1h` | volatility / N5 | s12(log(1+r1)); 12 finite returns |
| 11 | `daily_volatility` | volatility / N5 | s288(log(1+r1)); 288 finite 5m returns |
| 12 | `seven_day_volatility` | volatility / N5 | s2016(log(1+r1)); 2016 finite returns |
| 13 | `relative_quote_volume` | volume / N5 | Q/m2016(Q); full 2016 bars |
| 14 | `volume_zscore` | volume / N5 | z2016(Q); positive rolling std |
| 15 | `trade_count_zscore` | activity / N5 | z2016(N); positive rolling std |
| 16 | `taker_buy_share` | executed flow / N5 | B/Q; current bar |
| 17 | `taker_sell_share` | executed flow / N5 | 1-B/Q; current bar |
| 18 | `taker_flow_imbalance` | executed flow / N5 | 2B/Q-1; current bar |
| 19 | `return_5m_over_ex_ante_vol` | normalized return / N5 | r1/s12; both finite/nonzero scale |
| 20 | `return_1h_over_daily_vol` | normalized return / N5 | r12/s288; both finite/nonzero scale |
| 21 | `return_4h_over_7d_vol` | normalized return / N5 | r48/s2016; both finite/nonzero scale |
| 22 | `listing_age_days` | lifecycle / N5 | (feature_time-registry.causal_available_from)/86400s; identical formulas; in-lifecycle only |
| 23 | `history_length_days` | lifecycle / N5 | (feature_time-registry.causal_available_from)/86400s; identical formulas; in-lifecycle only |
| 24 | `trailing_liquidity_percentile` | liquidity rank / X5 | timestamp-local stable rank of m2016(Q), divided by max(1,members-1) |
| 25 | `trailing_volatility_percentile` | volatility rank / X5 | timestamp-local stable rank of s2016, same denominator |
| 26 | `trade_intensity_percentile` | activity rank / X5 | timestamp-local stable rank of N/m2016(N), same denominator |
| 27 | `btc_beta` | relative / A5 | cov(r1,BTC r1)/var(BTC r1), ddof1; 2016 paired observed rows |
| 28 | `btc_correlation` | relative / A5 | corr(r1,BTC r1); 2016 paired observed rows; constant -> NaN |
| 29 | `eth_correlation` | relative / A5 | corr(r1,ETH r1); 2016 paired observed rows; constant -> NaN |
| 30 | `relative_strength_vs_btc` | relative momentum / A5 | r12 - exact-time BTC r12; 13-bar returns |
| 31 | `relative_strength_vs_eth` | relative momentum / A5 | r12 - exact-time ETH r12; 13-bar returns |
| 32 | `beta_adjusted_residual_return` | relative / A5 | r12 - btc_beta * BTC r12; trailing beta, not future residual label |
| 33 | `btc_return_5m` | anchor / A5 | BTC C/C_lag(1)-1, exact feature timestamp; 2 bars |
| 34 | `btc_return_15m` | anchor / A5 | BTC C/C_lag(3)-1, exact feature timestamp; 4 bars |
| 35 | `btc_return_30m` | anchor / A5 | BTC C/C_lag(6)-1, exact feature timestamp; 7 bars |
| 36 | `btc_return_1h` | anchor / A5 | BTC C/C_lag(12)-1, exact feature timestamp; 13 bars |
| 37 | `btc_return_4h` | anchor / A5 | BTC C/C_lag(48)-1, exact feature timestamp; 49 bars |
| 38 | `btc_volatility_1h` | anchor volatility / A5 | BTC s12, exact feature timestamp |
| 39 | `btc_taker_flow_imbalance` | anchor flow / A5 | BTC 2B/Q-1, exact feature timestamp |
| 40 | `eth_return_5m` | anchor / A5 | ETH C/C_lag(1)-1, exact feature timestamp; 2 bars |
| 41 | `eth_return_1h` | anchor / A5 | ETH C/C_lag(12)-1, exact feature timestamp; 13 bars |
| 42 | `eth_return_4h` | anchor / A5 | ETH C/C_lag(48)-1, exact feature timestamp; 49 bars |
| 43 | `eth_volatility_1h` | anchor volatility / A5 | ETH s12, exact feature timestamp |
| 44 | `market_mean_return` | market context / X5 | mean finite member r1 at timestamp |
| 45 | `market_median_return` | market context / X5 | median finite member r1 at timestamp |
| 46 | `market_pct_positive` | market context / X5 | count(r1>0)/count(finite r1) |
| 47 | `market_pct_negative` | market context / X5 | count(r1<0)/count(finite r1) |
| 48 | `market_return_dispersion` | market context / X5 | population std of finite r1 (ddof0) |
| 49 | `market_median_volatility` | market context / X5 | median finite member s12 |
| 50 | `market_median_taker_flow_imbalance` | market context / X5 | median finite member (2B/Q-1) |
| 51 | `market_member_count` | market context / X5 | number of active feature rows, including rows with a missing statistic; witness retained |
| 52 | `htf_12h_return` | HTF / H12 | C/C_prev-1; 2 bars |
| 53 | `htf_12h_log_return` | HTF / H12 | log(C/C_prev); 2 bars |
| 54 | `htf_12h_range_pct` | HTF / H12 | (H-L)/O; current completed bar |
| 55 | `htf_12h_body_ratio` | HTF / H12 | (C-O)/(H-L); nonzero range |
| 56 | `htf_12h_upper_wick_ratio` | HTF / H12 | (H-max(O,C))/(H-L); nonzero range |
| 57 | `htf_12h_lower_wick_ratio` | HTF / H12 | (min(O,C)-L)/(H-L); nonzero range |
| 58 | `htf_12h_close_location` | HTF / H12 | (C-L)/(H-L); nonzero range |
| 59 | `htf_12h_ema20_distance` | HTF / H12 | C/EMA20-1; 20-bar seed |
| 60 | `htf_12h_ema20_50_spread` | HTF / H12 | EMA20/EMA50-1; 50-bar seed |
| 61 | `htf_12h_rsi14` | HTF / H12 | 14 gain/loss seed plus recursion; 15 closes initially |
| 62 | `htf_12h_relative_quote_volume` | HTF / H12 | Q/m20(Q); 20 bars |
| 63 | `htf_12h_volume_zscore` | HTF / H12 | z60(Q); 60 bars, positive std |
| 64 | `htf_12h_trade_count_intensity` | HTF / H12 | N/m20(N); 20 bars |
| 65 | `htf_12h_taker_buy_share` | HTF / H12 | B/Q; current bar |
| 66 | `htf_12h_taker_sell_share` | HTF / H12 | 1-B/Q; current bar |
| 67 | `htf_12h_taker_flow_imbalance` | HTF / H12 | 2B/Q-1; current bar |
| 68 | `htf_12h_atr14_pct` | HTF / H12 | mean14(true range)/C; first TR uses first close as previous-close seed |
| 69 | `htf_12h_ema20_slope_3bar` | HTF / H12 | EMA20/EMA20_lag3-1; 23-bar initial warm-up |
| 70 | `htf_12h_roc4` | HTF / H12 | C/C_lag4-1; 5 bars |
| 71 | `htf_12h_realized_vol_1d` | HTF / H12 | std2(log returns); 3 closes |
| 72 | `htf_12h_realized_vol_3d` | HTF / H12 | std6(log returns); 7 closes |
| 73 | `htf_12h_realized_vol_7d` | HTF / H12 | std14(log returns); 15 closes |
| 74 | `htf_1d_return` | HTF / H24 | C/C_prev-1; 2 bars |
| 75 | `htf_1d_log_return` | HTF / H24 | log(C/C_prev); 2 bars |
| 76 | `htf_1d_range_pct` | HTF / H24 | (H-L)/O; current completed bar |
| 77 | `htf_1d_body_ratio` | HTF / H24 | (C-O)/(H-L); nonzero range |
| 78 | `htf_1d_upper_wick_ratio` | HTF / H24 | (H-max(O,C))/(H-L); nonzero range |
| 79 | `htf_1d_lower_wick_ratio` | HTF / H24 | (min(O,C)-L)/(H-L); nonzero range |
| 80 | `htf_1d_close_location` | HTF / H24 | (C-L)/(H-L); nonzero range |
| 81 | `htf_1d_ema20_distance` | HTF / H24 | C/EMA20-1; 20-bar seed |
| 82 | `htf_1d_ema20_50_spread` | HTF / H24 | EMA20/EMA50-1; 50-bar seed |
| 83 | `htf_1d_rsi14` | HTF / H24 | 14 gain/loss seed plus recursion; 15 closes initially |
| 84 | `htf_1d_relative_quote_volume` | HTF / H24 | Q/m20(Q); 20 bars |
| 85 | `htf_1d_volume_zscore` | HTF / H24 | z60(Q); 60 bars, positive std |
| 86 | `htf_1d_trade_count_intensity` | HTF / H24 | N/m20(N); 20 bars |
| 87 | `htf_1d_taker_buy_share` | HTF / H24 | B/Q; current bar |
| 88 | `htf_1d_taker_sell_share` | HTF / H24 | 1-B/Q; current bar |
| 89 | `htf_1d_taker_flow_imbalance` | HTF / H24 | 2B/Q-1; current bar |
| 90 | `htf_1d_atr14_pct` | HTF / H24 | mean14(true range)/C; first TR uses first close as previous-close seed |
| 91 | `htf_1d_ema50_distance` | HTF / H24 | C/EMA50-1; 50-bar seed |
| 92 | `htf_1d_ema100_distance` | HTF / H24 | C/EMA100-1; 100-bar seed |
| 93 | `htf_1d_ema200_distance` | HTF / H24 | C/EMA200-1; 200-bar seed |
| 94 | `htf_1d_ema50_200_spread` | HTF / H24 | EMA50/EMA200-1; 200-bar seed |
| 95 | `htf_1d_ema20_slope_5d` | HTF / H24 | EMA20/EMA20_lag5-1; 25-bar initial warm-up |
| 96 | `htf_1d_roc7` | HTF / H24 | C/C_lag7-1; 8 closes |
| 97 | `htf_1d_realized_vol_3d` | HTF / H24 | std3(log returns); 4 closes |
| 98 | `htf_1d_realized_vol_7d` | HTF / H24 | std7(log returns); 8 closes |
| 99 | `htf_1d_realized_vol_30d` | HTF / H24 | std30(log returns); 31 closes |
| 100 | `htf_1d_volatility_zscore` | HTF / H24 | z180(std30(log returns)); 210 closes initially |
| 101 | `htf_1d_volatility_of_volatility` | HTF / H24 | std30(std30(log returns)); 60 closes initially |
| 102 | `htf_1d_distance_from_20d_high` | HTF / H24 | C/rolling_max20(H)-1; 20 bars |
| 103 | `htf_1d_distance_from_20d_low` | HTF / H24 | C/rolling_min20(L)-1; 20 bars |
| 104 | `htf_1d_distance_from_60d_high` | HTF / H24 | C/rolling_max60(H)-1; 60 bars |
| 105 | `htf_1d_distance_from_60d_low` | HTF / H24 | C/rolling_min60(L)-1; 60 bars |
| 106 | `htf_1d_drawdown_from_60d_high` | HTF / H24 | C/rolling_max60(H)-1; exact duplicate of distance_from_60d_high |
| 107 | `funding_zscore` | funding / D5 | z2016(as-of settled funding rate on 5m grid); repeated known values, not future estimate |
| 108 | `mark_index_basis` | basis / D5 | latest completed mark close / index close -1 |
| 109 | `contract_mark_basis` | basis / D5 | contract C / latest completed mark close -1 |

Source probe returned **130 physical Gold columns**; model features remain 109.
Derivatives are included in A6 even though they occur last in model grouping order. Feature
availability metadata, target values and cross-sectional source helpers remain outside the matrix.

## Additional independent adversarial probes

- **All 109 feature-prefix comparison: PASS**, 768 synthetic rows. Native fixture windows were
  shortened; all production columns, completed direct 12h/1d context and synthetic derivative
  observations were exercised. Full versus truncated observable history matched at rtol=1e-12,
  atol=1e-15, equal_nan=True. This is not real-Gold equivalence.
- **Missing hardening identity binding reproduced:** changing only hardening.py in a temporary
  copy left `scientific_source_identity` unchanged. No repository source was edited.
- **Negative threshold choice reproduced:** 30 non-overlapping synthetic trades had expectancy
  −0.0111 for every candidate; the selected threshold remained 10bps rather than no trade.
- **Duplicate qualification reproduced:** ten identical same-fold rows satisfied the ten-fold
  counters and yielded a tiny corrected p-value despite `folds_seen=1`.

## Executed verification and durable probe evidence

- Targeted command: `.venv/bin/python -m pytest tests/phase7 tests/phase5/test_phase7b_calibration_separation.py tests/test_phase7b_directional_accuracy.py -q` -> **689 passed in 56.39s**.
- Full command: `.venv/bin/python -m pytest -q` -> **1162 passed in 67.10s**. These include tiny fixture
  fits/causality/cache tests; no actual Gold training was started.
- Ruff check -> **FAIL**, three E501 comments in training.py. Ruff format -> **FAIL**, hardening.py
  and test_phase7a_final_metrics_and_baselines.py. Checks are recorded, not repaired.
- Linux verification -> **NOT RUN** on this macOS host. GPU/policy equivalence -> **NOT RUN**.
- Real Gold byte validation, actual fold row counts and real cache/uncached equivalence -> **NOT
  VERIFIED**; configured paths are absent. The earlier preserved report's fresh 138/138 data-hash
  claim is not evidence produced by this independent audit.

Reproduction from repository root (only synthetic computation, no training):

```sh
PYTHONPATH=src:. .venv/bin/python docs/reviews/evidence_crypto2_20261106/probes.py
```

The script writes its JSON under `/tmp/crypto2-audit-20261106` (create that directory first if
reproducing on a different host). [Preserved source](evidence_crypto2_20261106/probes.py),
[output](evidence_crypto2_20261106/probes.json), [source hash snapshot](evidence_crypto2_20261106/source_snapshot.json),
[full pytest log](evidence_crypto2_20261106/pytest.log), [lint](evidence_crypto2_20261106/ruff_check.log),
[format](evidence_crypto2_20261106/ruff_format.log). Audit evidence files are not production code or
model artifacts. Synthetic results establish a mechanism, not its frequency in real data.
