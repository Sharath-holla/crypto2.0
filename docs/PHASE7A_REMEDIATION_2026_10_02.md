# Phase 7A Remediation Report

Requested report date: 2026-10-02. Continuation completed on 2026-10-03 local time.
Scope: existing Phase 7A remediation, local code/tests/documentation only. The project remains on hold.

## 1. Starting State

Frozen Git baseline: `28d3098a82952a3d09073e4d81b5281f856c072e` on `main`.
Starting HEAD: `c856996` (see `git log`).
Verified code/test remediation commit: `5c36783` (33 files). Documentation is a separate logical
commit. These commits remain local; nothing was pushed.
Both historical tags, `crypto2.0-handoff-20260906` and `phase7a-hold-20260906`, were retained.

The worktree already contained pruning/preparation/resume edits and untracked production modules.
Those changes were integrated. Unrelated work directories, audit drafts, patches, and archived
handoff files were preserved and excluded from the remediation commits. No reset, clean, revert,
history rewrite, force push, cloud operation, account access, or production training occurred.

The first full reproduction, before remediation changes in this session, was **620 passed,
8 failed, 0 skipped, 3 warnings** in 158.19 seconds. The failures were two current-source versus
historical-freeze comparisons, one INELIGIBLE G0 resume crash, and five Windows Bash tests.
The previous continuation's focused gate was **62 passed**. Active findings ERR-01 through ERR-19
are resolved or classified in the accompanying changelog.

## 2. Scientific Invariants Preserved

| Invariant | Result |
| --- | --- |
| Binance USD-M, 5m primary market | Unchanged |
| Core20, point-in-time membership, survivorship protection, HNT retained, XPIN excluded | Unchanged |
| Phase 7A CORE-only research and 48 primary A6 specifications | Unchanged |
| 16 rolling folds: 24m TRAIN, 3m Validation, 3m Calibration, 3m TEST, 3m step | Unchanged |
| 54 native A6 features; full Gold/model A6 includes 22 completed 12h and 33 completed 1d columns | Unchanged; 109 model columns must not be confused with 54 native features |
| `multiasset_targets_v2`, 15/30/60/120-minute horizons, `open[i+2]` | Unchanged |
| Actual `label_end_time` purge, 120-minute embargo, train-only preparation | Unchanged |
| G0/C0/P0/H0, fixed LightGBM scientific parameters and seeds | Unchanged for canonical CPU behavior |
| Validation, Cal-A, Cal-B, frozen TEST release, cost-aware `NO_TRADE` | Unchanged |
| Float64 rows, feature order, matrices, targets, symbol encoding | Exact synthetic equivalence verified |
| Research cutoff `[start, 2026-07-01T00:00:00Z)` | Unchanged; July unused |
| August `LOCKED_UNUSED`, used=false, evaluation_authorized=false | Unchanged; no real holdout accessed |
| Phases 1–6 source implementations and historical artifacts | Preserved |

Temporal/target/cross-sectional leakage regression tests pass locally. This is implementation
evidence, not a claim that the migrated production Gold bytes have been evaluated or validated.
GPU training is a separately identified backend and has not been declared scientifically equivalent.

## 3. Source Identity Fix

Previously, source coverage omitted newly introduced matrix/backend/validation code and execution
details were mixed into strict checkpoint equality. The active authority is now
`phase7_scientific_source_manifest_v2`: a deterministic sorted, duplicate-free manifest of
repository-relative paths and content SHA-256 hashes. Missing critical files fail closed.
CRLF is normalized to LF for active source hashes so equivalent Git checkouts on Windows and
Linux share identity. Absolute paths, Git commit, documentation, temporary files and machine
metadata are excluded.

The 42-file scientific set covers training/models/cache/backend/Gold validation, features/targets,
folds/universe/registry, calibration/economics/metrics, transitive feature helpers, source contracts,
schema and acquisition/quality helpers used for fold descriptors, and the canonical/Phase 7A
configuration files. This is an explicit dependency list, not a hash of
the whole repository. Changes to executable source comments remain conservatively invalidating.

`execution_context` records Git, OS/Python, runtime roots, LightGBM/backend/GPU evidence and
compute budget. A separate nine-file operational source manifest identifies runtime/preflight/
logging/utility code. Driver/version/path differences alone do not reject compatible science.
Backend semantics remain part of scientific resume identity: CPU/OpenCL/CUDA are not presumed
interchangeable. Different source, Gold, configuration, membership or fold identities still reject.

Tests: `test_training_source_identity.py`, `test_remediation_runtime_trust.py`,
`test_hardening_audit.py`, and the two historical baseline contract suites.

