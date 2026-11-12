# Crypto 2 Project Guide

## Research architecture features models and the roadmap through Phase 18

Project owner: Sharath N. S.

Documentation snapshot: 23 October 2026

Audience: friends and technical collaborators learning how the project works

Crypto 2.0 studies whether official Binance market data contains repeatable, usable forecasting signals after trading costs. We have built the research foundation, completed several Bitcoin studies, and implemented a multi-asset training framework. We have not established a qualified profitable model, and we have not launched paper or live trading.

This guide explains the standalone project, from the first data pipeline to the planned tiny-capital trading stage. Phases 1 through 6 are completed research. Phase 7 has implemented software and completed data preparation, but its real multi-asset model study remains incomplete and on hold. Phases 8 through 18 describe the intended future system, not completed capabilities or permission to run them.

The main achievement so far is an auditable research process: preserve the data, control what each model could know at each timestamp, compare alternatives fairly, account for costs, and reject unsupported trading claims.

## 1 The project in plain English

### What we are trying to build

The eventual system would observe the market, estimate possible future returns and uncertainty, decide whether an opportunity is worth considering, apply liquidity and risk limits, and only then send an approved instruction to Binance. A forecast alone would never be sufficient authority to trade.

The current system covers the research part of that chain. It downloads and validates historical data, builds features and targets, trains controlled benchmark models in completed earlier studies, evaluates chronological predictions, calibrates signals, and applies a cost-aware NO_TRADE policy. The latest multi-asset framework is implemented but has not completed its real model experiment.

The main research market is Binance USD-M perpetual futures. Bitcoin, represented by BTCUSDT, was the first instrument, with five-minute candles as the main interval. One-minute data is supported where practical. Binance Spot is an explicitly separate secondary market; its records are not merged into futures Bronze data. Binance is also the intended eventual execution venue. Deprecated exchange-specific trading scripts are not part of the active research path.

### What the model actually predicts

The current models are regressors: they estimate a continuous future return rather than a guaranteed price or a buy command. For example, a return estimate of 0.0015 means 0.15 percent, or 15 basis points. It is an uncertain estimate, not a promised gain.

A downstream policy compares the calibrated estimate with assumed round-trip costs and a safety margin. If the estimate does not clear that hurdle, the correct output is NO_TRADE. A future risk engine would be allowed to veto an otherwise eligible signal.

### A short explanation to give a friend

“I am building a quantitative crypto research system using official Binance data. It turns verified historical candles and market context into causal features, tests models using chronological walk-forward validation, and checks whether any signal survives fees, spread, and slippage. We started with Bitcoin and have prepared a 20-coin historical research universe. The research has not yet qualified a model for trading. Temporal models, risk controls, paper trading, and small-capital execution are later gated phases.”

## 2 Current status and the full phase map

The following status separates implementation, completed research, and future design. A completed software phase does not mean that a trading strategy passed qualification.

| Phase | Subject | Status at this snapshot |
| --- | --- | --- |
| 1 | BTC data foundation | Complete |
| 2 | Data quality and validation | Complete |
| 3 | Labels and baseline ML | Complete |
| 4 | Market intelligence and Main Model V2 | Complete including Phase 4.1 |
| 5 | Walk forward validation and holdout protection | Complete including hardening |
| 6 | Feature research and ablations | Complete |
| 7 | ETH and multi asset expansion | Local framework complete; real study incomplete and on hold |
| 8 | Advanced temporal models | Planned |
| 9 | Regime Engine V2 | Planned |
| 10 | Ensemble and meta labeling | Planned |
| 11 | Event and sentiment engine | Planned |
| 12 | Portfolio and risk engine | Planned |
| 13 | Advanced event driven backtester | Planned |
| 14 | Binance paper trading | Planned |
| 15 | Shadow mode | Planned |
| 16 | Google Cloud production deployment | Planned |
| 17 | Monitoring and champion challenger | Planned |
| 18 | Tiny capital Binance trading | Planned and separately gated |

### The recorded Phase 7A research state

The frozen handoff records discovery at 507 of 507 entries, completed acquisition, 60 validated candle checkpoints, and Gold at 7 of 7 checkpoints. Gold contains 138 partitions and 50,352,548 rows. These are data-preparation achievements, not counts of trained models.

Fold 1 is STARTED_NOT_COMPLETE: 0 of 48 model specifications have completed reports, there are zero serialized models from that run, and 0 of 16 folds are complete. Fold 2 never started. Model quality for that experiment is therefore not yet evaluable. These figures come from the historical handoff, not a new inspection of remote storage in this documentation task.

The recorded research VM is terminated and must stay stopped until a separate resume authorization. The historical bottleneck was expensive matrix preparation before estimator fitting, without a durable reusable preparation boundary. Later local remediation implemented an identity-safe prepared-matrix cache and related safeguards. Real Linux verification, real-data equivalence, resource profiling, and an authorized Fold 1 remain outstanding.

### Protected research periods

Phase 6 and Phase 7 use the exclusive research cutoff 2026-07-01T00:00:00Z. July 2026 remains an unused buffer for those studies. August begins 2026-08-01T00:00:00Z and remains permanently LOCKED_UNUSED, with used=false and evaluation_authorized=false.

Phase 5 is an older, separately preserved protocol with the August boundary; its archived development evidence includes early July. That does not permit Phase 6 or Phase 7 to use July. The earlier artifacts are preserved rather than rewritten to pretend that every historical phase used identical date rules.

## 3 Architecture and the reasons behind it

### The implemented research chain

Official Binance archives and public REST data flow into immutable Bronze storage. Deterministic quality and lifecycle checks promote acceptable data to Silver. A historical registry and point-in-time universe determine which instruments are eligible. Gold then holds versioned features, targets, identity fields, and lineage. Chronological folds and prepared matrices feed the benchmark models. Calibration and cost thresholds freeze before test evaluation. Reports separate predictive metrics from research trade economics.

The future continuation is liquidity checks, risk, portfolio allocation, position sizing, leverage control, trade management, paper and shadow observation, and finally separately authorized execution. These downstream components are not implemented live capabilities.

### Data layers

| Layer | What it contains | Why it exists |
| --- | --- | --- |
| Bronze | Immutable source records, source identity, checksums, manifests | Preserve what was actually obtained and make ingestion auditable |
| Silver | Validated records with quality and lifecycle evidence | Stop malformed or unexplained data from becoming trusted research input |
| Gold | Versioned features, labels, timestamps, lineage and schemas | Reproduce exactly what each experiment consumed |
| Prepared matrices | Fold and specification bound arrays and metadata | Avoid repeating expensive conversion without changing scientific meaning |
| Experiment artifacts | Models, predictions, calibration, policies and reports | Audit decisions and compare methods without overwriting prior evidence |

All date ranges are half-open UTC ranges: start is included and end is excluded. Exchange price and volume strings retain exact Decimal representation in the trusted data layers. Derived model arrays use floating-point numbers deliberately; this is different from silently changing the raw market records.

