# Architectural Decisions

## ADR-023 - Use fixed-policy cost stress as the primary robustness test

- Date: 2026-08-20
- Status: Accepted.
- Decision: Freeze the 1x policy trade IDs, entry/exit timestamps, and
  directions, then change only execution costs at 1x/1.25x/1.5x/2x.
- Consequence: Qualification uses fixed-policy 1.5x results; any trade-hash
  change invalidates the stress test.

## ADR-024 - Keep adaptive-policy cost stress secondary and separate

- Date: 2026-08-20
- Status: Accepted.
- Decision: Retain cost-aware eligibility as
  `ADAPTIVE_POLICY_COST_STRESS`, separate from fixed-policy artifacts/reports.
- Consequence: Adaptive trade identity may change and cannot support the
  primary execution robustness conclusion.

## ADR-025 - Separate qualification from evidence interpretation

- Date: 2026-08-20
- Status: Accepted.
- Decision: Qualification is deterministic `PASS`/`FAIL`; evidence is one of
  `NEGATIVE`, `INCONCLUSIVE`, `WEAK_POSITIVE`, or `PROMISING_UNVALIDATED`.
- Consequence: Insufficient evidence can be inconclusive while the candidate
  still fails the predeclared qualification gates.

## ADR-026 - Split Calibration chronologically into Cal-A and Cal-B

- Date: 2026-08-20
- Status: Accepted.
- Decision: Preserve each outer three-month Calibration window; Cal-A fits and
  selects identity/linear calibration, while purged/embargoed Cal-B selects the
  unchanged edge threshold. TEST remains evaluation-only.

## ADR-027 - Keep the prospective holdout locked during hardening

- Date: 2026-08-20
- Status: Accepted.
- Decision: No Phase 5.1 row may have `feature_time` at or after
  `2026-08-01T00:00:00Z`; every fold/run records and asserts its maximum used
  timestamp.

## ADR-028 - Preserve historical Phase 5 evidence immutably

- Date: 2026-08-20
- Status: Accepted.
- Decision: `walkforward_v1` models, folds, predictions, trades, and summaries
  are read-only sources. Hardened outputs use `walkforward_v1_1` and reference
  source checksums.

## ADR-029 - Do not treat BTC as representative of every asset

- Date: 2026-08-20
- Status: Accepted as a future architecture constraint.
- Decision: Model volatility, liquidity, spread, funding, coin age, BTC beta,
  and instability explicitly when multi-asset research is authorized.

## ADR-030 - Benchmark global, cluster, per-coin, and hybrid models

- Date: 2026-08-20
- Status: Accepted as a future research rule.
- Decision: No multi-asset model structure is presumed to win; compare all four
  on matched leakage-safe evidence and use data-driven clusters.

## ADR-031 - Normalize cross-asset feature values appropriately

- Date: 2026-08-20
- Status: Accepted as a future architecture constraint.
- Decision: Prefer comparable relative, volatility-scaled, percentile, beta,
  and liquidity-normalized features where justified.

## ADR-032 - Separate entry prediction from trade management

- Date: 2026-08-20
- Status: Accepted as a future architecture constraint.
- Decision: Market models predict distributions; trade quality, entry,
  ongoing management, and exit remain independently gated responsibilities.

## ADR-033 - Make TP and SL adaptive rather than universal percentages

- Date: 2026-08-20
- Status: Accepted as a future research constraint.
- Decision: Future TP/SL research may use volatility, ATR, MFE/MAE, regime,
  liquidity, horizon, and risk budget. One pair for every coin is forbidden.

## ADR-034 - Represent expected profit probabilistically

- Date: 2026-08-20
- Status: Accepted.
- Decision: Future predictions estimate expected return, quantiles,
  uncertainty, probability above costs, and TP-before-SL probability; exact
  future profit is never promised.

## ADR-035 - Research MFE and MAE for future trade management

- Date: 2026-08-20
- Status: Accepted as a future target.
- Decision: Maximum favorable/adverse excursion may inform TP/SL and sizing
  only after separate leakage-safe label and evaluation authorization.

## ADR-036 - Keep market regime and fear/euphoria separate

