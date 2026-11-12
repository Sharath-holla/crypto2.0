#!/usr/bin/env bash
# Portable helpers shared by the Phase 7 launchers. Source, do not execute.
# No host-specific absolute paths, no GNU-only flags required to run.

# Resolve the uv executable: validated PHASE7_UV_BIN first, otherwise PATH.
phase7_resolve_uv() {
  local candidate="${PHASE7_UV_BIN:-}"
  if [[ -n "${candidate}" ]]; then
    if [[ ! -f "${candidate}" || ! -x "${candidate}" ]]; then
      echo "PHASE7_UV_BIN is set but is not an executable file: ${candidate}" >&2
      return 1
    fi
    printf '%s\n' "${candidate}"
    return 0
  fi
  if candidate="$(command -v uv 2>/dev/null)" && [[ -n "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  echo "uv not found: install uv on PATH or set PHASE7_UV_BIN to its absolute path" >&2
  return 1
}

# File size in bytes, identical on GNU and BSD userlands (no stat flags).
phase7_file_size() {
  local path="$1" size
  size="$(wc -c < "${path}" 2>/dev/null | tr -d '[:space:]')" || size=""
  printf '%s\n' "${size:-0}"
}

# Prefix command that records peak resources when GNU time is usable; empty
# otherwise (macOS/BSD time has no -v). Prints the prefix words, if any.
phase7_gnu_time_prefix() {
  local output="$1" binary="${PHASE7_GNU_TIME_BIN:-/usr/bin/time}"
  if [[ -x "${binary}" ]] && "${binary}" -v true >/dev/null 2>&1; then
    printf '%s -v -o %s\n' "${binary}" "${output}"
  fi
}
