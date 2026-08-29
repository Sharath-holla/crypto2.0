# Experiments

## Phase 3 BTC baseline — July 2026

Experiment: `experiment-5f0f09b3ee131bddba69a0b1`  
Gold dataset: `gold-19425b0820c974247b73fbe0`  
Source Silver: `silver-7105362e4dc25f97784d8f9a`

The bounded source range is Binance USD-M `BTCUSDT` 5-minute candles for `[2026-07-01T00:00:00Z, 2026-08-01T00:00:00Z)`. Phase 2 observed 8,928/8,928 expected candles, no gaps or structural errors, and 36 retained statistical outlier warnings.

Gold construction removed 49 feature warm-up rows and 13 terminal rows without a complete next-open-plus-60-minute label. No label was invalidated by a gap. The final dataset has 8,866 rows and 13 features.

Chronological development split after purging:

| Split | Feature-time range | Rows |
| --- | --- | ---: |
| Train | 2026-07-01 04:10 UTC → 2026-07-22 16:15 UTC | 6,194 |
| Validation | 2026-07-22 17:20 UTC → 2026-07-27 07:05 UTC | 1,318 |
| Development test | 2026-07-27 08:10 UTC → 2026-07-31 22:55 UTC | 1,330 |

The experiment configuration used deterministic row fractions (`0.70/0.15/0.15`) rather than explicit timestamp inputs. Those fractions resolved once against the immutable ordered Gold dataset to raw validation and test boundaries of `2026-07-22T17:20:00Z` and `2026-07-27T08:10:00Z`. Both timestamps, all post-purge periods, row counts, and purge counts are persisted in `experiment.json`, so the split is reproducible without randomization.

Twelve target-overlap rows were purged at Train → Validation and another twelve at Validation → Test. These are the twelve 5-minute feature rows immediately preceding each boundary whose 60-minute `label_end_time` would reach into the next split. The stored invariants verify every training label ends before validation and every validation label ends before test.

The development-test split was not supplied to model or scaler fitting, preprocessing, LightGBM early stopping, feature selection, model selection, hyperparameter selection, or threshold selection. LightGBM used validation only for its configured early stopping. The fixed model/configuration set was evaluated on development test only after fitting.

### Development-test comparison

| Model | MAE | RMSE | R² | Directional accuracy | Pearson IC | Spearman IC |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Zero | 0.00272915 | 0.00395053 | -0.006039 | 0.0000 | n/a | n/a |
| Historical mean | 0.00275188 | 0.00397369 | -0.017873 | 0.4654 | n/a | n/a |
| Momentum | 0.00423802 | 0.00576612 | -1.143249 | 0.4699 | -0.070182 | -0.085603 |
| Mean reversion | 0.00316854 | 0.00444736 | -0.274996 | 0.5376 | 0.085228 | 0.086307 |
| Ridge | 0.00276413 | 0.00401116 | -0.037159 | 0.5015 | 0.028475 | 0.071423 |
| LightGBM | 0.00275200 | 0.00397419 | -0.018125 | 0.4654 | -0.000919 | 0.016511 |

No learned model beat the zero baseline on test RMSE. Mean reversion had the best directional accuracy and correlation, but both correlations were weak. LightGBM early-stopped at iteration 3 and its prediction buckets were not monotonically related to realized returns. This one-month experiment provides no evidence for a trading or profitability claim.

### LightGBM feature importance

Full structured values are stored in `metrics/lightgbm.json` and `models/lightgbm.metadata.json` under the experiment directory. The largest gain values were `candle_range_pct`, `rolling_volatility_1h`, `rsi14`, `relative_volume`, and `ema50_distance`. The largest positive validation permutation-MAE changes were `rolling_volatility_1h`, `log_return_5m`, and `rsi14`; several other values were zero or negative. These are validation-set diagnostics for this fitted model, not causal findings or evidence that the features generalize.

### Target distribution

| Statistic | Value |
| --- | ---: |
| Count | 8,866 |
| Mean | 0.00008831 |
| Median | 0.00008243 |
| Standard deviation | 0.00358734 |
| Minimum | -0.01963131 |
| 1% | -0.00984664 |
| 5% | -0.00539720 |
| 25% | -0.00164459 |
| 50% | 0.00008243 |
| 75% | 0.00168875 |
| 95% | 0.00577251 |
| 99% | 0.01064121 |
| Maximum | 0.02423907 |

Using the documented ±1 basis-point research threshold: 49.73% positive, 46.46% negative, and 3.81% near zero.

No Phase 1 or Phase 2 model experiment was performed, and no Phase 3 backtest, simulated PnL, or order execution was performed.

## Phase 4 BTC Market Intelligence V2 — July 2026