## 4. Byte-Freeze Resolution

`configs/contracts/phase7_scientific_baseline_v1_9.json` was **not rewritten**. Its exact file
SHA-256 remains `a22c17b164792e909f39f619c59ea40db23411c8e611398e11e28d0e98e3f493`.
Both freeze tests now compare its source records to exact bytes at frozen commit `28d3098`,
instead of requiring approved remediation source to match the historical source byte-for-byte.
The typed methodology assertions and active-source dependency/noninterference tests still run.

For example, the historical `training.py` SHA is
`0120914fc4c5cfba28ae2b6b808063d2796b8e4fd94fa404897d27f0af2ee774`.
The active scientific manifest SHA at this completion is
`7a191213b6098c50490951b3bccf89b4b14f750964f491c608e6242541223486`.
These identify different objects and are not interchangeable hashes. The active digest changes
because execution/cache/resume/acceptance code was remediated; methodology remained unchanged.
Historical model checkpoints with different scientific source identity are not silently promoted.

## 5. Resume Fixes

| G0/report state | Behavior |
| --- | --- |
| COMPLETE and valid model | Hash/identity/frozen calibration/threshold checks, load and reuse for H0 |
| COMPLETE and missing model | Clear checkpoint/artifact inconsistency; no replacement fit |
| COMPLETE and corrupt model | Load/hash validation failure propagates |
| INELIGIBLE | Load the report only; no model file expected |
| H0 with required G0 INELIGIBLE | Explicit INELIGIBLE report; no silent global refit |
| FAILED or unknown orphan report status | Reject as non-reusable |
| Wrong science/Gold/fold/backend identity | Reject |
| Execution-only metadata differences | Compatible if scientific identity is identical |

Fold slicing INELIGIBLE reports also resume without rewriting immutable checkpoints. New artifact
references use logical roots, or checkpoint-relative paths when no logical root applies. Historical
absolute references remain readable; explicit `PHASE7_LEGACY_*_ROOT` mappings relocate them without
rewriting historical checkpoint hashes. File SHA-256 validation still applies after relocation.
Missing/corrupt artifacts must be investigated manually; automatic model/checkpoint repair is absent.
Both runners also validate scientific source/backend/configuration/Gold identity and partition
hashes before reusing a completed top-level
training stage. Legacy stage records without that identity require per-model review instead of
bypassing the model checkpoint gate.

## 6. Prepared Cache Fixes

| Mode | Behavior |
| --- | --- |
| `auto` (default) | Load verified entry; missing entry builds; invalid entry is quarantined then rebuilt |
| `rebuild` | Ignore existing entry; publish a replacement with rollback if publication fails |
| `read_only` | Valid entries load; missing/invalid/corrupt entries raise a dedicated error; no write |
| `disabled` | No durable entry created |

Miss errors no longer inherit `FileNotFoundError`. Identity includes Gold manifest/partition hashes,
source fingerprint, current scientific source digest, config, fold/view/membership, registry/universe,
horizon/target/features/order, purge/embargo, preprocessing, versions and float64/encoding contract.
Cache locations and cache IDs are execution evidence, not model scientific identity.

Entries contain Arrow tables, float64 NumPy matrices/targets, symbol vectors, exact inventories,
shape/dtype/schema/row metadata, checksums, manifest and `CACHE_COMPLETE`. Reads reject incomplete
inventories, checksum/shape/dtype/schema drift, non-finite prepared matrices, and identity mismatch.
NumPy matrices load as memmaps. Preparation does not release TEST for selection.

Publication writes a unique temporary directory completely, fsyncs on Linux, writes the marker,
then acquires a root-wide exclusive publication lock. Concurrent writers validate an existing
winner. Auto mode preserves valid entries; rebuild is an explicit replacement. Windows uses
directory rename/move under the same lock, with completion validation. Auto corruption quarantine
retains invalid evidence. A stale lock after process death must be inspected manually; it is never
automatically broken.

`manage_phase7_cache.py` reports total, published, and temporary/quarantine bytes. Optional
`PHASE7_CACHE_MAX_GB` caps publication and fails without eviction. Explicit cleanup requires
offline mode, all relevant readable report/artifact/checkpoint roots, exact IDs, and a rescan under
the publication lock. Any referenced ID or unreadable JSON blocks cleanup. Root escape and
symlink/alias targets are refused, including aliases to another entry inside the cache root.
Cleanup permanently deletes only requested
unreferenced entries. There is **no automatic LRU eviction**. Operators must list all roots and
stop workers first; this command is not a distributed running-process detector.

## 7. Gold Backup / Validation State

