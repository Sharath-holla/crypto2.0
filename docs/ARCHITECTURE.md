# Architecture

## Status and phase boundary

Phases 1 through 5 and Phase 5 Hardening are complete at their research gates.
This document records the accepted long-term architecture. Phase 5.1 does not
authorize account access, leverage logic, order submission, or live trading.

## Canonical venue decision

Binance is the sole canonical market-data and eventual execution venue.

- Primary research market: Binance USD-M `BTCUSDT` perpetual futures (`market=usdm`, source `binance_usdm_futures_rest`).
- Secondary context market: Binance Spot (`market=spot`, source `binance_spot_rest`).
- Eventual execution market: Binance USD-M futures, only after the required research, backtest, walk-forward, paper, shadow, and test-environment gates.
- Superseded design: Binance market data with CoinSwitch execution.

Spot and USD-M remain separate source domains. The Binance-only decision removes cross-exchange research/execution mismatch; it does not permit raw Spot and futures records to be merged or instrument rules to be shared implicitly.

## Implemented Phase 1 through Phase 3 flow

```text
CLI/TOML configuration
        |
        v
Binance REST adapter -----> immutable instrument snapshot
        |
        v
bounded UTC pagination
        |
        v
exact Candle domain objects
        |
        v
deterministic Arrow schema
        |
        +-----> quality report (never repairs/fills)
        |
        v
atomic immutable Bronze Parquet
        |
        v
SHA-256 + resumable manifest
        |
        v
partition/file/manifest/cross-boundary validation
        |
        +---- FAIL ----> report + quarantine reference
        |
     PASS/WARN (policy)
        |
        v
immutable Silver + complete lineage
        |
        v
causal Feature V1 + gap-safe next-open Label V1
        |
        v
immutable Gold training dataset
        |
        v
chronological split + label-boundary purge
        |
        v
transparent baselines / Ridge / LightGBM
        |
        v
OOS predictions + predictive metrics + artifacts
```

No implemented Phase 1–3 component connects to an account or submits an order.

## Canonical long-term target

```text
                         BINANCE
                            |
              +-------------+-------------+
              |                           |
       HISTORICAL DATA                LIVE STREAMS
              |                           |
              +-------------+-------------+
                            |
                     DATA INGESTION
                            |
                         BRONZE
                            |
                     DATA VALIDATION
                            |
                         SILVER
                            |
                     FEATURE ENGINE
                            |
       +--------------------+--------------------+
       |                    |                    |
 PRICE/TREND/VOLUME    DERIVATIVES/FLOW     MARKET STATE
       |                    |                    |
       +--------------------+--------------------+
                            |
                   MAIN MARKET MODEL
             expected return / probability /
                       uncertainty
                            |
                    NO-TRADE FILTER
                            |
                  SPECIALIZED / META
                            |
                       RISK ENGINE
                            |
                    PORTFOLIO ENGINE
                            |
               POSITION SIZE + LEVERAGE
                            |
                  PRE-TRADE VALIDATION
                            |
                    BINANCE FUTURES
                            |
            ACK / FILL / POSITION / PNL
                            |
              RECONCILIATION + MONITORING
```

This is a target sequence, not implemented functionality. Live deployment must progress through research, backtest, walk-forward, paper simulation, shadow mode, Binance test environment where supported, tiny capital, and gradual scale.

## Main Market Model

ADR-018 establishes one primary tabular model that directly consumes most structured market intelligence. The initial family remains LightGBM, later benchmarked against XGBoost and CatBoost. Specialized temporal, regime, event, and meta models may complement it later, but the main model must not depend only on their outputs.

Planned input families are:

- `PRICE`: returns and candle structure.
- `TREND`: compact EMA, slope, persistence, and trend-strength measures.
- `MOMENTUM`: RSI, rate of change, and acceleration candidates.
- `VOLATILITY`: realized volatility, range, ATR-normalized, percentile, and volatility-of-volatility candidates.
- `VOLUME`: base/quote volume, relative volume, trade count, and changes.
- `BUY_PRESSURE` and `SELL_PRESSURE`: verified Binance taker-volume semantics with zero-volume safety.
- `ORDER_FLOW`: documented imbalance and intensity features when reliable history exists.
- `DERIVATIVES`: funding, open interest, mark/index/basis, and other verified Binance futures context.
- `REGIME`: causal, chronologically fitted regime state/probabilities.
- `CROSS_ASSET`: BTC/ETH context, rolling correlation, and beta after those assets are ingested.
- `MARKET_BREADTH`: only after a valid multi-asset universe exists.
- `TIME`: explicitly defined calendar/funding-cycle context.

