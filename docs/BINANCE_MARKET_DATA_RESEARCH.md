# Binance USD-M Market Data Research

Last verified: 2026-08-20. This document covers public, unauthenticated BTCUSDT
USD-M futures data only. It is a research-source inventory, not permission to
use account, order, position, margin, leverage, or private API endpoints.

## Source strategy

Use the official Binance public archive for bulk historical files and the
public USD-M REST API for recent data, narrow gaps, and metadata. Every stored
dataset must retain the exact source identity, endpoint or archive path,
request range, retrieval time, checksum, and schema version. REST ranges are
normalized to half-open UTC `[start, end)` even when an upstream endpoint uses
inclusive bounds.

Official references:

- [USD-M REST market-data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [Binance public-data archive README](https://github.com/binance/binance-public-data/blob/master/README.md)
- [Binance archive download-tool README](https://github.com/binance/binance-public-data/blob/master/python/README.md)
- [USD-M API change log](https://developers.binance.com/docs/derivatives/change-log)

The Phase 6 recheck confirmed that the current USD-M kline contract still
accepts `12h` and `1d`, returns the standard 12 kline fields, and uses candle
open time as the record identifier. The public archive layout remains
`data/futures/um/monthly/klines/<symbol>/<interval>/` with sidecar checksum
files. The change log disclosed no Phase 6-relevant change to those kline
semantics. This verification does not authorize private or trading endpoints.

## Phase 4 classification

| Dataset | Public source | Historical behavior | Timestamp semantics | Phase 4 class | Decision |
|---|---|---|---|---|---|
| USD-M futures klines | Archive; `GET /fapi/v1/klines` | Archive supports daily/monthly bulk history; REST pages up to 1,500 rows | Candle open is event time; a feature can use a candle only at/after its close boundary | `MANDATORY_PHASE4` | Primary price, volume, trades, and taker-buy source |
| Funding-rate history | `GET /fapi/v1/fundingRate` | Public paginated history; shares a 500 requests/5 minutes/IP limit with funding-info | Funding time is both event and conservative availability time | `MANDATORY_PHASE4` | Ingest exact decimal rate and mark price; never assume a fixed 8-hour interval |
| Mark-price klines | Archive; `GET /fapi/v1/markPriceKlines` | Archive download scripts support futures mark klines from 2020-01-01; REST pages up to 1,500 rows | Use only after the mark candle closes | `MANDATORY_PHASE4` | Required for mark/contract basis features |
| Index-price klines | Archive; `GET /fapi/v1/indexPriceKlines` | Archive download scripts support futures index klines from 2020-01-01; REST pages up to 1,500 rows | Use only after the index candle closes | `MANDATORY_PHASE4` | Required for mark/index basis features |
| Premium-index klines | Archive; `GET /fapi/v1/premiumIndexKlines` | Archive download scripts support premium klines from 2020-01-01; REST pages up to 1,500 rows | Use only after the premium candle closes | `RECOMMENDED_PHASE4` | Prefer direct premium where coverage overlaps; basis remains independently derivable |
| Open-interest statistics | `GET /futures/data/openInterestHist` | Only the latest month is documented; up to 500 rows/request | Response timestamp is the end of the statistics period | `SHORT_HISTORY_ONLY` | Preserve as optional group with coverage and staleness diagnostics; never shrink all long-history experiments silently |
| Current open interest | `GET /fapi/v1/openInterest` | Current snapshot only | Transaction time is availability time | `LIVE_ONLY` | Excluded from historical training and backtests |
| Taker buy/sell statistics | `GET /futures/data/takerlongshortRatio` | Only the latest 30 days are documented; up to 500 rows/request | Response timestamp is the start of the period, so availability is conservatively shifted to the period end | `SHORT_HISTORY_ONLY` | Optional diagnostic; canonical kline taker-buy fields provide the long-history pressure proxy |
| Aggregate trades | Archive; `GET /fapi/v1/aggTrades` | Archive supports bulk history; REST is limited to recent data and sub-hour time windows | Individual trade event time; usable after receipt | `RECOMMENDED_PHASE4` | Archive-compatible adapter boundary; not required for the first bar-level V2 experiment |
| Raw trades | Archive | Bulk trade files are available from the official archive | Individual trade event time | `OPTIONAL_LATER` | High data volume; add only after bar-level marginal value is measured |
| Partial depth / order book | `GET /fapi/v1/depth`; WebSocket streams | REST is a current snapshot and streams are forward collection, not an official replay-quality long history | Snapshot/receipt time | `LIVE_ONLY` | Do not use in historical model training without a separately versioned collector |
| Book ticker | `GET /fapi/v1/ticker/bookTicker`; WebSocket | Current best bid/ask only; no dependable official long-history replay source documented | Transaction/receipt time | `LIVE_ONLY` | Backtester uses configurable spread assumptions instead of fabricated history |
| Liquidations | Public liquidation stream / recent endpoints where exposed | No dependable complete long-history public archive is documented | Event/receipt time | `NOT_RELIABLY_AVAILABLE` | Excluded from Main Model V2 |
| Global/account long-short ratios | `GET /futures/data/globalLongShortAccountRatio` and related endpoints | Only the latest 30 days are documented | Period timestamp; availability at period completion | `SHORT_HISTORY_ONLY` | Optional diagnostic, not a mandatory main-model input |
| Futures basis statistics | `GET /futures/data/basis` | Only the latest 30 days are documented | Period timestamp; availability at period completion | `SHORT_HISTORY_ONLY` | Main basis is instead calculated from causally aligned futures/mark/index candles |

## Field semantics used by Feature V2

The canonical USD-M kline contains open, high, low, close, base-asset volume,
quote-asset volume, trade count, taker-buy base volume, and taker-buy quote
volume. Long-history taker-sell quantities are derived exactly within each
closed bar:

```text
taker_sell_base  = base_volume  - taker_buy_base_volume
taker_sell_quote = quote_volume - taker_buy_quote_volume
buy_share        = taker_buy_quote_volume / quote_volume
sell_share       = taker_sell_quote / quote_volume
pressure_imbalance = (taker_buy_quote_volume - taker_sell_quote) / quote_volume
```

All denominators must be positive. Negative derived sell volume, buy volume
greater than total volume, impossible OHLC values, duplicates, non-monotonic
timestamps, and non-finite values are validation failures.

Funding rates are stored as exact decimals. Positive funding means longs pay
shorts; negative funding means shorts pay longs. A backtest applies a funding
cash flow only when an actual funding timestamp falls inside the held interval.
No hard-coded settlement interval is used.

## Causal alignment contract

Every external observation has `event_time` and `availability_time`. A feature
row at `feature_time` may join only a record satisfying:

```text
availability_time <= feature_time
```

The join records age/staleness, applies a dataset-specific maximum age, and
sets an explicit availability flag. It does not backward-fill, use nearest
future observations, or treat absence as the numeric value zero. A model
ablation that requires a dataset must use the same overlapping timestamps for
all models being compared.

## Known source limitations

- The official archive may replace a previously published file and checksum.
  Bronze storage therefore versions downloaded bytes/checksums and never
  silently overwrites an existing partition.
- Open-interest and ratio endpoints expose short rolling histories. Their
  absence outside those windows is source unavailability, not missing market
  activity.
- Current depth and book-ticker endpoints cannot reconstruct historical spread
  or queue position. Phase 4 cost tests therefore use transparent configurable
  assumptions and stress scenarios.
- Fees vary by product, user tier, maker/taker status, promotions, and time.
  Phase 4 stores fee assumptions in each backtest artifact rather than claiming
  that one number is universally current.

## Phase 4.1 verified bulk-history findings

The official archive documents daily and monthly files plus sidecar checksum
files, and warns that previously published archives can be replaced. Its USD-M
download tooling documents kline, mark, index, and premium history from
2020-01-01. Phase 4.1 therefore verifies each checksum and ZIP, retains every
downloaded byte under its checksum, and converts source-independent exact
decimal candles into immutable daily Bronze partitions. REST remains the
secondary transport for metadata, current increments, and verified gaps.

The current USD-M instrument metadata reported BTCUSDT onboarding at
`2019-09-08T17:55:00Z`; the official monthly archive begins at 2020-01. The
launch-period REST history contains placeholder zero-volume bars, so the first
continuously active trustworthy candle used by this research is
`2019-09-10T05:40:00Z`. The discarded launch placeholders are preserved and
quarantined rather than rewritten. The explicit Phase 4.1 cutoff is
`2026-08-01T00:00:00Z`.

Field comparison against current REST found two stale official archive days:
2023-11-10 (19 differing candles) and 2024-10-28 (15 differing candles). Both
sources, comparison reports, and checksums are retained. The reconciled Silver
manifest selects current official REST for exactly those daily partitions and
the archive everywhere else. This is auditable source composition, not silent
raw repair.

Mark and index archives contain a handful of timestamps absent from both the
archive and current REST. These observations are not synthesized. Their Silver
coverage remains above 99.997%, and affected derivatives feature rows are
excluded by the causal availability gate. Historical OI remains optional
because the official statistics endpoint documents only short retention.

| Validated Phase 4.1 source | Half-open research coverage | Rows/events | Result |
| --- | --- | ---: | --- |
| USD-M 5m active-launch REST bridge | `[2019-09-10 05:40, 2020-01-01)` | 32,476 | WARN-only outlier candidates; no gaps/duplicates/errors |
| USD-M 5m reconciled archive era | `[2020-01-01, 2026-08-01)` | 692,352 | WARN-only outliers/33 zero-volume bars; no gaps/duplicates/errors |
| USD-M 1m execution support | `[2025-07-01, 2026-08-01)` | 570,240 | WARN-only outliers/18 zero-volume bars/verified flat run |
| Funding events | `2019-09-10 08:00` through `2026-07-31 16:00` | 7,550 | Exact event timestamps; no fixed schedule assumed |
| Mark-price 5m | `[2020-01-01, 2026-08-01)` | 692,338 | 14 timestamps absent from archive and REST; not synthesized |
| Index-price 5m | `[2020-01-01, 2026-08-01)` | 692,339 | 13 timestamps absent from archive and REST; not synthesized |
| Open-interest history | Not acquired for multi-year family | 0 | Official retention is too short for a legitimate D3 comparison |

## Phase 6 higher-timeframe context

Phase 6 adds direct official BTCUSDT USD-M `12h` and `1d` candles as research
context. They describe slower trend, volatility, volume/taker flow, market
structure, and drawdown state; they are not execution intervals and are not
automatically prediction horizons. The same Bronze, Silver, manifest,
checksum, exact-decimal, and quality pipeline used by the 5-minute history is
reused without a parallel data system.

The conservative Phase 6 cutoff is `2026-07-01T00:00:00Z`, one month before
the locked prospective holdout. Direct coverage before that cutoff is:

| Interval | First open | Last open | Rows | Gaps | Duplicates | Quality |
| --- | --- | --- | ---: | ---: | ---: | --- |
| 12h | `2019-09-08T12:00:00Z` | `2026-06-30T12:00:00Z` | 4,975 | 0 | 0 | PASS |
| 1d | `2019-09-08T00:00:00Z` | `2026-06-30T00:00:00Z` | 2,488 | 0 | 0 | PASS |

Direct klines are canonical. Exact 5-minute aggregation is retained only as an
independent reconciliation. Of 4,971 comparable 12h candles, 4,963 match in
all nine OHLCV/trade/taker fields; of 2,485 comparable daily candles, 2,477
match exactly. The eight discrepancies in each interval cluster around known
source-revision dates and the launch period. They are reported, not repaired
or averaged, and do not change the direct-source policy.

A higher-timeframe candle with open time `t` and interval `I` has conservative
`availability_time = t + I`. A 5-minute feature row may use it only when
`availability_time <= feature_time`. Partial current 12h/daily candles are
therefore impossible to join, and future-source perturbation tests verify that
later higher-timeframe values cannot alter earlier feature rows.
