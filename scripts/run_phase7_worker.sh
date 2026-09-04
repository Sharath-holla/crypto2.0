#!/usr/bin/env bash
set -uo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_root="${repository}/local_artifacts/phase7/supervisor"
run_log="${repository}/local_artifacts/phase7-cloud-run.log"
exit_file="${state_root}/worker-exit-code"

mkdir -p "${state_root}" "$(dirname "${run_log}")"
cd "${repository}"

# Bound log growth: rotate a large historical log before the worker starts
# (single writer; never blocks worker startup).
bash "${repository}/scripts/rotate_phase7_run_log.sh" "${run_log}" || true

set +e
/home/nssharath123/.local/bin/uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --resume 2>&1 | tee -a "${run_log}"
pipeline_status=("${PIPESTATUS[@]}")
worker_status="${pipeline_status[0]}"
tee_status="${pipeline_status[1]}"
set -e

if [[ "${worker_status}" -eq 0 && "${tee_status}" -ne 0 ]]; then
  worker_status=74
fi

temporary="${exit_file}.tmp.$$"
printf '%s\n' "${worker_status}" > "${temporary}"
mv "${temporary}" "${exit_file}"
exit "${worker_status}"
