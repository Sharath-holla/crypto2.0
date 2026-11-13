# Cloud training runbook — Phase 7A Core20 on the Claude Code VM

Branch `experiment/phase7-cloud-training-prep` (based on `experiment/phase7-low-memory-training`).
Original research branch `fix/phase7-final-architecture-repair-20261106` is untouched.

**Nothing in this file has been executed with real data. Every stage waits for the owner's
explicit message. Nothing is scheduled.** Stop at the first failure; never work around a guard.

Research contract held fixed: Core20 (all 20 symbols, point-in-time eligibility per fold), the
109 A6 features, `multiasset_targets_v2` 15/30/60/120 m, G0/C0/P0/H0 LightGBM with unchanged
hyper-parameters, 16 rolling folds, actual-label purge, 120-minute embargo, Validation / Cal-A /
Cal-B / frozen TEST, cost-aware `NO_TRADE`, July 2026 unused, August `LOCKED_UNUSED`.
First authorized specification: `architecture-G0-A6-60m-raw`, Fold 0, CORE, CPU, one worker.

Conventions: `E=$CRYPTO2_LOCAL/evidence` after `source scripts/cloud/session_env.sh`.

---

## Stage 0 — Session setup (no data, no training)

```bash
bash scripts/cloud/setup_session.sh
```

```bash
source scripts/cloud/session_env.sh && E="$CRYPTO2_LOCAL/evidence"
```

Expected: freeze drift tests pass (v2 identities), equivalence tests pass with fitting blocked,
budget `fits: true`.

## Stage A — Owner approvals (Claude asks; the owner answers in chat)

The owner states, in their own words:

1. Approve the dataset transfer (2,777 files / 10,998,003,736 B) and the estimated charges
   (storage ≈ USD 0.22–0.26/month, ≈ USD 1.32–2.53 egress per VM download).
2. UTC stop deadline (e.g. `2026-11-14T18:00:00Z`).
3. Cost ceiling and currency (e.g. `5 USD`).
4. Source version: `experiment/phase7-cloud-training-prep` @ the commit in the final report,
   freeze `phase7a_low_memory_experiment_freeze_v2`.
5. Resource-policy exception: run under `PHASE7_MEMORY_PROFILE=low_memory` (floors ≥ 13 GiB
   effective RAM, ≥ 4 CPUs, free disk) instead of the 64 GiB standard floor, with
   `PHASE7_STAGING_DAYS=30`.

Claude never invents these values. Training (Stage D) needs a SEPARATE later approval.

## Stage B — Dataset transfer

Mac (owner): `TRANSFER_GUIDE.md` steps 1–4 (dry run, upload, access, token into the card).

VM (Claude):

```bash
uv run python scripts/cloud/transfer_set.py plan --root "$CRYPTO2_STAGE"
```

```bash
uv run python scripts/cloud/transfer_set.py fetch --root "$CRYPTO2_STAGE" --bucket crypto-ai-data-83921 --prefix phase7-transfer-20261113 --execute
```

```bash
uv run python scripts/cloud/transfer_set.py verify --root "$CRYPTO2_STAGE" --record "$E/transfer_verification.json"
```

```bash
uv run python scripts/closure/verify_gold_hashes_readonly.py --gold-dataset-dir "$PHASE7_GOLD_ROOT/gold-phase7-0cbf2910e8d96c9d19826598" --output "$E/gold_hash_verification.json"
```

```bash
uv run python -m crypto_ai.phase7.identity_summary --gold-manifest "$PHASE7_GOLD_ROOT/gold-phase7-0cbf2910e8d96c9d19826598/manifest.json" --sidecar "$PHASE7_FEATURE_CONTEXT_SIDECAR" | tee "$E/identity_summary.json"
```

Required: `VERIFIED` (2,777 files), Gold hashes pass, `GOLD_MANIFEST_SHA = a1420277…e2e711`,
`SIDECAR_SHA = ea5f25a2…048`. (`PREPARATION_DIGEST` and `SCIENTIFIC_SOURCE_DIGEST` are the
v2-freeze values, not the November handoff values, because the source changed by design.)

```bash
uv run python -m crypto_ai.phase7.low_memory_disk budget --path /home/user --fold-rows 4922887 --occupied staged_data="$CRYPTO2_STAGE"
```

## Stage C — Prepare-only validation (no model fit)

