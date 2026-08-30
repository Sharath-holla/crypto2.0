# Phase 7.1B future-proof architecture foundation

## Status and boundary

Phase 7.1B is an additive contract foundation around the approved Phase 7
research system. It does not change Phase 7 model inputs, feature or target
values, predictions, folds, universe membership, training/calibration/test row
ownership, economics, or model ranking. It does not start Phase 8.

The foundation is implemented under `crypto_ai.contracts`. No
`crypto_ai.phase7` module imports it. The original machine-readable baseline at
`configs/contracts/phase7_scientific_baseline_v1.json` remains immutable. The
authorized pre-cloud onboard-boundary correction is frozen by the successor
`configs/contracts/phase7_scientific_baseline_v1_1.json`. The interval-specific
archive-boundary correction is frozen separately by
`configs/contracts/phase7_scientific_baseline_v1_2.json`. Manifest-level
zero-volume quality semantics are frozen by
`configs/contracts/phase7_scientific_baseline_v1_3.json`; contract tests fail on
any further byte drift in the authoritative successor.

The only concrete execution adapter is `DisabledExecutionAdapter`. It performs
no I/O and returns `EXECUTION_DISABLED_PHASE7_1B` for submit and cancel
requests. PAPER, SHADOW, and LIVE are interface identities only. There is no
Binance account client, credential path, order writer, cloud action, or runtime
activation in this phase.

## Approved scientific baseline

The authoritative baseline is:

| Property | Frozen value |
|---|---|
| Baseline identity | `phase7_scientific_baseline_v1_3` |
| Phase 7 version | `1.3.0` |
| Configuration hash | `cc550337f1f4ee4654124bf6` |
| Feature contract | `multiasset_features_v2` |
| Market context contract | `market_context_v2` |
| Target contract | `multiasset_targets_v2` |
| Decision latency | one completed 5-minute bar |
| Architectures | G0, C0, P0, H0 |
| Folds | 16 |
| Research views | CORE, EXPANDING |
| Core universe | `core_universe_v1` |
| Expansion universe | `expansion_universe_v1` |
| Research cutoff | exclusive `2026-07-01T00:00:00Z` |
| July 2026 | UNUSED |
| Holdout start | `2026-08-01T00:00:00Z` |
| Holdout | `LOCKED_UNUSED` |
| Holdout used | `false` |
| Holdout evaluation authorized | `false` |
| Phase 7 model qualification | NONE |

Phase 7.2.1 corrected path serialization in the authoritative configuration
identity. The former `68e4b39899f8c9f0542d227b` value is retained only as
historical Windows-host metadata; it is not a portable semantic identity.

The same manifest records the reviewer-accepted canonical
`artifact_fingerprint_v1` values. The source freeze is distinct from the
historical-artifact fingerprint: the former detects scientific code/config
drift, while the latter proves preservation of existing datasets and research
artifacts.

## Package map

```text
crypto_ai.contracts
    baseline.py       approved Phase 7 invariants and safe-output assertions
    versioning.py     semantic versions, registry, compatibility, canonical hash
    events.py         immutable event envelope and event-store/projection ports
    models.py         model, prediction and deployment metadata contracts
    execution.py      adapter capabilities, order intent port, disabled adapter
    portfolio.py      portfolio snapshots, proposals, decisions and policy port
    observability.py  metrics, health, alerts and fail-closed policy port
    views.py          read-only dashboard materialized-view contract
```

These modules define boundaries. They do not instantiate services, databases,
message brokers, dashboards, model servers, exchange clients, or workers.

## Contract versioning policy

Contract identities use `name@MAJOR.MINOR.PATCH`.

- PATCH means representation-preserving corrections that do not change fields
  or semantics.
- MINOR means backward-compatible additions. New fields must be optional or
  have an unambiguous default, and old consumers must still validate.
- MAJOR means a breaking field, type, timing, ownership, or semantic change.
- A name/version pair has exactly one schema fingerprint. Re-registering the
  same definition is idempotent; a conflicting fingerprint is fatal.
