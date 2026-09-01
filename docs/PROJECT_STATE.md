# PROJECT STATE

## COMPLETED

- Phase 1: reliable Binance Spot and USD-M historical ingestion, canonical exact-decimal candle schemas, immutable Bronze Parquet, checksums, restartable manifests, and partition validation.
- Phase 2: typed production validation, deterministic PASS/WARN/FAIL reports, quarantine references, and controlled immutable Bronze-to-Silver promotion with lineage.
- Phase 3: a versioned, gap-safe 60-minute next-open label; 13 causal baseline features; immutable Gold datasets; chronological purged train/validation/test splits; six baseline regressors; predictive evaluation; rank metrics; target percentiles; structured feature importance; and reproducible local artifacts.
- Phase 4: official Binance data research; public funding/mark/index/premium/OI
  adapters and schemas; causal as-of alignment; Feature V2 and Regime V1;
  immutable Gold V2; Main Model V2 ablations; and an OOS, cost-aware,
  funding-aware, one-position backtest foundation.
- Phase 4.1: official-archive bulk ingestion, archive/REST reconciliation,
  multi-year BTCUSDT 5m history, recent 1m execution support, precise taker-flow
  Feature V2.1, hardened causal regimes, two-tier Gold datasets, fixed-parameter
  ablations, and expanded OOS/backtest diagnostics.
- Phase 5: deterministic rolling 24/3/3/3-month walk-forward folds; actual
  label-end purging; 60-minute embargoes; isolated train/validation/calibration/
  test responsibilities; identity/linear calibration; calibration-only
  no-trade thresholds; 1m/5m tagged execution; cost stress; predictive block
  intervals; drift/concentration diagnostics; resumable immutable artifacts;
  qualification gates; and a combined candidate decision.
- Phase 5 Hardening: immutable `walkforward_v1_1` post-processing from the 66
  frozen Phase 5 models; chronological Cal-A/Cal-B with purge/embargo;
  fixed-policy primary and adaptive-policy secondary cost stress; separate
  qualification/evidence statuses; reliability-safe ratios; stronger trade
  concentration; independent lineage/checksum/holdout verification; and the
  final **NO QUALIFIED MODEL** decision.
- Phase 6: direct official BTCUSDT USD-M 12h/daily Bronze and Silver history;
  exact direct-vs-derived reconciliation; completed-candle joins; isolated
  `market_v3_research` and `label_v2_research` families; five return horizons;
  MFE/MAE and ambiguity-safe volatility-normalized barrier labels; fixed
  chronological probes; higher-timeframe/cross/stress ablations; coverage,
  drift, redundancy, importance, and feature/target scorecards; zero use of the
  permanent holdout; and no champion promotion.
- Architecture revision: accepted Binance as the sole market-data and eventual
  execution venue, deprecated the old CoinSwitch target, and established the
  unified Main Market Model roadmap.
- Safe pre-baseline context foundation: provider-neutral public context
  records, Alternative.me Fear & Greed historical ingestion, Binance USD-M
  recent/forward open-interest collection, explicit point-in-time eligibility,
  immutable raw/normalized datasets, manifests, optional feature builders, and
  guarded one-shot CLI commands. Neither feature family is active in Phase 7.
- Phase 7.1B architecture foundation: semantic contract versioning, immutable
  event envelopes, model/prediction/deployment metadata, execution adapter
  capability protocols with a disabled-only implementation, portfolio read and
  decision interfaces, observability/failure contracts, query-only dashboard
  projections, and a machine-readable byte freeze of the approved Phase 7
  scientific source/config baseline.
- Phase 7.2 capability foundation: isolated `canonical_market_1m_v1`, strict
  completed-window 1m-to-5m aggregation, disabled `micro_1m_context_v1`,
  competing-risk/ambiguity contracts, fold-active ranking groups,
  interpretable monitor-only OOD, matched tree-challenger interfaces,
  prospective OI/BBO/depth/liquidation/metadata/EventContext schemas, trial
  declarations and predeclared promotion/cost controls. These capabilities are
  prepared but inactive; no new research result or qualified model exists.
- Preserved all implemented ingestion, validation, inspection, promotion, dataset, training, and evaluation interfaces covered by the full regression suite.

## IN PROGRESS

