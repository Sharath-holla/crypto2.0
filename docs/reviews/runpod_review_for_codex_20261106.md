# RunPod readiness review, for Codex (2026-11-06)

Author: Claude (Cowork). Scope requested by the owner: check thoroughly for remaining errors, review
the architecture, change as little code as possible, keep the existing (older) Gold training data
unchanged, and prepare to run on RunPod instead of the 16 GiB MacBook. **Nothing was trained.**
Gold, the sidecar, the checkpoints and the artifacts were only read. August = LOCKED_UNUSED.

## 0. What was and was not verified (read first)

* I could not execute the project: my sandbox is a separate Linux aarch64 machine with Python 3.10 and
  no PyPI. The owner's Mac does have Python (uv-managed 3.12.16, per your own `environment.json`);
  the "no Python / no pyarrow" remark applied only to my sandbox. Everything below that says
  "static" was read from files, not run.
* Re-verified by me today: all 138 Gold partitions hash to the manifest (read-only, stdlib script
  `scripts/closure/verify_gold_hashes_readonly.py`, PASS, no unlisted files); sidecar `manifest.json`
  SHA-256 equals `ea5f25a2...2048`; `pytest_final.xml` says 1370 tests / 0 failures / 0 errors / 1 skipped;
  all 302 Python files parse; no macOS junk (`.DS_Store`, `._*`) inside Gold or the sidecar; no
  case-colliding file names in git (matters on Linux); 793 of 793 files referenced by the stage
  checkpoints exist locally; the static import-boundary scan (155 `crypto_ai` modules) is clean.
* uv.lock has Linux x86_64 + aarch64 + macOS arm64 wheels for lightgbm 4.7.0, pyarrow 24.0.0,
  numpy 2.4.6, scipy, pydantic-core, psutil. `requires-python >= 3.11`.

## 1. Findings, most important first

| # | Finding | Status |
|---|---|---|
| F1 | **RAM and disk gates read the HOST, not the container.** `runtime.system_snapshot` and `memory_snapshot` use `psutil.virtual_memory()`. On RunPod/Docker the cgroup limit is the real ceiling, so `resource_admission` (RAM floor) and the preflight could pass on a pod that is about to be OOM-killed. | **FIXED** (small): `runtime._container_adjusted_memory` uses the cgroup v1/v2 limit and current usage only when a limit below host RAM is readable; macOS/bare metal unchanged. `resource_estimate.cgroup_limits` now also returns `cgroup_memory_current_bytes`. Two unit tests added (NOT run; need your Mac pytest). |
| F2 | **The stage checkpoints contain absolute Lightning paths** (`/home/nssharath123/crypto2.0/...`): 121 in `data`, 140 in `gold`, 530 in `universe`, 2 in `registry`. They resolve only through `PHASE7_LEGACY_*` roots. `benchmark_one_spec --execute` refuses to start unless the registry/universe/data/gold checkpoints verify. | Documented. Exact push list: `docs/reviews/evidence_closure/runpod_push_list.txt` (793 files, 10.2 GB, 0 missing locally). Silver/Bronze *parquet* are NOT needed, only the listed manifests. |
| F3 | **Working tree must be pushed byte-for-byte.** `scientific_source_identity()` hashes the tracked source files and (new) the sidecar manifest. Your uncommitted work is therefore part of the run identity. Do not `git checkout` an older commit on the pod; commit, then rsync/archive exactly that tree and compare `scientific_source_identity()["manifest_sha256"]` on both machines. | Operational. |
| F4 | **Network-volume risk.** Atomic rename, `fsync`, `flock`/run-lease and the cache lock are exercised only on macOS APFS. RunPod network volumes can behave differently. | Put `PHASE7_CHECKPOINT_ROOT`, `PHASE7_CACHE_ROOT`, output and logs on the pod's LOCAL disk; copy results out afterwards. Run `scripts/closure/verify_linux_external.sh` first (it is the only Linux evidence that can exist). |
| F5 | **CPU count is host-level** (`os.cpu_count()` in `ComputeBudget` and `models.py`). Harmless today because `ComputeBudget` raises if `PHASE7_TOTAL_CPU_THREADS` > detected and the default is 4 threads, but telemetry will show the host count. | Set `PHASE7_TOTAL_CPU_THREADS` to the pod's vCPU count. Optional later: use `len(os.sched_getaffinity(0))` and the cgroup quota (not done: could change test expectations). |
| F6 | `_context_sidecar_path` hard-codes the Gold dataset id (`gold-phase7-0cbf2910...`) to decide the sidecar is mandatory. Works, but any other Gold dataset silently skips the M-01 repair. | Suggestion: derive "sidecar required" from the census evidence hash recorded in the sidecar identity, or fail closed for any dataset not in an allow-list. |
| F7 | `load_sidecar_source` re-hashes every overlapping partition (up to 0.74 GB) on each call and `scientific_source_identity()` re-reads and hashes the manifest on every call. Correct but wasteful over 16 folds. | Suggestion: memoize by (path, mtime, size) per process. |
| F8 | The resource estimator is a whole-horizon average (66.1 GiB) and the fold-specific number only exists as an ad hoc computation in `resource_preflight.json` (25.8 GiB). | Suggestion: add `--fold-index` to `resource_estimate` so the preflight uses observed fold row counts. |
| F9 | `git count-objects` shows ~190 `tmp_obj_*` "garbage" files from commits made through the sandbox bridge. Harmless. | On the Mac: `git prune` (or `git gc`). |
| F10 | Numeric note from your report: sidecar vs producer differ by <= 4e-16 on two volatility columns (kept as a documented FAIL of exact equality). Training only reads the sidecar, so a Linux/x86 run does not recompute these features; identity stays stable. Do not re-run the feature producer on the pod and compare. | Informational. |

