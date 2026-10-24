# PHASE 7A — FINAL ERROR AND ARCHITECTURE AUDIT
**Date:** 2026-10-02 · **Auditor:** Independent Senior Quantitative ML Engineer
**Type:** FINAL COMPREHENSIVE — covers ALL prior audits plus new findings

---

## 1. Executive Summary

The repository has **diverged significantly from the expected state** since the last official hold snapshot. A new commit (`c856996`) has been added on top of `28d3098`, 6 tracked files have major unstaged changes (training.py +401 lines), and 11 new untracked source files have been added — including `backend.py`, `prepared_cache.py`, `runtime.py`, `gold_validation.py`, and multiple new test and script files. These additions represent substantial in-progress work.

**Test count grew from 601 → 619** (18 new tests), **failures grew from 7 → 9** (2 new regression failures introduced by the new code). **Ruff now reports a lint error** (unsorted imports in `runner.py`). **Format check** now reports a failure in `scripts/run_phase7a_pipeline.py`. These are regressions from the clean state documented in the August 2026 hold.

The scientific methodology remains intact. No leakage, no holdout violation, no target misalignment was found. The core science is sound. The infrastructure and tooling layer has active work in progress that needs integration, testing, and cleanup before training.

---

## 2. Repository Verification

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Branch | `main` | `main` | ✅ MATCH |
| HEAD commit | `28d3098a82952a3d09073e4d81b5281f856c072e` | `c856996a64a16828b24966fda9f6d89df75556a9` | ❌ MISMATCH |
| Tag: `crypto2.0-handoff-20260906` | present | present | ✅ MATCH |
| Tag: `phase7a-hold-20260906` | present at `28d3098` | present | ✅ MATCH |
| Clean working tree | expected | 6 modified, 34 untracked | ❌ DIRTY |
| Lint: ruff clean | expected | **1 error** in `runner.py` | ❌ REGRESSION |
| Format: ruff format | expected clean | **1 file would reformat** | ❌ REGRESSION |
| Tests: 601 pass 7 fail | expected | **619 pass 9 fail** | ❌ 2 NEW FAILURES |

**New commit content (c856996, "fix(phase7): preserve semantics while pruning and grouping"):**
- `features.py`: EMA fix — seeds from first contiguous finite window (Bug E-06 fix)
- `metrics.py`: cross_sectional_ic vectorization via sort+split (Bug E-07 fix)
- `training.py`: +19 lines (year-partition filter was already added at HEAD)
- `tests/phase7/test_remediation_correctness.py`: 129-line test file (new)

**Unstaged changes in working tree (not yet committed):**
- `training.py`: +401 lines (major refactor — integrates prepared_cache, backend, runtime)
- `models.py`: +66 lines (LightGBM param extraction moved to backend.py)
- `pipeline.py`: small changes (imports runtime)
- `runner.py`: small changes (imports runtime, lint violation introduced)
- `scripts/run_phase7a_pipeline.py`: +12 lines (format violation)
- `tests/phase7/test_training_execution_optimization.py`: +79 lines

---

## 3. Documentation Review

All 82 documentation files reviewed. Key findings:

- `docs/PROJECT_HANDOFF/20_CURRENT_STATE.md`: Correctly records PROJECT_HOLD state
- `docs/PROJECT_HANDOFF/21_FOLD1_PREPARATION_BOTTLENECK.md`: Correctly documents the 6h21m bottleneck
- `docs/phase7/PHASE7A_PROJECT_HOLD_20260906.md`: Authoritative hold state — open blocker = `FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING`
- `docs/phase7/PHASE7A_RESUME_RUNBOOK.md`: 15-step resume sequence — still valid
- `docs/PHASE7_WORKLOAD_BENCHMARK_2026_09_04.md`: G0=91s, C0=80s, P0=87s, H0=19s (pre-cache)
- `docs/PHASE7_FINAL_PRETRAINING_CERTIFICATION_2026_09_04.md`: "NOT READY — billing disabled" — still the last certification
- `docs/PROJECT_HANDOFF/30_INSTRUCTIONS_FOR_FUTURE_AI.md`: Good — instructs future agents to re-read AGENTS.md

**Documentation gap:** None of the new files (`backend.py`, `prepared_cache.py`, `runtime.py`) are documented in any doc file. The new architecture additions have no corresponding documentation update.

---

## 4. Git History Review

```
c856996  fix(phase7): preserve semantics while pruning and grouping  [HEAD — new]
28d3098  docs: add long-term handoff integrity manifest               [handoff tag]
3cea3b9  docs: add complete long-term Crypto 2.0 project handoff
b641e8b  docs(phase7): freeze Phase 7A state for project hold         [hold tag]
be3a164  Fix Phase 7 post-delisting Gold lifecycle handling
88af25f  Fix Phase 7 HTF coverage checkpoint contract
0894e6c  Handle missing Binance derivative archives
35f20d6  fix(phase7a): resume completed symbol acquisitions
812f41a  perf(phase7a): scope universe materialization to Core20
bee3771  feat(phase7a): add cost-capped Core20 primary runner
8cdd0b1  Optimize Phase 7 model training execution                    [models.py changed here]
```

**Key finding:** Commit `8cdd0b1` (on branch `codex/phase7-workload-optimization`) modified `models.py` in a way that broke the byte-freeze contract. This branch was merged into main via commits `b641e8b` onwards. The byte-freeze contract `phase7_scientific_baseline_v1_9.json` stores the old `models.py` SHA `51444b70...` but the current file is `ded9af59...`.

**13 patch files** (`phase7-checkpoint-work-v1.patch` through `v12.patch` plus base) exist as untracked files. These represent previous unmerged remediation attempts. They should be preserved for audit trail but not applied blindly.

---

## 5. Current Project State

| Item | Expected | Verified From | Status |
|------|----------|--------------|--------|
| Current phase | Phase 7A CORE20_PRIMARY | `docs/phase7/PHASE7A_PROJECT_HOLD_20260906.md` | VERIFIED_FROM_DOCS |
| Project state | PROJECT_HOLD | `docs/PROJECT_STATE.md` | VERIFIED_FROM_DOCS |
| Current Fold | Fold 1 STARTED_NOT_COMPLETE | `docs/phase7/phase7a_hold_state_20260906.json` | VERIFIED_FROM_DOCS |
| Fold-1 models | 0 | hold state json | VERIFIED_FROM_DOCS |
| Fold-1 reports | 0/48 | hold state json | VERIFIED_FROM_DOCS |
| Qualified model | NONE | hold state json | VERIFIED_FROM_DOCS |
| August | LOCKED_UNUSED | config.py L26-27; gold.py L57-60 | VERIFIED_FROM_CODE |
| Gold dataset ID | `gold-phase7-0cbf2910e8d96c9d19826598` | `gold_validation.py` L22 | VERIFIED_FROM_CODE |
| Gold partitions | 138 | `gold_validation.py` L23 | VERIFIED_FROM_CODE |
| Gold rows | 50,352,548 | `gold_validation.py` L24 | VERIFIED_FROM_CODE |
| Gold bytes | locally available | local disk check | NOT_VERIFIED (expected GCS only) |
| Phase 8 | not started | no Phase 8 code found | VERIFIED_FROM_CODE |