- Date: 2026-08-20
- Status: Accepted as a future architecture constraint.
- Decision: Regime describes market structure; FearState describes numeric
  stress/euphoria. Either state may coexist with any value of the other.

## ADR-037 - Allow liquidity to veto predictions

- Date: 2026-08-20
- Status: Accepted as a future safety constraint.
- Decision: The Liquidity Gate may PASS, REDUCE, or REJECT based on spread,
  volume, depth, impact, and safe notional even when expected return is high.

## ADR-038 - Let Risk own sizing and leverage

- Date: 2026-08-20
- Status: Accepted as a future safety constraint.
- Decision: Models do not output notional or leverage. Risk constrains sizing
  and deterministic leverage from equity, stop distance, volatility,
  liquidity, drawdown, portfolio state, and exchange/system limits.

## ADR-039 - Let Portfolio own correlated multi-asset exposure

- Date: 2026-08-20
- Status: Accepted as a future safety constraint.
- Decision: Portfolio controls total/cluster exposure, rolling correlation,
  BTC beta, factors, long/short balance, and open-position count.

## ADR-040 - Never let ML disable a hard risk stop

- Date: 2026-08-20
- Status: Accepted permanently.
- Decision: Deterministic account-level maximum-loss and kill-switch controls
  override every model. ML may only tighten or recommend an earlier exit.

## ADR-041 - Place Binance execution downstream of every safety gate

- Date: 2026-08-20
- Status: Accepted as the final adapter boundary.
- Decision: Only fully approved, sized, leverage-limited, portfolio-checked,
  and pre-trade-validated instructions may reach a future Binance adapter.

## ADR-042 - Never let an LLM issue unrestricted orders

- Date: 2026-08-20
- Status: Accepted permanently.
- Decision: LLM research output must be constrained, timestamped structured
  data. An LLM never directly creates or submits a Binance order.

## ADR-001 - Isolate Phase 1 from the legacy trading prototype

- Date: 2026-08-18
- Decision: Build the installable package under `src/crypto_ai/`; do not import or refactor legacy model/execution files in Phase 1.
- Reason: The archive contains valuable later-phase ideas but no tests and active order-related code. Isolation prevents accidental execution and unrelated rewrites.
- Alternatives: Move or delete the legacy tree; extend the existing root modules directly.
- Consequences: Legacy duplication remains visible until a future, separately tested migration.

## ADR-002 - Make Spot and USD-M futures explicit data domains

- Date: 2026-08-18
- Decision: Require `market=spot|usdm`, with distinct endpoints and source identifiers.
- Reason: The same symbol and fields do not imply the same market. Mixing them would make datasets ambiguous.
- Alternatives: Infer from CCXT symbols; support only the legacy futures domain.
- Consequences: Manifests and paths carry market identity and can safely coexist.

## ADR-003 - Use exact decimals and UTC microsecond timestamps

- Date: 2026-08-18
- Decision: Store prices/volumes as `decimal128(38,18)` and times as `timestamp[us, tz=UTC]`.
- Reason: Binance returns decimal strings, and Spot public archives use microseconds from 2025 onward. Float or millisecond-only storage can silently lose information.
- Alternatives: `float64`; integer scaled values; timestamp milliseconds.
- Consequences: Consumers must support Arrow decimals. Scale is deterministic and ample for the initial BTC datasets.

## ADR-004 - Immutable daily bronze partitions with deterministic partial-day names

- Date: 2026-08-18
- Decision: Split requests at UTC day boundaries and name each file with its exact start/end milliseconds. Never overwrite an existing partition.
- Reason: Daily units are small enough for validation and map cleanly to GCS while exact names distinguish partial days.
- Alternatives: One file per API page; one file per run; mutable upserts.
- Consequences: Resume is simple and corruption is surfaced rather than repaired silently.

## ADR-005 - REST first, public archive adapter later

- Date: 2026-08-18
- Decision: Implement official REST endpoints now and document Binance Public Data as the future bulk-backfill mechanism.
- Reason: REST enables a small, fully mocked Phase 1 implementation and recent samples. Archive ingestion adds ZIP/checksum/unit-transition concerns best added as a focused extension.
- Alternatives: Archive-only downloader; CCXT abstraction.
- Consequences: Multi-year 1-minute REST backfills are correct but slower and consume more request weight than archive downloads.

