#!/usr/bin/env bash
# RUN ON THE OWNER'S MAC. ADDED BY CLAUDE (2026-11-14).
# Pulls results (models, reports, logs, evidence incl. the 768-run ledger, model hash registry)
# from the pod into ~/Crypto2Results/phase7a-runpod/. Never pulls the dataset or prepared caches,
# never deletes anything on the Mac (no --delete), resumable, then verifies every model SHA-256
# against the ledger. Safe to run repeatedly while training continues.
#   POD=root@<public-ip> PORT=<ssh-port> KEY=~/.ssh/id_ed25519 bash mac_pull_results.sh
set -euo pipefail
: "${POD:?}"; : "${PORT:?}"; KEY="${KEY:-$HOME/.ssh/id_ed25519}"
SRC="${SRC:-/workspace/crypto2run}"; DEST="${DEST:-$HOME/Crypto2Results/phase7a-runpod}"
mkdir -p "$DEST"
rsync -a --partial -e "ssh -p $PORT -i $KEY -o ServerAliveInterval=30" \
  --exclude 'prepared_cache/' --exclude 'tmp/' --exclude '*.part' \
  "$POD:$SRC/" "$DEST/"
python3 - "$DEST" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]); ledger = json.loads((root / "evidence/study_ledger.json").read_text())
want = {r["model_sha256"] for r in ledger["runs"].values() if r["status"] == "COMPLETE_VERIFIED"}
have = {hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob("out/*/model/**/model.joblib")}
missing = want - have
print(f"verified runs in ledger: {len(want)}; model files matched on Mac: {len(want & have)}")
sys.exit(1 if missing else 0)
PY
