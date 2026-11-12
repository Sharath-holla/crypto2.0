# Phase 7 economic-evaluation architecture (design only, NOT ACTIVE)

Written by Claude (2026-11-08). Status: **DESIGN, NOT IMPLEMENTED, NOT USED BY THE FIRST SMOKE.**
The first smoke needs only the FORECAST pipeline. Nothing here changes a label, a feature, a target,
a fold, Gold, the sidecar or any identity.

## 1. Layer boundaries

| Layer | Owns | Current state | May depend on |
|---|---|---|---|
| FORECAST | features -> predicted forward return (LightGBM G0/C0/P0/H0), calibration (Cal-A) | implemented | Gold, folds |
| ACTION POLICY | prediction -> LONG / SHORT / NO_TRADE (Cal-B thresholds) | implemented (`economics.select_cal_b_thresholds`) | FORECAST output only |
| TRADE SIMULATION | action -> entry/exit times and reference prices, non-overlap per symbol | implemented as proxy (`build_oos_trades`), `REFERENCE_EXECUTION_PRICE` | ACTION POLICY, Gold timestamps |
| COST MODEL | per-trade cost in bps | `STATIC_COST_STRESS` 11 / 14 / 20 bps scenarios | TRADE SIMULATION |
| FUNDING MODEL | settlement cash flows while a position is open | **NOT_MODELLED** | TRADE SIMULATION, funding history |
| POSITION ACCOUNTING | per-position PnL incl. cost + funding | trade-level proxy only | COST, FUNDING |
| PORTFOLIO ACCOUNTING | capital, concurrency, equity curve, drawdown | NOT_AVAILABLE | POSITION ACCOUNTING |
| RISK | limits, leverage, sizing | out of scope (forbidden) | PORTFOLIO |
| LIVE EXECUTION | orders | forbidden; import-boundary tests enforce isolation | never imported by research |

Rule: information flows strictly downward. No layer below FORECAST may feed back into labels,
features, fits, calibration or Cal-B thresholds. Labels stay pure forward returns at the reference
price; funding and costs belong to economic evaluation only.

## 2. Funding settlement interface (future)

Inputs already present: Binance USD-M funding history is acquired (`MarketDataKind.FUNDING`) and
attached as-of to candles as `funding_rate` (feature `funding_zscore`). That as-of attachment is a
**feature** view (last known rate) and must not be reused as a settlement ledger.

A future `FundingModel` needs, per settlement event (one row per symbol per settlement):

| Field | Meaning | Source / rule |
|---|---|---|
| `symbol` | USD-M perpetual | registry |
| `funding_time` | settlement timestamp (UTC, exchange-reported `fundingTime`) | funding history |
| `funding_rate` | exact decimal string, realised rate for that settlement | funding history |
| `rate_known_time` | when the rate became knowable | = `funding_time` for realised rates; predicted rates are NOT used |
| `mark_price_at_settlement` | notional basis | mark-price klines at `funding_time` (verify against official docs) |
| `interval_hours` | settlement spacing (8h historically; some symbols 4h/1h) | derived from consecutive `funding_time`s, never assumed |

Per position (side s = +1 LONG, -1 SHORT; quantity q; entry time t0; exit time t1):

```
cash_flow_k = - s * q * mark_price(funding_time_k) * funding_rate_k
position_funding = sum over settlements k with t0 < funding_time_k <= t1   (convention TO BE VERIFIED)
```

Sign convention (to verify against current official Binance documentation before implementing):
positive funding rate -> LONG pays, SHORT receives; negative -> the reverse. The boundary convention
(position opened exactly at, or closed exactly at, a settlement) must be confirmed from the official
docs and fixed in a versioned contract; until then it is an OPEN decision, which is why no code exists.
Multiple settlements inside one holding period are summed; a 60-minute horizon crosses at most one
8h settlement but can cross one with 1h-interval symbols. Missing funding rows are reported as missing
(`FUNDING_DATA_GAP`), never forward-filled or assumed zero.

## 3. Cost model interface (future)

```
CostModel.cost_bps(symbol, side, entry_time, notional, context) -> CostBreakdown
  context = features known at entry_time only (spread proxy, volatility, volume, depth if acquired)
CostBreakdown = {fee_bps, spread_bps, impact_bps, label}
```

`STATIC_COST_STRESS` (11 / 14 / 20 bps by liquidity tier) is the first implementation and stays a
scenario label, not an estimate of fills. Volatility-, liquidity- or depth-based models plug in behind
the same interface without touching labels, because labels are cost-free forward returns.

## 4. What must exist before any tradability claim

Funding cash flows; a validated cost model; execution/slippage at a non-reference price; position
concurrency and capital accounting; portfolio equity curve and drawdown; capacity; independent
multi-fold OOS evidence; matched-baseline superiority on paired OOS folds; robustness; and
multiple-testing control (the registered selection chronology + trial ledger). Until then every report
carries `economic_status = REGRESSION_PLUMBING_ONLY_NO_TRADABILITY_CLAIM`, and
`hardening.require_no_tradability_claim` fails any payload that claims profitability while funding is
`NOT_MODELLED`.