No other defect was found by reading: the ledger, admission, selection protocol, preparation identity,
H0 ownership, Cal-A purge and vol-floor inverse code paths are the ones your 1370-test run covers.

## 2. Architecture observations (suggestions only, none applied)

1. `training.py` is >1,900 lines mixing orchestration, identity, cache keys, publication and report
   building. Splitting out `identity.py` and `publication.py` would make the identity layers (preparation,
   scientific, experiment-control, ledger) reviewable on their own.
2. Configuration is ~40 `PHASE7_*` environment variables. A typo silently falls back to a default.
   Suggest: reject unknown `PHASE7_*` names at admission and write the fully resolved settings into
   the run manifest.
3. The cloud gate is a single boolean env var (`PHASE7_ALLOW_CLOUD_RESEARCH=1`). Consider also
   binding the approval to the admission record's hashes, so an approval for one run cannot be
   replayed for another.
4. Three identity layers plus the sidecar hash must agree between Mac and pod. A single printed
   "identity summary" command (preparation digest, scientific manifest, experiment-control, protocol
   digest, sidecar sha, Gold manifest sha) would make push verification a one-line diff.
5. Gold is 130 columns while the model uses 109; fold loading reads all columns' Arrow copies
   (~10 GB heuristic of the 25.8 GiB). Column projection at read time would cut peak RAM materially
   without changing any value (cache identity unaffected if the projected columns are the same
   ones the model already uses). Do this only after a first measured run.
6. Reports/ledger are consistent; keep CSV strictly a view. Keep `NOT_MODELLED` funding labels in
   every artifact; there is still no portfolio engine, so no profitability claim is possible.

## 3. RunPod plan (CPU pod, plumbing smoke: `architecture-G0-A6-60m-raw`, Fold 0, CPU)

Why a pod solves the earlier problem: the full-universe Fold 0 heuristic peak is 25.8 GiB; a 3-coin
code path is not needed. Suggested pod: CPU or any pod used CPU-only (GPU is not qualified and the
smoke refuses it), >= 64 GiB RAM (about 2.4x the heuristic), >= 8 vCPU, >= 150 GB local disk.
No cost figure is asserted here; the owner must approve the pod, its price and a stop deadline.

Push (from the Mac; use rsync, not tar, so no `._*` files are created; `COPYFILE_DISABLE=1` if tar):
* the committed source tree (exact bytes, see F3), without `.venv`, `.git`, `Claude outputs`;
* every path in `runpod_push_list.txt`, keeping the layout under `crypto2-persistent/`;
* `phase7/checkpoints/phase7a-core20-primary-93f987736b1a79d26b773957/` and
  `phase7/artifacts/phase7a-core20-primary-93f987736b1a79d26b773957/` (about 5 MB);
