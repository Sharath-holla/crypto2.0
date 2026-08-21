# Master Specification

## Objective

Build a modular quantitative cryptocurrency research and trading platform whose eventual objective is robust risk-adjusted performance after realistic costs on unseen data. Binance is the sole canonical market-data and eventual execution venue. Profits are never guaranteed.

## Phase order

Architecture, data, data validation, labels, baselines, Binance market intelligence, structured feature research, backtest foundations, walk-forward validation, multi-asset research, advanced models, ensemble, events, portfolio/risk, Binance paper trading, shadow mode, cloud production, tiny capital, and gradual scaling.

A later phase must not compensate for a broken earlier phase. Each major phase requires an explicit task.

## Completed: Phase 1

Phase 1 delivered reliable BTC historical-data ingestion from Binance:

- `BTCUSDT`, initially at `5m`, with `1m` supported where practical.
- Binance USD-M perpetual futures as the primary research dataset; Spot as a separate secondary/cross-market dataset.
- Explicit Spot and USD-M futures domains with distinct raw paths and source identities.
- UTC, deterministic schemas, precise numeric representation, immutable bronze Parquet.
- Resumable downloads, duplicate-safe writes, checksums, manifests, structured logs, and instrument metadata.
- Basic partition validation for nulls, duplicates, ordering, expected intervals, OHLC relationships, and volumes.
- Tests that do not download years of data.

## Completed: Phase 2

Phase 2 delivered a production data-quality and validation engine:

- typed, versioned PASS/WARN/FAIL results and machine-readable reports;
- canonical schema, timestamp, interval, duplicate, gap, OHLC, volume, outlier, stale-data, source, ingestion, partition, file, and manifest checks;
- cross-partition continuity without loading the complete historical universe at once;
- configurable deterministic quality gates;
- immutable quarantine references for rejected datasets;
- controlled, idempotent Bronze-to-Silver promotion with complete lineage.

## Completed: Phase 3

Phase 3 delivered:

- a versioned, gap-safe 60-minute forward-return label using next-open entry semantics;
- a deliberately small causal feature set shared by training and later inference;
- deterministic Gold datasets with lineage to validated Silver and Bronze;
- chronological train/validation/development-test splits with label-boundary purging;
- zero, historical-mean, momentum, mean-reversion, Ridge, and LightGBM research baselines;
- out-of-sample predictions, predictive metrics, bucket analysis, and local reproducible artifacts.

Phase 3 is complete and final-verified. It is not an economic backtest, makes no trading PnL claim, and added no advanced models, large feature catalogs, risk/leverage logic, Binance execution, live orders, sentiment, or deployment.

## Completed: Phase 4 through Phase 5 Hardening

Phase 4 delivered Binance Market Intelligence, causal structured Feature V2,
Main Model V2, and an OOS backtest foundation. Phase 4.1 delivered official
archive ingestion, multi-year Feature V2.1 core/derivatives datasets, fixed
candidate ablations, one-minute execution references, and cost-aware research.

Phase 5 delivered rolling 24/3/3/3 retrospective walk-forward evaluation for
frozen L0/L5/D0/D2 candidates and locked the prospective holdout at
`2026-08-01T00:00:00Z`. Phase 5 Hardening versions the evidence as
`walkforward_v1_1`: chronological Cal-A/Cal-B ownership, fixed-policy primary
cost stress, separate adaptive stress, deterministic qualification versus
evidence status, reliability suppression, and stronger concentration fields.
It reuses frozen model and TEST-prediction artifacts and introduces no new
label, feature, hyperparameter, or model. No next phase is authorized.

## Completed: Phase 6

Phase 6 added direct official BTCUSDT USD-M 12h/daily context, completed-candle
as-of joins, isolated Feature V3/Label V2 research families, multi-horizon
returns, MFE/MAE, ambiguity-safe barrier labels, fixed chronological probes,
and feature/target scorecards. Its exclusive cutoff is
`2026-07-01T00:00:00Z`; all July and the permanent August holdout remain
unused. It promotes no champion and implements no Phase 7, advanced model,
asset expansion, TP/SL engine, fear engine, risk/leverage, or execution path.
No next phase is authorized.

## Canonical roadmap

Status lock: roadmap items 1 through 6, including Phase 4.1 and Phase 5
Hardening, are complete. Items 7 onward remain future concepts and are not
authorized by their presence in this roadmap.

1. Phase 1 — BTC Data Foundation — done.
2. Phase 2 — Data Quality & Validation — done.
3. Phase 3 — Labels + Baseline ML — done.
4. Phase 4 — Binance Market Intelligence + Advanced Structured Features + Main Model V2 + Backtest Foundation.
5. Phase 5 — Full Walk-Forward Validation + Purging + Embargo + Final Holdout.
6. Phase 6 — Feature Research + Ablations — done.
7. Phase 7 — ETH + Multi-Asset Expansion.
8. Phase 8 — Advanced Temporal Models.
9. Phase 9 — Regime Engine V2.
10. Phase 10 — Ensemble + Meta-Labeling.
11. Phase 11 — Event / Sentiment Engine.
12. Phase 12 — Portfolio + Risk Engine.
13. Phase 13 — Advanced Event-Driven Backtester.
14. Phase 14 — Binance Paper Trading.
15. Phase 15 — Shadow Mode.
16. Phase 16 — Google Cloud Deployment.
17. Phase 17 — Monitoring + Champion/Challenger.
18. Phase 18 — Tiny-Capital Binance Trading.
19. Phase 19 — Gradual Scale.

## Non-negotiable rules

- Use current official documentation for external APIs.
- Never fabricate market data or silently fill missing candles.
- Never silently lose price or volume precision.
- Never commit credentials or large historical datasets.
- Preserve source data and make every processed dataset reproducible.
- Use Binance as the sole market-data and eventual execution venue; preserve explicit Spot/USD-M source identities within Binance.
- Keep internal market, order, fill, position, account, prediction, signal, and risk types exchange-independent. Binance adapters own external API translation.
- Treat features, labels, model outputs, actions, risk parameters, and transaction costs as separate concepts.
- Never let an LLM issue direct trading decisions.
- NO-TRADE is mandatory in any later economic decision layer, and risk must be able to override ML.
- Leverage remains a risk-engine decision, not a predictive feature.
- BTC behavior must not be assumed representative of every coin. Future
  multi-asset research must benchmark global, cluster, per-coin, and hybrid
  approaches with appropriate normalization.
- Prediction, trade quality, expected edge, liquidity, risk, sizing, leverage,
  portfolio, trade management, safety, and execution have separate owners.
- Risk and liquidity may veto any model; ML may never disable a hard risk stop.
- Expected profit is a distribution, never a guarantee. See
  `FUTURE_TRADING_SYSTEM.md` for the locked future contracts.
- No next phase is authorized by this specification.
