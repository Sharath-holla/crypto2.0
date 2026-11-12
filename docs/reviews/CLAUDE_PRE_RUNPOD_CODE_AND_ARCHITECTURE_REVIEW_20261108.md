# Claude pre-RunPod code and architecture review — 2026-11-08

Author: Claude Code (Opus 5.5). Scope: local code, tests, architecture and docs only. No real data
was trained, no real prepared cache was built, no cloud resource was touched, July/August were not
accessed, no order path was run. Nothing here is evidence of model skill or profitability.

## 1. Executive summary

The training observer that a previous Claude session left **uncommitted** was well designed but
**not wired**: `bind_validation` was never called and no Validation context was built, so none of the
new LONG/SHORT precision/recall diagnostics could ever run. It also broke the suite (2 failing tests,
2 Ruff errors, 1 unformatted file). This session wired it end to end, fixed one serious defect it
would have introduced (LightGBM `predict()` inside the callback silently switched training to all CPU
cores), cut its cost from O(trees²) to O(trees), made the report deterministic, added fail-closed
fit-boundary invariants, replaced the approximate Ridge with an exact matched full-TRAIN weighted Ridge
(baseline contract v3), and added 63 targeted tests. The normalized-target unit defect (MR-28) is
fixed and tested. Gold, sidecar, features, targets, universe, folds, cache-preparation semantics,
early stopping and TEST visibility are unchanged; the prepared-matrix identity is byte-identical to
HEAD.

A second agent (the concurrent "local review", `docs/reviews/CRYPTO2_LOCAL_REVIEW_20261108.md`)
edited the same new modules during this session. Its four fixes were verified present and kept; its
one pending proposal (Ridge block-size guard) was applied here. **Freeze one source export after both
editors stop**, before transfer.

Verdict: **READY_FOR_RUNPOD_VERIFICATION_ON_WEDNESDAY** (code only; every external gate remains).

## 2. Branch / SHA

* Branch `fix/phase7-final-architecture-repair-20261106`, HEAD `3ec73e37d2a308eb4f03fc40cfeec6366acc2b34`.
* Nothing committed by this session. All changes are in the working tree (listed in section 30).
* Untracked items not created by this session and not touched: `Claude outputs/`,
  `docs/reviews/evidence_crypto2_20261106/`, `docs/reviews/phase7_*_20261106.md`, and the concurrent
  reviewer's `CRYPTO2_LOCAL_REVIEW_20261108.md`, `evidence_local_review_20261108/`,
  `tests/phase7/test_local_review_diagnostics.py`, `PROJECT_CONTEXT.md` edit.

## 3. Baseline test results (before any change by this session)

