# Phase 7A scientific reconciliation — 2026-11-01

Status: **TRAINING BLOCKED.** Nothing in this document is a readiness claim. The locked
`uv` environment (Python ≥ 3.11, pyarrow, LightGBM) could not be built in the authoring
sandbox, so the full test suite, the Phase 7/7A suite and the Linux software gate were **not
executed**. See "Test commands and results" and "Remaining blockers".

No paid training was started. The August holdout was not accessed. No immutable dataset or
cache was modified. `main_trader.py`, `live_trader.py`, CoinSwitch order APIs, dashboard order
paths and Aiventra were not run.

## Starting point

| Item | Value |
| --- | --- |
| Mac checkout at start | `main` @ `4ef91d5` (an ancestor of the migration branch) |
| Authoritative base | `origin/codex/laptop-migration-20261024` @ `7102b87` |
| Hardening branch | `origin/phase7a-pre-lightning-hardening-20261003` @ `0597a4d` |
| Merge-base of the two | `24dd814` |
| Reconciliation branch | `fix/phase7a-scientific-reconciliation-20261101` (created from `7102b87`) |
| `git fetch` | **Blocked** (HTTP 403 from the sandbox proxy). Refs used are the remote-tracking refs already present in the clone. Re-run `git fetch` on a networked machine before relying on tips. |
| Working tree at start | Clean except the untracked `Claude outputs/` folder (not committed) |

The branch switch initially left 27 tracked files that matched `main`, not the target (a stale
`index.lock` interrupted the checkout). Every one of them was byte-identical to its committed
`main` blob, so nothing of the owner's was lost; they were restored to the branch tip and the
stale lock was removed after deletion was approved.

Hardening branch only (not on the migration branch): `2076328`, `9a904ee` (picked) and the
documentation commits `6d2de50`, `0a4245e`, `0597a4d` (not picked: documentation of Lightning /
GCP external-state recovery, not needed for this fix set). Aiventra/application commits
(`e0cafe2`, `b8a574d`) are on the migration branch already and were not touched.

## Reconciled commits (provenance)

| Source | Original | Here | What |
| --- | --- | --- | --- |
| hardening branch (`cherry-pick -x`) | `2076328` | `79c717b` | Gold validator validates the physical producer order of the 12h/1d features; A6 model order unchanged; +120 test lines |
| hardening branch (`cherry-pick -x`) | `9a904ee` | `04af78b` | Hermetic Linux tests, Git-anchored historical-freeze assertion (replaces the unsupported SHA assertion), synthetic plan fixtures instead of protected Gold |

New commits on this branch: `de9c3a7`, `f18f3fe`, `e7b7d82`, `9eac310`, `937e550`, `0df95b5`,
`911f910`, `4959ae2`, `347ede3`, `68bd811`, `881e7ed`, `bd43f19`, plus the report commit.
Diff versus `7102b87`: about 42 files, +3,000 / −150 lines (see `git diff --stat 7102b87..HEAD`).

## Audit findings and mandatory defects — disposition

Audit IDs refer to `CRYPTO2_MACBOOK_READONLY_AUDIT.md`. "Mandatory" numbers are the 20 items in
the implementation brief.

