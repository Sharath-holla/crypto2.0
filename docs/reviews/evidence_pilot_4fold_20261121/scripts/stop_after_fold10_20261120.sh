#!/bin/bash
# Owner 2026-11-20 ~20:06Z: finish fold 10, then stop; do not train fold 15.
cd /Users/cortex/.crypto2-transfer
LOG=phase7-pilot-4fold-20261118/pilot.log
PY=/Users/cortex/Projects/crypto2.0/.venv/bin/python
until grep -qE 'POD_EXITED|FOLD_FAILED|PILOT_' <(awk '/STAGE_STARTED fold010 train/{f=1} f' $LOG); do sleep 2; done
kill 2995 3004 3005 2>/dev/null; sleep 3; pkill -f pilot_4fold_20261118.py
$PY - <<'PY'
import importlib.util, json
from datetime import UTC, datetime
s=importlib.util.spec_from_file_location('d','/Users/cortex/.crypto2-transfer/pilot_4fold_20261118.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
pods=m.api.call('POST','/graphql',{'query':'query { myself { pods { id desiredStatus } } }'})['data']['myself']['pods']
for p in pods:
    if p['desiredStatus']!='EXITED':
        m.api.call('POST','/v2/pods/'+p['id']+'/stop'); print('STOPPED',p['id'])
m.write(m.PILOT/'OWNER_STOP_20261120.json',{"instruction":"Owner 2026-11-20 ~20:06Z: 'just stop training fold 15 bcz i want to sleep now'. Fold 10 finishes; no fold 15; no compute until a fresh cost/deadline contract.","new_compute_or_training_authorized":False,"status":"OWNER_STOPPED","utc":datetime.now(UTC).isoformat(),"supersedes":["OWNER_AUTHORIZATION_20261120.json"]})
pods=m.api.call('POST','/graphql',{'query':'query { myself { currentSpendPerHr pods { id desiredStatus } } }'})['data']['myself']
print('NOT_EXITED',[p['id'] for p in pods['pods'] if p['desiredStatus']!='EXITED'],'spend/hr',pods['currentSpendPerHr'],'wallet',m.wallet())
PY
grep -E 'fold010 train|MODEL fold010|FOLD_FAILED|POD_EXITED|DEPLOYED' $LOG | tail -4 | cut -c1-200
