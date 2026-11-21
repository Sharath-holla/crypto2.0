#!/bin/bash
# Owner 2026-11-20: train folds 5/10/15 in EU-SE-1; retry hosts every 2 min until the 21:55Z hard stop.
cd /Users/cortex/.crypto2-transfer
PY=/Users/cortex/Projects/crypto2.0/.venv/bin/python
n=0
while [ "$(date -u +%Y%m%d%H%M)" -lt 202611202145 ]; do
  n=$((n+1)); L=phase7-pilot-4fold-resume-20261120-r2-try$n.log
  caffeinate -dimsu $PY pilot_4fold_20261118.py > $L 2>&1; rc=$?
  if grep -q "FOLD_FAILED.*NO_SUITABLE_HOST_AVAILABLE" $L && ! grep -q DEPLOYED $L; then echo "try$n $(date -u +%H:%M) no host"; sleep 120; continue; fi
  echo "try$n rc=$rc DRIVER_FINISHED"; tail -12 $L; exit 0
done
echo "WINDOW_EXPIRED_NO_HOST after $n tries"