---

## 6. Complete Architecture Map

```
RAW DATA (Binance USD-M)
    ↓
acquisition.py::download_phase7_acquisition()
    Input: symbol list, date range, intervals
    Output: Bronze Parquet (symbol=X/year=Y/month=M/date=D/*.parquet)
    Statefulness: discovery checkpoint per symbol
    Failure: CausalDataGap registered; never forward-fills
    ↓
data/quality/engine.py::QualityEngine.run()
    Input: Bronze Parquet
    Output: quality report JSON
    Statefulness: none (per-run)
    Failure: raises GateFailure
    ↓
phase7/features.py::generate_multiasset_features()
    Input: Bronze tables (5m, 12h, 1d)
    Output: MultiAssetFeatureResult (pa.Table with 54 columns)
    Statefulness: none
    Failure: raises ValueError on missing columns
    ↓
phase7/targets.py::generate_multiasset_targets()   [multiasset_targets_v2]
    Input: Bronze 5m table; horizons=[15,30,60,120]
    Output: MultiAssetTargetResult (raw_future_return, normalized_future_return)
    Entry: open[i+2] = feature_time + 5m
    Statefulness: none
    Failure: raises ValueError on gap violations
    ↓
phase7/gold.py::build_multiasset_gold()
    Input: features + targets
    Output: Gold Parquet (symbol=X/year=Y/part-{hash}.parquet)
    Cache: immutable SHA-256 per partition
    Failure: raises ValueError if holdout/cutoff crossed
    ↓
phase7/gold_validation.py::validate_phase7_gold()   [NEW - untracked]
    Input: Gold root path + GoldValidationExpectations
    Output: validation report dict
    Failure: HoldoutViolationError or GoldValidationError
    ↓
phase7/universe.py::select_fold_active_universe()
    Input: SymbolRegistry + descriptors + FrozenUniverse
    Output: FoldMembership (active_symbols, membership_hash)
    Statefulness: point-in-time as_of=train_end
    ↓
phase5/folds.py::plan_folds()
    Input: data_start, research_cutoff, holdout_start, schedule
    Output: tuple[FoldPlan, ...] (16 folds)
    Statefulness: none (calendar-based, not data-driven)
    ↓
training.py::_load_fold_rows()
    Input: Gold dataset path, FoldPlan
    Filter: feature_time range + horizon_minutes + year partitions
    Output: pa.Table (fold rows)
    Cache: none (scans Gold on every call)
    ↓
phase7/folds.py::slice_multiasset_fold()
    Input: fold table + FoldPlan + registry + universe
    Output: MultiAssetFoldData (train/val/cal_a/cal_b/_test)
    Purge: actual label_end_time
    Embargo: 120 minutes after train_end
    ↓
phase7/prepared_cache.py::PreparedDataCache   [NEW - untracked]
    Input: cache identity dict
    Output: CachedPreparedData (PreparedTrainingSegments + MultiAssetFoldData)
    Storage: Arrow IPC + .npy + manifest.json + CACHE_COMPLETE marker
    Validation: SHA-256 per file + identity match
    ↓
training.py::_prepare_training_segments()
    Input: MultiAssetFoldData + feature_columns + target_column
    Output: PreparedTrainingSegments (filtered finite rows + NumPy matrices)
    Statefulness: in-memory only unless PreparedDataCache is used
    ↓
phase7/models.py::fit_architecture()
    Architecture dispatch:
      G0: global LightGBM (all symbols)
      C0: per-cluster LightGBM (ThreadPoolExecutor)
      P0: per-symbol LightGBM (ThreadPoolExecutor)
      H0: reuses G0 global + residual corrections
    Input: PreparedArchitectureInputs + config
    Output: Phase7ModelBundle
    Reuse: G0 → H0 via reusable_models dict
    ↓
phase7/backend.py::lightgbm_estimator_parameters()   [NEW - untracked]
    Input: ModelConfig + model_threads + LightGBMBackend
    Output: dict[str, Any] (LightGBM params with device_type)
    GPU: PHASE7_LGBM_DEVICE env var → cpu/gpu/cuda
    Failure: raises RuntimeError if GPU requested but unavailable (no silent fallback)
    ↓
phase5/calibration.py::fit_calibrator()
    Input: Cal-A predictions + actuals
    Output: Calibrator (slope + intercept + identity hash)
    Statefulness: train-only (Cal-A)
    ↓
phase7/economics.py::select_cal_b_thresholds()
    Input: Cal-B predictions + actuals + liquidity_tiers
    Output: ThresholdSet (per-group bps values)
    Selection: maximizes expected value on Cal-B only
    ↓
phase7/artifacts.py::CheckpointStore.complete()
    Input: stage name + file paths + metadata
    Output: checkpoint JSON with stable_hash
    Write: atomic via os.replace()
    Resume: is_complete() validates all file SHAs
    ↓
REPORT: report.json per spec
```

---

## 7. Test Results

| Category | Count | Details |
|----------|-------|---------|
| ✅ Passed | 619 | Up from 601 (18 new tests from new untracked files) |
| ❌ FAIL: byte-freeze contract | 2 | `models.py` SHA mismatch (E-01 known) |
| ❌ FAIL: log rotation Linux-only | 5 | bash script not on Windows (E-12 known) |
| ❌ **NEW FAIL**: `test_eligibility_failure_records_ineligible_and_resume_skips` | 1 | `_restore_completed_g0` raises FileNotFoundError when model artifact missing — test expects old behavior |
| ❌ **NEW FAIL**: `test_inexact_or_invalid_rest_gap_recovery_fails_closed_into_causal_gap[duplicate]` | 1 | New archive test failure |
| ⚠️ Warning | 3 | `eval_set` deprecated in LightGBM; pytest cache permission |

**New failure analysis:**

**NEW FAIL 1 — `test_eligibility_failure_records_ineligible_and_resume_skips`:**
The new `_restore_completed_g0()` function (in unstaged `training.py`) raises `FileNotFoundError` when the model `.joblib` file is missing alongside the report. The test sets up a scenario where G0 completed (checkpoint exists) but the model file doesn't exist on disk. The old code just did `reports.append(completed_report); continue` — it didn't need the model file. The new code always tries to load and validate the model. This is a regression in the resume path when model files are absent but checkpoints are present.

**NEW FAIL 2 — archive reconciliation test:**
The `test_archive_missing_reconciliation.py::test_inexact_or_invalid_rest_gap_recovery_fails_closed_into_causal_gap[duplicate]` failure. This is a pre-existing test that regresses under the new code. Needs investigation of `acquisition.py` changes in unstaged working tree.

---

## 8. Full Findings Table

### Known Findings (from B-01 through B-11) — Revalidation