- Phase 7 cloud research. Local code, configuration, deterministic fixture
  tests, safe plan/dry-run commands, the stable `core_universe_v1`, causal
  fold-local `expansion_universe_v2`, separately labeled CORE/EXPANDING
  evaluations, bounded Gold construction, G0/C0/P0/H0 architecture runners,
  matched-coverage reporting, checkpoint/resume, and the Google Cloud runbook
  are implemented. Phase 7.1 re-audit corrected fold-local cross-sectional
  context and Cal-A/Cal-B ownership, added `multiasset_targets_v2` with a full
  post-signal decision-latency bar, and completed 35 pure race simulations. The
  existing VM remains stopped and no real multi-asset Phase 7 result exists yet.
  On 2026-08-25, the independent reviewer accepted canonical
  `artifact_fingerprint_v1` as the authoritative baseline and resolved R-13.
  The old undocumented digest remains non-comparable historical metadata only.
  Phase 7.1B adds side-effect-free future contracts without importing them into
  the scientific path. The original approved source/config freeze remains
  preserved as `phase7_scientific_baseline_v1`; the authorized pre-cloud
  onboard-boundary correction is frozen separately by v1_1, and the authorized
  exact per-interval archive-boundary correction is frozen by
  v1_2. The manifest-level zero-volume aggregation is frozen by v1_3, the
  integrity-liquidity separation is frozen by v1_4, and the evidence-gated
  official archive-versus-REST reconciliation is frozen by
  `phase7_scientific_baseline_v1_6`. Side-effect-only operational progress
  reporting is frozen by `phase7_scientific_baseline_v1_7`, without changing
  the 1.6.0 scientific version or contract values. Exact bounded REST recovery
  of validator-proven archive omissions is frozen by
  `phase7_scientific_baseline_v1_8` and Phase 7 version 1.7.0. Phase 7.2 adds only disabled
  research capabilities in a separate namespace.
  Cost-aware batch supervision is separately versioned as the operational-only
  `phase7_vm_supervisor_v1`; it preserves the v1_8 scientific freeze and
  atomically stops the existing VM only after durable `BLOCKED` diagnostics or
  proven `COMPLETED` artifact backup.
  Operational successor `phase7_vm_supervisor_v1_1` adds a conservative,
  non-scientific `BUDGET_STOPPED` state that preserves checkpoints/evidence and
  prevents automatic restart after the approved cloud-cost ceiling is reached.
  Patch `phase7_vm_supervisor_v1_1_1` adds only the audited recovery transition
  needed to archive an explicitly cleared budget stop before returning to
  `READY`.

## PHASE 7 PRE-PUSH STATUS

```text
Phase 1–6:
COMPLETE

Phase 7 implementation:
COMPLETE

Phase 7.1 re-audit verification:
COMPLETE / PASS / SAFE TO COMMIT

Phase 7.1B architecture foundation:
COMPLETE / PASS / SCIENTIFIC BASELINE UNCHANGED

Phase 7.2 capabilities:
PREPARED LOCALLY / DISABLED / SCIENTIFIC BASELINE UNCHANGED

Phase 7 cloud baseline gate:
READY FOR CLOUD BASELINE

Phase 7 real multi-asset acquisition:
NOT RUN

Phase 7 actual model training:
NOT RUN

Phase 7 baseline context:
MARKET DATA ONLY

Fear & Greed collector:
IMPLEMENTED / NOT ACTIVE IN MODEL / HISTORICAL KNOWLEDGE TIME UNVERIFIED

Fear & Greed Phase 7 training:
DISABLED

Open Interest collector:
IMPLEMENTED / FORWARD COLLECTION ONLY / NOT ACTIVE IN MODEL

Open Interest Phase 7 training:
DISABLED

1m enhancement:
NOT PROVEN / DISABLED

Competing-risk target:
NOT PROVEN / DISABLED

Ranking model:
NOT PROVEN / DISABLED

CatBoost/XGBoost:
NOT YET BENCHMARKED / DISABLED

CryptoPanic:
NOT IMPLEMENTED

Arkham:
NOT IMPLEMENTED

Reddit:
NOT IMPLEMENTED

Phase 7 overall:
IN PROGRESS

Qualified model:
NONE

July 2026:
UNUSED

Prospective holdout:
LOCKED / UNUSED

Prospective holdout used:
false

Prospective holdout evaluation authorized:
false

Phase 8:
NOT STARTED
```

