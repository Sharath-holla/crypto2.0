# Updated preemption/restart source — supersedes the earlier preparation kit

Training source: **1b6a027b180979981eb76a4d6cbdec22510960df**. The 7a64ee0 freeze is historical and must not be used for this runtime. Full details and measured continuation failures are in `../reviews/PHASE7A_PREEMPTION_RESUME_READINESS_20261117.md`.

**MID_FIT_RESUME_NOT_QUALIFIED.** Production never uses `init_model`. The supported recovery is a fresh, separately approved attempt from round zero on the exact same qualified cache. Native partial Boosters are retained for audit, not published as completed models or claimed as an equivalent continuing fit.

Wallet policy: absolute floor **$1.00**, configurable trigger **$1.75** by default, raised to cover rate × checkpoint/shutdown/billing-lag/export/API reserves plus margin. The controller requests a checkpoint and waits only within remaining safe time; near the floor/API-health failure it prioritizes provider stopping and the last verified persistent checkpoint. Storage continues billing after compute stops, so this is not an indefinite account-balance guarantee. No auto-top-up or automatic resume after funding.

# Phase 7A: three separate owner checkpoints — 18 November 2026

This is an operator kit, **not authorization to deploy, prepare or fit**. Tonight's work is static only. Scientific source stays at `1b6a027b180979981eb76a4d6cbdec22510960df`. This new freeze supersedes the historical 7a64ee0 source; use the Git-free frozen export, never the mutable checkout or the old `/workspace/crypto2.0` Phase 8 checkout.

## Source and inputs

Frozen archive on the Mac:

```
/Users/cortex/Crypto2Data/reports/phase7-preemption-20261117/crypto2-source-1b6a027b1809.tar.gz
```

SHA-256: `f1737c335d98cca4832251dc674b46fa17d6f53cfa434b42c1f0bf55a84c26d9`.
The archive contains 1,230 committed files (25,118,775 bytes), plus `source-freeze.json`: **1,231 shipped regular files, 25,343,270 bytes**. Archive size: **5,719,805 bytes**. The committed inventory digest is `50d2a570ac3beb1276635f642ddd72fd04608f177f2d135a45d0735bb9a0e5c6`. The export contains exact committed Git bytes; no uncommitted scientific source is shipped.

`runpod_source_manifest.json` binds the archive, source inventory, `uv.lock`, Python requirement and six content identities. `identity.expected.json` has exactly six keys and is valid for canonical `--expect`. Platform identity is separate; Linux x86_64 need not match Mac arm64.

Inputs are already uploaded: **2,777 files / 10,998,003,736 bytes** at `/workspace/phase7a-transfer/`, volume `kz9axr9t9v`, EU-SE-1, 50 GB. Completed at `2026-11-17T00:00:32.112735+05:30`. Do not re-upload the 58 GiB folder. `transfer.expected.json` retains the exact path/size/SHA inventory and descriptor supplements. Sidecar is a sibling of `crypto2-persistent`, not inside it. Preserve all 67 forensic extras; they are excluded by manifest-based discovery.

## A–B: live host and fresh authorization, on the Mac

1. Run the read-only selector. It checks CPU and GPU catalogs in the volume's region, records wallet/old Pod state and price orders eligible catalog candidates. Catalog eligibility is provisional; actual cgroups and local disk must pass inside the approved Pod.

```bash
cd /Users/cortex/Projects/crypto2.0
.venv/bin/python scripts/closure/runpod_select_host_phase7.py \
  --output /Users/cortex/.crypto2-transfer/phase7-live-hosts-20261118.json
```