## ADR-006 - Quality failures are reported, not repaired

- Date: 2026-08-18
- Decision: Write parseable raw candles unchanged, attach quality results, and mark the manifest `completed_with_quality_errors` when checks fail.
- Reason: Bronze must preserve source truth. Dropping or filling candles would hide exchange/data errors.
- Alternatives: Reject every imperfect partition; auto-fill gaps; deduplicate silently even when values conflict.
- Consequences: Downstream silver processing must require a passing report or an explicit exception policy.

## ADR-007 - Make Binance USD-M the primary research market

- Date: 2026-08-19
- Status: Accepted for its data-domain decision; its CoinSwitch-target rationale is superseded by ADR-017.
- Decision: Default to Binance USD-M `BTCUSDT` perpetual futures data. Retain Binance Spot as an explicit secondary/cross-market dataset.
- Reason: The eventual CoinSwitch target is a USDT-margined perpetual-futures domain. Binance USD-M is structurally closer than Spot while providing mature public historical data and instrument metadata.
- Alternatives: Keep Spot primary; combine Spot and futures into one raw dataset; ingest CoinSwitch account or trading data during Phase 1.
- Consequences: Default configuration and tests use `market=usdm`; Spot requires intentional selection. Raw sources remain separate. The historical CoinSwitch execution assumption is no longer valid; see ADR-017.

## ADR-008 - Use versioned typed quality results and deterministic gates

- Date: 2026-08-19
- Decision: Represent every check with typed PASS/WARN/FAIL and INFO/WARNING/ERROR/CRITICAL values; persist reports with explicit report and validator versions.
- Reason: Downstream research must be able to reproduce why a dataset was accepted or rejected.
- Alternatives: Log-only checks; boolean validity; unversioned free-form JSON.
- Consequences: Report IDs include source checksums, policy, and validator version. Any failing check rejects the dataset; warnings are policy-controlled.

## ADR-009 - Never repair gaps, conflicts, impossible candles, or outliers

- Date: 2026-08-19
- Decision: Classify unexplained missing candles as `UNKNOWN_GAP`; fail conflicting duplicates and impossible financial relationships; flag statistical candidates without deletion.
- Reason: Automatic repair would manufacture market history or erase legitimate extreme events.
- Alternatives: Forward-fill gaps; choose one conflicting row; rearrange high/low; delete threshold-based price spikes.
- Consequences: Bronze stays authoritative. Rejected datasets receive a metadata-only quarantine reference for investigation.

## ADR-010 - Validate partition-wise and require cross-partition continuity

- Date: 2026-08-19
- Decision: Read one daily Parquet partition at a time and retain compact boundary summaries for adjacent-partition checks.
- Reason: A complete multi-asset history should not need to fit in memory, while boundary gaps and overlaps cannot be ignored.
- Alternatives: Load the entire dataset; validate every file independently without a dataset pass.
- Consequences: Memory is bounded by partition size and all declared/actual boundaries remain part of the quality gate.

## ADR-011 - Gate immutable Silver on a lineage-complete report

- Date: 2026-08-19
- Decision: Promote only PASS or policy-authorized WARN reports. Sort rows and deduplicate only field-identical records allowed by policy; otherwise preserve values exactly.
- Reason: Silver must be safe for later research and traceable to immutable Bronze.
- Alternatives: Mutable cleaned files; automatic promotion after ingestion; copying failed data into a second large quarantine tree.
- Consequences: Each Silver partition and manifest records Bronze hashes, source manifest/dataset, validation report/version, and deterministic Silver version. Reruns are idempotent; lineage conflicts stop rather than overwrite.

## ADR-012 - Use next-open 60-minute simple return as Label V1

- Date: 2026-08-19
- Decision: Features become available at the prediction candle's next boundary. Entry references the next candle open; the target references the open 60 minutes later. For 5-minute row `i`, the equation is `open[i+13] / open[i+1] - 1`.
- Reason: The model cannot observe a completed candle and then retroactively execute at that same candle's close.
- Consequences: `feature_time`, `entry_time`, and `label_end_time` are explicit. Final 13 rows are unlabelable; any gap in the required path invalidates the sample.

