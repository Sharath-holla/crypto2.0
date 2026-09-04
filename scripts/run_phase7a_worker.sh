#!/usr/bin/env bash
set -uo pipefail

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_root="${repository}/local_artifacts/phase7/supervisor-phase7a"
run_log="${repository}/local_artifacts/phase7a-core20-primary-run.log"
exit_file="${state_root}/worker-exit-code"
config="configs/phase7/research_core20_primary_v1.toml"

mkdir -p "${state_root}" "$(dirname "${run_log}")"
cd "${repository}"
bash "${repository}/scripts/rotate_phase7_run_log.sh" "${run_log}" || true

run_stage() {
  /home/nssharath123/.local/bin/uv run python scripts/run_phase7a_pipeline.py \
    --config "${config}" --stage "$1" --resume
}

set +e
{
  run_stage registry &&
  run_stage universe &&
  run_stage data &&
  run_stage gold &&
  /usr/bin/time -v -o "${state_root}/fold1-resource-usage.txt" \
    /home/nssharath123/.local/bin/uv run python scripts/run_phase7a_pipeline.py \
    --config "${config}" --stage train --resume --canary &&
  /home/nssharath123/.local/bin/uv run python scripts/phase7a_feasibility_gate.py \
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