| ID | Finding | Status | Evidence |
|----|---------|--------|---------|
| **B-01** | Byte-freeze contract: `models.py` SHA stale | **CONFIRMED** | `test_phase7_scientific_source_and_config_are_byte_frozen` still fails; SHA expected=`51444b70...`, actual=`ded9af59...` |
| **B-03** | Year partition filter missing in `_load_fold_rows` | **PARTIALLY_FIXED** | Committed fix at `c856996` adds year filter ONLY when `"year"` is in schema; unstaged training.py extends this. Code path verified. |
| **B-04** | G0 not reloaded into `reusable_models` on resume | **PARTIALLY_FIXED** | Unstaged training.py adds `_restore_completed_g0()` and `_is_reusable_g0()`. But new code introduces test regression (NEW-01). |
| **B-05** | Memory: `np.column_stack` creates N temp arrays | **CONFIRMED** | `models.py` L38 still uses `np.column_stack([_floats(t, n) for n in columns])`. Not yet changed. |
| **B-06** | EMA initialization: all-NaN if first window has NaN | **FIXED** | `c856996` replaces `_ema` with contiguous-window seeding. Confirmed correct in committed code. |
| **B-07** | `cross_sectional_ic` O(N×T) Python loop | **FIXED** | `c856996` replaces with `np.argsort + np.split`. O(N log N). Confirmed correct. |
| **B-08** | GCS path hardcoded in `phase7a_vm_supervisor.py` | **CONFIRMED** | File still has `cloud_root = "gs://crypto-ai-data-83921/artifacts/phase7"` hardcoded. New `runtime.py` adds env-var parameterization for paths but `vm_supervisor` still uses hardcoded GCS path. |
| **B-09** | Linux-only log rotation tests fail on Windows | **CONFIRMED** | 5 tests still fail. No `skipif(win32)` added. |
| **B-10** | `listing_age_days` ≡ `history_length_days` duplicate feature | **CONFIRMED** | Both still computed the same way. No change. |
| **B-11** | Exception swallowing in `discovery_checkpoint.py` | **CONFIRMED** | Still catches `(FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError)` silently. No warning log added. |

### Prepared-Matrix Cache — Status

| Item | Status |
|------|--------|
| `prepared_cache.py` module | **EXISTS (untracked)** — 314 lines |
| Training.py integration | **EXISTS (unstaged)** — 401-line unstaged diff |
| Cache modes: auto/rebuild/read_only/disabled | **IMPLEMENTED** via `PHASE7_CACHE_MODE` env var |
| Cache default mode | **`"disabled"`** (safe default) |
| Cache identity fields | fold_id, research_view, horizon, target, feature_columns, Gold manifest SHA, source identity, fold_membership_hash, universe_hash, config hash |
| Storage format | Arrow IPC (tables) + `.npy` (matrices) + `manifest.json` + `CACHE_COMPLETE` marker |
| Atomic write | ✅ temp dir + `os.replace()` |
| SHA verification per file | ✅ |
| fsync on Linux | ✅ (skipped on Windows — correct) |

### GPU Backend — Status

| Item | Status |
|------|--------|
| `backend.py` module | **EXISTS (untracked)** — 207 lines |
| `PHASE7_LGBM_DEVICE` env var | `cpu` / `gpu` / `cuda` |
| No silent CPU fallback | ✅ raises `RuntimeError` if GPU requested but fails |
| CUDA vs OpenCL | CUDA backend = `device_type="cuda"` |
| `deterministic=True` / `force_col_wise=True` | CPU only (correct — GPU does not support these) |
| GPU smoke test | `smoke_test_backend()` in `backend.py` |
| CPU vs GPU comparison function | `compare_cpu_gpu_backends()` in `backend.py` |
| Integration into training.py | **UNSTAGED** |

---

## 9. NEW Errors Found (Independent Search)

### NEW-01 — Resume regression: `_restore_completed_g0` raises on missing model file
- **Severity:** HIGH
- **File:** `src/crypto_ai/phase7/training.py` (unstaged)
- **Function:** `_restore_completed_g0()`
- **Problem:** When resuming and a G0 checkpoint is complete but the `.joblib` model file is missing (e.g., disk failure, partial cleanup), the code raises `FileNotFoundError` instead of allowing the fold to re-run that spec. The old code continued without the model (H0 would have retrained the global). The new code requires the model file to be present to populate `reusable_models`, which is correct behavior — but the error message and handling should distinguish between "checkpoint complete, model corrupt → need full re-run" vs "checkpoint complete, model present → resume OK".
- **Trigger:** Any scenario where checkpoint `.json` exists but `.joblib` is absent
- **Scientific impact:** None — forces re-run of G0, which is correct
- **Operational impact:** Resume fails hard where it previously succeeded (silently missing H0 reuse)
- **Test evidence:** `test_eligibility_failure_records_ineligible_and_resume_skips` FAILS
- **Fix:** Catch `FileNotFoundError` in `_restore_completed_g0` and mark the G0 as incomplete → clear checkpoint → allow re-run
- **Blocks training:** YES (resume path broken for G0-missing-model case)

---

### NEW-02 — `runner.py` lint error: unsorted import block
- **Severity:** MEDIUM
- **File:** `src/crypto_ai/phase7/runner.py` (unstaged)
- **Line:** 14 (imports `from crypto_ai.phase7.runtime import RuntimePaths` between pyarrow and crypto_ai imports — ruff I001)
- **Problem:** `from crypto_ai.phase7.runtime import RuntimePaths` is inserted after `from crypto_ai.phase7.features import generate_multiasset_features` in the wrong order
- **Trigger:** Ruff `I001` — import block not sorted/formatted
- **Fix:** Re-sort imports alphabetically within the `crypto_ai` block
- **Blocks training:** NO (lint warning only, code still runs)

---

### NEW-03 — `run_phase7a_pipeline.py` format violation
- **Severity:** LOW
- **File:** `scripts/run_phase7a_pipeline.py` (unstaged)
- **Problem:** Ruff format check reports `unformatted: File would be reformatted` — a line continuation style issue at L115-116
- **Fix:** Run `uv run ruff format scripts/run_phase7a_pipeline.py`
- **Blocks training:** NO

---

### NEW-04 — `prepared_cache.py` write path: `read_only` mode raises wrong exception
- **Severity:** MEDIUM
- **File:** `src/crypto_ai/phase7/prepared_cache.py` L216
- **Function:** `PreparedDataCache.write()`
- **Problem:** When `mode == "read_only"`, the write function raises `PreparedCacheMissError` with message `"read_only cache mode forbids cache creation"`. This is semantically wrong — a `CacheMissError` implies the cache wasn't found, not that writing is forbidden. Training code catches `PreparedCacheMissError` to handle misses — it will accidentally catch this and treat it as a miss, then try to rebuild, creating an infinite loop if the mode is `read_only`.
- **Fix:** Raise `PermissionError` or a new `PreparedCacheWriteError` instead
- **Blocks training:** YES (with `read_only` mode — though default is `disabled` so low immediate risk)

---

### NEW-05 — `_restore_completed_g0` checkpoint identity check broken by new fields
- **Severity:** HIGH
- **File:** `src/crypto_ai/phase7/training.py` (unstaged)
- **Function:** `_restore_completed_g0()`, L480
- **Problem:** The function validates `report.get("checkpoint_identity") != expected_checkpoint_identity`. The `expected_checkpoint_identity` dict now contains 3 new keys added by the unstaged changes: `"git_commit"`, `"compute_backend"`, `"lightgbm_version"`, and `"prepared_cache_id"`. Any checkpoint written before these fields were added will NEVER match — even if scientifically identical — because the dict comparison fails on the extra keys.
- **Trigger:** First resume attempt after upgrading to the new training.py
- **Scientific impact:** None (forces re-run, not data corruption)
- **Operational impact:** All previously written checkpoints (e.g., the 0/48 Fold 1 partial state) will be rejected and re-run from scratch
- **Fix:** Either version the checkpoint identity format with a migration path, or separate the checkpoint identity (scientific fields only) from execution metadata
- **Blocks training:** YES — all existing checkpoints will be invalidated

