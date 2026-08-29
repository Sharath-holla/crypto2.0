# Phase 7.2 prospective data-capture plan

This is a disabled design for information that may be unavailable
retrospectively. It performs no network I/O and starts no service.

## Shared contract

Every prospective record contains source identity plus event, receive and
availability time. Quality is one of `MISSING`, `STALE`, `VALID`, `INVALID`, or
`PROVIDER_ERROR`; missing never means zero or neutral. Storage remains immutable
Parquet with raw payload lineage, manifests and checksums. Corrections create a
new version instead of overwriting a historical partition.

## Dataset plan

| Dataset | Schema | Initial retention | Training status | Main failure rule |
|---|---|---|---|---|
| Open interest | `open_interest_observation_v1` | legitimate public 5m recent/forward observations | `FORWARD_ONLY`; historical Phase 7 disabled | never fabricate pre-coverage history |
| Best bid/ask and spread | `bbo_observation_v1` | bounded continuous/snapshot records | prospective only | bid/ask arithmetic, freshness and receive time required |
| Depth | `depth_summary_v1` | 10/25/50 bps summaries first | prospective specialist only | sequence gaps invalidate; no zero-depth fill |
| Liquidations | `liquidation_event_v1` | event stream | prospective specialist only | no historical reconstruction without source events |
| Exchange rules | `exchange_symbol_metadata_v1` | changes plus periodic snapshots | point-in-time eligibility/evaluation candidate | current rules cannot be backfilled as historical truth |
| News/events | `event_context_v1` | metadata/first-seen/revisions where licensed | late-fusion research only | publisher time is not first-seen time; direction is not truth |

## Symbol selection

`ProspectiveSymbolPolicy` accepts only already-frozen core and expansion
membership and returns a deterministic bounded union. It does not query today's
universe or use future survival/liquidity. The default cap is 30 and the policy
is disabled. A future task may derive a collector list from a reviewed fold or
prospective research universe; Phase 7.2 does not start it.

## Existing OI collector

The current public Binance OI foundation is restart-safe and idempotent through
manifest identity and key deduplication, preserves raw/normalized checksums,
uses provider/receive/availability timestamps, rejects retention-exceeding
requests and labels data `FORWARD_ONLY`. Its symbol tuple is configurable. The
network guard remains separate and unset; no 24/7 process was started.

## Cost control

- BBO: store compact observations, not redundant full books.
- Depth: begin with summaries; raw L2 needs a separately approved specialist.
- Liquidations: event records only.
- OI: legitimate 5m cadence.
- Metadata: changes and periodic reconciliation rather than high-rate polling.
- Run a short capacity sample before committing storage; record bytes per
  symbol-day and sequence/quality failure rates.

## Restart and lineage requirements

Future collectors must be single-writer or use atomic partition ownership,
derive deterministic idempotency keys from provider identity, refuse
conflicting duplicates, checkpoint source sequence where available, and
reconcile manifests after restart. Provider errors create explicit quality
records/alerts; they do not create neutral features.

No private Binance endpoint, API credential, order endpoint or account state is
part of this plan.
