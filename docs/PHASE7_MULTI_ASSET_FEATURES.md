# Phase 7 Multi-Asset Features and Targets

## Identity and timing

Phase 7 introduces `multiasset_features_v1`, `market_context_v1`, and
`multiasset_targets_v1`. The canonical feature key is:

```text
(symbol, feature_time)
```

For a 5-minute candle opened at `t`, `feature_time = t + 5m`. The candle must
be complete. Entry remains the next 5-minute open. Target horizons are 15, 30,
60, and 120 minutes after that entry reference. All ranges are half-open UTC.
Every label requires a complete consecutive future path and
`label_end_time < 2026-07-01T00:00:00Z`.

Consequently all Phase 7 research features and label windows end before the
exclusive cutoff. July 2026 is an unused buffer. The prospective holdout from
`2026-08-01T00:00:00Z` is separately `LOCKED_UNUSED`, has zero rows, and is not
authorized for Phase 7 evaluation.

## Feature families

The implementation deliberately does not feed all Phase 6 research features
blindly. The cumulative ablations are:

- A0: normalized coin-local price, volatility, volume, trade, and taker-flow context;
- A1: A0 plus BTC context;
- A2: A1 plus ETH context;
- A3: A2 plus point-in-time market breadth/context;
- A4: A3 plus completed 12-hour context;
- A5: A4 plus completed daily context; and
- A6: A5 plus funding and mark/index/contract basis features.

Independent `BASE`, `BASE_PLUS_12H`, `BASE_PLUS_1D`, and
`BASE_PLUS_12H_1D` controls prevent the 12-hour and daily claims from being
hidden inside cumulative additions.

## Cross-asset normalization

Raw price scale is not treated as comparable between coins. Coin-local causal
features include lagged returns, range/body percentages, ATR percentage,
EMA distance, realized volatility, relative quote volume, rolling z-scores,
trade intensity, and taker-buy/sell shares. Taker flow means aggressive
executed flow inside the kline; it is not order-book depth or total market
buying/selling pressure.

Ex-ante volatility-normalized return features divide only by volatility
available at feature time. The normalized target is:

```text
raw future return / max(abs(feature-time daily volatility), floor)
```

A normalized model prediction is multiplied by that same stored ex-ante scale
before raw-return metrics, thresholds, or cost evaluation. Future volatility
is never accepted by the interface.

## Coin and anchor context

Coin context includes point-in-time listing age, history length, trailing
liquidity/volatility/trade percentiles, rolling BTC beta/correlation, ETH
correlation, BTC/ETH relative strength, and beta-adjusted residual return.
Rolling state resets at every reported candle gap.

Both listing age and cold-start age are measured from verified
`available_from`, not from later status or a potentially earlier descriptive
`onboard_date`. Fold age buckets are frozen at `fold.train_end` as 365–729,
730–1459, and 1460+ days.

BTC and ETH anchor values are exact timestamp joins. Missing anchor rows remain
missing; they are never forward-filled. Tests perturb future BTC, ETH, and
altcoin prices and assert that earlier features are unchanged.

## Market context and survivorship

At each feature timestamp, market means, medians, positive/negative breadth,
dispersion, median volatility, median taker-flow imbalance, and member count
use only registry-active symbols with a row available then. Each row stores a
hash of that timestamp's membership. A symbol appearing later cannot change an
earlier breadth value.

The data stage may contain the bounded union of symbols admitted by at least
one historical expansion fold, but market context remains timestamp-local. A
symbol has no membership before official evidence and cannot affect earlier
normalization, percentiles, breadth, feature statistics, or symbol counts.
Future survival and post-TRAIN liquidity are never consulted.

Phase 7 evaluates the same features in two labeled views: `CORE`, using
eligible `core_universe_v1` members, and `EXPANDING`, using
`fold_active_symbols`, the eligible core plus causally admitted
`expansion_universe_v1` members. The views have separate reports and
checkpoints; their results are never silently mixed.

## Higher-timeframe and derivatives joins

12-hour and daily features become available at `open_time + interval`. The
as-of rule is strictly:

```text
source availability_time <= feature_time
```

12-hour and daily streams are aligned independently so one timeframe cannot
erase the latest known value from the other. Funding is aligned from its event
availability with a 24-hour maximum age. Mark and index 5-minute klines use a
5-minute maximum age. Missing or stale values remain null.

Official semantics were reverified on 2026-08-22 against Binance's public
[kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Kline-Candlestick-Data),
[funding-rate](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History),
[mark-price kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Mark-Price-Kline-Candlestick-Data),
and [index-price kline](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Index-Price-Kline-Candlestick-Data)
documentation.

## Storage

Gold is partitioned by symbol and year. The cloud builder processes bounded
year chunks with only the required 5-minute and higher-timeframe warm-up and
future-label buffer. It does not require one all-coins/all-years feature matrix
in memory. Every manifest freezes the registry, `dual_universe_v2` definition,
`core_universe_v1`, expansion-policy and acquisition-union hashes,
feature/target versions, source lineage, file checksums, coverage, and the
unused holdout flags. Fold reports additionally freeze their exact active
membership hash.