## ADR-013 - Keep Feature V1 small, causal, and shared

- Date: 2026-08-19
- Decision: Use 13 documented price, candle, volume, volatility, EMA, and RSI features implemented under `crypto_ai.features`.
- Reason: Trustworthy leakage tests and reusable definitions are more valuable than a large indicator catalog at this stage.
- Consequences: No centered rolling windows or future shifts exist. A data gap resets warm-up; expected warm-up is dropped and unexpected non-finite values fail Gold construction.

## ADR-014 - Purge labels at chronological development boundaries

- Date: 2026-08-19
- Decision: Split in timestamp order and purge training/validation rows whose `label_end_time` reaches the next split boundary.
- Reason: A training target that consumes a validation-period price leaks boundary information even when feature rows themselves do not overlap.
- Consequences: The July experiment purged 12 rows at each boundary. Random splits and random K-fold are prohibited.

## ADR-015 - Establish simple baselines before advanced modeling

- Date: 2026-08-19
- Decision: Compare zero, training mean, momentum, mean reversion, Ridge, and conservative LightGBM regression using a common artifact and metric pipeline.
- Reason: A strong model must beat transparent baselines out of sample before complexity is justified.
- Consequences: Ridge scaling fits training only; LightGBM early-stops on validation only. Test data is evaluation-only. No Phase 3 metric is an economic-performance claim.

## ADR-016 - Make Gold and experiment identities content based

- Date: 2026-08-19
- Decision: Hash Silver content/version plus label/feature definitions for Gold, and hash Gold plus research/model configuration and code version for experiments. Exclude output paths.
- Reason: Moving the repository or artifact root must not change the identity of identical research content.
- Consequences: Identical reruns reuse immutable Gold and experiment artifacts; a version/configuration change produces a new directory.

## ADR-017 - Use Binance as the sole market-data and execution venue

- Date: 2026-08-19
- Status: Accepted.
- Supersedes: The previous Binance-data/CoinSwitch-execution target architecture and the CoinSwitch rationale recorded in ADR-007.
- Decision: Use Binance for historical data, future live market intelligence, account state, futures positions, and eventual execution. Keep Binance Spot and USD-M as explicit internal source domains. Deprecate all CoinSwitch-specific adapters, configuration, credentials, endpoints, and roadmap work.
- Reasons: A unified venue eliminates cross-exchange price/execution mismatch, aligns training and execution semantics, makes funding/mark/index context venue-consistent, simplifies transaction-cost modeling, and reduces reconciliation and operational complexity.
- Alternatives: Retain CoinSwitch execution; support both execution venues immediately; introduce a generic multi-exchange execution framework before a single venue is validated.
- Consequences: Future data-availability research, backtests, instrument rules, fees, funding, paper trading, reconciliation, and live gates must use verified Binance semantics. CoinSwitch-specific legacy code remains temporarily isolated for audit and possible extraction of generic concepts; it is not a supported adapter and must not run. This ADR authorizes no Phase 4 implementation or live order.

## ADR-018 - Establish a unified Main Market Model

- Date: 2026-08-19
- Status: Accepted as a future architecture requirement.
- Decision: One primary tabular model will directly consume the majority of structured market intelligence. Its initial family is LightGBM, later benchmarked against XGBoost and CatBoost. Specialized temporal, regime, event, and meta models remain optional complementary components.
- Feature families: Price, trend, momentum, volatility, volume, buy pressure, sell pressure, order flow, funding, open interest, basis/mark/index, regime, cross-asset context, market breadth, and time context.
- Reasons: The primary forecast should learn interactions among core market variables directly and must not depend only on outputs from specialized models.
- Alternatives: Feed the primary model only specialist outputs; create one model per feature family; immediately adopt deep temporal or reinforcement-learning models.
- Consequences: Every future feature needs explicit availability time, definition, lookback, missingness policy, version, lineage, test coverage, and feature-group ablation. Phase 3 `baseline_v1` remains immutable. Expanded features require a new version such as `market_v2`. This ADR does not claim that LightGBM or any additional feature will improve out-of-sample performance.