| ID | Disposition | Notes |
| --- | --- | --- |
| C-01 (wrong branch) / mandatory 1 | **FIXED** | Work is based on the migration tip; hardening commits reconciled above; provenance recorded |
| H-01 (Gold producer order) / 4 | **FIXED** (cherry-pick `2076328`) | Not independently re-executed here (needs pyarrow). Existing Gold is not reordered |
| H-02 (launchers) / 13 | **FIXED** | `scripts/lib/phase7_portable.sh`; uv from `PHASE7_UV_BIN` or `PATH`, `wc -c` instead of `stat -c`, GNU time only when usable. GCE supervisors/watchdogs untouched and not RunPod tooling |
| H-03 (scope by monkey-patch) / 6 | **FIXED** | `training.run_phase7_training(scope="PHASE7A_CORE20_PRIMARY")`; `phase7a-*` configs refuse the generic 58-spec CORE+EXPANDING run |
| H-04 (O(T×N) loops) / 7 | **FIXED** | `phase7/cross_section.py`; reference-equivalence tests executed (21 passed) |
| M-01 (context depends on label availability) / 3 | **FIXED (code), tests NOT EXECUTED** | See "Scientific behaviour changes". Residual: see below |
| M-02 (`release_test` only checks non-empty string) | **DEFERRED** | Not in the 20 items; scientific isolation still depends on caller discipline. Needs a measured, hash-bound release gate |
| M-03 / M-09 (environment identity) / 8 | **FIXED** | OS family + machine architecture + Python implementation now bound. Policy: one fixed Linux/x86_64 RunPod environment; Mac-generated artifacts are never production-compatible |
| M-04 (stale publication lock) / 9 | **FIXED** | Proven-dead recovery only; fails closed otherwise. Tests executed against the extracted lock logic (16 passed) |
| M-05 (run lease) / 10 | **FIXED / ALREADY_FIXED (parts)** | Active, abandoned, foreign-host and hash-bound recovery were already implemented and tested. Added `O_EXCL` creation so flock is not the sole arbiter |
| M-06 (post-TRAIN gap blocks fold) / 16 | **FIXED (reporting)** | `phase7/readiness.py` lists blocked segments up front. Blocking behaviour is deliberately unchanged and membership is not touched |
| M-07 (holdout hygiene) / 17 | **FIXED** | `research_scope.py` + CLI hook; README/RUNBOOK examples corrected. `phase6/config.py` still permits a later cutoff (legacy phase, not Phase 7A) — DEFERRED |
| M-08 (order-capable legacy code) / 20 | **NOT_APPLICABLE / guarded** | Not run or modified. Added a static test that research code imports no trader/CoinSwitch/dashboard module (executed: PASS over 45 files) |
| L-01 zero-actual directional accuracy | DEFERRED | Metric definition change would alter reported numbers; needs owner decision |
| L-02 / 19 (silent finite drop) | **FIXED** | Per-segment pre/post counts in every completed report (`finite_row_accounting`) |
| L-03, L-04 | DEFERRED | Methodological, documented in the audit; changing them changes the scientific contract |
| L-05 | DEFERRED | Redundant safeguard; purge is exact |
| L-06 macOS fsync | DEFERRED | Production target is Linux |
| L-07 `assert` invariants | DEFERRED | Separate hardening change |
| L-08 pickle model loading | DEFERRED | Local trust model; model-receipt hash binding already exists |
| L-09 README drift | **PARTIALLY FIXED** | Holdout/date examples corrected only |
| L-10 duplicate inference modules | DEFERRED | Out of scope |
| I-01 … I-05 | informational | No action |
| Mandatory 2 (membership causality) | **ALREADY_FIXED** | `TRAIN_HISTORY_ONLY_V2` in `universe.py`; `tests/phase7/test_membership_gap_causality.py` covers future-gap invariance of membership, hash, train table, clusters, tiers and numpy inputs. Not re-executed here |
| Mandatory 5 (Cal-B / OOS policy) | **ALREADY_FIXED** | `economics._policy_indices` is used by both `select_cal_b_thresholds` and `build_oos_trades` with stored `entry_time` / `label_end_time`; `test_standalone_training_remediation.py::test_cal_b_counts_the_same_non_overlapping_trades_as_oos` uses 5-minute signals with a 60-minute horizon. Not re-executed here |
| Mandatory 11 (model-only orphan) | **ALREADY_FIXED** | `training.py` raises `MODEL_ONLY` before any refit; `recovery.py` + 5 tests in `test_pre_lightning_hardening.py`. I did not add a training-loop-level end-to-end test (could not construct one without executing) |
| Mandatory 12 | **FIXED** (cherry-pick `9a904ee`) | A grep found no remaining test that reads protected Gold/Silver |
| Mandatory 14 (read-only preflight) | **FIXED / verified at unit level** | `RuntimePaths.validate` already did zero writes and rejected overlaps; added 76 tests (executed). Full `build_preflight_report` not executed |
| Mandatory 15 (bounded Fold-1 descriptors) | **ALREADY_FIXED + preparation mode added** | `_fold_descriptors(fold_ids=…)` exists and is tested; the one-spec path uses it. New `--prepare-only` mode for the single spec |
| Mandatory 18 (GPU qualification) | **FIXED** | `gpu_qualification.py` ladder; CPU LightGBM is baseline; 13 tests executed |

## Scientific behaviour changes

