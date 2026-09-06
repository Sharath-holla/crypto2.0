# Feature Engineering

## Counts and timing

The mechanically catalogued A6 schema has **109 model columns**:

- **54 native** 5m/cross-asset/derivative columns (the canonical native A6 count);
- 22 completed 12h columns;
- 33 completed 1d columns.

Gold is wider because it also stores identity, lineage, timestamps, targets, horizon fields, and
three preview/source-helper columns. These are not automatically model inputs. Five-minute source
candle `i` is usable only at its close, `feature_time = open[i+1]`. Rolling state resets at a
reported gap. Missing/warm-up values stay null and model rows require finite selected inputs.

## Exact 54 native columns

| Family | Exact columns | Source/calculation and leakage protection |
| --- | --- | --- |
| Returns | `return_5m`, `return_15m`, `return_30m`, `return_1h`, `return_4h` | Close/lagged-close − 1 over 1/3/6/12/48 consecutive 5m rows; completed rows only |
| Candle/trend | `range_pct`, `body_pct`, `atr14_pct`, `ema20_distance_pct` | Normalized OHLC geometry, gap-reset ATR14/EMA20; valid denominators and warm-up required |
| Volatility | `realized_volatility_1h`, `daily_volatility`, `seven_day_volatility` | Sample std of 5m log returns over 12/288/2016 causal rows |
| Volume/activity | `relative_quote_volume`, `volume_zscore`, `trade_count_zscore` | 2016-row causal mean/std; activity proxy, not market depth |
| Executed taker flow | `taker_buy_share`, `taker_sell_share`, `taker_flow_imbalance` | Kline taker-buy quote share and complement/difference; not order-book pressure |
| Vol-normalized returns | `return_5m_over_ex_ante_vol`, `return_1h_over_daily_vol`, `return_4h_over_7d_vol` | Causal numerator divided by causal nonzero volatility |
| Derivative context | `funding_zscore`, `mark_index_basis`, `contract_mark_basis` | Funding as-of max age 24h; mark/index max age 5m; stale/missing stays null |
| Lifecycle | `listing_age_days`, `history_length_days` | Days from verified `available_from`; row must be inside lifecycle |
| Cross-sectional ranks | `trailing_liquidity_percentile`, `trailing_volatility_percentile`, `trade_intensity_percentile` | Rebound at each timestamp to frozen fold-active symbols, not acquisition union |
| Coin/anchor relationships | `btc_beta`, `btc_correlation`, `eth_correlation`, `relative_strength_vs_btc`, `relative_strength_vs_eth`, `beta_adjusted_residual_return` | Exact-time anchor joins and causal 2016-row pair statistics; no forward fill |
| BTC context | `btc_return_5m`, `btc_return_15m`, `btc_return_30m`, `btc_return_1h`, `btc_return_4h`, `btc_volatility_1h`, `btc_taker_flow_imbalance` | Exact-timestamp BTC copies; missing BTC remains null |
| ETH context | `eth_return_5m`, `eth_return_1h`, `eth_return_4h`, `eth_volatility_1h` | Exact-timestamp ETH copies; missing ETH remains null |
| Market breadth/context | `market_mean_return`, `market_median_return`, `market_pct_positive`, `market_pct_negative`, `market_return_dispersion`, `market_median_volatility`, `market_median_taker_flow_imbalance`, `market_member_count` | Recomputed only from the fold's frozen active members; membership hash persisted |

The 24 base-return/candle/volatility/volume/taker/derivative/normalized columns plus 11 coin-context,
11 BTC/ETH-anchor, and 8 market-context columns total 54.

## Higher-timeframe context

The 22 12h columns are:

`htf_12h_return`, `htf_12h_log_return`, `htf_12h_range_pct`, `htf_12h_body_ratio`,
`htf_12h_upper_wick_ratio`, `htf_12h_lower_wick_ratio`, `htf_12h_close_location`,
`htf_12h_ema20_distance`, `htf_12h_ema20_50_spread`, `htf_12h_ema20_slope_3bar`,
`htf_12h_rsi14`, `htf_12h_roc4`, `htf_12h_realized_vol_1d`,
`htf_12h_realized_vol_3d`, `htf_12h_realized_vol_7d`, `htf_12h_atr14_pct`,
`htf_12h_relative_quote_volume`, `htf_12h_volume_zscore`,
`htf_12h_trade_count_intensity`, `htf_12h_taker_buy_share`, `htf_12h_taker_sell_share`,
`htf_12h_taker_flow_imbalance`.

The 33 1d columns are:

`htf_1d_return`, `htf_1d_log_return`, `htf_1d_range_pct`, `htf_1d_body_ratio`,
`htf_1d_upper_wick_ratio`, `htf_1d_lower_wick_ratio`, `htf_1d_close_location`,
`htf_1d_ema20_distance`, `htf_1d_ema50_distance`, `htf_1d_ema100_distance`,
`htf_1d_ema200_distance`, `htf_1d_ema20_50_spread`, `htf_1d_ema50_200_spread`,
`htf_1d_ema20_slope_5d`, `htf_1d_rsi14`, `htf_1d_roc7`,
`htf_1d_realized_vol_3d`, `htf_1d_realized_vol_7d`, `htf_1d_realized_vol_30d`,
`htf_1d_atr14_pct`, `htf_1d_volatility_zscore`, `htf_1d_volatility_of_volatility`,
`htf_1d_relative_quote_volume`, `htf_1d_volume_zscore`,
`htf_1d_trade_count_intensity`, `htf_1d_taker_buy_share`, `htf_1d_taker_sell_share`,
`htf_1d_taker_flow_imbalance`, `htf_1d_distance_from_20d_high`,
`htf_1d_distance_from_20d_low`, `htf_1d_distance_from_60d_high`,
`htf_1d_distance_from_60d_low`, `htf_1d_drawdown_from_60d_high`.

For any HTF candle: `availability_time = open_time + interval`, and the as-of join requires
`availability_time <= feature_time`. `valid_until`/maximum-age rules prevent stale context. The
12h and 1d streams join independently so absence in one does not erase a valid value in the other.

## Cross-sectional and Gold-only fields

Acquisition-union market values are tagged `ACQUISITION_UNION_PREVIEW` and forbidden as model-ready
context. Model-facing percentiles/breadth are rebuilt after fold membership freezes and tagged
`FOLD_ACTIVE_SYMBOLS`. Helper fields such as `cross_sectional_trailing_liquidity_source`,
`cross_sectional_volatility_source`, and `cross_sectional_trade_intensity_source` exist to support
that rebinding but are excluded from the 109 model columns.

Fear & Greed and open interest are disabled from Phase 7 training; MFE/MAE are targets/diagnostics,
never features. See the code-derived `docs/PHASE7_1_FEATURE_CATALOG.md` for the authoritative
formula-level catalog.