* the sidecar directory `feature_context_sidecar_v3/` (manifest, 8 parquet parts, `SIDECAR_COMPLETE`).

On the pod (order matters; stop at the first failure):
```bash
apt-get update && apt-get install -y libgomp1 rsync      # LightGBM needs OpenMP
curl -LsSf https://astral.sh/uv/install.sh | sh          # then: uv sync --locked --extra dev --python 3.12
P=/workspace/crypto2-persistent           # pushed data
L=/workspace/local                        # pod-local disk for cache/checkpoints/output
export PHASE7_DATA_ROOT=$P/data
export PHASE7_GOLD_ROOT=$P/data/gold/phase7a_core20_primary_v1
export PHASE7_ARTIFACT_ROOT=$P/phase7/artifacts
export PHASE7_CHECKPOINT_ROOT=$P/phase7/checkpoints   # copy to $L if the volume is a network volume
export PHASE7_CACHE_ROOT=$L/prepared_cache PHASE7_MODEL_ROOT=$L/models \
       PHASE7_REPORT_ROOT=$L/reports PHASE7_LOG_ROOT=$L/logs PHASE7_TEMP_ROOT=$L/tmp
export PHASE7_LEGACY_DATA_ROOT=/home/nssharath123/crypto2.0/data
export PHASE7_LEGACY_GOLD_ROOT=/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1
export PHASE7_LEGACY_ARTIFACT_ROOT=/home/nssharath123/crypto2.0/local_artifacts/phase7
export PHASE7_FEATURE_CONTEXT_SIDECAR=/workspace/sidecar/feature_context_sidecar_v3/manifest.json
export PHASE7_LGBM_DEVICE=cpu PHASE7_MODEL_PARALLELISM=1 PHASE7_TOTAL_CPU_THREADS=$(nproc)
export PHASE7_MIN_FREE_RAM_GIB=20 PHASE7_MIN_FREE_DISK_GIB=50 CRYPTO_AI_RESEARCH_MODE=1
# 1 data: python3 scripts/closure/verify_gold_hashes_readonly.py --gold-dataset-dir <gold-phase7-...> --output $L/gold_hash.json
# 2 Linux gate: bash scripts/closure/verify_linux_external.sh   (unsets PHASE7_*; run it in a fresh shell)
# 3 resource: uv run python -m crypto_ai.phase7.resource_estimate --manifest <gold manifest> --path $L --json
# 4 prepare:  PHASE7_ALLOW_CLOUD_RESEARCH=1 PHASE7_CACHE_MODE=auto uv run python -m \
#             crypto_ai.phase7.benchmark_one_spec --spec-id architecture-G0-A6-60m-raw \
#             --output-root $L/out --execute --prepare-only
# 5 then, ONLY after the owner reads steps 1-4 and approves: the same command with
#   PHASE7_CACHE_MODE=read_only and without --prepare-only.
```
`PHASE7_LEGACY_*` values are the old Lightning prefixes taken from the checkpoint contents above; the
exact variable semantics are in `docs/LIGHTNING_PHASE7A_RUNBOOK.md` (lines 56-62) and
`runtime.RuntimePaths.legacy_checkpoint_roots`. Codex: please confirm against the Mac invocation you
already used, and correct this block if your working invocation differs.

Still NOT established after all of the above: tradability, funding, portfolio metrics, a qualified
cache, genuine Linux verification, and any claim about edge. The smoke is plumbing only.

## 4. Files changed by this review

`src/crypto_ai/phase7/runtime.py`, `src/crypto_ai/phase7/resource_estimate.py`,
`tests/phase7/test_phase7a_resource_estimate.py` (small, marked `CHANGED BY CLAUDE`),
`docs/reviews/evidence_closure/runpod_push_list.txt`, this report. Gold and training data: untouched.
Please run `uv run pytest tests/phase7/test_phase7a_resource_estimate.py -q` and
`uv run ruff check . && uv run ruff format --check .` on the Mac before relying on the F1 fix.
