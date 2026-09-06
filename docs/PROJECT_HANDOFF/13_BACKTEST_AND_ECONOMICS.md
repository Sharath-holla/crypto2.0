# Backtest and Economics

## Current Phase 7 research contract

Cal-B compares a frozen threshold grid after the TRAIN-only liquidity tier cost. The configured
round-trip assumptions are:

| Tier | Taker fee | Spread | Slippage | Total round trip |
| --- | ---: | ---: | ---: | ---: |
| High | 4 bps/side | 1 bp | 1 bp/side | 11 bps |
| Medium | 4 bps/side | 2 bps | 2 bps/side | 14 bps |
| Lower | 4 bps/side | 4 bps | 4 bps/side | 20 bps |

These are labeled **RESEARCH COST ASSUMPTIONS**, not reconstructed realized costs. A prediction
must exceed tier cost plus the chosen 2/4/6/8/10 bps edge threshold. Fewer than 30 Cal-B trades
leaves the group's threshold null and yields `NO_TRADE`.

TEST trades use `entry_time=open[i+2]`, the stored target return, and no overlap per symbol until
the active horizon expires. Direction is prediction sign. Fixed-policy stress preserves exact
trade IDs/directions at 1.0×, 1.25×, 1.5×, and 2.0× costs; adaptive stress separately lets the
frozen threshold policy see the stressed cost without retuning thresholds.

Funding rate exists as causal input context but **funding charges are not deducted from Phase 7
trade returns**. Current Phase 7 economics also omit partial fills, order-book queue/impact, tick
and lot rounding, exchange rejects, liquidation/margin mechanics, precise network/order latency,
funding payments, portfolio concurrency, and venue reconciliation. Those gaps must be resolved and
validated before production or live claims.
