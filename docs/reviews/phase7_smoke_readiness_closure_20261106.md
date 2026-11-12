# Phase 7 smoke-readiness closure report (2026-11-06)

## VERDICT: NOT_READY_FOR_SMOKE

The verdict is not a failure of the code that was written. It is that the READY conditions require
real `pytest`, `ruff check`, `ruff format --check` and real-data census/cache evidence, and **none of those could be executed in this
session**. Nothing below is claimed PASS unless it was actually run. Where something was only
reasoned about or run through a stand-in, it says so.

## 1. Repository state

| | |
|---|---|
| Branch (start and end) | `fix/phase7-final-architecture-repair-20261106` |
| Start | `7bae15a` (verified from git; the old report's `070539e` was not trusted) |
| End | `96d7159` + this report |
| Pushed | No |

Commits (oldest first): 19ae8a4 ledger publication; f5fae0a real selection protocol; e32f68b shared
admission; 299c1c6 preparation-based cache identity; 6a291c9/0cd1953 test style; 0b3dce0 economic
status/proxy naming; bd1bdbd estimator; 72117ce Cal-A label_end purge; 78a2888 H0 data ownership;
7079a6e baseline contract v2; 7ebc79e vol-floor inverse fix; 5c89a62 truncation + import-boundary
tests and order-client guard; 96d7159 Gold hash evidence, superseded-cache registry, smoke yaml and
success-criteria amendment. 37 files changed, +5005/-94 (v. 7bae15a).

## 2. Real environment gate: NOT RUN (environment blocker, documented)

`uv sync --locked --extra dev`, `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`
were **not run**. Reasons, all verified:

* The only shell available to me is a Linux aarch64 VM with Python 3.10 and no route to PyPI or to
  the python-build-standalone download, so `uv sync` cannot create the project's Python>=3.11 env, and
  there is no pyarrow, lightgbm, pydantic or pytest there.
* The Mac helper that would run the repo's own `.venv` (`Claude outputs/Start science runner
  (double-click once).command`) was never started (its last request is still sitting unconsumed).
  Terminal can only be granted to me in click-only mode, so I cannot start it myself, and I did not try to work around that.

Consequences: every test and every line of new code in this report is **unexecuted under the real
stack**. What was executed instead is limited and labelled stand-in evidence:

* pure-numpy logic of the Cal-A purge (12 test cases, stubbed config), the cross-sectional IC
  helper, the vol-floor arithmetic, and the static import-boundary scan (stdlib only).
* hand-checked line length (<=100) and syntax (`ast.parse`) of every touched file. Import
  ordering and `ruff format` conformance are **unverified**; expect some reflow on the first real run.

## 3. Items closed in code (committed, not yet run under real pytest)

| Item | State |
|---|---|
| Ledger wiring | model -> report -> canonical record (full identity validated, no defaults) -> hashed receipt -> checkpoint COMPLETE -> CSV is a regenerable ledger view. Fault seams exist at every named crash point. The seven crash/resume tests are written but **not executed**. |
| Duplicate prevention | ledger key = run/spec/fold; second publication with the same identity is idempotent, different content is rejected; unexecuted. |
| Selection protocol | `configs/research/phase7_selection_chronology_v1.json` generated from the real 16 folds: TRAIN/VAL/CAL-A/CAL-B/TEST calendars, full overlap matrix, purposes DESCRIPTIVE_REPORT / DEVELOPMENT_SELECTION / INDEPENDENT_EVALUATION, smoke (fold 0 only) and pilot (precommitted spec; folds 1-10 development, 11-16 evaluation) documented before any result. Role-aware gate `authorize_use` rejects an evaluation whose TEST overlaps any segment of any development fold. Unexecuted tests. |
| Generic CLI admission | one `admit_official_training`; generic `phase7-research train` and legacy entrypoints raise `NON_CANONICAL_RESEARCH_ENTRYPOINT`; unexecuted tests. |
| CPU enforcement | smoke requires CPU and one worker; env vars cannot switch it; a GPU request fails closed (`GPU_NOT_QUALIFIED`) without an approved qualification file; unexecuted tests. |
| Cache identity | new `preparation_identity` (matrix-affecting code only) with `PREPARATION_SEMANTICS_VERSION`; economics/selection/ledger edits no longer invalidate matrices; feature/context/target/fold/membership changes do. The one existing cache is registered `SUPERSEDED_NOT_REUSABLE` (`docs/reviews/evidence_closure/superseded_caches.json`; nothing deleted; its identity has no preparation fields so the new identity cannot match). |
| Resource estimator | "upper bound" removed; values labelled MEASURED / ESTIMATED_AVERAGE / ESTIMATED_HEURISTIC_PEAK; adds rows, raw matrix bytes, Arrow bytes, cache bytes, physical and available RAM, free disk, cgroup RAM limit and CPU quota (v1/v2), `--json`. Old test deliberately updated (old asserts kept as comments). |
| Cal-A | internal selection split now purged by actual `label_end_time` + embargo, identity fallback when too few rows survive; Cal-B/TEST are not parameters. Tests for 15/30/60/120. |
| H0 | corrections now fit on the purged first part of Cal-A, calibrator on the later part, Validation = early stopping only; official run fails with `H0_CORRECTION_NOT_INDEPENDENT_OF_EARLY_STOPPING` otherwise. This changes H0 results versus earlier versions. |
| Baselines | contract v2: zero, TRAIN-mean, fixed Ridge on the same eligible rows, plus cross-sectional IC; no extra information. |
| Metric naming | trade Sharpe -> proxy name; `portfolio_sharpe`, `portfolio_max_drawdown` = NOT_AVAILABLE; `trade_drawdown_proxy`. |
| Funding / costs | `funding_model_status = NOT_MODELLED`; any tradability claim fails; `STATIC_COST_STRESS`, `REFERENCE_EXECUTION_PRICE` in every report. |
| Vol-floor inverse | **real defect reproduced and fixed**: the forward target divides by `max(|scale|, floor)` but the inverse multiplied by the raw scale. Scale 1e-10 returned 0.000123 instead of 0.0123, scale 0 returned 0, negative scale flipped sign. Real scales are ~1e-3 so the live effect is likely nil, but the inverse is now correct. Forward transform, raw target and Gold unchanged, so prepared caches stay valid. |
| Truncation invariance | test written (native, 12h/1d, multi-symbol, cross-sectional, gaps before/after T, three cutoffs, plus a negative control). **Not executed** (needs pyarrow). |
| Import boundary | static test **executed standalone and passed**: 155 `crypto_ai` modules scanned, none import `pipeline`, `main_trader`, `main_signal`, `dashboard`, `aiventra` or coinswitch; the 85-module Phase 7 closure has no order-function name. Runtime guard: `CRYPTO_AI_RESEARCH_MODE=1` (set by admission) makes `CoinSwitchClient` refuse construction. This is the only edit to live-side code; it is inert when the variable is unset; no credentials touched. |
| Smoke yaml / criteria | `phase7_primary_smoke_v1.yaml`: fold index 0, CPU, REGRESSION_PLUMBING_AND_PIPELINE_SMOKE, cache read-only after preparation, isolated output. `PHASE7_SUCCESS_CRITERIA_V1.md` section 5 now lists engineering-only criteria, kept separate from later pilot criteria (amended before any result existed). The yaml is still declarative; the enforced values are in admission. |

## 4. Gold verification (real data, read-only): PASS for hashes and manifest

`scripts/closure/verify_gold_hashes_readonly.py` (stdlib; evidence in
`docs/reviews/evidence_closure/gold_hash_verification.json`):

* dataset `gold-phase7-0cbf2910e8d96c9d19826598`; manifest SHA-256 `a1420277...2e711`
* 138/138 partition files present, 138/138 SHA-256 match the manifest, 9,672,256,838 bytes, no unlisted or missing file
* 109 feature columns; `multiasset_features_v2`; `multiasset_targets_v2`; row_count 50,352,548 (= sum of chunk counts)
* research cutoff 2026-07-01; holdout start 2026-08-01 `LOCKED_UNUSED`, used=false, evaluation_authorized=false; `july_2026_used=false`

**Not verified** (needs pyarrow): Parquet schema, physical columns, per-file row counts, timestamp bounds. `scripts/validate_phase7_gold.py` must be run on the Mac runner. Gold was only read.

## 5. M-01 census: NOT RUN -> DATA_INSUFFICIENT (by my own rule)

The census tool is implemented and its core logic was checked on six synthetic scenarios earlier,
but the real run needs pyarrow and the independent feature source (Silver candles under
`~/Crypto2Data/.../data/phase7/silver`), so no loss figures exist: no key counts, lost %, interior/terminal/per-symbol/per-fold/per-split numbers. Category: **DATA_INSUFFICIENT**. A `FEATURE_CONTEXT_SIDECAR` was
neither needed nor built because the materiality is unknown; if the census finds MATERIAL_LOSS it is still required.

## 6. Cache qualification: NOT DONE

Fold 1 CORE/A6/60m/raw was not prepared or qualified (prerequisites unmet: tests, census, Linux). No training was started, no model was fit, August was not accessed, no trade was placed, and no GCS/Binance download occurred.

## 7. Linux gate: LINUX_PENDING. `verify_linux` was not run on Linux and no Linux PASS is claimed. `--help` checks for preflight, resource_estimate, benchmark_one_spec and feature_census were not run.

## 8. READY conditions

| Condition | Met? |
|---|---|
| pytest PASS | NO (not run) |
| ruff check PASS | NO (not run) |
| ruff format PASS | NO (not run) |
| Gold verification PASS | PARTIAL (hashes/manifest yes; schema/rows no) |
| M-01 acceptable or sidecar installed | NO (not run) |
| ledger wired | yes in code, unexecuted |
| identity enforced | yes in code, unexecuted |
| protocol generated | YES |
| generic CLI bypass closed | yes in code, unexecuted |
| CPU enforced | yes in code, unexecuted |
| cache scientifically valid | NO (none qualified) |
| resource preflight meaningful | code yes, never run on real data |
| August locked | YES (manifest, never accessed) |
| live-order boundary protected | YES (static scan executed + guard) |
| no unresolved P0 scientific defect | cannot be asserted without the census |

## 9. Final self-attack checklist (YES = must be fixed or verdict stays NOT_READY)

1. Duplicate result records? Guarded in code; crash tests unexecuted -> **UNPROVEN**.
2. CSV disagrees with ledger? CSV regenerated from ledger with a match check; unexecuted -> **UNPROVEN**.
3. Partial run appearing complete? COMPLETE lists ledger files; unexecuted -> **UNPROVEN**.
4. Mixed-identity resume? Full identity validated; unexecuted -> **UNPROVEN**.
5. Later validation as independent evidence after overlapping earlier TEST? Blocked by `authorize_use`; unexecuted -> **UNPROVEN**.
6. Whole-timestamp M-01 loss escaping detection? Detector exists; **real data never checked -> YES (unknown)**.
7. Stale prepared matrices accepted? Old cache cannot match new identity by construction -> NO, pending real test.
8. Cal-B entering a fit? Not a parameter of Cal-A purge/H0 split -> NO.
9. TEST affecting thresholds? Thresholds come from Cal-B -> NO.
10. August accessed? NO.
11. GPU running in the CPU smoke? Fails closed in code; unexecuted -> **UNPROVEN**.
12. Generic CLI bypassing admission? Closed in code; unexecuted -> **UNPROVEN**.
13. Negative expectancy forcing a trade? NO_TRADE handling was added earlier; unexecuted.
14. Trade-level Sharpe shown as portfolio Sharpe? NO (renamed, portfolio fields NOT_AVAILABLE).
15. Funding absence hidden? NO (`NOT_MODELLED` in every report).
16. Resource preflight underestimating silently? It is labelled a heuristic and not a guarantee; the real run was never compared with a measurement -> **UNPROVEN**.
17. Research importing live-order code? NO (static scan executed).

Because items 6 (and several UNPROVEN ones) cannot be cleared without the real stack, the verdict remains NOT_READY_FOR_SMOKE.

## 10. Remaining risks

* A large amount of new code is untested under the real stack: expect failures on the first real run, especially import order/format, the
  existing `test_pretraining_integration`, `test_pre_lightning_finalization`, `test_hardening_audit`, and the H0 tests (H0 now needs
  >=100 Cal-A2 rows for the calibrator; small synthetic fixtures may need adjusting, not weakening).
* H0 results are no longer comparable with earlier H0 runs.
* Held-out Cal-A split and purge reduce calibrator rows.
* M-01 materiality unknown.

## 11. What must happen next (in this order)

1. Start the Mac science runner once (double-click the `.command`), or run the four gates in a Mac terminal: `uv sync --locked --extra dev`, `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`; fix what fails without weakening tests.
2. `uv run python scripts/validate_phase7_gold.py` (schema/columns/rows) and the real `feature_census` against Silver.
3. If the census is MATERIAL_LOSS, build the sidecar; then resource preflight, then qualify one Fold 1 cache, then Linux `verify_linux`.
4. Re-issue this report. Only if all conditions in section 8 hold does it become `READY_FOR_ONE_CPU_SMOKE_ONLY`; the exact command sequence will be derived from the then-current CLI. No training command has been derived or executed.