| Tree | pytest | ruff check | ruff format |
|---|---|---|---|
| Working tree as found (prior session's uncommitted edits) | **1392 passed, 2 failed** (`test_phase7b_hardening.py`: stale pooled P/R assertions) | **FAIL** (SIM905, SIM105) | **FAIL** (1 file) |
| Clean `git archive HEAD` export | 1381 passed, 13 failed — all 13 in `tests/integration/test_crypto_aiventra.py` need the git-ignored `source-freeze.json`, absent from an archive export (environmental, not code) | — | — |

`uv sync --locked --extra dev` succeeded (uv 0.13.7; Python 3.12.16, LightGBM 4.7.0, NumPy 2.4.6,
PyArrow 24.0.0). The previous report's "1394 passed" is consistent with HEAD in-repo
(1392 + the 2 tests broken only by the uncommitted edits).

## 4. Code errors found (this session)

See section 32 for the full register. Headline: OBS-01 observer not wired; OBS-02 suite/lint broken;
OBS-03 thread-budget leak; OBS-04 quadratic in-fit cost; OBS-05 non-deterministic report fields;
FB-01 no fit-boundary invariants for cache-reloaded matrices; MR-28 unit ambiguity; MR-26 unmatched
Ridge; PERF-01 pre-existing per-round Python metric cost; CACHE-01 over-broad cache key.

## 5. Errors fixed

OBS-01..06, FB-01, FB-02, MR-28, MR-26 (G0/H0 exact; C0/P0 documented as pooled reference), CX-5
(Ridge block guard). Concurrent reviewer fixes CX-1..4 verified present.

## 6. Errors remaining

PERF-01 (instrumented, not changed), CACHE-01 (deferred), PARAM-01 (needs justification, not
changed), FUND-01 / EXEC-01 (design only), CONC-01 (process), and every external RunPod gate.

## 7. Architecture before

`training_metrics.FitMetricObserver` printed one line per check with a pooled `fixed_precision` /
`fixed_recall` computed **inside the LightGBM metric callback** in target units (normalised units
labelled as bps) with undefined values forced to 0.0. New modules `action_metrics`,
`regression_diagnostics`, `training_observer` existed but were dead code. No invariant check at the fit
boundary for matrices reloaded from the prepared cache. Ridge baseline: ≤500k strided, unweighted rows.

## 8. Architecture after

```
training.py ── assert_fit_segments (fit_boundary)         read-only, before fit
           ├── try_build_validation_context (observer)   VALIDATION table only, raw units
           └── training_metric_scope(diagnostics=ctx)
                  models._fit ── assert_fit_matrices (fit_boundary)
                              └── observer.bind_validation(rows=mask for C0/P0)
                                    LightGBM callback ── FitMetricObserver.__call__
                                         ├── best-round tracking (every round)
                                         ├── TrainingDiagnostics.snapshot   (every check, Validation sample)
                                         │     ├── regression_diagnostics  (target units)
                                         │     └── action_metrics          (raw units, predeclared bps)
                                         ├── HealthTracker                  (heuristic flags)
                                         ├── JSONL telemetry                (append-only, fsync)
                                         └── format_diagnostic_lines        (console block)
           report.phase7b.training_observer = report_view(summary) + fit_boundary + weights + prediction_health
```

Responsibilities: fitting (`models`), callback/persistence (`training_metrics`), diagnostics/health/
formatting (`training_observer`), definitions (`action_metrics`, `regression_diagnostics`), invariants
(`fit_boundary`). No circular imports; observer modules import NumPy + the two pure metric modules.

## 9. training.py review

2,334 lines at HEAD. This session added ~67 lines (calls only) and moved all new logic to dedicated
modules. No extraction of existing code was done before the smoke: the safe candidates
(publication, preparation, fit runtime) touch `PREPARATION_FUNCTIONS` closures or resume identity, so
an extraction now would change the preparation identity or resume semantics for no scientific gain.
Recommended after the smoke (IMP-08).

## 10. Training monitoring architecture

Every `PHASE7_METRICS_EVERY` rounds (default 25): the existing one-line summary plus a block:

```
[fit fold-000/architecture-G0-A6-60m-raw/global] ---- round 250/500 | elapsed 0:41:12 | backend cpu x8 threads | lr 0.02 ----
  loss        train RMSE ...  validation RMSE ...  validation MAE ...  gap (val-train)/train +x%
  best        validation RMSE ... at round 231 | rounds since best 19 (early stopping: validation L2 only)
  validation  [DESCRIPTIVE, fixed subsample, n=250,000 of 518,400]  Pearson ...  Spearman ...  direction ...  xs-IC ...
  predictions mean ...  std ... (x% of target std)  range [..., ...]  finite 100.0%
  actions     [raw return; event |actual| >= 5 bps, action |predicted| >= 5 bps; DESCRIPTIVE, not selection, not profit]
    LONG  precision 0.512  recall 0.084  F1 0.144  | predicted 4,120 | actual events (support) 24,511
    SHORT precision   N/A  recall 0.000  F1   N/A  | predicted 0 | actual events (support) 23,980
    coverage 1.6%  NO_TRADE 98.4%  action direction hit-rate 0.508
  resources   RSS ... available RAM ... free disk ... | rows train ... validation ... | 109 features
  health      [heuristic] INFORMATIONAL VALIDATION_LOSS_IMPROVING (...)
```
(Values above are illustrative of format only.) End of fit: `FIT_SUMMARY <label>` with best round,
stop reason, telemetry and diagnostics status. The raw `FIT_METRICS` JSON is no longer echoed when the
table is on (it is still written to the log). Real rendering verified on the tiny integration fixture.

## 11. Regression metric definitions

See `docs/research/PHASE7_TRAINING_OBSERVER_METRICS.md` §3 (formula, split, units, frequency, role).
Train/validation RMSE and MAE are unweighted (the weighted L2 stays LightGBM's objective/stopping
metric). Directional accuracy excludes zero actuals; a zero prediction counts as a miss.

## 12. Precision/recall definitions

`action_diagnostics_v1_raw_decimal_inclusive_thresholds`. LONG event `actual ≥ +E`, SHORT event
`actual ≤ −E`, LONG action `pred ≥ +P`, SHORT action `pred ≤ −P`, inclusive; E = P = 5 bps raw
(`training_diagnostic_event_threshold_bps`, `training_diagnostic_prediction_threshold_bps`,
predeclared, never optimised; 5 bps carries over the earlier predeclared `fixed_threshold_bps`).
Precision = TP/actions, recall = TP/events (support), F1 = 2TP/(2TP+FP+FN). Zero is never an event or
an action (thresholds must be strictly positive and, per the concurrent fix, still positive after
conversion to raw). Hand-calculated tests: the brief's LONG example (TP 2, FP 1, FN 0, P 2/3, R 1,
F1 0.8), its SHORT mirror, mixed cross-errors, all-correct, all-wrong, no predictions, no events, ties
on the threshold, zeros, NaN exclusion, empty input. MCC/balanced accuracy deliberately not added.

