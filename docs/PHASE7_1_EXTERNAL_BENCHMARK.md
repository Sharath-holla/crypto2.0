# Phase 7.1 external architecture benchmark

This is a documentation-backed capability comparison, not a performance
backtest. Cell format is `score/source/confidence`; score is 0–5, `U` means the
reviewed primary source did not establish the capability, and confidence is
H/M/L. Unknown is deliberately preferred to inference. In a `U/-/L` cell,
`-` explicitly means that the primary source assigned to that system's column
was reviewed but supplied no affirmative evidence for the dimension; it is not
an unperformed review.

## Primary sources

- O1: this repository's code, tests, manifests and Phase 7 documents at HEAD.
- F1: [Freqtrade lookahead analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/)
  and [strategy customization](https://docs.freqtrade.io/en/latest/strategy-customization/).
- H1: [Hummingbot order lifecycle](https://hummingbot.org/connectors/connectors/architecture/order_lifecycle/)
  and [documentation](https://hummingbot.org/docs/).
- N1: [NautilusTrader concepts](https://nautilustrader.io/docs/latest/concepts/),
  including its documented event store, deterministic simulation, and live
  execution reconciliation surfaces.
- Q1: [Microsoft Qlib documentation](https://github.com/microsoft/qlib/blob/main/docs/index.rst).
- R1: [FinRL repository](https://github.com/AI4Finance-Foundation/FinRL) and
  [FinRL-X paper](https://arxiv.org/abs/2603.21330).
- L1: [LEAN engine documentation](https://www.lean.io/lean/docs),
  [live orders](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/trading-and-orders),
  and [reconciliation](https://www.quantconnect.com/docs/v2/writing-algorithms/live-trading/reconciliation).

## Evidence matrix

| Dimension | Ours | Freqtrade/FreqAI | Hummingbot | Nautilus | Qlib | FinRL | FinRL-X | LEAN |
|---|---|---|---|---|---|---|---|---|
| A Point-in-time data | 4/O1/H | 3/F1/M | U/-/L | 4/N1/M | 4/Q1/M | 2/R1/L | 3/R1/L | 4/L1/H |
| B Availability-time joins | 4/O1/H | U/-/L | U/-/L | 4/N1/M | 3/Q1/L | U/-/L | U/-/L | 4/L1/H |
| C Immutable raw lineage | 5/O1/H | U/-/L | U/-/L | 4/N1/M | 4/Q1/M | 2/R1/L | 3/R1/L | 4/L1/M |
| D Gap/duplicate validation | 5/O1/H | 3/F1/L | U/-/L | 4/N1/M | 3/Q1/L | U/-/L | U/-/L | 4/L1/M |
| E Causal universe | 5/O1/H | U/-/L | U/-/L | 4/N1/L | 4/Q1/M | U/-/L | U/-/L | 5/L1/H |
| F Cold-start support | 4/O1/H | U/-/L | U/-/L | U/-/L | 3/Q1/L | U/-/L | U/-/L | 4/L1/M |
| G Cross-sectional features | 4/O1/H | U/-/L | U/-/L | U/-/L | 5/Q1/H | 2/R1/L | 3/R1/L | 3/L1/L |
| H Multi-asset global models | 4/O1/H | 3/F1/M | U/-/L | U/-/L | 5/Q1/H | 3/R1/M | 4/R1/M | 3/L1/L |
| I Purged/embargo splits | 5/O1/H | U/-/L | U/-/L | U/-/L | 3/Q1/L | U/-/L | U/-/L | U/-/L |
| J Walk-forward | 5/O1/H | 4/F1/M | U/-/L | 4/N1/M | 5/Q1/H | 3/R1/M | 4/R1/M | 5/L1/H |
| K Lookahead diagnostics | 4/O1/H | 5/F1/H | U/-/L | 4/N1/M | 3/Q1/L | U/-/L | U/-/L | 4/L1/H |
| L Calibration ownership | 4/O1/H | U/-/L | U/-/L | U/-/L | 3/Q1/L | U/-/L | U/-/L | U/-/L |
| M Multiple-testing control | 2/O1/H | U/-/L | U/-/L | U/-/L | U/-/L | U/-/L | U/-/L | U/-/L |
| N Cost modeling | 3/O1/H | 4/F1/M | 4/H1/M | 5/N1/H | 4/Q1/M | 3/R1/M | 4/R1/M | 5/L1/H |
| O Funding/margin modeling | 3/O1/H | 2/F1/L | 4/H1/M | 5/N1/H | U/-/L | 3/R1/L | 4/R1/M | 5/L1/H |
| P Fill/slippage simulation | 1/O1/H | 4/F1/M | 4/H1/M | 5/N1/H | 4/Q1/M | 3/R1/M | 4/R1/M | 5/L1/H |
| Q Event-driven runtime | 1/O1/H | 3/F1/M | 5/H1/H | 5/N1/H | 3/Q1/M | 3/R1/M | 4/R1/M | 5/L1/H |
| R Order state machine | 3/O1/H | 3/F1/L | 5/H1/H | 5/N1/H | 0/Q1/M | 1/R1/L | 3/R1/L | 5/L1/H |
| S Position state machine | 2/O1/H | 3/F1/L | 5/H1/M | 5/N1/H | 1/Q1/L | 2/R1/L | 3/R1/L | 5/L1/H |
| T Idempotent commands | 3/O1/H | U/-/L | 4/H1/M | 5/N1/M | 0/Q1/M | U/-/L | U/-/L | 4/L1/M |
| U Durable event/state store | 1/O1/H | 3/F1/L | 3/H1/L | 5/N1/H | 3/Q1/M | 2/R1/L | 3/R1/L | 4/L1/M |
| V Restart/replay | 2/O1/H | 3/F1/L | 4/H1/M | 5/N1/H | 4/Q1/M | 2/R1/L | 3/R1/L | 4/L1/H |
| W REST/WS reconciliation | 2/O1/H | 3/F1/L | 5/H1/H | 5/N1/H | 0/Q1/M | 1/R1/L | 3/R1/L | 5/L1/H |
| X Single-writer/concurrency | 3/O1/H | U/-/L | 4/H1/M | 5/N1/M | U/-/L | U/-/L | U/-/L | 4/L1/H |
| Y Risk engine | 0/O1/H | 4/F1/M | 4/H1/M | 5/N1/H | 4/Q1/M | 4/R1/M | 5/R1/M | 5/L1/H |
| Z Portfolio accounting | 0/O1/H | 4/F1/M | 5/H1/H | 5/N1/H | 5/Q1/H | 4/R1/M | 5/R1/M | 5/L1/H |
| AA Paper/shadow mode | 1/O1/H | 5/F1/H | 5/H1/H | 5/N1/H | 4/Q1/M | 4/R1/M | 5/R1/M | 5/L1/H |
| AB Backtest/live parity | 1/O1/H | 4/F1/M | 4/H1/M | 5/N1/H | 4/Q1/M | 3/R1/M | 4/R1/M | 5/L1/H |
| AC Deterministic simulation | 3/O1/H | 3/F1/L | 3/H1/L | 5/N1/H | 4/Q1/M | 3/R1/L | 4/R1/L | 5/L1/H |
| AD Experiment tracking | 5/O1/H | 3/F1/M | 4/H1/M | 5/N1/M | 5/Q1/H | 4/R1/M | 5/R1/M | 5/L1/H |
| AE Model registry/promotion | 3/O1/H | 3/F1/L | U/-/L | 4/N1/L | 5/Q1/H | 3/R1/L | 5/R1/M | 4/L1/M |
| AF Drift monitoring | 1/O1/H | 2/F1/L | U/-/L | 4/N1/L | 5/Q1/M | 2/R1/L | 5/R1/M | 4/L1/M |
| AG Dashboard/control plane | 1/O1/H | 4/F1/M | 5/H1/H | 4/N1/M | 4/Q1/M | 3/R1/L | 5/R1/M | 5/L1/H |
| AH Venue adapter breadth | 1/O1/H | 5/F1/H | 5/H1/H | 5/N1/H | 3/Q1/L | 2/R1/L | 4/R1/M | 5/L1/H |
| AI Research reproducibility | 5/O1/H | 4/F1/M | 4/H1/M | 5/N1/H | 5/Q1/H | 4/R1/M | 5/R1/M | 5/L1/H |

## Interpretation

Our relative strengths are artifact immutability, causal split/universe controls,
post-signal target timing, reproducible experiment identity, and tested pure
concurrency semantics. The largest gaps are realistic fill simulation, a
durable runtime/event database, live reconciliation, risk/portfolio engines and
drift operations. NautilusTrader and LEAN are the strongest design references
for a later execution substrate; Qlib is the strongest research workflow
reference; Hummingbot is a useful connector/order-lifecycle reference. No
framework is copied wholesale and no score asserts superior trading returns.