Every feature requires a definition, timestamp semantics, rationale, lookback, missingness policy, version, lineage, and leakage test. Phase 3 `baseline_v1` is immutable; future expanded features use a new version such as `market_v2`. Feature groups must be individually ablatable.

## Conceptual separation

The system must keep these categories distinct:

| Category | Examples |
|---|---|
| Features | price, trend, volume, taker pressure, funding, OI, regime |
| Labels | future return, later trade/TP/SL outcomes |
| Model outputs | expected return, probabilities, uncertainty |
| Actions | long, short, hold, exit, no-trade |
| Risk parameters | size, leverage, stop distance, exposure |
| Transaction costs | fees, spread, slippage, funding payments |

Funding can have two roles without mixing timestamps: known funding at feature time may be predictive; funding charged or credited while a simulated position is held belongs to PnL. Trading fees are costs, not ordinary prediction features.

## Generic domain and adapter boundary

Internal objects must remain exchange-independent, including `MarketCandle`, `FundingRate`, `OpenInterest`, `Instrument`, `Prediction`, `Signal`, `OrderRequest`, `Order`, `Fill`, `Position`, and `AccountState`. Binance historical, streaming, account, and execution adapters translate external payloads at the boundary. Raw Binance JSON must not propagate into business logic.

The preserved legacy CoinSwitch modules do not satisfy this boundary. Their exchange-independent concepts may be extracted only after tests establish intended behavior; their endpoints, signing, identifiers, environment variables, and adapter assumptions must not be reused.

## Implemented Phase 4 research boundary

Phase 4 adds `crypto_ai.phase4`: public derivatives datasets, causal as-of
alignment, Feature V2/Regime V1, Gold V2, Main Model V2 ablations, and the OOS
backtest foundation. It extends immutable storage under `data/market/` and
records every candle/derivatives input, checksum, availability rule, feature
version, label version, and code version in Gold V2 lineage.

The official source inventory and historical-availability decisions are in
`docs/BINANCE_MARKET_DATA_RESEARCH.md`. The implementation remains public-only:
there are no credentials, account reads, positions, order submissions, margin
or leverage changes, or live-trading facilities. Phase 5 extends only this
offline research boundary.

## Current module boundaries

- `crypto_ai.domain`: exchange-independent candle objects and interval semantics.
- `crypto_ai.data.binance`: official Spot/USD-M response conversion; no storage or account behavior.
- `crypto_ai.data.schema`: versioned canonical Arrow schema.
- `crypto_ai.data.validation`: deterministic side-effect-free checks.
- `crypto_ai.data.quality`: typed results, policies, reports, gates, quarantine references, and Silver promotion.
- `crypto_ai.data.storage`: immutable Parquet and checksum primitives.
- `crypto_ai.data.ingestion`: UTC partition orchestration, resume behavior, exchange-info snapshots, and manifests.
- `crypto_ai.features`: reusable causal Phase 3 features.
- `crypto_ai.labels`: explicit feature/entry/target timing and gap-safe labels.
- `crypto_ai.research`: Gold construction, purged temporal splits, models, metrics, serialization, and artifacts.
- `crypto_ai.phase5`: calendar rolling folds, boundary purge/embargo,
  calibration, threshold policy, execution-aware test evaluation, aggregation,
  qualification, and prospective-holdout enforcement.
- `crypto_ai.contracts`: side-effect-free semantic versioning, event envelopes,
  model/prediction/deployment metadata, future execution and portfolio ports,
  observability/failure interfaces, dashboard read models, and the approved
  Phase 7 scientific freeze. It contains no exchange, account, cloud, training,
  or runtime activation implementation.
- `crypto_ai.cli`: data, validation, dataset, training, and evaluation commands.

Legacy root and `pipeline/` execution modules are outside `src/`, unpackaged, untested, and deprecated.

## Storage and future lineage

Implemented storage remains:

```text
data/bronze/binance/
    instruments/market=<spot|usdm>/...
    klines/market=<spot|usdm>/symbol=.../interval=.../date=.../
    manifests/
data/quality/
data/quarantine/
data/silver/binance/klines/...
data/gold/training_sets/gold-<content-hash>/...
local_artifacts/experiments/experiment-<identity-hash>/...
local_artifacts/phase5/walkforward/wf-<identity-hash>/...
```

