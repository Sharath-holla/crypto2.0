# Future dashboard and execution control-plane design

This document is design-only. The current code adds pure deterministic state
transitions and tests; it has no exchange adapter, network call, credentials,
account access, or order-submission path.

## Authority boundaries

The dashboard is a UI/control plane, never the safety engine. Binance plus the
durable local/event state are authoritative. The model emits a versioned
decision; a separate risk engine may produce an order intent; only a single
execution writer may submit it. UI retries cannot create exposure.

```text
market data -> feature/model -> decision ledger -> risk gate -> intent ledger
                                                       |
                                                       v
dashboard <- read models <- durable event store <- single writer <-> exchange
                                          ^             |
                                          +-- reconciler-+
```

Identifiers are immutable: `client_command_id`, `strategy_decision_id`,
`order_intent_id`, and exchange client-order ID. A uniqueness constraint on
intent/client-order identity and optimistic aggregate versioning provide
idempotency. Duplicate identical commands return the existing result; conflicting
payloads fail safe.

## Order and position states

Order states: CREATED, VALIDATED, SUBMITTING, ACKNOWLEDGED, PARTIALLY_FILLED,
FILLED, CANCEL_PENDING, CANCELLED, REJECTED, EXPIRED, and
UNKNOWN_RECONCILE_REQUIRED. Fills are cumulative and monotonic. A fill received
during cancel-pending wins; a late cancel cannot erase exposure.

Future position states: FLAT, ENTRY_PENDING, OPEN, REDUCING, EXIT_PENDING,
CLOSED, RECONCILING, ERROR_SAFE. Position quantity derives from authoritative
fills, never from a button click or a locally assumed order status. Manual
exchange changes force reconciliation before new risk.

## Concurrency, crash and reconciliation rules

- One writer owns submission/cancel/replace. Other processes append commands.
- Each state update is an atomic event append plus materialized-view version.
- WebSocket supplies low-latency events; REST periodically verifies open orders,
  positions, balances and order status. Neither source alone is trusted.
- Unknown, conflicting or sequence-gapped events enter reconcile-required state
  and block new exposure. Restart replays durable events, then reconciles before
  enabling commands.
- A kill switch stops new intents and attempts policy-defined reduction; it must
  not falsely label positions closed before exchange confirmation.
- Protective orders are reduce-only where the venue supports them. Stop updates
  are monotonic (long stops never decrease; short stops never increase), rounded
  to exchange filters, versioned and reconciled.

## Dashboard views

Read-only-by-default panels: data freshness/gaps; universe and fold membership;
model/version/prediction/uncertainty/NO_TRADE reason; open orders and positions;
realized/unrealized PnL; leverage/liquidation distance; SL/TP/trailing state;
reconciliation health; drift/calibration/coverage; and champion/challenger shadow
comparison. Mutating controls require authentication, role checks, confirmation,
idempotency ID and an audit record.

## Verification matrix

The exchange-independent suite implements all 35 required deterministic race
scenarios: duplicate UI/strategy commands; stable exchange IDs; identical and
conflicting idempotency retries; two-writer order/position version conflicts;
partial entry/protection/cancel crossings; fill-vs-cancel ordering; WebSocket
before REST acknowledgement; newer/stale REST snapshots; duplicate,
out-of-order, and sequence-gapped events; crashes before/after submit; restart
and replay; disconnected fills; manual close/order discovery; rejected and
partial reduce-only protection; non-loosening stops; filter changes; network
partition; stale data; kill switch during partial fill; transaction conflict;
replay determinism; retry exposure uniqueness; no false close; and explicit
safe-error alarm for any unprotected open quantity.

These tests validate pure transition semantics only. Process/database crash
atomicity, real connector behavior, durable transaction isolation, venue filter
changes, rate limits, listen-key recovery, and live reconciliation require a
later simulated adapter plus database integration test phase. Passing the pure
suite does not authorize a live adapter.

Paper and shadow modes use the same decision/risk/state interfaces and different
adapters. Before a shadow begins, its minimum independent observation count,
evaluation horizon, paired loss/economic metrics, cost/turnover limits,
calibration tolerances, and reconciliation-health limits must be frozen in the
run manifest. Promotion is never automatic: matched inputs, the predeclared
minimum, paired dependence-aware statistics, stable calibration, acceptable
cost/turnover and reconciliation health, no holdout access, human approval,
and a versioned rollback target are all required. Drift may quarantine or alert;
it cannot retrain or promote.

## Phase 7.1B typed contract boundary

Phase 7.1B implements the side-effect-free interfaces described here under
`crypto_ai.contracts`. It adds versioned event, model, prediction, adapter,
portfolio, observability, failure-policy and dashboard-read contracts. The
existing pure state-machine race simulations remain unchanged and do not import
the new package.

The only concrete adapter is disabled and performs no I/O. PAPER, SHADOW and
LIVE remain declarative protocol modes, not authorizations. Dashboard state is
a read-only projection; it owns no safety or exchange state. See
`PHASE7_1B_ARCHITECTURE_FOUNDATION.md` for the exact compatibility, ownership
and scientific-freeze rules.