Print the binding, owner reads it, then write it with `--confirm` (owner's values only):

```bash
uv run python scripts/cloud/write_owner_approval.py --mode prepare --owner "<owner>" --deadline "<UTC>" --cost-ceiling <amount> --currency <CUR> --output "$E/approval-prepare.json"
```

Canonical prepare-only run (one spec, Fold 0; builds and publishes ONE prepared cache, fits
nothing), with memory/disk measured and a hard stop below 2 GB free:

```bash
PHASE7_ALLOW_CLOUD_RESEARCH=1 PHASE7_CACHE_MODE=rebuild PHASE7_OWNER_APPROVAL_FILE="$E/approval-prepare.json" PHASE7_UNCACHED_DIGEST_FILE="$E/uncached_digest.json" uv run python scripts/cloud/run_measured.py --output "$E/prepare_measured.json" --disk-path /home/user --min-free-gb 2 -- uv run python -m crypto_ai.phase7.benchmark_one_spec --spec-id architecture-G0-A6-60m-raw --output-root "$CRYPTO2_LOCAL/out" --execute --prepare-only
```

Cached-versus-uncached qualification (fresh process, read-only reload; also checks chronology,
purge, embargo, research cutoff, locked holdout and symbol eligibility on the reloaded data):

```bash
uv run python -m crypto_ai.phase7.low_memory_validation --uncached-digest "$E/uncached_digest.json" --cache-root "$PHASE7_CACHE_ROOT" --gold-manifest "$PHASE7_GOLD_ROOT/gold-phase7-0cbf2910e8d96c9d19826598/manifest.json" --sidecar "$PHASE7_FEATURE_CONTEXT_SIDECAR" --resource-evidence "$E/prepare_measured.json" --output "$E/low_memory_validation.json"
```

```bash
sha256sum "$E/low_memory_validation.json" | tee "$E/low_memory_validation.sha256"
```

Required: `status: VALIDATED`, `differences: []`, `chronology_and_isolation_checks.all_passed:
true`, peak anon below ~11 GiB, min free disk ≥ 2 GB. Report these to the owner and STOP.

## Stage D — First real training (ONLY after a new explicit owner authorization)

```bash
uv run python scripts/cloud/write_owner_approval.py --mode train --owner "<owner>" --deadline "<UTC>" --cost-ceiling <amount> --currency <CUR> --output "$E/approval-train.json"
```

(The binding includes `low_memory_validation_sha256`; the owner reads it before `--confirm`.)

```bash
PHASE7_ALLOW_CLOUD_RESEARCH=1 PHASE7_CACHE_MODE=read_only PHASE7_OWNER_APPROVAL_FILE="$E/approval-train.json" PHASE7_LOW_MEMORY_VALIDATION_FILE="$E/low_memory_validation.json" uv run python scripts/cloud/run_measured.py --output "$E/train_measured.json" --disk-path /home/user --min-free-gb 2 -- uv run python -m crypto_ai.phase7.benchmark_one_spec --spec-id architecture-G0-A6-60m-raw --output-root "$CRYPTO2_LOCAL/out" --execute
```

This runs the canonical protocol for ONE spec: preflight (includes the small backend smoke fit),
fit on TRAIN with early stopping on Validation, calibration on Cal-A, thresholds on Cal-B, and
the frozen-identity TEST evaluation defined by the protocol. The August holdout is never read.

Reload and inference check (no fit):

```bash
uv run python scripts/cloud/verify_model_reload.py --model "$(find "$CRYPTO2_LOCAL/out" -name model.joblib | head -1)" --cache-root "$PHASE7_CACHE_ROOT" --output "$E/model_reload.json"
```

Persist to the PRIVATE bucket (the GitHub repository is public):

```bash
uv run python -m crypto_ai.phase7.run_persistence export --source out="$CRYPTO2_LOCAL/out" --source logs="$PHASE7_LOG_ROOT" --source evidence="$E" --source registry="$PHASE7_MODEL_HASH_REGISTRY" --destination "$CRYPTO2_LOCAL/persisted/fold0-g0" --execute
```

```bash
uv run python scripts/cloud/gcs_results.py push --source "$CRYPTO2_LOCAL/persisted/fold0-g0" --bucket crypto-ai-data-83921 --prefix phase7-results/fold0-g0 --execute
```

Owner retrieval on the Mac:

```bash
gcloud storage cp --recursive gs://crypto-ai-data-83921/phase7-results/fold0-g0 /Users/cortex/Crypto2Data/cloud-results/
```

## Stage E — Remaining specifications and folds (separate authorization each time)

The current admission permits ONE CPU smoke spec on Fold 0 (`FULL_GRID_NOT_AUTHORIZED`,
`OWNER_SCOPE_REFUSED` otherwise). Extending beyond it requires an owner-approved change to the
admission scope (a new freeze version), then, per durable cache key (fold × horizon × target,
6 specifications each): budget → prepare (staged) → qualify → train its specifications one at a
time → persist → `low_memory_disk release` the cache after all of its reports are terminal.
Estimated total for 48 specs × 16 folds: ~55–110 compute hours (estimate), across many sessions.

## Guards that must never be bypassed

64 GiB standard floor (default profile) · owner approval bound to exact identities · validation
record bound to current source · Gold manifest checksum of every partition · holdout lock ·
one worker · isolated output root · no fit in prepare-only · no automatic resume.
