# Crypto 2.0 local review — 2026-11-08

Integration update: Claude has now finished and applied the proposed Ridge block-size guard,
with regression coverage in `test_training_observer_diagnostics.py`. The combined source was
committed as `7a64ee0` and independently verified on its Git-free export: **1,471 passed**,
Ruff passed, and six identities matched. See the
[combined closure](CRYPTO2_COMBINED_LOCAL_CLOSURE_20261108.md). The concurrent-snapshot results
below are preserved as historical evidence. External gates remain deferred and this update
does not authorize training.

**Phase 7A CORE20 PRIMARY; NOT_READY_FOR_SMOKE.** This is a focused follow-up to the
[master report](CRYPTO2_FINAL_MASTER_READINESS_REPORT_20261106.md), not a replacement for its
data, recovery, holdout, or external qualification evidence. The owner deferred RunPod/Linux
setup and confirmed that Claude Code is still editing training diagnostics.

## Work completed locally

Reviewed the changed hardening configuration, experiment identity, observer, action/regression
metrics, fit-boundary checks, model wiring, training report wiring, and associated tests.
Used isolated detached worktrees to avoid testing a moving source tree. Preserved the earlier
unrelated review documents, source work in progress, and all historical failure evidence.

Applied four narrow fixes to the shared repository:

| Finding | Reproduction | Fix and verification |
| --- | --- | --- |
| Diagnostic thresholds can underflow to zero | A positive `1e-323` bps threshold becomes zero raw return, so a zero prediction is both LONG and SHORT; action coverage becomes 200% and NO_TRADE count becomes -1 | `ActionThresholds` rejects thresholds that are not representably positive after conversion to raw returns. Boundary/zero tests preserve the normal 5 bps behavior. |
| Diagnostic sampling can exceed its row budget | An uneven synthetic timestamp population selected 9,909 rows with a 1,000-row limit | Sample whole timestamp groups within the actual row cap; omit oversized groups, reject an impossible whole-group sample, and validate timestamp alignment. Sampling stays deterministic. |
| Prediction distribution uses the wrong population | Predictions `[1, 100]` with actuals `[1, NaN]` reported a prediction mean of 1 instead of the documented finite-prediction mean 50.5 | Compute prediction distribution over all finite predictions; keep error metrics and prediction/actual variance ratio on the same finite pairs. Distribution remains available when actuals are all missing. |
| New fit-acceptance guard is missing from the control identity | Changing `fit_boundary.py` did not change the experiment-control digest | Include the guard source in the identity and fail closed if it is missing. Pure monitoring setting classifications are independently checked. |

The first three changes affect diagnostic computation only. The identity change intentionally
prevents mixing different fit-acceptance policies on resume. No feature, label, Core20 membership,
selection rule, or stored market-data artifact was modified by these fixes.

The independent regression file is
[test_local_review_diagnostics.py](/Users/cortex/Projects/crypto2.0/tests/phase7/test_local_review_diagnostics.py).
The four fixes produced **10 failing regression cases before repair and 14 passing cases after**.
Three other useful boundary cases were already passing before the first three fixes; identity
coverage adds two formerly failing cases and one passing consistency check to that original set.

## Executed verification

| Run | Actual result |
| --- | --- |
| Initial complete snapshot suite | 1,392 passed, 2 failed; the assertions still expected the removed pooled precision/recall console contract |
| Subsequent complete snapshot suite, including independent fixes | **1,408 passed; zero failures, errors, or skips** |
| Same snapshot Ruff lint / format | **PASS; 738 files formatted** |
| Independent regression file | **14 passed** |
| New shared diagnostic tests plus independent regressions | **72 passed** on the later shared tree, including the new incremental prediction check; earlier 71-case result retained |
| Additional active-observer equivalence fixtures | **4 passed**; exact predictions and best iteration match with and without diagnostics for raw/normalized targets and weighted/unweighted fits |
| Latest complete snapshot suite after additional concurrent changes | **1,465 passed; zero failures, errors, or skips; 169.78 seconds** |
| Latest snapshot Ruff lint / format | **PASS; 739 files formatted** |