## ADR-019 - Treat data availability as a first-class feature constraint

- Date: 2026-08-19
- Status: Accepted.
- Decision: Every external observation carries event and availability time; a
  feature may join only `availability_time <= feature_time` within an explicit
  maximum age. Unavailable groups are excluded rather than zero-filled.
- Reason: Binance sources have materially different retention and timestamp
  semantics. Nearest/future joins or implicit zeroes create leakage and false
  market facts.
- Consequences: Funding and price-index inputs can support long-history work;
  OI/ratios remain short-history groups. A6/A7 may be visibly absent from an
  experiment without invalidating earlier ablations.

## ADR-020 - Make no-trade an explicit economic outcome

- Date: 2026-08-19
- Status: Accepted.
- Decision: The Phase 4 backtester trades only OOS forecasts whose magnitude
  clears both a configured signal threshold and expected non-funding costs.
- Reason: Predictive outputs smaller than fees, spread, and slippage should not
  become forced simulated trades.
- Consequences: A flat Main Model V2 result is valid. Phase 4 permits no
  leverage or live execution and makes no profitability claim.

## ADR-022 - Freeze Phase 5 walk-forward roles and prospective holdout

- Date: 2026-08-20
- Status: Accepted.
- Decision: Evaluate only L0/L5 and matched D0/D2 with rolling 24-month Train,
  3-month Validation, 3-month Calibration, and 3-month Test windows advanced
  three months. Purge using actual label end times and apply a separate
  60-minute embargo. Freeze `2026-08-01T00:00:00Z` as the untouched prospective
  holdout.
- Isolation: Training fits the estimator; Validation controls early stopping;
  Calibration fits prediction scaling and the no-trade/threshold policy; Test
  is evaluation-only and unavailable until those artifacts are frozen.
- Economics: Preserve Phase 4.1 costs and execution semantics, allow
  calibration-driven `NO_TRADE`, and evaluate frozen policies under
  0x/1x/1.25x/1.5x/2x cost scenarios. Low activity is insufficient evidence.
- Qualification: Require stability across folds, years, regimes, cost stress,
  drift, and concentration checks. Do not select a model using arbitrary profit
  targets. D2 value must be judged against matched D0 rows.
- Consequences: Phase 5 outputs are retrospective walk-forward OOS, not the
  prospective holdout. No result authorizes advanced ML, additional assets,
  leverage, account access, order execution, or live trading.

## ADR-021 - Prefer official archives and version Phase 4.1 semantics

- Date: 2026-08-20
- Status: Accepted.
- Decision: Use the official Binance public-data archive for reproducible bulk
  USD-M history and REST only for current metadata, recent increments, and
  independently verified gaps. Preserve `market_v2`; publish corrected taker
  terminology and expanded causal features as `market_v2_1`.
- Semantics: Kline taker-buy base/quote volumes describe aggressive executed
  flow, not the complete order book. Funding accounting follows actual event
  timestamps. A validated next 1-minute bar is preferred after the signal;
  otherwise the documented next-5-minute-open fallback applies.
- Coverage: The core long-history model may not be truncated to force a
  short-retention source such as open interest. OI is an optional separate
  ablation only when its shared sample is legitimate.
- Integrity: Archive bytes, checksums, canonical Bronze partitions, REST gap
  evidence, reconciliation reports, and Silver lineage remain immutable. When
  an archive-only market-value check is the sole cause of failure, Phase 7 may
  build a composed manifest only after public REST returns the exact same row
  count and timestamps, field-level non-equivalence evidence is persisted, and
  the composed manifest passes the unchanged quality gate. Any non-market-value
  failure, row/timestamp disagreement, identical invalid REST row, or persistent
  quality failure remains a hard stop.
- Versioning: The evidence-gated archive-versus-REST acquisition amendment is
  frozen in `phase7_scientific_baseline_v1_5`. It changes no feature, target,
  fold, universe, cutoff, holdout, policy, or modeling contract value, and all
  predecessor baselines remain immutable.
- Experiment discipline: Funding, basis, and OI comparisons use identical rows
  within their family. The fixed LightGBM configuration receives no broad HPO,
  and cost/no-trade thresholds are never lowered merely to manufacture trades.
