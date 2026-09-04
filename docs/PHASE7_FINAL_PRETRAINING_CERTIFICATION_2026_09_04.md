# PHASE 7 FINAL PRE-TRAINING CERTIFICATION

Date: 2026-09-04 UTC/IST review window

## 1. FINAL VERDICT

**NOT READY — the GCP billing account is disabled/delinquent.** The canonical
VM cannot be started, and GCS object reads/downloads return HTTP 403. Therefore
the mandatory fresh Linux verification at final HEAD, authoritative durable
state parsing, checksum validation, and read-only restore drill could not be
completed. No Phase 7 training or discovery was started.

## 2. GIT

- Starting laptop HEAD: `86cece5ca4a2eee886d5e2f411365bec1035311b`.
- Refreshed upstream/base before this pass: `158486f8b622bd2b5adc885240d1089464f725c5`.
- Hardened code commit: `91b59270e072255c264e22265855436d6fbed3ae`.
- Push status: `158486f..91b5927 main -> main` succeeded.
- The final report commit is the commit containing this document; its SHA is
  recorded in the task's final response because a commit cannot contain its
  own hash.
- Tracked worktree state was clean after the code commit. Pre-existing
  untracked audit directories, patches, and review material were preserved and
  excluded from the commit. No `data/phase7/` directory existed on the laptop.
- Canonical VM HEAD and worktree could not be inspected because VM start was
  rejected by disabled billing.

## 3. DISCOVERY

- Current authoritative `507/507` state: **not freshly verified**. GCS filename
  inventory is consistent with completed discovery, includes a final
  `ZRXUSDT` checkpoint, and contains 714 discovery checkpoint objects across
  current/versioned and legacy layouts, but object contents could not be read.
- No training model/checkpoint object names were found in the run-scoped
  backup inventory. This is supporting evidence only, not a substitute for
  parsing the canonical progress and supervisor state.
- Exactly five exclusion objects were inventoried for `GTCUSDT`, `ICPUSDT`,
  `MAGICUSDT`, `QNTUSDT`, and `TLMUSDT`; content/parsing verification is blocked.
- Discovery was not rerun.

## 4. HOLDOUT

- Configuration hash: `cc550337f1f4ee4654124bf6` (unchanged).
- Run identity: `phase7-cc550337f1f4ee4654124bf6` (unchanged).
- Research cutoff: `2026-07-01T00:00:00Z`, exclusive.
- Prospective holdout start: `2026-08-01T00:00:00Z`.
- Local contract/test result: `LOCKED_UNUSED`, `used=false`,
  `evaluation_authorized=false`.
- A synthetic August sentinel was proven present in isolated raw test input and
  absent from targets, Gold, and any model/training output path.
- The canonical durable state could not be parsed from the stopped VM or GCS,
  so the historical persisted flags are not reported as freshly verified.

## 5. PAIR_STATS

- Overflow form changed from `sqrt(var_x * var_y)` to
  `sqrt(var_x) * sqrt(var_y)` in correlation and conditioning math.
- One-dimensional/aligned shape validation now runs before the short-window
  early return. Valid short inputs retain the documented all-NaN result;
  malformed short inputs fail loudly.
- On platforms where `longdouble` has no more precision than `float64`
  (Windows), the exact reference implementation is used. The canonical Linux
  VM retains the vectorized extended-precision implementation.
- Focused reference-equivalence suite: 19 passed. Coverage includes normal,
  constant, near-constant, NaN-heavy, Inf-as-missing, perfect/anti-correlation,
  extreme magnitude, short/window-boundary, malformed shape, BTC, and ETH cases.
- Historical measured benchmark at commit `3f319c3`: 685,000 rows, window 2,016,
  144.9 seconds reference versus 0.20 seconds vectorized (714x); maximum
  correlation difference `1.2e-12` and beta difference `3.1e-12`.
- That benchmark was not rerun on the final Linux code because the VM could not
  start. Current Linux performance is therefore pending, not claimed.

## 6. TRAINING CHECKPOINT IDENTITY

- Previous identity used static `code_version="1.8.0"` alongside fold, Gold,
  configuration, feature, target, universe, and membership identities.
- New identity adds `phase7_training_source_manifest_v1`: a canonical manifest
  of 25 explicitly enumerated training-critical source files, each with SHA-256,
  plus a canonical 64-character manifest hash.
- Final local source manifest hash:
  `cecfc9d354218330be6df030f62422d891a33208ba38b5f35ced96ac1ae908de`.
- The source set covers data manifest/storage and Phase 5/6/7 calibration,
  folds, features, labels/targets, Gold, universe, models, training, economics,
  checkpoint/artifact, registry, segment, and pipeline code. Logs, tests,
  reports, and runtime artifacts are deliberately excluded.
- Missing source, corrupt identity, or a changed training-critical source fails
  closed. An irrelevant runtime report does not invalidate a checkpoint.
