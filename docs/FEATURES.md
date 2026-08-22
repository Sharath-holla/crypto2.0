# Baseline Feature Set V1

Feature version: `1.0.0`

All features are computed from the prediction candle or earlier completed candles. `feature_time` is the prediction candle's next interval boundary. No centered window, future shift, backfill, or global zero imputation is used.

| Feature | Definition | Minimum contiguous history |
| --- | --- | ---: |
| `return_5m` | `close[t] / close[t-1] - 1` | 2 candles |
| `return_15m` | `close[t] / close[t-3] - 1` | 4 candles |
| `return_30m` | `close[t] / close[t-6] - 1` | 7 candles |
| `return_1h` | `close[t] / close[t-12] - 1` | 13 candles |
| `log_return_5m` | `log(close[t] / close[t-1])` | 2 candles |
| `candle_range_pct` | `(high[t] - low[t]) / open[t]` | current candle |
| `candle_body_pct` | `(close[t] - open[t]) / open[t]` | current candle |
| `relative_volume` | current base volume divided by the trailing 12-candle mean, including current | 12 candles |
| `rolling_volatility_1h` | sample standard deviation of the trailing 12 five-minute log returns | 13 candles |
| `rolling_volatility_4h` | sample standard deviation of the trailing 48 five-minute log returns | 49 candles |
| `ema20_distance` | `close[t] / EMA20[t] - 1`; EMA is seeded by the first contiguous 20-candle mean | 20 candles |
| `ema50_distance` | `close[t] / EMA50[t] - 1`; EMA is seeded by the first contiguous 50-candle mean | 50 candles |
| `rsi14` | Wilder-smoothed 14-period RSI | 15 candles |

The complete official vector therefore requires 50 contiguous candles. Initial rows and the first 49 rows after any data gap are expected warm-up missingness and are excluded from Gold. Non-finite values after sufficient history are unexpected missingness and fail dataset construction.

Derived model values use `float64`; immutable Silver prices and volumes retain their exact Decimal representation. Gold manifests include missing/finite checks, descriptive distributions, percentiles, and constant/near-constant flags for every feature. Constant training features cause training to stop for review rather than being silently accepted.

The official feature list is an allowlist. Target-, future-, label-, and entry-reference-derived names cannot be added through configuration. Feature calculations live under `crypto_ai.features` so later inference code can reuse the same definitions.

## Market Feature Set V2

Feature version: `2.0.0`. The engine exposes 57 possible features and enabled
50 in the July experiment: 47 candle-derived features plus 3 funding features.
Basis (4) and open-interest (3) features activate only with causally complete,
validated inputs; unavailable groups are never encoded as zero.

| Group | Count | Examples |
| --- | ---: | --- |
| Price | 10 | multi-horizon returns, log return, range/body, upper/lower wick |
| Trend | 7 | EMA distances, spread/slopes, SMA48 distance |
| Momentum | 4 | RSI14, stochastic K, acceleration, positive-return share |
| Volatility | 5 | 1h/4h realized volatility, ATR%, range volatility, ratio |
| Volume | 5 | relative volumes/trades, average trade, 1h volume change |
| Pressure | 7 | taker buy/sell shares, imbalances, trailing alignment |
| Funding | 3 | latest known rate, causal 8h change, observation age |
| Basis | 4 | contract/mark and mark/index basis, change, z-score |
| Open interest | 3 | log/1h change and observation age |
| Regime V1 | 6 | trend/volatility scores and causal state flags |
| Time | 3 | UTC hour sine/cosine and weekend flag |

All rolling features require finite trailing observations. The validity gate
requires 336 contiguous five-minute candles, so gaps reset effective warm-up.
External values use only observations satisfying
`availability_time <= feature_time` and a dataset-specific maximum age.

Taker-sell volume is `total - taker_buy`; quote imbalance is
`(taker_buy_quote - taker_sell_quote) / quote_volume`. Negative derived sell
volume is a hard error. Regime V1 uses trailing 4h return and a causal one-day
normalization of trailing 4h volatility; it performs no full-sample fit.

The final 42-column Main Model V2 removes eight exact/near-exact
representations identified by the training-period redundancy audit while
leaving the immutable A0 Phase 3 baseline unchanged.

## Market Feature Set V2.1

Feature version `2.1.0` is additive: stored Feature V2/`market_v2` columns are
not renamed or reinterpreted. The long-history core has 52 columns: price 10,
trend 6, momentum 3, volatility 7, volume 6, taker flow 10, causal regime 7,
and UTC time 3. The derivatives-overlap family adds funding 3 and aligned
mark/index/basis 6 for 61 columns. OI would add 3 only when a legitimate shared
sample exists; it is not enabled in the multi-year run.

Canonical taker-flow columns are `taker_buy_base_share`,
`taker_sell_base_share`, `taker_buy_quote_share`,
`taker_sell_quote_share`, `taker_flow_imbalance_base`,
`taker_flow_imbalance_quote`, `taker_flow_imbalance_15m`,
`taker_flow_imbalance_1h`, `taker_buy_share_change_1h`, and
`taker_flow_price_alignment_1h`. With `V` as total base volume and `B` as
taker-buy base volume, sell volume is `V-B`, buy share is `B/V`, and imbalance
is `(B-(V-B))/V`. Quote features use the equivalent quote-volume fields. Zero
denominators remain unavailable; negative taker volume or `B>V` is a hard
failure. These values describe aggressive executed kline flow, not complete
historical order-book pressure.

The complete core vector requires 2,016 contiguous 5-minute candles (seven
days). Regime trend thresholds and volatility normalization are trailing and
historical. Future perturbations cannot change a past feature or regime;
missing intervals reset causal warm-up. External joins require
`availability_time <= feature_time`, with maximum age 12 hours for funding, 6
minutes for mark/index candles, and 10 minutes for OI.

## Market V3 research context

`market_v3_research-1.0.0` is an isolated Phase 6 research family; it does not
rename or reinterpret V2.1. It adds 22 completed-12h, 33 completed-daily, seven
cross-timeframe, and four market-stress candidates to the 61-column
derivatives-overlap V2.1 vector, for 127 columns. Direct Binance USD-M 12h/1d
Silver candles are canonical. A higher-timeframe value is joinable only after
`open_time + interval <= feature_time`.

The fixed same-row 1h ablation classifies 12h as `KEEP_CANDIDATE`, daily as
`WEAK`, and the current cross-timeframe and stress formulas as `REJECT`.
These are retrospective classifications, not production selection. Exact
definitions, coverage, stability, redundancy, and results are in
`PHASE6_FEATURE_RESEARCH.md`.

## Multiasset Features V1

Phase 7 adds `multiasset_features_v1` without modifying prior feature families.
It combines causal coin-local normalized price/volatility/volume/trade/taker
features with listing age, history, liquidity/volatility percentiles, rolling
BTC beta/correlation, ETH correlation, relative strength, BTC/ETH anchors,
point-in-time market breadth, completed 12h/daily context, and aligned public
funding/mark/index basis.

All rolling state is symbol-local and resets at reported 5m gaps. Anchor joins
require exact timestamps. Market aggregates use only registry-active symbols
available at that timestamp and persist a membership hash. Higher-timeframe
values require `availability_time <= feature_time`; 12h and daily streams are
aligned independently.

A0-A6 and independent BASE/12h/1d controls are defined in
`PHASE7_MULTI_ASSET_FEATURES.md`. They are research schemas, not production
feature approval.
