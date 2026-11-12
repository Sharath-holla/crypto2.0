# Crypto 2.0 — deep debugging and software evaluation

Subsequent scientific correction:
[future-gap membership look-ahead fix, 2026-10-23](PHASE7A_MEMBERSHIP_LOOKAHEAD_FIX_2026_10_23.md).
Results and identities below remain the historical October 22 snapshot.

Date: 2026-10-22. Scope: standalone Phase 7/7A training engine and its safety checks.
This report follows [the earlier remediation](PHASE7A_STANDALONE_TRAINING_REMEDIATION_2026_10_22.md).
That earlier test result was valid for its source snapshot, but did not cover the
additional failure cases reproduced here. This report does not claim every possible
error is eliminated, or substitute for a real Linux/data/resource qualification.

## Executive result

Further adversarial tests reproduced defects in prepared-cache consistency,
publication, read-only validation, preflight ordering and failure diagnostics.
The affected code was rewritten locally, rather than rebuilding the project or
changing its scientific experiment. Final local verification passed: **854 tests
passed, 5 Linux-only skips, zero failures**, plus the static checks below.

The project remains **ON HOLD**. No real training, acquisition, Gold scanning or
rebuilding, production prepared-cache preparation, cloud lifecycle operation,
account access or holdout evaluation was performed. All added cache objects and
estimator fixtures are small synthetic unit-test objects, not market history.

## Confirmed defects, root causes and corrections

| ID / priority | Reproduction and consequence | Root cause | Implemented correction |
| --- | --- | --- | --- |
| D01 / P1 | Change one cached feature, target or symbol array, update its checksum and completion marker: the old loader accepted disagreement with its own Arrow rows | Checksums, dimensions and finiteness were checked, but values/row correspondence were not | Compare ordered features, targets and symbols against stored tables, including Calibration-A symbol order; reject disagreement and mismatched fold-context identity |
| D02 / P1 | Supply an incorrect, correctly shaped target array to a rebuild: the old writer could replace the previously valid entry | Content was not semantically validated before moving the prior entry | Validate the completed temporary bundle before publication or touching the prior entry; an invalid candidate leaves the old entry intact |
| D03 / P2 | Failed mapped-array validation raised Windows file-lock errors during temporary cleanup, masking the real validation failure | NumPy memory maps remained open through exception tracebacks | Clear failed loader frame references before closing mapped files with an exit stack; successful returned memmaps remain usable |
| D04 / P2 | `create_outputs=False` still opened temporary write probes in existing output directories | Directory creation and write probing were not independently gated | Read-only inspection performs access checks but no mkdir/write probe; its report explicitly says writability was not proven and does not claim training readiness |
| D05 / P1 | Unsafe roots or invalid RAM values could be followed by Gold inspection and backend smoke fitting | Preflight ordered expensive actions before cheap admission checks | Contract, path and capacity checks precede Gold; any earlier blocker prevents subsequent inspection/fitting; Gold/report rejection prevents backend fit |
| D06 / P2 | Invalid floor strings, unavailable filesystems or list/null JSON evidence produced exceptions instead of useful failure reports | Several external-input and filesystem paths were not normalized into structured errors | Name invalid settings in `blocking_errors`; catch per-filesystem failures; reject malformed evidence containers; retain `FAIL`/`NOT_READY` |
| D07 / P2 | A fit exception left the per-estimator JSONL at `FIT_STARTED` | Only successful fitting emitted a terminal observer event | Emit `FIT_FAILED` with error type and last observed round, without copying exception text/data; retain the original exception if logging also fails |

These are demonstrated software failure modes, **not evidence that the real remote
cache is corrupt or that any historical trained model used wrong labels**. The
remote cache was not accessible in this session. A self-consistent rewritten hash
is deliberately adversarial: a checksum proves bytes, not relationships between
redundant representations. Comparing both representations is an additional guard,
not independent proof of equivalence to original Gold.

## What was rewritten and why

- `src/crypto_ai/phase7/preflight.py`: staged admission and structured error reporting.
  Blocking errors stop later Gold/cache inspection and backend fitting. The fit is
  still a tiny synthetic smoke test when explicitly requested and prerequisites pass.
