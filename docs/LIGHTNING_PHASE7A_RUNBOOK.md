# Lightning Phase 7A Runbook

This is a future, owner-reviewed workflow. The project remains on hold. This remediation did not
start cloud compute, migrate data, execute production training, or authorize any paid resource.
Before starting Lightning/L4 compute, agree a fresh cost ceiling, deadline, shutdown procedure and
scope with the owner. Keep July unused and August permanently LOCKED_UNUSED.

## 1. Open Lightning and retrieve the remediation

Use the owner-approved Linux workspace and NVIDIA L4 24 GB configuration. Do not invoke historical
GCP worker/supervisor/tmux scripts. Use a full clone so the frozen commit and tags remain available.
Pull the reviewed remediation commit, inspect Git status and preserve existing local edits.

```bash
git status --short
git log -5 --oneline
git tag --list '*20260906*'
uv sync --locked --extra dev
```

Check LightGBM's build, not just GPU presence. The ordinary wheel is not proof of CUDA support.
`device_type=gpu` is OpenCL; `device_type=cuda` is a separate implementation. Evaluate CUDA
explicitly on Linux/L4. Build/install according to the
[official installation guide](https://lightgbm.readthedocs.io/en/latest/Installation-Guide.html).
Do not tune frozen scientific parameters, `max_bin`, seeds, precision or feature selection for speed.

## 2. Configure execution paths

Choose actual Lightning persistent-storage paths. The following relative-to-PWD example is for a
workspace whose current directory is on persistent storage; replace it with the approved layout.
Do not edit frozen scientific TOML merely to change machine paths.

```bash
export PHASE7_DATA_ROOT="$PWD/persistent/data"
export PHASE7_GOLD_ROOT="$PWD/persistent/gold"
export PHASE7_ARTIFACT_ROOT="$PWD/persistent/artifacts"
export PHASE7_CACHE_ROOT="$PWD/persistent/prepared_cache"
export PHASE7_CHECKPOINT_ROOT="$PWD/persistent/checkpoints"
export PHASE7_MODEL_ROOT="$PWD/persistent/models"
export PHASE7_REPORT_ROOT="$PWD/persistent/reports"
export PHASE7_LOG_ROOT="$PWD/persistent/logs"
export PHASE7_CACHE_MODE=auto
export PHASE7_LGBM_DEVICE=cuda
export PHASE7_TOTAL_CPU_THREADS=4
export PHASE7_MODEL_PARALLELISM=1
export PHASE7_LIGHTGBM_THREADS_PER_MODEL=4
# RAM admission is optional; set only a reviewed, measured floor (not an assumed 32/64 GiB).
# export PHASE7_MIN_FREE_RAM_GIB=OWNER_APPROVED_POSITIVE_GIB
export PHASE7_MIN_FREE_DISK_GIB=25
# Optional publication cap; choose after measuring the full cache/disk workload:
# export PHASE7_CACHE_MAX_GB=100
```

The CPU example assumes at least four logical CPUs; use the actual allocated budget. Do not lower
RAM/disk floors merely to pass preflight. Host RAM, L4 VRAM, and persistent disk are different limits.
Keep `PHASE7_ALLOW_CLOUD_RESEARCH` unset during migration/validation/synthetic checks.

New checkpoint files use logical roots. For historical absolute records, explicitly map each old
artifact/Gold/model/report root to its corresponding runtime root using
`PHASE7_LEGACY_DATA_ROOT`, `PHASE7_LEGACY_ARTIFACT_ROOT`, `PHASE7_LEGACY_GOLD_ROOT`,
`PHASE7_LEGACY_MODEL_ROOT`, and
`PHASE7_LEGACY_REPORT_ROOT`. Values are the old root prefixes from trusted evidence, not guessed
replacement paths. Relocation must retain SHA-256 checks and original checkpoint bytes.
Legacy DATA mappings also resolve Silver group/child/source manifest inputs read for fold
descriptors, without editing historical manifests or bypassing segment/partition hash checks.

## 3. Migrate and verify the complete research state

The operator already completed the basic GCP→GCS backup: 139 source files, 139 GCS objects,
approximately 9.1 GB source and 9.01 GiB GCS. No GCP reconnection is required by this remediation.
Copy the approved GCS objects to Lightning persistent storage using the owner's chosen transfer
workflow. Copy existing registry/universe/data/Gold result/checkpoint state and source inputs needed
for fold descriptors as well. Gold alone is insufficient for the current canonical training runner.
Preserve valid discovery 507/507, 60 candle checkpoints, acquisition, and Gold 7/7.

Do not rewrite historical manifests to bypass checksums. Resolve and verify any legacy Silver/daily
input references before training. If source-state paths remain unresolved, stop the resume gate
and prepare a reviewed, hash-preserving migration mapping. Never reacquire or recompute valid work
just because its original machine path differs.

Expected Gold: dataset `gold-phase7-0cbf2910e8d96c9d19826598`, 138 Parquet partitions,
50,352,548 rows. 139 total dataset files may include the manifest. Keep generated reports outside
the dataset directory so file-count validation remains meaningful.

## 4. Validate Gold

These commands are read-only against migrated research data. The validator must not be pointed at
any August/holdout dataset. The expected Gold ends strictly before July 1.

```bash
mkdir -p "$PHASE7_REPORT_ROOT"
export PHASE7_GOLD_VALIDATION_REPORT="$PHASE7_REPORT_ROOT/gold-byte-validation.json"
uv run python -m scripts.validate_phase7_gold \
  --gold-root "$PHASE7_GOLD_ROOT" --output "$PHASE7_GOLD_VALIDATION_REPORT"
```

Require status PASS with `partition_hashes_verified=true`. A hash-skipped report is incomplete and
preflight rejects it. Output JSON is immutable; use a new report filename after a failed/stale run.
Review schema/native feature order, targets, horizons, Core20/HNT, duplicates, NaN/Inf counts,
UTC timing, cutoff, cross-sectional scope and locked holdout metadata. Gold NaNs are audited;
finite filtering and fold-bound context remain part of prepared matrix construction.

## 5. Preflight and full Linux verification

First perform software-only verification, with approved writable output roots present.
This entrypoint does not scan Gold or fit a GPU/backend smoke; the full suite has tiny
synthetic CPU tests. It requires all five Bash tests to execute, plus lint/format/lock/compile.

```bash
uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" \
  --output-root "$PWD/.pytest-linux-verification"
# Later, only after Gold validation and explicit synthetic backend-smoke authorization:
uv run python -m crypto_ai.phase7.preflight \
  --config configs/phase7/research_core20_primary_v1.toml \
  --gold-validation-report "$PHASE7_GOLD_VALIDATION_REPORT"
uv run pytest -q -o cache_dir=.pytest-lightning-cache --basetemp .pytest-lightning-run
uv run ruff check src/crypto_ai scripts tests
uv run ruff format --check src/crypto_ai scripts tests
git diff --check
```

All software failures must be resolved. The five Bash rotation tests skipped on Windows must
execute on Linux. Preflight's default smoke test is synthetic; skipping it leaves NOT_READY.
Check canonical stage artifact hashes/configuration identities, source digest and holdout flags.
Completed top-level training checkpoints require scientific stage identity; old missing identity
requires per-model review rather than a blind stage-level skip.

## 6. GPU smoke, preparation and CPU/GPU comparison

```bash
uv run python -m scripts.benchmark_phase7_backend --backend cuda
uv run python -m scripts.benchmark_phase7_preparation --rows 20000 --features 109
uv run python -m scripts.benchmark_phase7_backend --backend cuda --compare-cpu
```

The last command emits REVIEW_REQUIRED without explicit tolerances; successful computation
alone is not equivalence. For prediction-only assessment, add
`--tolerances /reviewed/operator-approved-limits.json` with all required keys documented in
[the hardening report](PHASE7A_PRE_LIGHTNING_HARDENING.md). Partial limits do not authorize
PASS. Threshold/no-trade policy equivalence needs separate review. GPU fit must be attested
by native fitted-backend plus independent live PID/GPU UUID/VRAM evidence; invisible evidence
fails closed without CPU retry. These commands are future-only, not executed by local hardening.

These utilities use synthetic data only. GPU smoke must fit successfully on the requested backend;
there is no CPU fallback. Record LightGBM/build/backend/GPU/driver information and elapsed time.
The CPU/GPU utility reports metrics and prediction differences; execution PASS is not equivalence
approval. The owner must review acceptable scientific differences. CPU/GPU checkpoints cannot be
interchanged automatically.

Review host RSS/available RAM and L4 VRAM. The small preparation benchmark establishes exact
value/order preservation, not full Fold-1 feasibility. Profile the real approved fold preparation
boundary separately: scan/year pruning, context rebinding, purge/slicing, finite filter, conversion,
cache publication and verified cached reload. Prove cached/uncached rows/features/targets/order and
predictions equivalent, and measure peak host memory/disk. No laptop/full-shape run is authorized.

## 7. Cache visibility and maintenance

```bash
uv run python -m scripts.manage_phase7_cache --cache-root "$PHASE7_CACHE_ROOT"
```

Default `auto` loads valid entries and rebuilds missing/invalid ones safely. `read_only` fails on any
miss/corruption. `rebuild` is an explicit replacement; `disabled` creates no durable matrix cache.
The optional capacity cap admits a conservative incoming estimate before construction and checks
exact bytes at publication; it never evicts entries automatically. Temporary
and quarantine bytes remain visible. Investigate stale locks; do not remove one while a writer runs.

For owner-directed cleanup, stop all workers and supply **all** active reference roots, including
the explicit report root. Use only exact unreferenced cache IDs chosen after inspecting the report:

```bash
# Permanently removes only the explicitly named unreferenced entry:
# uv run python -m scripts.manage_phase7_cache --cache-root "$PHASE7_CACHE_ROOT" \
#   --checkpoint-root "$PHASE7_CHECKPOINT_ROOT" \
#   --artifact-root "$PHASE7_ARTIFACT_ROOT" --artifact-root "$PHASE7_REPORT_ROOT" \
#   --offline --remove EXACT_64_HEX_CACHE_ID
```

Unreadable JSON or any referenced ID blocks removal. This is offline local maintenance, not a
distributed process monitor. No automatic LRU is implemented for Phase 7A.

## 8. One canonical model and subsequent authorization

After the previous gates, obtain fresh owner authorization for **one canonical Fold-1 model** with
a cost/deadline contract. Preserve exact fold rows, parameters, seeds, features and weights. Use a
reviewed isolated benchmark harness selecting the first canonical fold and a single existing G0
A6 specification; keep benchmark outputs distinct from canonical completion/qualification records.
The isolated production-package selector now exists. This command only prints a plan:

```bash
uv run python -m crypto_ai.phase7.benchmark_one_spec \
  --spec-id architecture-G0-A6-60m-raw \
  --output-root /persistent/crypto2-benchmark-isolated
```

Only separately owner-authorized `--execute`, after all target-host gates, may fit. Outputs are
BENCHMARK_ONLY under a separate run/checkpoint identity, with no canonical fold/run completion.
Unknown/deferred IDs and overlapping protected roots fail closed. Do not use `--canary`
as a substitute: its existing meaning remains the **entire 48-spec Fold-1 canary**.
See [pre-Lightning finalization](PHASE7A_PRE_LIGHTNING_FINALIZATION.md) for exact scope and blockers.

Record preparation/cache-hit time, model fit/best iteration, calibration/test stages, total runtime,
host RAM/VRAM, disk, and cost. Review the projected 48-spec cost with the owner. Only then may the
owner separately authorize all 48 Fold-1 specifications; folds 2–16 require their own decision.
Any later training invocation must explicitly set `PHASE7_ALLOW_CLOUD_RESEARCH=1` under that
contract. The Lightning entrypoint performs preflight before delegating to canonical training.
No production training command is executed or authorized by this runbook.

## Completion status of this remediation

| Gate | Current state |
| --- | --- |
| Local Windows software tests | See current pre-Lightning finalization gate; historical remediation gate was 665 passed, 5 Windows-only skips |
| Ruff/format | PASS |
| Lightning portability tooling | Prepared; target-host validation pending |
| Linux full suite/Bash operations | NOT RUN |
| L4 CUDA smoke/equivalence | NOT RUN; GPU_READY=NEEDS_LIGHTNING_TEST |
| Actual Gold byte validation | NOT RUN; BASIC GCS BACKUP COMPLETE |
| Real Fold-1 preparation/resources | Unmeasured |
| Production training | TRAINING_READY=NO; project on hold |
| July/August | July unused; August LOCKED_UNUSED |

Next safe action: owner reviews the remediation, then authorizes the migration/verification phase
with a fresh resource contract. Keep training stopped until all remaining gates are reviewed.

## Pre-Lightning finalization clarification (2026-10-03)

Canonical enumeration is unchanged: 48 primary A6 + 6 deferred ablations + 4 deferred HTF = 58.
Use `uv run python -m crypto_ai.phase7.benchmark_one_spec --enumerate` to print all fields/counts
without fitting. The historical v1.9 freeze stays byte-identical; current source identity is a
separate 44-file scientific manifest. The launcher imports production code; installed/editable
environment plus reviewed repository/configs are required. `python -m crypto_ai.phase7.lightning`
is the production-module entrypoint; the old script remains a compatibility launcher.

Gold validation now requires producer-derived 109 features / 130 physical columns. Regenerate
the validation report on the actual authorized Linux copy; a historical native-only PASS is not
sufficient. Structural one-horizon/key release is tested, not a measured production RAM bound.
Model/report fsync/order/binding are improved; model-only orphan recovery, conflicting-process
run leases and Linux fault qualification remain pending. GPU comparison execution PASS is still
not numerical equivalence approval. No target-host readiness or training authorization is implied.

## Final local hardening clarification (2026-10-03)

The preceding clarification describes the earlier finalization state. Current local lease,
state-machine/reconciliation, telemetry/resource admission and GPU policy/attestation tooling
are implemented and tested; consult [PHASE7A_PRE_LIGHTNING_HARDENING.md](PHASE7A_PRE_LIGHTNING_HARDENING.md).
Scientific manifest is now 46 files; execution manifest 15; historical freeze unchanged.
Use lease inspection/recovery, never delete guard files or steal by age. Model-only artifacts
are preserved for owner decision. Cleanup `--dry-run` requires all production AND benchmark
reference roots for meaningful candidate sizing. No actual cleanup occurred.
Real Linux/crash/concurrency, Gold-byte, preparation RSS/disk, GPU smoke/equivalence and
one-model benchmark gates remain NOT RUN. TRAINING_READY=NO; review the pushed branch
before any fresh paid resource/verification/migration authorization.
