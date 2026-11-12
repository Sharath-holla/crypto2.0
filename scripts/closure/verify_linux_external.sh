#!/usr/bin/env bash
# Software verification only, inside a fresh extracted source snapshot on existing Linux.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo "Linux/x86_64 required; no host result may substitute for Linux verification." >&2
  exit 2
fi
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo"
# Drop inherited research/admission/resource/data-path settings, without printing their values.
for variable in ${!PHASE7_@}; do unset "$variable"; done
export PHASE7_LGBM_DEVICE=cpu
command -v uv >/dev/null
uv --version
python3 --version
uname -a
uv sync --locked --extra dev --python 3.12
if [[ ! -e .git ]]; then
  uv run python -m crypto_ai.phase7.source_freeze --repository "$repo"
fi
uv run python -m crypto_ai.phase7.filesystem_probe --root "${1:-$repo/.linux-filesystem-probe}"
mkdir -p .linux-closure-logs
uv run pytest -q 2>&1 | tee .linux-closure-logs/pytest.log
uv run ruff check . 2>&1 | tee .linux-closure-logs/ruff.log
uv run ruff format --check . 2>&1 | tee .linux-closure-logs/format.log
# These are empty verification output directories, never market data or a prepared cache build.
uv run python - <<'PY'
from pathlib import Path
from crypto_ai.phase7.config import load_phase7_config
from crypto_ai.phase7.runtime import RuntimePaths
root = Path.cwd().resolve()
config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
paths = RuntimePaths.resolve(config.paths)
for name in ("artifact_root", "cache_root", "checkpoint_root", "model_root", "report_root", "log_root"):
    path = getattr(paths, name).resolve()
    if not path.is_relative_to(root) or path.is_relative_to(paths.data_root):
        raise ValueError("verification output is not isolated inside this source snapshot")
    path.mkdir(parents=True, exist_ok=True)
PY
uv run python -m crypto_ai.phase7.verify_linux \
  --repository "$repo" --output-root "$repo/.pytest-linux-verification" \
  2>&1 | tee .linux-closure-logs/verify_linux.log
echo "Software verification completed. Training, cache preparation and holdout evaluation remain unauthorized."