## HISTORICAL NEXT (SUPERSEDED)

- Phase 5 — Full Walk-Forward Validation requires a separate explicit instruction. No account access,
  execution, leverage, portfolio automation, or live-trading code is authorized
  by this checkpoint.

## NEXT

- Review the Phase 7.1/7.1B audit, risk register, baseline freeze and final
- Review the Phase 7.2 capability upgrade, adoption matrix, risk register and
  final verification report, then commit/push only in a separately requested
  Git action.
- After that source is available on the existing VM, follow
  `PHASE7_CLOUD_RUNBOOK.md` manually. Do not set
  `PHASE7_ALLOW_CLOUD_RESEARCH=1` during ordinary local work.
- Do not claim Phase 7 complete until the cloud research and verification are
  complete. The prospective holdout remains `LOCKED_UNUSED`, is not authorized
  for Phase 7 evaluation, and must remain unopened. No account access,
  execution, leverage, portfolio automation, or live trading is authorized.

## DECISIONS

- Binance is the sole canonical data and eventual execution venue. The former Binance-data/CoinSwitch-execution design is superseded by ADR-017.
- Binance USD-M perpetual futures are the primary research market; Spot remains a separately identified secondary/cross-market dataset.
- One future Main Market Model will directly consume most structured market information. LightGBM is the first candidate family, not a permanent winner.
- CoinSwitch-specific legacy modules are deprecated and retained temporarily only for audit and possible extraction of exchange-independent concepts.
- Phase 7 keeps a stable 20-symbol pre-2022 `core_universe_v1` benchmark and a
  separate causal expansion policy. Newer symbols may enter only at a fold's
  TRAIN end after verified availability, 365 days of history, required data
  quality/higher-timeframe coverage, and causal trailing-liquidity gates. The
  expanding view is capped at 10 additions and 30 total symbols per fold.
- CORE and EXPANDING architecture results are reported separately. Expansion
  selection cannot use future listing, survival, liquidity, returns,
  profitability, model accuracy, or TEST outcomes.
- Alternative.me Fear & Greed is one global context series. Its documented
  historical timestamp does not establish historical publication time, so
  historical rows remain `NOT_TRAINING_ELIGIBLE`.
- Binance USD-M OI is collected only from the public current and recent
  statistics endpoints. The official history is limited to the latest one
  month; records are `FORWARD_ONLY`, and no multi-year history is fabricated.
- The separate context config cannot alter Phase 7 features, folds, universes,
  architectures, targets, costs, cutoff, or locked holdout.
- `multiasset_features_v2` labels acquisition-union context preview-only and
  rebuilds all universe-dependent values from `fold_active_symbols` before
  model slicing. P0 eligibility uses Cal-A only; Cal-B owns policy thresholds.
- `multiasset_targets_v1` remains reproducible only for audit; its exact
  next-open reference equals feature availability and is excluded from new
  economic qualification. Configured `multiasset_targets_v2` reserves one full
  5-minute decision-latency bar.
- For Phase 7 prediction row `i`, use the completed candle at `i`, stamp the
  feature at `open[i+1]`, reference entry at `open[i+2]`, and calculate the
  60-minute target at `open[i+14]`. Phase 1–6 target versions remain unchanged.
- `artifact_fingerprint_v1` is the authoritative preservation baseline from
  2026-08-25. The earlier undocumented `11a00ed1...` combined digest is retained
  only as historical metadata and is not directly comparable with canonical
  v1.
- `phase7_scientific_baseline_v1_8` is the authoritative cloud source/config
  freeze. It adds bounded official REST recovery only for exact
  validator-proven archive omissions; v1_7 adds operational progress reporting
  only, and v1_6 records causal
  segment quarantine for an identical-invalid official archive/REST row. Its
  v1 through v1_7
  predecessors remain immutable historical evidence. `dual_universe_v3` and
  `expansion_universe_v2` make affected expansion eligibility fold-local while
  preserving strict core/context behavior. Future architecture
  services may depend on the additive `crypto_ai.contracts` package, but Phase 7 scientific modules must not import
  it. Any unreviewed hash or safe-output drift remains a correctness blocker.
