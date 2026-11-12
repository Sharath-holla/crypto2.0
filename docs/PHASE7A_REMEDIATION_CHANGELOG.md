# Phase 7A Remediation Changelog

Completed locally on 2026-10-03. Frozen baseline `28d3098`; pre-remediation HEAD `c856996`.
This log includes existing remediation work integrated during continuation. Details and measured
limits are in [the remediation report](PHASE7A_REMEDIATION_2026_10_02.md).
Verified code/tests: local commit `5c36783`; documentation committed separately. No push performed.

| ID | Original error | Fix / decision | Files | Verification | Status |
| --- | --- | --- | --- | --- | --- |
| ERR-01 | Historical byte freeze compared with approved current remediation | Preserve v1.9 JSON; verify exact historical Git bytes; active v2 content identity for current runs | baseline freeze/noninterference tests; training.py | Historical contract, source identity and methodology tests | FIXED |
| ERR-02 | G0 INELIGIBLE resume expected missing model | Distinguish COMPLETE/INELIGIBLE/invalid states; valid G0 reuse; missing/corrupt models fail; H0 explicitly ineligible when base unavailable | training.py | Training error/optimization, integration, runtime trust tests | FIXED |
| ERR-03 | Execution fields invalidated science checkpoints | Scientific compatibility excludes legacy Git/version/cache/execution evidence; backend semantics remain strict; stage-level shortcut guarded | artifacts.py, training.py, both pipeline runners | Legacy execution, backend mismatch, top-level stage tests | FIXED |
| ERR-04 | New/transitive training code missing from source identity | Explicit 42-file dependency set including acquisition/quality/schema descriptor dependencies, sorted/path-independent hashes, LF normalization; required modules tracked | training.py; new backend/cache/validator modules | Critical-module mutation, missing-source, CRLF and order/location tests | FIXED |
| ERR-05 | read_only miss entered rebuild path | Dedicated ReadOnlyError; miss no longer FileNotFoundError; all modes explicit; default auto | prepared_cache.py, runtime.py, training.py | Mode/missing/corrupt/identity/cache publication tests | FIXED |
| ERR-06 | Backup/byte validation status incomplete | Owner's manual GCP→GCS basic backup recorded: 139 files/objects, ~9.1 GB/9.01 GiB; migrated byte validation still pending | Report and Lightning runbook; Gold validator CLI | Synthetic validator only; no GCP connection | PARTIALLY_FIXED |
| ERR-07 | Ruff import ordering | Correct actual import violations | runner.py, new wrapper/tests | Ruff check PASS | FIXED |
| ERR-08 | Pipeline formatting | Format only actual violations in remediation files | run_phase7a_pipeline.py and listed remediation files | Ruff format check PASS | FIXED |
| ERR-09 | Deprecated LightGBM fit API in new utilities | Inspect installed 4.7 wrapper and official API; retain production eval_X/eval_y; update smoke/comparison; declare >=4.7 | backend.py, pyproject.toml, uv.lock | CPU smoke and production-model synthetic tests; no deprecation warnings | FIXED |
| ERR-10 | Windows directory os.replace portability | Complete temp build, marker/fsync on Linux, root-wide lock, rename/move, winner validation and rebuild rollback | prepared_cache.py | Windows concurrent publication/roundtrip/corruption/rebuild tests | FIXED |
| ERR-11 | Validator independently hardcoded interval | Import canonical FIVE_MINUTES_US from targets | gold_validation.py | Gold entry/label timing validation | FIXED |
| ERR-12 | Runtime configuration AssertionError | Clear ValueError for invalid/oversubscribed user budgets | runtime.py | Compute budget tests | FIXED |
| ERR-13 | Strict G0/path identity prevented portable resume | Science comparison, logical/relative references, explicit legacy-root mapping for checkpoints and immutable Silver/segment/source inputs; verify migrated file hashes | artifacts.py, runtime.py, acquisition.py, training.py, runners | Relocation, legacy remapping/root escape, Gold/fold/source/backend rejection | FIXED |
| ERR-14 | Linux/Bash tests failed on Windows | Five tests use win32 skip only; Linux assertions unchanged | test_log_rotation.py | Five expected Windows skips; Linux rerun pending | FIXED |
| ERR-15 | psutil undeclared or unavailable silently | Required dependency and locked 7.2.2; actual RAM/RSS reporting | pyproject.toml, uv.lock, runtime.py | Runtime/preflight/full suite | FIXED |
| ERR-16 | listing_age_days/history_length_days redundancy | KNOWN_REDUNDANT_FEATURE retained in frozen model inputs | Report | Native schema/spec contracts unchanged | DOCUMENTED_ONLY |
| ERR-17 | Discovery checkpoint errors silently swallowed | Log optional candidate path/reason; unexpected exceptions propagate; required reuse fails when valid evidence absent | discovery_checkpoint.py | Discovery checkpoint/quality suites | FIXED |
| ERR-18 | Unnecessary column_stack and one-hot copies | Preallocate ordered float64 matrix/final encoding; memmap cache; sampled RAM events; small exact-value benchmark | models.py, runtime.py, training.py, preparation utility | Exact values/order/encoding tests; synthetic timing/RSS observations | PARTIALLY_FIXED |
| ERR-19 | Possible symbol partition I/O pruning | Defer; shared G0/fold context requires full active universe; year pruning already retained/tested | No new subset pruning | Year/January-1 half-open equivalence tests; no symbol I/O benchmark claimed | DEFERRED |

