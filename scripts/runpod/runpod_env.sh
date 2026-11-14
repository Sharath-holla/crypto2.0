# Source this file on the RunPod pod (do not execute): `source scripts/runpod/runpod_env.sh`
# ADDED BY CLAUDE (2026-11-14). Paths + execution profile ONLY, mirroring scripts/cloud/session_env.sh
# (the profile that produced the six verified Fold-0 models) but rooted on the persistent volume.
# It never sets PHASE7_ALLOW_CLOUD_RESEARCH, PHASE7_CACHE_MODE or PHASE7_OWNER_APPROVAL_FILE: the
# runner sets those per step, so sourcing this file can never start anything.
export VOL="${VOL:-/workspace}"                                    # RunPod volume mount
export CRYPTO2_STAGE="${CRYPTO2_STAGE:-$VOL/crypto2data/staging}"  # the verified 2,777-file set
export CRYPTO2_LOCAL="${CRYPTO2_LOCAL:-$VOL/crypto2run}"           # caches/outputs/logs/evidence
export UV_CACHE_DIR="${UV_CACHE_DIR:-$VOL/.uv-cache}"              # survives pod restarts
P="$CRYPTO2_STAGE/crypto2-persistent"
export PHASE7_DATA_ROOT="$P/data"
export PHASE7_GOLD_ROOT="$P/data/gold/phase7a_core20_primary_v1"
export PHASE7_ARTIFACT_ROOT="$P/phase7/artifacts"
export PHASE7_CHECKPOINT_ROOT="$P/phase7/checkpoints"
# Legacy roots: identical values to the verified Claude Cloud runs (trusted evidence
# docs/reviews/evidence_final_closure/execution_20261106T143735Z/transfer_staging_final.json).
export PHASE7_LEGACY_DATA_ROOT=/home/nssharath123/crypto2.0/data
export PHASE7_LEGACY_GOLD_ROOT=/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1
export PHASE7_LEGACY_ARTIFACT_ROOT=/home/nssharath123/crypto2.0/local_artifacts/phase7
export PHASE7_FEATURE_CONTEXT_SIDECAR="$CRYPTO2_STAGE/feature_context_sidecar_v3/manifest.json"
export PHASE7_CACHE_ROOT="$CRYPTO2_LOCAL/prepared_cache"
export PHASE7_MODEL_ROOT="$CRYPTO2_LOCAL/models"
export PHASE7_REPORT_ROOT="$CRYPTO2_LOCAL/reports"
export PHASE7_LOG_ROOT="$CRYPTO2_LOCAL/logs"
export PHASE7_TEMP_ROOT="$CRYPTO2_LOCAL/tmp"
export PHASE7_MODEL_HASH_REGISTRY="$CRYPTO2_LOCAL/model_hash_registry"
export PHASE7_REQUIRE_MODEL_REGISTRY=1
export PHASE7_LGBM_DEVICE=cpu              # CPU only: the approval binding fixes backend=cpu
export PHASE7_MODEL_PARALLELISM=1          # per process; the runner adds cache-group workers
export PHASE7_TOTAL_CPU_THREADS="$(nproc)" # the runner divides this between workers
export PHASE7_MIN_FREE_RAM_GIB=2
export PHASE7_MIN_FREE_DISK_GIB=10
export PHASE7_MEMORY_PROFILE=low_memory    # the validated, output-identical profile (record ecd83e71)
export PHASE7_STAGING_DAYS="${PHASE7_STAGING_DAYS:-30}"
export PHASE7_GOLD_VALIDATION_REPORT="$CRYPTO2_LOCAL/evidence/gold_validation_report.json"
export PHASE7_LOW_MEMORY_VALIDATION_FILE="$CRYPTO2_LOCAL/evidence/low_memory_validation.json"
export CRYPTO_AI_RESEARCH_MODE=1
mkdir -p "$CRYPTO2_LOCAL"/{prepared_cache,models,reports,logs,tmp,out,evidence}
echo "RunPod Phase 7 paths set (volume=$VOL profile=$PHASE7_MEMORY_PROFILE cpus=$(nproc))"
