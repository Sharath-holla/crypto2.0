# Architecture Decisions

The original decision log is `docs/DECISIONS.md`. Its numbering has historical reuse, so cite both
heading and content rather than assuming an ADR number is globally unique.

| Decision | Rationale / current consequence |
| --- | --- |
| Binance-only canonical venue (ADR-017) | Supersedes CoinSwitch; Spot/USD-M remain separate source domains |
| Exact decimals and UTC microseconds | Preserve exchange precision and unambiguous half-open time |
| Immutable Bronze, gated Silver, content-addressed Gold | Raw truth remains auditable; outputs reproducible |
| Quality failures reported, not repaired | No synthetic candles/interpolation; official reconciliation retains lineage |
| Historical/PIT universe | Prevent current-listing and survivorship bias; keep delisted assets where historically eligible |
| Core20 + separate EXPANDING view | Stable benchmark plus causal cold-start experiment; no pooling |
| Completed-candle timing and `open[i+2]` | Full observability and decision latency before entry |
| Walk-forward, actual-label purge, embargo | Protect temporal ownership rather than random split |
| Cal-A/Cal-B separation | Calibration and threshold choice cannot reuse the same observations |
| `NO_TRADE` explicit | Costs/weak evidence may reject every opportunity safely |
| Fixed-policy cost stress primary | Prevent trade-list changes from disguising cost sensitivity |
| G0/C0/P0/H0 comparison | BTC is not assumed representative; compare pooled/local structure and coverage |
| Risk/model separation | Risk owns sizing/leverage/exposure and can veto ML; ML cannot disable stops |
| Lifecycle absence | Use request∩validated lifecycle; do not delete delisted symbols or fabricate rows |
| August lock | Prospective holdout remains unused and unauthorized throughout development |
| Phase 7A reduction | Separate affordable Core20-primary experiment; full methodology/config preserved |
| Side-effect-only observability | Progress reporting cannot alter scientific data or decisions |
| Cost-aware finite batch | Supervisors/checkpoints/deadlines prevent uncontrolled cloud spend |

Scientific corrections are frozen through successor manifests under `configs/contracts/`, rather
than rewriting old artifacts. Future modifications require a new version/identity and comparison
against preserved outputs.