2. Query fresh Pod and network-volume billing from `/v2/billing/pods` and `/v2/billing/network-volumes`, with UTC start/end and resource IDs. Reconcile cumulative identified charges with the retained $1.1418196061 snapshot; provider billing can lag. Record the wallet and existing storage rate. No top-ups. The historical $18 cap is an additional limit, **not a fresh spending allowance**.
3. Show the live type, RAM allocation, effective-CPU expectation, image/digest, EU-SE-1 placement, 200 GB container-disk proposal, and 1/2/4-hour all-in costs. Obtain explicit owner selection, maximum session USD, hard UTC stop and **LINUX VERIFICATION ONLY** approval. Do not invent either limit.
4. Copy `RUNPOD_COST_AND_STOP_CONTRACT_TEMPLATE_20261118.json` to a private session-contract file, fill fresh facts and owner-approved limits, and only then set its status to `APPROVED`. `session_start_utc` must include deployment/provisioning time. Every approval uses the same session ceiling/deadline; later approvals do not reset spending. Template validation deliberately fails until filled.
5. Owner-authorized operator deployment only: choose the cheapest live host satisfying allocation constraints; attach the existing volume at `/workspace`; request Linux x86_64, direct SSH, no extra volume disk, and **at least 150 GB container disk** (200 GB is a planning proposal). Do not auto-restart `3hv6n675gud1wu`. No deployment/start/create code exists in this kit.
6. Record the assigned new Pod ID, live rate, image, start time, allocated RAM/vCPU, local disk quota and mount in the contract. Discover SSH from `GET /v2/pods/{id}` → `ssh.direct`; do not reuse an old port. Verify the SSH host fingerprint through the provider console before recording it in `known_hosts`. The controller uses strict host-key checking.
7. Use resumable SSH/rsync to upload **only the 5.72 MB source archive, the separate operator kit, and the private session contract**. Extract source to `/crypto2-session/source` on verified local storage, operator kit to `/crypto2-operator-kit`. Never extract onto inputs, overwrite a historical result or copy API keys to the Pod. Before extraction, validate archive SHA and reject absolute/traversal/link member paths. No data re-upload is needed.

For example, after a trusted direct endpoint is discovered, replace `LIVE_HOST` and `LIVE_PORT` once; use the working dedicated SSH key:

```bash
rsync -avP -e 'ssh -i /Users/cortex/.ssh/runpod_crypto2 -p LIVE_PORT -o StrictHostKeyChecking=yes' \
  /Users/cortex/Crypto2Data/reports/phase7-preemption-20261117/crypto2-source-1b6a027b1809.tar.gz \
  root@LIVE_HOST:/crypto2-session/
```

The updated operator bundle is `/Users/cortex/Crypto2Data/reports/phase7-preemption-20261117/crypto2-preemption-operator-kit-20261117.tar.gz`. Its external `operator_bundle_manifest.json` and `SHA256SUMS` in the same directory record its SHA/inventory. The tar root is `crypto2-operator-kit`; extract it under `/` only after checking SHA and safe member paths. It must not be inserted into or represented as part of the frozen scientific package.

## Independent stop control — before any verification workload

The outside-Pod controller has no start/create/delete/resize operation. It uses a private 0600 Mac API-key file, reads current state/rate/volume and performs a **non-disruptive no-op `PATCH {locked:false}` on an already unlocked approved Pod**. That proves the documented `pods:write` scope shared by the stop action; it then verifies `stop` is an available transition. This is a permission/state probe, not an actual shutdown test. If it fails, its error path attempts a provider stop and confirms `EXITED`; do not leave before that receipt or manual console confirmation.

On the Mac, under a supervised launchd job or a dedicated Terminal while present:

```bash
caffeinate -dimsu /Users/cortex/Projects/crypto2.0/.venv/bin/python \
  /Users/cortex/Projects/crypto2.0/scripts/closure/runpod_stop_controller_phase7.py \
  --contract /Users/cortex/.crypto2-transfer/phase7-session-approved.json \
  --local-root /crypto2-session --arm
```

Keep the Mac powered, online and awake. Before leaving unattended, install and verify the supplied `com.crypto2.phase7-stop.20261118.plist.template` as a launchd `KeepAlive` supervisor, observe two fresh heartbeats (20-second interval), inspect `permission-probe.json`, and simulate a **local mock** deadline/stop path. Tomorrow, after approval: create the private controller-state directory, copy the template to `~/Library/LaunchAgents/com.crypto2.phase7-stop.20261118.plist`, then use `launchctl bootstrap gui/$(id -u) <plist-path>` and `launchctl kickstart gui/$(id -u)/com.crypto2.phase7-stop.20261118`. Inspect its stdout, permission probe and heartbeat before beginning work. The kit does not install or arm launchd tonight. Do not confuse a PID or Python termination with provider stop. After a confirmed stop the controller exits successfully; an expired contract can still stop its exact previously armed Pod on supervisor restart.

