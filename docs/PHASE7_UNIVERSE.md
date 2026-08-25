# Phase 7 Historical Registry, Core Universe, and Cold-Start Expansion

## Status and boundary

The local Phase 7 implementation is complete; the real cloud registry and
universes have not been built. This document defines two separately reported
research views. It does not name the eventual symbols before the official
historical data-quality stage runs on the VM.

Phase 7 uses Binance USD-M USDT-margined perpetual contracts only. It uses
public market data, requires no API key, and excludes account, position,
leverage, and order endpoints. Binance Spot remains outside this universe.

## Authoritative discovery

The registry is the union of:

- current `/fapi/v1/exchangeInfo` instrument metadata; and
- historical symbols proven by official Binance public archive object keys.

The implementation was reverified on 2026-08-22 against the official
[USD-M market-data catalog](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)
and the official
[public-data archive description](https://github.com/binance/binance-public-data/blob/master/README.md).
Archive ZIPs are accepted only after the official `.CHECKSUM` sidecar verifies.

Current exchange information alone is not a historical universe. A delisted
contract remains in the registry when archive evidence establishes its prior
existence. Registry records include symbol, base/quote asset, contract type,
onboard date when known, first/last verified market-data time, point-in-time
availability bounds, current status, supported intervals, per-family coverage,
source references, and a content identity hash.

`onboard_date` is exchange metadata only and never creates data availability.
`available_from` never precedes the first official market-data evidence.
`first_market_data_time` and `last_market_data_time` describe the evidence
bounds, while `available_until` is the exclusive lifecycle/data boundary.
Archive-catalog-only bounds are labeled `OFFICIAL_ARCHIVE_PERIOD_EVIDENCE`;
they are not presented as invented exact listing timestamps. Actual feature
rows still require verified canonical candles.

## Point-in-time existence

A symbol exists at time `t` only when:

```text
available_from <= t < available_until
```

For the research registry, every availability range is capped at the exclusive
research cutoff even when `current_status` is `TRADING`. For an inactive
historical contract, the earlier exclusive end is derived from official
historical evidence. No future status, future liquidity, future coverage, or
August holdout row may make a contract eligible in an earlier fold.

## Core benchmark: `core_universe_v1`

The stable apples-to-apples benchmark uses:

- selection cutoff: `2022-01-01T00:00:00Z`;
- core target size: 20 symbols;
- mandatory anchors: `BTCUSDT` and `ETHUSDT`;
- minimum point-in-time history: 365 days;
- trailing discovery window: 90 days;
- minimum coverage: 99.5%, with a warning below 99.9%; and
- direct market-data descriptors, never invented market capitalization.

After quality and maturity gates, eligible symbols are stratified by trailing
quote-volume liquidity, realized volatility, and history length. A
deterministic round-robin across the three-dimensional buckets selects a
behaviorally varied core while preserving BTC and ETH. Ties use coverage,
history, and symbol name. The complete inclusion/exclusion decisions and the
registry identity are frozen into `core_universe.json`.

The cutoff is not arbitrary: it is validated against the configured calendar
and must equal Fold 1's exclusive TRAIN end / Validation start. Selection
descriptors stamped at the cutoff summarize only market rows with
`timestamp < 2022-01-01T00:00:00Z`. Every descriptor persists
`source_max_time` and validation requires `source_max_time < as_of`.

This core membership is never backfilled with a contract first evidenced
after the cutoff. Its purpose is stable multi-year architecture comparison,
not coverage of every asset that exists later.

## Causal expansion: `expansion_universe_v1`

The expansion universe freezes a selection policy, not a 2026-informed symbol
list. At each fold, it uses `fold.train_end` as the as-of boundary and accepts
only descriptors whose `source_max_time < fold.train_end`. A non-core symbol is
considered only after its first official market-data evidence is itself in the
past. It must then pass:

- 365 days of point-in-time history;
- 99.5% trailing discovery coverage and integrity checks;
- required 5m, 12h, and 1d archive evidence;
- the configured trailing-liquidity floor; and
- active historical availability at the fold cutoff.

Candidates are ranked only by causal quality, trailing liquidity, and history.
Returns, Sharpe, profitability, model accuracy, TEST performance, later
survival, and later liquidity are forbidden selection inputs. A symbol that
later delists remains eligible in earlier folds where it genuinely existed.

The checked-in caps preserve the intended experiment size:

```text
core_target_size = 20
expansion_max_symbols_per_fold = 10
total_max_symbols_per_fold = 30
```

The discovery stage may inspect bounded daily official evidence to apply this
policy. Discovery candidates are not model membership. Full-resolution data
acquisition is restricted to symbols causally admitted in at least one fold.

## Two research views

Every fold produces separately labeled evaluations:

- `CORE`: eligible members of `core_universe_v1` only; and
- `EXPANDING`: eligible core members plus causally admitted newer symbols.

They are never pooled into an unlabeled result. The expanding view tests
cold-start/new-asset generalization while the core view preserves the stable
historical comparison.

## Fold-local active universe

The frozen core is not unconditional coverage. At every walk-forward fold,
core and expansion eligibility are recomputed at `train_end` from descriptors
sourced strictly before that timestamp. A symbol may be excluded for:

- not yet listed or already unavailable;
- insufficient history;
- insufficient trailing liquidity;
- inadequate coverage; or
- duplicates or invalid data.

Clusters and liquidity tiers are then fitted from TRAIN-known eligible data
only and frozen before Validation, Cal-A, Cal-B, and TEST. Cluster membership
may legitimately change between folds.

For the expanding view:

```text
fold_active_symbols =
    eligible core symbols
    UNION
    causally eligible, cap-selected expansion symbols
```

The acquisition layer may contain the bounded union of symbols needed by later
folds, but that union is not a model universe. After the membership above is
frozen, Phase 7.1 rebinds every cross-sectional percentile and market-context
field to the current fold's rows. The acquisition-union preview is explicitly
tagged and cannot be mistaken for model-facing context.

Each manifest persists fold ID, symbol, `CORE`/`EXPANSION` source,
`available_from`, history days and age bucket as of TRAIN end, causal
liquidity, quality status, eligibility, reason, and a membership hash. Symbols
not yet evidenced are absent rather than recorded as known future exclusions.
No rows are created before first availability or after a verified exclusive
`available_until`.

Age reporting uses TRAIN-end age from `available_from`, never future age:

```text
365–729 days
730–1459 days
1460+ days
```

## Data-quality policy

Quality is evaluated per symbol and interval. Missing candles are reported and
never filled. A failed symbol does not silently disappear: the fold/universe
manifest records its explicit ineligibility reason. Duplicate `(symbol,
feature_time)` keys are fatal.

The local tests cover delayed admission, minimum history, no retroactive
membership, future survival/liquidity perturbations, fold-bound breadth and cluster
causality, per-coin maturity, hybrid fallback, unknown-symbol global scoring,
fold caps, delisted-symbol retention, and point-in-time existence.

The research cutoff remains exclusive `2026-07-01T00:00:00Z`; July 2026 is
unused. The prospective holdout begins `2026-08-01T00:00:00Z` and remains
`LOCKED_UNUSED`, unused, and unauthorized for evaluation or expansion
selection.
