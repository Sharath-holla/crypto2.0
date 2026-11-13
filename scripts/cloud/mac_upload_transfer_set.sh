#!/usr/bin/env bash
# Mac -> private GCS upload of the verified Phase 7 data-only set (2,777 files / 10,998,003,736 B).
# ADDED BY CLAUDE (2026-11-13). DRY-RUN BY DEFAULT: without --execute nothing is created, uploaded
# or changed. Never deletes or modifies anything under the original Crypto2Data folders.
#
#   bash scripts/cloud/mac_upload_transfer_set.sh            # dry run: checks only
#   bash scripts/cloud/mac_upload_transfer_set.sh --execute  # hard-link mirror, verify, upload
set -euo pipefail
EXECUTE=0; [[ "${1:-}" == "--execute" ]] && EXECUTE=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGE="${STAGE:-/Users/cortex/Crypto2Data/reports/phase7-final-closure-20261106/runpod-transfer-20261107}"
LIST="${LIST:-/Users/cortex/Crypto2Data/reports/combined-local-closure-20261108T073250Z/runpod_data_only_files.txt}"
MIRROR="${MIRROR:-/Users/cortex/Crypto2Data/upload-fold0-20261113}"
BUCKET="${BUCKET:-gs://crypto-ai-data-83921}"
PREFIX="${PREFIX:-phase7-transfer-20261113}"
EXPECTED_LIST_SHA="5ebe6f7a60565afa4be6a6bd1d27855e9a3fec52959c94160cfe0277a01905b3"

echo "== 1. inputs"
[[ -d "$STAGE" ]] || { echo "missing staging root: $STAGE"; exit 2; }
[[ -f "$LIST" ]] || { echo "missing file list: $LIST"; exit 2; }
actual="$(shasum -a 256 "$LIST" | awk '{print $1}')"
[[ "$actual" == "$EXPECTED_LIST_SHA" ]] || { echo "FILE LIST SHA MISMATCH: $actual"; exit 3; }
echo "file list OK ($EXPECTED_LIST_SHA), $(grep -c . "$LIST") entries"
command -v gcloud >/dev/null || { echo "gcloud CLI not found"; exit 2; }
echo "gcloud account: $(gcloud config get-value account 2>/dev/null)"
echo "== 2. verify SOURCE files (size + SHA-256 of all 2,777; read-only)"
python3 "$REPO/scripts/cloud/transfer_set.py" verify --root "$STAGE"
if [[ $EXECUTE -eq 0 ]]; then
  echo "DRY RUN complete. Re-run with --execute to build the hard-link mirror and upload to:"
  echo "  $BUCKET/$PREFIX   (estimated storage ~USD 0.22-0.26/month; ingress free)"
  exit 0
fi
echo "== 3. hard-link mirror of exactly the listed files (no copy, originals untouched)"
mkdir -p "$MIRROR"
( cd "$STAGE" && cpio -pdl "$MIRROR" < "$LIST" ) 2>/dev/null
count="$(find "$MIRROR" -type f ! -name '.*' | wc -l | tr -d ' ')"
[[ "$count" == "2777" ]] || { echo "mirror has $count files, expected 2777"; exit 3; }
echo "== 4. upload (resumable: re-run this script to continue; gcloud checks CRC32C/MD5)"
gcloud storage rsync --recursive "$MIRROR" "$BUCKET/$PREFIX"
echo "== 5. remote object count"
remote="$(gcloud storage ls --recursive "$BUCKET/$PREFIX/**" | grep -vc '/$' || true)"
echo "remote objects: $remote (expected 2777)"
[[ "$remote" == "2777" ]] || { echo "REMOTE COUNT MISMATCH"; exit 3; }
echo "UPLOAD COMPLETE: $BUCKET/$PREFIX"
