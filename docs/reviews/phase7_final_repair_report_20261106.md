# Phase 7 final repair report (2026-11-06)

Written by Claude (Cowork) for sharath. Repository `crypto2.0`, branch `fix/phase7-final-architecture-repair-20261106`.

## 0. Verdict

**NOT_READY_FOR_SMOKE**

The new code is written and committed, but the three gates a smoke run needs have not been passed: the real `pytest` / `ruff` run on this branch (the Mac test runner was offline for the whole session), the real-Gold read-only verification with a qualified prepared cache (needs the Mac and pyarrow; this sandbox has neither), and the M-01 feature-key census on real data. Nothing here is claimed as passing that was not executed.

## 1. Branch, SHAs, scope

- Start: `c249e28` on `fix/phase7-final-architecture-repair-20261106` (from the audit branch lineage a99f14c -> ... -> 687e697 -> c249e28).
- End: `070539e` (nothing pushed).
- Commits (all with finding IDs): `d4c0825` IA-01/IA-02, `f5f8d33` IA-03, `32d594a` IA-04, `10006f6` IA-20, `60d6a86` NO_TRADE (message says IA-12; the correct ID is **IA-15**, corrected in code comments by the last commit), `a4db0e7` IA-05 census, `9191665` success criteria + smoke config, `070539e` ID correction.
- Files changed (14, +1476/-66): `src/crypto_ai/phase7/{result_integrity,selection_chronology,experiment_identity,result_ledger,feature_census}.py` (new), `hardening.py`, `training.py`, `economics.py` (modified), `tests/phase7/{test_phase7_final_integrity,test_feature_census}.py` (new), `test_phase7b_hardening.py`, `test_standalone_training_remediation.py` (modified), `docs/research/PHASE7_SUCCESS_CRITERIA_V1.md`, `configs/research/phase7_primary_smoke_v1.yaml` (new).
- Not committed on purpose: `Claude outputs/` helper scripts, `docs/reviews/evidence_crypto2_20261106/`, and five edited audit docs under `docs/reviews/` that were already modified before this task.

## 2. Findings table

Status words: FIXED / PARTIALLY_FIXED / DEFERRED / REQUIRES_REAL_DATA / NOT_REPRODUCED / ALREADY_FIXED. "Verified" below means code written and, where stated, run in the sandbox harness; **no real pytest run exists for this branch**.