When separately authorized, derivatives datasets may extend the same immutable/versioned pattern with distinct dataset types such as funding, mark price, index price, open interest, and aggregate trades. Enhanced Gold lineage must identify every Bronze/Silver market and derivatives input, its availability interval, feature version, label version, and code version. Missing history is never fabricated.

## Phase 4 gate — implemented

Phase 4 implements **Binance Market Intelligence + Advanced Structured
Features + Main Model V2 + Backtest Foundation**. Its official-document research
and historical-availability report covers futures klines, funding, mark/index
prices, open interest/statistics, aggregate trades, taker semantics, long/short
ratios, liquidations, book data, and fees.

Each dataset is classified by historical fitness before feature use. Phase 4
adds no live Binance trading or real-money orders. Phase 5 was separately
authorized and adds retrospective validation only; live behavior remains gated.

## CoinSwitch retirement boundary

ADR-017 supersedes every future CoinSwitch assumption. CoinSwitch-specific code is retained temporarily only as an isolated historical prototype, classified in `COINSWITCH_DEPRECATION.md`, and prohibited from use. Historical documents and experiment results may retain factual references but must identify the old decision as superseded rather than rewrite history.

## Phase 4.1 multi-year research path

```text
Binance public archive (bulk) ─┐
                              ├─ exact-decimal canonical Bronze
Binance public REST (gaps) ───┘              │
                                             ▼
                                  Phase 2 quality + Silver
                                             │
                    ┌────────────────────────┴──────────────────────┐
                    ▼                                               ▼
          core long-history Gold                         derivatives-overlap Gold
          Feature V2.1: 52                               + funding + mark/index: 61
                    │                                               │
                    ▼                                               ▼
                 L0–L5                                            D0–D2
                    └────────────────────────┬──────────────────────┘
                                             ▼
                                Main Model V2.1 OOS artifacts
                                             │
                         validated 1m bars ──┤── actual funding events
                                             ▼
                            bar-based Backtest V1.1 + stresses
```

Archives and REST share a canonical schema but retain distinct transport and
checksum lineage. The composed reconciled manifest is the only layer that may
choose a current REST day over an archive day, and only with a persisted
field-level discrepancy report. External feature joins are backward-looking
as-of joins with explicit staleness. Core and derivatives ablations never mix
row populations within a comparison family. Phase 4.1 ends at public-data
research artifacts; private APIs and live execution remain absent.

## Phase 5 retrospective validation boundary

Phase 5 consumes the immutable core and derivatives-overlap Gold V2.1 datasets
without changing Label V1, Feature V2.1, or the fixed LightGBM configuration.
It runs independent rolling 24/3/3/3-month Train/Validation/Calibration/Test
folds with three-month steps. Purging uses actual `label_end_time`; a separate
60-minute timestamp embargo is recorded at each later-segment boundary.

Model fitting, validation-only early stopping, calibration, policy selection,
and test evaluation are distinct APIs. The test vault is released only after a
model/calibrator/policy identity is frozen. All timestamps at or beyond
`2026-08-01T00:00:00Z` remain the untouched prospective holdout. See
`WALK_FORWARD.md` for exact artifact and qualification rules.

## Phase 5.1 hardening boundary

Phase 5.1 is versioned post-processing, not a new model phase. Historical
Phase 5 folds, models, TEST predictions, and summaries remain immutable under
`local_artifacts/phase5/`. The hardened runner references those model hashes,
predicts chronological Cal-A/Cal-B segments from the same Gold rows, reuses
saved TEST raw predictions, and writes new `walkforward_v1_1` artifacts under
`local_artifacts/phase5_hardening/`.

Cal-A owns calibrator fit/method selection; purged and embargoed Cal-B owns the
edge threshold; TEST owns evaluation only. Fixed-policy cost stress freezes
trade identity and is the primary qualification input. Adaptive-policy stress
is a separately labeled secondary diagnostic. Qualification and scientific
evidence statuses are distinct. The prospective holdout remains locked at
`2026-08-01T00:00:00Z`.

The canonical long-term ownership, multi-asset heterogeneity, expected-return
distribution, MFE/MAE, dynamic TP/SL, fear/euphoria, liquidity, risk, sizing,
leverage, portfolio, trade-management, and Binance execution contracts are
locked in `FUTURE_TRADING_SYSTEM.md`. They are documentation only; Phase 5.1
implements none of those future modules.

## Phase 6 retrospective research boundary