Missing candles are reported. They are never fabricated, interpolated, synthesized, or forward-filled. A gap resets rolling feature state and invalidates targets that require the missing path. Early rolling-window values remain unavailable until the required history exists.

### Technology stack

Python implements the research package. uv and the lockfile manage reproducible dependencies. PyArrow and Parquet provide typed, partitioned storage and columnar scans. NumPy supplies numerical arrays. LightGBM supplies the current tree regressors. Scikit-learn supplies Ridge, scaling, clustering, and supporting statistical machinery. Joblib serializes model bundles. Pydantic validates structured contracts, httpx handles public HTTP access, and TOML and JSON hold configurations and manifests.

Pytest, Ruff, compilation checks, dependency-lock checks, and Git diffs support verification. Bash and PowerShell support operating-system-specific tooling. Ubuntu and Google Compute Engine were used for historical research compute, with persistent storage and object-storage support. This does not mean the planned production deployment phase is complete. Neural frameworks, CatBoost, and XGBoost are not current Phase 7A direct training dependencies.

## 4 Phase 1 BTC Data Foundation

Status: complete.

The first phase established trustworthy historical BTCUSDT data, starting with five-minute candles and supporting one-minute data where practical. It implemented public-data ingestion, canonical instrument and source identities, UTC timestamps, typed Parquet storage, manifests, and checksums.

Ingestion is restartable and duplicate-safe. If a process stops, it should resume from verified work rather than silently duplicate or overwrite partitions. Raw partitions are immutable. A source record has enough identity and provenance to distinguish a futures observation from a Spot observation even if both use the same symbol name.

Initial checks cover nulls, duplicate keys, timestamp order, candle intervals, OHLC consistency, and volume validity. Exact decimals prevent avoidable corruption of exchange values. Checksums reveal whether a supposedly identical artifact has changed.

Why this phase matters: model scores are meaningless if the historical series contains accidental duplicates, missing sections disguised as real data, or inconsistent source identities. The output is an auditable data foundation, not a trading signal.

## 5 Phase 2 Data Quality and Validation

Status: complete.

This phase made validation a versioned decision process rather than a few informal assertions. The quality engine produces PASS, WARN, or FAIL and records the reasons. It checks schemas, timestamps, gaps, duplicates, OHLC relationships, volumes, unusual values, staleness, source identity, file and manifest integrity, and continuity across partitions.

Cross-partition checks use bounded memory so a large historical dataset need not fit entirely into RAM. Failed or suspect inputs can be quarantined with immutable evidence. Promotion into Silver is based on validated lineage and is idempotent: repeating the same verified promotion should not create a different trusted dataset.

A warning does not authorize repair by invention. For example, a missing five-minute candle remains a reported gap; it does not become a candle copied from the previous close. Quality status is visible in reports so later research can fail clearly when required evidence is missing.

Why this phase matters: a model may otherwise learn data-processing errors. Keeping quality decisions separate also makes an experiment explainable when a symbol or period is excluded.

## 6 Phase 3 Labels and Baseline ML

Status: complete.

Phase 3 defined Label V1, a gap-safe 60-minute forward return using the next-open research reference. It built the first Gold training dataset and a small 13-feature causal baseline. Every input is computed from the completed prediction candle or earlier history. Future prices are labels, never features.

The models were zero return, the training historical mean, a fixed momentum predictor, a fixed mean-reversion predictor, Ridge regression, and conservative LightGBM regression. The simple predictors answer whether a sophisticated model is doing more than repeating a trivial rule. Ridge tests a regularized linear relationship; LightGBM tests nonlinear tabular relationships and interactions.

The initial development split is chronological, approximately 70 percent training, 15 percent validation, and 15 percent development test. Rows with labels crossing the next segment boundary are purged. Validation controls LightGBM early stopping. Test does not fit preprocessing, choose features, tune hyperparameters, or stop training.

Outputs include model bundles, exact feature schemas, predictions, MAE, RMSE, R squared, directional accuracy, Pearson and Spearman information coefficients, and prediction buckets. Phase 3 does not calculate an execution-aware trading profit. No fees, positions, drawdown, or profitability claim should be attached to these baseline forecast metrics.

### The original 13 features

The baseline includes return_5m, return_15m, return_30m, return_1h, log_return_5m, candle_range_pct, candle_body_pct, relative_volume, rolling_volatility_1h, rolling_volatility_4h, ema20_distance, ema50_distance, and rsi14. The full vector needs 50 contiguous candles. Warm-up rows and the first 49 rows after a gap are excluded rather than imputed.

## 7 Phase 4 Market Intelligence and Main Model V2

Status: complete, including the Phase 4.1 multi-year extension.

Phase 4 expanded beyond simple returns. Feature V2 adds trend, momentum, volatility, volume, executed taker flow, funding, optional basis and open-interest context, causal regime summaries, and UTC time features. The engine exposes 57 possible columns. The historical July experiment enabled 50: 47 candle-derived and three funding columns. Basis and open interest require genuine, causally aligned coverage; unavailable data is not encoded as zero.

Main Model V2 remains deterministic LightGBM regression with the unchanged original target. A training-period redundancy audit reduces the final enabled vector to 42 columns. This does not modify the old 13-column baseline. Incremental ablations add groups on the same rows so any difference is attributable to a declared feature change rather than a different sample.

The backtest foundation separates predictions from a trading policy and charges assumed fees, spread, and slippage. Weak predictive metrics are not enough to justify trading. The research did not establish a repeatable tradable edge; abstention remains a valid outcome.

### Phase 4 point 1 Multi year research

The extension added official archive history and additive Feature V2.1. Its long-history core has 52 columns. The derivatives-overlap family has 61, adding funding and aligned mark/index/basis context. Open interest is not enabled in that multi-year run because a legitimate shared historical sample is required.

Fixed L0 through L5 core ablations and D0 through D2 derivatives ablations keep rows, target, split, seed, and parameters matched within each family. Training-only redundancy pruning yields later candidate schemas with fewer columns than the full feature generator. Cross-family metrics are descriptive because their historical samples differ.

One-minute references support execution diagnostics where overlap exists; they do not create missing historical order-book data. The results did not establish reliable economic edge. Small selected positive subsets are not sufficient evidence for promotion.

## 8 Phase 5 Full Walk Forward Validation

Status: complete, including a separately versioned hardening pass.

This phase replaced a single development split with rolling calendar windows: 24 months training, three validation, three calibration, three test, stepping forward three months. There are 17 primary folds and 16 derivatives folds. Test windows do not overlap. Actual label-end timestamps are purged at segment boundaries, with a separate 60-minute embargo under this older protocol.

Four candidates were frozen: L0 with 13 features, L5 with 46, D0 with the same 46-column schema on the matched derivatives range, and D2 with 55. All retain the fixed LightGBM parameters rather than an unconstrained tuning search. Reports assess fold, year, regime, drift, uncertainty, cost stress, and concentration as well as pooled scores.

### Why the hardening pass was needed

The hardened walkforward_v1_1 preserves the original walkforward_v1 artifacts. It reused all 66 saved LightGBM bundles and the frozen raw test predictions; no models were retrained. Calibration is split chronologically into Cal-A, which fits and selects identity or linear calibration, and Cal-B, which alone selects the trade threshold after purge and embargo. This separates prediction calibration from policy selection.

