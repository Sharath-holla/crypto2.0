# Phase 7.1 feature catalog

Code-derived inventory date: 2026-08-24. The configured full A6 schema contains
109 model columns: 54 native 5-minute/cross-asset columns, 22 completed 12-hour
columns, and 33 completed daily columns. This count excludes identity, lineage,
target, and the three retained cross-sectional source-helper columns. Nulls are
preserved; model rows are filtered for finite values rather than imputed or
forward-filled.

Common timing rule: a 5-minute candle opened at `t` becomes available at
`t+5m`, which is `feature_time`. Higher-timeframe values use
`availability_time=open_time+interval <= feature_time`. Every rolling transform
resets after a reported candle gap. `A0..A6` below refers to the cumulative
allowlist in `feature_ablation_sets`.

| Feature(s) | Class / allowlist | Formula and source | Availability, missingness, risk, recommendation |
|---|---|---|---|
| `return_5m`, `return_15m`, `return_30m`, `return_1h`, `return_4h` | REQUIRED BASELINE / A0 | `close[t]/close[t-lag]-1`, lags 1/3/6/12/48; USD-M 5m kline. | Completed candle only; null during warm-up or gaps. Keep. |
| `range_pct`, `body_pct` | REQUIRED BASELINE / A0 | `(high-low)/open`, `(close-open)/open`; USD-M 5m OHLC. | Same-row completed candle; invalid denominator stays null. Keep. |
| `atr14_pct` | REQUIRED BASELINE / A0 | Wilder-style 14-bar true-range scale divided by price. | Gap-reset, warm-up null. Keep scale-normalized. |
| `ema20_distance_pct` | REQUIRED BASELINE / A0 | `close/EMA20(close)-1`. | EMA begins after 20 consecutive finite rows and never crosses a gap. Keep. |
| `realized_volatility_1h`, `daily_volatility`, `seven_day_volatility` | REQUIRED BASELINE / A0 | Sample standard deviation of 5m log returns over 12/288/2016 rows. | Full window required; ex-ante only. Keep; do not globally normalize. |
| `relative_quote_volume`, `volume_zscore` | REQUIRED BASELINE / A0 | quote volume divided by, and z-scored against, causal 2016-row mean/std. | Full finite window; no fill. Keep as liquidity/activity proxy, not depth. |
| `trade_count_zscore` | REQUIRED BASELINE / A0 | trade count z-score over 2016 rows. | Full finite window. Keep as activity, not unique-trader count. |
| `taker_buy_share`, `taker_sell_share`, `taker_flow_imbalance` | REQUIRED BASELINE / A0 | taker-buy quote volume/quote volume; `1-buy`; `buy-sell`. | Completed kline; zero/invalid denominator null. Keep, but describe as executed aggressive flow, not order-book pressure. |
| `return_5m_over_ex_ante_vol`, `return_1h_over_daily_vol`, `return_4h_over_7d_vol` | REQUIRED BASELINE / A0 | causal return divided by causal 1h/1d/7d volatility. | Both operands must be finite/nonzero. Keep; perturbation-tested. |
| `funding_zscore` | CONTROLLED ABLATION / A6 | latest causal funding event, z-scored over the configured rolling window. | Event as-of, maximum age 24h; stale/missing null. Keep optional; never fabricate. |
| `mark_index_basis`, `contract_mark_basis` | CONTROLLED ABLATION / A6 | `mark/index-1`, contract kline close/mark-1. | Mark/index maximum age 5m; null on absence/staleness. Keep optional derivative context. |
| `listing_age_days`, `history_length_days` | CONTROLLED ABLATION / A0 | days from point-in-time verified `available_from` to feature time. | Registry lifecycle must contain row; otherwise null. Keep; future status/onboard date cannot substitute. |
| `trailing_liquidity_percentile`, `trailing_volatility_percentile`, `trade_intensity_percentile` | CONTROLLED ABLATION / A0 | timestamp cross-sectional percentile of causal volume mean, 7d volatility, and trade-count/mean. | Acquisition-union values are preview-only; model values are recomputed from frozen `fold_active_symbols`. Keep only with fold rebinding. |
| `btc_beta`, `btc_correlation`, `eth_correlation` | CONTROLLED ABLATION / A0 | 2016-row pair covariance/variance and correlation of coin 5m returns with exact-time BTC/ETH. | Full paired finite window; no anchor forward-fill. Keep. |
| `relative_strength_vs_btc`, `relative_strength_vs_eth` | CONTROLLED ABLATION / A0 | coin 1h return minus exact-time anchor 1h return. | Missing anchor gives null. Keep. |
| `beta_adjusted_residual_return` | CONTROLLED ABLATION / A0 | coin 1h return minus causal BTC beta × BTC 1h return. | Requires finite beta/anchor. Keep as controlled residual feature. |
| `btc_return_5m`, `btc_return_15m`, `btc_return_30m`, `btc_return_1h`, `btc_return_4h`, `btc_volatility_1h`, `btc_taker_flow_imbalance` | CONTROLLED ABLATION / A1 | Exact-timestamp copy of the corresponding BTC feature. | Missing BTC timestamp stays null. Keep as anchor ablation. |
| `eth_return_5m`, `eth_return_1h`, `eth_return_4h`, `eth_volatility_1h` | CONTROLLED ABLATION / A2 | Exact-timestamp copy of the corresponding ETH feature. | Missing ETH timestamp stays null. Keep as anchor ablation. |
| `market_mean_return`, `market_median_return`, `market_pct_positive`, `market_pct_negative`, `market_return_dispersion` | CONTROLLED ABLATION / A3 | Cross-sectional 5m return mean/median/sign fractions/sample std. | Rebuilt per timestamp from fold-active members; null/zero-member cases explicit. Keep only in `FOLD_ACTIVE_SYMBOLS` scope. |
| `market_median_volatility`, `market_median_taker_flow_imbalance`, `market_member_count` | CONTROLLED ABLATION / A3 | Cross-sectional median 1h volatility, median taker imbalance, and finite return member count. | Same fold-local rebinding and membership hash. Keep. |
| `htf_12h_return`, `htf_12h_log_return`, `htf_12h_range_pct`, `htf_12h_body_ratio`, `htf_12h_upper_wick_ratio`, `htf_12h_lower_wick_ratio`, `htf_12h_close_location` | CONTROLLED ABLATION / A4 | Completed direct USD-M 12h candle return/log return and normalized candle geometry. | Available only at 12h close; independent as-of join, null before first known value. Keep as A4. |
| `htf_12h_ema20_distance`, `htf_12h_ema20_50_spread`, `htf_12h_ema20_slope_3bar`, `htf_12h_rsi14`, `htf_12h_roc4` | CONTROLLED ABLATION / A4 | Causal 12h EMA trend, RSI14, and 4-bar rate of change. | Full causal warm-up; no fill across source gaps. Keep as A4. |
| `htf_12h_realized_vol_1d`, `htf_12h_realized_vol_3d`, `htf_12h_realized_vol_7d`, `htf_12h_atr14_pct` | CONTROLLED ABLATION / A4 | 12h log-return std over 2/6/14 bars and ATR14 percentage. | Completed direct 12h data only. Keep as A4. |
| `htf_12h_relative_quote_volume`, `htf_12h_volume_zscore`, `htf_12h_trade_count_intensity`, `htf_12h_taker_buy_share`, `htf_12h_taker_sell_share`, `htf_12h_taker_flow_imbalance` | CONTROLLED ABLATION / A4 | Causal 12h activity/flow ratios and rolling normalizations. | Full source window/valid denominator required. Keep as A4. |
| `htf_1d_return`, `htf_1d_log_return`, `htf_1d_range_pct`, `htf_1d_body_ratio`, `htf_1d_upper_wick_ratio`, `htf_1d_lower_wick_ratio`, `htf_1d_close_location` | CONTROLLED ABLATION / A5 | Completed direct USD-M daily candle return/log return and normalized geometry. | Available only at daily close; independent as-of join. Keep as A5. |
| `htf_1d_ema20_distance`, `htf_1d_ema50_distance`, `htf_1d_ema100_distance`, `htf_1d_ema200_distance`, `htf_1d_ema20_50_spread`, `htf_1d_ema50_200_spread`, `htf_1d_ema20_slope_5d` | CONTROLLED ABLATION / A5 | Daily EMA trend/distance/spread features. | Long causal warm-up creates expected nulls for newer coins. Keep and report cold-start coverage. |
| `htf_1d_rsi14`, `htf_1d_roc7` | CONTROLLED ABLATION / A5 | Daily RSI14 and 7-day rate of change. | Completed daily rows only. Keep. |
| `htf_1d_realized_vol_3d`, `htf_1d_realized_vol_7d`, `htf_1d_realized_vol_30d`, `htf_1d_atr14_pct`, `htf_1d_volatility_zscore`, `htf_1d_volatility_of_volatility` | CONTROLLED ABLATION / A5 | Daily return-volatility windows, ATR, vol z-score, and 30-day volatility-of-volatility. | Full causal window; missing stays null. Keep, with coverage ablation. |
| `htf_1d_relative_quote_volume`, `htf_1d_volume_zscore`, `htf_1d_trade_count_intensity`, `htf_1d_taker_buy_share`, `htf_1d_taker_sell_share`, `htf_1d_taker_flow_imbalance` | CONTROLLED ABLATION / A5 | Daily activity/flow ratios and rolling normalizations. | Completed source, full warm-up, valid denominators. Keep. |
| `htf_1d_distance_from_20d_high`, `htf_1d_distance_from_20d_low`, `htf_1d_distance_from_60d_high`, `htf_1d_distance_from_60d_low`, `htf_1d_drawdown_from_60d_high` | CONTROLLED ABLATION / A5 | close relative to causal rolling 20/60-day extrema. | Window excludes no future row; warm-up null. Keep. |
| Alternative.me Fear & Greed | REJECTED NOW / not in schema or allowlist | Separate provider-neutral context table. | Historical publication/knowledge time unverified. Disabled; do not join Phase 7. |
| Binance open interest | RESEARCH ONLY / not in schema or allowlist | Separate recent/forward-only public USD-M observations. | Official history is recent, not multi-year. Disabled; collect forward only under separate guard. |
| CryptoPanic, Arkham, Reddit, on-chain | FUTURE PHASE / absent | No approved source or implementation. | Publication lag, revisions, identity, and point-in-time history unresolved. Do not implement now. |
| MFE/MAE and barrier outcomes | TARGET DIAGNOSTICS / never features | Future path statistics used only as labels/economic diagnostics. | Must never enter same-row model allowlists. V2 return/MFE/MAE paths start at the post-signal entry. |

No negative-control feature is enabled in the configured baseline.
`include_rejected_negative_controls=false`. A negative control, if later added,
must be named, isolated from promotion, and registered as a separate experiment.
