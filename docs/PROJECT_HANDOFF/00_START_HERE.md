# Crypto 2.0

> **VERIFIED CURRENT STATE — PROJECT ON HOLD.** Do not start the VM or training from this
> document. The first future engineering task is to profile and checkpoint Fold-1 matrix
> preparation, not to rerun discovery, acquisition, Gold, or all 16 folds.

## What this project is

Crypto 2.0 is a production-oriented AI/ML research system for Binance USD-M perpetual-futures
market intelligence. It is not merely a price predictor. The intended chain is:

```text
data → validation → features → targets → models → walk-forward evaluation
→ calibration → NO_TRADE → research economics → risk → paper/shadow → future execution
```

Only the research portion through an incomplete Phase 7A Fold 1 exists today. Account access,
paper trading, risk automation, leverage control, and live execution are not implemented or
authorized.

## Current project status

The authoritative freeze is [20_CURRENT_STATE.md](20_CURRENT_STATE.md), based on the hold record
at Git baseline `b641e8b914a27f6b9a00ae4be7a2cbd75a02d9ed` and a read-only GCP check on
2026-09-06.

| Item | Verified state |
| --- | --- |
| Phase | Phase 7A `CORE20_PRIMARY`; **PROJECT ON HOLD** |
| Discovery | 507/507 complete |
| Acquisition | Complete; data checkpoint valid |
| Gold | 7/7 complete; 138 partitions; 50,352,548 rows |
| Fold 1 | `STARTED_NOT_COMPLETE`; 0/48 specifications; 0 serialized models |
| Folds | 0/16 complete; Fold 2 never started |
| Qualification | Not yet evaluable; qualified model `NONE` |
| July 2026 | Unused exclusion buffer |
| August | `LOCKED_UNUSED`; `used=false`; `evaluation_authorized=false` |
| Paper/live/Phase 8 | Not started |
| VM | `crypto-phase7` is `TERMINATED`; keep it terminated |

Gold exists only on the stopped VM's persistent boot disk. Do not delete the VM: that disk is
configured with `autoDelete=true`.

## Most important instruction

Do **not** immediately restart training. Approximately 6h21m of Fold-1 pipeline compute across
interrupted attempts produced no durable model/report because the expensive pre-estimator
preparation has no reusable checkpoint. Profile it, add an atomic identity-safe prepared-matrix
cache, prove scientific equivalence, and only then run one Fold 1 under explicit owner cost
authorization. See [21_FOLD1_PREPARATION_BOTTLENECK.md](21_FOLD1_PREPARATION_BOTTLENECK.md).

## Quick architecture

Official Binance archives/REST are checksummed into immutable Bronze. Quality gates and lifecycle
evidence promote trusted data to Silver. Registry and discovery evidence determine a causal,
survivorship-protected universe. Gold contains model-ready features and
`multiasset_targets_v2`. Sixteen rolling chronological folds use actual `label_end_time` purge,
a 120-minute embargo, train-only preprocessing, Validation, Cal-A, Cal-B, and frozen TEST
release. G0/C0/P0/H0 LightGBM regressors generate expected-return estimates. Cal-B selects
cost-aware thresholds; observations below the hurdle become `NO_TRADE`. Research economics
charge configured fees, spread, and slippage. Risk/execution remain future work.

The current A6 model schema has 109 columns: 54 native 5m/cross-asset/derivative columns plus 22
completed 12h and 33 completed 1d columns. The frozen contract's “54 features” means the native
count; do not confuse it with Gold's wider schema.

## Quick technology stack

Python 3.11+; `uv`/`uv.lock`; PyArrow and Parquet; NumPy; LightGBM; scikit-learn; joblib; Pydantic;
httpx; pytest; Ruff; TOML/JSON; Git; Bash/PowerShell; tmux/systemd operational tooling; Google
Compute Engine, persistent disk, and GCS. DuckDB, Polars, Spark, CatBoost, XGBoost, and neural
models are not current Phase 7A dependencies. Exact locked versions are in
[DEPENDENCY_SNAPSHOT.md](DEPENDENCY_SNAPSHOT.md).

## Quick resume sequence

