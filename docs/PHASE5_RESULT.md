# PHASE 5 RESULT

## 1 STATUS

COMPLETE. Phase 5 retrospective walk-forward validation is implemented and
executed. The evidence does not qualify any model.

## 2 TEST BASELINE

Before Phase 5: 133 tests passed. Ruff check/format on `src tests`, Python
compilation, and `uv lock --check` passed. Whole-repository Ruff also exposed
pre-existing deprecated legacy dashboard/live-tree lint debt; that excluded,
unpackaged code was not modified.

## 3 FINAL TEST RESULT

156 tests passed, 0 failed. Ruff lint and format checks on `src tests`, Python
compilation, dependency-lock validation, CLI plan/report/compare commands, and
artifact inspections passed.

## 4 PROSPECTIVE HOLDOUT

Boundary: `2026-08-01T00:00:00Z`. Used: **FALSE**. Every result is labeled
**RETROSPECTIVE WALK-FORWARD OOS**, not prospective holdout performance.

## 5 WALK-FORWARD DESIGN

Rolling UTC calendar windows: 24 months Train, 3 Validation, 3 Calibration,
3 Test, 3-month step, half-open ranges, actual-label-end purging, and a
separate 60-minute embargo. Validation controls early stopping; Calibration
controls calibration/threshold; Test is released only after all three are
frozen.

## 6 FOLD SUMMARY

Primary: 17 folds, 446,966 unique OOS rows per candidate, test coverage
`2022-03-18T06:40Z` through `2026-06-18T05:35Z`. Derivatives: 16 folds,
418,499 unique OOS rows per candidate, `2022-07-09T01:00Z` through
`2026-07-08T23:55Z`. Test windows do not overlap.

## 7 CANDIDATES

L0: 13 features; L5: 46; D0: the same 46-feature schema on the matched
derivatives range; D2: 55 features. Ordered schema hashes and the fixed Phase
4.1 LightGBM configuration are stored in every run/fold manifest.

## 8 L0 RESULTS

446,966 OOS rows; Pearson IC `0.008422` (95% block interval
`[-0.006481, 0.024592]`); direction `0.501967`; R-squared `-0.000167`. Base:
12 trades, expectancy `-0.004744`, summed net `-0.056928`, 0 reliable folds,
16 no-trade folds. Classification: **INCONCLUSIVE**.

## 9 L5 RESULTS

446,966 OOS rows; Pearson IC `0.023648` (`[0.004723, 0.041281]`); direction
`0.501671`; R-squared `0.000106`. Base: 17 trades, expectancy `-0.000989`,
summed net `-0.016808`, 0 reliable folds, 16 no-trade folds. Classification:
**INCONCLUSIVE**.

## 10 L0 VS L5

Identical test rows/timestamps. L5 minus L0: Pearson `+0.015226`, base
expectancy `+0.003755`. L5 has slightly better point estimates but only 17
trades and no reliable fold, so it does not qualify.

## 11 D0 RESULTS

418,499 OOS rows; Pearson IC `0.021348` (`[0.000455, 0.044284]`); direction
`0.499946`; R-squared `-0.000220`. Base: 72 trades, expectancy `-0.001802`,
summed net `-0.129754`, 1 reliable fold, 13 no-trade folds. Classification:
**INCONCLUSIVE**.

## 12 D2 RESULTS

418,499 OOS rows; Pearson IC `0.022113` (`[0.003633, 0.044533]`); direction
`0.501540`; R-squared `-0.000565`. Base: 207 trades, expectancy `-0.000816`,
summed net `-0.168940`, compounded net `-0.164020`, max drawdown `-0.275089`,
2 reliable folds, and 12 no-trade folds. Classification: **INCONCLUSIVE**.

## 13 D0 VS D2

Identical test rows/timestamps. D2 minus D0: Pearson `+0.000766`, base
expectancy `+0.000986`. Because D0 is below 100 total trades and both sides are
below 3 reliable folds, D2 value added is **INCONCLUSIVE**.

## 14 CALIBRATION

Primary candidate-folds selected identity 20 times and linear 14 times.
Derivatives selected linear 20 and identity 12 times. Slope/intercept, samples,
candidate MAE, distributions, and reliability curves are persisted. Test was
not supplied to calibration.

## 15 THRESHOLD HISTORY

Primary: 32/34 candidate-folds froze `NO_TRADE`; the two trade policies used
2 and 10 bps. Derivatives: 25/32 froze `NO_TRADE`; active policies used 2 bps
four times, 4 bps twice, and 10 bps once. Selection was calibration-only.

## 16 POOLED OOS PREDICTIVE RESULTS

| Candidate | MAE | RMSE | R-squared | Direction | Pearson | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 | 0.003289 | 0.005329 | -0.000167 | 0.501967 | 0.008422 | 0.005187 |
| L5 | 0.003290 | 0.005329 | 0.000106 | 0.501671 | 0.023648 | -0.003751 |
| D0 | 0.003162 | 0.005083 | -0.000220 | 0.499946 | 0.021348 | -0.000135 |
| D2 | 0.003163 | 0.005084 | -0.000565 | 0.501540 | 0.022113 | 0.005484 |