- Phase 7.2 remains an additive namespace. The first cloud baseline stays 5m,
  54 features, `multiasset_targets_v2`, one-bar latency, 16 folds and
  G0/C0/P0/H0 LightGBM. `micro_1m_context_v1`, competing risks, ranking,
  CatBoost/XGBoost, prospective capture and every Phase 8 model are disabled.
- One-minute information may later be aggregated into matched 5m rows for a
  BTC/ETH pilot. It must demonstrate incremental OOS value before symbol or
  history expansion; full-universe 1m training is not authorized.
- Prospective market records use event/receive/availability time and explicit
  missing/stale/invalid/provider-error states. OI remains forward-only and book,
  depth, liquidation, metadata and EventContext collectors were not started.
- Dashboard state is a read-only projection, and PAPER/SHADOW/LIVE adapter names
  are capability declarations rather than authorizations. The only Phase 7.1B
  implementation is disabled and cannot perform network, account, or order I/O.
- Require every expected open from entry through target. Missing intervals invalidate the label; no row is synthesized or forward-filled.
- Keep Phase 3 `baseline_v1` immutable, deliberately small, and causal. Future expanded features require a new version.
- Use a chronological 70/15/15 development split and purge boundary rows whose label horizons overlap the next split.
- Fit learned transforms and estimators on training data only. Validation may control LightGBM early stopping; test remains evaluation-only.
- Treat features, labels, model outputs, actions, risk parameters, and transaction costs as distinct concepts.
- Evaluate Phase 3 predictive quality only. No Phase 3 metric represents tradable PnL or profitability.
- Prefer official Binance archives for bulk history and current public REST for
  metadata, recent increments, and independently verified gap corrections.
- Preserve `market_v2`; Feature `market_v2_1` uses precise taker-flow names and
  never describes candle taker volume as full order-book pressure.
- Keep OI optional and short-history. Do not truncate the core model to force
  OI inclusion. Apply funding only at actual event timestamps and prefer a
  validated post-signal 1m execution reference where covered.
- Freeze the prospective holdout at `2026-08-01T00:00:00Z`. Phase 5 results are
  retrospective walk-forward OOS only. Keep Train, Validation, Calibration,
  and Test responsibilities separate and permit calibration-driven `NO_TRADE`.
- Phase 5.1 preserves Phase 5 artifacts, uses Cal-A for calibration and Cal-B
  for thresholds, and treats fixed-policy cost stress as primary.
- Phase 6 uses the exclusive `2026-07-01T00:00:00Z` cutoff, leaving all July
  unused and keeping the August prospective holdout untouched. Direct official
  USD-M 12h/daily candles are canonical; exact 5m aggregation is reconciliation
  only. Research feature/target classifications are not production approvals.
- Qualification `PASS`/`FAIL` is distinct from scientific evidence status.
- BTC is not representative of every coin. Future multi-asset model structure
  must be benchmarked, normalized, and gated by liquidity/risk/portfolio.
- Risk owns sizing/leverage and hard stops; Binance execution is downstream of
  all gates; LLMs never issue unrestricted orders.

## EXPERIMENT RESULTS

- Pre-Phase 3 regression baseline: 69 tests passed.
- Phase 3 final verification: 96 tests passed; Ruff lint and format checks, Python compilation, and `uv lock --check` passed.
- Architecture-change baseline: 96 tests passed.
- Phase 3 final-completion verification: 98 tests passed, 0 failed; Ruff lint/format, Python compilation, and dependency-lock validation passed.
- Real source: Binance USD-M `BTCUSDT`, `5m`, `[2026-07-01T00:00:00Z, 2026-08-01T00:00:00Z)`, 8,928 expected and observed candles across 31 daily partitions, with no gaps, duplicates, timestamp/OHLC/volume defects, or repairs.
- Phase 2 quality status was `WARN` only because 36 candidate statistical outliers were retained for research; report `quality-2d01975b9b0af1a8bf0711a2` and Silver dataset `silver-7105362e4dc25f97784d8f9a`.
- Gold dataset `gold-19425b0820c974247b73fbe0`: 8,866 rows and 13 features. It excluded 49 causal-feature warm-up rows and 13 rows without a complete future horizon; zero labels were invalidated by gaps.
- Purged split: 6,194 train, 1,318 validation, and 1,330 test rows; 12 rows were purged before each later split.
- Experiment `experiment-5f0f09b3ee131bddba69a0b1` produced validation/test predictions, model bundles, manifests, comparison tables, feature importance, target distribution, and reload checks.
- Test RMSE: zero `0.00395053`; historical mean `0.00397369`; momentum `0.00576612`; mean reversion `0.00444736`; Ridge `0.00401116`; LightGBM `0.00397419`.
- No learned model beat the zero baseline on test RMSE. Mean reversion had the highest test direction accuracy (`0.5376`) and weak positive Pearson correlation (`0.0852`); this is not evidence of profitability.
- LightGBM stopped at iteration 3 and its test correlation was approximately zero. Prediction-bucket returns were not monotonic, so no signal claim is supported.
- The architecture revision did not modify Phase 3 source, configurations, datasets, models, predictions, or historical experiment results.
- Final completion added verification coverage and documentation only; label, feature, Gold, split, model, configuration, and historical experiment semantics remain unchanged.
- Phase 4 Gold `gold-v2-f59110b7f683d2fe4342c8d6` contains 8,580 rows and
  50 enabled features from 8,928 BTCUSDT 5m candles plus 93 funding events.
