# Command Reference

> **WARNING — VERIFY COST AUTHORIZATION BEFORE STARTING VM/TRAINING.** The project is on hold.
> Commands in the status sections are read-only. No command here grants authorization.

## Local PowerShell — safe inspection

```powershell
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
git show crypto2.0-handoff-20260906 --no-patch
uv --version
uv sync --extra dev
uv run crypto-ai phase7-research --config configs/phase7/research_core20_primary_v1.toml --validate-config
uv run crypto-ai phase7-research --config configs/phase7/research_core20_primary_v1.toml --plan
```

The last two operations are safe config/plan modes and must report no network/private API use.
Do not run the heavy cloud command on the laptop.

## Tests and Ruff

```powershell
uv run pytest
uv run pytest tests/phase7 tests/operations/test_phase7_vm_supervisor.py
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
git diff --check
```

Run the full canonical gate on Linux after any Linux-specific operational change.

## GCP read-only status

```powershell
gcloud compute instances describe crypto-phase7 --project=crypto-ai-trading-506300 --zone=asia-south1-a
gcloud compute disks describe crypto-phase7 --project=crypto-ai-trading-506300 --zone=asia-south1-a
gcloud storage buckets describe gs://crypto-ai-data-83921 --project=crypto-ai-trading-506300
gcloud storage ls gs://crypto-ai-data-83921/artifacts/phase7/project-hold-20260906/
```

Do not start, stop, delete, resize, snapshot, or create resources without explicit owner authority.

## GCP SSH and VM repository — only after authorized start

```powershell
gcloud compute ssh crypto-phase7 --project=crypto-ai-trading-506300 --zone=asia-south1-a
```

Inside the VM:

```bash
cd /home/nssharath123/crypto2.0
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
pgrep -af 'run_phase7a_pipeline|crypto-ai.*phase7|phase7a_vm_supervisor'
tmux ls
systemctl list-units --type=service --all | grep -i phase7
journalctl --no-pager -u '<verified-phase7-unit>' -n 200
df -h
free -h
```

The quoted unit name must be discovered, not guessed. `pgrep` can show wrapper/supervisor
processes; determine **logical** workers using the repository supervisor rules before acting.

## Canonical Phase 7 files

```text
configs/phase7/research_v1.toml                 full CORE+EXPANDING study
configs/phase7/research_core20_primary_v1.toml  Phase 7A CORE-only operational scope
scripts/run_phase7a_pipeline.py                 Phase 7A scoped runner
scripts/run_phase7a_worker.sh                   guest worker wrapper
scripts/phase7a_vm_supervisor.py                guest supervisor
scripts/phase7a_feasibility_gate.py             Fold-1 budget gate
scripts/phase7a_control_plane_watchdog.ps1      independent control-plane guard
```

No long/expensive launch command is provided intentionally. Before any launch, follow
[29_ONE_YEAR_RESUME_RUNBOOK.md](29_ONE_YEAR_RESUME_RUNBOOK.md), inspect current scripts/config,
obtain a new owner budget, and construct a fresh deadline authority. Never reuse incident scripts
or expired authorities.
