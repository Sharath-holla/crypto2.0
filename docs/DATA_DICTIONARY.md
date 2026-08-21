# Data Dictionary

## Phase 4 public derivatives records

Every Phase 4 market record contains `symbol`, `event_time`,
`availability_time`, `source`, and `ingested_at`. Numeric exchange values use
`decimal128(38,18)` in Bronze/Silver.

| Dataset | Value fields | Availability rule |
| --- | --- | --- |
| Funding | `funding_rate`, nullable `mark_price`, nullable `rate_type` | funding timestamp |
| Mark/index/premium kline | exact OHLC | candle open plus interval |
| Open-interest statistics | `sum_open_interest`, `sum_open_interest_value` | documented period-end timestamp |

Gold V2 retains Phase 3 `feature_time`, next-open `entry_time`,
`label_end_time`, exact entry/future reference prices, Label V1 target, ordered
Feature V2 columns, and version metadata. External joins require
`availability_time <= feature_time`; source age limits and missing behavior are
persisted in the manifest.

Schema version: `1.0.0`

Dataset: Binance canonical candles (`data/bronze/binance/klines`)

| Column | Arrow type | Null | Meaning |
| --- | --- | --- | --- |
| `symbol` | `string` | no | Uppercase Binance instrument identifier, initially `BTCUSDT`. |
| `open_time` | `timestamp[us, tz=UTC]` | no | Inclusive candle-open instant and natural candle key with `symbol`. |
| `close_time` | `timestamp[us, tz=UTC]` | no | Last represented instant before the next candle boundary. |
| `open` | `decimal128(38,18)` | no | First traded price in the interval. |
| `high` | `decimal128(38,18)` | no | Highest traded price in the interval. |
| `low` | `decimal128(38,18)` | no | Lowest traded price in the interval. |
| `close` | `decimal128(38,18)` | no | Last traded price in the interval. |
| `base_volume` | `decimal128(38,18)` | no | Traded quantity denominated in the base asset. |
| `quote_volume` | `decimal128(38,18)` | no | Traded notional denominated in the quote asset. |
| `trade_count` | `int64` | no | Number of trades reported by Binance. |
| `taker_buy_base_volume` | `decimal128(38,18)` | no | Base volume attributed to taker buys. |
| `taker_buy_quote_volume` | `decimal128(38,18)` | no | Quote volume attributed to taker buys. |
| `source` | `string` | no | `binance_spot_rest` or `binance_usdm_futures_rest`. |
| `ingested_at` | `timestamp[us, tz=UTC]` | no | UTC capture timestamp shared by a fetched partition. |

Prices and volumes are never converted through binary floating point. The ignored twelfth Binance kline value is intentionally not stored.

Dataset: ingestion manifest (`data/bronze/binance/manifests`)

Each JSON manifest records source, market, symbol, interval, half-open start/end, timestamps, total row count, file locations, schema and ingestion versions, instrument snapshot, per-file SHA-256, per-partition quality result, and terminal status.

`binance_usdm_futures_rest` is the primary research source. `binance_spot_rest` is secondary and remains in separate bronze partitions and manifests.

## Silver candles

Dataset: validated canonical candles (`data/silver/binance/klines`)

Silver retains every Bronze candle column and Arrow type above. It adds no technical indicators, labels, returns, or other research features. Rows are chronological and may remove only field-identical duplicates when the active policy explicitly allows them. Missing candles and statistical outliers remain visible.

Silver Parquet schema metadata adds:

| Metadata key | Meaning |
| --- | --- |
| `layer` | Always `silver`. |
| `source_layer` | Always `bronze`. |
| `source_file` / `source_sha256` | Immutable Bronze lineage. |
| `source_manifest` | Phase 1 ingestion manifest used for validation. |
| `source_dataset_version` | Deterministic version derived from the manifest and Bronze checksums. |
| `validation_report_id` | Deterministic Phase 2 report identifier. |
| `validation_version` | Validator rules version, currently `1.0.0`. |
| `silver_dataset_version` | Deterministic promoted-dataset identifier. |
| `exact_duplicates_removed` | Count removed from that Silver partition. |

## Quality reports

Dataset: JSON reports (`data/quality`), report schema version `1.0.0`.