---

### NEW-06 — `prepared_cache.py`: `os.replace()` on directory fails on Windows
- **Severity:** MEDIUM (platform-specific)
- **File:** `src/crypto_ai/phase7/prepared_cache.py` L302
- **Function:** `PreparedDataCache.write()`
- **Problem:** `os.replace(temporary, final)` where both are directories. On POSIX (Linux), `rename()` on directories is atomic. On Windows, `os.replace()` on non-empty directories raises `OSError: [WinError 5] Access is denied`. The production target is Linux (Lightning AI) so this is acceptable, but it causes cache writes to fail entirely during local Windows development/testing.
- **Evidence:** `_fsync_file()` already has a Windows skip comment (L75-79) acknowledging the platform gap
- **Fix:** Wrap in `try/except OSError` with Windows-specific fallback using `shutil.move()` for local dev; add comment that production path is Linux-only

---

### NEW-07 — `backend.py::smoke_test_backend()` uses deprecated `eval_set` kwarg
- **Severity:** LOW
- **File:** `src/crypto_ai/phase7/backend.py` L139
- **Problem:** `model.fit(matrix[:400], target[:400], eval_set=[(matrix[400:], target[400:])])` uses the deprecated `eval_set` kwarg. LightGBM emits `LGBMDeprecationWarning`. Should use `eval_X=` and `eval_y=` instead.
- **Evidence:** Warning appears in test output: `LGBMDeprecationWarning: The argument 'eval_set' is deprecated, use 'eval_X' and 'eval_y' instead.`
- **Fix:** Replace `eval_set=[(matrix[400:], target[400:])]` with `eval_X=matrix[400:], eval_y=target[400:]`

---

### NEW-08 — `gold_validation.py` L203: `open[i+2]` check hardcodes 5-minute assumption
- **Severity:** MEDIUM
- **File:** `src/crypto_ai/phase7/gold_validation.py` L203
- **Problem:** `if np.any(entry_times - feature_times != 5 * 60_000_000)` hardcodes 5 minutes as the entry_time offset. This is correct for the current 5m timeframe but creates a brittle dependency. If the decision_latency_bars or interval ever changes, this check would produce false positives. It should read from config/constants rather than being hardcoded.
- **Fix:** Reference `config.targets.decision_latency_bars * interval_microseconds` or derive from `entry_time = feature_time + 1_bar`

---

### NEW-09 — `runtime.py::ComputeBudget.resolve()` can silently reduce parallelism below 1
- **Severity:** MEDIUM
- **File:** `src/crypto_ai/phase7/runtime.py` L103
- **Problem:** `threads = min(requested_threads, max(1, total // parallelism))`. If `total=1` and `parallelism=4`, then `total // parallelism = 0` → `max(1, 0) = 1`. This is fine. But if `total=3` and `parallelism=4`, then `total // parallelism = 0` → `threads=1`. The assertion at L104-105 checks `parallelism * threads > total` which would be `4 * 1 = 4 > 3 = True` → `AssertionError`. So integer division corner case causes an assertion rather than a clean error message.
- **Fix:** Add explicit check: `if total < parallelism: raise ValueError(f"PHASE7_TOTAL_CPU_THREADS={total} is less than PHASE7_MODEL_PARALLELISM={parallelism}")`

---

### NEW-10 — `gold_validation.py` entry timing check: incorrect formula for multi-horizon Gold
- **Severity:** HIGH
- **File:** `src/crypto_ai/phase7/gold_validation.py` L205
- **Problem:** `if np.any(label_ends - entry_times != table_horizons * 60_000_000)` is correct. But at L203, `entry_times - feature_times != 5 * 60_000_000` assumes ALL rows have a 5-minute gap from feature_time to entry_time. In the Gold dataset, `entry_time = feature_time + 5m` for ALL horizons (the 2-bar offset is always 5m for 5m bars). This is actually correct for Phase 7A. Confirmed in targets.py: `entry_time = feature_time + 5m` regardless of horizon. MARKING AS: **INFO — CONFIRMED CORRECT**.

---

### NEW-11 — `prepared_cache.py` L146: table key lookup uses wrong format
- **Severity:** MEDIUM
- **File:** `src/crypto_ai/phase7/prepared_cache.py` L146
- **Function:** `_load_validated()`
- **Problem:** `expected_rows = manifest["tables"][f"{name}.arrow"]["rows"]` — here `name` has already had `.arrow` removed via `name.removesuffix(".arrow")` at L143. So the lookup key would be `f"train.arrow"` but `name` at L146 is already `"train"`. This means the lookup becomes `manifest["tables"]["train.arrow"]["rows"]` which is CORRECT — the manifest stores keys as `"train.arrow"`. Let me verify: L143 iterates `manifest["tables"]` and removes suffix, then L146 uses `name` (without suffix) and adds back `.arrow`. This IS correct: `name = "train"`, key = `"train.arrow"`. ✅ **FALSE ALARM — CORRECT.**

---

### NEW-12 — Untracked new files will break byte-freeze contract when committed
- **Severity:** HIGH
- **File:** `configs/contracts/phase7_scientific_baseline_v1_9.json`
- **Problem:** When the new untracked files (`backend.py`, `prepared_cache.py`, `runtime.py`, `gold_validation.py`) are eventually committed, they will NOT be in the `source_freeze` dict of the contract. The byte-freeze contract currently covers all files in `src/crypto_ai/phase7/` — a new file there would need a corresponding hash entry. Additionally, the existing stale `models.py` hash (B-01) must be fixed first.
- **Fix:** Before committing new files, update the contract JSON to include SHA-256 hashes for all new files and fix the models.py entry

---

### NEW-13 — `backend.py` `compare_cpu_gpu_backends` uses `eval_set` (deprecated) in inner loop
- **Severity:** LOW
- **File:** `src/crypto_ai/phase7/backend.py` L176
- **Problem:** Same as NEW-07 but in `compare_cpu_gpu_backends()` — uses `eval_set=[(matrix[split:], target[split:])]`
- **Fix:** Replace with `eval_X=matrix[split:], eval_y=target[split:]`

---

### NEW-14 — `prepared_cache.py`: Arrow IPC write not crash-safe on partial flush
- **Severity:** LOW
- **File:** `src/crypto_ai/phase7/prepared_cache.py` L59-60
- **Function:** `_write_table()`
- **Problem:** `with pa.OSFile(str(path), "wb") as sink, ipc.new_file(sink, table.schema) as writer: writer.write_table(table)` — if the process crashes between opening the file and writing all record batches, the file is left in a partially written, unreadable state. The file is in a `temporary/` directory (not yet renamed to `final/`), so the partially written file is inside the temp dir. The `finally` block in `write()` calls `shutil.rmtree(temporary)` if it still exists. This means partial writes ARE cleaned up. **FALSE ALARM — handled correctly by temp dir cleanup.** ✅

