# Phase 6 Higher-Timeframe Feature Research

Status: complete retrospective research  
Feature version: `market_v3_research-1.0.0`  
Experiment: `phase6-btc-a6d0815c4adf041bf4107755`  
Gold: `gold-phase6-btc-a6d0815c4adf041bf4107755`

This report evaluates higher-timeframe BTCUSDT USD-M market context. It does
not promote a model, authorize Phase 7, or establish trading profitability.
Feature V2.1 remains unchanged; all additions live in a separate research
version.

## Lineage and availability

The research joins direct official Binance USD-M 12h and daily Silver candles
to the existing 5-minute Feature V2.1 family. Funding, mark, and index inputs
retain their Phase 4.1 lineage. The half-open research range ends at
`2026-07-01T00:00:00Z`; the permanent holdout begins
`2026-08-01T00:00:00Z` and contributes zero rows.

For a higher-timeframe candle opened at `t` with interval `I`:

```text
source_time       = t
availability_time = t + I
join condition    = availability_time <= 5m feature_time
```

Only completed candles can join. A partial 12h/daily bar is never exposed.
The Gold dataset stores both source and availability timestamps, and every
stored higher-timeframe availability is at or before its feature time.

## Formula notation

`O/H/L/C` are direct candle prices; `Q` is quote volume; `N` is trade count;
`BQ` is taker-buy quote volume; `EMA(n)` is the causal exponential moving
average; `RV(n)` is trailing return standard deviation; `ATR(14)` is trailing
true range; and `roll_mean/std/min/max` use only the current completed bar and
earlier bars. Ratios with invalid or zero denominators remain unavailable.

## New 12h candidates

| Feature | Formula / interpretation |
| --- | --- |
| `htf_12h_return` | `C[t]/C[t-1]-1` |
| `htf_12h_log_return` | `log(C[t]/C[t-1])` |
| `htf_12h_range_pct` | `(H-L)/O` |
| `htf_12h_body_ratio` | `(C-O)/(H-L)` |
| `htf_12h_upper_wick_ratio` | `(H-max(O,C))/(H-L)` |
| `htf_12h_lower_wick_ratio` | `(min(O,C)-L)/(H-L)` |
| `htf_12h_close_location` | `(C-L)/(H-L)` |
| `htf_12h_ema20_distance` | `C/EMA(20)-1` |
| `htf_12h_ema20_50_spread` | `EMA(20)/EMA(50)-1` |
| `htf_12h_ema20_slope_3bar` | `EMA20[t]/EMA20[t-3]-1` |
| `htf_12h_rsi14` | causal Wilder RSI(14) |
| `htf_12h_roc4` | four-bar rate of change |
| `htf_12h_realized_vol_1d` | `RV(2)` |
| `htf_12h_realized_vol_3d` | `RV(6)` |
| `htf_12h_realized_vol_7d` | `RV(14)` |
| `htf_12h_atr14_pct` | `ATR(14)/C` |
| `htf_12h_relative_quote_volume` | `Q/roll_mean(Q,20)` |
| `htf_12h_volume_zscore` | `(Q-roll_mean(Q,60))/roll_std(Q,60)` |
| `htf_12h_trade_count_intensity` | `N/roll_mean(N,20)` |
| `htf_12h_taker_buy_share` | `BQ/Q` |
| `htf_12h_taker_sell_share` | `1-BQ/Q` |
| `htf_12h_taker_flow_imbalance` | `2*BQ/Q-1` |

These features use direct 12h candles; exact 5-minute aggregation is only an
independent source reconciliation.

## New daily candidates

| Feature | Formula / interpretation |
| --- | --- |
| `htf_1d_return`, `htf_1d_log_return` | one-day simple and log returns |
| `htf_1d_range_pct` | `(H-L)/O` |
| `htf_1d_body_ratio` | `(C-O)/(H-L)` |
| `htf_1d_upper_wick_ratio`, `htf_1d_lower_wick_ratio` | normalized wick sizes |
| `htf_1d_close_location` | `(C-L)/(H-L)` |
| `htf_1d_ema20_distance` | `C/EMA(20)-1` |
| `htf_1d_ema50_distance` | `C/EMA(50)-1` |
| `htf_1d_ema100_distance` | `C/EMA(100)-1` |
| `htf_1d_ema200_distance` | `C/EMA(200)-1` |
| `htf_1d_ema20_50_spread` | `EMA(20)/EMA(50)-1` |
| `htf_1d_ema50_200_spread` | `EMA(50)/EMA(200)-1` |
| `htf_1d_ema20_slope_5d` | `EMA20[t]/EMA20[t-5]-1` |
| `htf_1d_rsi14` | causal Wilder RSI(14) |
| `htf_1d_roc7` | seven-day rate of change |
| `htf_1d_realized_vol_3d` | `RV(3)` |
| `htf_1d_realized_vol_7d` | `RV(7)` |
| `htf_1d_realized_vol_30d` | `RV(30)` |
| `htf_1d_atr14_pct` | `ATR(14)/C` |
| `htf_1d_volatility_zscore` | 30d volatility versus trailing 180d mean/std |
| `htf_1d_volatility_of_volatility` | trailing 30d std of 30d volatility |
| `htf_1d_relative_quote_volume` | `Q/roll_mean(Q,20)` |
| `htf_1d_volume_zscore` | `(Q-roll_mean(Q,60))/roll_std(Q,60)` |
| `htf_1d_trade_count_intensity` | `N/roll_mean(N,20)` |
| `htf_1d_taker_buy_share`, `htf_1d_taker_sell_share` | `BQ/Q`, `1-BQ/Q` |
| `htf_1d_taker_flow_imbalance` | `2*BQ/Q-1` |
| `htf_1d_distance_from_20d_high` | `C/roll_max(H,20)-1` |
| `htf_1d_distance_from_20d_low` | `C/roll_min(L,20)-1` |
| `htf_1d_distance_from_60d_high` | `C/roll_max(H,60)-1` |
| `htf_1d_distance_from_60d_low` | `C/roll_min(L,60)-1` |
| `htf_1d_drawdown_from_60d_high` | `C/roll_max(H,60)-1` |