Correlations are small, direction is near chance, and three candidates have
negative R-squared; the positive IC intervals do not establish economic edge.

## 17 POOLED OOS ECONOMIC RESULTS

| Candidate | Base trades | Expectancy | Summed net | Compounded net | Max drawdown |
| --- | ---: | ---: | ---: | ---: | ---: |
| L0 | 12 | -0.004744 | -0.056928 | -0.056487 | -0.056487 |
| L5 | 17 | -0.000989 | -0.016808 | -0.017099 | -0.041146 |
| D0 | 72 | -0.001802 | -0.129754 | -0.124642 | -0.159337 |
| D2 | 207 | -0.000816 | -0.168940 | -0.164020 | -0.275089 |

Primary has 29 base trades, all on tagged 5m fallback. Derivatives has 279
base trades: 157 tagged 1m and 122 tagged 5m.

## 18 FOLD STABILITY

Positive/negative IC folds: L0 10/7, L5 14/3, D0 14/2, D2 14/2. Positive/
negative net folds: L0 0/1, L5 0/1, D0 1/2, D2 1/3; remaining folds were flat.
Reliable folds: 0, 0, 1, and 2 respectively. Predictive signs did not translate
into stable net economics.

## 19 YEAR-BY-YEAR

Base trades were sparse and discontinuous. L0/L5 traded only in 2022 and lost.
D0 lost in both 2022 and 2026. D2 lost in 2022, 2025, and 2026. No candidate
has positive, broad year-level economic support.

## 20 REGIME PERFORMANCE

L0/L5 samples are too small. D0 loses in bull, bear, sideways, high-, and
low-volatility regimes. D2 is positive in bull (`+0.007561`) and high-volatility
(`+0.027689`) subsets but loses more in bear (`-0.068324`) and sideways
(`-0.108177`); this is not robust across regimes.

## 21 LONG VS SHORT

L0: 7 long/5 short, both negative. L5: 11 long negative, 6 short positive, but
17 total is unreliable. D0: 60 long/12 short, both negative. D2: 184 long and
23 short, both negative overall.

## 22 COST STRESS

At 1.5x costs, trade count/expectancy are L0 `10/-0.000419`, L5
`12/+0.000220`, D0 `41/-0.001326`, and D2 `96/-0.000604`. L5's positive point
estimate has only 12 trades. At 2x, L0 has 9 trades with a positive point
estimate; all other candidates are negative. No stressed result is reliable
and qualifying.

## 23 THRESHOLD STABILITY

Active thresholds are rare: L0 mean 2 bps, L5 10 bps, D0 2 bps, D2 mean 5 bps
with 3 bps standard deviation. The dominant stable action is `NO_TRADE`, not a
repeatable active threshold.

## 24 TRADE CONCENTRATION

Top 1% of positive trade PnL contributes L0 35.2%, L5 43.2%, D0 11.9%, and D2
13.1%. Top 10% contributes 62.7%, 72.9%, 52.8%, and 51.7% respectively. Primary
results are particularly concentrated and tiny-sample.

## 25 PNL CONCENTRATION

D0 and D2 each have a 100% top-positive-fold share because only one fold is net
positive. L0/L5 have no positive net fold. No candidate passes the fold/year
concentration gates; D2 alone passes the configured regime-share gate.

## 26 FEATURE DRIFT

Highest mean PSI groups include longer-horizon volatility and trade-size/quote
volume for core models. D2 additionally shows the largest drift in
`mark_index_basis` and `funding_rate`. Full per-feature fold PSI, median shift,
and IQR diagnostics are stored; drift adds caution rather than a causal claim.

## 27 BASELINE COMPARISON

Flat remains zero/no-trade. Buy-and-hold is +57.1% over the primary pooled
period and +188.0% over the later derivatives period, unleveraged and not a
comparable active forecast policy. Fixed momentum and mean-reversion baselines
lose approximately 38.41/30.39 summed-return units on primary and 36.27/27.64
on derivatives after costs.

## 28 MODEL QUALIFICATION

L0: INCONCLUSIVE. L5: INCONCLUSIVE. D0: INCONCLUSIVE. D2: INCONCLUSIVE. All
fail minimum reliable-fold, positive median/base expectancy, and concentration
requirements; D2 also exceeds the configured drawdown limit. No arbitrary
profit target was used.

## 29 CHAMPION / CHALLENGER DECISION

**NO QUALIFIED MODEL**

## 30 FILES CREATED

Created `src/crypto_ai/phase5/` (7 modules), two `configs/walkforward/*.toml`
files, four `tests/phase5/` files, `docs/WALK_FORWARD.md`, this report, two
immutable walk-forward run trees, and `candidate_comparison.json`.

## 31 FILES MODIFIED

Modified `src/crypto_ai/cli.py`, `AGENTS.md`, `README.md`, and the existing
Architecture, Modeling, Backtesting, Experiments, Project State, and Decisions
documents. Prior datasets, model experiments, and backtests were not modified.

## 32 COMMANDS

