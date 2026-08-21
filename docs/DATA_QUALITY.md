# Data Quality and Silver Promotion

Validator version: `1.0.0`  
Report schema version: `1.0.0`

## Architecture

The Phase 2 quality engine validates existing immutable Bronze Parquet and its Phase 1 manifest. It does not download data, contact an exchange, or mutate Bronze.

```text
Bronze manifest + Parquet
        |
        v
file and manifest integrity
        |
        v
partition validation (one file at a time)
        |
        v
adjacent-boundary continuity
        |
        v
versioned JSON report
        |
        +---- FAIL ----> quarantine reference; no Silver
        |
     PASS/WARN according to policy
        |
        v
sorted canonical Silver + lineage manifest
```

Quality reports use deterministic IDs derived from source checksums, validator version, report schema version, and the validated policy. Rerunning unchanged validation replaces the same report path rather than creating duplicates.

## Result model

Every check records `check_name`, `status`, `severity`, symbol, interval, partition, message, observed and expected values, affected-row count, bounded samples, and timestamp.

| Status | Meaning |
| --- | --- |
| `PASS` | No disqualifying or suspicious condition was found. |
| `WARN` | Data remains unchanged and may be promoted only if policy permits warnings. |
| `FAIL` | The dataset is ineligible for Silver and receives a quarantine reference. |

| Severity | Intended use |
| --- | --- |
| `INFO` | Passing or informational check. |
| `WARNING` | Suspicious condition requiring visibility, such as a statistical candidate outlier. |
| `ERROR` | Research-corrupting condition. |
| `CRITICAL` | Identity, schema, checksum, conflict, or impossible-price failure. |

The deterministic gate returns `FAIL` if any check fails, otherwise `WARN` if any check warns, otherwise `PASS`.

## Implemented checks

- Canonical schema: required columns, order, Arrow types, nullability, unexpected drift, and null required values.
- Timestamps: UTC schema, strict chronological order, open before close, configured close boundary, reusable fixed-interval duration, and UTC alignment.
- Duplicates: duplicate identity, field-identical duplicates, conflicting duplicates, and cross-partition duplicates. Conflicts receive `CRITICAL` severity.
- Gaps: expected/observed counts, missing count and percentage, first/sample missing timestamps, largest consecutive gap, and cross-partition gaps.
- Gap classification: unknown causes are recorded as `UNKNOWN_GAP`; maintenance, listing, and delisting causes are never fabricated.
- OHLC: positive prices and every high/low/open/close relationship.
- Volume and trades: non-negative base/quote/taker volumes and trade counts, taker volume not exceeding total volume, and positive volume with zero trades.
- Zero volume: count, percentage, runs, timestamps, and configurable warning/failure thresholds.
- Outliers: trailing fractional returns with rolling median and median absolute deviation (MAD). Candidates are warnings and are never deleted.
- Staleness: configurable repeated flat-candle runs.
- Identity: homogeneous expected symbol and source.
- Ingestion time: ingestion after represented market close and not implausibly later than validator time.
- Partition bounds: all opens belong to the declared half-open partition range.
- File integrity: existence, readability, canonical schema, non-empty completed files, and embedded metadata.
- Manifest integrity: file list, per-file and total row counts, requested timestamp range, SHA-256, and partition identity.
- Cross-partition integrity: chronological records, declared overlaps, actual overlaps, duplicates/conflicts, and missing boundary candles.

Checks operate on one daily Parquet table at a time. Cross-partition validation retains only compact first/last-row summaries, so memory does not scale with the complete multi-year universe.

## Default policy

The typed policy is stored in `configs/data_quality/default.toml`.

- Missing percentage: `0` allowed.
- Consecutive missing intervals: `0` allowed.
- Exact duplicate count: `0` allowed.
- Zero-volume presence: warning; more than `5%` fails.
- Outlier window: 21 returns; minimum history 7; MAD threshold 12.
- Repeated flat candles: warning at 3, fail at 12.
- Ingestion future tolerance: 300 seconds.
- Silver promotion: `PASS` and `WARN` allowed; any `FAIL` rejected.

Changing policy changes the deterministic report ID and therefore the Silver dataset version.

## Bronze-to-Silver rules

| Problem | Detected | Bronze modified? | Silver behavior |
| --- | --- | ---: | --- |
| Exact duplicate | Yes | No | Reported; only promotable if policy allows, then exact row is deduplicated. |
| Conflicting duplicate | Yes | No | `CRITICAL` failure; reject and quarantine by reference. |
| Missing candle | Yes | No | Never filled; default gate rejects. |
| Non-positive price | Yes | No | Reject. |
| Impossible OHLC | Yes | No | Reject; never rearrange values. |
| Negative/inconsistent volume | Yes | No | Reject. |
| Statistical outlier | Yes | No | Preserve row and warn. |
| Zero volume | Yes | No | Preserve and warn/fail according to policy. |
| Stale flat run | Yes | No | Preserve and warn/fail according to policy. |

Silver retains the canonical Candle schema and exact Decimal/UTC values. The only implemented transformations are chronological sorting and policy-authorized field-identical deduplication. No indicators, features, labels, interpolation, or market-value repairs are permitted.

Each Silver file embeds source file/checksum, source manifest and dataset version, quality report ID, validator version, Silver dataset version, and exact-duplicate removal count. The Silver manifest records the same lineage for the complete promoted dataset.

## Quarantine

Rejected datasets create a small deterministic JSON reference under `data/quarantine/`. It contains source paths/checksums, source manifest and dataset version, validation report/version, and failed checks. Bronze is referenced, not copied or moved.

## CLI

Validate a complete Phase 1 manifest and persist JSON:

```powershell
uv run crypto-ai quality-report `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml `
  --output-root data/quality
```

Validate one existing file without downloading:

```powershell
uv run crypto-ai quality-report `
  --path <parquet-path> `
  --market usdm `
  --source binance_usdm_futures_rest `
  --symbol BTCUSDT `
  --interval 5m
```

Promote only if the gate permits:

```powershell
uv run crypto-ai promote-silver `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml `
  --quality-root data/quality `
  --silver-root data/silver/binance `
  --quarantine-root data/quarantine
```

Run the bounded synthetic performance smoke:

```powershell
uv run python scripts/quality_performance_smoke.py --rows 1440
uv run python scripts/quality_performance_smoke.py --rows 1440 --tracemalloc
```

## Interval-scaled 1-minute flat-run policy

For validated 1-minute execution-support candles,
`configs/data_quality/execution_1m.toml` preserves the default policy's time
scale: warn after 15 minutes and fail after 60 minutes. Applying the default
12-bar failure threshold directly would mean only 12 minutes at 1m versus 60
minutes at 5m. The real 2025-08-29 19-bar flat run was identical in every
canonical field between the official archive and current REST, so it is
retained as a warning with both source checksums and an equivalence report.
