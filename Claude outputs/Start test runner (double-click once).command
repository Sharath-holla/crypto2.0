#!/usr/bin/env bash
# Written by Claude (2026-11-02). A visible helper that lets Claude run ONLY pytest / ruff in this
# repo's own .venv. It watches "Claude outputs/jobs/request.txt", runs one allowed command, writes
# "Claude outputs/jobs/result.txt". No training, no network, no other commands. Close this window
# (or press Ctrl+C) at any time to stop it.
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
PY=".venv/bin/python"
JOBS="Claude outputs/jobs"
mkdir -p "$JOBS"
echo "Claude test runner is waiting for jobs. Allowed: pytest, ruff-check, ruff-format-check, ruff-format <paths>."
echo "Leave this window open. Press Ctrl+C to stop."
while true; do
  if [ -f "$JOBS/request.txt" ]; then
    LINE="$(head -n 1 "$JOBS/request.txt")"
    rm -f "$JOBS/request.txt"
    set -- $LINE
    CMD="$1"; shift
    echo "[$(date +%T)] running: $CMD $*"
    {
      echo "== $CMD $*  ($(date))"
      case "$CMD" in
        pytest)             $PY -m pytest "$@" -p no:cacheprovider --no-header 2>&1 | tail -150 ;;
        ruff-check)         $PY -m ruff check "$@" 2>&1 | tail -80 ;;
        ruff-format-check)  $PY -m ruff format --check "$@" 2>&1 | tail -40 ;;
        ruff-format)        $PY -m ruff format "$@" 2>&1 | tail -40 ;;
        *)                  echo "REFUSED: command not allowed: $CMD" ;;
      esac
      echo "== finished"
    } > "$JOBS/result.tmp" 2>&1
    mv "$JOBS/result.tmp" "$JOBS/result.txt"
    echo "[$(date +%T)] done"
  fi
  sleep 2
done