Primary cost stress now keeps the exact base trade list fixed while costs rise. An adaptive-policy stress report is separate because changing the selected trades answers a different question. Qualification PASS or FAIL is separated from evidence interpretation such as INCONCLUSIVE. A small sample cannot become convincing simply by receiving a favorable label.

### Hardened retrospective results

| Candidate | Base trades | Average net return per trade | Reliable folds | Qualification |
| --- | --- | --- | --- | --- |
| L0 | 47 | -0.2776 percent | 0 | FAIL |
| L5 | 112 | -0.0080 percent | 1 | FAIL |
| D0 | 9 | -0.2944 percent | 0 | FAIL |
| D2 | 253 | -0.1601 percent | 2 | FAIL |

These are the hardened results, not a mixture with the original version. Pooled evidence remains INCONCLUSIVE, and no candidate meets the separate qualification requirements. All have negative base and 1.5-times fixed-policy expectancy. Three reliable folds are required; none reaches that threshold. Directional accuracy is near 50 percent, and pooled correlations are small.

The conclusion is NO QUALIFIED MODEL. This is a useful research result: the project rejected promotion instead of presenting weak correlation as trading profitability. The August prospective holdout was not evaluated.

## 9 Phase 6 Feature Research and Ablations

Status: complete retrospective research, with no production promotion.

Phase 6 created isolated market_v3_research and label_v2_research families, preserving Feature V1, V2, V2.1 and earlier artifacts. It joins official BTCUSDT USD-M 12-hour and daily candles only after each candle completes. A daily candle cannot be used at the beginning of the day just because its eventual close is known in a historical file.

The full research vector has 127 columns: 61 inherited derivatives-overlap columns plus 22 twelve-hour, 33 daily, seven cross-timeframe, and four market-stress candidates. The research Gold has 651,862 finite rows. Fixed probes use the same 39,224 sampled out-of-sample rows across four chronological folds for controlled comparisons.

The twelve-hour family is KEEP_CANDIDATE, daily is WEAK, and the current cross-timeframe and market-stress groups are REJECT. These judgments refer to the tested formulas, not a claim that all higher-timeframe or stress information is useless. The twelve-hour improvement is modest and not stable across every year or regime. No feature is production-approved.

Target probes examine 15 minutes, 30 minutes, one hour, two hours, and four hours. The first four remain research candidates only; four hours is research-only because stability is weaker. A stronger short-horizon rank correlation does not establish profitability, especially when turnover and costs could be larger.

MFE and MAE describe the best favorable and worst adverse future excursions. Barrier experiments preserve AMBIGUOUS when take-profit and stop-loss ordering cannot be known from the available bars. Validated one-minute data resolves only some overlaps. These are diagnostic labels, not selected production exits or a completed dynamic TP and SL engine.

## 10 Phase 7 ETH and Multi Asset Expansion

Status: local framework implemented; real Phase 7A training incomplete and on hold.

Bitcoin alone cannot establish whether an approach generalizes across coins. Phase 7 adds a historical registry, point-in-time symbol eligibility, normalized multi-asset features, cross-asset context, multiple targets, and global, cluster, per-coin, and hybrid LightGBM benchmarks. The broader framework supports a 15 to 30 symbol pilot. Phase 7A narrows the actual first study to the frozen Core20 primary experiment.

### The historical Core20

BTCUSDT, ETHUSDT, ZRXUSDT, NEOUSDT, FLMUSDT, KNCUSDT, ONTUSDT, BLZUSDT, HNTUSDT, UNIUSDT, TRXUSDT, KSMUSDT, COMPUSDT, IOTAUSDT, STORJUSDT, OMGUSDT, ZECUSDT, FILUSDT, BCHUSDT, and DOGEUSDT.

Selection is anchored as of 1 January 2022, with Bitcoin and Ether anchors, historical eligibility, at least 365 days of history, coverage checks, and trailing 90-day descriptors. Selection is stratified using historical liquidity, volatility, and history rather than future returns or present popularity. Coverage below 0.995 fails the configured gate; coverage below 0.999 is warned.

Delisted instruments remain part of the historical registry. HNT is not removed retroactively, and XPIN is not forced into the sample. Removing historical failures because they are absent today would introduce survivorship bias. An optional EXPANDING universe can add up to ten symbols under the framework, but that expansion is deferred in Phase 7A.

### The training experiment

Phase 7A evaluates the 109-column A6 feature set on four horizons and two target representations. Six architecture/control variants give 48 specifications per fold: four horizons times two target forms times six variants. Sixteen rolling folds are configured. The six variants are G0 balanced, G0 unbalanced, a G0 explicit-symbol-identity control, C0 cluster, P0 per coin, and H0 hybrid.

The broader framework also defines six incremental A0 through A5 ablations at the 60-minute raw target and four independent higher-timeframe controls: BASE, BASE plus 12h, BASE plus 1d, and BASE plus both. Those controls and EXPANDING are deferred in the narrowed first Phase 7A experiment.

### Phase 7 point 1 and Phase 7 point 2 foundations

The repository includes architecture, feature-catalogue, comparison, trial-ledger, and future research contracts. These prepare fair matched comparisons and future extensions. Candidate work includes CatBoost and XGBoost challengers, a tightly budgeted BTC and ETH one-minute context pilot, direct ranking, probability or distribution targets, and competing-risk target schemas. They are disabled, schema-only, or unbenchmarked as recorded; their presence in documentation is not a completed model result.

Interfaces for later temporal models do not mean that a neural model exists. The first task remains completing and evaluating the controlled tree baseline under the unresolved verification and cost gates.

## 11 Phase 8 Advanced Temporal Models

Status: planned and not authorized by this roadmap.

This phase would test whether the sequence of recent market observations adds useful information beyond the engineered tabular features. A tree sees a feature vector at one timestamp; a temporal model can process a causal window of vectors and learn how the pattern develops over time.

The recorded candidate order favors a small causal temporal convolutional network first and a compact PatchTST-style model second. Temporal Fusion Transformer and iTransformer are exploratory alternatives, subject to capacity and compute controls. No TCN, RNN, Transformer, or PatchTST model has been trained in the current Phase 7A study. A very large model is not a requirement.

A future experiment would need fixed lookback windows, masks for missing or newly listed histories, strictly past-only normalization, bounded batches, reproducible seeds, and the same target and out-of-sample rows as the tree control. Future rows must never enter a sequence window or its scaling statistics.

Promotion would require incremental matched-row evidence, stable economics, and resource costs justified by the measured improvement. Lower training loss alone would not be a reason to replace LightGBM.

## 12 Phase 9 Regime Engine V2

Status: planned.

A regime engine would describe the market environment, such as trending or ranging behavior, high or low volatility, and liquidity stress. Phase 4 already has causal regime summaries, and Phase 6 has stress research. Neither is a completed Regime Engine V2.