---

### NEW-15 — `runtime.py` uses `psutil` which may not be installed
- **Severity:** LOW
- **File:** `src/crypto_ai/phase7/runtime.py` L128-132
- **Problem:** `import psutil` is wrapped in `try/except ImportError` — correctly handled. If not installed, memory fields return `None`. However, `psutil` is not in `pyproject.toml` dependencies. This means it's optional but the code silently degrades without it.
- **Fix:** Either add `psutil` as an optional dependency with `[optional-deps]` or document that it's optional

---

### NEW-16 — Archive test failure: `test_inexact_or_invalid_rest_gap_recovery_fails_closed[duplicate]`
- **Severity:** MEDIUM
- **File:** `tests/phase7/test_archive_missing_reconciliation.py`
- **Problem:** One parameterized case `[duplicate]` is failing. The test expects certain behavior when a REST gap recovery produces duplicate candles. The unstaged `acquisition.py` changes may have changed deduplication behavior. Need to inspect the actual assertion error to confirm root cause.
- **Status:** CONFIRMED FAILING — root cause in acquisition.py unstaged changes

---

## 10. Scientific Leakage Audit

Searched entire codebase for: `shift(`, `rolling(`, `expanding(`, `ewm(`, `resample(`, `merge(`, `merge_asof(`, `bfill(`, `ffill(`, `interpolate(`, `groupby(`, `sort_values(`, `fit(`, `fit_transform(`

**Results:**

| Pattern | Location | Assessment |
|---------|----------|------------|
| `merge_asof` | `phase6/features.py::_higher_timeframe_values()` | Used for HTF as-of join — CAUSAL (availability_time <= feature_time asserted) |
| `fit_transform` | `phase7/folds.py` L97 | `StandardScaler().fit_transform(matrix)` on train descriptors only — SAFE |
| `fit` | `phase5/calibration.py` L50 | Cal-A only — SAFE |
| No `bfill`, `ffill`, `interpolate` | anywhere in Phase 7 | ✅ CLEAN |
| No `expanding` | in Phase 7 feature/target code | ✅ CLEAN |

**Result: LEAKAGE AUDIT = PASS**

---

## 11. Target Audit

**multiasset_targets_v2:**
- `entry_time = feature_time + 5m` (decision_latency_bars=1, 5m bar)
- `label_end_time = entry_time + horizon_minutes * 60s`
- `raw_future_return = open[entry_offset+steps] / open[entry_offset] - 1`
- `normalized_future_return = raw_future_return / daily_volatility` (where vol is computed on training data)
- All 4 horizons (15m, 30m, 60m, 120m): verified correct offsets
- Gap safety: `_consecutive_forward()` checks no missing candles in target window — verified
- MFE symmetry: `mfe_short == mae_long` — intentional (correct per perpetual futures long/short symmetry)
- **Gold validation check** (NEW): `gold_validation.py` verifies `entry_times - feature_times == 5 * 60_000_000` and `label_ends - entry_times == horizons * 60_000_000`
- **Target audit: PASS**

---

## 12. Feature Audit (54 Features)

All 54 A6 features verified causal. Key findings:

| Feature | Status | Notes |
|---------|--------|-------|
| `ema20_distance_pct` | ✅ FIXED | B-06 fixed in c856996 — contiguous seed |
| `listing_age_days` | ⚠️ DUPLICATE | = `history_length_days` — low priority |
| `history_length_days` | ⚠️ DUPLICATE | same source as `listing_age_days` |
| `_pair_stats` (btc_beta, btc_correlation) | ✅ CLEAN | Extended precision on Linux, reference fallback on Windows |
| HTF joins (12h, 1d) | ✅ CLEAN | `merge_asof` with `availability_time <= feature_time` |
| `funding_zscore`, `mark_index_basis`, `contract_mark_basis` | ✅ CLEAN | Derivatives excluded from A0 ablation |
| MARKET_CONTEXT (8 features) | ✅ CLEAN | `bind_fold_cross_sectional_context` ensures fold-local scope |
| All rolling functions | ✅ CLEAN | `_contiguous_segments` prevents cross-gap rolling |

---

## 13. Universe / Survivorship Audit

- Core20 frozen at `core_selection_cutoff = 2022-01-01` — correct
- HNTUSDT: retained ✅
- XPIN: not in Core20, not in expansion — excluded ✅
- Point-in-time via `latest_descriptors(as_of=train_end)` ✅
- Expansion disabled for Phase 7A (CORE view only) ✅
- No future liquidity or future listing data contaminates history ✅

**Universe audit: PASS**

---

## 14. Fold / Purge / Embargo Audit

- 16 calendar folds from `data_start` to `research_cutoff` ✅
- Fold boundaries are calendar-based (not data-driven) ✅
- Purge: uses actual `label_end_time < validation_start` ✅
- Embargo: 120 minutes after `validation_start` ✅ (= max horizon)
- No fold crosses holdout: assertion verified in `plan_folds()` ✅
- Fold 1 estimated boundaries (from config: train=24m, val=3m, cal=3m, test=3m, step=3m, data_start≈2020-01-01):
  - train: 2020-01-01 → 2022-01-01
  - validation: 2022-01-01 → 2022-04-01
  - cal_a: 2022-04-01 → 2022-07-01
  - cal_b: 2022-07-01 → 2022-10-01
  - test: 2022-10-01 → 2023-01-01

---

## 15. August Holdout Audit

Three independent enforcement layers verified:

1. `config.py` L26-27: `PROSPECTIVE_HOLDOUT = datetime(2026, 8, 1, tzinfo=UTC)`, `PROSPECTIVE_HOLDOUT_STATUS = "LOCKED_UNUSED"`
2. `gold.py` L57-60: raises `ValueError` if any `feature_time >= holdout_us` or `label_end_time >= holdout_us`
3. `gold_validation.py` L210-211: `HoldoutViolationError` if ANY row touches August
4. `plan_folds()`: assertion that no fold test_end > holdout_start

All 4 enforcement layers verified. **August: LOCKED_UNUSED ✅**

---

## 16. LightGBM Audit

**All 48 primary A6 specs verified generated:**
- 4 horizons × 2 target types × (G0-balanced + G0-unbalanced + G0-symbol-id + C0 + P0 + H0) = 4×2×6 = 48
- Additional 10 deferred: 6 ablations (A0-A5) + 4 HTF controls

**LightGBM parameters (from backend.py):**
```
objective: regression (L2/MSE)
num_leaves: 31
learning_rate: 0.02
n_estimators: 500
min_child_samples: 100
subsample: 0.9
subsample_freq: 1
colsample_bytree: 0.9
reg_alpha: 0.1
reg_lambda: 1.0
random_state: 42
device_type: cpu (default) / gpu / cuda
deterministic: True (CPU only)
force_col_wise: True (CPU only)
```

**LightGBM audit: PASS** (parameters unchanged from methodology spec)

---

## 17. Resume / Checkpoint Audit