| ID | Topic | Status | What was done / why |
|---|---|---|---|
| IA-01 | Invalid inference | FIXED (code) | Validation doubles as early-stopping data, so p-values / Bonferroni "pass" were removed. `descriptive_ranking` returns `NOT_INDEPENDENT`, `p_values=NOT_APPLICABLE`; `evaluate_success` returns `DESCRIPTIVE_ONLY`, `qualifies_as_independent_evidence=False`. Terminology constants DEVELOPMENT_METRIC / SELECTION_METRIC / INDEPENDENT_EVALUATION_METRIC in `result_integrity.py`. |
| IA-02 | Result identity | PARTIALLY_FIXED | `validate_result_set` rejects duplicates, missing folds, non-COMPLETE rows, missing or mixed identity. Result rows now carry seed, feature_set, backend, scientific_code_identity, hardening_identity, baseline_contract_version. **Not yet enforced where results are written** (see IA-20). |
| IA-03 | Selection chronology | PARTIALLY_FIXED | `overlap_matrix` (fold-000 TEST reused as fold-002 VALIDATION is detected), immutable tamper-evident `selection_chronology.json` writer/loader, `selection_eligible_ranking` refuses development/evaluation overlap. The real protocol file has **not** been generated for a real run. |
| IA-04 | Identity split | PARTIALLY_FIXED | `experiment_control_identity` (hardening/selection/ledger source + active settings) is bound into checkpoint/resume identity and recorded in the report. `hardening.py` is not in the cache-critical file list (tested). **Caveat:** `training.py` and `economics.py` ARE cache-critical, and I edited both, so every prepared cache built before this branch has a different code identity and is not reusable. The monolithic `training.py` is why the split cannot be clean (P3 modularisation, deferred). |
| IA-05 / M-01 | Context completeness | PARTIALLY_FIXED / REQUIRES_REAL_DATA | `feature_census.py` (read-only, refuses to overwrite its output) compares independent feature keys with Gold keys: lost keys terminal vs interior, per-symbol, per-window, timestamps with all peers lost, pre-declared materiality thresholds. Core logic ran in the sandbox (6 scenario checks OK). Context tests added (duplicate-horizon invariance; a vanished peer changes the context hash). **Real-data census not run; sidecar design not written; M-01 is NOT closed and "acceptable bounded" is not claimed.** |
| IA-06 | Funding | DEFERRED | Funding is still `NOT_MODELLED`. Scientific blocker for any tradability claim. |
| IA-07 | Execution realism | DEFERRED | Static cost scenarios unchanged; no volatility/liquidity stress. |
| IA-08 | Trade vs portfolio metrics | DEFERRED | Naming not changed; trade-level Sharpe must not be quoted as portfolio Sharpe. |
| IA-09 | Verification gates | NOT_RUN | Runner offline. |
| IA-10 | Real Gold / cache | REQUIRES_REAL_DATA | No Gold manifest, hash, schema, 109-feature check or cache qualification performed. Stale caches are classified SUPERSEDED_NOT_REUSABLE by identity mismatch only; nothing deleted. |
| IA-11 | Admission coverage | DEFERRED | `benchmark_one_spec --execute` is guarded (cloud-allowed check, runtime contract, Gold validation, preflight). Generic `crypto-ai phase7-research --stage train` is not, and is not labelled NON_CANONICAL. |
| IA-12 | GPU qualification | DEFERRED | No approval-marker enforcement added. |
| IA-13 | Cal-A internal split | DEFERRED | |
| IA-14 | H0 data reuse | DEFERRED | |
| IA-15 | Threshold selection | FIXED (code) | `select_cal_b_thresholds` now treats NO_TRADE as a candidate: a group trades only if its best eligible Cal-B net expectancy is strictly positive; decision recorded per group. Two tests added; existing positive-return tests are unaffected. |
| IA-16 | Baseline fairness | PARTIALLY_FIXED | `baseline_contract_version` and `metric_class=DEVELOPMENT_METRIC` stamped on baselines. Cross-sectional IC in validation baselines not added. |
| IA-17 | Vol-floor inverse | DEFERRED | Not reproduced or fixed. |
| IA-18 | Diagnostic units | DEFERRED | |
| IA-19 | Resource bound wording | DEFERRED | "UPPER_BOUND" wording and cgroup detection unchanged. |
| IA-20 | Result table crash recovery | PARTIALLY_FIXED | `result_ledger.py`: atomic per-fold result + receipt, corruption detection, idempotent resume, trial ledger, CSV as a view. **Not wired into `_run_one`; the CSV is still what the run path writes.** |
| IA-21 | Artifact trust | DEFERRED | |
| IA-22 | Feature redundancy / truncation test | DEFERRED | |
| IA-23 | RunPod operations | DEFERRED | RunPod not started. |
| IA-24 | Universe evidence | DEFERRED | `universe_provenance_report.json` not produced. |

I read the full text of IA-01 to IA-06, IA-10 and IA-11 in this session; for the others I worked from the titles and the earlier audit summary, so "DEFERRED" means not addressed, not "reviewed and accepted".

## 3. Tests and tooling

- Tests added: `test_phase7_final_integrity.py` (24 tests: duplicates / replay / missing / mixed identity, overlap matrix, protocol immutability and tamper, selector rejection, control identity, ledger), `test_feature_census.py` (8), two NO_TRADE tests, two ranking/duplicate tests replacing the old Bonferroni test.
- Failing-first: not demonstrated with a real runner. The replaced Bonferroni test was removed because it asserted the now-invalid behaviour; that is a deliberate semantic change, not a weakened check.
- Executed: the 24 integrity tests and the census core logic passed in the sandbox harness (stdlib/numpy only, with shims). **The pyarrow-dependent tests (context tests, NO_TRADE tests, ranking tests) have never been executed.**
- `pytest` full suite: **NOT_RUN** (last known: 1162 passed at 687e697, before this branch).
- `ruff check .` / `ruff format --check .`: **NOT_RUN** on this branch. Fixed by hand the known E501 lines in `training.py`, the `hardening.py` formatting line and over-long lines in new files (checked with a 100-column scan). Remaining known format item: `tests/phase7/test_phase7a_final_metrics_and_baselines.py` (audit log said ruff-format wants it re-flowed) was not touched. Pre-existing `backend.py:49` is 102 columns (inside a string; may need a `# noqa` or a split).
- Linux status: **LINUX_PENDING**. Mac status: **MAC_PENDING** (not MAC_PASS).

## 4. Status of the required evidence items

