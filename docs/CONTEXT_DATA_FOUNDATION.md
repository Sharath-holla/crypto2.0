# Context Data Foundation

## Status and boundary

`crypto_ai.context` is a small provider-neutral foundation for public external
context data. It is additive to Phase 7; it does not change
`multiasset_features_v1`, `market_context_v1`, `multiasset_targets_v1`, the
G0/C0/P0/H0 architecture matrix, walk-forward folds, universe membership,
costs, thresholds, or model inputs.

The Phase 7 cloud baseline remains **MARKET DATA ONLY**. Both implemented
context feature families are training-disabled in `configs/context/default.toml`:

- `fear_greed_context_v1`: implemented, not active in model training; and
- `open_interest_context_v1`: implemented for future/controlled research,
  not active in model training.

Context observations collected after the exclusive
`2026-07-01T00:00:00Z` research cutoff are allowed as forward observations,
but are not eligible for the current Phase 7 experiment. July 2026 remains
unused. The prospective holdout beginning `2026-08-01T00:00:00Z` remains
locked and unused.

## Provider-neutral records

The package exposes public-GET provider capabilities and explicit training
eligibility rather than using nulls as an eligibility signal:

- `HISTORICAL_RESEARCH_CANDIDATE`;
- `FORWARD_ONLY`;
- `NOT_TRAINING_ELIGIBLE`; and
- `DISABLED`.

Normalized records preserve provider, source endpoint, provider timestamp,
availability timestamp where defensible, ingestion timestamp, symbol/scope,
raw identifier, canonical raw-payload checksum, schema/source versions,
the explicit `HISTORICAL_RESEARCH_DATA` or `FORWARD_OBSERVATION_DATA` class,
eligibility, and the reason/policy behind eligibility. Manifests additionally
record actual/requested coverage, duplicate and gap diagnostics, data/raw
checksums, Git SHA, context-config hash, and prior dataset lineage.

Raw JSON is content-addressed and immutable. Normalized Parquet datasets and
manifests are versioned. A retry with no new identity keys reuses the validated
version. Conflicting values for an existing provider key are rejected rather
than overwritten.

## Alternative.me Fear & Greed

Official documentation was checked on 2026-08-22:

- API root: `https://api.alternative.me`;
- public endpoint: `GET /fng/`;
- `limit=0` requests all available history; and
- no API key is documented for this endpoint.

The index is stored once as `scope=GLOBAL`; it is not fabricated into separate
BTC, ETH, or altcoin sentiment observations. The documented historical
`timestamp` is preserved as `provider_timestamp`.

Alternative.me does not document enough evidence to establish that historical
`timestamp` equals the historical publication/knowledge time. Therefore
historical `availability_time` is null, the policy is
`HISTORICAL_PUBLICATION_TIME_UNVERIFIED`, and every ingested historical row is
`NOT_TRAINING_ELIGIBLE`. Raw historical collection remains useful without
making a false point-in-time claim.

The optional feature builder uses a strict
`availability_time <= feature_time` as-of rule and never performs future
backfill, centered windows, interpolation, or indefinite forward fill. It
provides value, 1/3/7-day changes, 7/30-day means, 30-day standard deviation
and z-score, age, missingness, and classification flags. Missing is not
neutral and is never converted to 50.

## Binance USD-M open interest

Official Binance USD-M Futures documentation was checked on 2026-08-22:

- current snapshot: public `GET /fapi/v1/openInterest`;
- recent statistics: public `GET /futures/data/openInterestHist`;
- supported statistics periods include `5m`;
- the statistics timestamp is the period end; and
- only the latest one month is available from the statistics endpoint.

No Binance account, API key, secret, signature, position, leverage, or order
operation is used. Current and historical/statistical responses have distinct
schemas:

- current snapshots store `symbol`, exact-decimal `open_interest`, provider
  transaction time, and ingestion/availability metadata; and
- recent history stores `symbol`, `period`, exact-decimal
  `sum_open_interest`, exact-decimal `sum_open_interest_value`, provider period
  end, and ingestion/availability metadata.

For both modes, the earliest defensible local knowledge time is ingestion, so
`availability_time=ingested_at`. Records are `FORWARD_ONLY` and
`training_eligible=false`. The collector refuses requests beyond its configured
recent-retention window, records actual returned coverage, reports gaps, and
never fabricates, interpolates, or backfills multi-year OI.

The optional OI feature builder prepares causal change, percent-change,
value-change, age, and z-score fields. `FORWARD_ONLY` rows are ignored unless a
future experiment explicitly opts in. These fields are absent from the
default Phase 7 feature matrix.

## Storage layout

```text
data/context/
  alternative_me/
    raw/
    history/normalized/
    manifests/history/
  binance_open_interest/
    raw/
    recent_history/<symbol>/<period>/normalized/
    forward_snapshots/<symbol>/normalized/
    manifests/
```

The paths are configurable through `configs/context/default.toml`. Context
data is separate from immutable Phase 1-6 data and validated Phase 7 datasets.

## Safe local commands

These commands perform no network request:

```powershell
uv run crypto-ai context status
uv run crypto-ai context fear-greed --plan
uv run crypto-ai context oi --plan --symbol BTCUSDT
```

Real collection is one-shot, non-interactive, restart-safe, and requires the
separate public-context guard. It is not a daemon or scheduler:

```powershell
$env:CRYPTO_AI_ALLOW_CONTEXT_NETWORK = "1"
uv run crypto-ai context fear-greed fetch
uv run crypto-ai context oi recent --symbol BTCUSDT
uv run crypto-ai context oi snapshot --symbol BTCUSDT
Remove-Item Env:CRYPTO_AI_ALLOW_CONTEXT_NETWORK
```

Do not set `PHASE7_ALLOW_CLOUD_RESEARCH=1` for these commands. Conversely, the
context guard does not unlock Phase 7 training.

## Cloud Storage restore and backup

Use the already-existing bucket; do not create a new bucket or hard-code a
bucket in source. On the existing VM:

```bash
export CONTEXT_CLOUD_STORAGE_ROOT="gs://<existing-bucket>/data/context"

# Restore before collecting so validated versions are reused.
gcloud storage rsync --recursive \
  "${CONTEXT_CLOUD_STORAGE_ROOT}" ./data/context

# Back up after a verified one-shot collection.
gcloud storage rsync --recursive \
  ./data/context "${CONTEXT_CLOUD_STORAGE_ROOT}"
```

Collection and backup are separate from the market-data-only Phase 7 baseline
run. Do not automatically start a VM, create paid infrastructure, or schedule
these commands in this phase.

## Deferred providers

- `cryptopanic`: disabled and not implemented; plan/coverage and news-time
  semantics require a dedicated review.
- `arkham`: disabled and not implemented; access, cost, labels, and historical
  knowledge time require a dedicated review.
- `reddit`: disabled and not implemented; no scraping, dependency, or model
  input exists.
