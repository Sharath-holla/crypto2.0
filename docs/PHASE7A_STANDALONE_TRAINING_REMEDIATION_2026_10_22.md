# Standalone training remediation — 2026-10-22

Follow-up: [deep debugging and evaluation](PHASE7A_DEEP_DEBUG_AND_EVALUATION_2026_10_22.md)
records later cache/preflight/failure-path corrections. The results and identities
below describe this earlier snapshot, not the later source.

## Status and scope

Local engineering amendments on `integration/aiventra-crypto-os`, based on HEAD
`b8a574d62213bddab0eca356bdb903ebd4c2973f` (uncommitted). This is not a training
authorization, a replacement scientific baseline approval, or a profitability claim.
The project remains ON HOLD. No real-data training, acquisition, Gold scan/rebuild,
prepared-cache build, holdout evaluation, cloud lifecycle action, or account access
was performed. Tiny synthetic CPU estimator fits are unit tests only.

Phases 1–6, their artifacts, the canonical configurations, Core20 (including HNT),
109-column A6 schema, 16 folds, 48 primary specifications, label timing, actual-label
purge and 120-minute embargo remain unchanged. July remains excluded; August remains
`LOCKED_UNUSED`, `used=false`, `evaluation_authorized=false`.

## Confirmed defects and changes

| Issue | Correction | Evidence / limitation |
| --- | --- | --- |
| Cal-B counted overlapping signal rows as trades while OOS used a non-overlapping policy | Shared chronological per-symbol policy for selection and OOS, using actual entry/label-end times | Dense 36-signal fixture produces only 3 executable trades per symbol and cannot satisfy the 30-trade gate |
| Fitting was silent | Training-scoped terminal JSON plus persistent per-estimator JSONL: native L2 loss, MAE, RMSE and directional accuracy for TRAIN and Validation | First round, periodic rounds and final best/last-round information; no TEST metric during fitting |
| Dependency changes did not invalidate scientific resume/cache identities | Bind exact Python and installed numerical/model package versions plus LF-normalized `pyproject.toml` / `uv.lock` SHA-256 | Dependency and lock mutation tests; portable identity excludes host/RAM/path observations |
| One-spec/canary startup computed descriptors for all folds | Select and validate canonical fold IDs before Silver reads | One-fold descriptor output equals the corresponding full-run output; one read instead of sixteen |
| Direct Phase 7A CLI could bypass the Lightning-only preflight | Canonical train CLI owns one shared preflight; Lightning delegates to it | Startup test refuses work before stage execution; avoids duplicate backend smoke fitting |
| Training could proceed with no explicit RAM floor or with implicit cache preparation | Cheap startup guard requires a positive RAM floor, read-only cache and valid metric period | Fails before Gold/checkpoint work; a configured floor is not proof of empirical memory sufficiency |
| Output roots could overlap immutable inputs | Reject ancestor/descendant overlap between writable roots and Gold/data before directory creation or write probes | Sentinel tests confirm rejection leaves input bytes unchanged |
| Final fit logs could claim early stopping after every requested round ran | Use observed callback rounds, not LightGBM's rolled-back booster iteration count | Separate best-iteration and last-executed-round fields; regression cases cover both end conditions |
| Invalid thresholds such as NaN could bypass hurdle comparisons | Validate finite/nonnegative values, known policy identity and Cal-B ownership at construction and use | Also revalidate mutable dictionary contents; malformed or stale policies fail closed |
| Missing trade timestamps could evade causal/non-overlap comparisons | Reject null feature, entry and label-end timestamps | Regression tests for all three timing columns |

The Cal-B correction is an intentional, versioned scientific policy amendment:
`phase7_nonoverlapping_cal_b_v2`. It changes threshold eligibility and possibly OOS
results; it is not described as numerical equivalence to the defective old policy.
Historical artifacts and frozen contracts have not been overwritten.

## Live training diagnostics

`PHASE7_METRICS_EVERY` is a positive integer, default `25`; `1` displays every round.
Canonical runs write beneath
`PHASE7_LOG_ROOT/<run_identity>/<fold_id>/<spec_id>/fit-<unique_attempt>.jsonl`.
Partition workers inherit the scope and write separate attempt files. These are
standalone Python logs, with no Aiventra application dependency.

This is regression: “accuracy” means **directional accuracy**, not classification
accuracy. MAE/RMSE/directional diagnostics are unweighted row summaries in the
selected target's units; normalized targets therefore have normalized loss/error
units. The native training L2 retains fitting weights. No precision/F1/AUC,
profitability, portfolio Sharpe, or live-execution result is implied.

