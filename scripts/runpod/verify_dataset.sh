#!/usr/bin/env bash
# RUN ON THE POD after the transfer. ADDED BY CLAUDE (2026-11-14).
# 1) size + SHA-256 of all 2,777 files against the COMMITTED manifest (fails on any difference);
# 2) the production byte-level Gold validation, ONCE per pod session, recorded as evidence;
# 3) identity summary (preparation/scientific/control digests) for comparison with the Mac/VM.
# No training, no model fit, no download.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$REPO"
source scripts/runpod/runpod_env.sh
E="$CRYPTO2_LOCAL/evidence"
uv run python scripts/cloud/transfer_set.py verify --root "$CRYPTO2_STAGE" --record "$E/transfer_verification.json"
uv run python - <<'PY'
import json, os
d = json.load(open(os.environ["CRYPTO2_LOCAL"] + "/evidence/transfer_verification.json"))
assert d["status"] == "VERIFIED" and d["files"] == 2777, d
print("DATASET VERIFIED:", d["files"], "files", d["bytes"], "bytes")
PY
uv run python scripts/cloud/run_measured.py --output "$E/gold_validation_measured.json" --disk-path "$VOL" --min-free-gb 5 -- \
  uv run python scripts/validate_phase7_gold.py --gold-root "$PHASE7_GOLD_ROOT" \
    --output "$E/gold_validation_report.json" > "$E/gold_validation.out"
GOLD_MANIFEST=$(uv run python -c "from pathlib import Path;import os;from crypto_ai.phase7.gold_validation import locate_gold_manifest;print(locate_gold_manifest(Path(os.environ['PHASE7_GOLD_ROOT'])))")
# Optional --expect: place a previously recorded identity_summary (same commit) at the path below
# to require an exact cross-host match; the setup gate already checks the freeze identities.
EXPECT=(); [ -f "$E/identity_summary_claude_vm.json" ] && EXPECT=(--expect "$E/identity_summary_claude_vm.json")
uv run python -m crypto_ai.phase7.identity_summary --gold-manifest "$GOLD_MANIFEST" \
  --sidecar "$PHASE7_FEATURE_CONTEXT_SIDECAR" "${EXPECT[@]}" > "$E/identity_summary.json"
echo "VERIFIED: dataset, Gold and identities recorded under $E (nothing trained)"