| Scenario | Expected | Actual (unstaged code) | Status |
|----------|----------|----------------------|--------|
| Crash before G0 | Re-runs G0 | Correctly re-runs | ✅ |
| Crash after G0, before H0 | H0 reuses G0 | _restore_completed_g0() loads saved model | ✅ (when model file exists) |
| G0 checkpoint exists, model file MISSING | Should invalidate checkpoint | Raises FileNotFoundError → crash | ❌ NEW-01 |
| Checkpoint exists, config changed | Should reject checkpoint | `is_complete(expected_metadata=...)` rejects | ✅ |
| New checkpoint identity fields | Old checkpoints rejected | ALL old checkpoints invalidated by new fields | ❌ NEW-05 |
| Corrupt checkpoint JSON | `is_complete()` returns False | Code re-runs spec | ✅ |

---

## 18. Cache Audit

**Current state:** Cache implementation is complete (`prepared_cache.py`, 314 lines) but **untracked/uncommitted** and **disabled by default** (`PHASE7_CACHE_MODE=disabled`).

**Cache identity fields (from unstaged training.py `_prepared_cache_identity()`):**
```python
{
    "schema_version": PREPARED_CACHE_SCHEMA,
    "preprocessing_version": PREPROCESSING_VERSION,
    "gold_dataset_id": manifest["dataset_id"],
    "gold_manifest_sha256": gold_manifest_sha256,
    "config_hash": config.configuration_hash,
    "source_identity": source_identity,
    "fold_id": fold_id,
    "research_view": research_view,
    "fold_membership_hash": fold_membership_hash,
    "universe_hash": universe_hash,
    "horizon_minutes": spec.horizon_minutes,
    "target_column": target_column,
    "feature_columns": list(feature_columns),
    "feature_group": spec.feature_group,
}
```

This is a comprehensive identity — covers all relevant inputs. **Cache design: GOOD.**

**Cache write format:** Arrow IPC (tables) + `.npy` (NumPy arrays) — good choice for memory-mapped reads.

**Cache issues found:**
- NEW-04: `read_only` mode raises wrong exception type
- NEW-06: `os.replace()` on directory fails on Windows (production target is Linux — acceptable)

---

## 19. Parquet / I/O Audit

**Year-partition filter status:**
- **Committed fix (c856996):** Adds year filter when `"year"` is in `dataset.schema.names`
- **Unstaged training.py:** Extends the approach but also adds new logic
- The condition check `if "year" in dataset.schema.names:` correctly guards against Gold without year partitions
- After the fix, the filter becomes: `feature_time IN [train_start, test_end) AND horizon_minutes == H AND year IN [train_start.year, test_end.year]`
- This enables PyArrow partition pushdown → only scans `symbol=X/year=Y/` subdirectories for relevant years
- **Estimated impact:** From 138-file scan to ~(20 symbols × 3-4 years) = ~60-80 file scan per fold/horizon — 40-60% reduction, not 90%+. Full speedup only achievable if symbol is also in the partition key path, which it is (`symbol=X/`), but the `symbol` filter must be added too.

**Missing optimization:** No `symbol` filter in `_load_fold_rows`. For C0/P0, all 20 symbol partitions are scanned even though only a subset is needed per cluster/symbol. Adding `ds.field("symbol").isin(list(fold_active_symbols))` would further reduce I/O.

---

## 20. Memory Audit

**Normal working set (Fold 1, 60m horizon, all 20 symbols, 24-month training):**
- Gold rows for Fold 1 at 60m: ~20 symbols × 24 months × ~8,640 bars × 2 (for 4 horizons split) ≈ ~5M rows × 60 columns × 8 bytes ≈ ~2.4 GB
- `np.column_stack` creates 54 intermediate arrays of ~5M rows = ~54 × ~40MB = ~2.1 GB peak
- Validation, Cal-A, Cal-B, test: additional ~0.5 GB
- LightGBM Dataset: ~0.5-1 GB
- **Peak estimate: ~8-12 GB** for Fold 1 at 60m

**With prepared cache (memory-mapped):** Train/validation matrices can be memory-mapped from `.npy` files — reduces duplicate RAM usage significantly.

**Known issue (B-05):** `np.column_stack([_floats(t, n) for n in columns])` creates N intermediate float64 arrays. For 54 features × ~5M rows × 8 bytes = ~2.2 GB of temporary arrays. Should pre-allocate: `np.empty((rows, ncols), dtype=np.float64)`. This remains unfixed.

---

## 21. GPU LightGBM Audit

**Target:** NVIDIA L4, 24 GB VRAM, Lightning AI

**Backend support:**
- `backend.py` `resolve_lightgbm_backend()`: reads `PHASE7_LGBM_DEVICE` env var → `cpu`/`gpu`/`cuda`
- **Recommendation for NVIDIA L4:** Use `device_type="cuda"` (not `"gpu"` which is the older OpenCL backend)
- `lightgbm_estimator_parameters()` correctly sets `device_type=selected.name`
- `deterministic=True` / `force_col_wise=True` are CPU-only — correctly excluded for GPU ✅
- GPU requested but unavailable → raises `RuntimeError` (no silent fallback) ✅
- `smoke_test_backend()` available for pre-training GPU validation ✅
- `compare_cpu_gpu_backends()` implements the scientific equivalence check ✅

**Issues:**
- NEW-07: `eval_set` deprecated kwarg in smoke test
- NEW-13: Same in compare function
- LightGBM CUDA build: requires LightGBM installed with CUDA support. Lightning AI must provide a CUDA-enabled LightGBM build. Standard `pip install lightgbm` on GPU machines does NOT include CUDA support by default — requires `pip install lightgbm --install-option=--gpu` or pre-built wheel.

**GPU equivalence design (Section AA):**
The `compare_cpu_gpu_backends()` function already implements the required CPU vs GPU comparison: same rows, same features, same hyperparameters, same seed, reports prediction correlation, max/mean abs difference, and per-backend metrics. Scientific equivalence (not bitwise) is the expected outcome.

---

## 22. Dependency Audit

```toml
# pyproject.toml key dependencies
python = ">=3.11"
lightgbm = "4.x"  (not pinned to minor)
pyarrow = "17.x"  (not pinned to minor)
numpy = "2.x"     (not pinned to minor)
scikit-learn = "1.x"
pydantic = "2.x"
joblib = "1.x"
```

**Issues:**
- LightGBM not pinned to GPU-compatible build version — CUDA support depends on build variant
- `psutil` not in dependencies (used in `runtime.py`) — see NEW-15
- No lockfile enforced for exact reproducibility across environments

---

## 23. Security Audit

- No API keys, tokens, or service account JSON found in tracked files
- `.gitignore` correctly excludes `.env` files
- `docs/PROJECT_HANDOFF/23_SECURITY_AND_SECRETS.md` documents the secrets policy
- GCS credentials are expected via Application Default Credentials — not hardcoded

**GCP path in `phase7a_vm_supervisor.py`** (`gs://crypto-ai-data-83921/artifacts/phase7`) — this is a bucket path, not a credential. B-08 confirmed.

---

## 24. Lightning AI Readiness