ERR-18 is structurally improved, but production RAM/speed improvement is not measured.
ERR-06 is not a missing-backup claim: BASIC GCS BACKUP COMPLETE; BYTE VALIDATION PENDING.

Necessary architecture work: A3 identity separation, A4 integrated/tracked modules, A6 Lightning
entrypoint, A8 runtime overrides, and A5 capacity/reporting/explicit offline cleanup. No automatic
LRU. A1/A2/A7 large module splits are POST_PHASE7A_REFACTOR.

Verification before: 620 passed / 8 failed / 0 skipped / 3 warnings.
Verification after: 665 passed / 0 failed / 5 Windows-only skips / 0 warnings in 150.74 seconds.
Ruff PASS; format PASS (221 files); dependency lock check PASS; August LOCKED_UNUSED.
GPU smoke and migrated Gold byte validation NOT RUN. TRAINING_READY=NO.

## Focused pre-Lightning finalization — 2026-10-03

Starting HEAD `2dcf12bb2b7bdc8ec089d3248bbc157a9a9ef2a8`. Detailed investigation, all 58
generated rows, current identities, tests and readiness are in
[PHASE7A_PRE_LIGHTNING_FINALIZATION.md](PHASE7A_PRE_LIGHTNING_FINALIZATION.md).
No config/scientific methodology expansion: original/current canonical primary count is 48;
the quoted 40 claim was stale. Historical v1.9 bytes, July/August locks and existing artifacts
are preserved. Current scientific source identity includes 44 files, operational identity 10.

The IDs below preserve the latest fresh audit's numbering (not the superseded draft numbering).
The five HIGH findings were confirmed in starting code; four fixed, memory/resume partly fixed.

| ID / finding | Evidence | Fix | Tests | Status |
| --- | --- | --- | --- | --- |
| POST-NEW-01 HIGH rebuild integration | Post-write rebuild lookup forced miss | Explicit validated open_published after write | Same-object float64 roundtrip; runner fit sentinel | RESOLVED |
| POST-NEW-02 HIGH eager memory/resume | All horizons/cache keys resident | Lazy one-horizon/key retention; release prior payload/models | Weakref previous-horizon release; isolated runner | UNRESOLVED / PARTIALLY_FIXED: production RSS/admission and early completion triage pending |
| POST-NEW-03 HIGH descriptor identity | Numerical cluster/tier inputs not bound | Hash causal descriptor payload and fold context into cache/checkpoint/model | Descriptor change/order/future exclusion; existing identity suite | RESOLVED |
| POST-NEW-04 HIGH orphan content binding | Filename/structural identity insufficient | Pre-load model SHA + report digest + expected science; serialized input identity | Content swap/report mismatch; actual tiny estimator roundtrip | RESOLVED |
| POST-NEW-05 HIGH full Gold contract | Native-only 54-column PASS | Producer-derived 109 features/130 physical types/order; reject stale preflight evidence | Seven partition mutations; old native-only PASS | RESOLVED |
| POST-NEW-06 MEDIUM publication durability | COMPLETE report before model; weak fsync | Model→bound report→checkpoint; file/POSIX-directory fsync | Injected model/report/replace failure; fsync ordering | UNRESOLVED / PARTIALLY_FIXED: model-only recovery/multi-file Linux crash gate pending |
| POST-NEW-07 MEDIUM capacity admission | Full build before cap; single mount floor | Preconstruction estimate + exact final bytes without double count; finite per-output floors | Below/equal/above cap; protected/temp behavior; runtime trust | PARTIALLY_FIXED: no reserved capacity/production ENOSPC qualification |
| POST-NEW-08 MEDIUM cross-process race | No model/report run lease | No conflicting process execution authorized; retain blocker | Cache locks do not certify model/report concurrency | UNRESOLVED |
| POST-NEW-09 MEDIUM GPU equivalence | Computation PASS has no acceptance tolerances | Retain explicit gate; no unapproved device/scientific change | GPU benchmark NOT RUN | UNRESOLVED |
| POST-NEW-10 LOW comment hash policy | Full normalized source bytes include comments | Preserve conservative content identity | Existing source identity tests | DOCUMENTED / DEFERRED |