- `COMPLETE` orphan adoption now independently reconstructs and validates model,
  calibrator, threshold, frozen-component, and frozen-test identities.
- Regression tests prove same-source reuse, critical-source rejection,
  corrupted-identity rejection, orphan mismatch rejection, corrupt/missing
  model rejection, missing calibrator/threshold rejection, programming-error
  propagation without false `COMPLETE`, and resumable legitimate `INELIGIBLE`.

Scientific byte-freeze consequences:

- `features.py`: `f6db831af8c2922df57fbbd47ebe4a14fca6c42564cb8d18939803569e556e8d`
  -> `eb3e99b28c0ba3b070758dcfbb77deb189b2adc4f9cb19da7c3f838230946b48`.
- `training.py`: `0447b07187fc4162ac3c5c390eb94046a6081b7046fa84b88139a06c71be3738`
  -> `d80a2d4094a7ba14657fa175468e9f80d9e25c5e1978b3c50b9c83900f98350a`.
- The repository-approved source-freeze manifest was mechanically repinned only
  after reference-equivalence, timing/holdout, checkpoint, baseline, and full
  tests passed. Configuration, target, feature meaning, fold/universe method,
  timing, and holdout semantics remain unchanged.

## 7. SECURITY

- High-confidence tracked secret files: 0.
- High-confidence workspace secret files after remediation: 0 (excluding Git,
  virtual environments/caches, generated data, and inaccessible pytest temp).
- The untracked `ask_gpt.py` plaintext API-key literal was removed. It now reads
  `SEEKAI_API_KEY` from the environment and is explicitly ignored by Git.
- The previously exposed credential should be rotated by its owner if it ever
  reached chat, logs, backup, or another shared system. No credential was
  printed or automatically revoked.
- No tracked Binance secret, GitHub deploy key, GCP private key, or recognized
  OpenAI/Claude/API token was found.

## 8. GCS

- Backup URI:
  `gs://crypto-ai-data-83921/artifacts/phase7/backup-phase7-cc550337f1f4ee4654124bf6-20260904T044426Z/`.
- Filename inventory: 3,361 objects.
- Previously measured aggregate size: 4,521,436,877 bytes (4.21 GiB).
- Manifest object: `backup_manifest.json`, previously measured at 767,197 bytes.
- Inventory includes configuration/run identity, registry, discovery
  checkpoints, progress, supervisor state/history, exclusions, quarantine,
  reconciliation, quality evidence, manifests, and a compressed historical log.
- Historical log backup: 96,156,869 bytes (91.70 MiB compressed).
- Current metadata/checksum reads and downloads fail with HTTP 403 because the
  owning project's billing state is delinquent. Manifest parsing, checksum
  comparison, and the representative read-only restore drill are **not done**.
- The isolated temporary restore directory was removed after the failed
  download; no active project data was overwritten or deleted.

## 9. LOGGING / DISK

- Pre-start rotation is implemented by `rotate_phase7_run_log.sh`: default
  threshold 512 MiB, two gzip generations, skip while a worker is active,
  atomic move, and restore on compression failure.
- `run_phase7_worker.sh` rotates before opening the writer and maps a `tee`
  write failure to exit 74, preventing silent continuation after log/disk I/O
  failure. Five focused rotation cases pass locally, including injected gzip
  failure and restoration of the live log.
- Rotation bounds growth across starts/resumes, but deliberately does not rotate
  under an active writer; a single uninterrupted long run can exceed 512 MiB.
- Laptop free disk measured 388.36 GiB. Canonical VM disk capacity is 250 GB;
  current VM free/used space could not be measured while billing is disabled.
- The pipeline requires at least 8 GiB free disk and 8 GiB RAM at startup and
  records disk-free values in training heartbeats. The 8 GiB reserve is a
  fail-fast floor, not a capacity proof for the projected run.

## 10. FINAL TESTS

- Local full pytest: **573 passed, 0 failed, 0 skipped, 1 warning in 147.84 s**.
  The warning is joblib's harmless Windows physical-core detection fallback.
- Ruff configured scope: `ruff check src tests scripts` passed.
- Ruff formatting: `ruff format --check src tests scripts` passed; 198 files
  already formatted.
- Scientific baseline/non-interference plus log rotation focus: 13 passed in
  9.18 s.
- `_pair_stats` reference-equivalence focus: 19 passed.
- Tiny end-to-end integration/reproducibility test passed twice-exact checks for
  Arrow feature/target hashes, folds, universe/fold membership, predictions,
  reports, frozen identities, and checkpoint behavior.
- Holdout, timing, purge/120-minute embargo, folds, Gold/data lineage,
  checkpoint/resume, error classification, supervisor, and failure paths all
  pass within the full suite.
- Leakage sentinel: **CLEAR**. No negative shift, backfill, centered rolling,
  forward as-of, random split, or shuffled production training was found.
  Scalers found in context are fitted only on TRAIN-known descriptors/rows;
  the shuffled-label path is an explicitly TRAIN-only negative control.
