# Phase 7.2 research capability upgrade

Phase 7.2 is additive. It prepares research capabilities without changing the
approved Phase 7 experiment. The first real cloud run remains a 5-minute,
54-feature, `multiasset_targets_v2`, G0/C0/P0/H0 LightGBM benchmark over 16
folds. None of the capabilities below is active in that run.

## 1. Why 5m remains primary

The 5m baseline is already specified, validated and byte-frozen. Its target
horizons are 15/30/60/120 minutes, so full 1m training would multiply highly
overlapping rows and cost without proven incremental information. Five-minute
rows reduce noise, memory pressure and training time. A finer data layer is not
evidence that a finer model row frequency is better.

## 2. Why 1m is context rather than baseline training

`canonical_market_1m_v1` represents completed half-open one-minute windows
with exact decimals, explicit availability time, missingness, quality,
eligibility, listing age and source identity. It can support later intrabar and
microstructure research. The default Phase 7.2 config leaves
`micro_1m_context_v1.enabled=false`; no Phase 7 module imports Phase 7.2.

## 3. One-minute architecture

```text
immutable Binance Bronze
        |
        v
canonical_market_1m_v1 (optional, immutable, no fabricated gaps)
        |
        +--> micro_1m_context_v1 (disabled experiment)
        |
        v
strict completed-window aggregation
        |
        v
5m model rows (unchanged sampling frequency)
```

The schema permits optional mark, index and funding state only when they are
actually available. Missing observations are flagged; OHLCV is never
forward-filled. Derived taker-sell volume is total minus valid taker-buy volume,
not order-book flow.

## 4. Deterministic 1m to 5m aggregation

`aggregate_1m_to_5m` requires five ordered, unique, contiguous, valid and
eligible observations aligned to a 5m boundary. It rejects incomplete windows,
duplicates, gaps, out-of-order input, invalid quality and early `as_of` times.
Open is first, high/low are extrema, close is last, and all volume/trade/taker
fields are sums. The result's availability time is the latest source-row
availability time, so it cannot exist before the fifth minute is known.

This utility does not replace the approved Phase 7 5m source.

## 5. Future micro-feature experiment

The compact `micro_1m_context_v1` family contains 17 interpretable short-window
features: 1/2/3/5m returns, realized volatility, shock/range/location,
directional consistency, momentum/reversal, volume/trade/taker acceleration and
volume concentration. Every source observation must be complete and available
by the 5m feature time.

The first possible experiment is BTCUSDT and ETHUSDT only:

- Control A: approved 5m features.
- Challenger B: identical rows, folds, targets, costs and evaluation plus
  `micro_1m_context_v1`.

The period is deliberately not selected before data availability and holdout
separation are reviewed. Failure to add matched OOS value rejects broad 1m
expansion.

## 6. Competing-risk research

`competing_risk_targets_v1` is separate from `multiasset_targets_v2`. It can
represent `UP_FIRST`, `DOWN_FIRST`, `NO_HIT`, event/censor time, barriers,
past-only volatility/cost references, MFE, MAE, path quality and ambiguity.

`IntrabarOrderStatus` is `ORDER_KNOWN`, `AMBIGUOUS` or `NOT_APPLICABLE`. When a
single available bar crosses both barriers and no finer ordering exists, the
event time is not invented: it is censored and excluded from cause loss.
Probability validators enforce
`P(UP by H) + P(DOWN by H) + P(NO HIT by H) = 1`, nondecreasing cumulative event
probabilities and nonincreasing survival/no-hit probability.

Future controls are independent horizon regressions and a multinomial
triple-barrier classifier; a discrete hazard model is only a challenger.

## 7. Ranking research

`cross_asset_ranking_v1` groups rows by exact `feature_time`. Membership is
strictly the fold's frozen `fold_active_symbols`; acquisition-union assets,
future listings and eventual survivors cannot enter. Rows are ordered
deterministically, missing targets remain explicit, and later-delisted assets
remain included when historically eligible.