- Main Model V2 experiment `main-model-v2-7ab8dd9185dc27f90d1179b0`
  used 5,994/1,275/1,287 purged train/validation/test rows and seven same-row
  ablations (A0-A5, A8); basis A6 and OI A7 were unavailable for the run.
- A8 used 42 post-redundancy features. Test MAE was `0.00277019`, RMSE
  `0.00400915`, R-squared `-0.012705`, direction accuracy `0.464646`, Pearson
  IC `0.123210`, and Spearman IC `0.079366`. This does not establish skill.
- Backtest `backtest-v1-3fe833c385aba7b0d34d49a0` made zero Main Model V2
  trades because predictions did not clear the 13 bps configured signal/cost
  hurdle. Momentum and mean-reversion comparators lost money after costs.
- Phase 4 final verification: 107 tests passed; Ruff lint/format, Python
  compilation, dependency compatibility, and lock validation passed.
- Phase 4.1 validated 724,828 contiguous active-market BTCUSDT USD-M 5m candles
  over `[2019-09-10T05:40:00Z, 2026-08-01T00:00:00Z)` and 570,240 1m candles
  over `[2025-07-01T00:00:00Z, 2026-08-01T00:00:00Z)`. No candle gaps,
  duplicates, conflicting duplicates, schema/OHLC/volume/timestamp errors, or
  unreadable/corrupt partitions remained in promoted history.
- Historical derivatives contain 7,550 actual funding events, 692,338 mark
  rows, and 692,339 index rows. Fourteen mark and thirteen index observations
  absent from both official transports remain visibly missing; OI is not
  forced into the multi-year sample.
- Core Gold `gold-v2-1-a3d74d086a912070ee63a5ec` contains 722,395 rows and 52
  features. Derivatives Gold `gold-v2-1-445fe8d3e2f5c2cb9e5ac6d1` contains
  683,863 rows and 61 features.
- Main Model V2.1 experiment `main-model-v2-1-55f7b64298b70d529a1c5e39`
  ran L0–L5 and D0–D2 on identical rows within each family, with no HPO. L5
  test Pearson IC was 0.03252, direction accuracy 0.49659, and bootstrap IC
  interval crossed zero. D2 R² remained negative. Added groups did not show a
  reliable incremental edge.
- Backtest `backtest-v2-1-1ab164e8a1409ebbad40b155` selected only 5 of 102,580
  opportunities at base costs. Its positive return/large mechanical ratios are
  `INSUFFICIENT_SAMPLE`; the 2,478-trade zero-cost diagnostic lost 1.8975% and
  had negative expectancy. The evidence classification is NO RELIABLE EDGE.
- Phase 4.1 final verification: 133 tests passed, 0 failed; Ruff lint and format,
  Python compilation, dependency resolution/lock validation, and diff checks
  passed.
- Phase 5 primary run `wf-btc-primary-v1-c3b30d4b831a8a576cdfd405`
  produced 17 L0/L5 folds and 446,966 unique OOS rows per candidate. L0/L5
  base policies made 12/17 trades with negative expectancy and no reliable
  fold; both are `INCONCLUSIVE`.