The controller writes local receipts and publishes a Pod heartbeat via strict SSH. The operator stages refuse missing/stale (>90 s) receipts or a different contract. It stops via `POST /v2/pods/{id}/action {action:stop}` and verifies `EXITED` plus preserved volume. It uses the conservative maximum of identified billing, wallet decline and elapsed time × approved/account-observed all-in rate. Default trigger reserve covers 90 seconds checkpoint grace + 120 shutdown + 300 billing lag + 30 minimal export + 30 API latency, plus $0.25. Grace is bounded by remaining wallet/session/deadline headroom; near the floor it becomes zero. Any wallet/billing/API/SSH health failure triggers provider-stop attempts. No large cache copy delays shutdown.

Limitations: delayed billing is not exact real-time cost; network/API outages or a powered-off Mac cannot guarantee control-plane reachability. Do not run unattended without a functioning outside-Pod supervisor and reliable power/network. This preparation is **not** a claim that tomorrow's live controller has passed. Container disk is erased on stop; copying evidence/results first is essential. The network volume is never deleted. Retained network storage continues billing after compute stops.

## C: locked bootstrap, inside the approved Pod

Set only the operator variables below in a clean shell; do not inherit any `PHASE7_*` variables from previous experiments:

```bash
export CRYPTO2_SOURCE_ROOT=/crypto2-session/source
export CRYPTO2_LOCAL_ROOT=/crypto2-session
export CRYPTO2_SESSION_CONTRACT=/crypto2-session/session-approved.json
export KIT=/crypto2-operator-kit
bash "$KIT/scripts/closure/runpod_bootstrap_phase7.sh" --execute
export CRYPTO2_OPS_PYTHON="$CRYPTO2_SOURCE_ROOT/.venv/bin/python"
```

Bootstrap checks the source inventory before importing it, Linux/x86_64, current Pod ID, local mount type/capacity and provider quota, then installs `libgomp1`/CA/curl/`python3-venv` and uses `uv sync --locked --extra dev --python 3.12`. Choose an image with Python >=3.11 (prefer 3.12) to run the bootstrap itself. If uv is absent it installs the pinned operator tool `uv==0.13.7` into an isolated local tool venv; no system-pip override or research dependency upgrades outside `uv.lock`. Python/project package/uv/Ruff versions and mount evidence are retained. A cheap cgroup RAM/CPU capacity check runs before Gold validation or the Linux suite. Docker/overlay `df` can expose the host disk: both measured filesystem capacity and provider container quota must pass.

## D–F: transfer, relocation, descriptors, identities

```bash
bash "$KIT/scripts/closure/runpod_verify_transfer_phase7.sh" --execute
```

This checks only the 2,777 named records for existence/size, hashes critical metadata, copies the small historical stage metadata/checkpoints byte-for-byte into isolated local seed directories, then calls canonical `CheckpointStore.is_complete` for all four stages and `validate_phase7_gold`. Required checkpoint/Gold hash gates remain enabled; they read large Gold files. The frozen benchmark also repeats canonical validation during prepare/train. This mandatory work is not a newly added blanket hash scan, and it cannot be skipped by claiming prior upload provenance.

All canonical discovery remains manifest-driven. The canonical Fold-0 descriptor builder reads only its selected TRAIN lookback; all descriptor inputs are in the transferred supplements. Its identity is recorded and independently rederived for cache qualification. No fresh acquisition.

Mappings:

| Historical prefix | Current root |
| --- | --- |
| `/home/nssharath123/crypto2.0/data` | `/workspace/phase7a-transfer/crypto2-persistent/data` |
| `/home/nssharath123/crypto2.0/data/gold/phase7a_core20_primary_v1` | same Gold subdirectory under current data root |
| `/home/nssharath123/crypto2.0/local_artifacts/phase7` | `/crypto2-session/stage-artifacts` |

The longest-prefix canonical mapper handles references; every checkpoint hash/reference must pass. No fabricated `/home/nssharath123` tree. All writes use local `stage-artifacts`, `stage-checkpoints`, `cache`, `models`, `model-hashes`, `reports`, `logs`, `tmp`, and `benchmarks/smoke`. The model hash registry is outside the artifact folder, is required on reload, and is exported with results. Uploaded network inputs are never rewritten.

Canonical identity command (wrapper runs the same implementation):