Each report records report/dataset/validator versions, source/market/symbol/interval, half-open range, creation time, overall `PASS`/`WARN`/`FAIL`, source manifest, source files and checksums, the validated policy, aggregate summary, and typed checks.

Each check records name, status, severity (`INFO`, `WARNING`, `ERROR`, or `CRITICAL`), identity context, explanatory message, observed and expected values, affected-row count, bounded samples, and timestamp.

## Gold training dataset

Dataset: `data/gold/training_sets/<dataset-version>/dataset.parquet`, schema version `1.0.0`.

| Column | Arrow type | Meaning |
| --- | --- | --- |
| `symbol` | `string` | Instrument identity inherited from Silver. |
| `interval` | `string` | Candle interval used for all timing logic. |
| `prediction_candle_open_time` | `timestamp[us, tz=UTC]` | Open of the completed candle used for the feature vector. |
| `feature_time` | `timestamp[us, tz=UTC]` | Exact boundary when that prediction candle has completed. |
| `entry_time` | `timestamp[us, tz=UTC]` | Next candle open used as the Phase 3 entry reference. |
| `label_end_time` | `timestamp[us, tz=UTC]` | Open exactly 60 minutes after the entry reference. |
| `entry_reference_price` | `decimal128(38,18)` | Exact next-candle open used in the label equation. |
| `future_reference_price` | `decimal128(38,18)` | Exact horizon open used in the label equation. |
| 13 baseline feature columns | `float64` | Causal V1 values documented in `docs/FEATURES.md`. |
| `future_return_60m` | `float64` | `future_reference_price / entry_reference_price - 1`. |
| `label_name` | `string` | `forward_return_60m`. |
| `label_version` | `string` | Label definition version. |
| `feature_version` | `string` | Feature definition version. |

The Gold manifest records Silver files and checksums, Silver/Bronze dataset versions, validation report, feature/label configuration and hashes, target/feature distributions, warm-up and label-exclusion counts, dataset checksum, and deterministic version. Silver is never modified.

## Out-of-sample predictions

Each model prediction artifact stores symbol, `feature_time`, `label_end_time`, actual/predicted return, model name/version, dataset/feature/label versions, and `validation` or `test` split identity. Timestamps and future reference prices are metadata and never part of the official predictive feature list.

## Phase 4.1 archive and Gold V2.1 artifacts

Official archive ZIP bytes and supplied checksum files are stored below
`data/bronze/binance-public-data/archives` under a checksum-qualified path.
Canonical daily Bronze Parquet remains under the Binance candle tree and uses
the same exact-decimal schema regardless of `transport=archive` or
`transport=rest`. The manifest records object URL, archive/checksum SHA-256,
transport, source identity, and each canonical partition checksum.

A reconciliation manifest is composition metadata: it names the original
archive manifest, field-level archive/REST comparison reports, and only the
specific REST daily partitions allowed to replace discrepant archive days. It
does not modify either raw source. Silver records the effective per-partition
`row_source` and complete Bronze lineage.

Gold V2.1 lives under
`data/gold/market_intelligence_v2_1/<dataset-version>`. Its manifest identifies
the core or derivatives-overlap family, explicit cutoff, all source manifests
and hashes, Feature `2.1.0`, unchanged Label V1, enabled groups, join/staleness
policy, and row exclusions. `feature_coverage.json` reports group/column
availability, dates, expected and available rows, percentage, maximum gap,
missing reason, and source. `feature_stability.json` reports monthly median,
IQR, extreme-value rate, and normalized median drift. `target_analysis.json`
reports Label V1 overall, by year, and by causal regime.

## Phase 6 research Gold

Phase 6 Gold lives under
`data/gold/phase6_research/gold-<phase6-experiment-id>/`. It contains symbol,
`feature_time`, next-open `entry_time`, 12h/daily `source_time` and
`availability_time`, 127 ordered float64 research features, all Label V2
return/MFE/MAE/barrier values, five horizon-specific `label_end_time` columns,
and explicit feature/label versions.

The manifest classifies the dataset `RETROSPECTIVE_RESEARCH`, records every
5m/12h/1d/1m/derivatives manifest in lineage, locks the exclusive research
cutoff and prospective boundary, declares zero holdout use, and checksums the
immutable Parquet file. MFE/MAE, barrier outcomes, and timestamps are labels or
metadata and are excluded from the feature allowlist.
