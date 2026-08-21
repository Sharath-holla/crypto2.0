# Future Trading System Architecture Lock

Status: canonical design constraint; documentation only. No module described in
this document is authorized or implemented by Phase 5 Hardening. Phase 6 has
not started.

## Permanent safety boundary

The eventual system is Binance-only for canonical public market data and any
later explicitly authorized execution. Prediction, trade quality, expected
edge, liquidity, risk, sizing, leverage, portfolio control, trade management,
safety, and exchange execution are separate responsibilities. No model may
directly emit an unrestricted order containing coin, direction, notional,
leverage, Take Profit, and Stop Loss. Deterministic risk controls can always
reduce or reject an action, and ML can never disable a hard maximum-loss stop.

LLMs may eventually summarize news or events into constrained, timestamped,
structured data. An LLM never generates or submits an unrestricted Binance
order.

## Canonical future decision pipeline

```text
BINANCE MARKET DATA
  -> DATA VALIDATION
  -> FEATURE ENGINE
  -> COIN STATE + BTC/ETH STATE + MARKET STATE + DERIVATIVES
  -> MAIN MARKET MODEL + TEMPORAL MODEL + REGIME ENGINE + FEAR/EVENT ENGINE
  -> TRADE QUALITY / META LAYER
  -> EXPECTED EDGE
  -> NO_TRADE FILTER
  -> LIQUIDITY GATE
  -> RISK ENGINE
  -> PORTFOLIO ENGINE
  -> POSITION SIZING
  -> LEVERAGE LIMITER
  -> ENTRY
  -> TRADE MANAGEMENT
  -> TP / SL / HOLD / EXIT
  -> PRE-TRADE / EXIT SAFETY
  -> BINANCE EXECUTION ADAPTER
```

The ordering is a safety contract. A downstream component may reject or reduce
an upstream proposal; an upstream model cannot bypass a downstream gate.

## Decision ownership

| Decision | Owner |
| --- | --- |
| What may happen? | Main and Temporal Models |
| What market structure exists? | Regime Engine |
| How fearful, euphoric, or stressed is the market? | Fear/Euphoria Engine |
| Is the prediction worth considering? | Trade Quality / Meta Layer |
| Is expected return larger than costs? | Expected Edge Engine |
| Can the trade be executed safely? | Liquidity Gate |
| Can the account tolerate it? | Risk Engine |
| How much capital? | Position Sizing, constrained by Risk and Portfolio |
| How much leverage is safe? | Risk Engine / deterministic Leverage Limiter |
| When and how to enter? | Approved Signal plus Execution Adapter |
| TP, SL, hold, partial exit, or full exit? | Trade Management plus Risk |
| How does it affect total exposure? | Portfolio Engine |
| Submit the approved order | Binance Execution Adapter after all gates |

## Asset heterogeneity is mandatory

BTC behavior must never be assumed representative of ETH, liquid large-cap
alts, medium-cap alts, small-cap alts, or newly listed assets. These groups can
differ in volatility, liquidity, spread, slippage, volume, trade intensity,
funding, trend persistence, BTC beta/correlation, impact, listing age, and
pump/crash behavior.

Future asset context may include `coin_age`, `history_length`,
`liquidity_score`, `volatility_score`, `BTC_beta`, `BTC_correlation`, average
spread, volume/funding profiles, and data-driven cluster probabilities. Every
value must be historically available at its feature timestamp. New listings
require explicit uncertainty and history sufficiency checks and may face
stricter risk, liquidity, or NO_TRADE rules.

## Multi-asset model benchmarks

No multi-asset structure is presumed to win. When explicitly authorized,
research must compare on matched leakage-safe evidence:

- Global model: eligible assets together, normalized market features, and
  asset/context identity.
- Cluster model: evidence-driven groups such as BTC/ETH, liquid large caps,
  medium caps, volatile small caps, or new/unstable listings. Clusters are not
  permanent hand-authored labels.
- Per-coin model: coin-specific estimation only where history and sample size
  are sufficient; do not automatically create hundreds of independent models.
- Hybrid model: shared global learning plus coin/cluster context and
  coin-specific calibration. This is a hypothesis, not a chosen winner.

Comparable features should use relative or normalized quantities where
appropriate: return divided by realized volatility, ATR/price, volume divided
by rolling volume, spread/price, funding z-score, OI percent change, relative
strength versus BTC/market, and volatility/liquidity percentiles. Raw values
must not be assumed comparable across coins.

## Prediction and profit-estimation contracts

The Main Market Model answers what may happen; it does not allocate capital.
Its eventual contract may produce an expected-return distribution rather than
an exact profit promise:

```text
MarketPrediction
  asset
  prediction_time
  horizon
  expected_return
  return_quantiles
  probability_return_positive
  probability_return_above_costs
  uncertainty
  model_version and lineage
```

Current Label V1 remains the unchanged 60-minute target. Future, separately
authorized research may compare 15m, 30m, 1h, 2h, and 4h horizons. Profit is
probabilistic and never guaranteed.

Trade-management research may later define:

- MFE (maximum favorable excursion): best movement after entry within the
  intended horizon.
- MAE (maximum adverse excursion): worst movement after entry within that
  horizon.
- Probability that TP is reached before SL.
- Expected MFE/MAE distributions conditional on asset and market state.

MFE/MAE labels and multi-horizon targets are not implemented in Phase 5.

## Entry, trade quality, and expected edge

`TradeCandidate` combines a timestamped market prediction with direction,
intended horizon, expected costs, uncertainty, and complete lineage. It is not
an order.