Gold V2: `gold-v2-f59110b7f683d2fe4342c8d6`  
Experiment: `main-model-v2-7ab8dd9185dc27f90d1179b0`  
Backtest: `backtest-v1-3fe833c385aba7b0d34d49a0`

The real source range remains the longest validated overlapping local range:
Binance USD-M BTCUSDT 5m candles for `[2026-07-01, 2026-08-01)` plus 93 public
funding observations. Gold V2 enables 50 features and retains 8,580 rows after
336-row causal warm-up, external availability, and terminal-label checks.
Mark/index and OI were not available to this run, so A6/A7 were not fabricated.

Purged split: 5,994 train, 1,275 validation, and 1,287 development-test rows;
12 target-overlap rows were purged at each boundary. All ablations used these
same rows. A8 was predeclared as the complete available-group model; test was
not used for selection.

| Ablation | Features | Test MAE | Test RMSE | R² | Direction | Pearson | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A0 Phase 3 baseline | 13 | 0.00277214 | 0.00401243 | -0.014363 | 0.464646 | -0.067908 | 0.028382 |
| A1 + price/trend | 21 | 0.00277099 | 0.00400945 | -0.012855 | 0.464646 | 0.160238 | 0.137858 |
| A2 + momentum/volatility | 27 | 0.00277284 | 0.00401320 | -0.014749 | 0.464646 | -0.063991 | -0.049379 |
| A3 + volume | 31 | 0.00277341 | 0.00401340 | -0.014853 | 0.464646 | -0.082218 | -0.078653 |
| A4 + pressure | 38 | 0.00277182 | 0.00401133 | -0.013807 | 0.464646 | 0.043251 | 0.055377 |
| A5 + funding | 41 | 0.00277088 | 0.00400413 | -0.010171 | 0.458430 | 0.133229 | 0.103372 |
| A6 + basis | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| A7 + OI | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| A8 + regime/time, pruned | 42 | 0.00277019 | 0.00400915 | -0.012705 | 0.464646 | 0.123210 | 0.079366 |

A8 stopped at iteration 1. Its predictions were small and nearly constant.
Funding age, 4h volatility, funding change, EMA spread, UTC hour cosine, EMA20
slope, funding rate, and volatility z-score had nonzero gain. Validation
permutation effects were tiny; they do not establish stable importance.

The redundancy audit removed eight exact/near-exact representations from A8.
No absolute training correlation at or above 0.995 remained in the final input.

Pressure buckets were not monotonic. Test mean realized return ranged from
approximately -5.98 bps to +1.21 bps across deciles, with the positive result
in decile 9 rather than the highest-pressure decile. Regime diagnostics were
also unstable: bull, bear, sideways, and high-volatility subsets all had weak
or inconsistent correlation and no uniformly positive skill.

### Cost-aware development-test backtest

The base hurdle is 4 bps taker fee per side, 1 bp round-trip spread, 1 bp
slippage per side, actual funding, and a separate 2 bps prediction threshold.

| Strategy | Trades | Total net | Compounded net | Max drawdown | Hit rate | Exposure |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Zero | 0 | 0.000000 | 0.000000 | 0.000000 | n/a | 0.0000 |
| Historical mean | 0 | 0.000000 | 0.000000 | 0.000000 | n/a | 0.0000 |
| Momentum | 100 | -0.125011 | -0.118377 | -0.131939 | 0.3600 | 0.9245 |
| Mean reversion | 82 | -0.074634 | -0.072568 | -0.086847 | 0.3659 | 0.7581 |
| Main Model V2 | 0 | 0.000000 | 0.000000 | 0.000000 | n/a | 0.0000 |

Main Model V2 did not clear the expected-cost hurdle and correctly produced no
trades. Cost stresses at 1.0x/1.5x/2.0x/3.0x therefore remained flat. This is a
valid safe no-trade result. Neither predictive nor backtest evidence supports a
profitability, leverage, deployment, or live-trading claim.

## Phase 4.1 multi-year result

Core Gold `gold-v2-1-a3d74d086a912070ee63a5ec` has 722,395 labeled rows
from 724,828 validated 5-minute candles. Derivatives Gold
`gold-v2-1-445fe8d3e2f5c2cb9e5ac6d1` has 683,863 rows after causal
funding/mark/index coverage and seven-day warm-up. Experiment
`main-model-v2-1-55f7b64298b70d529a1c5e39` uses the unchanged Label V1,
one fixed LightGBM configuration, seed 42, and no HPO.

Long-history L0–L5 share exactly 505,664/108,347/108,360 purged
train/validation/test rows:

