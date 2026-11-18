# Phase 7A Fold-0 signal diagnosis: architecture-G0-A6-60m-raw

Date: 2026-11-18. Scope: diagnosis only. No model was refit, no parameter, feature, threshold or
target was changed, and no TEST row was read for diagnosis (TEST figures below are copied from the
canonical report and are labelled `DESCRIPTIVE_OOS_RESULT`).

## Sources

| Source | Identity |
| --- | --- |
| Canonical result | `~/Crypto2Data/models/phase7-one-smoke-20261118-attempt14/evidence/train-result.json` (report identity `775fabbb…12e3`) |
| Model | `model.joblib`, SHA-256 `ee44671558750c1b85c4d129a607555ce6342ccd299a9eee12881508ddfba1be` (Mac and volume copies match) |
| Prepared cache | `/workspace/phase7a-cache/350b800c…25b1` on volume `kz9axr9t9v` |
| Diagnostics | `scripts/closure/diagnose_fold_phase7.py` (commit `5f0173f`), output `~/Crypto2Data/reports/fold0-diagnosis-20261118/fold_diagnosis.json`; feature importance `feature_importance.json` |
| Source / config | commit `e2fbe33`, configuration hash `93f987736b1a79d26b773957`, Gold `gold-phase7-0cbf2910e8d96c9d19826598` |

Fold-0 windows: TRAIN 2020-01-01..2022-01-01, VALIDATION 2022-01-01..2022-04-01,
CALIBRATION 2022-04-01..2022-07-01, TEST 2022-07-01..2022-10-01. July 2026 unused; August 2026
holdout `LOCKED_UNUSED`.

## A1. Exact Fold-0 result

Alignment proof: re-scoring the cached Validation matrix with the saved model reproduces the canonical
Validation RMSE exactly (`0.011075902325934792`, absolute difference `0.0`). Feature order in the
model equals the report's 109 `same_row_feature_columns`. Cached segment shapes equal the canonical
segment row counts.

| Item | Value |
| --- | --- |
| Rows (train / validation / cal A / cal B / test) | 2,055,698 / 495,539 / 227,627 / 260,528 / 518,389 |
| Features | 109 (A6) |
| Best iteration / completed rounds / stop reason | 47 / 75 / `EARLY_STOPPING` (50-round patience, cap 500) |
| Parameters | lr 0.02, 31 leaves, min_child_samples 100, subsample 0.9, colsample 0.9, L1 0.1, L2 1.0, seed 42, CPU, symbol-balanced weights |
| Train RMSE (400k-row sample, best model) | 0.015461 (zero predictor 0.015928) |
| Validation RMSE / MAE | 0.0110759 / 0.0075904 |
| Validation Pearson / Spearman | 0.02094 / 0.02313 (canonical) |
| Validation directional accuracy (non-zero targets) | 0.5105 |
| Validation cross-sectional Spearman IC | mean 0.0078, std 0.274 over 9,157 timestamps (16,726 skipped, < 5 symbols) |
| Prediction mean / std (Validation) | 7.5e-05 / 3.64e-04 |
| Target mean / std (Validation) | 1e-06 / 0.011077 |
| Peak RSS | 6.4 GiB (100 GiB cgroup) |
| TEST directional accuracy | 0.479 — `DESCRIPTIVE_OOS_RESULT` |
| TEST LONG / SHORT signals | 0 / 0 — the CAL_B-selected global threshold is `null`, so every TEST row is NO_TRADE |

LONG/SHORT on Validation at the 5 bps diagnostic threshold (best model, all Validation rows):

| Side | Predicted | Actual events | TP | FP | FN | Precision | Recall | F1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LONG | 4,253 | 239,397 | 2,377 | 1,876 | 237,020 | 0.559 | 0.0099 | 0.0195 |
| SHORT | 1,843 | 229,155 | 992 | 851 | 228,163 | 0.538 | 0.0043 | 0.0086 |

Action coverage 1.23 %.

## A2. Prediction collapse

| | p01 | p05 | p25 | p50 | p75 | p95 | p99 | min | max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Prediction | -3.8e-05 | -3.0e-05 | -3.0e-05 | -1.0e-05 | 1.33e-04 | 4.03e-04 | 4.74e-04 | -0.0276 | 0.0129 |
| Target (validation) | -0.0319 | -0.0174 | -0.0051 | 0.0002 | 0.0053 | 0.0165 | 0.0306 | -0.152 | 0.236 |

`prediction_std / target_std = 0.033`. 98 % of predictions lie in a ±5 bps band while the target's
interquartile range is ±52 bps. Classification: **STRONG_SHRINKAGE** (partial collapse: a few
extreme predictions exist, the body is nearly constant).

## A3. Target difficulty

