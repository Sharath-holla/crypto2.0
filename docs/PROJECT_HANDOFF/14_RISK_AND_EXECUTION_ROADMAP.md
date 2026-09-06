# Risk and Execution Roadmap

## Implemented now

The research layer implements expected-return predictions, causal evaluation, cost thresholds,
`NO_TRADE`, non-overlapping per-symbol research trades, and disabled future execution interfaces.
`crypto_ai.contracts.execution.DisabledExecutionAdapter` performs no I/O and rejects submit/cancel
with `EXECUTION_DISABLED_PHASE7_1B`. There is no account client, position sizer, leverage engine,
portfolio optimizer, order router, or production dashboard owner.

## Planned — not authorized or implemented

Future risk architecture is expected to own:

- maximum risk per trade and risk-based position sizing;
- per-symbol, directional, gross/net, sector/cluster, and portfolio exposure limits;
- hard leverage caps and margin/liquidation-distance controls;
- daily and weekly loss limits;
- peak-to-trough drawdown kill switch;
- correlation/concentration constraints;
- volatility, liquidity, staleness, and spread filters;
- exchange/account reconciliation and unprotected-position alarms;
- operator approval, audit, rollback, and fail-closed health gates.

Exact numerical limits are **UNKNOWN / NOT VERIFIED** and must not be invented. Leverage belongs
here because it changes loss and liquidation exposure; it must never be fed to the predictor as a
feature or optimized to make a backtest look profitable.

## Promotion sequence

1. Finish retrospective folds and obtain a genuinely qualified candidate.
2. Phase 7.5 hardening/robustness if separately specified and authorized.
3. Event-driven simulation with realistic exchange constraints.
4. Binance paper/test environment with no real capital.
5. Shadow mode: observe decisions without submitting orders.
6. Tiny-capital deployment only after risk, security, reconciliation and owner gates.
7. Production scaling only after sustained monitored evidence.

Every stage needs an explicit promotion decision. No document, model score, or runtime label grants
order authority, and profitability can never be promised.