1. **Cross-sectional context is label-independent (M-01).** Previously
   `bind_fold_cross_sectional_context` ran on the rows of one horizon *after* label filtering, so
   `market_member_count`, market means/medians/dispersion and the three percentiles at time *t*
   changed with which symbols happened to have a valid label for that horizon. Context is now
   built from the union of all four horizons' feature rows
   (`fold_context_v3_label_independent`) and attached by `(symbol, feature_time)`; it is identical
   across horizons. Duplicates across horizons must agree exactly or the build fails.
   **Residual:** Gold is an inner join of features and labels, so a symbol-time with *no* label in
   *any* horizon (the ~20 minutes before a gap or the cutoff) is absent from Gold. Context can
   therefore still reflect that a label exists for the shortest horizon. Removing this entirely
   needs a feature-only Gold, which is immutable and was not rebuilt. DEFERRED, bounded to the
   shortest horizon's availability window.
2. **Numerics.** Mean/dispersion of market returns are now computed by grouped summation, which
   can differ from `np.mean`/`np.std` at floating-point summation-order level (relative ~1e-12
   in tests). Medians, fractions, counts, ranks, ties and memberships are exactly equal to the
   reference loop. Any cache built before this change is invalid anyway (see below).
3. **Phase 7A scope** is enforced by an explicit argument, not by patching module globals.
4. **Environment identity** now includes OS family and architecture.
5. No change to features, targets, horizons, purge, embargo, folds, hyper-parameters, seeds,
   cost policy, calibrators or the config hash.

## Identity / version changes

| Identity | Old | New |
| --- | --- | --- |
| Fold context | (implicit) | `fold_context_v3_label_independent`, added to the prepared-cache identity |
| Environment schema | `phase7_dependency_compatibility_v1` | `phase7_dependency_platform_compatibility_v2` (+ `numerical_platform`) |
| Scientific source identity | 46-file manifest | changed (source files edited; `cross_section.py` added to `TRAINING_CRITICAL_SOURCE_FILES`) |
| Configuration hash | `93f987736b1a79d26b773957` | **unchanged** (recomputed and confirmed from `research_core20_primary_v1.toml`; generic config `cc550337f1f4ee4654124bf6` also unchanged) |
| Cache publication lock | `pid=…` text | JSON owner record (pid, host, start time, token) |
| Report | — | adds `finite_row_accounting` |

## Old 60m/RAW cache compatibility verdict

`~/Crypto2Data/incoming/prepared_cache/` (cache id
`f022133827272c166b734aa5d48dc2aa4e1ce574f802461c45e33218f5e4245a`, Fold 1, CORE, A6, 60m, raw,
109 features) was inspected **read-only**:

* `CACHE_COMPLETE` contains `8d7104785f97e85b64f457b9fe842e255ce4387d94c719e95c291957b4ef53c5`,
  which equals the SHA-256 of `manifest.json`; the manifest's `cache_id` matches the folder's
  recorded id. Its recorded Gold manifest SHA (`a1420277…e711`) equals the Gold manifest verified
  below.
* **Verdict: NOT REUSABLE by the new code, by design.** The new identity contains
  `fold_context_version`, a `scientific_environment` with the platform fields, and a changed
  `scientific_source_identity` / `matrix_code_identity`; the old identity has none of the first
  two and the old source identity (`ff27ed83…`) no longer matches. The cache was *not* edited,
  re-labelled or loaded. It also encodes the pre-M-01 context, so its feature values are
  scientifically superseded. It remains valid historical evidence.
* A new cache must be derived on the Linux production environment (below).

## Test commands and results

**Not executed (blocked):** `uv sync --locked --extra dev`, `uv run pytest` (full hermetic suite),
the Phase 7/7A suite, `ruff check/format`, `crypto_ai.phase7.verify_linux`. Reason: neither the
sandbox nor the linked Mac can reach PyPI / GitHub / python-build-standalone (HTTP 403 / DNS
failure), the Mac VM has Python 3.10 (project needs ≥ 3.11) and neither machine has pyarrow or
LightGBM. I did not route around the egress policy.

**Executed** (ad-hoc environment: Python 3.13.18 in the sandbox, NumPy 2.5.3 which is *outside*
the project's `numpy<2.5` lock; `pytest`, `pydantic`, `psutil`; pyarrow stubbed to an empty module
where only an import was needed). These show the logic of the listed modules, not the locked
environment:

