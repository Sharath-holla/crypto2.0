#!/usr/bin/env bash
set -euo pipefail
kit="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "STAGE bootstrap"
exec "${CRYPTO2_OPS_PYTHON:-python3}" "$kit/runpod_phase7_ops.py" bootstrap "$@"