- Consumers pin a major version and persist the exact producer version.
- Version compatibility is necessary but not sufficient: schema and semantic
  review remain mandatory before promotion.
- Feature, target, universe, fold, prediction, execution, event, projection and
  portfolio contracts are versioned independently. One must not inherit a new
  identity merely because another changes.

Canonical identities use deterministic sorted JSON. Decimal values remain
decimal strings, timestamps remain timezone-aware values, non-finite floats
are rejected, and mappings are key-sorted before SHA-256.

## State ownership

| State | Future authoritative owner | Non-authoritative consumers |
|---|---|---|
| Historical market data | Immutable Bronze/Silver manifests | features, research, dashboard |
| Phase 7 scientific definition | frozen config/source manifest | deployment metadata, reports |
| Model artifact and lineage | versioned model registry record | prediction provider, dashboard |
| Prediction | versioned prediction event | portfolio proposal, dashboard |
| Order intent | durable command/event store | adapter, dashboard projection |
| Venue order/fill truth | exchange plus reconciled durable event state | dashboard and reports |
| Position truth | reconciled exchange/event state | portfolio and dashboard views |
| Portfolio snapshot | versioned projection at a source sequence | policy interface, dashboard |
| Dashboard state | read-only materialized projection | human/UI only |

The dashboard owns no order, position, portfolio, model, or safety state. A UI
retry can only repeat a versioned/idempotent request through a separately
authorized command boundary; the dashboard projection itself exposes query
methods only.

## Event semantics

`EventEnvelope` separates:

- `occurred_at`: when the domain event occurred;
- `observed_at`: when the system learned it, never earlier than occurrence;
- `event_id`: immutable delivery/idempotency identity;
- `aggregate_type` and `aggregate_id`: state ownership boundary;
- `sequence`: monotonic aggregate ordering;
- `correlation_id`: end-to-end decision/request lineage;
- `causation_id`: the immediate causal predecessor when applicable;
- `schema_version`: event payload contract;
- `content_sha256`: deterministic immutable content identity.

The future delivery assumption is at least once. Therefore consumers must be
idempotent by event ID. A different payload under an existing ID is a contract
violation. An event append carries `expected_version`; stale writers conflict
rather than overwrite. A sequence gap, conflicting sequence, uncertain write,
or state disagreement enters reconciliation/fail-closed handling. Replay and
projections must be deterministic.

`EventWriter`, `EventReader`, and `EventProjection` are protocols only. Phase
7.1B does not claim durable transactions or solve R-09.

## Model and prediction contract

`ModelContract` records contract version, model and architecture identity,
feature/target identities, configuration hash, code revision, artifact and
input/output schema fingerprints, training boundary, and research cutoff.

`PredictionEnvelope` records model identity, symbol, completed-feature time,
emission time, earliest eligible action time, horizon, target identity, input
lineage, and either an exact-decimal expected return or an explicit no-trade
reason. For the approved Phase 7 baseline:

```text
earliest_action_time = feature_time + 1 * 5 minutes
```

Deployment metadata is separate from the model artifact. It records lifecycle,
requested runtime mode, validation evidence, rollback identity and explicit
approval reference. Metadata cannot itself start a process or authorize an
adapter. Phase 7 has no trained or qualified cloud model, so no runtime
deployment record is approved by this task.

## Execution abstraction

`ExecutionAdapter` defines future `submit`, `cancel`, and `reconcile` ports.
Every adapter declares capabilities independently:

- public market-data read;
- private account read;
- order write;
- cancellation write;
- runtime mode.

Capability declaration prevents a PAPER or SHADOW label from silently implying
order authority. A later composition root must compare declared capabilities
with an externally approved runtime policy before construction.