| Area | Tests | Result |
| --- | --- | --- |
| Vectorized cross-section vs legacy-loop oracle (`test_cross_section_vectorized.py`) | 21 | pass |
| Portable launchers + existing log-rotation tests | 17 | pass |
| Stale publication lock + exclusive run lease (extracted lock methods, real `run_lease.py`) | 16 | pass (one of my own new tests initially asserted the wrong thing for a dead PID with no start time; the *test* was corrected, the implementation was not changed) |
| `RuntimePaths` read-only validation/overlap + preparation admission | 82 | pass |
| Environment platform identity | 6 | pass |
| Post-TRAIN gap readiness | 6 | pass |
| GPU qualification ladder | 13 | pass |
| Research-scope guard logic; finite-row accounting; live-order isolation | ad-hoc assertions | pass |

Total executed pytest cases: **161 passed, 0 failed.**

**Written but not executed** (need pyarrow/LightGBM): `test_fold_context_causality.py`,
`test_research_scope_guard.py` (its CLI cases), the rewritten scope tests in
`test_phase7a_core20_primary.py`, `test_finite_row_accounting.py` (the function itself was
exercised ad hoc), the `test_gold_validation.py` additions from `2076328`, and every
pre-existing test. Existing tests that assert exact report key sets or call `slice_multiasset_fold` directly
may need adjustment once the suite can run; I could not check.

## Benchmark results (synthetic fixtures only; not the production dataset)

20 symbols, ties, NaNs, ∞ and inactive rows; sandbox CPU.

| Timestamps (rows) | Legacy percentile | Vectorized percentile | Legacy market ctx | Vectorized market ctx |
| --- | --- | --- | --- | --- |
| 2,000 (40k) | 0.08 s | 0.007 s | 0.28 s | 0.05 s |
| 8,000 (160k) | 1.4 s | 0.03 s | 1.8 s | 0.2 s |
| 32,000 (640k) | (not run) | 0.17 s | (not run) | 1.1 s |
| 285,000 (5.7M, fold scale) | (not run) | 2.5 s | (not run) | 14 s |

The legacy cost grew ~17× for 4× the timestamps (quadratic); the new code is near-linear. The
production dataset was not benchmarked.

## Data lineage (read-only inspection of `~/Crypto2Data`)

| Check | Result |
| --- | --- |
| Gold dataset `gold-phase7-0cbf2910e8d96c9d19826598` | present: 139 files = 138 Parquet partitions + `manifest.json` |
| Gold manifest | `row_count` 50,352,548; 109 features; `A6` group 109; `multiasset_features_v2`/`multiasset_targets_v2`; cutoff `2026-07-01T00:00:00+00:00`; `prospective_holdout_used=false`, `LOCKED_UNUSED`, `evaluation_authorized=false`, `july_2026_used=false` |
| Gold bytes | **all 138 partition SHA-256 match the manifest (138/138)**; manifest SHA-256 `a1420277…e711` |
| 130 physical columns, per-partition time ranges | **not checked** (needs pyarrow); the manifest flags above are metadata, not an independent scan |
| `data_manifest.json` | SHA-256 `e6532a8b…59dd0` equals the Gold lineage's `data_manifest_sha256`; Silver manifests referenced: 20 symbols × {5m, 12h, 1d} = 60; derivative bindings: 20 symbols × 3 kinds |
| Silver manifests and Silver Parquets | **NOT PRESENT in the mirror** (the references point at `/home/nssharath123/…/silver/…`; the mirror holds Bronze and Gold only) |
| Phase 7 data file count | 74,857 files under `data/phase7` (Bronze), not the historically cited 1,274,859 Phase 7 files; 131,148 Silver Parquets cannot be confirmed |
| Fold-1 descriptors | recorded in `incoming/artifacts/fold_descriptors.json`, but the code recomputes them from Silver 1d candles (see blockers) |

**DATA_LINEAGE = PARTIAL.** Gold is verified byte-for-byte against its manifest; Silver cannot be
verified from this mirror.

## Linux / RunPod status

Not run. No Linux x86_64 environment with the locked dependencies was available. The Mac VM is
aarch64 Linux with Python 3.10. `verify_linux` has not been executed.

## Remaining blockers (training stays blocked until all PASS)

