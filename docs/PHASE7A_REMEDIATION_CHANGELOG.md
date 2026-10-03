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