The intended starting point is observable, causal market measurements. More complex state models, such as hidden Markov or Markov-switching challengers, would need a separate experiment. Their fitted parameters must come from training history only; retrospective full-sample state smoothing would reveal future information.

Regime and fear are different concepts. A rising market can still be unstable or stressed. A future fear or stress estimate would need its own definition, availability timestamps, validation, and boundaries. Current stress formulas are not a finished fear engine.

Outputs would be timestamped regime states or probabilities with uncertainty and data-quality status. Regime conditioning would have to improve evaluation on unseen periods without becoming a device for selecting favorable historical slices.

## 13 Phase 10 Ensemble and Meta Labeling

Status: planned.

An ensemble would combine genuinely complementary models. Meta-labeling would estimate whether a candidate opportunity deserves to be taken, rather than asking the return model to perform every decision itself. The future chain separates return prediction, opportunity quality, expected edge after costs, and NO_TRADE.

Stacking must use out-of-fold predictions. Training a second model on first-stage predictions generated on the same rows used to fit the first model would make the second stage learn an unrealistically easy problem. A shallow, controlled ensemble is the intended research starting point; adding models without diversity does not automatically add information.

Possible outputs include calibrated probability, a return distribution, expected net edge, or a take versus abstain score. The final labels and acceptance criteria are not frozen production choices. Probability work would need log loss, Brier score, and calibration checks; quantile work would need pinball loss and coverage. Those are future metric families, not current Phase 7A regression results.

Any improvement must survive the same chronological, cost, sample-size, and concentration requirements as the underlying models. Test data cannot train the ensemble or choose a threshold.

## 14 Phase 11 Event and Sentiment Engine

Status: planned, with only a small separate public-context foundation present.

This phase would research whether timestamped events or sentiment add value beyond market data. Historical events require several clocks: when the event happened, when it was published, when the system received it, and whether it was revised. A retrospective article timestamp alone may not prove the information was available to a live decision process.

The existing small context foundation can collect public Alternative.me Fear and Greed and Binance USD-M open interest only through a separate explicit context-network guard. Both feature families are disabled from Phase 7 training. Historical Fear and Greed knowledge time is unverified, and open interest is recent or forward-only. They cannot be assumed to supply a clean multi-year sentiment dataset.

CryptoPanic, Arkham, and Reddit integrations are not implemented. Future sources would need licensing checks, deduplication, entity mapping, revision handling, and causal joins before experiments. An LLM could help turn text into a structured, timestamped record, but would not receive unrestricted authority to submit trades.

Sentiment must demonstrate incremental matched-row value after accounting for delayed publication, outages, and realistic costs. It is not a shortcut around the unfinished baseline research.

## 15 Phase 12 Portfolio and Risk Engine

Status: planned and not part of the current authorized research implementation.

A future risk engine would decide whether a model opportunity is safe enough to consider and how much exposure is allowed. It would own position size, leverage, portfolio exposure, concentration, drawdown responses, hard loss limits, and emergency vetoes. The predictor would not own these controls.

Portfolio construction must consider correlated exposures. Ten long altcoin positions can be one large Bitcoin-sensitive bet rather than ten independent risks. BTC beta, cluster concentration, common market shocks, and liquidity would need to be considered alongside individual forecasts.

Leverage is a risk decision, not a predictive feature. A future liquidity layer could return PASS, REDUCE, or REJECT using trustworthy volume, trade, spread, and depth evidence. The current candle-based taker-flow and activity features are not a substitute for historical order-book depth or executable capacity.

Hard risk stops must remain active even when a model is confident. Exact capital limits, leverage caps, drawdown thresholds, and sizing formulas require a separately approved specification; there are no final numeric production limits to report today.

## 16 Phase 13 Advanced Event Driven Backtester

Status: planned.

The current bar-level research economics cannot reproduce a real exchange. An event-driven backtester would model the sequence of market updates, decisions, orders, fills, positions, costs, and account changes. It would test the interaction between prediction, liquidity, risk, and execution under one event clock.

Required work includes order and cancellation latency, partial fills, tick and lot rules, exchange rejections, funding payments, margin and liquidation mechanics where relevant, position accounting, concurrent exposures, and reconciliation. Queue position and market impact require credible data and models rather than optimistic defaults.

Bar-based take-profit and stop-loss ordering is especially dangerous. When both levels are touched inside an unresolved bar, the simulator must preserve ambiguity or use a documented conservative rule; it cannot choose the favorable order silently. Phase 6 barrier labels establish this caution but do not supply the full simulator.

The backtester would need deterministic replay, an auditable event ledger, unit and scenario tests, and comparisons with later paper observations. Any new simulation assumption must be visible in reports. More elaborate simulation does not repair a predictive model with no reliable edge.

## 17 Phase 14 Binance Paper Trading

Status: planned and not running.

Paper trading would observe a live data stream and run the complete decision pipeline without risking real capital. Its purpose is to detect operational differences between historical research and an online process: delayed bars, missing updates, stale features, model loading, clock alignment, state transitions, and reconciliation.

The model and policy must be frozen before the paper observation period. Changing the strategy after every disappointing day would turn the period into development rather than an honest forward test. Decisions, rejected signals, simulated orders, fills, costs, and data-quality failures should all be logged.

The precise paper environment and fill methodology still need selection. Simulated fills or test environments do not establish real queue priority, capacity, or execution economics. Readiness would require an approved risk design, validated backtester assumptions, repeatable state recovery, and sufficient observation across varied conditions.

Paper trading is not current authorization to access an account or run legacy trading scripts.

## 18 Phase 15 Shadow Mode

Status: planned.

Shadow mode would run production-shaped decisions alongside live market observation while withholding real order submission. It focuses on whether the system behaves correctly under realistic operating conditions, independently of whether a backtest looks attractive.

The intended checks include signal timing, feed interruptions, feature freshness, risk vetoes, model-version consistency, restart behavior, and discrepancies between expected and observable execution conditions. A read-only shadow process and paper simulation can overlap operationally, but their reports must state what was actually observed and what was only simulated.

An immutable decision ledger would make it possible to reconstruct why an opportunity was accepted, reduced, or rejected. A stale or corrupt input should produce a safe abstention rather than an order built from invented data.

The duration, pass criteria, and access arrangement are not selected today. Shadow results would be another gate before capital exposure, not automatic permission for it.

## 19 Phase 16 Google Cloud Deployment

Status: planned production deployment; historical research compute is a separate completed activity.

The project previously used cloud compute for data and research preparation. Phase 16 means deploying an approved operational system, not merely having used a virtual machine. The current project is on hold, and its historical research VM is recorded as stopped.

A future deployment would need reproducible environments, least-privilege identities, secret management, isolated services, artifact integrity checks, durable state, restart procedures, backups, observability, and cost controls. Development, research, and any eventual order-capable environment should have separate boundaries.

Resource choices must follow measurement. Before any research restart, the owner must approve a fresh cost and deadline contract, and the missing real-data preparation and Linux gates must be completed. A cloud plan does not permit starting, resizing, or creating resources.

The production architecture, service layout, infrastructure sizes, and recurring spend are not finalized. They should be chosen after a model and operating requirements are justified rather than presented as existing features.

