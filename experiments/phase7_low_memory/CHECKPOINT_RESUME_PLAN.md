# Checkpoint and resume plan

The VM is temporary. Completed work survives only if it is outside the VM: in your PRIVATE GCS
bucket (results) or reproducible from verified inputs (data in the same bucket, caches rebuilt
deterministically and checked against their recorded manifests).

> **The GitHub repository `Sharath-holla/crypto2.0` is PUBLIC** (verified 2026-11-13). Real-run
> outputs (models, metrics, reports, approvals, logs) must never be pushed there.
> `experiments/phase7_low_memory/runs/` is git-ignored. GitHub receives code, tests, documents and
> synthetic-data evidence only. If you make the repository private later, this rule can be
> relaxed by your decision, not by default.

## What already exists in the pipeline (unchanged)

| Mechanism | Where |
|---|---|
| Stage checkpoints bound to identity (config, Gold, universe, registry, source, backend, environment, control digests) | `artifacts.CheckpointStore`, `training_stage_resume_identity` |
| A spec is skipped on resume only if its checkpoint identity matches exactly | `_run_phase7_training_owned` (`resume=True` in `benchmark_one_spec`) |
| Atomic JSON/Parquet writes (temp + fsync + rename), refusal to overwrite different content | `artifacts.atomic_json`, `atomic_parquet` |
| Prepared cache: identity-keyed, CACHE_COMPLETE marker, per-file SHA-256, read-only reload validation | `prepared_cache.PreparedDataCache` |
| Model hash registry outside the artifact folder; `load_model` refuses unregistered/changed files | `model_registry` (`PHASE7_MODEL_HASH_REGISTRY`, `PHASE7_REQUIRE_MODEL_REGISTRY=1`) |
| Run lease (one writer), orphan model/report detection | `run_lease.owned_run`, `recovery.inspect_spec_artifacts` |

## Added for cloud sessions (2026-11-13)

| Need | Tool |
|---|---|
| Persist completed small artifacts outside the VM | `python -m crypto_ai.phase7.run_persistence export` → `$CRYPTO2_LOCAL/persisted/<run>/` + `PERSISTED_MANIFEST.json` (SHA-256 per file), then `scripts/cloud/gcs_results.py push` → `gs://crypto-ai-data-83921/phase7-results/<run>/` (create-only, MD5-verified) |
| Restore into a new session | `gcs_results.py pull` (SHA-256 verified) then `run_persistence restore` (verifies every SHA-256, refuses to overwrite different files) |
| See what is complete | `run_persistence status --run-root ...` |
| Transfer progress / verified dataset identity | `.transfer-state/progress.jsonl`, `evidence/transfer_verification.json` |
| Cached-vs-uncached qualification record (bound to source digests) | `evidence/low_memory_validation.json` + its SHA-256 |
| Resource evidence per step | `evidence/*_measured.json` (`scripts/cloud/run_measured.py`) |
| Cache release receipts (manifest kept after deletion) | `evidence/cache-receipts/*.release.json` (`low_memory_disk release`) |

What is persisted per run (to the private bucket): experiment/run identity, execution manifests (source commit, freeze
digests, configuration hash, Gold manifest SHA, admission record incl. memory profile and
staging days), checkpoints, reports (metrics, calibration, thresholds, TEST evaluation produced
by the canonical protocol), `model.joblib` + model hash registry, training-metric logs,
approvals, validation record, measured resources. NOT persisted: market data, prepared caches,
spill files, matrices (rebuilt from verified data; their manifests are in the receipts).

## Manual resume in a new cloud session

```bash
git fetch origin experiment/phase7-cloud-training-prep && git checkout experiment/phase7-cloud-training-prep && git pull --ff-only
```

```bash
bash scripts/cloud/setup_session.sh
```

```bash
source scripts/cloud/session_env.sh
```

Pull the persisted run from the private bucket (needs the owner's 1-hour token in the credential
card), then restore it (dry run first, then add `--execute`):

```bash
uv run python scripts/cloud/gcs_results.py pull --bucket crypto-ai-data-83921 --prefix phase7-results/fold0-g0 --destination "$CRYPTO2_LOCAL/persisted/fold0-g0" --execute
```

```bash
uv run python -m crypto_ai.phase7.run_persistence restore --source "$CRYPTO2_LOCAL/persisted/fold0-g0" --target out="$CRYPTO2_LOCAL/out" --target logs="$PHASE7_LOG_ROOT" --target evidence="$CRYPTO2_LOCAL/evidence" --target registry="$PHASE7_MODEL_HASH_REGISTRY"
```

Re-download and verify data (owner token again; skips nothing that is missing, re-verifies all):
see `TRANSFER_GUIDE.md`. Then re-run the SAME canonical command; completed specifications are
skipped because their checkpoint identities match, and a cache is reused only if its identity
and file hashes match.

Rules: never treat a checkpoint as valid unless its recorded identities equal the current ones
(the pipeline enforces this); never schedule an automatic resume; each new run step needs the
owner's explicit instruction.
