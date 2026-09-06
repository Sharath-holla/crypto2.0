# Repository Map

```text
configs/                 versioned data/model/walk-forward/Phase 6/Phase 7 contracts
docs/                    architecture, ADRs, results, audits, runbooks, this handoff
scripts/                 cloud worker/supervisor/watchdog/benchmark utilities
src/crypto_ai/           installable production/research package
  data/                  canonical Binance acquisition and manifests
  quality/               source validation and Silver promotion
  features/, labels/     earlier phase feature/label families
  phase5/, phase6/       preserved completed research paths
  phase7/                current canonical multi-asset implementation
  phase7_2/              additive future research contracts, disabled by default
  contracts/             Phase 7.1B future-safe interfaces and baseline contracts
tests/                   unit/integration/adversarial tests
data/                    local generated Bronze/Silver/Gold; normally untracked
local_artifacts/         local experiment/checkpoint/report artifacts; normally untracked
models/, logs/, tmp/     generated/local runtime state; do not treat as source
pipeline/, phaseA/, extra/ preserved legacy prototype/audit code; not canonical execution
project_hold_20260906/   untracked local hold archive; preserve, do not stage wholesale
```

## Training-critical Phase 7 paths

- `src/crypto_ai/phase7/{config,registry,universe,features,targets,gold,folds,models,training,pipeline}.py`
- `configs/phase7/research_v1.toml` — full Phase 7 experiment.
- `configs/phase7/research_core20_primary_v1.toml` — separate Phase 7A scope.
- `configs/contracts/phase7_scientific_baseline_v1_9.json` and successor chain — frozen
  invariants/source fingerprint contract.
- `scripts/run_phase7a_pipeline.py`, `run_phase7a_worker.sh`, `phase7a_vm_supervisor.py`,
  `phase7a_feasibility_gate.py`, `phase7a_control_plane_watchdog.ps1` — reusable operations.

The detailed per-file guide is [FILE_INDEX.md](FILE_INDEX.md).

## Runtime/generated versus source

Tracked Python, TOML, JSON contracts, tests, and docs are source. Bronze/Silver/Gold Parquet,
checkpoints, model binaries, prediction tables, runtime authorities, PIDs, tmux state, temporary
patches, SSH material, and incident logs are generated or private operational data. They must not
be added with `git add .`. Stage documentation files explicitly.

The many existing untracked `.codex_*`, patch, audit, and `project_hold_20260906/` paths belong to
prior incidents/owner evidence. Preserve them unless separately authorized; they are not approved
canonical launch tools. `pipeline/live_trader.py`, `main_trader.py`, and `dashboard.py` are legacy
and must not be run.