## 20 Phase 17 Monitoring and Champion Challenger

Status: planned full production capability.

Current logs, manifests, training events, checkpoints, and research supervisors support debugging and audit. They are not a completed production monitoring and champion-challenger system.

A future monitor would track data freshness, missingness, schema drift, feature drift, prediction drift, realized error, policy behavior, risk actions, execution quality, resource use, and operational incidents. It should distinguish a feed failure from genuine market change and a forecasting issue from an execution issue.

A champion would be a model that passed the frozen promotion protocol; a challenger would be evaluated without receiving privileged future information. No current model holds that champion status. Automatic replacement based on a short favorable period would create selection bias and operational risk.

The future system needs versioned approvals, rollback, reproducible reports, and retained failed trials. Multiple-comparison methods and a research trial ledger can reduce overstatement when many alternatives are explored, but cannot rescue a contaminated test set.

## 21 Phase 18 Tiny Capital Binance Trading

Status: planned, not authorized, and not running.

This is the first roadmap stage that would risk real capital. It would require a separately approved small capital allocation and strict exposure limits after model qualification, realistic economics, risk engineering, paper observation, shadow operation, and deployment checks.

The purpose would be to measure actual operational and execution behavior with tightly limited consequences, not to assume that a backtest scales directly into income. Fill quality, fees, funding, rejections, reconciliation, downtime, and emergency shutdown would matter as much as forecast scores.

Any such phase must preserve hard risk vetoes, account and venue reconciliation, an auditable order trail, manual shutdown, and clear stop conditions. Precise capital, leverage, instruments, duration, and acceptance thresholds remain unapproved. No fixed monthly profit or accuracy target is guaranteed.

The canonical roadmap has a later Phase 19 for gradual scaling. It is outside this guide's requested scope and would require additional evidence and authorization even if Phase 18 succeeded.

## 22 The complete current feature catalogue

### How the versions relate

Feature versions are separate research families, not a single ever-growing production model. V1 has 13 columns. V2 exposes 57 candidates, with 50 enabled in its historical experiment and 42 in its pruned Main Model V2. V2.1 generates 52 core or 61 derivatives-overlap columns; frozen Phase 5 candidates use selected 13, 46, or 55-column schemas. Phase 6 has a separate 127-column research vector.

The current Phase 7 A6 model schema has exactly 109 columns: 54 native five-minute, coin-context, anchor, and market columns plus 22 completed twelve-hour columns and 33 completed daily columns. The numbers below describe that schema, not all columns physically stored in Gold.

Gold also stores timestamps, targets, horizon identifiers, lineage, membership hashes, and source-helper fields. These do not automatically become features. In particular, entry prices, future returns, future volatility, MFE, MAE, and label-end timestamps must not enter a model input vector.

### Native return features

Five columns: return_5m, return_15m, return_30m, return_1h, return_4h.

They compare the latest completed close with closes 1, 3, 6, 12, and 48 five-minute rows earlier. They describe recent direction and magnitude at several scales. All required rows must be contiguous. These are past returns; the future target is stored separately.

### Native candle and trend features

Four columns: range_pct, body_pct, atr14_pct, ema20_distance_pct.

Range and body describe the completed candle's geometry. ATR14 measures recent true range relative to price. EMA20 distance measures price relative to its causal exponential average. Normalized values make the measurements more comparable across differently priced coins. Warm-up and valid denominators are mandatory.

### Native volatility features

Three columns: realized_volatility_1h, daily_volatility, seven_day_volatility.

These use trailing sample standard deviations of five-minute log returns over 12, 288, and 2,016 causal rows. They describe recent variability, not future risk known with certainty. The daily scale used to normalize targets is frozen at feature time.

### Native activity features

Three columns: relative_quote_volume, volume_zscore, trade_count_zscore.

Causal trailing statistics over 2,016 rows compare present activity with recent history. A z-score measures distance from a trailing mean in trailing standard-deviation units. Activity may help characterize market conditions, but it is not a direct measurement of order-book depth or fill capacity.

### Native executed taker flow features

Three columns: taker_buy_share, taker_sell_share, taker_flow_imbalance.

These use exchange candle taker-buy quote volume and total quote volume. Sell volume is the valid complement. Buy share, sell share, and their difference describe aggressive executed flow. They are related representations, not three independent sources of information. They do not reconstruct resting buy and sell orders.

### Native volatility normalized returns

Three columns: return_5m_over_ex_ante_vol, return_1h_over_daily_vol, return_4h_over_7d_vol.

These divide past returns by causal volatility scales so the model can distinguish a large unusual move from a move typical for a volatile instrument. Zero or invalid denominators stay unavailable. No future-window volatility is allowed.

### Native derivative context

Three columns: funding_zscore, mark_index_basis, contract_mark_basis.

Funding context describes the historically available funding observation relative to its causal distribution. Basis describes deviations among contract, mark, and index prices. Funding uses an as-of maximum age of 24 hours; mark and index context use a five-minute maximum age under this Phase 7 feature contract. Missing or stale sources remain null. These settings belong to this version and must not be confused with earlier-version age rules.

### Coin lifecycle features

Two columns: listing_age_days, history_length_days.

They measure days from verified availability and usable history. Each row must lie inside the instrument's verified lifecycle. These features let research test whether behavior differs with instrument maturity without pretending that newly listed coins have years of data.

### Cross sectional rank features

Three columns: trailing_liquidity_percentile, trailing_volatility_percentile, trade_intensity_percentile.

At each timestamp, these compare a coin with the frozen active symbols for that fold. They are recomputed after causal membership is fixed. Ranking against the acquisition union would leak a different universe into the experiment and is not allowed as model-ready context.

### Coin and anchor relationship features

Six columns: btc_beta, btc_correlation, eth_correlation, relative_strength_vs_btc, relative_strength_vs_eth, beta_adjusted_residual_return.

Exact-time anchor joins and causal 2,016-row pair statistics describe market sensitivity, co-movement, and performance relative to Bitcoin or Ether. Beta-adjusted residual return separates the recent move from the part associated with the Bitcoin relationship. Missing anchor observations are not forward-filled.

### Bitcoin context features

Seven columns: btc_return_5m, btc_return_15m, btc_return_30m, btc_return_1h, btc_return_4h, btc_volatility_1h, btc_taker_flow_imbalance.

These copy Bitcoin context at the exact feature timestamp. They let a model interpret a coin move alongside the market anchor rather than in isolation. Missing Bitcoin context remains missing.

### Ether context features

Four columns: eth_return_5m, eth_return_1h, eth_return_4h, eth_volatility_1h.

These add a second market anchor using exact timestamps. They do not assume Ether and Bitcoin provide identical information.

### Market breadth features

Eight columns: market_mean_return, market_median_return, market_pct_positive, market_pct_negative, market_return_dispersion, market_median_volatility, market_median_taker_flow_imbalance, market_member_count.

These summarize the frozen fold-active universe at each timestamp. They measure broad direction, disagreement, variability, aggregate flow, and the size of the contributing group. Acquisition-union previews are tagged separately and forbidden as model-ready context. The membership hash is retained so an aggregate cannot silently change meaning between runs.

