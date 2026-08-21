# Binance Historical Kline Contract

Verified against official Binance material on 2026-08-19.

## Research priority

Binance USD-M `BTCUSDT` perpetual futures are the primary Phase 1 research dataset. Binance Spot `BTCUSDT` remains supported as a secondary/cross-market dataset. This priority changes defaults only: the two markets retain different endpoints, source identifiers, instrument snapshots, manifests, and bronze paths.

## Supported mechanisms

1. Spot REST: `GET /api/v3/klines`. The public market-data-only host `https://data-api.binance.vision` supports this endpoint without authentication.
2. USD-M futures REST: `GET /fapi/v1/klines` on `https://fapi.binance.com`, also public.
3. Binance Public Data: `https://data.binance.vision` publishes daily and monthly ZIP archives for Spot, USD-M futures, and COIN-M futures, with companion SHA-256 checksum files.

Phase 1 implements REST ingestion for bounded and recent ranges. The public archive is the preferred future optimization for multi-year bulk backfills because it reduces API load and supplies upstream checksums.

## Kline identity and fields

Klines are uniquely identified by open time. Spot and USD-M futures kline rows expose the same 12 ordered values used here:

1. open time;
2. open;
3. high;
4. low;
5. close;
6. base-asset volume;
7. close time;
8. quote-asset volume;
9. trade count;
10. taker-buy base-asset volume;
11. taker-buy quote-asset volume;
12. unused/ignored value.

The exchange returns prices and volumes as decimal strings. They are parsed directly into `Decimal` and written as `decimal128(38,18)`.

## Intervals and range semantics

Spot supports case-sensitive `1s`, `1m`, `3m`, `5m`, `15m`, `30m`, `1h`, `2h`, `4h`, `6h`, `8h`, `12h`, `1d`, `3d`, `1w`, and `1M`. The current Phase 1 implementation supports fixed-duration intervals and intentionally excludes calendar-month `1M`.

`symbol` and `interval` are required. `startTime`, `endTime`, and `limit` are optional. Binance interprets `startTime` and `endTime` in UTC; Spot also supports a `timeZone` parameter for candle boundaries, which this project deliberately does not send. The project exposes half-open `[start, end)` ranges and maps them to Binance's inclusive millisecond `endTime` by sending `end - 1 ms`.

## Pagination and rate limits

- Spot klines have request weight 2, default limit 500, and maximum limit 1,000.
- The current USD-M endpoint documentation gives a default limit of 500 and maximum of 1,500. Request weight is limit-dependent: below 100 = 1, 100-499 = 2, 500-1,000 = 5, and above 1,000 = 10. The adapter permits the documented 1,500 maximum for USD-M but defaults to 1,000 because it is more request-weight efficient. Spot remains capped at 1,000.
- Binance publishes active rate limits in `exchangeInfo` and reports used IP weight in `X-MBX-USED-WEIGHT-*` response headers.
- HTTP 429 means a request limit was exceeded. Repeated violations can produce an HTTP 418 IP ban. `Retry-After` supplies the required wait. The client honors that header and retries only idempotent GET requests, with bounded exponential backoff for transport and server failures.

Pagination advances fixed, non-overlapping time windows of at most `limit * interval`. Responses are filtered back to the requested half-open range and deduplicated by `(symbol, open_time)`. Conflicting duplicates are fatal.

## Timestamp conventions

- REST JSON time fields are milliseconds by default. Spot can return microseconds only when a caller explicitly requests that time unit; this client does not.
- Binance Public Data Spot files switched to microsecond timestamps from 2025-01-01 onward. USD-M examples remain millisecond based.
- The canonical Arrow schema uses `timestamp[us, tz=UTC]` and the parser explicitly detects millisecond versus microsecond source values. This avoids losing the archive's newer precision while keeping UTC semantics consistent.

## Spot versus USD-M futures

| Property | Spot | USD-M futures |
| --- | --- | --- |
| Research role | Secondary/cross-market | Primary |
| REST path | `/api/v3/klines` | `/fapi/v1/klines` |
| Default host | `data-api.binance.vision` | `fapi.binance.com` |
| Project market value | `spot` | `usdm` |
| Spot `timeZone` option | Available, not used | Not part of this contract |
| Canonical source | `binance_spot_rest` | `binance_usdm_futures_rest` |
| Instrument metadata | Spot `exchangeInfo` | USD-M `exchangeInfo` |

USD-M is the configured default; Spot must be selected intentionally. Spot and futures data are never merged under the same source identity.

## Official sources

- [Spot kline endpoint](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market)
- [Spot REST limits and timestamp units](https://developers.binance.com/en/docs/products/spot/rest-api)
- [Market-data-only hosts](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md)
- [Binance Public Data](https://github.com/binance/binance-public-data/blob/master/README.md)
- [USD-M market-data API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
- [USD-M kline endpoint](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data)