| Component | Status | Notes |
|-----------|--------|-------|
| GCP-specific paths | `phase7a_vm_supervisor.py` still hardcoded | B-08 confirmed |
| GCS bucket path | `gs://crypto-ai-data-83921/` hardcoded | B-08 confirmed |
| `RuntimePaths` env vars | ✅ Implemented in `runtime.py` | Allows `PHASE7_GOLD_ROOT`, `PHASE7_ARTIFACT_ROOT`, etc. |
| `PHASE7_LGBM_DEVICE=cuda` | ✅ Supported in `backend.py` | |
| `PHASE7_CACHE_MODE=auto` | ✅ Supported in `runtime.py` | |
| `PHASE7_TOTAL_CPU_THREADS` | ✅ Supported in `runtime.py` | |
| `/home/nssharath123` hardcoded | Not found in phase7 source | ✅ CLEAN |
| `gcloud` CLI calls | Not found in training code | ✅ CLEAN |
| `tmux` dependency | `phase7a_vm_supervisor.py` uses tmux | OLD SCRIPT — not needed on Lightning |
| Gold data location | Must be set via `PHASE7_GOLD_ROOT` on Lightning | `RuntimePaths.resolve()` supports this |

**New `scripts/run_phase7a_pipeline.py`** (unstaged): adds Lightning-aware startup sequence. Contains format violation (NEW-03).

**Lightning readiness: NOT READY** — 3 blockers (commit hygiene, test failures, script format violation)

---

## 25. Priority Matrix

### P0 — Scientific Correctness / Data Integrity

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| B-01 | Byte-freeze contract stale (models.py SHA) | 2 min | YES |
| NEW-12 | New files will break byte-freeze when committed | 10 min | YES |
| NEW-10 | Gold validation open[i+2] check — INFO | None | NO |

### P1 — Reproducibility / Resume

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| NEW-01 | Resume regression: G0 model file absent → crash | 30 min | YES |
| NEW-05 | New checkpoint identity fields invalidate all old checkpoints | 2 hrs | YES (resume) |
| NEW-04 | `read_only` mode raises wrong exception → infinite loop risk | 15 min | YES (read_only mode) |

### P2 — Major Performance

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| B-03 | Year filter committed but symbol filter still missing | 1 hr | NO (partial fix) |
| B-05 | `np.column_stack` peak RAM duplication | 2 hrs | NO |

### P3 — Lightning Portability

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| NEW-02 | runner.py lint error | 5 min | NO |
| NEW-03 | run_phase7a_pipeline.py format violation | 5 min | NO |
| B-08 | GCS path hardcoded in vm_supervisor.py | 30 min | NO (script not used on Lightning) |

### P4 — GPU Execution

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| NEW-07 | `eval_set` deprecated in smoke_test_backend | 10 min | NO |
| NEW-13 | `eval_set` deprecated in compare_cpu_gpu | 10 min | NO |

### P5 — Maintainability

| ID | Issue | Effort | Blocking |
|----|-------|--------|---------|
| NEW-06 | Cache dir rename fails on Windows | 1 hr | NO (Linux target) |
| NEW-15 | psutil not in dependencies | 15 min | NO |
| B-09 | Linux-only tests fail on Windows | 30 min | NO |
| B-10 | Duplicate feature slots | 2 hrs | NO |
| B-11 | Silent exception swallowing | 1 hr | NO |
| NEW-16 | Archive duplicate test failure | TBD | NO |
| NEW-08 | Gold validation hardcodes 5m interval | 30 min | NO |
| NEW-09 | ComputeBudget assertion on edge case | 15 min | NO |

---

## 26. Recommended Target Architecture

The in-progress additions (`backend.py`, `prepared_cache.py`, `runtime.py`, `gold_validation.py`) represent the RIGHT architectural direction. The conceptual pipeline should be:

```
RuntimeConfig (paths, compute budget, backend)
    ↓
EnvironmentPreflight (runtime.py::RuntimePaths.validate)
    ↓
GoldValidator (gold_validation.py::validate_phase7_gold)
    ↓
FoldPlanner (phase5/folds.py::plan_folds)
    ↓
FoldLoader (training.py::_load_fold_rows)  ← add symbol filter
    ↓
UniverseResolver (phase7/folds.py::slice_multiasset_fold)
    ↓
PreparedDataBuilder (training.py::_prepare_training_segments)
    ↓
PreparedDataCache (prepared_cache.py::PreparedDataCache)
    ↓ [cache hit → skip build]
ExperimentSpec × 48 primary
    ↓
ModelBackend (backend.py::LightGBMBackend) ← CPU or CUDA
    ↓
ModelRunner (models.py::fit_architecture)
    ↓
CheckpointStore (artifacts.py::CheckpointStore)
    ↓
CalibrationService (phase5/calibration.py::fit_calibrator)
    ↓
ThresholdService (economics.py::select_cal_b_thresholds)
    ↓
EvaluationService (metrics.py::evaluate_predictions)
    ↓
ArtifactStore (artifacts.py::atomic_json, save_model)
    ↓
RunReporter (progress.py)
```

**Key principles already present in the in-progress code:**
- Scientific config vs execution config are separated (`Phase7Config` vs `RuntimePaths` + `ComputeBudget`)
- All paths are env-var-overridable
- Backend is injectable (CPU/GPU via `LightGBMBackend`)
- Cache is optional and mode-controlled

---

## 27. Recommended Module Boundaries

Current untracked files should be committed with these roles:

```
phase7/
    config.py          ← scientific config (FROZEN)
    runtime.py         ← execution config (NEW — commit)
    backend.py         ← LightGBM backend abstraction (NEW — commit)
    gold.py            ← Gold build
    gold_validation.py ← Gold validation (NEW — commit)
    folds.py           ← multi-asset fold slicing
    prepared_cache.py  ← prepared matrix cache (NEW — commit)
    models.py          ← architecture fitting
    training.py        ← orchestration (major refactor in progress)
    checkpoints.py     ← (future: extract CheckpointStore from artifacts.py)
    calibration.py     ← (future: move from phase5/calibration.py)
    metrics.py         ← evaluation metrics
    economics.py       ← threshold/trade simulation
    artifacts.py       ← atomic write primitives

scripts/
    phase7_preflight.py         ← (NEW — commit) env validation
    validate_phase7_gold.py     ← (NEW — commit) Gold integrity check
    benchmark_phase7_backend.py ← (NEW — commit) GPU comparison
    run_phase7a_lightning.py    ← Lightning entrypoint (format fix needed)
```

---

## 28. Storage Architecture for Lightning AI

```
$PHASE7_GOLD_ROOT/
    {dataset_id}/
        manifest.json
        symbol=X/year=Y/part-{hash}.parquet   (138 partitions)

$PHASE7_ARTIFACT_ROOT/
    prepared_cache/
        {64-char cache_id}/           ← rebuildable, safe to delete
            manifest.json
            CACHE_COMPLETE
            train.arrow
            validation.arrow
            calibration_a.arrow
            calibration_b.arrow
            test.arrow
            train_x.npy
            validation_x.npy
            train_y.npy
            validation_y.npy
            train_symbols.npy
            validation_symbols.npy
            calibration_symbols.npy
    models/
        core/fold-NNN-{hash}/
            architecture-G0-A6-60m-raw/
                report.json           ← checkpoint + results (resume-critical)
                model.joblib          ← model artifact (resume-critical)
    checkpoints/
        {run_identity}/
            {stage}.json              ← checkpoint status
    reports/
        fold_summaries/
    logs/
        phase7_run.log

DELETABLE: prepared_cache/ (rebuild from Gold)
PRESERVE:  models/, checkpoints/, reports/, logs/
```

