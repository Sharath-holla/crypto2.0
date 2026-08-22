# Historical Data and Quality Runbook

## Install and verify

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check src tests
```

## Download

The checked-in configuration defaults to the primary Binance USD-M futures dataset:

```powershell
uv run crypto-ai download --config configs/data/binance.toml --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z
```

Expected output is one JSON line containing an absolute manifest path, status, and row count. Structured operational logs are written to stderr. A fully populated one-hour `5m` range normally has 12 rows.

For primary USD-M 1-minute data:

```powershell
uv run crypto-ai download --config configs/data/binance.toml --interval 1m --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z
```

For the secondary Spot dataset, select the market explicitly:

```powershell
uv run crypto-ai download --config configs/data/binance.toml --market spot --start 2026-08-01T00:00:00Z --end 2026-08-01T01:00:00Z
```

## Validate and inspect

Read the manifest's `file_locations`, prefix the value with `data/bronze/binance/`, then run:

```powershell
uv run crypto-ai validate <parquet-path> --interval 5m
uv run crypto-ai inspect <parquet-path> --limit 5
```

Validation exits `0` for a passing file and `2` when quality errors exist. Gaps are listed but never filled.

## Resume behavior

Run the identical download command again. The deterministic manifest is reopened, checksums and row counts are verified, and completed/empty partitions are skipped. A missing file is downloaded again. A checksum or embedded metadata mismatch stops the run.

## Failure recovery

- HTTP 429/418: the client honors `Retry-After`; do not add parallel request bursts.
- HTTP 5xx or transport timeout: bounded exponential retries are automatic for GET requests.
- `failed` manifest: inspect `last_error`, fix the cause, and rerun the same command.
- checksum mismatch or unexpected existing-file metadata: do not delete/replace automatically. Quarantine the exact file after manual review, then rerun.
- `completed_with_quality_errors`: inspect each partition's `quality` object. Preserve the bronze file; do not synthesize missing candles.

No command in this runbook starts legacy signal or trading processes.

## Generate a dataset quality report

Validation reads existing Bronze only and does not contact Binance:

```powershell
uv run crypto-ai quality-report `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml `
  --output-root data/quality
```

Exit `0` means PASS or policy-accepted WARN. Exit `2` means FAIL. The command prints a human summary and the deterministic JSON report path.

To validate one existing partition independently:

```powershell
uv run crypto-ai quality-report `
  --path <bronze-or-silver-parquet-path> `
  --market usdm `
  --source binance_usdm_futures_rest `
  --symbol BTCUSDT `
  --interval 5m
```

## Promote to Silver

```powershell
uv run crypto-ai promote-silver `
  --manifest data/bronze/binance/manifests/usdm-btcusdt-5m-32e89aae75adbdc5.json `
  --quality-config configs/data_quality/default.toml `
  --quality-root data/quality `
  --silver-root data/silver/binance `
  --quarantine-root data/quarantine
```

PASS promotes. WARN promotes only when `allow_warnings_for_silver = true`. FAIL writes a small quarantine JSON reference and creates no Silver Parquet. Repeating unchanged promotion verifies and reuses the deterministic Silver files and manifest.

Inspect promoted output with the existing command:

```powershell
uv run crypto-ai inspect <silver-parquet-path> --limit 5
```

## Quality failure recovery

- Checksum, schema, metadata, conflicting duplicate, impossible OHLC, or volume failure: preserve Bronze and investigate the source; never edit the partition in place.
- `UNKNOWN_GAP`: confirm instrument lifecycle or exchange incident information from authoritative evidence before classifying it further; never fill it.
- Candidate outlier: inspect the preserved row and surrounding candles; it remains a warning unless an independent integrity rule fails.
- Existing Silver lineage mismatch: stop. Do not overwrite the file; investigate why source/report identity changed.

## Build a Gold research dataset

The configured source must be a Phase 2 Silver manifest with eligible PASS/WARN status and valid checksums:

```powershell
uv run crypto-ai build-dataset `
  --config configs/datasets/btcusdt_5m_july_2026.toml `
  --label-config configs/labels/forward_return_60m.toml `
  --feature-config configs/features/baseline_v1.toml
```

The command reports warm-up, insufficient-future, gap-invalidated, and final row counts. It never modifies Silver. An identical rerun verifies and reuses the deterministic Gold directory.

If the result says no usable rows remain, the Silver range is too short for the 50-candle feature warm-up plus the next-open/60-minute label. Acquire and validate a larger bounded range through the normal Bronze → quality gate → Silver workflow; do not fabricate rows.

## Train and evaluate research baselines

Simple baselines and Ridge only:

```powershell
uv run crypto-ai train `
  --dataset-manifest data/gold/training_sets/gold-19425b0820c974247b73fbe0/manifest.json `
  --config configs/models/baseline_v1.toml
```