- `src/crypto_ai/phase7/prepared_cache.py`: bounded matrix/table validation,
  temporary-entry validation before replacement, and failed-load mmap cleanup.
  Alignment compares one column and up to 65,536 rows at a time; it does not allocate
  another full feature matrix. The previous full-matrix finite-mask allocation was
  replaced by batch checks. Real workload overhead still requires profiling.
- `src/crypto_ai/phase7/runtime.py`: no-write semantics for no-create inspection.
- `src/crypto_ai/phase7/training_metrics.py` and `models.py`: sanitized failed-fit
  events, preserving normal fitting, exception propagation and metric ownership.
- `tests/phase7/test_deep_debug_regressions.py`: adversarial regression coverage.

The earlier changes remain: Cal-B uses the same non-overlapping per-symbol policy
as OOS; threshold policy is versioned; dependency identity participates in resume
and cache compatibility; one-fold execution bounds descriptor construction; direct
CLI training uses preflight; invalid thresholds/timestamps fail closed; and live
TRAIN/Validation metrics are separate from frozen TEST evaluation.

## Training visibility and troubleshooting

Live fit logs display native L2 loss, MAE, RMSE and directional accuracy. The default
period is 25 rounds; `PHASE7_METRICS_EVERY=1` requests every round. Paths are:

```text
PHASE7_LOG_ROOT/<run_identity>/<fold_id>/<spec_id>/fit-<attempt-id>.jsonl
```

Lifecycle: `FIT_STARTED` → periodic `FIT_METRICS` → `FIT_FINISHED` or `FIT_FAILED`.
The final success record distinguishes best iteration from the last executed round.
Failure records identify the exception class without copying raw exception messages.
The caller still receives the original traceback for debugging. If the logger also
fails (for example, disk full), the original exception is retained with a note.

For this regression experiment, “accuracy” means directional accuracy. Error/loss
units follow the selected raw or normalized target. The diagnostic summaries are
unweighted; native fit L2 retains training weights. Validation L2 remains the first
and sole early-stopping selection metric. TEST is not fed into fitting diagnostics.

When reporting an unresolved error, provide the command, traceback, operating system,
Python/package versions, expected versus observed behavior and relevant log event.
Do not include credentials or upload market data/holdout rows to debug a software error.
External errors without such evidence are **not yet reproduced**, not silently marked fixed.

## Evaluation and evidence

The evaluation has two different meanings:

1. **Software correctness:** targeted tests, complete local suite, lint/format,
   compilation, lock consistency, source/config identities and diff review.
2. **Scientific/model quality:** real-data OOS scores, economics, Fold-1 runtime,
   memory and cache/Gold equivalence. These are **NOT EVALUATED here**. The historical
   0/48 completed Fold-1 specifications cannot be interpreted as bad performance.

Red/green evidence: the first added failure suite reproduced 12 product failures;
its thirteenth case initially had a read-only fixture mutation mistake, which was
corrected and independently reproduced the invalid-rebuild acceptance. Three
additional diagnostic tests reproduced malformed JSON and missing fit-failure logs.
The first implementation gate then had 129 passes and two failures: missing setting
name in one diagnostic and mmap cleanup masking a validation error. Both were fixed;
the next gate passed 131 tests, followed by 134 after diagnostic additions.

Verification of the corrected implementation:

| Check | Result |
| --- | --- |
| Preceding focused cache/preflight/training/hardening gate | 136 passed in 38.34 s |
| Final adversarial module, including traceback-lifetime check | 19 passed in 10.68 s |
| Complete final Windows suite | 854 passed, 5 skipped, zero failures/errors, one non-fatal joblib warning; 465.55 s |
| Ruff lint and format | PASS; 251 files checked |
| Compilation, lockfile consistency, diff whitespace | PASS; offline lock check resolved 31 packages without changing the lock |
| Real Linux, GPU, production cache and model-quality evaluation | NOT RUN / NOT QUALIFIED |

The first complete follow-up run was intentionally interrupted during final review
to add the traceback-reference cleanup and its regression. It is **not** counted as
a completed passing run. The final complete gate starts afresh on the final source.
Durable result:
[final full-suite JUnit XML](../local_artifacts/phase7/verification/deep-debug-full-final-v2-20261022.xml).
Focused evidence:
[136-case gate](../local_artifacts/phase7/verification/deep-debug-targeted-release-20261022.xml),
[19-case final adversarial module](../local_artifacts/phase7/verification/deep-debug-final-lifecycle-20261022.xml).