```bash
"$CRYPTO2_OPS_PYTHON" -m crypto_ai.phase7.identity_summary \
  --gold-manifest /workspace/phase7a-transfer/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/manifest.json \
  --sidecar /workspace/phase7a-transfer/feature_context_sidecar_v3/manifest.json \
  --expect "$KIT/docs/runpod/identity.expected.json"
```

Run canonical commands from the frozen source directory with its environment/PYTHONPATH, not an editable install of the main checkout.

## G–I: Linux, filesystem and measured resource gate

```bash
bash "$KIT/scripts/closure/runpod_preflight_phase7.sh" --execute
```

This wraps the exact frozen command:

```bash
bash /crypto2-session/source/scripts/closure/verify_linux_external.sh /crypto2-session/linux-fs
```

It covers the full pytest suite, Ruff, formatting, source/export verification, Linux verification, ledger/crash recovery and filesystem primitives. The existing canonical external script intentionally runs the full suite and then `verify_linux`, which runs its own suite; this duplication is preserved, not silently edited. It removes inherited research environment variables in its child. Its outputs remain local and are exported afterward.

The operator then calls canonical `qualify_filesystem` on `/crypto2-session/filesystem-qualification`: file/directory fsync, atomic file replace, directory rename, cross-process cache locks and RunLease exclusion/release. Only that newly created UUID probe directory is removed afterward; cleanup is recorded. All output roots share the qualified local filesystem. Standalone primitive command:

```bash
"$CRYPTO2_OPS_PYTHON" -m crypto_ai.phase7.filesystem_probe --root /crypto2-session/filesystem-qualification
```

Resource estimate command, derived from current `--help`:

```bash
"$CRYPTO2_OPS_PYTHON" -m crypto_ai.phase7.resource_estimate \
  --manifest /workspace/phase7a-transfer/crypto2-persistent/data/gold/phase7a_core20_primary_v1/gold-phase7-0cbf2910e8d96c9d19826598/manifest.json \
  --path /crypto2-session/cache --fold-index 0 --horizon-minutes 60 \
  --config /crypto2-session/source/configs/phase7/research_core20_primary_v1.toml --json
```

It reads manifest-selected row/time/horizon data for the measured estimate; no matrix build or fit. Admission additionally uses canonical `smoke_resource_errors` (64 GiB effective RAM, 8 effective CPUs, **150,000,000,000 bytes** disk). Headroom guards in the proposed contract: minimum **32 GiB available RAM**, **25 GiB free disk**, checked repeatedly by canonical resource admission. They are minimum operational guards, not proofs of peak capacity. The prior Fold-0 heuristic is ~25.836 GiB / 4,922,887 pre-filter rows and is **not an upper bound**; inspect actual admission, keep substantial RAM headroom and stop if insufficient. One model worker uses canonical effective CPU count (affinity and cgroup quota), not one thread or all host threads.

**STOP AND REPORT HERE.** Export evidence. Do not prepare until the owner separately says **PREPARE ONE CACHE**.

## J–L: separately approved one-cache preparation and read-only qualification

Copy `OWNER_PREPARE_TEMPLATE_20261118.json`, record the owner's new explicit prepare approval, preserve its exact canonical binding, and fill the same session USD/deadline. Only this record may use `mode:prepare` and `status:APPROVED`.

```bash
bash "$KIT/scripts/closure/runpod_prepare_one_cache_phase7.sh" --execute \
  --approval /crypto2-session/owner-prepare-approved.json
bash "$KIT/scripts/closure/runpod_reload_cache_phase7.sh" --execute \
  --approval /crypto2-session/owner-prepare-approved.json
```

The preparation wrapper invokes only:

```
python -m crypto_ai.phase7.benchmark_one_spec --config configs/phase7/research_core20_primary_v1.toml --spec-id architecture-G0-A6-60m-raw --output-root /crypto2-session/benchmarks/smoke --execute --prepare-only
```

It supplies `PHASE7_CACHE_MODE=auto`, CPU, one logical worker, canonical thread budget, sidecar, relocated paths, Gold validation report, owner approval and resource floors. The CLI selects canonical Fold 0; it has **no `--fold-index` argument**. Require `PREPARED_ONLY` and `models_fitted:0`.

