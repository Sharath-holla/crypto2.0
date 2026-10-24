# Crypto 2.0 — Fresh Post-Remediation Architecture Audit

Audit date: 2026-10-03. Repository: `C:\Users\HP\Documents\ChatGPT\crypto2.0`.
Verified HEAD: `2dcf12bb2b7bdc8ec089d3248bbc157a9a9ef2a8`, branch `main`.
Controlling request: the owner's attachment `51988226-8474-425d-a0ff-7b9a715b4d84/Pasted text.txt`.

This is an audit, not an implementation or authorization to resume. Only this document was edited. No source, configuration, tests, freeze hashes, or commits were changed. No production fit, Fold 1, acquisition, GCP operation, Lightning session, account access, July/August data access, or Phase 8 work was performed. The required full pytest suite includes small synthetic CPU fits; no separate benchmark fit was launched. Subsequent row tracing reused a checksum-verified synthetic model produced by that test suite.

Evidence labels: **observed** means inspected code, executed check, or bounded synthetic reproduction; **reasoned** means a reachable source path or arithmetic estimate; **not verified** means no host/data/device evidence. Resource figures below are estimates, not measured real-Fold-1 peaks.

## 1. Executive Summary

The remediation is materially useful, but the active execution architecture is not yet safe to certify for production research training. The fresh Windows gate independently reproduced **665 passed, 0 failed, 5 skipped, 0 warnings**. Static gates pass. Adversarial inspection nevertheless found **5 HIGH, 4 MEDIUM, 1 LOW**, and no confirmed CRITICAL finding.

The main blockers are: a broken runner/rebuild-mode interaction; eager retention of all prepared keys and all horizon tables; result-relevant TRAIN descriptor/cluster inputs omitted from cache/model identities; orphan recovery lacking an independent binding to estimator bytes; and Gold validation covering 54 native columns rather than the complete 109-column production A6 input contract. GPU comparison also reports PASS without enforcing scientific-equivalence criteria.