| | TRAIN | VALIDATION |
| --- | --- | --- |
| Mean / median | 1.64e-04 / 2.02e-04 | 1e-06 / 1.83e-04 |
| Std / MAD | 0.01593 / 0.00639 | 0.01108 / 0.00523 |
| Min / max | -0.531 / +0.703 | -0.152 / +0.236 |
| Positive / negative / zero | 50.8 % / 48.8 % / 0.4 % | 50.7 % / 48.6 % / 0.6 % |
| \|r\| < 5 bps | 4.6 % | 5.4 % |
| \|r\| ≥ 1 % | 33.4 % | 25.0 % |
| \|r\| ≥ 3 % | 5.1 % | 2.3 % |

The 5 bps diagnostic threshold is a **common** event (≈95 % of rows qualify as LONG or SHORT events):
it separates "moved" from "flat", not "large" from "small". The target is heavy-tailed, and TRAIN
(2020–2021) is ≈44 % more volatile than VALIDATION (Q1 2022), with tails up to ±70 %.

## A4. Baselines (Validation, canonical matched contract v3)

| Model | RMSE | MAE | Pearson | Spearman | Direction |
| --- | --- | --- | --- | --- | --- |
| Zero | 0.0110773 | 0.0075956 | – | – | – |
| TRAIN mean | 0.0110783 | 0.0075940 | – | – | – |
| Matched weighted Ridge (alpha 1.0, full TRAIN, symbol-balanced) | 0.0111261 | 0.0076457 | 0.0165 | 0.0156 | 0.5035 |
| **LightGBM** | **0.0110759** | **0.0075904** | **0.0209** | **0.0231** | **0.5105** |

| LightGBM improvement | Absolute RMSE | Relative RMSE |
| --- | --- | --- |
| vs zero | 1.40e-06 | **0.0126 %** |
| vs TRAIN mean | 2.39e-06 | 0.0216 % |
| vs Ridge | 5.02e-05 | 0.451 % |

LightGBM beats Ridge clearly but beats the zero predictor by only 0.0126 % RMSE. These are
development metrics: Validation also drove early stopping. **LightGBM does not materially
outperform zero on Validation.**

## A5. Feature importance (gain and split)

Gain concentration: top 5 = 43.3 %, top 10 = 60.3 %, top 20 = 78.8 %. Zero-gain features: 19;
near-zero (< 0.1 % of gain): 29. Top by gain: `mark_index_basis` 13.8 % (36 splits),
`btc_return_4h` 9.9 % (86), `htf_12h_return` 6.9 % (40), `daily_volatility` 6.6 % (77),
`eth_volatility_1h` 6.1 % (106), `market_return_dispersion` 3.9 %, `eth_return_4h` 3.7 %,
`htf_12h_range_pct` 3.5 %, `return_1h_over_daily_vol` 3.1 %, `market_median_volatility` 2.8 %.
The full gain/split table for all 109 features is in `feature_importance.json`.

`mark_index_basis` is checked as a dominance suspect: its TRAIN Pearson (-0.038) is three times its
Spearman (-0.013), and its Validation relationship is near zero (-0.005 / -0.009). Its gain comes
from splits on TRAIN tail rows, not from a leaked or validation-stable signal. No feature was removed.

## A6. Redundancy (TRAIN, 400k-row sample)

22 feature pairs have \|Pearson\| ≥ 0.95, several exactly ±1.000 (for example `taker_sell_share` ~
`taker_flow_imbalance`, `listing_age_days` ~ `history_length_days`,
`htf_12h_taker_buy_share` ~ `htf_12h_taker_sell_share` ~ `htf_12h_taker_flow_imbalance`,
`htf_1d_distance_from_60d_high` ~ `htf_1d_drawdown_from_60d_high`). No near-constant features.
Redundancy is real but explains wasted columns, not the absence of signal; it remains the deferred
research item and the 109-feature contract is unchanged.

## A7. Univariate signal

The strongest relationships are short-horizon **mean reversion** (negative coefficient on recent
returns): `btc_return_4h` TRAIN Spearman -0.051 → VALIDATION -0.021; `btc_return_1h` -0.027 → -0.051;
`eth_return_1h` -0.024 → -0.047; `ema20_distance_pct` -0.037 → -0.027; `return_1h` -0.028 → -0.026.
The maximum \|Validation Spearman\| over all 109 features is 0.051. Of 49 features with
\|TRAIN Spearman\| > 0.01, 40 keep their sign in Validation and 9 flip. Volatility features
(`market_median_volatility`, `eth_volatility_1h`) have Pearson ≫ Spearman in TRAIN (tail-driven) and
lose most of it in Validation. Classification: a **small, mostly sign-stable rank signal**, plus
tail-driven Pearson relationships that are `NON_STATIONARY_OR_OVERFIT_UNIVARIATE_SIGNAL`.

## A8. Per coin (Validation)