| Ablation | Features | Best iteration | Test MAE | Test RMSE | R² | Direction | Pearson | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 Phase 3 baseline | 13 | 123 | 0.00300819 | 0.00463378 | 0.003018 | 0.49860 | 0.06871 | -0.00556 |
| L1 price + trend | 16 | 91 | 0.00300802 | 0.00463619 | 0.001981 | 0.49902 | 0.05220 | 0.00529 |
| L2 + momentum/volatility | 26 | 55 | 0.00300865 | 0.00463735 | 0.001484 | 0.49906 | 0.04991 | -0.01058 |
| L3 + volume | 32 | 101 | 0.00300871 | 0.00463664 | 0.001787 | 0.49973 | 0.04766 | -0.00268 |
| L4 + taker flow | 42 | 35 | 0.00300863 | 0.00463905 | 0.000750 | 0.49911 | 0.04026 | -0.00290 |
| L5 + causal regime/time | 46 | 50 | 0.00301008 | 0.00463977 | 0.000439 | 0.49659 | 0.03252 | -0.01551 |

The predeclared complete core model is L5; L0 nevertheless has the strongest
test RMSE/R²/IC. L5's moving-block-bootstrap 95% Pearson interval is
`[-0.00472, 0.05515]`, and its direction interval includes 50%. Added groups do
not demonstrate incremental OOS value.

Derivatives D0–D2 share exactly 478,692/102,567/102,580 purged rows:

| Ablation | Features | Best iteration | Test MAE | Test RMSE | R² | Direction | Pearson | Spearman |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D0 core | 46 | 2 | 0.00305229 | 0.00471704 | -0.000757 | 0.49946 | 0.01687 | 0.00384 |
| D1 + funding | 49 | 2 | 0.00305234 | 0.00471700 | -0.000739 | 0.49962 | 0.02619 | 0.01152 |
| D2 + mark/index/basis | 55 | 19 | 0.00305215 | 0.00471540 | -0.000060 | 0.50103 | 0.03133 | 0.00301 |
| D3 + OI | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |

Funding and basis produce only tiny mixed changes; D2 R² remains negative and
direction is effectively chance. D3 is not legitimate because official OI
statistics do not provide the multi-year overlap. Across L5 OOS, Pearson falls
from 0.0458 in 2024 to 0.0291 in 2025 and 0.0190 in 2026; 2026 Spearman is
-0.0338. Bear-regime Pearson is 0.0698, but bull and sideways results are
negative, so no stable regime claim is supported.

Taker-flow test deciles show lower buy share had higher subsequent mean return
than the highest-share decile, with non-monotonic middle buckets. This may be
consistent with short-horizon exhaustion but is descriptive, not causal.
Funding buckets use training-only quantile thresholds; duplicated historical
funding quantiles make several buckets empty, an explicit distribution fact.

The result is **NO RELIABLE PREDICTIVE EDGE**. Phase 4.1 has materially stronger
data and experiment control, but it does not establish production
profitability or authorize live execution.

The corresponding 1-minute execution backtest is
`backtest-v2-1-1ab164e8a1409ebbad40b155`. Base costs select only 5 of 102,580
test opportunities (102,575 NO_TRADE), producing 11.6783% summed net and a
mechanical Sharpe of 21.89. This is `INSUFFICIENT_SAMPLE`: one 2025 trade and
four 2026 trades, clustered in the bear regime, drive the result. The 2,478
trade zero-cost diagnostic has negative expectancy and -1.8975% summed net.
The few positive threshold-selected trades therefore do not overturn the
predictive conclusion or establish an economic edge.

## Phase 5 retrospective walk-forward result

Primary run `wf-btc-primary-v1-c3b30d4b831a8a576cdfd405` evaluates L0/L5
over 17 non-overlapping test folds and 446,966 unique OOS rows per candidate.
Derivatives run `wf-btc-derivatives-v1-c446e61dcf7a3f17e2e4f6cd` evaluates
matched D0/D2 over 16 folds and 418,499 rows each. All rows precede the
untouched `2026-08-01T00:00:00Z` prospective holdout.

| Candidate | Pearson IC | Direction | R-squared | Base trades | Expectancy | Summed net |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| L0 | 0.008422 | 0.501967 | -0.000167 | 12 | -0.004744 | -0.056928 |
| L5 | 0.023648 | 0.501671 | 0.000106 | 17 | -0.000989 | -0.016808 |
| D0 | 0.021348 | 0.499946 | -0.000220 | 72 | -0.001802 | -0.129754 |
| D2 | 0.022113 | 0.501540 | -0.000565 | 207 | -0.000816 | -0.168940 |

