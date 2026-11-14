#!/usr/bin/env bash
# RUN ON THE OWNER'S MAC. ADDED BY CLAUDE (2026-11-14).
# Copies ONLY the 2,777 verified files (the committed manifest's file list) from the Mac staging
# folder to the RunPod volume over SSH (rsync). Resumable (--partial), never deletes anything on
# either side, never touches Binance. Re-running after an interruption continues where it stopped.
#   POD=root@<public-ip> PORT=<ssh-port> KEY=~/.ssh/id_ed25519 bash mac_send_dataset.sh
set -euo pipefail
: "${POD:?set POD=root@<pod public IP> from the RunPod Connect tab (Direct TCP)}"
: "${PORT:?set PORT=<external port mapped to :22>}"
KEY="${KEY:-$HOME/.ssh/id_ed25519}"
STAGE="${STAGE:-/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107}"
LIST="${LIST:-/Users/cortex/Crypto2Data/reports/combined-local-closure-20261108T073250Z/runpod_data_only_files.txt}"
DEST="${DEST:-/workspace/crypto2data/staging}"
[ -d "$STAGE" ] && [ -f "$LIST" ] || { echo "missing $STAGE or $LIST"; exit 1; }
echo "files listed: $(grep -c . "$LIST")   (expected 2777)"
SSH="ssh -p $PORT -i $KEY -o ServerAliveInterval=30 -o ServerAliveCountMax=6"
$SSH "$POD" "mkdir -p '$DEST'"
for attempt in 1 2 3 4 5 6; do
  # macOS ships an old rsync; `brew install rsync` gives --info=progress2. -a keeps the layout.
  if rsync -a --partial --partial-dir=.rsync-partial --files-from="$LIST" \
       --human-readable --stats -e "$SSH" "$STAGE/" "$POD:$DEST/"; then
    echo "TRANSFER COMPLETE (now run the SHA-256 verification on the pod)"; exit 0
  fi
  echo "rsync interrupted (attempt $attempt); retrying in $((attempt*30)) s"; sleep $((attempt*30))
done
echo "TRANSFER NOT COMPLETE after 6 attempts; re-run this script to resume"; exit 1
