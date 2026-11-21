#!/usr/bin/env bash
# Written by Claude (2026-11-06). A visible helper that lets Claude run a SHORT ALLOWLIST of commands in
# this repo, using the repo's own .venv (uv). It replaces the older pytest/ruff-only runner and adds the
# read-only research tools needed to close the Phase 7 smoke gates. It watches
# "Claude outputs/jobs/request.txt" (one line: [#nonce] command args), runs ONE allowed command and writes
# "Claude outputs/jobs/result.txt" (tail) plus a full log in "Claude outputs/jobs/logs/".
# Allowed: pytest | ruff-check | ruff-format-check | ruff-format | uv-sync | pymod <module> <args> |
#          pyscript scripts/closure/<tracked file>.py <args>
# pymod modules are an allowlist below. NO training: any --execute without --prepare-only is refused.
# No network use except `uv-sync`. Close this window (or Ctrl+C) at any time to stop it.
cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export CRYPTO_AI_RESEARCH_MODE=1
PY=".venv/bin/python"
JOBS="Claude outputs/jobs"
mkdir -p "$JOBS/logs"
ALLOWED_MODULES=" crypto_ai.phase7.feature_census crypto_ai.phase7.preflight crypto_ai.phase7.resource_estimate crypto_ai.phase7.verify_linux crypto_ai.phase7.benchmark_one_spec crypto_ai.phase7.readiness crypto_ai.phase7.gold_verification crypto_ai.phase7.selection_protocol_cli crypto_ai.phase7.cache_qualification "
echo "Claude SCIENCE runner is waiting for jobs."
echo "Allowed: pytest, ruff-*, uv-sync, pymod <allowlisted module>, pyscript scripts/closure/*.py. No training."
echo "Leave this window open. Press Ctrl+C to stop."
while true; do
  if [ -f "$JOBS/request.txt" ]; then
    LINE="$(head -n 1 "$JOBS/request.txt")"
    rm -f "$JOBS/request.txt"
    set -- $LINE
    NONCE=""
    case "$1" in "#"*) NONCE="$1"; shift ;; esac
    CMD="$1"; shift
    LOG="$JOBS/logs/$(date +%Y%m%d-%H%M%S)-$CMD.log"
    echo "[$(date +%T)] running: $NONCE $CMD $*"
    {
      echo "== $NONCE $CMD $*  ($(date))"
      case "$CMD" in
        pytest)             $PY -m pytest "$@" -p no:cacheprovider --no-header 2>&1 ;;
        ruff-check)         $PY -m ruff check "$@" 2>&1 ;;
        ruff-format-check)  $PY -m ruff format --check "$@" 2>&1 ;;
        ruff-format)        $PY -m ruff format "$@" 2>&1 ;;
        uv-sync)            uv sync --locked --extra dev 2>&1 ;;
        pymod)
          MOD="$1"; shift
          case "$ALLOWED_MODULES" in
            *" $MOD "*)
              case " $* " in
                *" --execute "*) case " $* " in *" --prepare-only "*) $PY -m "$MOD" "$@" 2>&1 ;; *) echo "REFUSED: --execute without --prepare-only (no training)" ;; esac ;;
                *) $PY -m "$MOD" "$@" 2>&1 ;;
              esac ;;
            *) echo "REFUSED: module not allowed: $MOD" ;;
          esac ;;
        pyscript)
          SCR="$1"; shift
          case "$SCR" in
            scripts/closure/*.py)
              if git ls-files --error-unmatch "$SCR" >/dev/null 2>&1 && [ -z "$(git status --porcelain -- "$SCR")" ]; then
                $PY "$SCR" "$@" 2>&1
              else echo "REFUSED: script must be tracked AND committed unchanged: $SCR"; fi ;;
            *) echo "REFUSED: only scripts/closure/*.py allowed" ;;
          esac ;;
        *) echo "REFUSED: command not allowed: $CMD" ;;
      esac
      echo "== finished (exit shown above if any)"
    } > "$LOG" 2>&1
    { head -n 1 "$LOG"; tail -n 220 "$LOG"; echo "(full log: $LOG, $(wc -l < "$LOG") lines)"; } > "$JOBS/result.tmp"
    mv "$JOBS/result.tmp" "$JOBS/result.txt"
    echo "[$(date +%T)] done"
  fi
  sleep 2
done