L5 improves the L0 Pearson point estimate but has no reliable trade fold. D2
improves D0 Pearson by only 0.000766 and base expectancy by 0.000986; because
D0 is below 100 trades and both candidates are below the three-reliable-fold
minimum, D2 value added is `INCONCLUSIVE`. Every candidate has negative pooled
base expectancy. At 1.5x costs only L5 has a positive point estimate, based on
12 trades, which is insufficient.

Calibration freezes `NO_TRADE` in 32/34 primary candidate-folds and 25/32
derivatives candidate-folds. L0/L5 trade only one fold each; D0/D2 have 13/12
zero-trade folds. Predictive block intervals and many positive fold IC signs do
not translate into broad net economics. D0/D2 lose at base costs; D2's modest
bull/high-volatility gains are outweighed by bear/sideways losses.

The combined comparison is
`local_artifacts/phase5/walkforward/candidate_comparison.json`. L0, L5, D0, and
D2 are all `INCONCLUSIVE`; the single champion decision is **NO QUALIFIED
MODEL**. Detailed fold, calibration, threshold, drift, cost, year, regime,
direction, baseline, and concentration evidence is in `PHASE5_RESULT.md` and
the run artifacts. This is retrospective walk-forward OOS evidence, not a
prospective holdout or deployment result.

## Phase 6 higher-timeframe and target research

Experiment `phase6-btc-a6d0815c4adf041bf4107755` is retrospective research
before the exclusive `2026-07-01T00:00:00Z` cutoff. Its immutable Gold has
651,862 rows and 127 features; 1,725,856 saved OOS predictions cover fixed
zero, historical-mean, Ridge, and LightGBM probes. Four chronological folds
use a 240-minute purge, 60-minute embargo, seed 42, and no HPO.

On 39,224 identical sampled 1h OOS rows, LightGBM Spearman IC is 0.034533
without 12h/daily, 0.038519 with 12h, 0.035171 with daily, and 0.037984 with
both. The 12h group is `KEEP_CANDIDATE`; daily is `WEAK`; current
cross-timeframe and stress additions are `REJECT`. These are research feature
classifications, not production approval.

Full-context LightGBM Spearman IC is 0.06892/0.05319/0.03510/0.02367/0.01417
for 15m/30m/1h/2h/4h. The first four are `TARGET_CANDIDATE` diagnostics and 4h
is `RESEARCH_ONLY`; costs and policy economics were not evaluated. MFE/MAE and
volatility-normalized barriers are descriptive labels only. No champion is
promoted, the permanent holdout contributes zero rows, and current status is
**NO QUALIFIED MODEL**.

## Phase 7 local implementation checkpoint

Phase 7 has no real experiment result yet. The checked-in local implementation
defines the future cloud run and passes deterministic synthetic multi-asset
tests, but it has not selected the actual historical registry/pilot, downloaded
the full pilot data, trained the model matrix, or opened any TEST/holdout data
outside its fixture.

The preregistered cloud matrix compares G0/C0/P0/H0 on A6 across raw and
normalized 15/30/60/120-minute targets, G0 identity/weight controls,
incremental A0-A5 ablations, and independent 12h/1d controls over 16 planned
rolling folds. Required outputs include predictive macro/micro/coverage/
cross-sectional metrics and Cal-B-selected liquidity-cost economics.

The only honest current conclusion is **NO QUALIFIED MODEL / CLOUD RESEARCH
PENDING**. `PHASE7_RESULTS.md` must not be created until the real cloud run and
artifact verification finish.

## Phase 7.2 future trial registry

Phase 7.2 prepares trial identities but runs none. Every future declaration
must record `trial_family`, hypothesis, exact feature/target/model changes,
primary metric, promotion rule, random seed, data manifest, universe and cost
assumptions. Failed trials remain registered.

| Family | Registered members | Current status |
|---|---|---|
| `P7_BASELINE_TREE` | Ridge; G0/C0/P0/H0 LightGBM | first cloud run pending |
| `P7_TREE_CHALLENGERS` | CatBoost; XGBoost | disabled / not benchmarked |
| `P7_MICRO_1M` | 5m baseline; same rows plus `micro_1m_context_v1` | disabled / BTC+ETH pilot not run |
| `P7_TARGET_CHALLENGERS` | `multiasset_targets_v2`; `competing_risk_targets_v1` | v2 baseline frozen; challenger not trained |
| `P7_RANKING` | regression-score ranking; direct LambdaMART ranking | disabled / label not selected |
| `P8_TEMPORAL` | reserved only | not authorized |

All comparisons use identical `ModelComparisonKey` intersections and report
native plus matched coverage. The experiment order and promotion gates are in
`PHASE7_2_EXPERIMENT_ROADMAP.md` and `PHASE7_2_PROMOTION_POLICY.md`.