- Phase 5 derivatives run `wf-btc-derivatives-v1-c446e61dcf7a3f17e2e4f6cd`
  produced 16 matched D0/D2 folds and 418,499 rows each. D0/D2 base expectancy
  is negative; reliable-fold counts are 1/2. D2 value added is `INCONCLUSIVE`.
- Combined decision `candidate_comparison.json`: **NO QUALIFIED MODEL**.
  Prospective holdout used: false. Final verification: 156 tests passed,
  0 failed; Ruff lint/format and Python compilation passed.
- Phase 5.1 primary run
  `wf-hardened-btc-primary-v1-1-80bd34e54566298fc97a4b11` completed 17 folds
  for L0/L5. Base fixed-policy trades are 47/112; both expectancies are
  negative and both qualification statuses are FAIL / evidence INCONCLUSIVE.
- Phase 5.1 derivatives run
  `wf-hardened-btc-derivatives-v1-1-5ad6d2c0eaf8b990161d25ad` completed 16
  folds for D0/D2. Base fixed-policy trades are 9/253; both expectancies are
  negative and both qualification statuses are FAIL / evidence INCONCLUSIVE.
- Phase 5.1 verifier audited 66 hardened and 66 source fold manifests with 0
  checksum/invariant failures, 0 duplicate OOS timestamps, 0 holdout rows, no
  retraining, and unchanged features, Label V1, model configuration, and
  qualification gates. Resume left the 1,136-file hardened tree SHA unchanged.
- Final Phase 5.1 decision: **NO QUALIFIED MODEL**. Prospective holdout used:
  false; maximum development `feature_time`: `2026-07-08T23:55:00Z`.
- Phase 5.1 final verification: 164 tests passed, 0 failed, 0 skipped;
  Ruff lint/format, Python compilation, and `uv lock --check` passed.
- Phase 6 direct data contains 4,975 12h and 2,488 daily candles through the
  exclusive July cutoff, each at 100% timestamp coverage with zero gaps,
  duplicates, or invalid rows. Exact reconciliation found eight discrepant
  shared candles in each interval; direct current Binance klines remain
  canonical and all discrepancies are preserved in the report.
- Phase 6 Gold `gold-phase6-btc-a6d0815c4adf041bf4107755` contains 651,862
  rows and 127 features. Its maximum feature time is
  `2026-06-30T19:55:00Z`; every stored 12h/daily availability is at or before
  feature time, every 4h label ends before cutoff, and holdout rows used are 0.
- Experiment `phase6-btc-a6d0815c4adf041bf4107755` produced 1,725,856 OOS
  prediction rows across four purged/embargoed folds. On the fixed 1h
  LightGBM probe, 12h adds +0.003986 pooled Spearman IC and is
  `KEEP_CANDIDATE`; daily adds +0.000639 and is `WEAK`; current cross-timeframe
  and stress groups reduce the reference IC and are `REJECT`.
- The 15m/30m/1h/2h target families are retrospective `TARGET_CANDIDATE`
  diagnostics; 4h is `RESEARCH_ONLY`. No cost, turnover, capacity, policy, or
  profitability qualification was performed. Current model status remains
  **NO QUALIFIED MODEL** and no champion was promoted.
- Phase 6 final verification: 187 tests passed, 0 failed, 0 skipped; Ruff lint
  and 105-file format checks, Python compilation, and `uv lock --check` passed.
- Phase 7 pre-push and newer-coin hardening verification: 241 tests passed, 0
  failed, 0 skipped; Ruff lint and 129-file format checks, Python compilation,
  `uv lock --check`, and `git diff --check` passed. The 54 Phase 7 tests include
  13 focused cold-start/expansion tests and remain deterministic local
  fixtures; no heavy cloud run or real Phase 7 result was produced. The sole
  warning is joblib's harmless Windows physical-core detection fallback to the
  configured logical-core limit.
- Safe context-foundation verification: 280 tests passed, 0 failed, 0 skipped;
  the 39 focused context tests and all 54 Phase 7 tests passed. Ruff lint,
  141-file formatting, Python compilation, `uv lock --check`, and
  `git diff --check` passed. All safe Phase 7 CLI outputs matched the pre-change
  normalized baseline, all context status/plan commands used no network, and
  historical artifact inventories and fingerprints were unchanged.
