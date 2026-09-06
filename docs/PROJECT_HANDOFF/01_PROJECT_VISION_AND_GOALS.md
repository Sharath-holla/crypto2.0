# Project Vision and Goals

## Original problem

Crypto 2.0 asks whether public Binance market data can support a reproducible, causally evaluated
crypto-futures intelligence system whose decisions remain useful after realistic research costs.
Earlier BTC-only experiments found weak or inconsistent edge, which motivated multi-year,
multi-asset, higher-timeframe, and walk-forward research rather than a profitability claim.

The intended system separates responsibilities:

- market data and validation establish what was knowable;
- features describe completed market state;
- targets describe future outcomes without leaking them into features;
- models estimate expected return or opportunity;
- calibration and thresholds may emit `NO_TRADE`;
- research economics test fees, spread, and slippage;
- a future risk engine owns sizing, exposure, leverage, and kill switches;
- future paper/shadow/live adapters own execution and reconciliation.

## Why Binance USD-M

ADR-017 superseded the old Binance-data/CoinSwitch-execution concept. Binance is the sole
canonical market-data and possible future execution venue. USD-M perpetual futures are the
primary research market because they provide the contract, funding, mark, and index public-data
families needed by this research. Binance Spot remains an explicitly separate secondary dataset;
its Bronze identity must never be merged with USD-M.

## Decision semantics

Future user-facing actions may include `LONG`, `SHORT`, `HOLD`, `EXIT`, and `NO_TRADE`, but these
are **planned**, not a current live engine. The current Phase 7 layer predicts continuous returns
and applies a cost-aware threshold. `NO_TRADE` is essential: weak, costly, unavailable, stale, or
unsafe opportunities should be rejected rather than forcing a position.

Profitability alone is insufficient. Evidence must be stable across folds, symbols, horizons,
regimes, costs, and coverage; must survive leakage controls; and must not depend on a few trades or
assets. Prior positive-looking small samples were classified as insufficient rather than promoted.

## Prediction versus risk

Prediction estimates an outcome. Risk decides whether and how much capital may be exposed. These
must remain separate because even a strong score cannot override maximum loss, liquidity,
correlation, exposure, operational-health, or kill-switch rules. Leverage changes payoff and
liquidation risk; it is a future risk/execution decision, never a predictive feature.

## Causality and universe integrity

Chronological walk-forward testing is required because random shuffling would mix future regimes
into the past. Features use only completed data available at `feature_time`; labels enter at
`open[i+2]`; actual `label_end_time` purging and embargo protect split boundaries.

Current listings are not historical truth. A current-only universe would discard failed/delisted
contracts and introduce survivorship bias. The registry preserves official historical evidence,
and each fold admits symbols using only information available at its TRAIN end. Point-in-time
universe construction therefore prevents later survival, liquidity, coverage, or performance from
changing earlier membership.

## Intended final capabilities — planned only

- opportunity/ranking and calibrated uncertainty;
- `LONG`/`SHORT`/`HOLD`/`EXIT`/`NO_TRADE` policy;
- position sizing, risk-per-trade, portfolio exposure, correlation and liquidity controls;
- leverage caps, daily/weekly loss limits, and drawdown kill switch;
- event-driven backtesting with richer execution realism;
- Binance paper, then shadow, then tiny-capital operation;
- monitored champion/challenger and production deployment.

None of these future capabilities is authorized merely because it appears in the roadmap. No
qualified Phase 7A model exists, and no profitability is promised.
