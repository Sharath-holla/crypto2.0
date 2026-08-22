# Phase 7 Google Cloud Runbook

## Current status

The local implementation and fixture tests are complete. The existing Google
Cloud VM is still stopped, and no cloud data acquisition or training has been
run. Execute these commands only after reviewing, committing, and pushing the
local changes. Do not create a new VM, project, service, or GPU.

The required order is: review and commit/push locally; start the existing VM;
SSH; pull/clone; `uv sync`; restore existing Cloud Storage inputs; run tests;
validate; plan and inspect; enable the guard; start `tmux`; run `--resume`;
verify; back up to the existing bucket; and stop the VM.

The Phase 7 baseline is market-data-only. The separate Fear & Greed and open
interest collectors documented in `CONTEXT_DATA_FOUNDATION.md` are not Phase 7
model inputs and must not be enabled during this baseline run.

## 1. Review, commit, and push locally

Complete the local pre-push audit first. Review `git diff`, then commit and push
only after the audit verdict is `READY_FOR_CLOUD`. This runbook does not perform
those Git actions automatically.

## 2. Set local identifiers and start the existing VM

PowerShell on the local machine:

```powershell
$env:PHASE7_GCP_PROJECT = "<existing-project-id>"
$env:PHASE7_GCP_ZONE = "<existing-vm-zone>"
$env:PHASE7_GCP_VM = "<existing-stopped-vm-name>"

gcloud compute instances start $env:PHASE7_GCP_VM `
  --project $env:PHASE7_GCP_PROJECT `
  --zone $env:PHASE7_GCP_ZONE

gcloud compute ssh $env:PHASE7_GCP_VM `
  --project $env:PHASE7_GCP_PROJECT `
  --zone $env:PHASE7_GCP_ZONE
```

Do not resize or otherwise modify the VM. The target is approximately 16 vCPU,
64 GB RAM, no GPU.

## 3. Update and verify the repository

On the VM:

```bash
cd ~/crypto2.0
git status --short
git pull --ff-only
uv sync --extra dev --frozen

uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run python -m compileall -q src tests
uv lock --check
```

Stop if the worktree is unexpectedly dirty or any check fails.

## 4. Restore prior data/artifacts when required

Set the already-existing bucket path. The code itself remains filesystem
oriented and does not require a GCS Python SDK.

```bash
export PHASE7_CLOUD_STORAGE_ROOT="gs://<existing-bucket>/artifacts/phase7"

# Adjust source prefixes to the paths already used by your bucket.
gcloud storage rsync --recursive \
  "gs://<existing-bucket>/data" ./data
gcloud storage rsync --recursive \
  "gs://<existing-bucket>/local_artifacts" ./local_artifacts
```

Never copy over a different immutable artifact with the same identity. Inspect
and resolve any checksum mismatch instead of deleting or repairing it.

## 5. Validate and plan without heavy work

```bash
uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --validate-config

uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --plan

uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --dry-run

uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --test-universe
```

These commands make no network request and perform no heavy training. Confirm:

- `core_universe_v1` has a 20-symbol target selected at the first TRAIN end;
- `expansion_universe_v1` uses `fold_train_end`, at most 10 additions, and a
  30-symbol total fold cap;
- both `CORE` and `EXPANDING` research views are planned separately;
- 16 calendar folds end at the exclusive 2026-07-01 research cutoff;
- July 2026 remains unused and the 2026-08-01 holdout is `LOCKED_UNUSED`;
- `prospective_holdout_evaluation_authorized=false`; and
- paths, disk, RAM, threads, architectures, and horizons are correct.

## 6. Enable the VM-only guard and run in tmux

```bash
export PHASE7_ALLOW_CLOUD_RESEARCH=1
tmux new -s phase7
cd ~/crypto2.0

uv run crypto-ai phase7-research \
  --config configs/phase7/research_v1.toml \
  --resume 2>&1 | tee local_artifacts/phase7-cloud-run.log
```

Detach with `Ctrl+B`, then `D`. Reattach with:

```bash
tmux attach -t phase7
```