The two obsolete assertions were corrected in Claude's concurrent changes; the original failures
are retained. These were not treated as model-performance results or silently skipped.
The four equivalence fixtures use tiny synthetic arrays and CPU LightGBM fits. They do not fit a
real-data model, construct a real prepared cache, or establish scientific model quality.

The earlier passing snapshot is identified by
[verified_snapshot_manifest.json](evidence_local_review_20261108/verified_snapshot_manifest.json).
The subsequent snapshot includes Claude's full-TRAIN weighted Ridge implementation, console
formatting updates, fixture repairs, and new diagnostic tests; it is identified by
[latest_snapshot_manifest.json](evidence_local_review_20261108/latest_snapshot_manifest.json).
Claude continued changing `training_metrics.py` and its diagnostic tests during the latest run,
including an incremental prediction cache for monitoring. Those subsequent edits are not covered
by the 1,465-test snapshot result. The source comparison is retained in
[concurrent_state_at_review_close.json](evidence_local_review_20261108/concurrent_state_at_review_close.json).
These are dirty-tree review snapshots, not committed RunPod source exports. The old verified
source export `99cf12f` does not contain the newer work.

## One proposed fix in an actively edited file

**`hardening.matched_ridge_predict`: validate `block_rows` before use.** In the newly added
implementation, zero and negative sizes are accepted. The iteration step is clamped to 1 but the
same invalid size is still used for slicing. A zero-size slice can leave the `np.empty` prediction
buffer unwritten; a float raises an incidental TypeError, and True is accepted as a row count.
The normal production caller uses a positive default, so this is an input-validation defect,
not evidence that current default predictions are wrong.

Prepared and independently exercised a two-line guard rejecting non-positive integers, floats,
and booleans. It is **proposed only**, because the owner confirmed Claude is editing this area.
It does not change the positive-default Ridge algorithm or its scientific definition:

- [Proposed patch](evidence_local_review_20261108/pending_matched_ridge_block_guard.patch)
- [Before/proposed verification](evidence_local_review_20261108/pending_ridge_guard_verification.json)

Also retain the explicit F1 policy: when either side precision or recall is undefined, F1 is null.
This is the policy now asserted by the new diagnostic tests; it is not a model selection metric.
The count-formula documentation should be read with that explicit undefined-value convention.

## Handoff and next boundary

Updated [PROJECT_CONTEXT.md](/Users/cortex/Projects/crypto2.0/PROJECT_CONTEXT.md) to distinguish the
historical remote freeze from the validated recovered local data, identify the current report,
and explain that prepared-cache implementation exists while real-data qualification is pending.
The older handoff package remains historical evidence.

After Claude finishes: reconcile the proposed guard, inspect the combined diff, rerun the full
suite/lint/format on the final source, commit/freeze that exact source, and regenerate the portable
source inventory and six identities. Existing recovered data and the validated feature-only
sidecar should be reused. Do not transfer an older source archive as though it contains these edits.
Do not commit another editor's unfinished changes merely to obtain a new export hash.

The deferred external sequence remains:

1. Owner supplies the authorized Linux target and cost/deadline contract.
2. Revalidate transferred checkpoints/data/sidecar, six identities, full Linux software gate,
   and the intended local cache/output filesystem.
3. Separately authorize one real prepare-only run; measure resources and prove cached/uncached
   and read-only reload equivalence.
4. Only after all smoke-critical gates pass, authorize one CPU training smoke.

No cloud resources were started, real market data regenerated, real model/cache built, orders
placed, or July/August outcomes accessed. August remains `LOCKED_UNUSED`; the full grid remains
`NOT_AUTHORIZED`. Source work remains uncommitted while Claude is editing; no push was made.

Evidence index: [README](evidence_local_review_20261108/README.md).
