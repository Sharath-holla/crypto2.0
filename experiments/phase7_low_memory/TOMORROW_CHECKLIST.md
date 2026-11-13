# Checklist — 14 November 2026 (starts ONLY when the owner says so)

Nothing runs automatically. Each box needs the owner's explicit go-ahead in chat.

## Before anything
- [ ] Owner message received: "start Stage A" (or equivalent).
- [ ] New session? Run `bash scripts/cloud/setup_session.sh`, then `source scripts/cloud/session_env.sh`.
- [ ] Freeze drift tests pass (v2); budget `fits: true`.

## Stage A — approvals (owner answers)
- [ ] Transfer approved (2,777 files / 10,998,003,736 B).
- [ ] Charges accepted (storage ≈ USD 0.22–0.26/month; egress ≈ USD 1.32–2.53 per download).
- [ ] UTC stop deadline: `______________________Z`
- [ ] Cost ceiling + currency: `________ ___`
- [ ] Source version accepted: branch `experiment/phase7-cloud-training-prep`, freeze v2.
- [ ] Low-memory profile exception accepted (13 GiB / 4 CPU / free-disk floors; staging 30 days).
- [ ] Reminder acknowledged: the GitHub repository is PUBLIC; results go to the private bucket.

## Stage B — transfer
- [ ] Mac: `git worktree add …crypto2.0-cloudprep origin/experiment/phase7-cloud-training-prep`.
- [ ] Mac: `bash scripts/cloud/mac_upload_transfer_set.sh` (dry run passes, 2,777 SHA-256 OK).
- [ ] Mac: `bash scripts/cloud/mac_upload_transfer_set.sh --execute` (remote count 2,777).
- [ ] Mac: `bash scripts/cloud/mac_setup_reader_access.sh` → review → `--execute`.
- [ ] Mac: token pasted ONLY into Claude's credential card.
- [ ] VM: `transfer_set.py fetch --execute` → `verify` = VERIFIED.
- [ ] VM: Gold hash verification passes; GOLD_MANIFEST_SHA `a1420277…`, SIDECAR_SHA `ea5f25a2…`.
- [ ] VM: disk budget fits with the data present.

## Stage C — prepare-only validation (no fit)
- [ ] Prepare approval printed, owner read the binding, written with `--confirm`.
- [ ] Prepare-only run exit 0; peak anon ______ GiB; min free disk ______ GB; time ______.
- [ ] Qualification `VALIDATED`, `differences: []`, chronology/isolation `all_passed: true`.
- [ ] Validation record SHA-256: `________________________________`
- [ ] Results reported to owner. **STOP.**

## Stage D — first training (needs a NEW explicit authorization)
- [ ] Owner: "authorize training of architecture-G0-A6-60m-raw Fold 0".
- [ ] Train approval (binds the validation SHA-256) printed, read, written.
- [ ] Canonical run exit 0; peak memory ______; time ______.
- [ ] `verify_model_reload.py` → RELOAD_VERIFIED.
- [ ] Metrics reported (Validation / Cal-A / Cal-B / protocol TEST as produced by the run).
- [ ] `run_persistence export` + `gcs_results.py push` done; owner can `gcloud storage cp` it.

## Stage E
- [ ] Plan for further specs/folds presented; NOT started without separate authorization.

## Afterwards
- [ ] `bash scripts/cloud/mac_setup_reader_access.sh --cleanup` (removes access).
- [ ] Optional: delete `gs://crypto-ai-data-83921/phase7-transfer-20261113` to stop storage charges.
