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

## Phase 7 registry, universe, Gold, and model artifacts

`symbol_registry_v1` is immutable JSON keyed by symbol. Each record stores
base/quote assets, contract type, current status, onboard date when known,
first/last verified market-data timestamps, point-in-time availability bounds,
history length, supported intervals, family coverage summaries, and metadata
sources. The registry freezes its research cutoff and content hash.
`onboard_date` never substitutes for data evidence. `available_from` is the
inclusive evidence boundary; `available_until` is exclusive;
`first_market_data_time`/`last_market_data_time` describe the evidence range;
and `availability_evidence` distinguishes verified timestamps from official
archive-period evidence. No missing onboard/listing timestamp is invented.

`core_universe_v1` stores the registry identity, pre-2022 selection
cutoff/method, ordered members with liquidity/volatility/history percentiles,
every point-in-time exclusion and reason, and a core hash.
`expansion_universe_v1` stores the frozen fold-TRAIN-end admission policy,
quality/history/liquidity requirements, age-bucket edges, and expansion/total
caps—not a future-informed static symbol list. `dual_universe_v2` identifies
the combined research definition.

Per-fold membership manifests store the separately labeled CORE or EXPANDING
view, eligible core and expansion symbols, total active symbols, membership
hash, and one record per known candidate with fold ID, source,
`available_from`, TRAIN-end history/age bucket and liquidity, quality status,
eligibility, and reason. They also store TRAIN-only cluster mapping,
descriptors, and liquidity tiers.

Phase 7 Gold rows use `(symbol, feature_time, horizon_minutes)` and include:

- feature/market-context/target versions and membership hash;
- ordered A0-A6 feature inputs;
- next-open `entry_time` and per-horizon `label_end_time`;
- `raw_future_return`, `ex_ante_volatility_scale`, and
  `normalized_future_return`; and
- long/short MFE/MAE evaluation labels.

The dataset is partitioned by symbol/year. Its manifest records all partition
checksums, registry/core/expansion/combined-universe hashes, source lineage,
feature groups, coverage,
bounded chunk IDs, the exclusive cutoff, and explicit false holdout/July-use
flags. It also stores `prospective_holdout_status=LOCKED_UNUSED` and
`prospective_holdout_evaluation_authorized=false`.
Partition paths are POSIX-style and relative to the manifest directory so the
same verified dataset can be restored under a different Windows or Linux root.

Model artifacts store architecture, ordered feature schema, target type,
symbol/cluster mappings, weighting mode, estimator identities, hybrid fallback
corrections, calibration, Cal-B thresholds, TEST metrics, cost stress, and a
frozen pre-TEST identity. Checkpoints checksum every required file.
Model checkpoint identity additionally binds experiment/config, research view,
registry, core universe, expansion policy, exact fold membership, Gold
manifest, feature/target versions, horizon/type, architecture, fold, and Phase
7 code version; a mismatch is not reusable.

## External context datasets

All context records carry `provider`, `source_endpoint`,
`provider_timestamp`, `availability_time`, `ingested_at`, `raw_identifier`,
`raw_payload_checksum`, `normalized_schema_version`, `source_version`,
`observation_class`, `training_eligibility`, `training_eligible`, `eligibility_reason`, and
`availability_policy`.

`alternative_me_fear_greed_v1` is global, not per-symbol. Its key is
`(scope, provider_timestamp)` and its value fields are integer `value` and
`value_classification`. Historical `availability_time` is null and
`observation_class=HISTORICAL_RESEARCH_DATA` while
`training_eligibility=NOT_TRAINING_ELIGIBLE` because documented provider time
does not prove historical publication time.

`binance_open_interest_history_v1` uses
`(symbol, period, provider_timestamp)` and stores exact-decimal
`sum_open_interest` and `sum_open_interest_value`. The timestamp is the
provider's period end. `binance_open_interest_snapshot_v1` uses
`(symbol, provider_timestamp)` and stores exact-decimal `open_interest`.
Both datasets use `availability_time=ingested_at`, are `FORWARD_ONLY`, and are
`observation_class=FORWARD_OBSERVATION_DATA`; they are excluded from current
Phase 7 training.

Context manifests are `context_manifest_v1`. They record requested and actual
coverage, rows/new rows/duplicates, bounded missing timestamps, raw and Parquet
paths/checksums, Git/config identities, eligibility, coverage limitation, and
previous dataset version. Exact retries reuse an existing validated version;
conflicting duplicate identities fail.
