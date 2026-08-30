# Phase 7 Multi-Asset Features and Targets

## Identity and timing

Phase 7.1 uses `multiasset_features_v2`, `market_context_v2`, and
`multiasset_targets_v2`. The canonical feature key is:

```text
(symbol, feature_time)
```

For a 5-minute candle opened at `t`, `feature_time = t + 5m`. The candle must
be complete. Target v2 then reserves one complete decision-latency bar and
references entry at `t + 10m`, the open after feature availability. Thus for
row `i`, `feature_time=open[i+1]`, `entry_time=open[i+2]`, and an `H`-bar
horizon ends at `open[i+2+H]`. Target horizons are 15, 30, 60, and 120 minutes
from that simulated entry. The 4h horizon is not configured in Phase 7. All
ranges are half-open UTC.

The superseded `multiasset_targets_v1` is retained as an explicit audit-only
function. It reproduces the prior same-boundary `entry_time == feature_time`
construction, but it is no longer the configured target identity and must not
be used for Phase 7 economic qualification. Existing Phase 1–6 labels and
artifacts were not changed or overwritten.
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

At acquisition/Gold construction, market context is explicitly marked
`ACQUISITION_UNION_PREVIEW`; it is not model-ready because the bounded
acquisition union contains symbols admitted by later folds. Source values for
liquidity, volatility and trade intensity are retained as non-model helper
columns.

After causal fold eligibility filtering, every model-facing percentile, mean,
median, breadth, dispersion, volatility, taker-flow, member count and membership
hash is recomputed from that fold's frozen active-symbol rows and marked
`FOLD_ACTIVE_SYMBOLS`. Training never consumes the preview values.

The data stage may contain the bounded union of symbols admitted by at least
one historical expansion fold. A non-admitted symbol cannot affect a fold's
model normalization, percentiles, breadth, feature statistics or symbol count.
Future survival and post-TRAIN liquidity are never consulted for admission.

Phase 7 evaluates the same features in two labeled views: `CORE`, using
eligible `core_universe_v1` members, and `EXPANDING`, using
`fold_active_symbols`, the eligible core plus causally admitted
`expansion_universe_v2` members. The views have separate reports and
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
in memory. Every manifest freezes the registry, `dual_universe_v3` definition,
`core_universe_v1`, expansion-policy and acquisition-union hashes,
feature/target versions, source lineage, file checksums, coverage, and the
unused holdout flags. Fold reports additionally freeze their exact active
membership hash.