### The 22 completed twelve hour columns

The following are the exact model column names. Every value requires a completed source candle and valid causal history.

- htf_12h_return
- htf_12h_log_return
- htf_12h_range_pct
- htf_12h_body_ratio
- htf_12h_upper_wick_ratio
- htf_12h_lower_wick_ratio
- htf_12h_close_location
- htf_12h_ema20_distance
- htf_12h_ema20_50_spread
- htf_12h_ema20_slope_3bar
- htf_12h_rsi14
- htf_12h_roc4
- htf_12h_realized_vol_1d
- htf_12h_realized_vol_3d
- htf_12h_realized_vol_7d
- htf_12h_atr14_pct
- htf_12h_relative_quote_volume
- htf_12h_volume_zscore
- htf_12h_trade_count_intensity
- htf_12h_taker_buy_share
- htf_12h_taker_sell_share
- htf_12h_taker_flow_imbalance

These describe higher-timeframe candle shape, trend, momentum, volatility, activity, and executed flow. Return and log return measure one completed bar. Body, wick, and close-location ratios normalize candle geometry by its range. ROC4 is four twelve-hour bars of rate of change. EMA slope uses three bars. The 1d, 3d, and 7d volatility windows contain 2, 6, and 14 twelve-hour observations. ATR14 is normalized by price. Relative quote volume and trade intensity use 20-bar trailing means; volume z-score uses 60 bars.

### The 33 completed daily columns

- htf_1d_return
- htf_1d_log_return
- htf_1d_range_pct
- htf_1d_body_ratio
- htf_1d_upper_wick_ratio
- htf_1d_lower_wick_ratio
- htf_1d_close_location
- htf_1d_ema20_distance
- htf_1d_ema50_distance
- htf_1d_ema100_distance
- htf_1d_ema200_distance
- htf_1d_ema20_50_spread
- htf_1d_ema50_200_spread
- htf_1d_ema20_slope_5d
- htf_1d_rsi14
- htf_1d_roc7
- htf_1d_realized_vol_3d
- htf_1d_realized_vol_7d
- htf_1d_realized_vol_30d
- htf_1d_atr14_pct
- htf_1d_volatility_zscore
- htf_1d_volatility_of_volatility
- htf_1d_relative_quote_volume
- htf_1d_volume_zscore
- htf_1d_trade_count_intensity
- htf_1d_taker_buy_share
- htf_1d_taker_sell_share
- htf_1d_taker_flow_imbalance
- htf_1d_distance_from_20d_high
- htf_1d_distance_from_20d_low
- htf_1d_distance_from_60d_high
- htf_1d_distance_from_60d_low
- htf_1d_drawdown_from_60d_high

Daily context adds longer trend distances, trend spreads, seven-day momentum, 3/7/30-day volatility, volatility normalization, and distances from historical extrema. The volatility z-score compares 30-day volatility with its trailing 180-day distribution; volatility of volatility measures its trailing 30-day variability. EMA200 and long volatility statistics intentionally require substantial history. The high-distance and drawdown representations can be redundant; inclusion is a research schema choice, not evidence that each is independently useful.

### Higher timeframe timing and unavailable values

A higher-timeframe candle becomes available at its opening time plus its full interval. It can join a five-minute row only when that availability time is no later than feature time and maximum-age rules are satisfied. Twelve-hour and daily streams align independently; missing one must not erase a valid observation in the other. A selected model row still needs all of that model's required inputs to be finite.

The native count is 24 base return/candle/volatility/activity/taker/normalized/derivative columns plus 11 coin-context columns, 11 Bitcoin and Ether columns, and eight market columns. That equals 54; adding 22 and 33 gives 109.

## 23 Targets timing and model training

### Current targets and the latency convention

Phase 7 uses multiasset_targets_v2 with 15, 30, 60, and 120-minute horizons. Each horizon has raw_future_return and normalized_future_return. The latter divides raw return by the larger of the absolute feature-time daily volatility and 0.00000001. Normalized predictions are multiplied by that same stored ex-ante scale before raw-return economics.

For source candle i, feature time is open[i+1], after the source candle completes. The current target includes one additional full five-minute latency bar, so the entry reference is open[i+2]. Label end is entry time plus the selected horizon. Future return compares the open at label end with the entry open.

For example, a source bar opening at 10:00 and closing at 10:05 supplies features at 10:05. The Phase 7 entry reference is 10:10; a 60-minute target ends at 11:10. This is the current label contract, not proof of a real fill. Earlier label versions used a next-open convention without this additional bar and remain separate preserved versions.

The full future path must exist without gaps through the endpoint. Missing entry, missing endpoint, delisting, missing path rows, or a label end at or beyond the exclusive cutoff invalidates the label. NO_TRADE is not a label class in the current return targets; it is a later policy decision.

### The four model architectures

| Architecture | What it learns | Why compare it |
| --- | --- | --- |
| G0 global | One pooled return model across eligible coins | Share information and test a common normalized relationship |
| C0 cluster | Separate models for training defined groups of similar coins | Allow group behavior without requiring a full model for every coin |
| P0 per coin | Separate model for each sufficiently supported coin | Test whether pooled learning hides coin specific relationships |
| H0 hybrid | Global prediction plus supported coin or cluster residual correction | Share a global foundation with controlled local adaptation |

All four use LightGBMRegressor rather than four different neural networks. G0 has balanced, unbalanced, and explicit-symbol-identity controls. Balanced weighting prevents a large-history symbol from dominating simply because it contributes more rows. Explicit symbol identity tests whether memorizing coin identity helps or harms the matched result.

C0 fits StandardScaler and K-means on training descriptors only; the default cluster count is four. P0 requires at least 20,000 training rows, 2,000 validation rows, and 2,000 Cal-A rows per eligible estimator. H0 uses validation to control residual structure and falls back from supported symbol correction to cluster correction to the global model. Unsupported coverage is reported rather than silently hidden. Compatible G0 work may be reused by H0 only when all scientific identities match.

### Frozen LightGBM configuration

The current configuration uses seed 42, learning rate 0.02, at most 500 estimators, 31 leaves, max depth -1, minimum child samples 100, subsample 0.9, column sample 0.9, L1 regularization 0.1, L2 regularization 1.0, and validation early stopping after 50 non-improving rounds. CPU fitting is deterministic under the configured environment and thread controls. GPU or neural training is not established by this setup.

These conservative fixed settings limit the degrees of freedom in comparison. No test-driven hyperparameter search is permitted. Deterministic seeds help reproduction but do not replace data, code, package, schema, and environment identities.

### Who may learn from which period

| Segment | Permitted use | Forbidden use |
| --- | --- | --- |
| TRAIN | Fit weights, scaling, clusters, symbol levels and historical cost tiers | Use later outcomes to redefine its universe or transformations |
| Validation | Early stopping and declared hybrid residual decisions | Become the final evidence of generalization |
| Cal A | Fit and select identity or linear calibration | Choose the economic trade threshold |
| Cal B | Select the frozen cost aware threshold policy | Fit return models or inspect TEST for selection |
| TEST | Evaluate the fully frozen research decision chain | Choose models, features, thresholds or promotion rules |