Phase 7.1B provides no Binance implementation. The concrete disabled adapter
has every network/account/write capability set to false and deterministically
blocks calls. Order intents carry stable intent, decision and idempotency
identities, exact-decimal quantities/prices, expiration, purpose and
reduce-only semantics. They carry no account credential or exchange signing
material.

## Portfolio abstraction

The portfolio boundary consists of:

- immutable `PortfolioSnapshot` projections at an explicit source sequence;
- `PositionView` records with observation time;
- `ExposureProposal` carrying a quantity supplied by an external future owner;
- `PortfolioDecision` with explicit status, reasons and policy version;
- `PortfolioReadPort` and `PortfolioPolicy` protocols.

This phase adds no allocation engine, sizing optimizer, exposure optimizer, or
automatic leverage functionality. The portfolio policy interface may accept or
reject a supplied proposal; it does not calculate or mutate its quantity.

## Observability and failure policy

Metrics use exact-decimal values, units, timestamps and unique label keys.
Health reports require explicit reason codes for non-healthy states. Alerts
carry severity, stable code, correlation identity and observation time.

The `FailurePolicy` protocol separates failure classification from response.
The pure `FailClosedFoundationPolicy` blocks new actions on every failure. It
can additionally request quarantine, reconciliation, bounded retry and operator
attention. It has no external side effects. Contract violations, stale data,
unknown failures, inconsistent state and sequence gaps never silently continue.

Required future observability families include event lag, projection lag,
duplicate/conflict count, reconciliation age/result, stale-data age, prediction
coverage, model version, adapter capability/mode, rejected intent reasons,
unprotected-position alarms and operator acknowledgements. Names and service
objectives must be frozen before a paper or shadow run.

## Dashboard boundary

`DashboardSnapshot` is a versioned read model containing prediction, order,
position, alert and overall-health projections at one projection version. Its
port exposes only `latest` and `at_version` queries. There are deliberately no
submit, cancel, modify, train, promote or cloud methods.

Any later UI command surface must call a separately authenticated command API;
that API must use idempotency keys, expected aggregate versions, an atomic
event append, durable audit lineage, the same safety gates as non-UI callers,
and exchange reconciliation. The UI cannot bypass or own those rules.

## Change protocol

Any later scientific change must create a new baseline manifest rather than
edit an existing baseline. `phase7_scientific_baseline_v1_1` retains v1 and
records the authorized interval-aware onboard-boundary correction;
`phase7_scientific_baseline_v1_2` retains both predecessors and records the
exact per-interval archive-boundary correction. V1_3 retains all three prior
contracts and records the versioned manifest-level zero-volume quality
correction. Before accepting another manifest, review must compare feature values, target values, folds, universes, row membership,
predictions and economics on identical fixtures/artifacts.

If the Phase 7 source/config hashes change during Phase 7.1B, or any safe CLI
output differs from the approved manifest, classify it as:

`PHASE7_1B_CORRECTNESS_BLOCKER`

Do not update the hashes to conceal drift. Stop and review the scientific
change separately.

## Explicit non-deliverables

Phase 7.1B does not implement model training, new model families, reinforcement
learning, feature additions, external sentiment/on-chain sources, portfolio
automation, risk automation, automatic leverage, real or testnet execution,
private Binance access, cloud operations, databases, event brokers, dashboard
UI, background workers, or holdout evaluation.

## Final local verification

The completed local gate produced:

- 353 tests passed, 0 failed, 0 skipped;
- 25 focused contract and scientific-freeze tests passed;
- Ruff lint passed and all 161 source/test files were already formatted;
- Python compilation and `uv lock --check` passed;
- `git diff --check` passed apart from informational Windows line-ending notices;
- all 20 frozen Phase 7 source/config files remained byte-identical;
- all four safe Phase 7 CLI checks matched the frozen contract and wrote zero files;
- canonical protected-artifact count, bytes and every SHA-256 matched
  `artifact_fingerprint_v1` exactly.

The sole test warning was joblib falling back from unavailable physical-core
detection to the logical-core count on Windows. It did not affect test status.
