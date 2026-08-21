# Phase 6 Target Research

Status: complete retrospective research  
Label version: `label_v2_research-1.0.0`  
Experiment: `phase6-btc-a6d0815c4adf041bf4107755`

These targets are diagnostic labels, not execution rules, dynamic TP/SL
settings, or evidence of profitability. Phase 3 Label V1
`forward_return_60m` version `1.0.0` remains unchanged.

## Timing and gap contract

For completed 5-minute prediction candle row `i`, the research reference is:

```text
feature_time = boundary after candle i
entry_time   = open_time[i+1]
target row   = i + 1 + horizon_steps
return       = open[target row] / open[i+1] - 1
```

`horizon_steps` is 3, 6, 12, 24, or 48 for 15m, 30m, 1h, 2h, or 4h. The
entry reference is the next candle open at the boundary after the completed
prediction candle; the prediction candle's close is never reused as an entry
price. This is a label convention, not a claim of executable fill timing.

Every expected 5-minute open from the prediction row through the terminal
reference must exist. A gap invalidates the affected target and excursion.
`label_end_time` is stored separately for each horizon, and Gold admits a row
only if all five terminal times are before the exclusive Phase 6 cutoff.

## Return target results

The research Gold contains 651,862 finite rows per horizon. Fixed model probes
sample every twelfth eligible row, producing 39,224 pooled OOS observations
per feature-set/horizon comparison. The table reports the fixed full-context
LightGBM probe; no hyperparameter search was performed.

| Horizon | MAE | RMSE | R2 | Direction | Pearson IC | Spearman IC | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 15m | 0.00170905 | 0.00275323 | -0.002437 | 0.52486 | 0.05018 | 0.06892 | `TARGET_CANDIDATE` |
| 30m | 0.00240765 | 0.00390489 | 0.000068 | 0.51968 | 0.05523 | 0.05319 | `TARGET_CANDIDATE` |
| 1h | 0.00339869 | 0.00547399 | 0.000731 | 0.51157 | 0.05211 | 0.03510 | `TARGET_CANDIDATE` |
| 2h | 0.00480578 | 0.00767639 | -0.001400 | 0.50625 | 0.04408 | 0.02367 | `TARGET_CANDIDATE` |
| 4h | 0.00694425 | 0.01087010 | -0.012041 | 0.50642 | 0.02488 | 0.01417 | `RESEARCH_ONLY` |

`TARGET_CANDIDATE` means only that retrospective rank signal is positive in at
least three folds and the configured diagnostic threshold was met. It does
not mean economically viable, model-qualified, or production-approved.
Fifteen-minute rank IC is strongest, but it also implies the highest potential
turnover and has negative R2. Costs, spread, slippage, capacity, latency, and
policy selection were not evaluated.

Spearman IC is positive in all four folds for 15m, 30m, 1h, and 2h. The 4h
folds are `[0.01661, 0.04850, 0.02664, -0.00375]`, and its 2025/2026 yearly IC
is negative. No horizon is currently convincing enough for champion or
production promotion.

## Serial dependence

Overlapping forward windows create strong serial dependence. Target
autocorrelation at lags 1/3/12 rows is:

| Horizon | lag 1 | lag 3 | lag 12 |
| --- | ---: | ---: | ---: |
| 15m | 0.6502 | -0.0232 | -0.0055 |
| 30m | 0.8169 | 0.4783 | -0.0054 |
| 1h | 0.9063 | 0.7343 | -0.0198 |
| 2h | 0.9524 | 0.8645 | 0.4864 |
| 4h | 0.9758 | 0.9311 | 0.7365 |

This is why the probes use chronological folds, a 240-minute purge, a
60-minute embargo, and a twelve-row sampling stride. Observation count must
not be mistaken for independent sample size.

## MFE and MAE definitions

For each entry reference and horizon, long maximum favorable excursion is the
largest entry-to-high return inside the horizon; long maximum adverse
excursion is the largest entry-to-low loss. Short-oriented MFE/MAE mirror the
long adverse/favorable values. They are evaluation labels only and are blocked
from the feature allowlist.

| Horizon | median MFE | MFE p95 | median MAE | MAE p95 | median MFE/MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| 15m | 0.001243 | 0.006578 | 0.001248 | 0.006703 | 0.9874 |
| 30m | 0.001791 | 0.009391 | 0.001797 | 0.009708 | 0.9865 |
| 1h | 0.002574 | 0.013367 | 0.002579 | 0.013915 | 0.9906 |
| 2h | 0.003720 | 0.019057 | 0.003737 | 0.019954 | 0.9914 |
| 4h | 0.005463 | 0.027073 | 0.005464 | 0.028371 | 0.9931 |

Excursions scale materially with volatility. At 1h, high-volatility median
MFE/MAE is 0.003520/0.003502 versus 0.002133/0.002147 in low volatility. Bear
1h median MAE (0.003534) exceeds MFE (0.003455); bull median MFE (0.003166)
slightly exceeds MAE (0.003127). Full regime/horizon distributions are in
`mfe_mae_analysis.json`.

Daily volatility has roughly 0.27 Spearman association with both MFE and MAE
across horizons. Fixed LightGBM OOS predicted return has only weak positive
association with MFE (Spearman 0.0406 to 0.0680) and near-zero/mixed
association with MAE (-0.0320 to 0.0198). This is useful diagnostic structure,
not a trade-management rule.

## Volatility-normalized barrier research

The 1h coarse-bar study uses prediction-row 5-minute ATR% applied to the next
open entry reference. Two fixed research pairs are evaluated:

```text
symmetric:             TP = +1.0 ATR, SL = -1.0 ATR
reward/risk asymmetric: TP = +1.5 ATR, SL = -1.0 ATR
```

If TP and SL first occur in different 5-minute bars, ordering is known. If
both occur in one 5-minute bar, validated 1-minute candles are consulted only
where the minute overlap exists. A same-minute overlap or absent 1-minute
coverage remains `AMBIGUOUS`; no favorable ordering is invented.

| Pair | TP | SL | timeout | ambiguous |
| --- | ---: | ---: | ---: | ---: |
| 1.0/1.0 ATR | 311,835 (47.84%) | 317,361 (48.69%) | 17,672 (2.71%) | 4,994 (0.77%) |
| 1.5/1.0 ATR | 234,204 (35.93%) | 366,601 (56.24%) | 48,505 (7.44%) | 2,552 (0.39%) |

Across the full label audit, 1-minute data resolved 326 symmetric and 137
asymmetric coarse overlaps. The remaining ambiguous labels include periods
before 1-minute coverage begins on `2025-07-01` and same-minute overlaps.
Regime percentages are preserved in `barrier_analysis.json`; they are not
final TP/SL parameters.

## Recommendation

- Retain 15m, 30m, 1h, and 2h as research candidates only.
- Keep 4h for diagnostics; its recent/fold stability is weak.
- Preserve MFE/MAE and ambiguity-safe barrier labels for future, separately
  authorized trade-management research.
- Do not design a dynamic TP/SL engine, risk engine, leverage policy, or live
  execution path from these retrospective results.

Detailed immutable evidence is under
`local_artifacts/phase6/research_v1/phase6-btc-a6d0815c4adf041bf4107755/`.