`TradeQualityDecision` answers TAKE or REJECT/NO_TRADE using predictions,
model disagreement, regime, fear, liquidity, funding, spread, and expected
costs. The Expected Edge Engine independently determines whether the predicted
distribution clears fees, spread, slippage, funding, impact, and a declared
safety margin. TEST data cannot tune this decision retrospectively.

## Dynamic Take Profit and Stop Loss

Universal percentages such as TP=2% and SL=1% for every asset are forbidden.
Future TP distance may depend on predicted return, MFE distribution, ATR,
realized volatility, regime, liquidity, asset/cluster type, uncertainty,
holding horizon, and only empirically supported market context.

Future SL distance may depend on MAE distribution, ATR, volatility, regime,
liquidity, coin characteristics, and account risk budget. Risk owns the hard
maximum-loss boundary. ML may recommend a tighter exit; it may never widen or
disable the deterministic account-level safety stop.

These are future research contracts only. No TP/SL engine exists in Phase 5.1.

## Trade Management and exits

After entry, a future `TradeManagementDecision` may periodically return HOLD,
FULL_EXIT, PARTIAL_EXIT, TIGHTEN_STOP, or TRAIL_STOP. Inputs may include the
entry/current predictions, PnL, time in trade, volatility, regime, taker flow,
volume, funding, BTC movement, MFE/MAE so far, and liquidity.

An `ExitDecision` may be caused by TP, SL, prediction reversal/weakening,
regime change, rising stress, disappearing buy flow, increasing sell flow, BTC
reversal, deteriorating liquidity, maximum holding time, or a forced Risk
Engine exit. Trade management never overrides a Risk Engine forced exit.

## Regime versus Fear/Euphoria

Regime answers what market structure exists: bull, bear, sideways, high
volatility, crash, or recovery. Fear/Euphoria answers how stressed or euphoric
the market is. They are independent dimensions; a bull regime can coexist with
high fear during a correction.

A future numeric `FearState` may contain fear, euphoria, stress, and panic
probability plus an encoded state. Candidate inputs include BTC volatility and
drawdown, breadth, dispersion, cross-coin correlation, funding extremes,
liquidation/OI stress when trustworthy, volume spikes, BTC momentum, and
market-wide flow. Any external Fear & Greed series is one timestamp-controlled
feature family, never a direct rule such as "index below X means buy." Text is
not direct model input.

No fear, sentiment, news, or external Fear & Greed API is implemented here.

## Liquidity Gate

A positive expected move can still be untradeable. `LiquidityAssessment` may
return PASS, REDUCE, or REJECT plus `liquidity_score`, estimated slippage, and
maximum safe notional. Inputs may include quote volume, trade frequency,
spread, validated depth, estimated impact, order-book imbalance, average trade
size, and slippage estimates. The gate can veto any model signal, especially
for small or new assets.

## Risk, position sizing, and leverage

`RiskDecision` returns REJECT, REDUCE, or APPROVE and overrides every model.
It considers account equity, risk budget, stop distance, volatility,
liquidity, expected edge, uncertainty, correlation, portfolio exposure, and
drawdown.

`PositionSizingDecision` computes notional from the approved risk budget; a
prediction model never directly outputs notional. Leverage is deterministic
risk functionality based on position size, equity, volatility, liquidity,
regime, drawdown, exchange instrument limits, and stricter system limits. High
model probability never implies maximum leverage.

No position sizing, leverage change, account query, or private Binance API is
implemented or authorized in Phase 5.1.

## Portfolio and correlation control

When multiple assets are authorized, the Portfolio Engine owns total exposure,
open-position count, BTC beta, rolling correlation, cluster exposure,
long/short balance, regime, and drawdown. Ten long altcoin positions can be one
large BTC-factor exposure. Future controls may use rolling correlation,
hierarchical clustering, BTC beta, PCA/factors, and cluster exposure limits.
Individual signals never independently consume capital.

## Minimal future component contracts

The following are documentation-level interfaces, not implemented classes:

- `MarketPrediction`: distribution, horizon, uncertainty, timestamps, lineage.
- `MarketState`: causal market context and Regime output.
- `FearState`: numeric fear/euphoria/stress state and availability time.
- `TradeCandidate`: prediction plus expected cost and asset context; no order.
- `TradeQualityDecision`: TAKE or NO_TRADE with reason/version.
- `LiquidityAssessment`: PASS/REDUCE/REJECT, slippage, safe notional.
- `RiskDecision`: APPROVE/REDUCE/REJECT and hard limits.
- `PositionSizingDecision`: risk-derived notional and constraints.
- `TradeManagementDecision`: HOLD/EXIT/PARTIAL/TIGHTEN/TRAIL.
- `ExitDecision`: action, reason, safety priority, and timestamp.

All contracts require causal timestamps, versions, input lineage, and explicit
missing/uncertain states.

## Future research map (not authorized)

- Multi-asset research: global/cluster/per-coin/hybrid benchmarks,
  normalization, and asset context.
- Regime/market state: advanced regime and internal fear/euphoria.
- Prediction research: multi-horizon returns, MFE, MAE, TP-before-SL.
- Meta/trade quality: trade versus NO_TRADE.
- Risk/portfolio: sizing, leverage, correlations, exposure, kill switches.
- Trade management: dynamic TP/SL, trailing, partial and reversal exits.
- Execution: Binance paper, shadow, test environment, then tiny capital only
  after separate explicit gates.

No future phase is authorized by this map.
