# Project File Index

`training-critical` means a change can alter Phase 7 rows, identities, models, reports, or runtime
safety. `generated` means it is produced at runtime and normally must not be committed.

| Path | Purpose / owner | Training-critical | Generated |
| --- | --- | --- | --- |
| `pyproject.toml`, `uv.lock` | Package/dependency contract | Yes | No |
| `AGENTS.md`, `PROJECT_CONTEXT.md` | Agent safety and handoff entry | Operational | No |
| `configs/phase7/research_v1.toml` | Full canonical Phase 7 config | Yes | No |
| `configs/phase7/research_core20_primary_v1.toml` | Separate Phase 7A config | Yes | No |
| `configs/contracts/phase7_scientific_baseline_v1_9.json` | Current frozen Phase 7 source/config identity | Yes | No |
| `configs/data/binance.toml` | Binance public source configuration | Yes | No |
| `configs/data_quality/default.toml` | Bronze→Silver quality gates | Yes | No |
| `src/crypto_ai/phase7/config.py` | Frozen config and identity validation | Yes | No |
| `src/crypto_ai/phase7/sources.py` | Official discovery/source manifest | Yes | No |
| `src/crypto_ai/phase7/registry.py` | Historical/current symbol registry | Yes | No |
| `src/crypto_ai/phase7/discovery_checkpoint.py` | Per-symbol discovery durability | Yes | No |
| `src/crypto_ai/phase7/segments.py` | Causal gap/lifecycle acquisition status | Yes | No |
| `src/crypto_ai/phase7/acquisition.py` | Archive/REST acquisition, reconciliation, Silver load | Yes | No |
| `src/crypto_ai/phase7/quality.py` | Data quality and causal descriptors | Yes | No |
| `src/crypto_ai/phase7/universe.py` | Core/expansion/fold membership | Yes | No |
| `src/crypto_ai/phase7/features.py` | Native/anchor/market/HTF features | Yes | No |
| `src/crypto_ai/phase7/targets.py` | `multiasset_targets_v2` and timing | Yes | No |
| `src/crypto_ai/phase7/gold.py` | Feature/target join and Gold chunks | Yes | No |
| `src/crypto_ai/phase7/folds.py` | Fold plan, split, cluster/tier fitting | Yes | No |
| `src/crypto_ai/phase7/models.py` | G0/C0/P0/H0 fitting/serialization | Yes | No |
| `src/crypto_ai/phase7/training.py` | Spec matrix, calibrate, threshold, OOS reports | Yes | No |
| `src/crypto_ai/phase7/metrics.py` | Phase 7 predictive/coverage metrics | Yes | No |
| `src/crypto_ai/phase7/economics.py` | Costs, thresholds, trades, stress | Yes | No |
| `src/crypto_ai/phase7/artifacts.py` | Atomic artifacts/checkpoints/batch scans | Yes | No |
| `src/crypto_ai/phase7/pipeline.py` | Cloud stage orchestrator | Yes | No |
| `src/crypto_ai/phase7/progress.py` | Side-effect-only reporting/projections | Operational | No |
| `src/crypto_ai/phase7/runner.py` | Safe plan/validate/dry-run | Operational | No |
| `src/crypto_ai/contracts/` | Phase 7.1B future interfaces, disabled execution | No baseline effect | No |
| `src/crypto_ai/phase7_2/` | Disabled future research contracts | No baseline effect | No |
| `scripts/run_phase7a_pipeline.py` | Phase 7A CORE/48-spec scope + budget behavior | Yes | No |
| `scripts/run_phase7a_worker.sh` | Linux guest worker entry | Operational | No |
| `scripts/phase7a_vm_supervisor.py` | Guest supervision/safe shutdown | Operational | No |
| `scripts/phase7a_feasibility_gate.py` | Fold-1 projection gate | Operational | No |
| `scripts/phase7a_control_plane_watchdog.ps1` | Independent deadline/termination guard | Operational | No |
| `scripts/benchmark_phase7_workload.py` | Synthetic/local workload benchmark | No result authority | No |
| `tests/phase7/` | Phase 7 scientific and artifact regressions | Verification | No |
| `tests/operations/test_phase7_vm_supervisor.py` | Supervisor logic | Verification | No |
| `tests/contracts/` | Baseline/noninterference contracts | Verification | No |
| `docs/DECISIONS.md` | ADR log | Reference | No |
| `docs/PHASE7_1_FEATURE_CATALOG.md` | Code-derived 109/54 feature catalog | Reference | No |
| `docs/PHASE7_UNIVERSE.md` | PIT universe design | Reference | No |
| `docs/PHASE7_MODEL_ARCHITECTURES.md` | Models/evaluation design | Reference | No |
| `docs/phase7/PHASE7A_PROJECT_HOLD_20260906.md` | Frozen Phase 7A evidence | Authoritative state | No |
| `docs/phase7/phase7a_hold_state_20260906.json` | Machine-readable hold state | Authoritative state | No |
| `docs/phase7/PHASE7A_RESUME_RUNBOOK.md` | Immediate resume safety | Operational | No |
| `data/bronze/`, `data/silver/`, `data/gold/` | Market/model datasets | Yes | Yes; do not Git-add |
| `local_artifacts/phase7/` | Checkpoints, models, reports, run state | Yes | Yes; do not Git-add |
| `project_hold_20260906/` | Local hold archive/bundles | Evidence | Yes/untracked; preserve |
| `.codex_*`, `*.patch`, logs, PID/authority files | Incident/transient tooling | No canonical authority | Yes; preserve, do not stage |
| `pipeline/`, `phaseA/`, `extra/` | Legacy prototype/audit material | Not current | Mixed; do not run live paths |