Reload sets `PHASE7_CACHE_MODE=read_only`. There is no CLI flag that combines prepare-only with read-only: canonical preparation correctly forbids that combination. The operator calls **`PreparedDataCache(root, 'read_only').load(fresh_identity, canonical_fold)` twice**. Identity is independently rederived with the frozen canonical `_prepared_cache_identity`, Fold-0 membership and descriptors, Gold/source/sidecar/environment bindings and A6 order; it is not accepted from a self-asserting cache manifest.

Qualification validates `CACHE_COMPLETE` (the actual marker name), manifest, exact inventories/SHA-256s, rows, schemas, float64 arrays, finite matrices, symbol/target/feature alignment, weights, split timestamps, label-end purging and no July/August. Canonical fit-boundary checks are reused without fitting. TEST is checked structurally for timestamps/rows only; no TEST outcomes, predictions or metrics are scored. Exact manifest/file hashes, row/time/symbol summaries and deterministic weight hashes must agree across both loads. No rebuild/quarantine is allowed in read-only mode. Failure requests a provider stop.

**STOP AND REPORT AGAIN.** Export cache qualification/reload evidence; do not train until the owner separately says **TRAIN ONE CPU SMOKE**. With `retain_qualified_cache:true` (default proposal), the reload wrapper now copies the fully qualified cache once to `/workspace/phase7a-cache/<cache-id>/`, verifies all copied hashes and publishes the completion directory atomically. Capacity uses both free bytes and the provisioned 50 GB quota (metadata-only `du -sb /workspace`), leaving 5 GiB reserve. No high-churn training writes use this retained cache. If persistence is disabled or lacks capacity, the report says `MODEL_RESUME_WITH_CACHE_REPREPARATION`; a new separately approved preparation must reproduce the exact identity and payload hashes before restarting the model. Never assume instant cache recovery.

## M: separately approved single CPU smoke

Copy `OWNER_TRAIN_TEMPLATE_20261118.json`, retain canonical exact binding, enter the owner's separate train approval with the same session USD/deadline. Then:

```bash
bash "$KIT/scripts/closure/runpod_train_one_smoke_phase7.sh" --execute \
  --approval /crypto2-session/owner-train-approved.json
```

Only the same benchmark command is used, **without `--prepare-only`**, with `PHASE7_CACHE_MODE=read_only`. Cache is revalidated before `.fit()`. No pipeline/grid dispatcher, GPU backend, extra fold/spec/seed, new acquisition or scientific modification is allowed. The one-model benchmark must report exactly one completed benchmark result; partial/ineligible output is not recorded as PASS.

Purpose: **REGRESSION_PLUMBING_AND_PIPELINE_SMOKE**. `PHASE7_LGBM_DEVICE=cpu`, `GPU_NOT_QUALIFIED`; the GPU remains unused for fitting. Original maximum 500 rounds, learning rate .02 and 50 early-stopping rounds remain unchanged. Record best iteration, stop reason, cap reached and monitoring overhead; do not retune mid-run.

At the configured 25-round interval retain TRAIN/Validation RMSE, Validation MAE/best RMSE/iteration/rounds since best/gap/Pearson/Spearman/direction/cross-sectional IC where supported, prediction distribution, descriptive LONG/SHORT precision/recall/F1/support, action coverage, RSS, available RAM, disk, elapsed time, backend and threads. Undefined action metrics are null/N/A. Thresholds stay in correct raw-return units; no adaptive diagnostic threshold selection, profitability claim or TEST metric inside fit. Zero, TRAIN mean, full-TRAIN weighted matched Ridge where supported and LightGBM comparisons use the authorized scored rows; do not overclaim pooled baselines as matched. Record any remaining full-TRAIN metric cost without optimizing it during the smoke.

## Evidence and shutdown

Each successful stage writes machine-readable receipts and add-only snapshots under:

```
/workspace/phase7a-evidence/<approved-pod-id>/<UTC-snapshot>/
```

Snapshots contain Linux/fs/identity/resource reports, descriptor evidence, cache qualification, logs/telemetry, model/report/receipt/canonical result/checkpoint directories and the owner session contract. No account API credentials. Qualified cache retention happens separately and early, immediately after qualification/reload when space permits; it is never attempted during a wallet emergency. Add-only copies refuse conflicting historical evidence. On failure the external controller attempts a bounded rescue before stopping; a hard stop can still lose unexported ephemeral work.

Manual collection uses the same gates:

```bash
bash "$KIT/scripts/closure/runpod_collect_evidence_phase7.sh" --execute
```