Owner-supplied manual verification supersedes the old September storage-only statement:

| Evidence | Status |
| --- | --- |
| GCP → GCS basic offsite backup | BASIC GCS BACKUP COMPLETE |
| Source files / GCS objects | 139 / 139 |
| Source size / GCS size | approximately 9.1 GB / 9.01 GiB |
| Migrated Gold byte-level validation | PENDING until available on Lightning |

No GCP/GCS connection was made. Historical handoff documents remain historical evidence; their
"only VM copy" descriptions predate the operator's backup. Object counts/sizes are not proof of
partition hashes, row counts or scientific schema.

## 8. Gold Validator

The read-only validator expects dataset `gold-phase7-0cbf2910e8d96c9d19826598`, 138 Parquet
partitions, 50,352,548 rows, Core20 and all four horizons. It separately validates manifest records,
physical Parquet sets and 139 total files. Store output reports **outside** the dataset directory.
It checks partition hashes by default, required lineage/registry/universe/cutoff/holdout fields,
feature/target versions, 54 native features/order, A6 declared order, common schemas, required
target/excursion/scale fields, float64 scientific numeric fields, UTC non-null timestamps/keys,
entry and label timing, duplicate keys/partition boundaries, symbols/horizons, NaN/Inf statistics,
cross-sectional scope, and exclusive research/holdout boundaries. Infinite values fail; native
Gold NaNs are reported because missing feature availability is legitimate and finite filtering
occurs in fold preparation. Raw acquisition-union context must be rebound to fold-active context.

The interval is imported from `targets.FIVE_MINUTES_US`, not independently hardcoded. Missing
holdout flags fail closed. `--skip-file-hashes` produces `INCOMPLETE_HASH_VERIFICATION`, which
preflight rejects. The validator has passed synthetic tests; production Gold validation is NOT RUN.

## 9. Runtime / Lightning Architecture

Runtime roots/device/cache/CPU budgets are supplied through environment variables without editing
scientific TOML or changing config hashes. Explicit model/report overrides use run-scoped roots;
without overrides the legacy run layout is preserved. Phase 7A progress uses an explicit log root.
Discovery checkpoint root follows the runtime override. New checkpoint records are portable and
historical checkpoint root remapping is explicit and hash-checked.
`PHASE7_DATA_ROOT` and `PHASE7_LEGACY_DATA_ROOT` also resolve old Silver/segment/Bronze manifest
references during descriptor loading, preserving historical JSON and partition/segment checksums.
Root escape is rejected; legacy input remapping requires an explicit current counterpart root.

`python -m scripts.run_phase7a_lightning` delegates to the canonical Phase 7A runner after requiring
explicit runtime variables. Training entry requires successful preflight and a hash-verified Gold
report. The active Python path has no gcloud/GCE/tmux or `/home/nssharath123` requirement.
Historical GCP supervisors/workers remain unchanged and must not be used for Lightning.
Gold is located by dataset ID after migration, retaining old result.json bytes as evidence.
Source-stage artifacts and required Silver/daily inputs must also be migrated and verified for
descriptor construction; Gold alone is not a complete research workspace.

Preflight checks writable outputs, Gold manifest/report, backend smoke, compute budget, cache size,
RAM/disk and holdout metadata. Default minimums are 32 GiB available RAM and 25 GiB free disk;
these are preliminary floors, not measured production requirements. Skipped backend smoke means
NOT_READY. `--no-create` inspects existing ancestor disk capacity and reports missing roots without
creating them. Lightning execution remains untested on the target host.

## 10. GPU LightGBM Architecture

`PHASE7_LGBM_DEVICE` explicitly selects `cpu`, `gpu` or `cuda`. OpenCL `gpu` and `cuda` are distinct
implementations. NVIDIA L4 24 GB on Linux requires explicit CUDA evaluation and a compatible
LightGBM build. Unsupported requested GPU execution raises a detailed error without CPU fallback.
CPU retains deterministic/column-wise controls. OpenCL requests double-precision accumulation;
scientific hyperparameters and input float64 are preserved. Backend semantics are distinct resume
keys. Synthetic smoke and CPU/GPU comparison utilities do not use Gold.

Comparison reports MAE/RMSE/R²/directional accuracy/Pearson IC/Spearman IC, prediction correlation,
mean/max difference, best iteration and runtime on identical synthetic data/weights/seeds/config.
PASS means the utility executed; no unapproved scientific tolerance is implied. GPU readiness
requires target-host smoke, review of differences, VRAM/RAM measurements and owner review.

