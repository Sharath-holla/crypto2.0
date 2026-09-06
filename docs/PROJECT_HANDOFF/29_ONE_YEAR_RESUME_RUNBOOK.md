# One-Year Resume Runbook

This is for Sharath returning after approximately one year with a new Codex.

> **DO NOT START TRAINING.** Cloud resources, IAM, prices, packages, APIs, and repository state may
> have changed. First reconstruct evidence and obtain a new cost authorization.

1. Read `PROJECT_CONTEXT.md`, `AGENTS.md`, and this entire `docs/PROJECT_HANDOFF/` package.
2. Verify a clean tracked worktree, `main`, `origin/main`, and annotated tags
   `crypto2.0-handoff-20260906` and `phase7a-hold-20260906`. Investigate any divergence; do not reset
   owner files or rewrite history.
3. Check GCP project access, billing status/budget alerts, current pricing, IAM/service account,
   APIs, and resource inventory using read-only commands.
4. Confirm VM `crypto-phase7` status. It should remain terminated until the owner explicitly
   authorizes a bounded start.
5. Confirm the 250 GB disk and `gs://crypto-ai-data-83921` exist. Because `autoDelete=true`, never
   delete the VM before independently preserving the only Gold dataset.
6. Inventory GCS manifests/hold archives. After authorized boot, verify disk mount/filesystem and
   validate registry, discovery 507/507, universe, data checkpoint SHA, 60 candle checkpoints, Gold
   checkpoint, all 138 partitions, hashes, 50,352,548 rows, and dataset ID. File presence is not
   validation. Do not rerun valid discovery/acquisition/Gold.
7. Verify config and artifacts still say July unused and August `LOCKED_UNUSED`, `used=false`,
   `evaluation_authorized=false`; require zero forbidden rows/access.
8. Sync the lockfile environment, then run targeted and complete tests plus Ruff on Linux. Stop on
   identity, leakage, lifecycle, holdout, checkpoint, or operational P0/P1 failures.
9. Profile Fold-1 preparation only: Gold scan, filtering, membership/context, slicing/purge,
   finiteness, Arrow→NumPy, descriptors, and first fit. Record CPU/RSS/I/O/rows/time.
10. Implement the smallest general atomic prepared-matrix checkpoint/cache; bind every scientific
    identity described in `21_FOLD1_PREPARATION_BOTTLENECK.md`. Do not change methodology.
11. Prove uncached/cached scientific equivalence, invalidation, corruption detection, atomic crash
    recovery, and no false COMPLETE. Rerun the full Linux gate.
12. Obtain a fresh owner-approved runtime/cost window. Start only the existing VM, ensure zero stale
    workers, then run exactly one logical Fold-1 worker with independent guest/control-plane guards.
13. Complete all 48 Fold-1 specs and measure preparation, fit, calibration, economics, CPU/RAM/disk,
    and actual cost. Preserve/validate checkpoints.
14. Calculate a conservative folds 2–16 projection. Stop and present evidence; the owner decides
    whether to proceed. Never reset cumulative budgets silently.
15. Only after all authorized folds complete and qualification/robustness gates pass may a separate
    decision consider Phase 7.5 and later paper trading. Phase 8/live trading remain separately
    gated.

Fail closed on unexpected source/config drift, missing/corrupt checkpoints, August access, active-
lifecycle gaps, duplicate workers, false completion, OOM/NaN/storage errors, watchdog failure, or
deadline risk. Preserve evidence and terminate paid compute safely under the approved policy.
