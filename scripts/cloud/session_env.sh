# Source this file (do not execute): `source scripts/cloud/session_env.sh`
# ADDED BY CLAUDE (2026-11-13). Sets ONLY paths and execution profile for the Claude Code cloud VM.
# Values for the legacy roots are copied from trusted evidence
# (docs/reviews/evidence_final_closure/execution_20261106T143735Z/transfer_staging_final.json).
# It does NOT set PHASE7_ALLOW_CLOUD_RESEARCH, PHASE7_CACHE_MODE or PHASE7_OWNER_APPROVAL_FILE:
# each run step sets those explicitly, so sourcing this file can never start anything.
export CRYPTO2_STAGE="${CRYPTO2_STAGE:-/home/user/crypto2data/staging}"   # downloaded data set
export CRYPTO2_LOCAL="${CRYPTO2_LOCAL:-/home/user/crypto2run}"            # caches/outputs/logs
P="$CRYPTO2_STAGE/crypto2-persistent"
export PHASE7_DATA_ROOT="$P/data"
export PHASE7_GOLD_ROOT="$P/data/gold/phase7a_core20_primary_v1"
export PHASE7_ARTIFACT_ROOT="$P/phase7/artifacts"
export PHASE7_CHECKPOINT_ROOT="$P/phase7/checkpoints"
export PHASE7_LEGACY_DATA_ROOT=/home/nssharath123/crypto2.0/data
export PHASE7_LEGACY_GOLD_ROOT=/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1
export PHASE7_LEGACY_ARTIFACT_ROOT=/home/nssharath123/crypto2.0/local_artifacts/phase7
export PHASE7_FEATURE_CONTEXT_SIDECAR="$CRYPTO2_STAGE/feature_context_sidecar_v3/manifest.json"
export PHASE7_CACHE_ROOT="$CRYPTO2_LOCAL/prepared_cache"
export PHASE7_MODEL_ROOT="$CRYPTO2_LOCAL/models"
export PHASE7_REPORT_ROOT="$CRYPTO2_LOCAL/reports"
export PHASE7_LOG_ROOT="$CRYPTO2_LOCAL/logs"
export PHASE7_TEMP_ROOT="$CRYPTO2_LOCAL/tmp"
export PHASE7_MODEL_HASH_REGISTRY="$CRYPTO2_LOCAL/model_hash_registry"  # outside model dirs
export PHASE7_REQUIRE_MODEL_REGISTRY=1
export PHASE7_LGBM_DEVICE=cpu
export PHASE7_MODEL_PARALLELISM=1          # one worker, sequential specifications
export PHASE7_TOTAL_CPU_THREADS="$(nproc)"
export PHASE7_MIN_FREE_RAM_GIB=1           # per-stage live check; profile floors are separate
export PHASE7_MIN_FREE_DISK_GIB=2
export PHASE7_MEMORY_PROFILE=low_memory
export PHASE7_STAGING_DAYS="${PHASE7_STAGING_DAYS:-30}"
export CRYPTO_AI_RESEARCH_MODE=1
mkdir -p "$CRYPTO2_LOCAL"/{prepared_cache,models,reports,logs,tmp,out,evidence}
echo "Phase 7 cloud session paths set (profile=$PHASE7_MEMORY_PROFILE staging_days=$PHASE7_STAGING_DAYS)"