## 13. Normalized-target unit fix (MR-28)

Predictions are multiplied by `max(|ex_ante_volatility_scale|, normalization_floor)` — the same divisor
as the forward transform and `targets.effective_normalization_scale` — before any bps threshold.
Tested at scale > floor, = floor, < floor, = 0 and negative; the divisor is positive so no sign
inversion. A row-by-row unit guard (`y * divisor == raw_future_return`) disables diagnostics
(`UNAVAILABLE:TARGET_UNIT_MISMATCH`) instead of printing wrong-unit numbers. A test shows that the old
behaviour (bps threshold on normalised values) gives different answers.

## 14. Undefined metric handling

Zero denominator → JSON `null`, `*_status = NOT_DEFINED`, a reason code; console `N/A`; support and
predicted counts always shown. A printed `0.000` is a genuine zero. Non-finite values in any JSON
record become `null` (`json_safe`). Correlations of constant inputs / <2 rows and IC with <5 assets per
timestamp are `null`. Verified in the integration fixture: `LONG precision N/A | predicted 0 | events 277`.

## 15. Training telemetry schema

`training_telemetry_v1`; full field lists in the metrics doc §7. One `fit-<attempt>.jsonl` per attempt,
fsynced per record, `check_id = attempt:iteration` (unique, tested). Classes `DEVELOPMENT_METRIC` /
`DESCRIPTIVE_VALIDATION_DIAGNOSTIC`; diagnostic records carry `selection_eligible=false`,
`independent_evidence=false`. `FIT_FINISHED` also records `fit_seconds` and the cumulative Python
custom-metric seconds (PERF-01 measurement).

## 16. Early stopping ownership