- Consequences: Historical Phase 3/4 datasets and experiment IDs remain valid.
  Phase 4.1 adds explicit cutoff-bound artifacts and prepares—but does not
  implement—Phase 5 walk-forward validation.

## ADR-022 - Quarantine unrecoverable corruption as causal segments

- Date: 2026-08-30
- Status: Accepted for Phase 7 retrospective research.
- Decision: When an archive row fails a structural market-value check and the
  bounded same-interval REST attempt returns the identical invalid row, retain
  both official observations as immutable evidence and represent the affected
  half-open interval as an explicit unusable data gap. Do not promote the row,
  reconstruct it, interpolate it, or weaken the quality gate.
- Acquisition: A discovery candidate returns a typed
  `QUALITY_REJECTED_SEGMENT` outcome and independent symbols continue. Silver
  is an immutable group of separately quality-validated contiguous child
  segments with source, quality, quarantine, REST, and comparison lineage.
- Causality: A symbol is excluded only from folds whose admission, feature,
  target, training, validation, calibration, or test information range crosses
  the gap. Folds ending before a future gap are unchanged. Re-entry requires a
  new clean segment to satisfy the existing minimum-history and complete-fold
  rules; no recovery duration is added.
- Derivations: Rolling features, higher-timeframe context, and targets reset at
  segment boundaries. Missing intervals are never treated as continuous.
- Core: Unrecoverable gaps in mandatory core/context symbols remain strict hard
  stops; only expansion/discovery candidates receive fold-local quarantine.
- Versioning: These acquisition and universe-eligibility semantics are frozen
  in `phase7_scientific_baseline_v1_6`, `dual_universe_v3`, and
  `expansion_universe_v2`. The configuration hash, 54 features,
  `multiasset_targets_v2`, 16 folds, latency, cutoff, and holdout lock are
  unchanged. All predecessor baselines remain immutable.

## ADR-023 - Benchmark multi-asset architectures with a historical universe

- Date: 2026-08-22
- Status: Accepted for Phase 7 retrospective research.
- Decision: Build a current-plus-historical Binance USD-M symbol registry,
  freeze a deterministic 20-symbol `core_universe_v1` at
  `2022-01-01T00:00:00Z`, and separately freeze an
  `expansion_universe_v1` admission policy. The expanding view admits newer
  symbols only from evidence strictly before each fold's TRAIN end, after 365
  days and configured data-quality/liquidity gates, with 10 expansion and 30
  total symbols maximum per fold. Retain historically delisted contracts when
  official archive evidence proves their existence; later survival cannot
  change earlier eligibility.
- Models: Compare Global (G0), TRAIN-only Cluster (C0), eligible Per-coin (P0),
  and global-with-fallback Hybrid (H0) LightGBM architectures. Test explicit
  symbol identity and equal-symbol training mass. Report CORE and EXPANDING
  views separately, including native coverage and identical-observation
  matched architecture comparisons.
- Features/targets: Version multi-asset features, membership-aware market
  context, and raw plus ex-ante-volatility-normalized 15/30/60/120-minute
  targets separately from Phase 6. Retest 12h and daily context independently.
- Validation: Preserve 24/3/3/3 rolling folds, actual label-end purging, and
  chronological Cal-A/Cal-B. Use a 120-minute embargo for the longest target.
  Clusters, liquidity tiers, calibration, and thresholds never use TEST.
- Resources: Use bounded symbol/year Parquet and time chunks. Heavy public-data
  acquisition/training is VM-only, manually started, non-interactive,
  checkpointed, and resume-safe. No cloud service or GPU is required.
- Consequences: Local implementation does not complete Phase 7. A real cloud
  run, verification, backup, and VM shutdown remain required. July 2026 and the
  August holdout remain unused. The holdout status is `LOCKED_UNUSED` and
  evaluation is not authorized. No account, portfolio, risk, leverage, order,
  or live-trading authority is introduced.

## ADR-024 - Side-effect-only Phase 7 runtime observability

- Date: 2026-08-30
- Status: Accepted for the Phase 7 cloud research run.
- Decision: Add stable structured progress events, concise human rendering, a
  low-frequency model-fit heartbeat, and an atomic resumable runtime
  `progress.json`. The same supplied runtime/result objects feed both renderings.