No violation of the named scientific invariants or newly introduced future-data leakage was observed. This is not a proof of bitwise equivalence of every source change: the earlier `c856996` EMA repair intentionally changes leading-NaN/gap-recovery corner cases. Nor is it a byte-validation certificate for migrated Gold. July remains unused; August remains `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.

**Training readiness: NO.** Offline migration into quarantine and a full Linux verification gate are the next allowable *types* of work after owner approval, not actions authorized by this audit. Copying bytes does not imply activation or a funded compute contract.

Scope/assurance limit: repository-wide inventories and targeted text screening were performed; the active Phase 7A cache/training/resume/Gold/runtime/backend path, relevant tests, remediation documentation, README, PROJECT_CONTEXT and handoff documents 00–30 were reviewed deeply. The request's literal every-line review of all legacy `docs/**`, `src/**`, `scripts/**`, and `tests/**` was **not completed**. This report must not be represented as exhaustive certification of every legacy module. `.github/**` is absent. Unrelated legacy exchange/execution code was not run. All host-specific production gates remain open.

The pre-existing draft at this exact report path had stale assertions (40 specs, pending freeze updates, and older test warnings). This fresh report supersedes it; it does not modify either historical audit document or any scientific baseline.

## 2. Repository State

| Item | Independently checked state |
|---|---|
| HEAD | `2dcf12bb2b7bdc8ec089d3248bbc157a9a9ef2a8` |
| Branch | `main` |
| Original baseline / handoff tag target | `28d3098a82952a3d09073e4d81b5281f856c072e` |
| Hold tag target | `b641e8b914a27f6b9a00ae4be7a2cbd75a02d9ed` |
| Remediation commit | `5c3678328c03627f379ae6b4f124f0cea2fdf5ba` exists |
| Documentation commit | `2dcf12b` exists; three documents, 563 added lines |
| Baseline-to-HEAD change | 38 files; 4,511 insertions, 172 deletions |
| `5c36783` change | 33 files; 3,786 insertions, 174 deletions |
| Tracked worktree | Clean before and after audit; `git diff --stat` empty |
| Untracked work | Many pre-existing remediation directories, patches and audits; preserved. Fresh pytest scratch/results and this report are untracked |
| Remote state | Local `origin/main` remains at the historical baseline; no fetch/push/commit performed |
| Historical research completion | Discovery/acquisition and Gold complete; real Fold 1 remains 0/48; qualification NOT_YET_EVALUABLE |

`git status`, current branch, HEAD, 30-commit log, baseline diff inventory/statistics, both remediation commits and relevant changed hunks/modules were inspected. This was not a full historical-secret audit of every Git object. Annotated tag object IDs are not their peeled commit IDs; the table uses peeled commits.

## 3. Remediation Change Map

REMEDIATION_CHANGE_MAP: file paths in this portable document are repository-relative to the absolute root stated above. Coverage refers to the fresh passing suite, not real-data or GPU qualification. Risk is the remaining audit risk, not an accusation that every changed file is defective.

| FILE | PURPOSE | SCIENTIFIC IMPACT | EXECUTION IMPACT | TEST COVERAGE | RISK |
|---|---|---|---|---|---|
| `docs/LIGHTNING_PHASE7A_RUNBOOK.md` | Manual migration/verification gates | None directly | Operator sequencing | Source comparison | Medium: gates not executed |
| `docs/PHASE7A_REMEDIATION_2026_10_02.md` | Remediation evidence and limits | None directly | Handoff | Fresh gate comparison | Low: claims need host evidence |
| `docs/PHASE7A_REMEDIATION_CHANGELOG.md` | Change history | None directly | Traceability | Commit comparison | Low |
| `pyproject.toml` | psutil and development exclusions | Dependency context | RAM observation/install | uv lock check, suite | Medium: GPU binary not pinned by lock |
| `uv.lock` | Locked dependency resolution | Numerical versions | Reproducible CPU environment | uv lock check | Medium: build/driver environment remains separate |
| `scripts/benchmark_phase7_backend.py` | Synthetic smoke/comparison CLI | Diagnostic only | GPU gate tooling | Backend tests indirectly | Medium: unconditional comparison PASS |
| `scripts/benchmark_phase7_preparation.py` | Bounded synthetic matrix check | Exact float64 value/order check | Preparation timing | Matrix tests indirectly | Low; not a real-Fold memory profile |
| `scripts/manage_phase7_cache.py` | Offline named-entry cleanup | Preserves referenced inputs | Storage management | Prepared-cache cleanup tests | Medium: operator must provide every reference root |
| `scripts/phase7_preflight.py` | Neutral preflight wrapper | None directly | Environment gate | Runtime-trust tests | Medium: incomplete capacity checks |
| `scripts/run_phase7a_lightning.py` | Required-env wrapper | Delegates canonical plan | Neutral paths/preflight | Runtime-path unit coverage | Medium: no real Studio evidence |
| `scripts/run_phase7a_pipeline.py` | Runtime roots, Gold locating, stage resume | Included in science identity | Portable primary dispatch | Stage identity/runtime tests | Medium: canary still 48 specs |
| `scripts/validate_phase7_gold.py` | Read-only validator CLI | Verifies data contract | Migration gate/report | Gold validator tests | High: incomplete full A6 contract |
| `src/crypto_ai/phase7/acquisition.py` | Exact archive/reconciliation checks | Rejects invalid source records | Fail-closed acquisition | Archive/reconciliation tests | Low in reviewed changes; whole module remains complex |
| `src/crypto_ai/phase7/artifacts.py` | Logical checkpoint references/metadata normalization | Science vs execution compatibility | Portable resume | Checkpoint/runtime tests | High through orphan adoption; Medium write race |
| `src/crypto_ai/phase7/backend.py` | CPU/OpenCL/CUDA parameter dispatch | Device numerical semantics | Fail-closed requested-device errors | CPU smoke, mocked GPU failure | Medium: actual device/equivalence evidence missing |
| `src/crypto_ai/phase7/discovery_checkpoint.py` | Warnings for rejected checkpoints | No selection change observed | Diagnosable cold/resume state | Discovery/hardening tests | Low |
| `src/crypto_ai/phase7/features.py` | Earlier causal EMA seed/gap fix | Intentional corner-case value repair | Avoid all-NaN cascades | Remediation-correctness/features tests | Medium: not universally byte-equivalent to old implementation |
| `src/crypto_ai/phase7/gold_validation.py` | Manifest and physical-byte audit | Guards holdout/schema | Read-only activation gate | Hash/schema/holdout tests | High: 55 HTF columns not fully checked |
| `src/crypto_ai/phase7/metrics.py` | Earlier grouped IC optimization | Reference-formula equivalence tested | Avoid repeated full timestamp scans | Reference IC test | Low within tested domain |
| `src/crypto_ai/phase7/models.py` | Matrix preallocation, prepared inputs, reuse/backend | Float64/features/targets preserved | Lower temporary matrix pressure | Execution optimization/model tests | High: estimator identity not content-bound |
| `src/crypto_ai/phase7/pipeline.py` | Runtime roots/Gold resume locating | Stage identity checks | Portability | Pipeline/identity tests | Medium: generic cold train still uses persisted manifest path |
| `src/crypto_ai/phase7/preflight.py` | Capacity/Gold/backend checks | No direct training selection | Readiness report | Runtime-trust tests | Medium: PASS too coarse for real workload |
| `src/crypto_ai/phase7/prepared_cache.py` | Arrow/NumPy durable boundary | Exact prepared inputs persisted | Restartable preparation | Roundtrip/corruption/cleanup/concurrency tests | High: runner rebuild, identity, memory integration |
| `src/crypto_ai/phase7/runner.py` | Runtime checkpoint roots | No methodology change observed | Provider-neutral locating | Existing runner tests | Low |
| `src/crypto_ai/phase7/runtime.py` | Paths/budget/events/RSS | Execution-only by design | Env overrides and diagnostics | Runtime/backend/trust tests | Medium: persistence/cgroup/GPU memory not proven |
| `src/crypto_ai/phase7/training.py` | Cache/resume/source identity integration | Stronger guards, incomplete input identity | Main orchestration | Training, orphan, G0/H0 tests | High: multiple confirmed integration defects |
| `tests/contracts/test_phase7_baseline_freeze.py` | Separate historical frozen files from approved operational work | Freeze remains enforced | Correct current contract | PASS | Low; no freeze update needed for this audit |
| `tests/phase7/test_gold_validation.py` | Gold integrity tests | Negative holdout/schema cases | Migration assurance | PASS | Medium: reduced 54-column fixture masks production gap |
| `tests/phase7/test_hardening_audit.py` | Hardening assertions | Scientific safety | Regression detection | PASS | Low within scope |
| `tests/phase7/test_log_rotation.py` | Windows exclusion for Bash tests | None | Honest platform gate | Five Windows skips | Medium: Linux gate remains open |
| `tests/phase7/test_prepared_cache.py` | Durable-cache tests | Exact roundtrip/identity | Corruption/locking/cleanup | PASS | Medium: rebuild loaded through auto, not runner rebuild |
| `tests/phase7/test_remediation_correctness.py` | Year pruning, EMA, IC equivalence | Reference comparisons | Optimization regression checks | PASS | Medium: single-year and fully missing-year cases need explicit coverage |
| `tests/phase7/test_remediation_runtime_trust.py` | Preflight/path/trust tests | Config identity stays stable | Host/path fail-closed checks | PASS | Medium: host storage/GPU still mocked or synthetic |
| `tests/phase7/test_runtime_backend.py` | Budget/backend tests | Device dispatch | Error handling | PASS | Medium: mocked OpenCL failure not actual CUDA build |
| `tests/phase7/test_training_error_classification.py` | INELIGIBLE vs defects/resume | Prevent false scientific ineligibility | Fail-closed training failures | PASS | Medium: harness disables durable cache |
| `tests/phase7/test_training_execution_optimization.py` | Prepared reuse/concurrency | Exact inputs and G0/H0 reuse | Avoid redundant work | PASS | Medium: no production-size memory gate |
| `tests/phase7/test_training_source_identity.py` | Content/path/source-change identity tests | Strong source binding | Portable resume | PASS | Medium: tests do not prove transitive input completeness |
| `tests/phase7_2/test_baseline_noninterference.py` | Protected baseline isolation | Preserves frozen work | Noninterference assurance | PASS | Low |

No baseline-to-HEAD differences were observed for canonical configuration, target generation, fold definitions, universe selection source or economics source. A source file being unchanged does not eliminate incomplete integration keys.

## 4. Test Results

Fresh full-suite command, executed on this Windows host:

```powershell
uv run pytest -q -o cache_dir=.pytest-post-audit-cache --basetemp .pytest-post-audit-full --junitxml=.pytest-post-audit-full-report.xml
```

Observed terminal result: **665 passed, 5 skipped in 178.53s**; no failures or warnings. JUnit independently records 670 cases, 0 failures, 0 errors, 5 skipped, 178.513s. The five skips are `tests/phase7/test_log_rotation.py` Bash/Linux operational cases at lines 45, 57, 72, 80 and 84. They are not silently ignored scientific failures.

| Gate | Command/result |
|---|---|
| Ruff | `uv run ruff check src/crypto_ai scripts tests` — PASS |
| Format | `uv run ruff format --check src/crypto_ai scripts tests` — PASS, 221 files already formatted |
| Lock | `uv lock --check` — PASS, 31 packages resolved |
| Compilation | `uv run python -m compileall -q src scripts tests` — PASS, exit 0 |
| Diff whitespace | `git diff --check` — PASS |
| Configured typing | No mypy/pyright gate configured; NOT APPLICABLE, not fabricated PASS |
| Real Gold bytes | NOT RUN |
| Full Linux suite | NOT RUN |
| L4/OpenCL/CUDA smoke | NOT RUN |
| CPU/GPU numerical equivalence | NOT RUN |

The suite was executed once freshly; bounded adversarial probes then checked uncovered paths without additional fits. One initial row-trace probe had an invalid audit fixture identity (`feature_columns` omitted), failed, and also exposed Windows open-memmap cleanup sensitivity. The corrected fixture completed. The failed diagnostic is not hidden and is not counted as a canonical production-gate failure. The final report does not attribute that malformed-input error to canonical training.

## 5. Scientific Contract Verification

| Invariant | Evidence/conclusion |
|---|---|
| Binance USD-M, 5m primary | Canonical configs/contracts preserved; Spot remains distinct |
| Core20 / HNT / XPIN | Frozen Core20 retained; HNT present, XPIN absent; no retroactive survivorship edit |
| CORE primary | Phase 7A wrapper limits canonical research view to CORE; general Phase 7 also supports EXPANDING |
| 16 folds | Canonical plan still generates 16 |
| 48 A6 primary specs | Current Phase 7A primary selection produces 48, not 40; weighting and symbol-ID comparisons explain count beyond 4×4×2=32 |
| A6 columns | **54 native + 22 completed 12h + 33 completed 1d = 109 production model columns**; do not conflate 54 native with full A6 |
| Targets | `multiasset_targets_v2`; raw and volatility-normalized; horizons 15/30/60/120 minutes |
| G0/C0/P0/H0 | Global, cluster, per-symbol and hybrid dispatch retained |
| Entry | `feature_time=open_time[i]+5m`; one decision-latency bar gives entry `open[i+2]`, feature_time+5m |
| Purge/embargo | Actual label_end_time strictly before segment boundary; 120-minute embargo retained |
| Cal-A / Cal-B / TEST | Cal-A calibrator, Cal-B cost thresholds, frozen identity before TEST release; TEST not selected on |
| NO_TRADE | Null threshold produces no trades, not a fabricated profitable result |
| Universe and ranks | TRAIN-as-of descriptors/membership; acquisition-union Gold ranks rebound to fold-eligible context |
| Survivorship | Lifecycle-aware registry and eligibility remain; no padding delisted history |
| HTF availability | Completed/as-of higher-timeframe logic remains causal in inspected paths; validator completeness is a separate weakness |
| Balancing/normalization | Per-symbol balanced weights and causal ex-ante scale retained; no float32 conversion |
| Scientific hyperparameters/seeds | Canonical learning rate/leaves/depth/sampling/regularization/early stopping/seed=42 unchanged |
| July/August | Exclusive July 1 cutoff; July unused; August holdout locked/unused/unauthorized |
| Earlier phases | Freeze/noninterference tests pass; Phase 5/6 artifacts were not altered |

Verdict: **NO observed named-invariant regression**, not unconditional scientific certification. POST-NEW-03/04/05 can create incorrect reuse/acceptance under changed or stale inputs; no evidence shows historical production results actually affected. Since real Fold 1 has no completed reports, 0/48 says nothing about model quality.

### One observation traced through the boundaries

Observed, synthetic fixture only: `test_tiny_pipeline_connects_and_is_reproducible`'s 2022 dataset, two model features, 60m raw G0. It is not a canonical one-model benchmark or a test of real 109-feature Gold. Existing `run-b/model.joblib` was loaded only after its checkpoint/file hashes validated. No new fit was performed for this trace.

| Boundary | Observed identity/value |
|---|---|
| Raw candle | BTCUSDT, index 1607, open 2022-04-02 13:55 UTC; open `52439.632258306774`, close `52433.52295434922` (synthetic fixture values) |
| Feature | 2022-04-02 14:00 UTC; return_5m `0.00007205575101809636`, range_pct `0.0021163851535710393` |
| Target | Entry open at 14:05 (`i+2`), `52454.251952774735`; endpoint at 15:05 (`i+14`), `52525.198943752686`; raw return `0.0013525498570035044` equals endpoint/entry−1 exactly in fixture arithmetic |
| Gold | Joined key `(BTCUSDT, 14:00 UTC, 60m)` read from suite-produced Parquet; same feature/entry/end/target |
| Fold | `fold-mini-integration`, test segment; 120m embargo moves first released test observation beyond nominal 12:00 start; label end before 2022 test end and research cutoff |
| Preparation | Same ordered two columns; train/validation finite filter; float64 matrices |
| Durable cache | New ephemeral synthetic auto-mode entry; marker/checksums validated; loaded train matrix exactly equal to prepared matrix |
| Model matrix/model | Existing fixture G0 predicts covered observation `0.0006625636433155109` |
| Calibration | Stored Cal-A calibrator gives `0.0005346261861842122`; no refit or TEST tuning |
| Threshold | Stored `CAL_B_ONLY` global threshold is null |
| TEST/economics | Observation produces no trade; whole fixture TEST trade count 0 agrees with stored report |
| Freeze/checkpoint/report | Frozen identity `d4201d0152d12dafd7200545`; original checkpoint is complete with expected synthetic identity; report and model frozen fields validated |

The added ephemeral cache uses an explicitly synthetic trace identity rather than asserting the production identity is complete. This joins existing test boundaries without proving the full production runner/cache-mode integration; POST-NEW-01 remains reproduced.

## 6. Source Identity

Observed current scientific manifest SHA-256:
`7a191213b6098c50490951b3bccf89b4b14f750964f491c608e6242541223486`.
Algorithm: `phase7_scientific_source_manifest_v2`, **42 files**. A separate operational manifest covers nine files.

Included training-critical modules cover training, models, features, targets, folds, universe, registry, segments, quality, acquisition, Gold creation/validation, cache, backend, artifacts, calibration, metrics, economics, canonical configs and the Phase 7A dispatch script. Absolute root, Git commit and host stat metadata are not hashed. CRLF is normalized to LF, records sorted/deduplicated, and missing files hard-fail.

| Identity test | Result |
|---|---|
| Change critical source | Existing source-mutation tests PASS; changes manifest |
| Feature/target/backend source | Included in authoritative inventory; byte change changes digest by construction |
| Change docs/runtime report | Excluded; irrelevant-artifact test PASS |
| Change root or file-list order | Existing relocated fixture test PASS |
| Windows CRLF vs Linux LF | Existing test PASS |
| Change OS file metadata only | Not an input to digest; reasoned unchanged |
| Change comments in critical source | **Changes identity**, contrary to the requested comment-stability property; POST-NEW-10 |

No obvious missing direct numerical implementation module was found in the inspected active path. However source closure is not the same as data-input closure: causal descriptor/cluster hashes are missing (POST-NEW-03). Third-party numerical builds/versions are recorded operationally, not bound into an approved compatibility/equivalence contract. Runtime/progress exclusion is currently reasonable because paths/budget/reporting are operational; future changes that alter scientific selection there must promote the affected module into the scientific set.

Over-inclusion: operational-only edits inside artifacts, acquisition, pipeline or the dispatch script invalidate resume conservatively. Do not switch hastily to AST hashing; that can miss meaningful constants, imports or packaging effects. Prefer an explicit reviewed policy/version if less conservative invalidation is later required.

## 7. Execution Context

Execution metadata records Git, Python/OS, LightGBM/backend/device information, compute budget, roots and the operational source digest separately from scientific resume identity. Checkpoint compatibility normalizes selected legacy execution fields; backend semantics (`cpu`, `gpu`, `cuda`) remain part of expected model/stage identity. Thus moving a compatible CPU run to another machine can be accepted without allowing a CPU checkpoint to impersonate CUDA.

False rejection risk: comments/operational changes inside science-listed files invalidate otherwise equivalent work. False acceptance risk: identical source/backend names do not establish equivalent LightGBM binary, dependency ABI or prediction semantics across arbitrary versions. Cross-machine resume is conditionally portable, **not** a promise that any environment is scientifically compatible. Pin the locked environment, record build/compiler/driver details, then qualify changed numerical environments before reuse.

Prepared-cache keys deliberately do not depend on backend because the prepared float64 input is device-neutral. Model/stage keys do depend on backend. That separation is sensible.

## 8. Gold Architecture

Expected production data, taken from contracts/handoff and owner transfer report, not remeasured here:

- Dataset `gold-phase7-0cbf2910e8d96c9d19826598`.
- 138 Parquet partitions, 50,352,548 rows; 139 objects including manifest.
- Approximately 9.1 GB source / owner-reported 9.01 GiB GCS. Counts and rounded sizes are transfer inventory evidence, not checksum evidence.

The validator reads physical Parquet bytes, not merely metadata. It checks partition SHA-256, manifest/physical inventories, total rows, per-partition schema agreement, 54 native names/order/float64, target fields/version, key/timestamp types, exact entry/horizon timing, actual symbols and horizons, duplicate keys/boundaries, numeric Inf, holdout flags/cutoffs and acquisition-union scope. NaNs are counted rather than globally forbidden, because warmup/unavailable causal context may legitimately be NaN before training finite filtering. `--skip-file-hashes` returns incomplete verification and is unsuitable for activation.

**POST-NEW-05:** the validator does not establish the complete canonical 109-column A6/HTF contract. It derives A6 from the supplied manifest and only requires/audits the native 54 numeric features. The existing reduced fixture returns PASS with A6 containing just 54. Additional declared HTF feature presence/order/types/Inf and required fold-rebinding helper inputs are not fully checked. Matching partition schemas to each other is not matching them to an authoritative full schema.

Preflight accepts a prior PASS report bound to the manifest SHA; it does not freshly rehash every partition itself. The training loader does rehash manifest-listed partition bytes, which prevents treating that particular omission as a demonstrated training bypass. Keep Gold mounted read-only after a fresh activation validation, and retain an independently frozen manifest/hash anchor rather than trusting mutually consistent rewritten files.

## 9. Fold Architecture

Canonical first fold is `fold-000-a0e9a4f72689`: TRAIN [2020-01-01, 2022-01-01), validation [2022-01-01, 2022-04-01), calibration [2022-04-01, 2022-07-01), TEST [2022-07-01, 2022-10-01). These are historical 2022 dates, not the prohibited July 2026 buffer. The global research cutoff remains 2026-07-01 exclusive.

`slice_multiasset_fold` applies actual label-end purge, embargo, point-in-time eligibility, gap masks and fold-specific cross-sectional rebinding. Cal-A and Cal-B are separate. `_test` is released only with a frozen identity. This is strong discipline, although Python object privacy is not a security boundary: internal code can access `_test`, and cache files legitimately persist TEST data. Trust must come from reviewed causal flow and access policy, not a field name alone.

TRAIN descriptors govern clustering and liquidity policy. Membership hashing captures eligibility/history/quality/liquidity membership but not every numerical descriptor used by clustering. POST-NEW-03 means membership equality alone is insufficient for prepared/model reuse. The ordinary pipeline's immutable descriptor artifact mitigates casual in-place mutation; it does not complete the lower-level cache/checkpoint key or prove correctness of a newly adopted run.

## 10. Cache Architecture

The durable boundary is well chosen: persist finite prepared segment tables and train/validation arrays before fitting. Storage uses five Arrow tables, seven non-pickle NumPy arrays, metadata, manifest hashes and `CACHE_COMPLETE` bound to manifest bytes. Reader checks exact inventory, identity, checksums, array dtype/shape, table schema/row counts, train/validation vector dimensions and finite numeric matrices. Float64 remains intact; `.npy` uses `allow_pickle=False` and read-only memmap.

| Mode | Intended behavior | Audited status |
|---|---|---|
| auto (current default) | Validate hit; prepare missing; quarantine corrupt | Unit roundtrip works; key completeness and memory issues remain |
| read_only | Valid hit only, no rebuild/quarantine | Absent/corrupt tests hard-fail with distinct exceptions |
| rebuild | Ignore old lookup, publish replacement, then train | **Broken in runner**: post-write load uses same miss-forcing object |
| disabled | No durable lookup/write | Works; loses preparation on interruption |

Publication uses an exclusive global writer lock, temporary child directory, flush/fsync on POSIX, completion marker and final directory move, with rebuild backup/rollback. Concurrent valid-winner publication is tested. Linux production durability differs from the Windows rename fallback; full Linux crash/power-loss testing was not run. A killed process can leave temporary directories, backup/quarantine entries or a stale lock; ownership/liveness and explicit offline recovery remain operational requirements.

Checksums establish byte agreement with a trusted manifest, not independent truth of every row relationship. The reader does not recompute every matrix cell/row-key mapping from Arrow. More importantly a cache can be perfectly intact yet wrong for current causal descriptors because its key omits them. Safe cleanup refuses named referenced entries and aliases/symlinks; normal filesystem trust still matters, and external tampering is outside an unsigned local manifest's threat model.

## 11. Resume Architecture

Valid complete checkpoints validate expected scientific metadata and hashes of referenced files. Completed G0 is restored into the H0 reusable pool, preventing silent retraining of its base. INELIGIBLE G0 is tracked and makes dependent H0 ineligible rather than fabricating a base. FAILED or unexpected report statuses are not adopted as completed scientific work. Identity mismatches fail closed.

However runner resume first opens/preloads cache keys and possibly fold tables before deciding each model is complete. Fully completed work can therefore incur avoidable preparation/cache scans (POST-NEW-02). And the orphan path is a different trust path from valid checkpoint reuse: it loads a joblib bundle and compares structural model metadata plus frozen calibrator/threshold fields, then mints a new checkpoint checksum. This does not independently bind the fitted estimator to the report (POST-NEW-04).

Wrong source/config/Gold/backend is rejected in checked paths. Different roots and Git commit with unchanged scientific identity can be accepted via explicit root mappings. Arbitrary stale or rewritten metadata is not an independently authenticated scientific record. Orphans need a report-bound model digest validated **before deserialization**, not just a new digest after acceptance.

## 12. Checkpoint Architecture

| Scenario | Present behavior / assurance |
|---|---|
| Normal completion | Report then model then checkpoint; valid checkpoint checks both files |
| Preparation killed before cache publish | Completed inputs/checkpoints preserved; partial cache not a valid hit; preparation may repeat |
| Fit killed/OOM/GPU error | Prepared cache can survive; current estimator fit is lost; no fit-state checkpoint |
| After model, before checkpoint | Orphan report/model adoption exists but has content-binding gap |
| After report, before model | COMPLETE orphan report missing model hard-fails; no safe automatic retry transaction |
| Corrupt checkpoint JSON | Completion rejected rather than silently trusted; orphan path still requires stronger proof |
| Missing model / wrong checksum | Valid checkpoint fails verification; missing orphan model errors; a loadable replacement orphan remains weakly bound |
| Wrong Gold/config/source/backend | Expected metadata comparison rejects |
| Different root | Logical root + relative path supports migration with revalidated hashes |
| Same science/different Git commit | Execution-only Git metadata does not unnecessarily reject |
| INELIGIBLE | Reusable terminal scientific eligibility result; no serialized estimator required |
| FAILED | Not falsely promoted to COMPLETE; operational error must be addressed |

Atomic rename is not equal to power-loss durability. Cache explicitly fsyncs on POSIX; JSON/model/checkpoint helpers do not consistently fsync files/directories. Interrupted writes generally fail closed, but there is no shared artifact transaction proving a durable report/model/checkpoint set. POST-NEW-06/08 apply.

## 13. Artifact Architecture

Logical-root checkpoint references improve portability and hash-based reuse. Relative paths are confined to configured logical roots in the inspected branch; legacy absolute roots require explicit mappings. Existing immutable artifacts refuse differing content in normal single-writer operation. Source and scientific metadata separate from execution context is a sound design.

Two qualifications matter: (1) file-level check-then-replace is not immutable under conflicting simultaneous writers; (2) report/model publication is not transactional or consistently durable. A COMPLETE report alone does not mean a completed checkpoint. Retain a single operational owner and add a run-level exclusive lease before parallel independent processes are permitted.

Generic `phase7.pipeline.run_stage` cold train still uses a persisted `gold["manifest"]` path, whereas the active Phase 7A Lightning path locates runtime Gold. This is a **scope-limited portability weakness**, not an active Phase 7A Lightning blocker. Avoid claiming the whole historical/general framework is provider-neutral merely because the Phase 7A route is neutral.

## 14. Memory Architecture

Preallocation in `models._matrix` removes the old list-of-full-columns plus `np.column_stack` construction. It does not remove Arrow buffers, column `combine_chunks`/conversions, finite masks and filtered tables, advanced-indexed train/validation subsets, appended symbol-ID matrices, LightGBM binning/internal buffers, prediction/calibration arrays or retained G0 models. Threaded C0/P0 jobs can overlap independent subset/fit allocations. Symbol Unicode memmaps are converted back to object arrays on load.

The bigger problem is orchestration. `training.py:1067–1160` opens every expected cache key; cold loading holds all four horizon tables and sliced folds; `cached` keeps each new bundle for the fold. For CORE A6 there are **8 durable keys per fold** (4 horizons × 2 targets), despite 48 specs sharing those keys. Every key contains both Arrow tables and NumPy train/validation features. Raw/normalized and horizon variants duplicate much feature payload. Finite validation scans every X/Y memmap, so memmap is not a guarantee of negligible working-set pressure.

### Auditable arithmetic, not measured RSS

Use an illustrative upper-availability first-fold calendar: 20 symbols × 288 rows/day × 1,004 days = 5,783,040 rows per horizon. TRAIN+validation: 20 × 288 × 821 = 4,728,960 rows. At 109 float64 columns, each numeric feature row uses 872 bytes.

| Payload | Estimated GiB before targets/strings/other columns |
|---|---:|
| One horizon, all-segment feature payload | 4.696 |
| One train+validation X pair | 3.840 |
| Four retained cold horizon feature payloads | 18.786 |
| Eight retained X pairs alone | 30.724 |
| Eight durable entries, tables + X feature payload | 68.295 |

These are allocation/storage-equivalent payload estimates under full symbol coverage, not resident-memory lower bounds: Arrow/memmap pages can remain nonresident, purge/gaps/finite filtering/delistings reduce rows, and IPC/array layout differs. OS paging can instead cause thrash. Extra columns, copies, fit buffers and drivers increase peaks. A row-availability factor `q` scales these main terms approximately linearly but must be measured from validated data, not guessed as zero.

Planning scenarios only: a single-horizon/single-key base might require roughly 10–20 GiB including other buffers; cold multi-horizon paths can plausibly reach 30–60 GiB; retained warm/mixed keys plus fits can plausibly pressure 60–100+ GiB. These ranges have no real-Fold empirical calibration and are not capacity certificates or strict worst-case bounds. Worst case is not bounded by the unused 8 GiB `memory_guard_gb` setting, and concurrent fit allocations can exceed them.

**32 GiB: not approved**, little credible headroom on current eager path. **64 GiB: not approved without profiling**, especially cache preload and 4 concurrent GPU/CPU fits. Keep float64. Fix bounded lazy key retention and horizon streaming, release references, then profile cold/hit/resume peaks with an enforced budget before 48 specs. A safe one-model selector must avoid preloading all eight keys.

## 15. Disk Architecture

Prepared IPC/NumPy data is not compressed like the ~9 GiB Gold Parquet corpus. One key's feature-only estimate above is ~8.54 GiB. With target/timestamp/context/string/metadata columns, an illustrative **9–14 GiB/key**, **72–112 GiB/Fold 1**, and **1.125–1.75 TiB for 16 folds** is a reasonable capacity-planning scenario under the stated full-availability approximation, not a measurement. The feature-only approximation for 128 entries is ~1.07 TiB. Real fold calendars/listings/finite row sets vary. Gold, source datasets, models, reports, temp copies, rebuild backups and quarantine are additional.

There is **no finite configured global worst-case retention bound** by default: cache cap is optional, and interrupted/quarantined generations can accumulate. The publication cap checks after the temporary entry is fully written. This protects final acceptance but not filesystem exhaustion during construction. The old draft's claim that `projected=current` necessarily undercounts the new temporary entry is incorrect: `cache_size_report` already includes it. The real defect is timing and per-filesystem coverage, POST-NEW-07.

Planning recommendation, not spending authorization: budget at least ~256 GiB persistent working storage for isolated Fold-1 preparation with reserve, and consider >=2 TiB for retaining all 16-fold caches **only after measuring actual bytes and approving retention**. Available capacity must include simultaneous temporary generation and source artifacts; nominal provisioned capacity is not usable free capacity.

Recommended policy: warning at 70% utilization; block new entry construction around 85% or sooner if free space cannot hold one largest estimated entry plus safety reserve; configure a publication cap no greater than ~80% usable filesystem capacity. Reserve at least max(25% capacity, two largest entry sizes) during rebuild/migration until profiling refines it. Inspect each distinct filesystem separately.

No automatic LRU is required for correctness. Current offline exact-ID cleanup is safer than blind eviction, but insufficient as a long-run retention policy: completed reports/checkpoints reference entries and protect them. Keep all active/reference roots in inventory, stop every reader/writer, archive referenced generations with owner approval, verify archive hashes, then authorize targeted removal. Never auto-delete Gold, valid discovery/acquisition/60 candle checkpoints, historical Phase 5/6, or an entry supporting a live checkpoint. No cleanup was performed by this audit.

## 16. Concurrency Architecture

`ComputeBudget.resolve` checks positive values, detected logical CPU limits and workers ≤ total; per-estimator threads are clamped so workers×threads ≤ total. For default max_workers=4/model_threads=4:

| Logical CPUs | Workers | Threads/model | Concurrent estimator thread budget |
|---:|---:|---:|---:|
| 8 | 4 | 2 | 8 |
| 16 | 4 | 4 | 16 |
| 32 | 4 | 4 | 16 |

One global fit does not use four concurrent estimators. C0/P0/hybrid partition work uses the pool. CPU arithmetic is sound for these explicit budgets, but `os.cpu_count()` is not necessarily a container/cgroup quota or affinity budget; Arrow/BLAS/other native thread pools are not globally governed. Invalid worker counts below CPU capacity fail with a clear ValueError; the old draft's alleged zero-thread/assertion bug does not apply to current code.

GPU concurrency is a separate resource. Four CPU-budgeted workers can submit multiple estimators to one L4 without a device-memory admission controller. Runbook's explicit workers=1, threads=4 is a sensible first diagnostic setting, not automatic proof. L4 24 GB is the owner-specified target, not an inspected device. Model concurrency, GPU peak VRAM and source/preparation RAM need independent measurements.

Cache publication has a global writer lock. Models/reports/checkpoints lack an equivalent cross-process run lease. Threaded independent estimator jobs are different from launching two processes into identical run roots. POST-NEW-08 reproduces the latter artifact race.

## 17. PyArrow / I/O

Current training constructs `ds.dataset(..., partitioning="hive")` and adds a year predicate in `_load_fold_rows` when `year` exists, alongside half-open feature_time and horizon filters. End year is calculated using end−1 microsecond, so January 1 exclusive end does not unnecessarily include the next year. Exact sorted logical equivalence against the non-partitioned reference passes for multi-year and January-boundary fixtures, including a symbol with a missing 2020 partition.

The current parametrized equivalence test does **not** independently cover every requested case: an explicit same-year range, a whole missing year for all symbols, and lifecycle cutoffs within a delisted symbol's year still deserve named tests. The sparse HNT fixture models absent data but is not itself a real delisting validation. No missing records are manufactured or padded.

Optional optimizations: project only required features/target/helper/key fields, prune to eligible symbols after point-in-time selection, verify row-group statistics predicate pushdown and horizon filtering on real files. Preserve rank-rebinding inputs and exact row/value/order equivalence. These are separate from the must-fix eager retention; no real scan speedup or RAM reduction was measured here.

## 18. Lightning Portability

Active path is the Lightning wrapper → Phase 7A dispatcher → runtime/preflight/cache/training backend. It requires explicit data/Gold/artifact/cache/checkpoint/model/report/log roots plus device and cache mode; train requires a compatible Gold validation report and preflight. It does not create GCE/GCS resources or shell out to old supervisors. Gold is read, not repaired/rewritten by training.

Path checks prove directories exist/writable and Gold is present. They do **not** prove Studio storage survives stop/restart, is a persistent mount, has an expected filesystem/device ID, or maps distinct generations without aliasing. Writable ephemeral `/tmp` is not made persistent by naming it `PHASE7_CACHE_ROOT`. Owner must verify persistence and approved mount/root separation. Creating output directories is intentional, so wrong-but-writable env roots can still be created; explicit reviewed runtime configuration remains essential.

Hardcoded dependency classification from repository-wide text screening:

| Dependency group | Classification | Why |
|---|---|---|
| User paths/GCE/GCS/tmux in `phase7_vm_supervisor.py`, `phase7a_vm_supervisor.py` | HISTORICAL ONLY | Not called by active Lightning route; retained audit tooling, do not run |
| `/home/nssharath123`, fixed uv and `/usr/bin/time` in `run_phase7_worker.sh`, `run_phase7a_worker.sh` | HISTORICAL ONLY | Old worker wrappers, not required neutral entrypoint |
| `phase7a_control_plane_watchdog.ps1` gcloud VM commands | HISTORICAL ONLY | Old control-plane script; never execute in this audit/migration path |
| Supervisor mocks/old path fixtures under tests | TEST ONLY | No external VM operation in fresh tests |
| Handoff/runbooks/README cloud commands and `research_v1.toml` GCS placeholder comment | DOCUMENTATION ONLY | Historical/manual references; some broad old date examples need prominent current restrictions |
| Persisted absolute manifest in generic Phase 7 cold-train branch | ACTIVE BLOCKER for migrating that generic route, NOT Phase 7A Lightning | Use runtime locator consistently if that route is separately brought into scope |
| Phase 7A active roots | Runtime/operator dependency, not hardcoded provider | Fail-closed missing env; mount persistence not automatically established |

The scan is an inventory classification, not proof that every arbitrary legacy path string was reviewed in full. Historical paths do not justify deleting historical code or treating current active training as GCP-dependent.

Migration sequence after approval: copy owner-reported GCS objects to **quarantined persistent** Lightning storage without rewriting manifests/raw bytes; inventory against expected source; verify SHA-256 and physical rows/full schema; run Linux suite and preflight; activate read-only only after passing. No GCP access is needed for this review, and none occurred. A 139-object match alone cannot prove completeness/correctness.

## 19. GPU Architecture

Dispatch recognizes `cpu`, `gpu` (OpenCL) and `cuda`; unsupported requested device errors propagate as hard failure, not retry-on-CPU. CPU deterministic/column-wise settings are CPU-only. Device backend participates in model/stage identity. Small CPU smoke works in the suite; mocked requested GPU failure is tested. Actual OpenCL or CUDA failure/success on a real build, device use and L4 resources remain NOT RUN.

Official LightGBM distinguishes OpenCL GPU and CUDA implementations; CUDA requires a supported Linux/NVIDIA build. Its parameter documentation restricts `deterministic` to CPU and `gpu_use_dp` to OpenCL; CUDA uses double precision. Identical seeds do not guarantee bitwise identical models across devices/builds. Histogram/reduction ordering can change best iteration, predictions, calibration, selected thresholds and economic decisions. [Official parameters](https://lightgbm.readthedocs.io/en/latest/Parameters.html), [official GPU/CUDA build guide](https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html).

Float64 input preservation is necessary but not sufficient for CPU/GPU numerical equivalence. The backend helper collects requested/actual labels, driver/device metadata and comparison differences. `smoke_test_backend`'s actual_backend is currently resolved request metadata, not independently extracted proof from a fitted booster. There is no observed silent CPU fallback in the inspected code, but do not use this field alone as device attestation. Record fitted booster parameters/build flags/logs plus device utilization/memory during fit.

**POST-NEW-09:** `compare_cpu_gpu_backends` reports PASS after computing comparisons without checking finiteness/correlation/difference/metric acceptance thresholds. A successful computation is not a passed equivalence gate. It also compares only one small synthetic regression setup, not G0/C0/P0/H0, calibration, threshold stability or canonical feature distributions. Require predeclared tolerance and policy-decision drift criteria, repeated runs, and compatible-data CPU/GPU comparisons before choosing production GPU semantics. No backend was silently changed in this audit.

## 20. Benchmark Safety

Current `--canary` limits folds, **not primary specs**: it is a 48-spec first-fold run. No checked-in exact-one-canonical-spec benchmark selector was found. Neither preparation microbenchmark nor synthetic backend smoke is that selector. **There is no verified existing command to run exactly one canonical real-data model safely. Do not run canary for that purpose.**

Proposed interface only, **NOT IMPLEMENTED / NOT RUN**:

```text
uv run python -m scripts.benchmark_phase7_one_model \
  --config configs/phase7/research_core20_primary_v1.toml \
  --fold-id fold-000-a0e9a4f72689 \
  --spec architecture-G0-A6-15m-raw \
  --benchmark-only --output-root <approved-isolated-persistent-root>
```

Required design: derive the unchanged canonical plan/spec list first; validate exact one match (G0, 15m, raw, A6, canonical balancing/ID settings); prepare/load only that key; refuse canonical checkpoint/model/report roots; write a distinct benchmark identity and manifest `mode=ISOLATED_SINGLE_SPEC_BENCHMARK`, `canonical_fold_complete=false`; assert planned/executed folds=1/specs=1; preserve all 109 features, float64, seeds/purge/embargo/calibration/test boundaries; never alter holdout state or call full fold-completion aggregation. Dry-run selector and negative-selection tests must precede any authorized fit. The placeholder command is a specification, not an executable instruction.

## 21. Observability

Structured events cover cache lookup/hit/miss/build, fold load, matrix preparation elapsed time, compute budget, model start/done, Cal-A, Cal-B and TEST. Progress reports expose spec/fold counters, row counts, coverage, eligibility and economics. Source/config/Gold/backend/paths are inspectable in metadata. RSS snapshots now use psutil.

Limits: reported process peak is the maximum of **sampled** RSS snapshots, not a guaranteed OS lifetime peak; short spikes may be missed. GPU snapshot is inventory, not continuous VRAM/active-device telemetry. Filesystem-specific capacity and long cache-validation/checksum progress need better visibility. Reports/checkpoints should have a distinct durable commit event rather than treating MODEL_DONE or COMPLETE JSON as the final durable boundary. Error messages are useful but operator recovery actions are scattered across large modules and runbooks.

## 22. Failure Recovery

| Failure | Preserved | Lost/restarted | Manual requirement |
|---|---|---|---|
| Studio stop / process kill | Bytes on truly persistent storage; valid earlier checkpoints/cache | Current fit; partial preparation may repeat | Verify mount persistence and stale locks/temp state before resume |
| OOM | Completed immutable data/cache/checkpoints | Current model and transient buffers | Fix memory path/budget; no blind repeated OOM run |
| GPU error | Prepared input and earlier valid work | Current estimator | Diagnose requested build/device; no CPU fallback |
| Disk full in cache temp | Previously valid entries | Current temporary generation | Free only explicitly authorized unreferenced state offline; inspect leftover temp/backup |
| Disk full in report/model/checkpoint | Earlier complete checkpoints | May leave report-only orphan/model without checkpoint | Manual quarantine/reconciliation with proof; repair publication transaction first |
| Cache corruption | Gold/checkpoints and other intact entries | auto can quarantine and rebuild; read_only fails | Investigate corruption; include quarantine in capacity budget |
| Checkpoint corruption | Model/report files may remain | Checkpoint trust lost | Independent content-bound orphan proof needed; current adoption gap blocks blind recovery |
| Network loss during transfer | Verified complete destination files | Partial downloaded file/object | Keep staging separate; validate bytes before activation |
| Network loss after local Gold activation | Local prepared/model work | Normally none for offline training | Ensure runtime does not depend on streaming source storage |

Prepared-cache publication is a genuine improvement over the historical missing checkpoint boundary. It does not checkpoint partially fitted LightGBM estimators. No Studio stop, OOM, ENOSPC or actual GPU-fault injection was performed here.

## 23. Dependencies

Observed local runtime: Python **3.12.14**, NumPy **2.4.6**, PyArrow **24.0.0**, LightGBM **4.7.0**, scikit-learn **1.9.0**, joblib **1.5.3**, psutil **7.2.2**. `pyproject.toml` permits Python >=3.11; uv.lock fixes package resolution but not arbitrary Python patch/build, native compiler flags, CUDA/OpenCL drivers or LightGBM GPU binary construction.

Passing suite/compile demonstrates current Windows API compatibility, including current LightGBM eval_X/eval_y usage. It does not prove Linux installation or GPU binary reproducibility. Use the locked environment on Linux, record interpreter/uv/package/build versions and build recipe/checksum, then run the full gate. Changes to numerical dependencies require reviewed scientific equivalence and serialization/resume validation even when source digest and backend name stay unchanged. No dependency update or new lint toolchain was introduced.

## 24. Security

Tracked HEAD and remediation revisions were screened using filename-only Git searches for common private-key blocks, AWS-style keys, Google API-key shapes, GitHub tokens and service-account `private_key` fields. No matches were returned. A second filename-only scan for credential assignment names in tracked src/scripts/configs/tests also returned no matches. Secret values were never printed. Environment-only secret handling and account-execution prohibition remain intact.

This is not a guarantee of no secret anywhere: pattern scans miss arbitrary passwords, unusual token formats, untracked files and historical objects outside the inspected revisions. No cloud credential/account was accessed to expand the scan. Keep GCS transfer credentials outside repo/docs/logs and exclude signed URLs from run metadata.

Joblib deserialization is a trusted-code boundary. Never load models from an untrusted or writable-by-untrusted-users migration root; orphan checksum proof should occur before `load_model`. Hashes detect accidental changes only relative to trusted anchors. Protect cache/checkpoint roots, reject path escapes/aliases and use read-only Gold after activation. Historical trading scripts remain prohibited.

## 25. Test Quality

Strengths: meaningful negative cases for corruption, wrong source, missing fields, holdout flags/timestamps, feature ordering, protected cleanup, aliases, archive duplicates and INELIGIBLE classification. Tiny independent twice-built datasets/models give deterministic end-to-end fixture evidence. Reference IC and year-pruning comparisons test values, not just successful execution. Windows skips are explicit.

False-confidence risks: source-list mutation tests prove that listed bytes are hashed, not that the list or non-source input keys are complete. The production Gold validator's fixture intentionally omits HTF inputs and still passes. The rebuild test reads via a new auto cache, so does not exercise the runner's same-object rebuild reload. Error-classification mocks disable cache and bypass parts of data/fit orchestration. GPU-unavailable tests mock estimator failure instead of testing a actual CUDA/OpenCL binary. Artifact concurrency coverage is strong for cache publication, not all artifact writers. No real-Gold/large-memory/Linux/device qualification has occurred.

| Requested integration boundary | Current evidence | Missing/required |
|---|---|---|
| Gold → FoldLoader → Cache | Synthetic pieces + this bounded row probe | Full 109-column runner integration, all modes, mutated descriptor identities |
| Cache → ModelRunner | Prepared-input tests; runner integration partial | Same-object rebuild, hit/miss/read_only/corrupt end-to-end without production fit |
| G0 → H0 resume | Existing reuse/restore tests PASS | Content-swapped orphan base rejection |
| Checkpoint → cross-machine | Logical root/metadata fixtures PASS | Linux migration of realistic directory layout and dependency-compatible model predict |
| Runtime → Lightning paths | Env/path/preflight fixtures | Persistent mount/alias/distinct-filesystem scenarios |
| GPU request → actual backend | Mocked hard failure + CPU smoke | Real L4/OpenCL/CUDA, fitted booster/device evidence |
| Gold → corrupt partition | Hash corruption negative test PASS | HTF/helper omission/wrong dtype/Inf and trusted full-schema anchor |
| Cache → corrupt array | Unit negative checks PASS | Semantically wrong row-order with self-consistent metadata/bytes |
| Disk full | Source reasoning/cap test | ENOSPC at each write/rename/fsync boundary on isolated test filesystem |
| Interrupted publication | Atomic protocol inspected | Process-kill/stale-lock/power-loss Linux fault suite |
| One-spec selection | None | Dry-run exactly one canonical spec, isolated roots, no false fold-complete |

## 26. New Errors

The IDs below mean newly established by this audit. They do not all prove introduction specifically in `5c36783`: some are pre-existing or newly exposed weaknesses. No production artifact was demonstrated to have been contaminated.

### Final findings table

| ID | SEVERITY | AREA | FILE / FUNCTION | FINDING / EVIDENCE | SCIENTIFIC IMPACT | OPERATIONAL IMPACT | BLOCKS WHAT / FIX TIMING | RECOMMENDATION |
|---|---|---|---|---|---|---|---|---|
| POST-NEW-01 | HIGH | Cache mode integration | `prepared_cache.py:286 load`; `training.py:1480–1483 run_phase7_training` | rebuild forces every load to miss, including immediate post-publication runner load; bounded synthetic write succeeds then same-object load raises PreparedCacheMissError | No changed values demonstrated; prevents promised path | Expensive preparation publishes, runner aborts before fit | Rebuild-enabled one-model/training; BEFORE_ONE_MODEL | Separate lookup policy from validated post-write opening; runner integration test all modes |
| POST-NEW-02 | HIGH | Memory/resume | `training.py:1067–1160,1483 run_phase7_training` | Preloads all keys, retains all horizon tables/slices and bundles; finite scans touch large mappings | No direct leakage; partial/OOM runs unevaluable | Unbounded fold working set, paging/OOM; completed resume still scans preparation | Real preparation/profile and 48-spec run; BEFORE_ONE_MODEL / BEFORE_48_MODELS | One-key lazy loading, bounded retention, horizon streaming, early checkpoint triage; profile exact float64 path |
| POST-NEW-03 | HIGH | Input identity | `training.py:437 _prepared_cache_identity`, model identity construction; `universe.py:668 select_fold_active_universe` | Membership/cache/model keys omit descriptor fields used for TRAIN clustering; probe retains membership hash but changes cluster mapping | Wrong cluster/base/threshold reuse possible under changed descriptors | Intact but semantically stale cache/checkpoint accepted | Any input-reusing benchmark/training; BEFORE_ONE_MODEL | Hash canonical causal descriptor payload and cluster/tier identities in prepared/model/stage keys |
| POST-NEW-04 | HIGH | Orphan integrity | `models.py:507–542 fit_architecture`, `training.py:542 _validate_complete_orphan_report`, `training.py:1369–1399` | Structural model_identity is not fitted-tree content; orphan accepted then new file digest minted | Wrong estimator can be associated with old calibrated report/TEST identity | Invalid resume, trusted pickle exposure before proof | Orphan adoption / G0-H0 reuse; BEFORE_ONE_MODEL | Persist independent model SHA in report/transaction; verify before load; bind fitted content/schema |
| POST-NEW-05 | HIGH | Gold validation | `gold_validation.py:167–179 validate_gold_manifest`, `229–307 validate_phase7_gold` | Only canonical native 54 audited; supplied A6 derived from supplied manifest; fixture with 54 A6 passes though production expects 109 | HTF input contract may be incomplete or corrupt despite PASS | Migration activation falsely overqualified; later training fails/drops rows | Gold activation and one model; BEFORE_ONE_MODEL | Frozen full 109-column schema/order/types plus helper inputs, HTF Inf/NaN audit and mutation tests |
| POST-NEW-06 | MEDIUM | Durable publication | `training.py:1001–1003 _run_one`; `artifacts.py:44 atomic_json`; `models.py:559 save_model` | COMPLETE report published before model; crash leaves report-only orphan; no shared durable transaction/fsync | Fail-closed missing model, not proven false metric | Lost fit and manual reconciliation; immutable report can obstruct retry | Reliable model crash recovery; BEFORE_ONE_MODEL | Publish model→content-bound report→commit/checkpoint, fsync and recovery states; fault injection |
| POST-NEW-07 | MEDIUM | Capacity/disk full | `preflight.py:113–138 build_preflight_report`; `prepared_cache.py:553 write` | Only artifact filesystem inspected; floors accept NaN/negative; cap checked after entire temp entry written | Usually fails closed, no demonstrated partial hit | ENOSPC before cap; wrong mount capacity PASS | Safe production writes; BEFORE_ONE_MODEL | Positive finite floors; per-filesystem estimates/reserve; reject before construction |
| POST-NEW-08 | MEDIUM | Concurrency/immutability | `artifacts.py:44 atomic_json, atomic_parquet`; `models.py:559 save_model` | Existence check and replace not protected by run lease; scheduled two-thread conflicting JSON writes both succeed | Conflicting run artifacts can overwrite trusted identity/results | Single-writer assumption unenforced; no consistent run generation | Multi-process safety; BEFORE_48_MODELS (prefer before one model) | Exclusive run lease and lock/no-replace publication with comparison under lock |
| POST-NEW-09 | MEDIUM | GPU equivalence/attestation | `backend.py:125 smoke_test_backend`, `167 compare_cpu_gpu_backends` | comparison returns PASS without numerical thresholds; actual_backend is request-derived | Material device prediction/threshold drift can be mislabeled acceptable | False assurance from successful computation | GPU qualification, not offline migration; BEFORE_GPU_TEST | Separate COMPUTED from EQUIVALENT; finite/tolerance/policy criteria; verify fitted backend and device usage |
| POST-NEW-10 | LOW | Source identity policy | `training.py:146 _content_source_identity` | Full normalized bytes include comments; comment-only edit changes science identity | Conservative false rejection, not false acceptance | Avoidable cache/resume invalidation | Requested comment-stability property; POST_PHASE7A | Document conservative rule or approve reviewed identity policy; do not casually weaken hashing |

### Reproductions and qualifications

**POST-NEW-01:** with the existing prepared-cache synthetic fixture, `PreparedDataCache(root,"rebuild").write(identity,fold,prepared)` published a valid entry; `.load(identity,plan)` on that object raised PreparedCacheMissError. The runner performs exactly that write/load pair. Existing test only reloads via `auto`. Probe result: `published_valid_entry=True; post_write_load=PreparedCacheMissError`. No fit required.

**POST-NEW-02:** source path is sufficient to show retained object scope. The arithmetic in sections 14/15 quantifies payload, not actual OOM. No real-Fold memory test was authorized. Fixing one temporary matrix builder does not bound orchestration. Resume completion checks occur too late to avoid initial cache/fold work.

**POST-NEW-03:** synthetic_registry/synthetic_descriptors/fixture_universe_config were used; frozen universe/policy and quote-volume/membership inputs held fixed. TRAIN volatility/beta/correlation/funding variability/trade intensity were changed into two separated groups. Membership hash stayed identical. Cluster map changed from BTC=1, ETH=0, SOL=0, XRP=0 to BTC=0, ETH=0, SOL=1, XRP=1. Since source/config/Gold/registry/universe/key inputs were unchanged, the prepared key lacks that result-relevant distinction. Ordinary immutable pipeline artifacts mitigate some mutations; lower-level training/new-run adoption still lacks complete binding.

**POST-NEW-04:** a synthetic Phase7ModelBundle with unrelated estimator payload but matching structural model_identity was serialized/reloaded, paired with self-consistent calibrator/threshold/frozen report fields and accepted by `_validate_complete_orphan_report`. Result: `unbound_different_estimator_payload_accepted=True`. This tests validator sufficiency, not a production prediction with that deliberately unrelated payload. Valid pre-existing checkpoint SHA verification remains stronger; the vulnerability is missing/invalid-checkpoint orphan adoption.

**POST-NEW-05:** the existing synthetic Gold fixture and fixture count/symbol expectations were passed through the same validator implementation. PASS was returned with 54 A6 columns. Expectations alter dataset/counts, not the missing canonical HTF check. Actual production Gold may be entirely correct; the issue is that this validator cannot prove it.

**POST-NEW-06:** source order is report→model→checkpoint. Kill/disk-full between first two leaves a COMPLETE JSON without model; resume raises FileNotFoundError. This is safe refusal but poor recoverability, not a demonstrated falsely completed checkpoint. Recompute in same roots can conflict with immutable content including execution context. Transaction/fault tests missing.

**POST-NEW-07:** reasoned code proof: `float("nan")` or negative minimum makes `< floor` checks nonblocking; only `system_snapshot(artifact_root ancestor)` is sampled; full temporary entry precedes maximum check. No actual disk-full simulation was performed, and no completed corrupted cache was accepted.

**POST-NEW-08:** isolated two-thread synthetic `atomic_json` probe scheduled both after absence checks and serialized only the final replace calls. Both calls succeeded with different payloads, demonstrating the check/replace race. It used a scheduling wrapper around replace, not a production filesystem stress test. Ordinary nonconflicting single-writer tests remain valid.

**POST-NEW-09:** source returns literal PASS after comparisons, with no acceptance decision. No real device fit performed. Official backend behavior and no CPU retry are positive evidence, but request-derived metadata cannot alone attest device execution. Treat as a gate-design defect, not an observed CPU fallback.

**POST-NEW-10:** bytes are hashed after only CRLF normalization; comments are retained. Path/docs tests pass. This is explicitly conservative policy, rated LOW for the requested property, not a reason to change scientific hashes during an audit.

### Adversarial falsification summary

| Skeptical question | Concrete path / answer |
|---|---|
| Can correct bytes represent wrong preparation? | Yes: omitted causal descriptor identity, POST-NEW-03 |
| Can stale estimator replace a completed result? | Invalid-checkpoint orphan path lacks independent model content binding, POST-NEW-04 |
| Can future data leak through remediation? | No demonstrated new path; cutoff/as-of/purge/freeze guards remain. Full migrated-byte validation still required |
| Could August be used accidentally? | Manual broad legacy date examples/direct bypasses are operator risk; active code rejects post-cutoff rows; August not accessed here |
| Can GPU change scientific semantics despite seed? | Yes numerically; current equivalence PASS does not gate drift, POST-NEW-09 |
| Can migration corrupt Gold but match counts? | Yes; counts/size insufficient. Partition checksums and trusted schema/manifest anchor required |
| Can a crash look successful? | COMPLETE report before model can mislead dashboards, though checkpoint refuses missing model, POST-NEW-06 |
| Can two immutable writers conflict? | Yes TOCTOU publication race, POST-NEW-08 |
| Can paths select wrong storage? | Writable but ephemeral/aliased env roots possible; bytes/roots/persistence must be verified |
| Can run claim GPU while CPU used? | No automatic fallback found; labels alone insufficient actual-device proof |

## 27. Architecture Strengths

TOP 10 STRENGTHS:

1. Strict July research cutoff and locked August holdout, with false/unauthorized flags enforced rather than merely documented.
2. Point-in-time lifecycle universe and retention of delisted HNT avoid retroactive survivorship edits.
3. Actual label-end purge plus explicit embargo protects segment causality more accurately than fixed-row trimming.
4. Distinct Cal-A, Cal-B and frozen TEST access encode selection boundaries in the flow.
5. Immutable Bronze/source lineage/checksums avoid silent market-data repair or fabrication.
6. Prepared Arrow/NumPy durable boundary is appropriately located before expensive model fitting.
7. Sorted path-independent 42-file source identity separates science from host/Git context.
8. Logical-root checkpoint files improve portable, checksum-based resume.
9. Explicit CPU/OpenCL/CUDA dispatch hard-fails requested-device errors instead of retrying CPU.
10. Broad 665-test passing suite includes useful negative corruption/leakage/reference-equivalence tests, plus new progress/RSS visibility.

These strengths are genuine but qualified by the new findings; “atomic,” “durable,” “portable” and “equivalent” should not be read as unbounded guarantees.

## 28. Architecture Weaknesses

TOP 10 WEAKNESSES:

1. Eager full-fold/cache working set defeats much of the intended memory benefit.
2. Rebuild is unit-tested but broken when integrated in the training runner.
3. Causal descriptor/cluster inputs are not fully bound to cache/model identity.
4. Orphan model identity is structural rather than independently tied to fitted estimator bytes.
5. Gold PASS covers native features but not the complete production HTF input contract.
6. Report/model/checkpoint publication lacks a durable transaction and cross-process immutable lease.
7. Disk capacity admission is late, optional and not per-filesystem; retained caches can grow without bound.
8. GPU equivalence/actual-backend proof remains insufficient and unexecuted on the target device.
9. No safe exact-one-canonical-spec benchmark CLI; canary is 48 specs.
10. Large coupled orchestration modules, mocked integration boundaries and historical documentation complexity raise operational burden.

| Timing category | Debt/action |
|---|---|
| NOW | Report confirmed defects; keep on hold; require owner-reviewed fixes/identity/Gold/isolated-selector gates before fits |
| POST-FOLD1 | Profile actual cache bytes/RSS/VRAM, optimize shared payloads/projection, clarify telemetry and recovery playbooks |
| POST-PHASE7A | Review conservative identity invalidation, standardize active/historical adapters/docs, deeper integration fault tests |
| LONG-TERM | Split orchestration responsibility only under approved no-semantic-change contracts; typed execution/state interfaces |

Duplicate listing-age/history features remain potential historical feature debt; do not remove or alter canonical inputs during Phase 7A merely for aesthetics. Modules training/acquisition/progress were not split.

## 29. Maturity Scores

Scores are engineering assessments of the current artifact, not probabilities, financial forecasts or a measured benchmark. Overall **68/100** is the rounded equal-weight mean of the 19 detailed dimensions (68.37); dimensions overlap, so this is a transparent heuristic, not a validated metric.

| Dimension | Score / rating | Why points were lost |
|---|---|---|
| Scientific architecture | 88 — STRONG | Input identity/validation can admit semantically stale work; no real post-remediation gate |
| Data architecture | 85 — STRONG | Full A6/schema anchor incomplete; migrated bytes not independently verified |
| Feature/target architecture | 87 — STRONG | Production HTF contract gap; corner-case old/new values not universally certified |
| Fold/leakage architecture | 90 — STRONG | Strong boundaries; descriptor binding and real-data audit still incomplete |
| Training architecture | 65 — ADEQUATE | Rebuild integration bug, eager state, large orchestrator, missing one-spec selector |
| Prepared-cache architecture | 60 — ADEQUATE | Identity incompleteness, mode integration, duplicate payload, late capacity gate |
| Checkpoint/resume architecture | 62 — ADEQUATE | Orphan content binding and report-first crash recovery gaps |
| Artifact integrity | 68 — ADEQUATE | Single-writer immutable checks, absent full fsync transaction/content attestation |
| Memory architecture | 45 — WEAK | No bounded working set or real 32/64 GiB profile |
| Disk/storage architecture | 50 — WEAK | Optional/late cap and no approved long-run referenced-cache retention policy |
| Cloud portability | 80 — ADEQUATE | Active path neutral; mount persistence and general legacy route unresolved |
| Lightning readiness | 65 — ADEQUATE | No target-host byte/Linux/persistence evidence; training blocked |
| GPU architecture | 68 — ADEQUATE | Useful fail-closed dispatch; no device/build/equivalence qualification |
| Testing | 78 — ADEQUATE | Missing all-mode runner, descriptor swap, orphan tree swap, ENOSPC/Linux/GPU/full-schema coverage |
| Observability | 72 — ADEQUATE | Sampled RSS not true peak; GPU/storage/durable commit visibility incomplete |
| Failure recovery | 56 — WEAK | Report-only orphan, stale lock/temp and missing transaction tests |
| Maintainability | 58 — WEAK | Large coupled modules and harness-heavy tests; frozen/research/operational semantics require careful navigation |
| Security | 72 — ADEQUATE | No scanned secrets; trusted pickle/local manifests and limited historical coverage |
| Operational simplicity | 50 — WEAK | Many env roots, manual gates/cleanup/recovery, no one-model entrypoint |
| OVERALL | **68 — ADEQUATE, NOT TRAINING_READY** | Strong science contracts, materially incomplete execution qualification |

The additional requested dimensions map as follows: causality STRONG (fold/target evidence); reproducibility ADEQUATE (source strong, device/build conditional); storage portability ADEQUATE (logical roots, manual persistent mounts); compute portability ADEQUATE (explicit dispatch, unqualified builds); CPU scalability ADEQUATE (thread arithmetic, weak memory/cgroup governance); GPU readiness WEAK until device gate; memory efficiency WEAK; disk efficiency WEAK; dependency management ADEQUATE (lock yes, native build pin no). None is rated CRITICAL without a confirmed named-invariant violation.

## 30. Pre-Lightning Blockers

Offline quarantine migration is conceptually supported. It is not permission to provision/start/pay for Studio compute.

1. Fresh owner cost/deadline/storage contract; confirm destination is persistent and generation-isolated, and historical GCP workers/watchdogs are not used.
2. Preserve Gold/source manifests and transfer inventories; copy into quarantine, keep source unchanged; establish trusted hashes rather than accepting counts/rounded sizes as integrity proof.
3. Require full physical-byte/full-A6 validation and Linux verification before **activation**; current native-only validator needs an owner-authorized correction for activation certification.

These are operational preconditions, not three invented migration code defects. POST-NEW-01–04 do not prevent copying bytes into quarantine, but do prevent certifying training after that copy.

## 31. Pre-GPU Blockers

1. Owner authorization/fresh cost limit, supported Linux build recipe and pinned LightGBM binary/driver/device evidence.
2. One worker initially; observe fitted booster backend/device utilization/VRAM and prove unavailable gpu/cuda hard-fail without CPU retry.
3. Fix/clarify POST-NEW-09 before treating comparison PASS as equivalence; approve tolerances and repeated-run/policy-drift protocol.

Synthetic device smoke tooling is available. No production data or canonical training should be used merely to establish a build can fit 512 synthetic rows.

## 32. Pre-One-Model Blockers

1. Owner-authorized fixes and tests for rebuild/complete input identity/orphan estimator binding/full 109-column Gold contract and durable artifact publication (POST-NEW-01/03/04/05/06).
2. Implement/test an isolated exact-one-canonical-spec selector, lazy one-key preparation, and finite per-filesystem capacity/memory admission (POST-NEW-02/07); do not substitute canary.
3. Fresh full Linux suite, trusted real Gold byte/schema validation, compatible dependency/build proof and an explicit benchmark cost/deadline/stop contract.

There is presently no safe executable one-model command being recommended. All proposed code changes require the owner's next authorization; this audit implemented none.

## 33. Pre-48-Model Blockers

1. Pass all one-model gates and document benchmark correctness/recovery, without contaminating canonical fold state.
2. Bound retained cache/fold state, profile real cold/hit/resume RSS/VRAM/time/bytes; choose CPU/GPU workers and storage from measurement, not assumed 32/64 GiB sufficiency.
3. Run-level exclusive lease/no-overwrite publication (POST-NEW-08), filesystem reserve/retention policy, failure-injection/recovery gate and fresh 48-spec budget/deadline/stop approval.

No conclusion here authorizes all 16 folds. Their persistent-cache retention/cost contract must be separately approved.

## 34. Post-Fold1 Improvements

1. Use measured row/feature/cache payload distributions to refine storage/RAM estimates and retention plans.
2. Share scientifically identical immutable feature payloads across horizon/target keys under explicit shape/key equivalence checks.
3. Add safe column/symbol/row-group pruning with reference-value/order tests.
4. Add continuous high-water RSS/VRAM/filesystem telemetry and explicit durable-checkpoint events.
5. Consolidate operator recovery/cleanup generation inventory and cost/performance scorecards without interpreting incomplete runs as poor model performance.

## 35. Long-Term Refactors

1. Separate preparation, execution, publication and recovery state machines from the large training orchestrator under no-semantic-change tests.
2. Split acquisition protocol/validation/reconciliation responsibilities and progress views into typed boundaries only after owner approval and freeze-aware verification.
3. Standardize historical-vs-active adapters/docs and artifact-generation schemas; explicit trusted numerical-build compatibility policy.

No aesthetic refactor, source split, new cloud service, execution/risk engine, sentiment family or live-trading integration belongs in this audit.

## 36. Final Readiness

```text
CRYPTO 2.0 — POST-REMEDIATION ARCHITECTURE SCORECARD

Scientific architecture:          88/100 — STRONG
Data architecture:                85/100 — STRONG
Feature/target architecture:      87/100 — STRONG
Fold/leakage architecture:        90/100 — STRONG
Training architecture:            65/100 — ADEQUATE
Prepared-cache architecture:      60/100 — ADEQUATE
Checkpoint/resume architecture:   62/100 — ADEQUATE
Artifact integrity:               68/100 — ADEQUATE
Memory architecture:              45/100 — WEAK
Disk/storage architecture:        50/100 — WEAK
Cloud portability:                80/100 — ADEQUATE
Lightning readiness:              65/100 — ADEQUATE
GPU architecture:                 68/100 — ADEQUATE
Testing:                          78/100 — ADEQUATE
Observability:                    72/100 — ADEQUATE
Failure recovery:                 56/100 — WEAK
Maintainability:                  58/100 — WEAK
Security:                         72/100 — ADEQUATE
Operational simplicity:           50/100 — WEAK
OVERALL:                          68/100

NEW CRITICAL ERRORS:               0
NEW HIGH ERRORS:                   5
NEW MEDIUM ERRORS:                 4
NEW LOW ERRORS:                    1
SCIENTIFIC REGRESSION:             NO (none observed; not exhaustive proof)
AUGUST:                           LOCKED_UNUSED
FULL TEST SUITE:                   665 passed / 0 failed / 5 skipped / 0 warnings; 178.53s
RUFF:                             PASS
FORMAT:                           PASS (221 files)
DEPENDENCY LOCK / COMPILE:         PASS / PASS
GOLD BYTE VALIDATION:              NOT RUN (production migrated dataset)
LINUX VALIDATION:                  NOT RUN
GPU SMOKE TEST:                    NOT RUN (actual GPU)
CPU/GPU EQUIVALENCE:               NOT RUN

READY FOR LIGHTNING MIGRATION:     YES — offline quarantine copy only, after owner/storage contract
READY FOR LINUX VERIFICATION:      YES — verification workflow, not training; after owner host authorization
READY FOR GPU SMOKE TEST:          YES — isolated synthetic diagnostic only, after owner/build authorization
READY FOR ONE-MODEL BENCHMARK:      NO
READY FOR 48-MODEL FOLD 1:          NO
TRAINING_READY:                    NO
```

YES denotes an available safe type of next diagnostic work with stated preconditions, not that a cloud environment exists, a budget is approved, or any target-host gate has passed. No code fix was made, so every confirmed finding remains open.

**NEXT SAFE ACTION:** owner reviews this report and selects a narrowly scoped remediation authorization. Resolve the identity/content/schema/rebuild defects and establish bounded isolated preparation/benchmark design locally; rerun full gates. Then, only with a fresh cost/deadline contract, migrate into quarantine and verify real Gold bytes/full schema on Linux before any model benchmark. Existing valid discovery/acquisition/60 candle and Gold checkpoints must be validated/reused, not recomputed by default.

**STOP:** audit delivered. No fixes, fits, Fold 1, August access, cloud starts, Phase 8, commit or push follow from this document.