After a completed single smoke and successful evidence export, the training wrapper automatically creates `/crypto2-session/control/SESSION_COMPLETE.json`. The controller stops the Pod and confirms `EXITED`, retaining `kz9axr9t9v`. If the session is ended manually instead, create that file with `{ "reason": "OWNER_SESSION_COMPLETE" }` after collecting evidence. Inspect the controller's stop receipt before leaving. If any gate fails, do not work around it; preserve/export evidence and confirm compute is stopped. Do not run more models after a successful smoke.

## Tonight's dry run

Without `--execute`, every shell wrapper only prints a JSON plan, even on the Mac. Controller without `--arm` does not read credentials, connect or schedule anything. Current checkpoint/controller/operator tests, exact-export tests and continuation measurements are retained in `docs/reviews/evidence_preemption_20261117`. Historical preparation evidence remains in the main checkout under `docs/reviews/evidence_runpod_preparation_20261117`. Mac results never imply Linux/cache/model readiness.

## After preemption and top-up: fresh authorization, new Pod, restart one model

1. Read the external controller's `stop-receipt.json`; previous Pod must be `EXITED`. Add funds yourself. Nothing auto-resumes.
2. Obtain a fresh session contract: live wallet/billing/rate, cheapest qualifying EU-SE-1 host, new Pod ID, new maximum session USD and hard UTC deadline. Old $18 history is not a fresh allowance. Set `previous_pod_id` and copy the prior checkpoint's `model_threads`; the new host must support that thread budget. Locked numerical environment/Python version and all six scientific identities must match.
3. Repeat the new source/package, Linux/filesystem/resource/input/identity gates. Start the supervised outside-Pod controller; it checks the previous Pod is still EXITED. Do not run a real cache build unless separately approved.
4. Obtain explicit **RESUME ONE CPU SMOKE** authorization using `OWNER_RESUME_TEMPLATE_20261118.json`. It has canonical `mode:train` plus `operation:RESUME_ONE_CPU_SMOKE_RESTART_FROM_ZERO`, the saved logical run ID and exact checkpoint SHA. All fields must refer to the new session's limits; an old approval or wallet top-up is insufficient.
5. If cache retention passed, restore it to local disk and requalify it:

```bash
bash "$KIT/scripts/closure/runpod_restore_cache_phase7.sh" --execute \
  --approval /crypto2-session/owner-resume-approved.json \
  --checkpoint /workspace/phase7a-evidence/training-checkpoints/LOGICAL/SESSION/iter-NNNNNN-ID
```

If absent, stop at `MODEL_RESUME_WITH_CACHE_REPREPARATION`, obtain a separate prepare approval, then prepare/qualify/reload the same cache. Identity or payload mismatch refuses restart; no repair or silent substitution.

6. Restart exactly the one model:

```bash
bash "$KIT/scripts/closure/runpod_resume_one_smoke_phase7.sh" --execute \
  --approval /crypto2-session/owner-resume-approved.json \
  --checkpoint /workspace/phase7a-evidence/training-checkpoints/LOGICAL/SESSION/iter-NNNNNN-ID
```

This explicitly restarts at round zero, with at most 500 trees in the final model. It preserves `logical_run_id` and assigns a distinct `execution_session_id`; telemetry emits `MODEL_RESTARTED_AFTER_PREEMPTION`, never a false `TRAINING_RESUMED` round offset. All source, cache contents, row/weight/schema/target identity, native parameters, threads and versions must match before fitting.

During fitting, native partial snapshots publish every 25 rounds and on a request/SIGTERM/SIGINT flag. Only ordinary callbacks perform I/O. Local fsync/rename/marker/hash verification precedes network publication; an independent process parses the copied native Booster. Keep three verified snapshots with immutable retention-audit metadata. Partial checkpoints never enter the complete result ledger. Large cache copying is never part of the bounded low-wallet grace period. Native partials plus full per-session JSONL and telemetry tails reside under `/workspace/phase7a-evidence/training-checkpoints/<logical-run-id>/`.

The native file records every completed tree (`save_model(num_iteration=-1)`), including trees after the best round; it also records best L2/RMSE/iteration/patience, max/remaining rounds, exact parameters/seeds/threads and immutable scientific/cache bindings. These records do not restore the missing equivalence of a continued fit. The original early-stopping callback and parameters remain unchanged for normal fits.