The sixteen Phase 7 folds use calendar-defined rolling windows over the research range from 1 January 2020 to the exclusive 1 July 2026 boundary. Geometry is 24 months TRAIN, three Validation, three Calibration, three TEST, and a three-month step. The calibration interval splits at its chronological midpoint into Cal-A and Cal-B.

Actual label-end timestamps are purged: a retained label must end strictly before the next segment begins. A separate 120-minute embargo applies under the Phase 7 protocol. This prevents overlapping future outcomes from connecting supposedly separate segments. Random train-test shuffling is inappropriate here because adjacent market observations and overlapping forward targets are dependent.

### What appears during training

The locally remediated training path emits structured JSONL events while a model is actually fitting, with native loss, MAE, RMSE, and directional accuracy for TRAIN and Validation. The default reporting interval is 25 rounds; PHASE7_METRICS_EVERY=1 requests each round. Validation native L2 remains the first early-stopping metric so added display metrics do not silently change model selection.

Directional accuracy is a regression diagnostic measuring whether the predicted sign matches the realized sign. It is not a classification accuracy guarantee or a profit measure. F1, AUC, and probability calibration are not appropriate current metrics unless a separately defined classification or probability task is introduced. TEST is not displayed as a fitting metric because training must not inspect it.

Preparation, cache, fitting, and failure events should be distinguishable. A sanitized FIT_FAILED record must not leak sensitive exception text; the original exception is retained for debugging. The implementation is locally tested, but actual full-scale Phase 7 training observations are still pending.

## 24 Evaluation costs and the meaning of evidence

### Predictive metrics

MAE measures average absolute return error. RMSE gives larger mistakes more weight. R squared compares squared error with a constant-reference forecast; a negative value means worse than that reference on the evaluated sample. Directional accuracy measures sign agreement. Pearson IC measures linear association between predicted and realized returns; Spearman IC measures rank association.

Phase 7 also requires pooled micro metrics, equal-symbol macro metrics, per-coin and per-cluster views, lifecycle slices, timestamp cross-sectional IC, coverage, and concentration. A pooled metric can be dominated by one heavily represented coin, while a macro metric weights symbols equally. Both are useful and neither should hide exclusions.

Moving-block statistical intervals account for time dependence better than treating every overlapping target as an independent observation. Paired identical-row comparisons help isolate the declared model or feature change. Feature importance and permutation importance describe model behavior; they do not prove causality or economic usefulness.

### Research cost assumptions

| Liquidity tier | Fee per side | Spread total | Slippage per side | Round trip total |
| --- | --- | --- | --- | --- |
| High | 4 bps | 1 bp | 1 bp | 11 bps |
| Medium | 4 bps | 2 bps | 2 bps | 14 bps |
| Lower | 4 bps | 4 bps | 4 bps | 20 bps |

One basis point is 0.01 percent. These are frozen research assumptions, not a current Binance fee quotation or reconstructed realized execution costs. Training history defines the tiers. Cal-B selects among 2, 4, 6, 8, and 10 bps of additional edge. A group without at least 30 executable, non-overlapping Cal-B trades remains NO_TRADE.

As an illustration, an estimated 15 bps return with an 11 bps round-trip assumption and a 6 bps threshold does not pass the 17 bps hurdle. This is only an arithmetic example, not a real model prediction or trade recommendation.

TEST policy trades do not overlap within a symbol until its active horizon expires. Primary stress uses the same trade identities and directions at 1.0, 1.25, 1.5, and 2.0 times cost. Secondary adaptive stress lets the frozen policy see stressed costs without retuning its threshold and reports the resulting different trade set separately.

### What current economics still omit

Funding is a causal feature, but Phase 7 economics do not deduct funding payments. They also omit partial fills, order-book queue and impact, tick and lot rounding, rejects, margin and liquidation mechanics, precise network and order latency, portfolio concurrency, and venue reconciliation.

Current Phase 7 trade reports are research diagnostics, not a complete account simulation or a production equity curve. Summed per-trade returns are not an investor's compounded portfolio return. Future roadmap references to Sharpe, Sortino, sophisticated capacity, or full portfolio drawdown must not be presented as completed Phase 7A results.

### The promotion decision

A model needs adequate sample size, broad fold and instrument support, positive and robust net economics, acceptable concentration, and the separately frozen qualification criteria. A high training score, a small profitable subgroup, or one positive correlation does not satisfy those conditions. Phase 5 has no qualified model; Phase 6 has research candidates only; the incomplete Phase 7A model study is not yet evaluable.

## 25 Engineering safeguards and recent debugging

### Protecting scientific identity

Data, ordered feature schemas, targets, universe membership, fold boundaries, model settings, source versions, dependencies, and compatible runtime identities bind reusable artifacts. A file existing on disk is not enough proof that it belongs to the current experiment. Incompatible caches or resume artifacts must fail closed rather than be relabeled to look current.

Prepared-matrix caching is content-addressed and uses an atomic publication boundary. Alignment checks compare feature, target, and symbol arrays with Arrow source values in bounded chunks of 65,536 rows. Valid file hashes alone do not prove semantic row alignment. Validation before publication protects an existing valid artifact from an invalid rebuild. Memory-map cleanup matters on Windows because live references can prevent safe file replacement or removal.

Bounded independent estimator workers and per-estimator thread budgets avoid CPU oversubscription. Source scans and finite filtering use Arrow-native operations where practical. Compatible prepared inputs can be shared across architectures, but only when their scientific meaning is identical. These are engineering efficiency measures, not evidence of improved predictive skill.

### The major causal universe bug and its correction

The October 23 local review found that a future data gap later in Validation, Calibration, or TEST could influence whether a coin was admitted to the earlier TRAIN universe. Even though the gap concerned data quality, using future quality to change a past universe is look-ahead bias.

The correction restricts the membership gap gate to fully elapsed required TRAIN history. Future metadata cannot change active coins or their membership hash. Gap ordering and duplicate descriptions cannot change equivalent results. New membership artifacts declare TRAIN_HISTORY_ONLY_V2; legacy artifacts retain their old policy meaning and hashes rather than being silently promoted.

An active coin's unacceptable post-TRAIN gap now blocks the whole fold as a data error. It does not quietly remove that coin based on future evidence, mark an incomplete specification complete, or manufacture clean observations. This preserves the causal universe and makes a broken evaluation visible.

### Other local hardening

Cal-B threshold selection now counts executable non-overlapping trades rather than overlapping candidate rows. Training diagnostics preserve early-stopping semantics and exclude TEST. Dependency and environment identities bind resume and cache compatibility. One-fold benchmark descriptors are scoped to one fold rather than all sixteen. CLI preflight, RAM gates, read-only cache behavior, no-write checks, and output-root protection have regression coverage.

These changes remain local remediation. They do not establish that the stopped cloud copy has been updated, that a real Linux run passed, or that any model qualified.

### Latest recorded verification