Installed LightGBM is 4.7.0. Its sklearn wrapper deprecates `eval_set` in favor of `eval_X`/`eval_y`.
The smoke/comparison code now uses the supported inputs; production fitting retains validation,
early stopping callbacks, best iteration and frozen CPU parameters. The declared minimum is 4.7.
Primary references: [LightGBM parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html),
[LGBMRegressor API](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRegressor.html).

## 11. Memory Improvements

Matrix conversion preallocates a final float64 array and fills ordered columns, avoiding retention
of a full list of converted columns plus column_stack output. Symbol one-hot augmentation fills
one final array and avoids an intermediate encoded matrix. Exact value/order/encoding tests pass.
Cache memmaps and year partition filtering are integrated. No symbol-pruning change was made:
G0/shared fold context legitimately requires all active symbols, and C0/P0 subset filtering belongs
after shared context is established. ERR-19 remains deferred pending measured I/O benefit.

RAM events record process RSS, sampled observed peak RSS and host available/total memory around
fold load, preparation, cache build/hit and model fit. Sampled peak is not a continuous OS peak.
The small synthetic benchmark observed 20,000 × 109 float64 values, 17,440,000 matrix bytes,
0.0187793 seconds conversion, RSS 176,410,624 before and 194,236,416 after. These are host-specific
observations with exact value equivalence, not comparative production RAM or speedup evidence.
Full Fold-1 preparation/cached-versus-uncached profiling remains pending on Lightning.

## 12. Windows Compatibility

Five Bash/Linux rotation tests are explicitly skipped on Windows; their Linux assertions remain
unchanged. Cache publication/concurrency/rebuild tests pass on this Windows host. Linux fsync and
Bash behavior still require the full Linux gate. The old `.pytest_cache` directory denied writes;
verification used a separate writable pytest cache directory and fresh basetemp rather than
changing permissions or suppressing warnings.

## 13. Lint / Formatting

`uv run ruff check src/crypto_ai scripts tests`: PASS.
`uv run ruff format --check src/crypto_ai scripts tests`: PASS (221 files).
Formatting/import corrections were limited to actual violations in remediation files and the
existing pruning test. `git diff --check`: PASS. `psutil` is required and locked at 7.2.2; resource
reporting no longer silently disappears. Invalid compute budgets raise ValueError, not AssertionError.

## 14. Files Changed

| File(s) | Change / why | Scientific impact | Test coverage |
| --- | --- | --- | --- |
| `pyproject.toml`, `uv.lock` | Required psutil; minimum LightGBM 4.7; locked dependencies | Supports existing fit API, no CPU parameter change | Full suite, CPU smoke |
| `training.py` | Science/execution identities; cache boundary; resume/H0 states; runtime outputs/RAM | Behavior-preserving inputs; invalid/ineligible resume now explicit | Source identity, training error/optimization/runtime trust, integration |
| `artifacts.py` | Scientific compatibility, logical/relative and legacy remapped references | Same hash-bound artifacts | Hardening/runtime trust |
| `models.py` | Backend factory, preallocation/encoding, execution evidence | Exact float64 equivalence; backend distinctions explicit | Optimization/models/integration |
| `backend.py` | CPU/OpenCL/CUDA selection, smoke, equivalence metrics | CPU semantics retained; GPU equivalence pending | Runtime/backend, CPU smoke |
| `prepared_cache.py` | Durable verified matrices, modes, publication, capacity/cleanup | Strict data/science-bound cache | Prepared cache tests |
| `runtime.py` | Paths, budgets, psutil, telemetry, root mappings | Execution metadata separated | Runtime/backend/runtime trust |
| `gold_validation.py` | Read-only fail-closed Gold gate | Rejects untrusted data; does not mutate Gold | Gold validation |
| `preflight.py` | Provider-neutral readiness checks | No research execution | Runtime trust |
| `discovery_checkpoint.py` | Corruption warnings; runtime checkpoint root | No acquisition/quality changes | Discovery and full suite |
| `acquisition.py` | Runtime relocation of immutable Silver/segment/source references | Same manifests/rows/checksums; no network or quality-policy change | Input remapping, HTF/causal segment/interval suites |
| `pipeline.py`, `runner.py`, `run_phase7a_pipeline.py` | Runtime roots and portable records; Gold-ID lookup | Canonical methodology retained | Phase7A, hardening, full suite |
| `run_phase7a_lightning.py` | Explicit runtime config and training preflight | Delegates to canonical runner | Runtime trust, CLI help |
| `phase7_preflight.py`, `validate_phase7_gold.py` | Read-only CLI gates and immutable report | No dataset mutation | Module tests/CLI import |
| `manage_phase7_cache.py` | Size reporting and explicit offline unreferenced cleanup | No automatic eviction | Cache/runtime tests |
| `benchmark_phase7_backend.py`, `benchmark_phase7_preparation.py` | Synthetic smoke/comparison/preparation utilities | No Gold/holdout use | CPU smoke, exact-value benchmark |
| `test_phase7_baseline_freeze.py`, `test_baseline_noninterference.py` | Historical Git-byte checks plus active identity coverage | Preserves frozen evidence | Contract tests |
| `test_training_source_identity.py`, `test_hardening_audit.py` | Determinism, critical coverage, compatibility, relocation | Assertions only | Focused/full gates |
| `test_training_error_classification.py`, `test_training_execution_optimization.py` | G0/H0/slicing states, identity rejection, matrix equivalence | Assertions only | Focused/full gates |
| `test_prepared_cache.py`, `test_runtime_backend.py`, `test_gold_validation.py`, `test_remediation_runtime_trust.py` | Mode/corruption/concurrency/cleanup/GPU/Gold/runtime regressions | Assertions only | Focused/full gates |
| `test_log_rotation.py`, `test_remediation_correctness.py` | Windows-only skip; actual format fix | Linux assertions/year-boundary equivalence unchanged | Full gate |
| This report, changelog, Lightning runbook | Evidence, classifications, future workflow | Documentation only | Diff review |