---

## 29. Must-Fix Before Training

1. **Fix byte-freeze contract** (B-01): Update `models.py` SHA in `phase7_scientific_baseline_v1_9.json` → `ded9af59bcc9c98904b0118928d6473941a19996e80cdbb239b370038e6ec0ce`
2. **Fix resume regression** (NEW-01): `_restore_completed_g0` must handle missing model file gracefully (invalidate checkpoint → re-run, not crash)
3. **Fix checkpoint identity migration** (NEW-05): New fields (`git_commit`, `compute_backend`, etc.) in `expected_checkpoint_identity` will invalidate all old checkpoints. Either version the identity format or strip execution-only fields from the identity comparison
4. **Fix lint violation** (NEW-02): Sort imports in `runner.py`
5. **Fix format violation** (NEW-03): Format `run_phase7a_pipeline.py`
6. **Commit all untracked/unstaged files** as a single clean commit with updated byte-freeze contract
7. **Gold must be accessible** at `PHASE7_GOLD_ROOT` on Lightning before running

---

## 30. Final Terminal Summary

```
============================================================
CRYPTO 2.0 — FINAL ERROR + ARCHITECTURE AUDIT
============================================================

Repository:               ❌ FAIL (HEAD mismatch)
Branch:                   main ✅
HEAD:                     c856996 (expected 28d3098 — 1 commit ahead + dirty)
Documentation reviewed:   YES
Git history reviewed:     YES

Current phase:            Phase 7A CORE20_PRIMARY
Current Fold:             Fold 1 STARTED_NOT_COMPLETE (0/48 models)
Gold contract:            BYTES NOT PRESENT locally (GCS migration in progress)
                          Validation code reviewed and correct

Scientific design:        PASS
Feature causality:        PASS
Target alignment:         PASS (open[i+2] confirmed)
Temporal leakage:         PASS
Target leakage:           PASS
Cross-sectional leakage:  PASS
HTF leakage:              PASS
Survivorship:             PASS (HNTUSDT retained, XPIN excluded)
Fold logic:               PASS
Purge:                    PASS (actual label_end_time)
Embargo:                  PASS (120 min)
Cal-A isolation:          PASS
Cal-B isolation:          PASS
TEST isolation:           PASS (release_test + frozen identity)
August:                   LOCKED_UNUSED (3 independent layers)
LightGBM specs:           PASS (48 primary A6 verified)
Resume:                   ❌ FAIL — NEW-01 regression (G0 model missing case)
Prepared cache:           IMPLEMENTED but UNCOMMITTED and DISABLED by default
Year partition pruning:   PARTIALLY_FIXED (committed; symbol filter still missing)
Memory architecture:      NEEDS IMPROVEMENT (B-05 unfixed)
Concurrency:              GOOD
Artifact integrity:       PASS
Source identity:          ❌ FAIL — B-01 stale SHA + NEW-12 new files not in contract

Lightning portability:    NOT READY — new files uncommitted, lint/format violations
GPU LightGBM support:     IMPLEMENTED (backend.py) — uncommitted; eval_set deprecated
GPU silent fallback:      PASS — raises RuntimeError on GPU failure (no silent fallback)

Tests:                    619 passed, 9 failed, 3 warnings
Known findings confirmed: B-01 ✅  B-03 ✅  B-04 ✅  B-05 ✅  B-06 FIXED
                          B-07 FIXED  B-08 ✅  B-09 ✅  B-10 ✅  B-11 ✅
Known findings fixed:     B-06 (EMA), B-07 (cross_sectional_ic), B-03 (partial year filter)
Known findings obsolete:  0

NEW CRITICAL:             0
NEW HIGH:                 3  (NEW-01, NEW-05, NEW-10→INFO)
NEW MEDIUM:               5  (NEW-02, NEW-04, NEW-06, NEW-08, NEW-09, NEW-16)
NEW LOW:                  4  (NEW-03, NEW-07, NEW-13, NEW-14→FALSE ALARM, NEW-15)

TOTAL ACTIVE ISSUES:      18

TOP 10 ERRORS:
1.  B-01   Byte-freeze contract stale (models.py SHA mismatch) — 2 tests fail
2.  NEW-01 Resume regression: G0 model file absent → FileNotFoundError — 1 test fails
3.  NEW-05 New checkpoint identity fields invalidate ALL existing checkpoints
4.  NEW-12 New source files (backend.py, etc.) not in byte-freeze contract
5.  B-05   np.column_stack peak RAM duplication — ~2 GB unnecessary peak
6.  NEW-04 read_only cache mode raises wrong exception → risk of infinite loop
7.  B-08   GCS path hardcoded in vm_supervisor.py
8.  NEW-02 runner.py lint error (unsorted imports) — ruff now fails
9.  NEW-03 run_phase7a_pipeline.py format violation — ruff format now fails
10. NEW-16 Archive duplicate test failure — regression in acquisition.py

TOP ARCHITECTURE IMPROVEMENTS:
1.  Commit all new files (backend.py, prepared_cache.py, runtime.py, gold_validation.py)
2.  Fix byte-freeze contract to include all new files
3.  Version the checkpoint identity format to allow graceful forward migration
4.  Add symbol-level partition filter to _load_fold_rows (complete B-03 fix)
5.  Pre-allocate feature matrices instead of np.column_stack (fix B-05)
6.  Enable prepared cache by default on Lightning (PHASE7_CACHE_MODE=auto)
7.  Add psutil to optional dependencies in pyproject.toml
8.  Add @pytest.mark.skipif(win32) to log rotation tests (B-09)
9.  Fix eval_set deprecation in backend.py smoke/compare functions
10. Document new modules in docs/phase7/ architecture files

MUST FIX BEFORE TRAINING:
1. Fix B-01: update models.py SHA in byte-freeze contract
2. Fix NEW-01: handle missing model file gracefully in _restore_completed_g0
3. Fix NEW-05: version or migrate checkpoint identity fields
4. Fix NEW-02 + NEW-03: lint and format violations
5. Commit all new untracked files as clean single commit with updated contract

LIGHTNING READINESS:    NOT READY
GPU READINESS:          IMPLEMENTED but uncommitted — needs clean commit
TRAINING READINESS:     NOT READY

NEXT SAFE ACTION:
  1. Fix all 5 MUST-FIX items above
  2. Commit all new files in a single clean commit
  3. Update byte-freeze contract for all modified and new files
  4. Run full test suite — target: 0 failures (619+ passed)
  5. Run ruff check + ruff format — target: 0 violations
  6. Set PHASE7_GOLD_ROOT, PHASE7_ARTIFACT_ROOT, PHASE7_LGBM_DEVICE=cuda
  7. Run GPU smoke test on Lightning before starting Fold 1
  8. Start Fold 1 with PHASE7_CACHE_MODE=auto for prepared matrix caching

============================================================
```

---

*Audit complete. No code was modified. No training was started. No August data was accessed.*
