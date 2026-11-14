#!/usr/bin/env bash
# Resource + progress monitor (read-only). ADDED BY CLAUDE (2026-11-14). Run in its own tmux window:
#   bash scripts/runpod/monitor.sh            # appends one line per minute to evidence/monitor.log
set -uo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/runpod_env.sh" >/dev/null
L="$CRYPTO2_LOCAL/evidence/study_ledger.json"
while true; do
  done_runs=$(python3 -c "import json;r=json.load(open('$L'))['runs'].values();print(sum(x['status']=='COMPLETE_VERIFIED' for x in r))" 2>/dev/null || echo "?")
  line="$(date -u +%FT%TZ) load=$(cut -d' ' -f1 /proc/loadavg) mem_used=$(free -g | awk 'NR==2{print $3}')G avail=$(free -g | awk 'NR==2{print $7}')G disk_free=$(df -BG --output=avail "$VOL" | tail -1 | tr -d ' ') verified_runs=$done_runs/768 workers=$(pgrep -fc benchmark_one_spec)"
  echo "$line" | tee -a "$CRYPTO2_LOCAL/evidence/monitor.log"
  sleep 60
done