- Metrics: Fold economics and predictive values are displayed only when they
  already exist in the approved OOS report. Unavailable values render as `N/A`;
  no new backtest, estimator, model callback, or metric is introduced.
- Non-interference: Reporting does not alter data order, features, targets,
  folds, model configuration/state, calibration, thresholds, costs,
  qualification, July exclusion, or the August holdout lock. The canonical
  configuration hash remains `cc550337f1f4ee4654124bf6`.
- Versioning: `phase7_progress_v1` is the operational reporter identity. The
  source freeze advances to `phase7_scientific_baseline_v1_7` solely because
  existing contract tests byte-freeze every Phase 7 module; Phase 7 remains
  version 1.6.0 and every scientific contract value is unchanged.

## ADR-025 - Bounded official REST recovery for proven archive omissions

- Date: 2026-08-31
- Status: Accepted for the Phase 7 cloud research run.
- Decision: Binance historical archive remains primary. When the unchanged
  validator proves exact empty interior archive partitions, and registry
  lifecycle plus requested-range evidence proves those timestamps should
  exist, official unauthenticated Binance REST may supply only those exact
  interval-derived timestamps. Consecutive omissions may share one bounded
  request; separate ranges remain separate. No arbitrary gap-length limit is
  introduced.
- Preconditions: Existing ADR-021 structural-row reconciliation runs first.
  Gap recovery requires exact symbol, interval, partition, and half-open
  boundary identity; complete expected timestamps; no extras or duplicates;
  and PASS/WARN under the unchanged structural validator. Listing, delisting,
  request-edge, or otherwise ambiguous absence is ineligible.
- Evidence: Archive bytes, archive manifest, original FAIL report, quarantine,
  missing timestamp list, immutable REST rows and retrieval metadata,
  comparison report, composition-only manifest, per-partition row source, final
  report, and Silver lineage remain auditable. Existing archive rows are never
  replaced by this policy. Failure remains an unusable causal gap and cannot be
  bridged by features, targets, or folds.
- Versioning: These historical acquisition semantics advance Phase 7 to
  version 1.7.0 and are frozen by `phase7_scientific_baseline_v1_8` contract
  1.0.9. Configuration hash `cc550337f1f4ee4654124bf6`, 54 features,
  `multiasset_targets_v2`, 16 folds, model families, latency, costs, cutoff,
  July exclusion, and the locked August holdout are unchanged. Every
  predecessor baseline remains immutable.

## ADR-026 - Supervise the Phase 7 VM as a finite cost-aware batch

- Date: 2026-08-31
- Status: Accepted for the Phase 7 cloud research run.
- Decision: A manually invoked, VM-local supervisor owns exactly one research
  worker in tmux session `phase7-auto`. It atomically records `READY`,
  `RUNNING`, `BLOCKED`, or `COMPLETED`, consumes the existing operational
  `progress.json`, preserves checkpoints and evidence, and never treats quiet
  training as idle. It is deliberately not a boot service.
- Failure: A genuine worker failure writes a durable diagnostic bundle and a
  `BLOCKED` marker before requesting VM shutdown. A later invocation refuses
  to resume while either the marker or state remains blocked. Clearing the
  marker requires an explicit audited reason after diagnosis and validation.
- Completion: Exit zero is insufficient on its own. Completion additionally
  requires the canonical configuration hash, final Phase 7 progress event,
  matching code commit, unused July buffer, and locked unused August holdout.
  Final artifacts are synced to the existing Phase 7 GCS root before shutdown.
- Interruption: SIGINT/SIGHUP/SIGTERM exit codes are recorded as resumable
  operational interruptions rather than scientific failures. Checkpoint and
  `--resume` semantics are unchanged.
- Non-interference: `phase7_vm_supervisor_v1` is an operational contract. It
  changes no source, validation, universe, feature, target, fold, model,
  calibration, cost, qualification, cutoff, or holdout behavior. The frozen
  scientific baseline remains `phase7_scientific_baseline_v1_8`, Phase 7
  remains 1.7.0, and the canonical hash remains
  `cc550337f1f4ee4654124bf6`.