Additional requested items: exact canonical ID/combination/deferred-count tests; production-package
Lightning launcher/startup tests; plan-only exact-one canonical selector with BENCHMARK_ONLY
root/checkpoint/completion isolation; protected historical/current identity tests. Cache cap's
old final `current` already included temporary bytes: undercount allegation not reproduced;
admission timing was the actual defect. No automatic LRU introduced.

Final full verification: 696 passed / 0 failed / 5 Windows-only skips / 0 warnings in 335.98 seconds.
Ruff/format (225 files), lock/compile/diff checks PASS.
Local code/tests commit: `0cf62a67d55b9ff51e3b34f8d2726c4e9beb58b0`; documentation committed separately. No push.
No real Gold validation, migration, production fit, real
one-model benchmark or GPU benchmark. Working set PARTIALLY_BOUNDED. TRAINING_READY=NO.

## Final local pre-Lightning hardening — 2026-10-03

Started at `4ef91d53f2eb6b83157394078452cf4c1a85a5fe`; safe new branch requested:
`phase7a-pre-lightning-hardening-20261003`. Full evidence and future-only commands:
[PHASE7A_PRE_LIGHTNING_HARDENING.md](PHASE7A_PRE_LIGHTNING_HARDENING.md).
Earlier entries above are historical evidence, not current unresolved statuses.

| ID | Local changes/tests | Current status |
| --- | --- | --- |
| POST-NEW-02 | Exact no-copy all-finite Arrow/contiguous float64 selection; one-horizon/key release retained; optional RAM admission and structured stage telemetry | PARTIAL: early completion triage still follows context load; real RSS profile NOT RUN |
| POST-NEW-06 | Model→receipt→bound report→checkpoint; read-only states; model-only refusal; lease-protected deterministic checkpoint reconciliation; killed-process/truncation/hash-order and synthetic ENOSPC tests | LOCAL CODE/TESTS RESOLVED; Linux filesystem crash qualification NOT RUN |
| POST-NEW-07 | Configurable finite RAM/disk floors; artifact/cache/checkpoint/model/report/temp roots; preconstruction cache admission; fail-closed ENOSPC, protected cleanup dry-run | LOCAL CODE/TESTS RESOLVED; no reservation guarantee; real disk profile NOT RUN |
| POST-NEW-08 | Persistent guard inode + OS lock/owner metadata; second writer rejection; conservative hash-bound stale recovery; separate benchmark lease; local subprocess kill tests | LOCAL CODE/TESTS RESOLVED; Linux target-filesystem cross-process qualification NOT RUN |
| POST-NEW-09 | Explicit complete/partial/no-tolerance comparison semantics; prediction-only PASS scope; native fitted-backend + independent live PID/GPU UUID/VRAM evidence; no CPU retry | LOCAL CODE/TESTS RESOLVED; actual GPU smoke, numerical and policy equivalence NOT RUN |

Historical v1.9 freeze unchanged; canonical config/science, 48+6+4 specs, 109 features/130 fields,
Core20/HNT, July-unused/August LOCKED_UNUSED retained. New scientific manifest has 46 files;
execution-only manifest 15. All existing discovery/acquisition/candle/Gold artifacts preserved.
No large module refactor, real Gold access, migration, cloud start, GPU/real-model benchmark,
production Fold 1, 48-spec run or Phase 8. TRAINING_READY=NO.

Final verification and selective commit/push evidence: see the hardening report and the final
owner-facing Git report. Earlier full verification during integration: 747 passed, 5 Windows
Bash skips, 0 failures/warnings. Fresh final gate: **751 passed / 0 failed / 5 Windows-only
Bash skips / 0 warnings in 190.52 seconds**. Final focused hardening + tiny integration:
58 passed. Ruff/format (233 files), lock, compile and diff checks PASS. Actual external
Linux/Gold/resource/GPU/real-benchmark gates remain NOT RUN.
