#!/usr/bin/env bash
# One-time (and idempotent) RunPod pod setup. ADDED BY CLAUDE (2026-11-14).
# Installs tools and the LOCKED dependency set, then runs the Linux verification gate.
# It downloads no market data, starts no training and fits no model.
#   bash scripts/runpod/setup_pod.sh            (from the repository root on the volume)
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"; cd "$REPO"
source scripts/runpod/runpod_env.sh
echo "== host"; uname -m; nproc; free -g | sed -n 2p; df -h "$VOL" | tail -1
cat /sys/fs/cgroup/memory.max 2>/dev/null || cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || true
echo "== system packages"
command -v rsync >/dev/null && command -v tmux >/dev/null || { apt-get update -qq && apt-get install -y -qq rsync tmux time >/dev/null; }
command -v uv >/dev/null || { curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$HOME/.local/bin:$PATH"; }
echo "== branch/commit"; git branch --show-current; git log --oneline -1
[[ "$(git rev-parse --is-shallow-repository)" == "true" ]] && git fetch --unshallow origin || true
echo "== locked dependencies"; uv sync --locked --extra dev --python 3.12
echo "== Linux verification gate (lint + full test suite; fits blocked by the no-fit guard where marked)"
uv run ruff check . && uv run ruff format --check .
uv run pytest -q -p no:cacheprovider -x
uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" --output-root "$CRYPTO2_LOCAL/linux-verification"
echo "SETUP COMPLETE: nothing was downloaded or trained"