The latest local code verification report records 886 passed tests, five Windows skips, zero failures or errors, and one non-fatal joblib physical-core discovery warning. Ruff lint and format checked 252 files; compilation, the offline dependency lock check, and Git whitespace checks passed. The five skips are Linux and Bash log-rotation checks, not evidence of a passing Linux gate.

These results belong to the October 23 remediation snapshot. This documentation task did not rerun scientific training, inspect remote data, open protected periods, or revalidate every external artifact. Passing software tests reduces known implementation risk; it does not prove that all bugs are gone or that the strategy makes money.

## 26 What must happen before further research

The project remains on hold. Existing discovery, acquisition, the 60 candle checkpoints, and Gold should be reused only after identity and checksum validation. No expensive local multi-symbol workload or cloud resource action is authorized by this guide.

Before the next real Fold 1, the required sequence is to verify the frozen state and protected dates, inventory the checkpoints, complete the full Linux verification gate, profile real Gold scans and matrix preparation, prove cached versus uncached scientific equivalence, and measure resource needs. The owner must then approve a fresh cost and deadline contract before compute starts.

Only one Fold 1 should be authorized and measured before deciding whether folds 2 through 16 proceed. Completion and qualification are separate decisions. No August evaluation is authorized, and July remains unused for the current study. Future temporal models, risk automation, account access, paper trading, and live orders need separate approvals.

## 27 Strengths limitations and honest project claims

### What is strong today

The project preserves raw data, explicit lineage, exact source identity, gap evidence, and historical research artifacts. Feature and label versions are separate. Temporal availability, label purging, calibration ownership, causal universes, cost-aware abstention, fixed-policy stress, and qualification gates make the experiments more defensible than a randomly shuffled price-prediction notebook.

The design compares simple baselines with nonlinear models before adding complexity. It preserves negative and inconclusive findings. It also distinguishes local implementation success from full-scale experimental completion, which prevents test counts or data volume from becoming substitute claims of trading performance.

### What remains weak or unknown

Earlier studies do not establish stable net edge. Phase 7A has no completed real model result. Historical liquidity and lifecycle evidence can be incomplete. Selected features are often correlated, and their meaning may drift. Current trading costs are assumptions and several real exchange effects are omitted. The protected prospective holdout has not been used and cannot be claimed as a passing external test.

The real-data cache boundary and Linux execution behavior need verification. Research runtime, memory, cloud cost, multi-coin generalization, and subsequent production capacity remain measurement questions. Advanced models and sentiment may add complexity without value. None is an automatic solution to weak economic evidence.

### Claims we can and cannot make

We can say that the project implements an auditable quantitative research pipeline, has completed Bitcoin baseline and walk-forward studies, has built a point-in-time multi-asset framework, and has prepared a large historical Gold dataset. We can describe the future trading architecture as a roadmap.

We cannot say that all 18 phases are built, that a transformer is already trained, that 50 million rows produced a qualified strategy, that 0 of 48 reports proves bad model performance, or that a fixed return, win rate, or income is guaranteed. There is currently no approved trading champion.

## 28 Glossary

| Term | Meaning in this project |
| --- | --- |
| Candle or bar | OHLC prices and trading activity over a fixed interval |
| Causal feature | A value computed only from information available by decision time |
| Target or label | The future outcome a research model attempts to predict |
| Leakage | Future or evaluation information influencing a prior decision |
| Survivorship bias | Selecting history using only instruments that survived until today |
| Point in time universe | Instruments selected using evidence available at the historical selection time |
| Purge | Remove observations whose future label reaches the next segment |
| Embargo | Additional separation around a chronological boundary |
| OOS | Out of sample relative to the frozen fitting and selection process |
| Calibration | Adjust the relationship between model scores and realized outcomes using its assigned segment |
| IC | Information coefficient or association between forecasts and future returns |
| Ablation | Controlled addition or removal of a declared feature or model component |
| MFE | Maximum favorable excursion along a future price path |
| MAE excursion | Maximum adverse excursion along a future price path |
| MAE error | Mean absolute prediction error; different from adverse excursion |
| Basis point | One hundredth of one percent |
| NO_TRADE | Abstain when the frozen decision policy does not justify a trade |
| Checkpoint | Verified reusable artifact with identity and completeness evidence |
| Champion | A model that passed an approved promotion protocol; none exists today |

## 29 Documentation and code reference map

The repository is https://github.com/Sharath-holla/crypto2.0. The snapshot described here also includes locally verified remediation that may not yet be published to the remote repository. Historical reports keep their original versions and results. When an old status paragraph conflicts with the latest remediation, use the newer scoped record rather than rewriting old evidence.

The following repository-relative references provide deeper technical detail without exposing private infrastructure identifiers or credentials.

- PROJECT_CONTEXT.md and docs/PROJECT_HANDOFF/00_START_HERE.md: current hold, scientific contract, and handoff entry.
- docs/MASTER_SPEC.md: canonical phase order and boundaries.
- docs/ARCHITECTURE.md and docs/DATA_DICTIONARY.md: system and data contracts.
- docs/FEATURES.md, docs/LABELS.md, docs/MODELING.md, and docs/BACKTESTING.md: earlier feature, target, model, and evaluation definitions.
- docs/PHASE5_RESULT.md and docs/PHASE5_HARDENING_VERIFICATION.md: original and hardened walk-forward evidence.
- docs/PHASE6_FEATURE_RESEARCH.md and docs/PHASE6_TARGET_RESEARCH.md: fixed feature and target research results.
- docs/PROJECT_HANDOFF/06_UNIVERSE_AND_CORE20.md: historical selection and survivorship protection.
- docs/PROJECT_HANDOFF/07_FEATURE_ENGINEERING.md and docs/PHASE7_1_FEATURE_CATALOG.md: exact current feature names and formula-level catalogue.
- docs/PROJECT_HANDOFF/08_TARGETS_AND_LABELS.md through 13_BACKTEST_AND_ECONOMICS.md: current labels, architectures, experiment, evaluation, and research costs.
- docs/PHASE7_2_EXPERIMENT_ROADMAP.md and docs/PHASE7_2_RESEARCH_UPGRADE.md: future matched experiments and schema-only extensions.
- docs/FUTURE_TRADING_SYSTEM.md: intended prediction, liquidity, risk, portfolio, trade-management, and execution responsibilities; its historical phase-status text is not the current status source.
- docs/PHASE7A_STANDALONE_TRAINING_REMEDIATION_2026_10_22.md and docs/PHASE7A_DEEP_DEBUG_AND_EVALUATION_2026_10_22.md: local training, cache, and evaluation hardening.
- docs/PHASE7A_MEMBERSHIP_LOOKAHEAD_FIX_2026_10_23.md: latest causal-universe correction and recorded 886-test verification.
- src/crypto_ai/: installable research implementation; tests/: regression and behavior checks; configs/: versioned research definitions. Older live or dashboard entry points are not the active research workflow and must not be run.

The central conclusion remains unchanged: the research foundation is built, the latest multi-asset experiment is unfinished, and every step toward execution depends on evidence and explicit approval.