Commands used from the repository (PowerShell; the explicit existing interpreter
avoids Windows App Execution Alias failures):

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q --tb=short -p no:cacheprovider --basetemp local_artifacts/deep-debug-full-final-v2-20261022 --junitxml local_artifacts/phase7/verification/deep-debug-full-final-v2-20261022.xml
.\.venv\Scripts\ruff.exe check --no-cache src tests integration scripts
.\.venv\Scripts\ruff.exe format --check --no-cache src tests integration scripts
.\.venv\Scripts\python.exe -B -m compileall -q src/crypto_ai scripts tests
uv lock --check --offline
git diff --check
```

Use a fresh, dedicated `--basetemp` name for another run. Test-generated files stay
under `local_artifacts`; these commands do not grant real training/cloud authority.

Non-failing Windows messages must not be confused with verified code defects:
five Bash log-rotation cases are skipped here and still require Linux; joblib may
warn that physical-core discovery is unavailable and fall back to logical CPUs;
Git's LF-to-CRLF notices are informational, while `git diff --check` reports no
whitespace errors. A Windows App Execution Alias can make bare `python` unavailable;
the commands above use the existing working `.venv` interpreter without changing
system settings or installing dependencies.

Source/environment identity of this final uncommitted snapshot:

- Scientific source:
  `eb60b8d74514e62c9df13c8b34b470d23fd9935b57cbe6444d36007e3a8cf8dc`.
- Execution source:
  `0ca737d09c5c3b1b80a78b642985b8edf7dd57277a0974b86bbbdcdeff8efca9`.
- Dependency compatibility:
  `11c7722c2d289762066135d20fd4f10d4f9e4a7ab402342bfde38161c38f61ba`.
- Python 3.12.14; NumPy 2.4.6; PyArrow 24.0.0; LightGBM 4.7.0;
  scikit-learn 1.9.0; joblib 1.5.3; Pydantic 2.13.4.

## Preservation and compatibility

Work continues uncommitted on `integration/aiventra-crypto-os`, HEAD
`b8a574d62213bddab0eca356bdb903ebd4c2973f`. No reset, commit, push or new checkout.
Owner files and unrelated untracked evidence are preserved.

Phases 1–6, canonical configurations, original model/report artifacts, Core20/HNT,
109 A6 inputs, 16 folds, 48 primary specifications, targets, latency, actual-label
purge, 120-minute embargo and calibration ownership remain unchanged. July stays
excluded; August stays `LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.
The final local configuration inspection confirmed hash
`93f987736b1a79d26b773957`, 16 folds, 109 features, 48 primary specifications,
July 1 exclusive research cutoff, and the unchanged locked/false holdout flags.

Aiventra's runtime/adapter production code and source approval guard remain unchanged.
The amended engine is not approved for launch through that integration. Earlier
synthetic adapter fixture isolation remains test-only, with real rejection tests.

Source identity changes conservatively invalidate incompatible prepared/model resume.
Do not edit completion markers, hashes, identities or manifests to force a real cache
through the new validator. Existing remote compatibility is UNKNOWN. Preserve original
evidence and use read-only validation; no automatic rebuild is authorized. Reuse valid
discovery, acquisition, candle and Gold checkpoints after their normal verification.

## Remaining release requirements

- Run the complete Linux software gate; Windows does not validate Bash, process/signal
  behavior or production filesystem semantics.
- Independently validate the original remote checkpoints and Gold. Inventory caches
  before deciding whether any separately authorized preparation is necessary.
- Prove real cached/uncached scientific equivalence and measure the added consistency
  check's runtime, I/O and memory on the real host. GPU equivalence remains unverified.
- Completed-spec resume still loads/validates prepared fold data before per-spec skips;
  this documented performance limitation has not been redesigned in this pass.
- Obtain a fresh owner-approved cost/deadline contract before any real Fold 1. No local
  test result or preflight label authorizes training, paper trading or live execution.