The native Validation L2 remains the first metric and sole early-stopping selection
criterion. The observer uses LightGBM's existing evaluation predictions, not a new
`predict()` call per round. Four tiny CPU comparisons (weighted/unweighted and
early-stop/round-limit fixtures) require bitwise-equal predictions and equal best
iterations with logging enabled/disabled. This does not establish production-scale
overhead, RAM sufficiency or GPU equivalence. Stage telemetry remains separate from
per-round predictive metrics; no per-round CPU/RAM/VRAM sampling claim is made.

## Checkpoint compatibility and separation from Aiventra

New scientific source, dependency and policy identities reject incompatible model
resume. Prepared-cache identities now bind dependency compatibility as well. Old
caches are not deleted, rewritten, silently migrated or automatically rebuilt.
Read-only mode fails closed if a compatible cache is unavailable. Validate existing
discovery/acquisition/candle/Gold checkpoints before reuse; these fixes do not
authorize recomputing those layers.

Aiventra runtime/application code and its production source-approval guard remain
unchanged. That guard intentionally rejects this amended engine until a separately
reviewed integration approval exists. Synthetic adapter job-protocol tests now
isolate their fixture from the live checkout's approval state; dedicated tests
still exercise the real guard, including job-preview rejection on scientific drift.
Passing synthetic adapter tests is not approval to launch the amended engine there.

One remaining performance limitation is explicit: completed-spec resume still
validates/loads the prepared fold payload before checking individual spec completion.
The one-fold descriptor fix does not claim to eliminate every startup cost.

## Verification record

The final complete Windows run passed **835 tests, 5 skipped, 0 failures, 0 errors**
in 421.10 seconds (one joblib host-discovery warning). Durable result:
[release JUnit XML](../local_artifacts/phase7/verification/standalone-remediation-release-20261022.xml).
The pre-edge-case complete Windows run passed **822 tests, 5 skipped, 0 failures**
in 374.09 seconds. After the final edge-case corrections, the targeted remediation,
models/economics and adapter suites passed **91 tests** in 11.41 seconds. The new
remediation module contains **41 regression cases**. Linux verification,
real prepared-cache equivalence, real Fold-1 profiling and GPU verification remain
NOT RUN in this session. The Linux studio was not accessible, so the actual remote
cache inventory/compatibility is UNKNOWN, not “missing” or “corrupt.”

Earlier failures are preserved rather than hidden: the initial observer was not
hashable as a LightGBM callback and was corrected; the first full intermediate run
had 794 passes, 13 failures and 5 Windows skips. Eleven failures were synthetic
adapter fixtures encountering the unchanged production source guard; those fixtures
were isolated and a real guard regression added. Two Windows `WinError 5` atomic
rename failures in untouched legacy/data tests passed on isolated rerun (2/2),
without altering frozen earlier-phase source or weakening assertions.

Static checks after the final code changes: Ruff lint PASS; Ruff format PASS
(250 files checked across `src`, `tests`, `integration`, and `scripts`); compileall
PASS; `uv lock --check --offline` PASS (31 packages); `git diff --check` PASS.
One joblib Windows physical-core discovery warning falls back to logical cores;
the five skips cover the Bash/Linux log-rotation utility. Neither is Linux evidence.

Final configuration sanity checks: hash `93f987736b1a79d26b773957`, 16 folds,
48 primary specifications and 109 model features. The exclusive research cutoff
remains July 1, 2026; all prospective holdout flags remain locked and false.
Git diff inspection confirmed no Aiventra runtime/adapter production changes,
no frozen configuration changes and no earlier-phase scientific source changes.
Original unrelated untracked owner files were preserved; no commit or push was made.

Final source/environment identities (LF-normalized source manifest, not a commit):

- Scientific source (48 files):
  `1577f44afe44471eb173778bebb4ca9e4ca2c79e68e5566e1e2d922797f3ef6b`.
- Execution source (15 files):
  `c4d9349909c0c8b8d170679d997300330e2d083431b5b03cfbedf844956af2b6`.
- Dependency compatibility:
  `11c7722c2d289762066135d20fd4f10d4f9e4a7ab402342bfde38161c38f61ba`.
- Local environment: Python 3.12.14, LightGBM 4.7.0, NumPy 2.4.6, PyArrow 24.0.0,
  scikit-learn 1.9.0, joblib 1.5.3, Pydantic 2.13.4.

## Remaining release gates

1. Review this standalone policy/source amendment and checkpoint compatibility.
2. Run the complete Linux suite, lint/format checks and scientific identities.
3. Validate original remote data/Gold checkpoints without recomputation.
4. Inventory compatible prepared caches; obtain separate authorization for any
   necessary profiling/preparation and prove cached/uncached scientific equivalence.
5. Measure production-sized preparation and logging resource cost. Obtain a fresh
   owner cost/deadline contract before exactly one real Fold 1 is considered.

No qualified model exists yet; historical 0/48 Fold-1 reports are incomplete work,
not bad model performance. A local green test suite cannot replace these gates.
