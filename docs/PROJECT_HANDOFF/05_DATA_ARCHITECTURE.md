# Data Architecture

## Source and timeframes

The canonical Phase 7 source is public Binance USD-M USDT-margined perpetual-futures data. The
decision interval is 5m. Required direct candle families are 5m, 12h, and 1d; funding, mark, and
index are derivative families. Features named 15m, 30m, 1h, 2h, or 4h are rolling/return horizons
derived from the primary stream unless an explicitly named HTF feature says 12h or 1d. There is no
canonical direct 4h source requirement in Phase 7A.

## Bronze, Silver, Gold

| Layer | Meaning | Rules |
| --- | --- | --- |
| Bronze | Immutable raw/source truth plus source manifests/checksums | Never silently overwrite or repair; preserve exchange decimal strings |
| Silver | Validated/trusted data promoted from Bronze or approved composed official-source evidence | Quality and interval/lifecycle checks must pass; failures/quarantine remain explicit |
| Gold | Model-ready features, targets, timing, lineage, and partitions | Built only from validated causal inputs; identity and file hashes checkpointed |

Official Binance archive ZIPs require matching `.CHECKSUM` evidence. Public REST may reconcile a
missing archive row only through the evidence-gated reconciliation contract; it is another
official source, not synthetic repair. Reconciliation outputs retain lineage.

## Absence and corruption semantics

- Never fabricate, interpolate, forward-fill, or synthesize OHLC candles.
- Pre-listing and post-delisting windows outside a validated lifecycle are legitimate lifecycle
  absence, not gaps.
- A partial request loads only `requested_window ∩ validated_lifecycle`.
- Missing timestamps inside an active lifecycle are interior gaps and fail closed unless official
  reconciliation establishes the row.
- Duplicate keys, malformed shapes, corrupt/nonfinite market values, invalid interval spacing, or
  checksum mismatch are quality failures, not low liquidity.
- A zero-volume but structurally valid market interval is distinguishable from corruption and may
  legitimately support `NO_TRADE`/low-liquidity outcomes.

## Registry and discovery

The registry unions current ExchangeInfo with historical symbols proven by official archive keys,
so delisted symbols remain available for earlier folds. The Phase 7A durable discovery checkpoint
contains 507 completed candidates. The requested “790 registry symbols” could not be verified from
the stopped-VM-accessible repository/hold evidence and is therefore **UNKNOWN / NOT VERIFIED**.
Do not substitute 790 for the verified 507 discovery count.

Core20 is selected at 2022-01-01 from causal coverage/history/liquidity/volatility descriptors.
The full design can add up to ten causally eligible non-core members per fold (30 total), but
Phase 7A evaluates only CORE. Delisted HNT remains because later survival cannot rewrite the past.

## Manifests and durability

Manifests bind source URLs/types, half-open UTC ranges, schema, record counts, checksums, quality,
registry/universe identities, feature/target versions, holdout flags, and partition files.
`CheckpointStore` validates required outputs rather than trusting a filename. Current acquisition
checkpoint and manifest hashes are recorded in [20_CURRENT_STATE.md](20_CURRENT_STATE.md). Gold's
checkpoint hash is unknown while the VM is stopped and must be validated before reuse.
