#!/usr/bin/env bash
# Bounded rotation for the Phase 7 cloud run log.
#
# Usage: rotate_phase7_run_log.sh <log-path>
# Env:   PHASE7_LOG_ROTATE_MB  (default 512)  - rotate when the log exceeds MB
#        PHASE7_LOG_ROTATE_KEEP (default 2)   - gzipped generations to keep
#
# Safety properties:
#   - runs BEFORE the research worker starts, so there is a single writer and
#     no concurrent truncation race;
#   - skips entirely if a research worker is already running (guard against
#     rotating a live log out from under an open handle);
#   - never blocks or fails the caller: every failure path exits 0;
#   - the live log is moved aside atomically before compression, so no write
#     can be lost; if compression fails the original is restored.
set -u

log_path="${1:-}"
rotate_mb="${PHASE7_LOG_ROTATE_MB:-512}"
rotate_keep="${PHASE7_LOG_ROTATE_KEEP:-2}"

if [[ -z "${log_path}" || ! -f "${log_path}" ]]; then
  exit 0
fi
if pgrep -f '[c]rypto-ai phase7-research' >/dev/null 2>&1; then
  exit 0
fi

size_bytes="$(stat -c %s "${log_path}" 2>/dev/null || echo 0)"
threshold_bytes=$((rotate_mb * 1024 * 1024))
if [[ "${size_bytes}" -lt "${threshold_bytes}" ]]; then
  exit 0
fi

gzip_bin="gzip"
command -v pigz >/dev/null 2>&1 && gzip_bin="pigz"

# Shift generations down: .1.gz -> .2.gz -> ... -> .K.gz; drop the oldest.
gen=$((rotate_keep - 1))
while [[ "${gen}" -ge 1 ]]; do
  if [[ -f "${log_path}.${gen}.gz" ]]; then
    mv -f "${log_path}.${gen}.gz" "${log_path}.$((gen + 1)).gz" 2>/dev/null || true
  fi
  gen=$((gen - 1))
done
if [[ -f "${log_path}.1.gz" ]]; then
  rm -f "${log_path}.1.gz" 2>/dev/null || true
fi

temporary="${log_path}.rotate.$$"
if mv -f "${log_path}" "${temporary}" 2>/dev/null; then
  if ! "${gzip_bin}" -3 -c "${temporary}" > "${log_path}.1.gz" 2>/dev/null; then
    rm -f "${log_path}.1.gz" 2>/dev/null || true
    mv -f "${temporary}" "${log_path}" 2>/dev/null || true
  else
    rm -f "${temporary}" 2>/dev/null || true
  fi
fi
exit 0