#!/usr/bin/env bash
# Prepare a fresh Claude Code cloud session. ADDED BY CLAUDE (2026-11-13).
# Installs dependencies and VERIFIES; it downloads no market data and fits no model.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO"
echo "== branch/commit"; git branch --show-current; git log --oneline -1
[[ "$(git rev-parse --is-shallow-repository)" == "true" ]] && git fetch --unshallow origin || true
echo "== resources (container-aware)"
uname -m; nproc; free -g | sed -n 2p
cat /sys/fs/cgroup/memory.max 2>/dev/null || echo "cgroup memory.max: not exposed"
df -h / | tail -1
echo "== dependencies"
uv sync --locked --extra dev --python 3.12
echo "== freeze drift + low-memory/staging equivalence (model fitting blocked)"
uv run pytest -q -p no:cacheprovider -p experiments.phase7_low_memory.tools.no_fit_guard \
  -m "not model_fit" tests/phase7/test_low_memory_source_freeze.py \
  tests/phase7/test_low_memory_equivalence.py tests/phase7/test_low_memory_admission.py \
  tests/phase7/test_low_memory_disk.py tests/phase7/test_run_persistence.py \
  tests/operations/test_transfer_set.py
echo "== Fold-0 disk budget (data not yet downloaded)"
uv run python -m crypto_ai.phase7.low_memory_disk budget --path /home/user --fold-rows 4922887 \
  --data-bytes-pending 10998003736 --occupied repository="$REPO" || true
echo "SESSION READY FOR OWNER-APPROVED STEPS (nothing was downloaded or trained)"