- `python -m compileall -q src tests` passed; `uv lock --check` resolved all 30
  locked packages. Local `uv sync --frozen --extra dev` succeeded with Python
  3.12.14 and the locked environment.
- Existing vulnerability scanners (`pip-audit`, `osv-scanner`) were not
  installed; no dependency upgrade was attempted.
- Mandatory fresh Linux run at final HEAD: **NOT RUN — billing blocker**.

## 11. REMAINING FINDINGS

- P0: none found in the locally verified code/contracts.
- P1: disabled/delinquent GCP billing blocks the mandatory canonical Linux test,
  VM durable-state inspection, current VM disk check, GCS checksum reads, and
  restore drill. This single infrastructure condition prevents certification.
- P2: rotate the formerly embedded scratch API credential; measure final Linux
  `_pair_stats` and representative LightGBM throughput before committing budget;
  verify that VM RAM/disk projections fit actual Gold metadata.
- P3: one benign Windows joblib physical-core warning; no installed dependency
  vulnerability scanner.

## 12. TRAINING CAPACITY ESTIMATE

Measured/fixed planning facts:

- VM: e2-standard-16, 16 vCPU, 64 GB RAM, 250 GB disk; model fits are sequential
  and each LightGBM estimator is capped at four threads.
- Range: 2,373 days, at most 683,424 five-minute rows per full-history symbol,
  and at most 20,502,720 feature-time rows for 30 symbols before eligibility,
  gaps, warm-up, and listing-history reductions.
- Four horizons can produce an upper planning envelope near 82 million
  horizon rows before exclusions.
- Plan: 16 folds x 2 research views x 58 experiment specifications = 1,856
  model bundles. With four clusters and 30 eligible symbols, the architectural
  ceiling is about 10,048 LightGBM estimators; actual P0/C0 eligibility and
  early stopping should reduce this.
- Historical `_pair_stats` benchmark: 0.20 s per 685k-row symbol-anchor call on
  the measured host; the prior reference implementation took 144.9 s.

Low-confidence projections (no final VM Gold/model benchmark was possible):

| Resource | Optimistic | Expected | Conservative |
| --- | ---: | ---: | ---: |
| Feature/target/Gold wall time | 2-6 h | 8-20 h | 24-48 h |
| Training wall time | 120-250 h | 300-800 h | 1,000-2,000 h |
| Peak fold memory | 20-30 GB | 35-55 GB | over 64 GB |
| Gold/intermediate disk | 15-30 GB | 30-70 GB | 80-120 GB |
| Model/report artifacts | 5-15 GB | 20-60 GB | over 100 GB |
| Checkpoint metadata | 10-30 MB | 50-150 MB | about 300 MB |
| One uninterrupted live log | 0.2-0.5 GB | 0.5-2 GB | 5-20 GB |

The expected first bottleneck is CPU/wall-clock because thousands of estimator
fits are sequential and use only four threads. RAM is the closest fail-fast
capacity risk, and disk can become limiting in the conservative case. These
ranges must be replaced with actual Linux measurements before budget approval;
they are not runtime promises.

## 13. SCIENCE INVARIANTS

- Binance USD-M perpetual futures remain the canonical market; Spot remains
  explicit secondary/cross-market data and is not merged into USD-M Bronze.
- Five-minute decision data remains primary; required context is 12h/1d.
- The 54-native-feature contract is unchanged.
- `multiasset_targets_v2`, horizons 15/30/60/120 minutes, and G0/C0/P0/H0 are unchanged.
- Sixteen causal rolling folds and CORE/EXPANDING views are unchanged.
- Entry timing remains `open[i+2]`.
- Purge uses actual `label_end_time`; the 120-minute embargo is intact.
- `NO_TRADE`, costs, funding method, model families, and qualification rules are intact.
- Leverage is not a predictive input; no risk/leverage/live execution engine was added.
- July remains outside research/evaluation and August remains locked by config and tests.

## 14. WORKER STATE

- Final VM state: `TERMINATED`.
- A terminated VM cannot have a running research process; effective worker count
  is zero.
- `tmux ls`, `pgrep`, canonical progress parsing, and persisted
  `training_started=false` could not be freshly checked because the VM never
  started. No local training command, discovery command, Fold 1, Phase 8, or
  trading process was launched.

## 15. NEXT SAFE COMMAND

Do not run this until billing is restored, the blocked Linux/GCS verification
gates pass at final HEAD, budget environment values are explicitly approved,
supervisor state is clear, and the owner separately authorizes training.
With the runbook-required environment variables already exported, the canonical
launcher is:

```bash
tmux new-session -d -s phase7-supervisor -c "$HOME/crypto2.0" \
  "uv run python scripts/phase7_vm_supervisor.py supervise \
  --repository $HOME/crypto2.0 >> local_artifacts/phase7-supervisor.log 2>&1"
```

This command was printed only and was not executed.