| Item | Status |
|---|---|
| Gold verification (manifest, id, partitions, size, SHA-256, schema, 109 features, target version, cutoff, holdout flags) | NOT_RUN - REQUIRES_REAL_DATA |
| Cache verification / qualification of one cache path | NOT_RUN. Existing caches are stale by code identity (section 2, IA-04). |
| M-01 real-data census | NOT_RUN - tool ready |
| Identity | control identity wired; result-row identity columns added; not enforced at write time |
| Ledger | module only |
| Chronology | module + tests; no real protocol file |
| Calibration (Cal-A purge) | DEFERRED |
| H0 | DEFERRED |
| Economics | NO_TRADE fixed; funding / stress / metric naming DEFERRED |
| Resource / RunPod | unchanged; RunPod not started |
| Holdout | **AUGUST_NOT_ACCESSED** (LOCKED_UNUSED, used=false, evaluation_authorized=false); July unused. No paid training, no trading, no Gold rebuild, no network downloads, nothing pushed. |

## 5. Remaining blockers (must close before any smoke)

1. Run the full `pytest`, `ruff check .`, `ruff format --check .` on the Mac and fix whatever they report.
2. Real Gold read-only verification and qualify ONE cache (all existing caches are stale after the `training.py` / `economics.py` edits).
3. Run `python -m crypto_ai.phase7.feature_census` against the independent feature keys and Gold; if the verdict is `MATERIAL_LOSS_SIDECAR_REQUIRED`, design a versioned FEATURE_CONTEXT_SIDECAR (Gold stays immutable). Terminal and interior gaps hit every peer at once, so a material verdict is plausible.
4. Wire `result_ledger` and `validate_result_set` into the run path so duplicates cannot be produced or consumed.
5. Close the generic-CLI admission bypass (IA-11) or label it non-canonical.
6. Before any tradability claim: funding (IA-06), portfolio vs trade metrics (IA-08), Cal-A purge (IA-13), H0 separation (IA-14).

## 6. Honest re-scores (out of 10)

| Dimension | Score | Why |
|---|---|---|
| Scientific | 5 | Invalid inference removed and chronology contamination made detectable, NO_TRADE fixed; but funding absent, M-01 unmeasured, selection protocol not yet applied to real folds. |
| Engineering | 5 | Clean, tested-in-isolation modules and small commits; but the new modules are not wired into the run path, `training.py` is still monolithic, and nothing has been run by a real test runner. |
| Statistical rigor | 4 | No more false p-values, but there is still no independent evaluation design in force, and development metrics dominate. |
| Trading realism | 3 | Static costs, no funding, reference entry, trade-level metrics only. |
| Reproducibility | 5 | Control identity and receipts exist; caches are invalidated and unqualified; results are still CSV-driven. |
| RunPod readiness | 3 | Not started; resource wording and admission gaps remain; no Linux verification. |

## 7. Self-attack checklist

| Attack | Answer |
|---|---|
| Duplicate result rows counted? | Closed in ranking/success (fail closed). Still possible in the CSV file itself until the ledger is wired. **Remaining risk.** |
| Later fold leaks earlier TEST? | Yes by design of the rolling calendar; now detected by the overlap matrix and refused by the selector. Not closed for a real run until the protocol is generated. |
| Resume with changed hardening semantics? | Closed for checkpoint resume (control identity in the checkpoint identity); untested on a real resume. |
| M-01 escape? | **Yes - open.** Census not run; whole-timestamp loss is invisible from Gold alone. |
| Stale cache reused? | Not reusable: code identity changed. Nothing deleted. |
| Cal-B / TEST leaks? | No new leak found; Cal-A purge unverified (IA-13 open). |
| August touched? | No. |
| Forced negative-expectancy trading? | Fixed (IA-15). |
| Trade-Sharpe as portfolio Sharpe? | **Yes - open** (IA-08 naming). |
| Funding silently zero? | It is labelled NOT_MODELLED, not silent, but still absent. **Open.** |
| GPU without approval? | **Open** (no marker enforced); the smoke plan is CPU only. |
| CLI bypass? | **Yes - open** for `phase7-research --stage train`. |
| False "completed" results? | Validators reject non-COMPLETE rows; write path not yet enforced. |
| Partial CSV? | Ledger writes are atomic; CSV path unchanged. **Open until wired.** |
| RunPod resource overrun? | Estimator wording/cgroup unchanged. **Open.** |
| Live-order imports? | No import-boundary test added. **Open.** |

## 8. Smoke commands

Not issued, because the verdict is NOT_READY_FOR_SMOKE and the instruction was to provide them only for READY_FOR_ONE_CPU_SMOKE_ONLY. For orientation only, the current CLI exposes `python -m crypto_ai.phase7.preflight`, `resource_estimate --manifest --path`, `verify_linux`, and `benchmark_one_spec --config --spec-id --output-root [--prepare-only] [--execute]` (default prints a plan). Nothing was executed.