| Gate | State |
| --- | --- |
| SOURCE_RECONCILIATION | **PASS (with caveat)** — base, picks and provenance recorded; `git fetch` could not be run |
| TEST_SUITE | **NOT RUN** |
| LINUX_SOFTWARE_GATE | **NOT RUN** |
| DATA_LINEAGE | **PARTIAL** — Gold verified, Silver absent |
| HOLDOUT_GUARD | **PASS (static)** — flags verified in the Gold manifest and config; date guard added; no scan of Gold timestamps |
| CACHE_IDENTITY | **PASS (design) / UNVERIFIED (execution)** — old cache correctly non-reusable; new identity untested end-to-end |
| SELECTED_FOLD_READINESS | **NOT RUN** — needs Silver 1d for descriptors, then the readiness report and a real preparation |
| RUN_LEASE | **PASS (logic executed)**; real-filesystem behaviour on the RunPod volume unverified |
| RESOURCE_PREFLIGHT | **NOT RUN** — set a measured `PHASE7_MIN_FREE_RAM_GIB`; no RAM figure was assumed |

Other open items: M-02 release gate; residual M-01 availability window; the end-to-end
`--prepare-only` path is unexecuted; push this branch (the sandbox cannot).

## Commands (NOT EXECUTED — owner must authorize each)

Prerequisites on the pod: push the branch, check it out in a full clone, mount Gold + the
checkpoint seed + the run state + the Silver 1d inputs (see blockers) and map legacy roots:

```bash
git clone https://github.com/Sharath-holla/crypto2.0.git && cd crypto2.0
git checkout fix/phase7a-scientific-reconciliation-20261101
uv sync --locked --extra dev
uv run pytest -q                       # must be fully green first
uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" --output-root "$PWD/.pytest-linux-verification"
```

Common environment (replace the paths with the real volume; do not edit scientific TOML):

```bash
export PHASE7_DATA_ROOT=/workspace/crypto2-persistent/data
export PHASE7_GOLD_ROOT=/workspace/crypto2-persistent/data/gold/phase7a_core20_primary_v1
export PHASE7_ARTIFACT_ROOT=/workspace/crypto2-persistent/artifacts
export PHASE7_CACHE_ROOT=/workspace/crypto2-persistent/prepared_cache
export PHASE7_CHECKPOINT_ROOT=/workspace/crypto2-persistent/checkpoints
export PHASE7_MODEL_ROOT=/workspace/crypto2-persistent/models
export PHASE7_REPORT_ROOT=/workspace/crypto2-persistent/reports
export PHASE7_LOG_ROOT=/workspace/crypto2-persistent/logs
export PHASE7_LGBM_DEVICE=cpu
export PHASE7_ALLOW_CLOUD_RESEARCH=1
export PHASE7_MIN_FREE_RAM_GIB=<MEASURED_POSITIVE_VALUE>
export PHASE7_GOLD_VALIDATION_REPORT="$PHASE7_REPORT_ROOT/gold-byte-validation.json"
uv run python -m scripts.validate_phase7_gold --gold-root "$PHASE7_GOLD_ROOT" --output "$PHASE7_GOLD_VALIDATION_REPORT"
uv run python -m crypto_ai.phase7.readiness --config configs/phase7/research_core20_primary_v1.toml \
  --run-root "$PHASE7_ARTIFACT_ROOT/phase7a-core20-primary-93f987736b1a79d26b773957"
```

**One-model preparation** (Fold 1, CORE, A6, 60m, raw, CPU LightGBM; builds and publishes the
prepared cache only, fits nothing):

```bash
export PHASE7_CACHE_MODE=auto
uv run python -m crypto_ai.phase7.benchmark_one_spec \
  --spec-id architecture-G0-A6-60m-raw \
  --output-root /workspace/crypto2-benchmark-isolated \
  --execute --prepare-only
```

**One-model training** (only after preparation succeeded and the owner re-authorizes cost):

```bash
export PHASE7_CACHE_MODE=read_only
uv run python -m crypto_ai.phase7.benchmark_one_spec \
  --spec-id architecture-G0-A6-60m-raw \
  --output-root /workspace/crypto2-benchmark-isolated \
  --execute
```

`architecture-G0-A6-60m-raw` is the canonical G0 balanced A6 60m raw spec. (The first of the 48 in
enumeration order is the 15m one; the 60m spec is the one the brief names.)