The final relevance label is not selected. Candidate hypotheses include
cost-adjusted return and MFE/MAE/time-to-event quality. A future LambdaMART
ranker must use identical eligible rows and report rank IC, timestamp Spearman,
NDCG@k, top-k value, turnover and concentration.

## 8. Uncertainty and OOD

`ood_assessment_v1` is an interpretable TRAIN-fitted robust baseline using
medians and IQR-derived scales. It reports feature extremeness, unseen symbol,
listing-age status, missing/stale/invalid data and optional model disagreement.
Reasons and scores are deterministic. The default is monitor-only: OOD does
not silently remove a model row.

Conformal and adaptive-conformal objects remain research plans. Future reports
must show empirical coverage, interval width, regime stability and coverage
under drift. Coverage is not a guarantee of exchangeability or trading value.

## 9. Prospective data capture

Versioned schemas exist for forward-only OI, BBO/spread, compact depth
summaries, liquidation events, exchange metadata and EventContext. Every market
record separates event, receive and availability time and uses the common
`MISSING`, `STALE`, `VALID`, `INVALID`, `PROVIDER_ERROR` semantics.

Capture specifications and frozen-universe symbol selection are disabled. No
collector was started. Existing OI remains guarded, public, restart-safe,
checksummed and `FORWARD_ONLY`; it is not historical Phase 7 training data.

## 10. CatBoost/XGBoost challenger plan

Lightweight adapter specifications name a common feature schema, target,
folds, universe, calibration and cost model. CatBoost and XGBoost are disabled,
not installed by Phase 7.2, and not trained. `ModelComparisonKey` identifies
matched rows by symbol, feature time, target, horizon, universe, fold, cost and
feature schema. Native and matched coverage must be reported separately.

## 11. Future neural compatibility

The schema can later express asset, time and feature-family axes, missingness
and eligibility masks, fine 1m context, pooled 5m rows, higher-timeframe context
and cross-asset context. This is compatibility only. No TCN, RNN, Transformer,
PatchTST, Set Transformer or Phase 8 model exists in Phase 7.2.

## 12. Cost control

The BTC/ETH pilot must record rows, compressed storage, peak memory, CPU time
and expected VM hours before expansion. It does not train every minute; it
aggregates fine context onto existing 5m timestamps. Prospective capture starts
with small BBO records, depth summaries rather than raw L2, event-form
liquidations, legitimate 5m OI and metadata changes.

DuckDB, Polars, Iceberg and Spark are deferred. Current Pandas/PyArrow/Parquet
paths have no demonstrated bottleneck requiring a rewrite. Iceberg becomes an
option only if schema evolution, concurrent writers, snapshots/time travel or
multi-engine consistency justify it.

## 13. Baseline-preservation rules

- `configs/phase7/research_v1.toml` and every `crypto_ai.phase7` file remain
  byte-frozen by `phase7_scientific_baseline_v1_5` after the authorized
  acquisition-boundary, zero-volume aggregation, integrity-liquidity
  separation, and evidence-gated official archive-versus-REST reconciliation.
- Phase 7 modules do not import `crypto_ai.phase7_2`.
- Phase 7.2 defaults disable micro features, competing risks, ranking,
  CatBoost/XGBoost, capture, cloud/private/live activity, leverage and Phase 8.
- July remains unused and the August holdout remains `LOCKED_UNUSED`.
- Fear & Greed and historical OI remain disabled from training.

## 14. Future experiment order

1. Clean 5m LightGBM Phase 7 baseline.
2. Matched CatBoost.
3. Matched XGBoost.
4. BTC/ETH 5m baseline versus 5m plus `micro_1m_context_v1`.
5. Regression-score ranking versus a direct ranking objective.
6. `multiasset_targets_v2` controls versus `competing_risk_targets_v1`.
7. Only after those gates, separately authorized Phase 8 temporal/neural work.

Prediction remains separate from opportunity/ranking, `NO_OPPORTUNITY`,
downstream `NO_TRADE`, risk, portfolio, sizing, trade management and execution.
No ranking or prediction interface can submit an order.
