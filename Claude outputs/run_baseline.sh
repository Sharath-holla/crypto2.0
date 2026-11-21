#!/usr/bin/env bash
# Written by Claude: read-only baseline (no training, no data changes, no network). Output: baseline_results.txt
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
PY=".venv/bin/python"
OUT="Claude outputs/baseline_results.txt"
{
  echo "== git"; git rev-parse --short HEAD; git status --short
  echo "== python"; $PY --version; $PY -c "import lightgbm, pyarrow, numpy; print('lightgbm', lightgbm.__version__, 'pyarrow', pyarrow.__version__)"
  echo "== pytest"; $PY -m pytest -q --no-header -p no:cacheprovider 2>&1 | tail -60
  echo "== ruff check"; $PY -m ruff check . 2>&1 | tail -30
  echo "== ruff format --check"; $PY -m ruff format --check . 2>&1 | tail -15
  echo "== verify_linux"; $PY -m crypto_ai.phase7.verify_linux --repository "$PWD" --output-root "$PWD/.pytest-linux-verification" 2>&1 | tail -30
  echo "== done"
} > "$OUT" 2>&1
echo "Finished. Results saved to: $OUT"