Phase 6 adds `crypto_ai.phase6` without changing Phase 5/5.1. Direct Binance
USD-M 12h and daily candles reuse Bronze, quality, and Silver infrastructure;
exact 5-minute aggregates are reconciliation evidence only. Completed-candle
as-of joins feed an isolated `market_v3_research` feature family. A separate
`label_v2_research` family owns multi-horizon returns, MFE/MAE, and diagnostic
barrier outcomes.

The resulting Gold and fixed Ridge/LightGBM probes are classified
`RETROSPECTIVE_RESEARCH`. They cannot promote a champion or call private APIs.
The cutoff is `2026-07-01T00:00:00Z`, all July is unused by Phase 6, and the
permanent `2026-08-01T00:00:00Z` holdout remains unopened. Final TP/SL, fear,
risk, leverage, portfolio, and execution systems remain outside this boundary.

## Phase 7 multi-asset research boundary

`crypto_ai.phase7` is an isolated, public-data, retrospective research package.
Its source flow is:

```text
official current metadata + official historical archive catalog
    -> immutable historical symbol registry
    -> point-in-time quality/liquidity/history gates
    -> frozen 20-symbol core benchmark + causal fold-local expansion policy
    -> separately labeled CORE and EXPANDING fold_active_symbols
    -> 5m/12h/1d/funding/mark/index Silver families
    -> bounded yearly multi-asset Gold partitions
    -> rolling G0/C0/P0/H0 experiments
    -> native/matched coverage, macro/micro/cold-start/economic scorecards
```

The local and cloud modes call the same package. Local mode exposes plan,
configuration, universe-fixture, and in-memory dry-run operations. Heavy stages
require an explicit VM-only environment guard. The pipeline uses atomic
artifacts and checksum-verified stage plus fold/experiment checkpoints.

Gold is partitioned by symbol/year and built in bounded time chunks. Cross-
asset market context is computed only from point-in-time active members.
Clusters and liquidity tiers are TRAIN-only; Cal-A owns calibration, Cal-B owns
threshold selection, and TEST is released only after a frozen identity exists.

The exclusive research cutoff remains `2026-07-01T00:00:00Z`, so July remains
unused, and the permanent August holdout is `LOCKED_UNUSED`, has zero rows, and
is not authorized for Phase 7 evaluation. Local implementation is complete;
the real cloud research result is pending. See the four `PHASE7_*`
documents. No Phase 7 component accesses an account or implements allocation,
risk, leverage, orders, or live trading.

## Training-disabled context-data boundary

`crypto_ai.context` is an additive public-data package beside, not inside,
`crypto_ai.phase7`. Its provider-neutral flow is:

```text
explicit guarded public GET
    -> content-addressed immutable raw JSON
    -> provider-specific exact normalization
    -> point-in-time eligibility and quality checks
    -> versioned Parquet + checksum manifest
    -> optional research-only feature builder
```

Alternative.me Fear & Greed history is global context and remains
`NOT_TRAINING_ELIGIBLE` because its historical publication/knowledge time is
not established by the provider documentation. Binance USD-M current and
recent OI observations use ingestion as their defensible availability time and
remain `FORWARD_ONLY`; the official recent-statistics retention is only the
latest one month. Neither source is loaded by the Phase 7 baseline.

The separate `CRYPTO_AI_ALLOW_CONTEXT_NETWORK=1` guard unlocks only explicit
one-shot public context collection. It does not unlock the Phase 7 cloud
pipeline, create a service, or authorize credentials, account access, trading,
or holdout evaluation. See `CONTEXT_DATA_FOUNDATION.md`.

## Phase 7.1B contract and baseline-freeze boundary

Phase 7.1B adds interfaces around Phase 7 without importing them into the
scientific path. `phase7_scientific_baseline_v1_2` byte-freezes every Phase 7
source file after the authorized onboard-boundary and exact interval-archive
boundary correctness amendments, including the archive reader used to resolve
those bounds, together with the approved research config. Typed assertions
freeze the safe validation, plan, dry-run and causal-universe outputs. A mismatch is a
`PHASE7_1B_CORRECTNESS_BLOCKER` and cannot be repaired by silently refreshing
hashes.

Future model serving, event storage, execution, portfolio, observability and
dashboard components must implement the protocols in `crypto_ai.contracts` or
introduce an explicitly reviewed new major contract. The only concrete adapter
is disabled and side-effect-free. No private Binance access, order capability,
cloud action, portfolio automation, or automatic leverage exists in this
foundation. See `PHASE7_1B_ARCHITECTURE_FOUNDATION.md`.