The EMA200 and 180-day volatility normalization create the longest warmups.
They are intentionally unavailable until enough completed daily history exists.

## Cross-timeframe and stress candidates

| Feature | Formula / source |
| --- | --- |
| `trend_alignment_score` | mean sign of 5m, 12h, and daily EMA20 distance |
| `trend_conflict_score` | half-range of those three trend signs |
| `short_bounce_in_daily_bear` | 1h return positive while daily EMA20 distance is negative |
| `return_5m_over_daily_volatility` | 5m return / daily 30d volatility |
| `return_1h_over_daily_volatility` | 1h return / daily 30d volatility |
| `return_4h_over_7d_volatility` | 4h return / daily 7d volatility |
| `atr14_over_price_context` | 5m ATR% / daily ATR% |
| `stress_daily_drawdown` | positive magnitude of daily 60d drawdown |
| `stress_daily_volatility` | positive component of daily volatility z-score |
| `stress_12h_volume_shock` | positive component of 12h volume z-score |
| `stress_negative_taker_flow` | negative component of 12h taker imbalance |

The stress group is exploratory structured market context. It is not a Fear
Engine, fear score, or trading gate.

## Coverage, drift, and redundancy

The final research Gold contains 651,862 rows and 127 features: 61 inherited
Feature V2.1 derivatives-overlap columns plus 66 new candidates. Mean raw-row
coverage is 99.8073% for 12h, 98.4597% for daily, 99.5680% for cross-timeframe,
and 97.0454% for stress. Final Gold rows require every enabled feature, so
model ablations use identical rows despite different raw warmups.

Stability is reported monthly and yearly as median shift divided by the
feature's full-sample IQR. Maximum absolute yearly shifts are 0.9695 IQR for
12h, 1.2675 for daily, 1.0000 for cross-timeframe, and 1.0441 for stress.
These are diagnostics, not stationarity proofs.

At absolute Pearson correlation 0.98, the new families contain four 12h,
seven daily, zero cross-timeframe, and two stress pair memberships. Return vs
log-return, taker buy/sell/imbalance transforms, and duplicate high/drawdown
representations explain several of them. Individual classifications are
preserved in `feature_scorecard.json`; implementation is not deleted when a
candidate is marked redundant or rejected.

## Same-row 1h ablations

All results below use 39,224 identical sampled OOS rows, four chronological
folds, a 240-minute purge, 60-minute embargo, seed 42, and the same fixed
LightGBM parameters.

| Feature set | MAE | RMSE | R2 | Pearson IC | Spearman IC |
| --- | ---: | ---: | ---: | ---: | ---: |
| without 12h/1d | 0.00340095 | 0.00547831 | -0.000846 | 0.047854 | 0.034533 |
| +12h | 0.00339797 | 0.00547266 | 0.001217 | 0.056003 | 0.038519 |
| +1d | 0.00339878 | 0.00547196 | 0.001471 | 0.056589 | 0.035171 |
| +12h+1d | 0.00339796 | 0.00547025 | 0.002097 | 0.059613 | 0.037984 |
| +12h+1d+cross only | 0.00339994 | 0.00547303 | 0.001081 | 0.055186 | 0.032471 |
| +12h+1d+stress only | 0.00339848 | 0.00547298 | 0.001099 | 0.054335 | 0.035490 |
| full context | 0.00339869 | 0.00547399 | 0.000731 | 0.052108 | 0.035098 |

The 12h family adds +0.003986 pooled Spearman IC and is positive in all four
folds, but its yearly increment is negative in 2024 and 2025 and its low-vol
increment is negative. Daily alone adds only +0.000639. Combined 12h+daily
adds +0.003451. Cross-timeframe and stress additions reduce pooled Spearman by
0.005513 and 0.002494 respectively versus the 12h+daily reference.

## Scorecard and recommendation

| Family | Status | Interpretation |
| --- | --- | --- |
| `higher_timeframe_12h` | `KEEP_CANDIDATE` | modest retrospective increment; needs later confirmation |
| `higher_timeframe_1d` | `WEAK` | small aggregate increment and several redundant transforms |
| `cross_timeframe` | `REJECT` | current formulas reduce same-row OOS rank signal |
| `market_stress_research` | `REJECT` | current group reduces pooled rank signal |
| inherited Feature V2.1 families | `RESEARCH_ONLY` | preserved; not individually reselected in Phase 6 |

Gain and fold-4 permutation importance are diagnostics only. The top positive
permutation entries include `candle_range_pct`, `wick_balance_pct`,
`return_15m`, and `htf_12h_rsi14`; group ablations carry more weight than
individual importance. No feature is production-approved and no causal claim
is made.

Detailed immutable evidence is under
`local_artifacts/phase6/research_v1/phase6-btc-a6d0815c4adf041bf4107755/`.