`lgb.early_stopping(50, first_metric_only=True)`; the first metric is LightGBM's built-in `l2` on the
eval set named `validation`; the `train` eval set is skipped by LightGBM (`_is_train_set`). Cal-A,
Cal-B and TEST are never passed to `fit`. Action/regression diagnostics are computed in the callback
from a separate predict and cannot feed back. Tests: existing
`test_fit_metrics_do_not_change_predictions_or_early_stopping` (4 variants) and new
`test_diagnostics_never_change_the_fit_or_early_stopping` (diagnostics active at 1 bps and 50 bps:
identical `best_iteration_`, bit-identical predictions, observer best round == LightGBM's). The
concurrent reviewer added 4 more equivalence fixtures (raw/normalised × weighted/unweighted).

## 17. Split isolation

The diagnostics context is built only from the Validation table; `TrainingDiagnostics` only receives
the Validation matrix passed to `_fit` (spy test: every predicted matrix equals `validation_x`). The
observer modules contain no reference to `release_test`, Cal-A, Cal-B or holdout (source test). TEST is
still released only after model, calibrator and Cal-B thresholds are frozen (`release_test` with the
frozen identity, unchanged). Cross-sectional IC groups only rows sharing a Validation timestamp; the
sampler keeps whole timestamps (concurrent fix: within the row cap). Sidecar context is unaffected
(observer reads predictions and targets only).

## 18. Baseline fairness

Contract `baseline_contract_v3_matched_full_train_fit_weighted_ridge`. `ridge` is now
`MATCHED_RIDGE_BASELINE_V3`: exact weighted normal equations over **all** TRAIN rows (blocked, bounded
memory; 109×109 system), TRAIN-only weighted standardisation, the **same weights** as the global fit
(symbol-balanced from TRAIN symbol counts), predeclared alpha, same Validation rows and target units as
LightGBM, zero and TRAIN-mean (now fit-weighted) baselines. Tested against a closed-form weighted ridge
and against v2 when no subsampling occurs. The v2 Ridge is kept as
`ridge_approximate_v2_strided_unweighted` (`APPROXIMATE_NOT_MATCHED_AUDIT_ONLY`). Remaining
non-identity, disclosed in `baseline_fairness`: Ridge has no symbol one-hot (relevant to the symbol-id
ablation) and is a pooled reference for C0/P0. All baseline deltas are DEVELOPMENT metrics (Validation
also drives early stopping). Status: **PARTIAL** (exact for G0/H0, the smoke's architecture).

## 19. Configuration architecture

Every `HardeningConfig` field has one class in `hardening.SETTING_CLASSES` (MONITORING, LEGACY,
DIAGNOSTIC_DEFINITION, BASELINE, OPERATIONAL, SUCCESS_CRITERIA); a test enforces completeness and that
`experiment_identity.MONITORING_ONLY_SETTINGS` matches. New fields are validated (finite, positive,
integer minima). `resolved_monitor_manifest()` gives value, default, unit, class and source (DEFAULT /
TOML / ENV) and is written to the training report and `DIAGNOSTICS_BOUND`. Not done: a single typed
resolved object spanning `Phase7Config` + hardening + env (IMP-07, after smoke).

## 20. Identity impacts

| Identity | HEAD | Final | Why |
|---|---|---|---|
| Preparation (cache matrix) | `07b510b1…31581` | `07b510b1…31581` | unchanged (tested invariant) |
| Scientific source | `920a43fc…6302` | changed | `training.py`, `models.py`, `training_metrics.py` edited (expected; no completed run to resume) |
| Experiment control | changed | changed | `hardening.py` (baseline v3), `action_metrics.py`, `fit_boundary.py` (concurrent fix) are control sources; monitoring-only settings excluded |
| Configuration hash | unchanged | unchanged | no research TOML change |

Monitoring settings, console format, interval and JSONL location change no identity (tested).
Diagnostic thresholds change the control identity only (tested). LightGBM parameters change the
configuration hash and so model/checkpoint identity (tested).

## 21. Cache impacts

None. No preparation file or function changed; preparation identity is identical. Note CACHE-01: the
prepared-cache key also includes the whole `configuration_hash`, so a pure LightGBM/resource/cost change
would (conservatively) invalidate matrices. Safe direction; deferred.

## 22. Performance overhead

Synthetic, single thread, 300 rounds, 100k train × 109, 50k validation (a deliberately pessimistic
validation:train ratio). Wall-clock on this Mac varies ±25% between identical runs; in-run timings are
the reliable figures.

| Measure | Result |
|---|---|
| Observer off / base observer / + diagnostics (min of 3, after fixes) | 13.1 s / 15.5 s / 17.8 s |
| Time inside diagnostic checks, full re-predict each check (before OBS-04) | 1.5 s (with the thread leak) |
| Same after incremental prediction + thread pin | 1.28 s = 7.2% of this fixture's fit |
| One check at smoke scale, full re-predict (250k rows, 109 features) | 1.5 s @100 trees, 3.6 s @250, 6.8 s @500 → ~70 s per 500-round fit before OBS-04 |
| Metric computation only (no predict), 250k rows, with xs-IC | 0.11 s |
| Pre-existing base observer (Python metric on TRAIN+Validation every round) | +18–24% on fixtures (PERF-01) |

Scaling estimate for the smoke (ESTIMATED): diagnostics ≈ 1–2% of fit time after OBS-04; PERF-01 may
be ~10–20% and is now measured in-run (`scope_custom_metric_seconds` vs `fit_seconds` in `FIT_FINISHED`).

## 23. Reproducibility

Report block contains only deterministic fields (`report_view`); verified by the existing tiny-pipeline
reproducibility test, which failed before OBS-05. Diagnostic subsample seed 20261108 fixed. CPU fits
remain `deterministic=True, force_col_wise=True`. Recorded already: git commit, configuration hash,
scientific source identity, environment identity (Python, NumPy, PyArrow, LightGBM, scikit-learn,
platform), backend metadata, thread budget, seed, spec, fold, Gold id/manifest, sidecar hash, control
identity, hardening config. Added: resolved monitor settings, fit-boundary summary, sample-weight
summary (min/max/mean/per-symbol share; uses no target information).

## 24. Crash/resume safety

New attempt → new log file (never appended), `FIT_STARTED` lists prior attempts and
`resumed_after_incomplete_attempt` (tested). Telemetry write failure (disk full) → one
`TELEMETRY_DEGRADED` line, fit continues, identical model, no log file, nothing claims completion
(tested). Diagnostics exceptions → contained, disabled after 3 (tested). The canonical ledger, model
save, receipts and atomic publication code are unchanged and remain the only completion authority.
One new hazard found and fixed: timing code inside the LightGBM metric callback initially raised
(`FrozenInstanceError`) and killed the fit — any exception there is fatal, so it is now suppressed.

## 25. Holdout safety

No new code reads data. July unused, August `LOCKED_UNUSED`, `used=false`,
`evaluation_authorized=false` (config literals unchanged; existing holdout tests pass).

## 26. Live-order isolation

No new imports outside NumPy/PyArrow/LightGBM and Phase 7 modules; existing import-boundary and
live-order isolation tests pass with no skips.

## 27. Funding architecture recommendation

`docs/research/PHASE7_FUNDING_AND_EXECUTION_ARCHITECTURE.md`: per-settlement record (symbol,
funding_time, exact decimal rate, rate_known_time, mark price, derived interval), cash flow
`−side × qty × mark × rate`, summation over settlements inside the holding interval. Sign and boundary
conventions must be verified against current official Binance docs before code; missing funding is
reported, never filled. Remains `NOT_MODELLED`, not in the smoke.

## 28. Execution/portfolio architecture recommendation

Strict downward layers FORECAST → ACTION POLICY → TRADE SIMULATION → COST → FUNDING → POSITION →
PORTFOLIO → RISK, LIVE EXECUTION never imported. `CostModel.cost_bps(...)` interface lets volatility/
liquidity/depth costs replace `STATIC_COST_STRESS` (11/14/20 bps scenarios) without touching labels.
`REFERENCE_EXECUTION_PRICE` remains a label, not a fill.

## 29. Multiple-testing recommendation

Register every attempted spec/seed/hyperparameter in the trial ledger before it runs; the smoke is
`REGRESSION_PLUMBING_AND_PIPELINE_SMOKE` (selection protocol CLI) and is not a discovery trial. No Fold-0
number may authorise tuning. Before any claim: pre-registered fold split (development vs evaluation),
paired OOS comparison vs the matched baseline, and family-wise control over all registered trials
(the configured Bonferroni or a deflated-Sharpe style correction for economics).

## 30. Architecture improvements completed (DONE_NOW)

Files: new `fit_boundary.py`; edited `models.py`, `training.py`, `training_metrics.py`,
`training_observer.py`, `hardening.py`; tests `test_training_observer_diagnostics.py` (63 tests) plus 3
updated tests; docs `PHASE7_TRAINING_OBSERVER_METRICS.md`, `PHASE7_FUNDING_AND_EXECUTION_ARCHITECTURE.md`,
this report. (`action_metrics.py`, `regression_diagnostics.py`, the `hardening`/`experiment_identity`
settings work and the TOML were authored by the previous session; reviewed, lint-fixed and tested here;
the concurrent reviewer also edited them.)

## 31. Architecture improvements deferred

PERF-01 check-round-only custom metrics; CACHE-01 narrower cache key; IMP-07 single typed resolved
config; IMP-08 training.py decomposition; funding/cost/portfolio implementation; Ridge with symbol
one-hot for the symbol-id ablation.

## 32. Error register

| ID | Sev | Status | File / function | Problem | Reproduced | Scientific impact | Engineering impact | Fix | Test | Identity | Cache | RunPod / Smoke / Pilot / Tradability blocker |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OBS-01 | HIGH | FIXED | models._fit, training.run_experiment | observer diagnostics never bound; P/R never shown | grep: `bind_validation` had no caller | none (monitoring) | requested observability absent | wire context + bind (masks for C0/P0) | integration output, `test_telemetry_records_carry_the_required_schema` | scientific source | none | N / N / N / N |
| OBS-02 | MED | FIXED | regression_diagnostics, training_observer, 2 tests | suite red, Ruff red | baseline run | none | gates fail | lint/format fixes; tests updated to MR-28 semantics | full suite | none | none | Y(gate) / – / – / – |
| OBS-03 | HIGH | FIXED | training_metrics._incremental_predict | `predict()` in callback without `num_threads` switches remaining training to all cores | rounds 7–60 took 0.67 s vs 1.75 s after one default predict | none on values (deterministic) | breaks CPU admission/thread budget, oversubscribes pod | pin `num_threads` = fit threads (also final snapshot) | `test_in_fit_predictions_pin_the_fit_thread_budget` + benchmark ordering | scientific source | none | Y / Y / Y / – |
| OBS-04 | MED | FIXED | same | full re-predict every check: O(trees²), est. 4–9% of smoke | timed 1.5–6.8 s/check at 250k rows | none | cost | cached additive GBDT prediction | `test_incremental_validation_prediction_matches_full_predict` (1e-12) | scientific source | none | N / N / N / N |
| OBS-05 | MED | FIXED | training report | attempt ids, timings, resource flags in report → irreproducible | `test_tiny_pipeline_connects_and_is_reproducible` failed | reproducibility | – | `report_view` | that test + unit test | scientific source | none | – |
| OBS-06 | LOW | FIXED | FitMetricObserver.__call__ | JSON line duplicated the table every check | visual | none | console flood | echo only when table off | existing tests | scientific source | none | – |
| MR-28 | MED | FIXED | training_metrics.display_metrics / action_metrics | normalised predictions thresholded as raw bps; undefined → 0.0 | source + `test_normalized_predictions_are_converted_to_raw_before_bps_thresholds` | misleading diagnostics | – | raw conversion with effective divisor; NOT_DEFINED | 15+ tests | control (action_metrics) | none | N / N(raw smoke) / Y(normalised specs) / – |
| MR-26 | MED | PARTIALLY_FIXED | hardening.score_baselines | Ridge strided/unweighted vs weighted full G0 | code inspection | unfair baseline | – | v3 exact matched Ridge; v2 kept as APPROXIMATE | 4 tests | control | none | N / N / Y(C0/P0 disclosure) / Y |
| FB-01 | MED | FIXED | fit_boundary | no row/order/dtype/finite/weight/purge/duplicate checks at fit time for cache-reloaded matrices | fixture violating purge passed silently | leakage guard | – | `assert_fit_matrices`, `assert_fit_segments`, `prediction_health` | 4 tests | control (concurrent fix) | none | N / Y(safety) / Y / – |
| FB-02 | LOW | FIXED | tests `_fold_data` | fixture had Train == Validation with labels past validation start | FB-01 fired | test realism | – | Train rows one day earlier | 6 tests | – | – | – |
| CX-1..4 | MED | FIXED (concurrent reviewer) | action_metrics, training_observer, regression_diagnostics, experiment_identity | threshold underflow; sample over row cap; prediction distribution population; fit_boundary missing from control identity | their evidence dir | diagnostics/identity | – | their patches | `test_local_review_diagnostics.py` | control | none | – |
| CX-5 | LOW | FIXED | hardening.matched_ridge_predict | malformed `block_rows` silently coerced | their verification json | none | – | guard | `test_matched_ridge_rejects_malformed_block_sizes` | control | none | – |
| PERF-01 | MED | OPEN (instrumented) | display_metrics | Python metric on full TRAIN+Validation every round | +18–24% on fixtures | none | runtime | measure on smoke; then check-round-only metrics | timing recorded in FIT_FINISHED | – | none | N / N / consider / – |
| CACHE-01 | LOW | DEFERRED | training._prepared_cache_identity | cache key includes whole config hash (models/resources/costs) | code inspection | none (over-invalidation) | rebuilds | narrow to data/feature/target/fold config | – | preparation (would change) | would change | N |
| PARAM-01 | LOW | OPEN (NEEDS_JUSTIFICATION) | ModelConfig | 500 rounds at lr 0.02 may end at ROUND_LIMIT before early stopping | tiny fixture stopped at ROUND_LIMIT | possible underfit | – | none pre-smoke; read `stop_reason` on smoke | – | – | – | N / N / review before pilot / – |
| FUND-01 | HIGH | OPEN | economics | funding cash flows NOT_MODELLED | by design | economics invalid for tradability | – | design doc | – | – | – | N / N / N / Y |
| EXEC-01 | HIGH | OPEN | economics | reference-price fills, static costs, no portfolio | by design | as above | – | design doc | – | – | – | N / N / N / Y |
| CONC-01 | MED | OPEN | process | two agents editing the same files concurrently | file mtimes, concurrent review report | none if merged | source export risk | freeze one export after both finish, re-run full suite there | – | – | – | Y (process) |
| EXT-* | HIGH | EXTERNAL_RUNPOD_REQUIRED | – | Linux x86, filesystem, cross-host identity, real cache, ≥64 GiB resources | – | – | – | Wednesday | – | – | – | Y / Y / Y / Y |

## 33. Improvement register

| ID | Current | Problem | Proposed | Why | Risk | Effort | Scientific effect | Runtime | When |
|---|---|---|---|---|---|---|---|---|---|
| IMP-01 | observer dead code | no live P/R | wired observer | requested visibility | low | done | none | +1–2% est. | DONE_NOW |
| IMP-02 | full re-predict | quadratic | incremental | cost | low | done | none | −~70 s/fit | DONE_NOW |
| IMP-03 | approx Ridge | unfair | matched v3 | fair comparison | low | done | baseline semantics (versioned) | +seconds | DONE_NOW |
| IMP-04 | no fit-boundary checks | cache reload trust | fit_boundary | fail closed | low | done | none | ~1 s | DONE_NOW |
| IMP-05 | per-round Python metric | 10–20% est. | metrics only on check rounds; best round from built-in l2 | cost | medium (callback contract) | S | none | −10–20% | ON_RUNPOD_BEFORE_SMOKE decide from measured `scope_custom_metric_seconds`, else AFTER_SMOKE |
| IMP-06 | cache key has full config hash | over-invalidation | data-only config projection | fewer rebuilds | medium (cache identity) | S | none | rebuild avoidance | AFTER_SMOKE |
| IMP-07 | config split over TOML/hardening/env | provenance spread | one typed resolved config + manifest | clarity | low | M | none | none | AFTER_SMOKE |
| IMP-08 | 2.3k-line training.py | maintainability | extract publication / fit runtime | clarity | medium | M | none if identity-neutral | none | AFTER_SMOKE |
| IMP-09 | pooled Ridge for C0/P0, no symbol one-hot | partial fairness | per-partition Ridge; Ridge+one-hot for ablation | fairness | low | S | baseline | small | BEFORE_PILOT |
| IMP-10 | no funding/costs/portfolio | no economics | per design doc | tradability | high | L | economics | – | BEFORE_TRADABILITY |
| IMP-11 | 500-round cap | possible ROUND_LIMIT | pre-registered cap review from smoke stop_reason (not tuning) | avoid underfit | low | XS | model | – | BEFORE_PILOT |

## 34. Full test results (final)

Final source state (includes the concurrent reviewer's files), 2026-11-08:

* `uv run pytest -q`: **1471 passed, 0 failed, 0 errors, 0 skipped** (158 s).
* `uv run ruff check .`: All checks passed. `uv run ruff format --check .`: 748 files already formatted.
* `git diff --check` (src, tests, configs, docs/research): clean.
* New file `tests/phase7/test_training_observer_diagnostics.py`: 63 passed; concurrent
  `test_local_review_diagnostics.py`: passed.
* Identities after: preparation `07b510b1ebacdf80e22ad142861318b1052387973260605cdea509d2a9b31581`
  (= HEAD); Gold, sidecar, feature, target, universe, fold and research-TOML files byte-unchanged vs HEAD.

## 35. Exact RunPod TODO list for Wednesday

1. Confirm both local editors have stopped; `git status`; commit or export one frozen source; record SHA
   and the export manifest; run the full suite on that export (expect 0 failed, 0 skipped).
2. Fresh owner cost/deadline contract before creating any pod.
3. Linux x86_64: `uv sync --locked --extra dev`; full pytest; ruff; `crypto_ai.phase7.verify_linux`.
4. Cross-host identity: compare preparation (`07b510b1…`), scientific, control and environment
   identities Mac vs pod via `identity_summary`.
5. Filesystem qualification of the target volume (fsync/rename/locks).
6. Transfer Gold `gold-phase7-0cbf2910e8d96c9d19826598` + `feature_context_sidecar_v3`; verify hashes.
7. Build the one Fold-0 prepared cache in the separate preparation step; measure RSS/disk; reload
   read-only and prove equivalence.
8. Resource admission on ≥64 GiB / ≥8 CPU / ≥150 GB.
9. Only then, if authorised: `architecture-G0-A6-60m-raw`, Fold 0, CPU, one worker. Watch the block in
   section 10; afterwards read `FIT_FINISHED.scope_custom_metric_seconds / fit_seconds` (PERF-01) and
   `stop_reason` (PARAM-01). Treat every number as plumbing evidence, not skill.

## 36. Final verdict

Scores after changes (0–10, not inflated): Data 8, Lineage 8, Silver 6, Gold 8, Features 7,
HTF timing 7, Cross-sectional context 8, Targets 8, Universe 7, Splits 8, Purging 8, Embargo 8,
Leakage prevention 8, Model design 7, LightGBM setup 7, Training observability 9, Calibration 7,
Thresholding 7, NO_TRADE 7, Baselines 7, Regression metrics 8, Action diagnostics 8, Precision/recall
semantics 9, IC 7, Result ledger 8, Cache identity 8, Scientific identity 8, Configuration 7,
Crash recovery 8, Mac reliability 8, RunPod preparedness 5, Trading metrics 3, Funding 1,
Execution realism 2, Portfolio realism 1, Holdout 10, Live-order safety 9, Documentation 8.

SCIENTIFIC 7/10 · ENGINEERING 8/10 · STATISTICAL RIGOR 5/10 · TRAINING OBSERVABILITY 9/10 ·
REPRODUCIBILITY 8/10 · RUNPOD CODE READINESS 7/10 · TRADING REALISM 2/10.

Safety questions: Validation monitoring cannot see TEST (spy + source tests). Precision/recall cannot
be computed in target units (raw conversion + unit guard). Undefined precision cannot become 0
(NOT_DEFINED tests). Thresholds are config constants, never adapted. Diagnostics cannot affect early
stopping (equivalence tests). Monitoring settings cannot change experiment identity; definitions do
(tests). Telemetry failure cannot mark completion. Resume cannot duplicate rounds within a log; the
ledger is authoritative. Monitoring allocates one sample copy per estimator and one prediction vector
per check. Train/validation rows are checked at the fit boundary. A stale cache still cannot bypass
identity (preparation identity unchanged). No refactor touched Gold/feature/target semantics. August
cannot enter. Research code cannot reach live trading.

**READY_FOR_RUNPOD_VERIFICATION_ON_WEDNESDAY**