- Phase 7.1B final verification: 353 tests passed, 0 failed, 0 skipped, including
  25 contract/baseline-freeze tests and the existing Phase 7 and control-plane
  suites. Ruff lint, 161-file formatting, Python compilation, `uv lock --check`,
  and `git diff --check` passed. All 20 Phase 7 scientific source/config files
  remained byte-identical to the pre-7.1B state, and validation/plan/dry-run/
  universe outputs matched `phase7_scientific_baseline_v1`. The read-only
  canonical artifact fingerprint remained `ad44fe62a5bae2df4c9b21f3d39f02b2141fe4dd6db7db022bb3fe6ee62103f1`.
  No cloud, account, private API, order, July, or holdout access occurred.
- Phase 7.2 final local verification: 400 tests passed, 0 failed, 0 skipped,
  including 46 focused capability/non-interference tests. Ruff lint, 178-file
  formatting, Python compilation, `uv lock --check`, safe validation/plan/
  dry-run/test-universe and `git diff --check` passed. The Phase 7 hash remains
  `68e4b39899f8c9f0542d227b` on the audit's Windows host, and the accepted
  artifact fingerprint remains
  `ad44fe62a5bae2df4c9b21f3d39f02b2141fe4dd6db7db022bb3fe6ee62103f1`.
  No capability was activated and no cloud, network collection, private API,
  order, July, holdout, leverage or Phase 8 activity occurred.
- Phase 7.2.1 replaces that host-dependent path serialization with canonical
  POSIX logical paths at the authoritative Phase 7 configuration-identity
  layer. The cross-platform hash is `cc550337f1f4ee4654124bf6`; the old
  `68e4b39899f8c9f0542d227b` is historical Windows metadata only. Actual
  label-end purging proves the 125-minute maximum feature-to-label span at
  every boundary, while the separate 120-minute next-segment embargo remains
  correct. No model-facing scientific value or row assignment changed.

## KNOWN PROBLEMS

- The historical first Phase 4 experiment remains one month. Phase 4.1 expands
  BTC to multi-year coverage and Phase 5 adds full retrospective walk-forward
  evaluation, but completed research through Phase 6 still has one instrument.
  Phase 7 multi-asset cloud research is pending. The sacred prospective
  holdout remains deliberately unopened.
- Phase 4 has bar-level timing, fees, funding, spread/slippage assumptions, and
  normalized one-position accounting, but no depth replay, queue position,
  partial-fill, impact, latency-variance, liquidation, leverage, or portfolio
  engine. Next-open remains a reference assumption, not an execution guarantee.
- None of the learned models demonstrated test-RMSE skill over the zero baseline. The artifacts are an engineering baseline, not a trading recommendation.
- Historical availability and timestamp semantics are documented in
  `BINANCE_MARKET_DATA_RESEARCH.md`. The real July run includes funding but not
  mark/index basis or OI; those groups must not be inferred from absent data.
- Alternative.me historical Fear & Greed knowledge time is not proven. The
  collected history is preserved but intentionally unavailable to research
  features until reviewed. Binance OI has only recent provider coverage, so it
  cannot support the current multi-year Phase 7 baseline.
- CoinSwitch-specific legacy modules contain unverified live account/order behavior, missing/undeclared components, and unsafe configuration patterns. They remain isolated, deprecated, and must not run.
- Label V2 remains research-only; no Phase 6 target is a production target.
- Statistical outlier windows in the inherited Phase 2 validator reset at partition boundaries.
- Git provides the tracked baseline for this Phase 7 change. Verification also
  uses inventories, tests, static checks, and artifact manifests.
- The base-cost Phase 4.1 result has only five trades, concentrated in bear/high
  volatility periods and driven by a few extreme moves. Sharpe, Sortino, profit
  factor, Calmar, and apparent return are not reliable at this sample size.
- Bar-based 1m execution still cannot reproduce bid/ask, queue position,
  partial fills, depth impact, or sub-minute latency. Fees/spread/slippage are
  explicit assumptions, not account-specific observed costs.
- Phase 6 target observations overlap strongly, especially at 2h/4h, so raw
  row counts are not independent sample sizes. Purge, embargo, folds, and the
  sampling stride reduce but do not eliminate research bias.
- The 1m barrier-refinement overlap begins `2025-07-01`; earlier same-5m TP/SL
  overlaps and same-minute overlaps remain explicitly ambiguous. Barrier
  results are not final TP/SL settings.
