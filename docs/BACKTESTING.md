# Backtest Foundation V1

Phase 4 implements an event-ordered, out-of-sample-only research backtester.
It is not an execution engine and contains no account or order access.

## Timing and exposure

For candle `[09:55, 10:00)`, values become available at 10:00 UTC. The
prediction has `feature_time=10:00`; reference entry is the next available 5m
open at 10:00 and exit is the open 60 minutes later. Entry before feature time
is rejected; the observed prediction-candle close is never an execution price.

Only validation/test prediction artifacts are accepted. The reported suite
uses development test. One normalized position may be open; overlapping
signals are skipped. There is no leverage, pyramiding, or forced trade.

## Costs

The base configuration assumes 4 bps taker fee per side, 1 bp round-trip
spread, 1 bp slippage per side, and actual funding events in
`(entry_time, exit_time]`. The non-funding hurdle is therefore 11 bps before a
separate 2 bps signal threshold. These are configurable research assumptions,
not a claim about any user's tier or executable fills. Stress runs multiply
non-funding cost by 1.0, 1.5, 2.0, and 3.0.

Positive funding is a long cost and short credit; negative funding is the
opposite. No fixed funding interval is assumed.

## Metrics and limitations

Artifacts report gross/net/compounded return, drawdown, daily annualized Sharpe
when defined, hit rate, profit factor, average trade, exposure, turnover,
funding contribution, regime performance, and pressure buckets. Flat
strategies have zero return/drawdown and undefined trade statistics.

Bar data cannot recover queue position, historical executable spread, partial
fills, impact, latency variance, or depth. Results are diagnostics, not a
profitability or deployment claim.

## Phase 4.1 execution and stress policy

When validated 1-minute data covers a prediction, entry uses the first 1-minute
open at or after `feature_time + configured latency`; the 60-minute exit uses a
later 1-minute open. Otherwise the explicit Label V1 next-5-minute-open
reference is used. Same-close execution is prohibited. Delay scenarios are the
base executable observation, +1 minute, and +5 minutes; no sub-minute or
tick-level precision is claimed.

Maker and taker fees are separate configuration fields. The research run uses
the configured taker fee, an `ASSUMED_SPREAD`, fixed per-side slippage, one
normalized unleveraged position, and one-position-at-a-time exposure. Funding
uses the realized events satisfying `entry_time < funding_time <= exit_time`;
model eligibility may use only funding known at signal time. Positive funding
is a long debit and short credit.

Cost diagnostics use 0×, base, 1.25×, 1.5×, and 2× non-funding costs. Each
result records trade count and flags fewer than 30 trades as insufficient.
NO_TRADE remains mandatory and thresholds are not relaxed to produce activity.

## Real Phase 4.1 OOS result

Backtest `backtest-v2-1-1ab164e8a1409ebbad40b155` evaluates D2's 102,580
development-test opportunities using validated 1-minute entries from
`silver-7f6d09b0d30767698f12f843`. At the 13 bps base hurdle it makes 5 trades
and leaves 102,575 opportunities as NO_TRADE. All five are long/bear-regime
observations; four are high-volatility observations. This is explicitly below
the 30-trade reliability gate.

The five trades sum to 12.2283% gross and 11.6783% net: fees 0.4000%, assumed
spread 0.0500%, slippage 0.1000%, and funding 0.0000%. Compounded net is
12.0948%, expectancy 2.3357%, max drawdown -0.4456%, exposure 0.0585%, and
turnover 10. Sharpe 21.89, undefined Sortino, profit factor 27.21, and Calmar
94.90 are reported mechanically but are not meaningful with five trades.

The broad 0-cost diagnostic makes 2,478 trades and loses 1.8975% net including
actual funding, with negative expectancy. Base/1.25×/1.5× select 5 trades;
2× selects only 2. Their positive totals remain `INSUFFICIENT_SAMPLE` and
cannot support an edge claim. +1-minute and +5-minute delay retain five trades
with 11.9521% and 9.3043% summed net respectively; the +5-minute scenario has
one unavailable final observation. The apparent returns are driven by a few
extreme one-hour BTC moves, not a broad repeatable signal.

## Phase 5 fold execution

Phase 5 preserves the 11 bps base non-funding assumptions and actual funding
event accounting. Every fold threshold is frozen on its calibration segment;
test is then replayed at 0x, 1x, 1.25x, 1.5x, and 2x non-funding costs without
retuning. Zero cost is diagnostic only.

Validated one-minute next-open execution is used only when both the delayed
entry and 60-minute exit are present without a gap. All other observations use
the Label V1 next-five-minute-open references and carry
`execution_resolution = 5m`; one-minute rows carry `1m`. The completed
signal-candle close remains forbidden. Each fold starts normalized equity
independently, and completed non-overlapping tests are stitched chronologically
for pooled diagnostics.

Qualification requires sufficient total and per-fold activity and rejects
performance dependent on one fold, year, or regime. Machine-readable metrics
remain available below reliability thresholds, but are explicitly classified
as insufficient rather than promoted as evidence.

## Phase 5.1 fixed and adaptive cost semantics

Phase 5.1 makes fixed-policy stress the primary robustness result. The exact
base-cost trade list is assigned deterministic trade IDs and repriced at 1x,
1.25x, 1.5x, and 2x non-funding costs. Selection, threshold, entry, exit, and
direction cannot change; a different trade-identity hash invalidates the run.
Funding cash flow is based on the same held interval and is not multiplied by
the execution-cost factor. Higher fees, spread, and slippage therefore make
fixed-policy net PnL monotonically non-increasing.

Adaptive-policy stress remains a separately named secondary diagnostic. It
re-evaluates the expected-edge eligibility hurdle at each cost multiplier, so
trade count and identity may change. Fixed and adaptive artifacts, tables, and
summary keys are never combined under an unlabeled cost-stress result.

All economic outputs contain a statistical reliability flag/reason. Raw ratio
calculations are auditable, but an unreliable profit factor is removed from the
headline field and displays as `INSUFFICIENT_SAMPLE`. Phase 5.1 does not add
Sharpe, Sortino, or Calmar as evidence.