Files without a path prefix in this table reside in `src/crypto_ai/phase7`, `scripts`, or the matching
`tests/phase7` directory. The exact committed path list is available in `git show --stat`.

## 15. Test Results

Before: **620 passed, 8 failed, 0 skipped, 3 warnings**.
Previous focused gate: **62 passed**. Expanded continuation gate: **99 passed**.
Final focused cache/runtime/error gate: **26 passed**. Final CRLF identity regression: **9 passed**.
Final stage/source/Phase7A focused gate: **24 passed**.
Final input-remapping/descriptor-source/causal/Gold contract gate: **69 passed**.
Final cache-alias/malformed-manifest/runtime trust gate: **22 passed**.
Final full Windows gate: **665 passed, 0 failed, 5 skipped, 0 warnings** in **150.74 seconds**.

Command: `uv run pytest -q -o cache_dir=.pytest-remediation-cache --basetemp .pytest-remediation-closing-gate --junitxml=.pytest-remediation-closing-gate-report.xml`.
The final full gate includes preserved earlier-phase and leakage regression suites. Linux gate,
GPU smoke/comparison, and actual migrated Gold validation are NOT RUN here.
All five skips are the Bash/Linux-only tests in `tests/phase7/test_log_rotation.py`.
`uv lock --check` also passed. The test-generated temporary directories and XML reports were
retained locally and excluded from commits; no cleanup or unrelated-file staging occurred.

## 16. Remaining Limitations

- `KNOWN_REDUNDANT_FEATURE`: `listing_age_days` and `history_length_days` remain frozen inputs.
- ERR-19 symbol pruning deferred; no measured subset-I/O benefit demonstrated.
- `POST_PHASE7A_REFACTOR`: splitting training.py, acquisition.py and progress.py deferred.
- Automatic LRU, stale-lock recovery, model/checkpoint repair, and distributed cleanup are absent.
- Canonical CPU equivalence is covered by small fixtures; production RAM/time and GPU equivalence
  are unmeasured. L4 VRAM is not a substitute for host RAM or durable disk capacity.
- Historical evidence is preserved. A complete migrated workspace must include source-stage
  artifacts/Silver inputs used for descriptors; every legacy path/checksum must be resolved.
- Baseline contract tests require the historical commit to be present; use a full Git clone.
- The ordinary runner has no dedicated one-model selector. Its existing `--canary` runs all 48
  Fold-1 specifications. A reviewed isolated one-model benchmark invocation is a future authorized
  step, not permission to use the 48-spec canary as a substitute.

## 17. Training Readiness

Code/tooling is prepared for target-host verification. **TRAINING_READY=NO**.
**LIGHTNING_READY=YES for migration and verification tooling, conditional on Linux validation**.
**GPU_READY=NEEDS_LIGHTNING_TEST**. Gold byte validation is NOT RUN; August remains LOCKED_UNUSED.

Blocking next gates: migrate and hash-validate Gold plus required state; run the full Linux gate;
run L4 CUDA smoke/equivalence and real preparation/RAM/VRAM profiling. Then obtain a fresh owner
cost/deadline authorization for one canonical model. Review measured runtime/cost before separately
authorizing 48 Fold-1 specifications. The project remains on hold and no such training was run.