Ran both `walk-forward --plan` and full `walk-forward --resume` commands,
`compare-candidates`, focused/full pytest, Ruff check/format, `compileall`,
`uv lock --check`, artifact checksum/range inspections, and Git status/diff
inventory. No private, account, order, or live-trading command ran.

## 33 KNOWN LIMITATIONS

One asset and one venue; bar-level execution; assumed fees/spread/slippage; no
queue/depth/impact/partial fills; sparse calibrated trades; no leverage or
portfolio; bootstrap economics secondary; family histories differ; prospective
holdout remains unopened.

## 34 INTERPRETATION

There is weak retrospective predictive correlation but no stable repeatable
net-cost edge. The strongest honest conclusion is that abstention dominates:
Phase 5 does not justify model promotion or trading deployment.

## 35 PROJECT STATE

Phase 5 is complete at the retrospective validation gate. Phases 1-4.1 and all
historical artifacts remain preserved. Live/account functionality remains
unauthorized and isolated.

## 36 NEXT PHASE

STOP. Do not open the prospective holdout, add advanced ML/assets, or begin
paper/live execution without a separate explicit instruction and a newly
frozen protocol.

# PHASE 5.1 HARDENING RESULT

Phase 5.1 is complete as a versioned methodological correction. It did not
rewrite any result above. All 66 historical LightGBM bundles were reused; no
model was retrained. Saved TEST raw predictions were reused, while Cal-A and
Cal-B predictions were recomputed from the frozen models because v1 did not
persist full Calibration predictions.

The outer 24/3/3/3 geometry, L0/L5/D0/D2 schemas, Label V1, model parameters,
threshold grid, qualification gates, and `2026-08-01T00:00:00Z` holdout are
unchanged. Each three-month Calibration period is split chronologically:
Cal-A fits/selects identity or linear calibration; labels are purged at the
Cal-A to Cal-B boundary; Cal-B receives a 60-minute embargo and alone selects
the threshold. TEST remains evaluation-only.

## Hardened pooled predictive results

| Candidate | OOS rows | MAE | RMSE | R-squared | Direction | Pearson | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 | 446,966 | 0.003290 | 0.005329 | -0.000169 | 0.503868 | 0.013499 | 0.004607 |
| L5 | 446,966 | 0.003290 | 0.005331 | -0.000642 | 0.502412 | 0.026490 | 0.000419 |
| D0 | 418,499 | 0.003164 | 0.005086 | -0.001176 | 0.499789 | 0.020299 | -0.000291 |
| D2 | 418,499 | 0.003165 | 0.005089 | -0.002476 | 0.501378 | 0.016730 | 0.005076 |

## Primary fixed-policy cost stress

The 1x trade list is frozen at every multiplier. Counts and trade hashes are
identical within each candidate; only costs and net economics change.

| Candidate | Trades | 1x net | 1.25x net | 1.5x net | 2x net |
| --- | ---: | ---: | ---: | ---: | ---: |
| L0 | 47 | -0.130485 | -0.143410 | -0.156335 | -0.182185 |
| L5 | 112 | -0.008980 | -0.039780 | -0.070580 | -0.132180 |
| D0 | 9 | -0.026496 | -0.028971 | -0.031446 | -0.036396 |
| D2 | 253 | -0.404953 | -0.474528 | -0.544103 | -0.683253 |

All fixed-policy results are monotonically non-increasing as adverse costs
rise. Base expectancy is L0 `-0.002776`, L5 `-0.000080`, D0 `-0.002944`, and
D2 `-0.001601`. Base maximum drawdown is `-0.124528`, `-0.168953`,
`-0.045554`, and `-0.379013` respectively.

## Secondary adaptive-policy cost stress

Adaptive trade counts at 1x/1.25x/1.5x/2x are L0 `47/33/29/16`, L5
`112/90/71/55`, D0 `9/5/5/4`, and D2 `253/164/118/69`. These changing trade
sets answer a different question and are not used for the primary cost
robustness conclusion or qualification.

## Qualification and reliability

| Candidate | Qualification | Evidence | Pooled base reliability | Reliable folds |
| --- | --- | --- | --- | ---: |
| L0 | FAIL | INCONCLUSIVE | false: 47 trades below 100 | 0 |
| L5 | FAIL | INCONCLUSIVE | true: 112 trades | 1 |
| D0 | FAIL | INCONCLUSIVE | false: 9 trades below 100 | 0 |
| D2 | FAIL | INCONCLUSIVE | true: 253 trades | 2 |

Pooled reliability does not satisfy the separate requirement for three
reliable folds. All candidates have negative base expectancy and negative 1.5x
fixed-policy expectancy. D2 also exceeds the maximum-drawdown gate. Therefore
the hardened decision remains **NO QUALIFIED MODEL**.

The maximum development `feature_time` is `2026-07-08T23:55:00Z`; an
independent scan found zero Phase 5.1 `feature_time`, `entry_time`, or
`label_end_time` values at or beyond the holdout. See
`PHASE5_HARDENING_VERIFICATION.md` and the machine-readable
`verification_report.json` for the integrity audit.