1. Read this complete package and the root `PROJECT_CONTEXT.md`/`AGENTS.md`.
2. Verify `main`, `origin/main`, and annotated tag `crypto2.0-handoff-20260906`.
3. Check current GCP resource and billing state without starting anything.
4. Obtain explicit owner authorization and a new runtime/cost budget before starting the existing VM.
5. Validate data and Gold checkpoints/hashes; do not trust presence alone or recompute valid work.
6. Prove July and August remain unused and holdout flags remain locked.
7. Profile the pre-estimator path and add a content-addressed, atomic prepared-matrix checkpoint.
8. Run tests on Linux and prove cached/uncached scientific equivalence.
9. Run exactly one Fold 1 with one worker and independent shutdown guards.
10. Measure real runtime/cost; the owner decides whether folds 2–16 proceed.

The full procedure is [29_ONE_YEAR_RESUME_RUNBOOK.md](29_ONE_YEAR_RESUME_RUNBOOK.md).

## Documents to read next

1. [01_PROJECT_VISION_AND_GOALS.md](01_PROJECT_VISION_AND_GOALS.md)
2. [02_SYSTEM_ARCHITECTURE.md](02_SYSTEM_ARCHITECTURE.md)
3. [03_TECH_STACK.md](03_TECH_STACK.md)
4. [04_REPOSITORY_MAP.md](04_REPOSITORY_MAP.md)
5. [05_DATA_ARCHITECTURE.md](05_DATA_ARCHITECTURE.md)
6. [06_UNIVERSE_AND_CORE20.md](06_UNIVERSE_AND_CORE20.md)
7. [07_FEATURE_ENGINEERING.md](07_FEATURE_ENGINEERING.md)
8. [08_TARGETS_AND_LABELS.md](08_TARGETS_AND_LABELS.md)
9. [09_MODEL_ARCHITECTURE.md](09_MODEL_ARCHITECTURE.md)
10. [10_TRAINING_AND_WALK_FORWARD.md](10_TRAINING_AND_WALK_FORWARD.md)
11. [11_PHASE7A_EXPERIMENT.md](11_PHASE7A_EXPERIMENT.md)
12. [12_MODEL_EVALUATION_AND_QUALIFICATION.md](12_MODEL_EVALUATION_AND_QUALIFICATION.md)
13. [13_BACKTEST_AND_ECONOMICS.md](13_BACKTEST_AND_ECONOMICS.md)
14. [14_RISK_AND_EXECUTION_ROADMAP.md](14_RISK_AND_EXECUTION_ROADMAP.md)
15. [15_GCP_INFRASTRUCTURE.md](15_GCP_INFRASTRUCTURE.md)
16. [16_CHECKPOINT_AND_RESUME.md](16_CHECKPOINT_AND_RESUME.md)
17. [17_MAJOR_BUGS_AND_FIXES.md](17_MAJOR_BUGS_AND_FIXES.md)
18. [18_GIT_HISTORY_AND_COMMITS.md](18_GIT_HISTORY_AND_COMMITS.md)
19. [19_PHASE_HISTORY.md](19_PHASE_HISTORY.md)
20. [20_CURRENT_STATE.md](20_CURRENT_STATE.md)
21. [21_FOLD1_PREPARATION_BOTTLENECK.md](21_FOLD1_PREPARATION_BOTTLENECK.md)
22. [22_RUNTIME_AND_COST_HISTORY.md](22_RUNTIME_AND_COST_HISTORY.md)
23. [23_SECURITY_AND_SECRETS.md](23_SECURITY_AND_SECRETS.md)
24. [24_COMMAND_REFERENCE.md](24_COMMAND_REFERENCE.md)
25. [25_CONFIGURATION_REFERENCE.md](25_CONFIGURATION_REFERENCE.md)
26. [26_TESTING_AND_VALIDATION.md](26_TESTING_AND_VALIDATION.md)
27. [27_ARCHITECTURE_DECISIONS.md](27_ARCHITECTURE_DECISIONS.md)
28. [28_GLOSSARY.md](28_GLOSSARY.md)
29. [29_ONE_YEAR_RESUME_RUNBOOK.md](29_ONE_YEAR_RESUME_RUNBOOK.md)
30. [30_INSTRUCTIONS_FOR_FUTURE_AI.md](30_INSTRUCTIONS_FOR_FUTURE_AI.md)

Navigation aids: [FILE_INDEX.md](FILE_INDEX.md),
[DEPENDENCY_SNAPSHOT.md](DEPENDENCY_SNAPSHOT.md), machine-readable
[project_context.json](project_context.json), and [HANDOFF_MANIFEST.json](HANDOFF_MANIFEST.json).
