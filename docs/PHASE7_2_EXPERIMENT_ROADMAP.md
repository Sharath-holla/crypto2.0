# Phase 7.2 experiment roadmap

This roadmap preregisters future trial families. It does not authorize a run.
Every trial must declare hypothesis, exact feature/target/model change, primary
metric, promotion rule, seed, data manifest, universe and cost assumptions.
Failed trials remain in the ledger.

## Ordered experiment families

| Order | Family | Control | Challenger | Status |
|---:|---|---|---|---|
| 1 | `P7_BASELINE_TREE` | Ridge and naïve controls | G0/C0/P0/H0 LightGBM | First cloud run; not yet run |
| 2 | `P7_TREE_CHALLENGERS` | matched winning LightGBM row set | CatBoost | Disabled / not benchmarked |
| 3 | `P7_TREE_CHALLENGERS` | matched winning LightGBM row set | XGBoost | Disabled / not benchmarked |
| 4 | `P7_MICRO_1M` | BTC/ETH 5m baseline | same 5m rows plus `micro_1m_context_v1` | Disabled / period not selected |
| 5 | `P7_RANKING` | sort calibrated regression score | direct LambdaMART ranking | Disabled / label not selected |
| 6 | `P7_TARGET_CHALLENGERS` | independent v2 horizon regressions and multinomial control | `competing_risk_targets_v1` hazard model | Schema only / not trained |
| 7 | `P8_TEMPORAL` | best qualified tree | compact temporal models | Reserved; not authorized |

## Matched-comparison rules

Comparisons use `ModelComparisonKey`: symbol, feature time, target, horizon,
universe version, fold, cost model and feature schema. Each result reports
native coverage and intersection/matched coverage. No challenger receives more
history, future symbols, different TEST rows, different costs or a looser
calibration policy.

Cal-A owns prediction calibration. Cal-B owns policy/threshold selection. TEST
does not choose a model, label, threshold, feature or promotion rule.

## Primary measurements

- Regression: R², MAE, Pearson, Spearman and directional diagnostics.
- Ranking: timestamp Spearman/rank IC, NDCG@k, top-k hit/value, turnover and
  concentration.
- Probability: Brier, log loss, slope/intercept, AUPRC and secondary ECE.
- Distribution: pinball loss, empirical coverage and interval width.
- Economics: gross, costs, net, expectancy, profit factor, Sharpe, Sortino,
  drawdown and turnover, always with sample/concentration disclosure.
- Robustness: chronological, unseen/new/delisted, volatility, liquidity-stress
  and data-degradation slices.

## Statistical preparation

Use moving/stationary block bootstrap and paired identical-row comparisons.
Track all trials for Deflated Sharpe and Probability of Backtest Overfitting.
White Reality Check or Hansen SPA is applied to declared candidate families
when the family has enough completed comparable trials. These tools do not
repair biased data or a contaminated holdout.

## BTC/ETH 1m pilot budget gate

Before selecting a period or running the pilot, record:

| Quantity | Required record |
|---|---|
| Rows | 1m input rows and matched 5m output rows by symbol |
| Storage | raw, canonical and feature bytes with compression |
| Memory | peak working-set memory for aggregation/features |
| CPU | acquisition validation and feature wall time |
| VM | estimated hours and instance shape; no resource is started by planning |

Scale beyond BTC/ETH only if the matched OOS improvement is statistically
credible, economically meaningful, broad across folds and worth the measured
resource cost.
