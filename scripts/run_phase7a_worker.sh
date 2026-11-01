#!/usr/bin/env bash
set -uo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_root="${repository}/local_artifacts/phase7/supervisor-phase7a"
run_log="${repository}/local_artifacts/phase7a-core20-primary-run.log"
exit_file="${state_root}/worker-exit-code"
config="configs/phase7/research_core20_primary_v1.toml"

mkdir -p "${state_root}" "$(dirname "${run_log}")"
cd "${repository}"
# shellcheck source=scripts/lib/phase7_portable.sh
source "${repository}/scripts/lib/phase7_portable.sh"
uv_bin="$(phase7_resolve_uv)" || exit 78
bash "${repository}/scripts/rotate_phase7_run_log.sh" "${run_log}" || true

# Empty when GNU time is unavailable (e.g. macOS); resource usage is then not recorded.
time_prefix="$(phase7_gnu_time_prefix "${state_root}/fold1-resource-usage.txt")"

run_stage() {
  "${uv_bin}" run python scripts/run_phase7a_pipeline.py \
    --config "${config}" --stage "$1" --resume
}

set +e
{
  run_stage registry &&
  run_stage universe &&
  run_stage data &&
  run_stage gold &&
  ${time_prefix} \
    "${uv_bin}" run python scripts/run_phase7a_pipeline.py \
    --config "${config}" --stage train --resume --canary &&
  "${uv_bin}" run python scripts/phase7a_feasibility_gate.py \
    --summary local_artifacts/phase7/phase7a-core20-primary-93f987736b1a79d26b773957/canary_summary.json \
    --launch "${state_root}/runtime-authority.json" \
    --output "${state_root}/feasibility-gate.json" &&
  run_stage train &&
  run_stage report
} 2>&1 | tee -a "${run_log}"
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