The monolithic command executes `registry`, `universe`, `data`, `gold`,
`train`, and `report`. The universe stage writes the frozen core definition,
the frozen expansion policy, and point-in-time fold memberships before
full-resolution acquisition. Each completed stage and each
view/fold/experiment has a checksum-validated checkpoint. Membership, core,
expansion-policy, Gold, and configuration identities invalidate stale work.
After interruption, run the identical `--resume` command.

For deliberate staged execution, run in order:

```bash
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage registry --resume
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage universe --resume
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage data --resume
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage gold --resume
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage train --resume
uv run crypto-ai phase7-research --config configs/phase7/research_v1.toml --stage report --resume
```

The registry and data stages use only official Binance public endpoints and
checksum-verified public archives. No API key should be present or required.

## 7. Verify results

```bash
find local_artifacts/phase7/checkpoints -type f -name '*.json' | sort
find local_artifacts/phase7 -type f -name 'phase7_report.json' -print

uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run python -m compileall -q src tests
uv lock --check
```

Review the final report for:

- `prospective_holdout_status: LOCKED_UNUSED`,
  `prospective_holdout_used: false`,
  `prospective_holdout_evaluation_authorized: false`, and
  `july_2026_used: false`;
- registry, `dual_universe_v2`, core-universe, expansion-policy, and fold
  membership identities;
- separately labeled `CORE` and `EXPANDING` scorecards;
- the persisted `fold_active_symbols` source, age, liquidity, quality, and
  reason records, with no pre-listing or future-survival admission;
- all required fold/architecture reports or explicit ineligibility reasons;
- micro, macro, per-coin, per-cluster, cold-start age-bucket, coverage,
  cross-sectional IC, and matched-architecture comparisons;
- no-trade cases, cost stress, and concentration; and
- a research-only conclusion with no live model approval.

Do not call the cloud research complete if required checks or artifacts are
missing.

## 8. Back up completed outputs

```bash
gcloud storage rsync --recursive \
  ./local_artifacts/phase7 \
  "${PHASE7_CLOUD_STORAGE_ROOT}/local_artifacts"

gcloud storage rsync --recursive \
  ./data/gold/phase7 \
  "${PHASE7_CLOUD_STORAGE_ROOT}/gold"

gcloud storage rsync --recursive \
  ./data/phase7 \
  "${PHASE7_CLOUD_STORAGE_ROOT}/data"
```

List the destination and spot-check sizes before stopping the VM:

```bash
gcloud storage ls --recursive "${PHASE7_CLOUD_STORAGE_ROOT}/**"
```

## 9. Stop the existing VM

Exit SSH, then run locally:

```powershell
gcloud compute instances stop $env:PHASE7_GCP_VM `
  --project $env:PHASE7_GCP_PROJECT `
  --zone $env:PHASE7_GCP_ZONE
```

Stopping the VM is mandatory after verification and backup. This Phase 7 batch
job does not authorize Cloud Run, GKE, Vertex endpoints, background services,
account access, leverage, or order submission.

## Optional later context-data maintenance

This is a separate operation after the baseline, not a Phase 7 training step.
Restore the validated context directory before collecting so retries reuse
existing versions:

```bash
export CONTEXT_CLOUD_STORAGE_ROOT="gs://<existing-bucket>/data/context"
gcloud storage rsync --recursive \
  "${CONTEXT_CLOUD_STORAGE_ROOT}" ./data/context

uv run crypto-ai context status
uv run crypto-ai context fear-greed --plan
uv run crypto-ai context oi --plan --symbol BTCUSDT

export CRYPTO_AI_ALLOW_CONTEXT_NETWORK=1
uv run crypto-ai context fear-greed fetch
uv run crypto-ai context oi recent --symbol BTCUSDT
uv run crypto-ai context oi snapshot --symbol BTCUSDT
unset CRYPTO_AI_ALLOW_CONTEXT_NETWORK

uv run pytest tests/context
gcloud storage rsync --recursive \
  ./data/context "${CONTEXT_CLOUD_STORAGE_ROOT}"
```

Do not set the Phase 7 cloud-research guard for this maintenance, create a new
bucket, add credentials, schedule a daemon, or feed the resulting columns into
the current baseline.
