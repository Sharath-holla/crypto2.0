#!/bin/bash
# Owner 2026-11-21: train all remaining folds in EU-SE-1 within $8.39 / 8h. Retry no-host every 2 min,
# and retry up to 3 times after an SSH transport drop (exit 255). Any other failure or budget stop ends the loop.
cd /Users/cortex/.crypto2-transfer
PY=/Users/cortex/Projects/crypto2.0/.venv/bin/python
END=202611211428; n=0; drops=0
while [ "$(date -u +%Y%m%d%H%M)" -lt $END ]; do
  n=$((n+1)); L=phase7-pilot-4fold-resume-20261121d-try$n.log
  caffeinate -dimsu $PY pilot_4fold_20261118.py > $L 2>&1; rc=$?
  if grep -q "FOLD_FAILED.*NO_SUITABLE_HOST_AVAILABLE" $L && ! grep -q DEPLOYED $L; then echo "try$n $(date -u +%H:%M) no host"; sleep 120; continue; fi
  if grep -qE "REMOTE_COMMAND_FAILED_255|exit status 255" $L && [ $drops -lt 3 ]; then drops=$((drops+1)); echo "try$n $(date -u +%H:%M) ssh drop #$drops; retrying"; sleep 30; continue; fi
  echo "try$n rc=$rc DRIVER_FINISHED"; tail -12 $L; exit 0
done
echo "WINDOW_EXPIRED after $n tries"