Full Phase 3 comparison including LightGBM:

```powershell
uv run crypto-ai train `
  --dataset-manifest data/gold/training_sets/gold-19425b0820c974247b73fbe0/manifest.json `
  --config configs/models/lightgbm_v1.toml

uv run crypto-ai evaluate `
  --experiment local_artifacts/experiments/experiment-5f0f09b3ee131bddba69a0b1/experiment.json
```

Training checks timestamp order, split sizes, purging, finite values, constant features, feature schema, and target type. If a model artifact exists with incompatible identity, preserve it and investigate rather than overwriting it. These metrics are predictive diagnostics only; do not interpret them as net returns or deploy the legacy trader.

## Phase 4 public market data and research

Download a public derivatives dataset without an API key:

```powershell
uv run crypto-ai download-market-data --kind funding `
  --start 2026-07-01T00:00:00Z --end 2026-08-01T00:00:00Z
```

Supported kinds are `funding`, `mark_kline`, `index_kline`, `premium_kline`,
and `open_interest`. Open interest is explicitly short-history only. Successful
commands validate and write content-addressed Bronze and Silver manifests under
`data/market/`.

Build, train, and backtest the July Phase 4 experiment:

```powershell
uv run crypto-ai build-dataset-v2 `
  --config configs/datasets/btcusdt_5m_phase4_july_2026.toml

uv run crypto-ai train-v2 `
  --dataset-manifest data/gold/market_intelligence/gold-v2-f59110b7f683d2fe4342c8d6/manifest.json `
  --config configs/models/main_model_v2.toml

uv run crypto-ai backtest-v1 `
  --experiment local_artifacts/phase4/experiments/main-model-v2-7ab8dd9185dc27f90d1179b0/experiment.json `
  --config configs/backtests/foundation_v1.toml `
  --funding-manifest data/market/silver/funding/market-silver-08ea0ea50e7251782660b1f2/manifest.json
```

The backtest rejects training predictions, enters at the next available 5m
open, holds at most one normalized position for 60 minutes, applies both-side
fees, spread, slippage, and actual funding events, and permits no leverage.
Zero trades is valid when predicted edge is below assumed cost. Never run the
legacy trader commands.

## Run the locked Phase 6 research build

Phase 6 inputs must already be validated Silver/public-market artifacts. The
checked-in configuration enforces the exclusive July 1 cutoff and August 1
prospective boundary:

```powershell
uv run crypto-ai phase6-research --config configs/phase6/research_v1.toml
```

The command verifies input checksums, reconciles direct 12h/1d candles against
exact derived candles, applies completed-candle joins, builds immutable
research Gold, and runs fixed chronological probes. Identical output identity
is verified rather than overwritten. It performs no account access, model
promotion, backtest optimization, or order submission.

## Phase 7 safe local checks

```powershell
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --validate-config
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --plan
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --test-universe
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --dry-run
```

These commands use no account credentials. Plan, validation, and fixture modes
make no network request; dry-run writes no files. Running without one of those
safe flags enters the heavy pipeline and is rejected unless
`PHASE7_ALLOW_CLOUD_RESEARCH=1` is explicitly set on the training VM.

Safe output must report `prospective_holdout_status=LOCKED_UNUSED`,
`prospective_holdout_used=false`, and
`prospective_holdout_evaluation_authorized=false`. The cloud run may not
evaluate the holdout.

Do not set that guard on the laptop. For VM start/SSH, restore, tmux,
stage/resume, verification, Cloud Storage backup, and mandatory shutdown
commands, follow `PHASE7_CLOUD_RUNBOOK.md`.

## Training-disabled context collection

Inspect and plan locally without network access:

```powershell
uv run crypto-ai context status
uv run crypto-ai context fear-greed --plan
uv run crypto-ai context oi --plan --symbol BTCUSDT
```

One-shot real collection requires a separate guard and uses only unauthenticated
public endpoints:

```powershell
$env:CRYPTO_AI_ALLOW_CONTEXT_NETWORK = "1"
uv run crypto-ai context fear-greed fetch
uv run crypto-ai context oi recent --symbol BTCUSDT
uv run crypto-ai context oi snapshot --symbol BTCUSDT
Remove-Item Env:CRYPTO_AI_ALLOW_CONTEXT_NETWORK
```

Fear & Greed history remains training-ineligible until its historical
publication time is proven. OI is recent/forward-only and is never extended
into fake multi-year history. Neither dataset enters the current Phase 7
baseline. Do not set `PHASE7_ALLOW_CLOUD_RESEARCH=1`, start training, or create
a scheduler for these operations. See `CONTEXT_DATA_FOUNDATION.md` for schemas,
storage, and existing-bucket backup/restore commands.
