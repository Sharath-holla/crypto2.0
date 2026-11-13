#!/usr/bin/env bash
# Least-privilege, read-only access for the Claude Code VM to ONE bucket prefix.
# ADDED BY CLAUDE (2026-11-13). DRY-RUN BY DEFAULT (prints the exact commands). --execute runs
# them; --cleanup removes the access and the service account afterwards. No key file is created:
# the VM receives a 1-hour impersonated access token that you paste only into the secure
# credential card (never chat).
set -euo pipefail
MODE="${1:-dry-run}"
PROJECT="${PROJECT:-crypto-ai-trading-506300}"
BUCKET_NAME="${BUCKET_NAME:-crypto-ai-data-83921}"
PREFIX="${PREFIX:-phase7-transfer-20261113}"
SA_NAME="crypto2-claude-reader"
SA="${SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
ME="$(gcloud config get-value account 2>/dev/null)"
CONDITION="expression=resource.name.startsWith(\"projects/_/buckets/${BUCKET_NAME}/objects/${PREFIX}/\"),title=phase7-transfer-read-only"
commands=(
  "gcloud iam service-accounts create $SA_NAME --project=$PROJECT --display-name=Crypto2-read-only-transfer"
  "gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME --member=serviceAccount:$SA --role=roles/storage.objectViewer --condition=$CONDITION"
  "gcloud iam service-accounts add-iam-policy-binding $SA --project=$PROJECT --member=user:$ME --role=roles/iam.serviceAccountTokenCreator"
)
case "$MODE" in
  dry-run)
    echo "uniform bucket-level access (must be true for the prefix condition):"
    gcloud storage buckets describe "gs://$BUCKET_NAME" --format="value(uniform_bucket_level_access)" || true
    printf '%s\n' "${commands[@]}"
    echo "Token for the credential card (1 hour, read-only, prefix only):"
    echo "gcloud auth print-access-token --impersonate-service-account=$SA" ;;
  --execute)
    for c in "${commands[@]}"; do echo "+ $c"; eval "$c"; done ;;
  --cleanup)
    gcloud iam service-accounts delete "$SA" --project="$PROJECT" --quiet
    echo "optional storage cleanup (stops storage charges):"
    echo "gcloud storage rm --recursive gs://$BUCKET_NAME/$PREFIX" ;;
  *) echo "usage: $0 [--execute|--cleanup]"; exit 2 ;;
esac