19 of 20 symbols have positive Spearman (range -0.007 KSM to +0.054 BTC); RMSE skill vs zero ranges
-0.0009 (FIL) to +0.0011 (BCH). The signal is **broad and uniformly tiny**, not concentrated in a
few coins and not hidden by opposite-sign coins.

## A9. Time blocks (Validation, six equal chronological blocks)

| Block | Spearman | Pearson | Direction | RMSE skill vs zero | Prediction std |
| --- | --- | --- | --- | --- | --- |
| 01-01..01-15 | +0.001 | +0.010 | 0.504 | -0.00013 | 2.3e-04 |
| 01-15..01-30 | +0.017 | +0.051 | 0.510 | +0.00097 | 5.4e-04 |
| 01-30..02-14 | +0.015 | +0.048 | 0.510 | +0.00078 | 1.8e-04 |
| 02-14..02-28 | -0.013 | -0.019 | 0.503 | -0.00223 | 5.8e-04 |
| 02-28..03-14 | +0.047 | +0.071 | 0.524 | +0.00120 | 2.3e-04 |
| 03-14..03-31 | +0.065 | +0.019 | 0.513 | +0.00056 | 1.8e-04 |

Five of six blocks are positive; one (late February 2022, the start of the Russia–Ukraine shock) is
negative with the largest loss. The aggregate is a weak positive signal with **one adverse regime**,
not positive and negative regimes cancelling.

## A10. LONG vs SHORT

Validation (A1 table): LONG precision 0.559, recall 0.010; SHORT precision 0.538, recall 0.004.
Both sides are marginally above 50 % precision on very few signals (coverage 1.2 %); neither side
carries a distinct signal. TEST: no signals (null threshold).

## A11. TRAIN vs VALIDATION

| | TRAIN sample | VALIDATION |
| --- | --- | --- |
| Pearson | 0.292 | 0.021 |
| Spearman | 0.086 | 0.023 |
| Direction | 0.527 | 0.511 |
| RMSE skill vs zero | 2.9 % | 0.013 % |
| Prediction std | 2.0e-03 | 3.6e-04 |

TRAIN Pearson ≫ Spearman: the fit is driven by TRAIN's extreme 2020–2021 tail rows. The rank signal
falls from 0.086 to 0.023. Classification: **overfit to TRAIN-period tails / non-stationary**, with a
small genuine rank signal surviving.

## A12. Early stopping

Validation RMSE: 0.0110780 at round 1, best 0.0110759 at round 47 (total improvement 2.1e-06,
0.019 %), flat to round 75 when patience expired. TRAIN RMSE fell 0.0159 → 0.0153 (3.8 %) over the
same rounds. Early stopping behaved correctly; the 500-round cap was irrelevant. Raising rounds would
only fit TRAIN further.

## Pipeline observation (not a data bug)

The CAL_A calibrator selected `linear` with **slope -0.729** (intercept -4.5e-04): on the calibration
window, raw predictions were inversely related to outcomes, so calibration **inverts the sign** of the
raw model before TEST. This is consistent with the regime instability above and explains part of the
gap between Validation direction (0.511) and TEST direction (0.479, `DESCRIPTIVE_OOS_RESULT`). The
calibration policy is frozen; whether a sign-inverting calibrator should be allowed is recorded as a
review question for the protocol owner, not changed here.

## Verdict for Part B

`CRITICAL_DATA_BUG: NO`. Exact re-scoring proves the cached features, targets, rows and feature order
align with the canonical result; the label-end purge was applied at the calibration boundary
(754 rows purged); no TEST rows were used for fitting or selection (`test_used_for_selection: false`).

Most likely causes, ranked:

| Cause | For | Against | Confidence |
| --- | --- | --- | --- |
| TARGET_TOO_NOISY (heavy-tailed raw 60 m return) | ±70 % tails; L2 skill 0.013 %; 95 % of rows are 5 bps "events" | small rank signal exists | HIGH |
| PREDICTION_SHRINKAGE | pred/target std 0.033 | shrinkage is the correct L2 response to noise | HIGH |
| REGIME_INSTABILITY / MODEL_OVERFIT to TRAIN tails | TRAIN Pearson 0.29 vs 0.02; volatility 44 % higher in TRAIN; negative calibration slope; adverse Feb-2022 block | 40/49 univariate signs stable | MEDIUM |
| FEATURES_WEAK_FOR_60M | max \|Validation Spearman\| 0.051 | consistent mean-reversion family | MEDIUM |
| FEATURE_REDUNDANCY | 22 pairs ≥ 0.95, several exact duplicates | trees tolerate duplicates | LOW |
| GLOBAL_MODEL_HIDES_ASSET_STRUCTURE / FEW_COINS | – | 19/20 coins positive and uniform | LOW |
| SIGNAL_ONE_DIRECTION | – | LONG and SHORT both ≈ 0.55 precision | LOW |
| DATA_ALIGNMENT_BUG | – | exact re-score, purge applied | LOW |
