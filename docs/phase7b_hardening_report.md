# Phase 7B hardening report

Written by Claude on 2026-11-02/03 for the Crypto 2.0 owner. Branch `fix/phase7b-hardening-20261102`,
built on `fix/phase7a-scientific-reconciliation-20261101` (`a99f14c`) plus the owner's commit
`5d66ba2`. Every changed line carries a "CHANGED BY CLAUDE" comment and, where code was replaced,
the old code is kept beside it as a comment.

**What was and was not run.** On the owner's Mac `.venv` (Python 3.12), after Phase 3 was wired in:
`pytest` gave 1150 passed (1136 after Phase 2 plus 14 new Phase 3 tests), `ruff check` passed and
`ruff format --check` reported all 684 files formatted. `verify_linux` reports "Linux required" on
a Mac and must be run on RunPod. No training, no data download, no August/July access, no Silver
restore. `git fetch` is blocked from the sandbox, so the branch has not been compared with GitHub.

## Phase 2: findings

| ID | Status | What changed | Tests |
| --- | --- | --- | --- |
| M-06 | Fixed | `PostTrainDataGapError` (a `ValueError`, not `IneligibleFoldError`) names fold, symbol, interval, partition and gap range. `readiness.gap_census` lists every fold with `can_run`; with Silver missing it uses gaps observed in Gold timestamps and labels the source. | `test_phase7b_gap_census.py`, `test_membership_gap_causality.py` |
| M-01 | Test added, no fix needed | Perturbing label values and label end times after a fold's TRAIN end leaves all context columns unchanged. | `test_phase7b_m01_label_perturbation.py` |
| M-02 | Fixed | `release_test` logs every TEST release (rows, feature-time range, identity), re-checks an `expected_identity` re-derived from the live model/calibrator/thresholds, and refuses a consumer that re-reads TEST under a different identity. `test_used_for_selection` is measured. Limit: the check proves ordering within a process, not that no other code read the fold's TEST table. | `test_phase7b_test_access.py` |
| L-01 | Fixed | Zero actuals leave the directional-accuracy denominator; `n_zero_actuals` reported. Phase 4.1/5 bootstrap code left alone (immutable results). | `test_phase7b_directional_accuracy.py` |
| L-03 | Fixed (opt-in) | Method chosen on the last 25% of Cal-A, chosen method refit on all of Cal-A. Default off in `fit_calibrator` so Phase 5 reproduces; Phase 7 training turns it on. The fraction is a module constant, not a config key (see below). | `test_phase7b_calibration_heldout.py` |
| L-04 | Documented, not fixed | H0 corrections are fit on the early-stopping Validation set. A separate slice needs new fold structure. Recorded in model metadata as `hybrid_correction_source` (after the model identity is computed, so identities are unchanged). | covered by existing H0 tests |
| L-05 | Fixed | `check_calibration_separation` uses max/min. | `test_phase7b_calibration_separation.py` |
| L-06 | Fixed | One `durable_fsync` helper (`F_FULLFSYNC` on macOS, `os.fsync` elsewhere) used by artifacts, run lease and prepared cache. | `test_phase7b_durable_fsync.py` |
| L-07 | Fixed | Four production `assert`s became explicit `ValueError`s; a test scans all of `src/` for `assert`. | `test_phase7b_no_asserts_in_source.py` |
| L-08 | Fixed | `model_registry.py` keeps a SHA-256 outside the model folder (`~/.crypto_ai/model_hash_registry`, or `PHASE7_MODEL_HASH_REGISTRY`). `load_model` refuses a mismatch before unpickling. Set `PHASE7_REQUIRE_MODEL_REGISTRY=1` to also refuse unregistered models. **On RunPod set the registry path to the persistent volume, outside the model folder.** Local trust model only; not a signature. | `test_phase7b_model_hash_registry.py` |
| L-09 | Fixed (docs) | README: current branch note, historical labels, `verify_linux` note, RunPod flow. | n/a |
| M-08 | Header + test, proposal below | LEGACY header on `live_trader.py`, `coinswitch_client.py`, `main_trader.py` (first line only). Import-isolation test widened to phase5/phase6/research/phase7. | `test_live_order_isolation.py` |
| L-10 | Report only | See below. | n/a |

## Phase 3: additive improvements

All settings live in `crypto_ai.phase7.hardening.HardeningConfig`, optionally overridden by a TOML
file named in `PHASE7_HARDENING_CONFIG` (shipped defaults: `configs/phase7/hardening_v1.toml`).
They are deliberately **not** in the frozen Phase 7 config, because new keys there change the
config hash `93f987736b1a79d26b773957` and invalidate every prepared cache.

| Key | Default | Effect |
| --- | --- | --- |
| `console_table` | true | One readable line every `PHASE7_METRICS_EVERY` (25) rounds: round, train/val L2, MAE, RMSE, directional accuracy, fixed-threshold precision/recall (labelled validation only), trend flag. The JSON lines in `fit-*.jsonl` are unchanged. |
| `console_precision_recall` | true | Adds `fixed_precision`/`fixed_recall` after the existing metrics (L2 still drives early stopping). |
| `fixed_threshold_bps` | 5.0 | A signal is `|prediction|` at or above it; a real move is `|actual|` at or above it. |
| `metric_max_rows` | 1,000,000 | Strided subsample cap for the live precision/recall. |
| `baseline_ridge_alpha`, `baseline_max_rows` | 1.0, 500,000 | Ridge baseline on a strided TRAIN subsample. |
| `abort_after_worse_checks` | 0 (off) | Abort a fit after N consecutive checks with validation RMSE above the zero-return baseline. |
| `stop_file_name` | `STOP_PHASE7` | If this file appears in the run directory the run stops cleanly **between specs**; the current fit finishes and its report is written; a `training_summary_partial.json` is written. |
| `fold_gate_folds` | 0 (off) | After folds 1..N stop if no spec beat the zero baseline on validation. |
| `pilot_horizon_minutes`, `pilot_target_type` | 0, "" (off) | Set both to run one horizon × one target type. |
| `success_min_net_positive_folds`, `success_min_beats_baseline_folds` | 10, 10 | **Placeholders.** Confirm or change before training; do not edit after seeing results. |
| `success_alpha`, `multiple_testing_correction` | 0.05, bonferroni | Specs are ranked on validation skill only; p-values are multiplied by the number of specs tried. |

Other Phase 3 behaviour:

- **Per-fold baselines** (`report["phase7b"]["baselines"]`): zero-return and Ridge scored on the
  same covered validation rows as LightGBM.
- **Decision step** (`report["phase7b"]["decision"]`): LONG/SHORT/NO_TRADE signals from the frozen
  Cal-B thresholds, per-side precision/recall/F1. These are signal-level (before the non-overlap
  execution filter); a LONG is correct when the actual return beat the round-trip cost.
- **Trading metrics:** profit factor, per-trade Sharpe (not annualized), max drawdown, fees and
  slippage fill the fold-report fields that were hard-coded `None`. ROC-AUC, PR-AUC and Brier stay
  empty: the model is a regressor.
- **Funding is not modelled anywhere in the pipeline.** Fees, spread and slippage are applied
  inside `net_return`; funding is not. It is reported as `NOT_MODELLED`. No cost was invented.
- **Results table:** `phase7b_results.csv`, one row per fold × spec, in the run's report root.
  Specs restored from a checkpoint on resume do not re-append a row.
- **End-of-run summary:** `python -m crypto_ai.phase7.hardening <phase7b_results.csv>` prints the
  corrected ranking and the pass/fail against the written criteria. It is not called automatically.
- **Silver:** training from Gold prints a warning when Silver is absent; the Gold rebuild stage
  fails with `SilverMissingError`. Gold-only validation is unaffected.

## Deliberately not changed

Model type, features, targets, horizons, fold definitions, Core20, the frozen config, any Phase
1-6 artifact, the legacy trading code beyond a header, and the 48-spec scope. No data was moved,
downloaded or rebuilt. Source-file hashes that feed prepared-cache/checkpoint identity changed
(`folds.py`, `training.py`, `calibration.py`, ...): **any cache or checkpoint built before this
branch is invalid** (none valid exists today).

## Proposals awaiting your decision

1. **M-08, move the order-capable legacy code** (`main_trader.py`, `main_signal.py`, `dashboard.py`,
   `pipeline/`, `phaseA/`, `data/`, `extra/`) to a separate repository or an archive branch, leave a
   one-line pointer in the README, and delete nothing from history. Codex's note in `pyproject.toml`
   says these files' bytes should be preserved; the move preserves them. Until then the header and
   the import-isolation test are the guard.
2. **L-10, consolidate the inference modules.** `data/inference.py` and `pipeline/inference.py`
   (515 and 517 lines) differ only in the "Scenario C: profitable long" rule. `data/` takes a long
   only when `sig_thresh <= p_long <= strong_thresh` and never marks it strong; `pipeline/` takes
   any long at or above `sig_thresh` and marks it strong at or above `strong_thresh`. Only
   `main_signal.py` imports the `pipeline/` one; Phase 7 uses neither. Plan: pick the intended rule
   with the owner, keep one file, add a test, then remove the other in a separate approved change.
3. **Silver decision:** `[ ] Silver restored` or `[ ] Gold is the source of truth`. Pending. Until
   chosen, Gold rebuild/audit-from-Silver commands are blocked by design.
4. **Success criteria:** confirm or change the placeholder numbers above before any training.

## Commands for the next step (not executed)

On RunPod, after pushing the branch and following the prerequisites in
`docs/PHASE7A_RECONCILIATION_2026_11_01.md`:

```bash
git checkout fix/phase7b-hardening-20261102
uv sync --locked --extra dev
uv run pytest -q && uv run ruff check . && uv run ruff format --check .
uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" --output-root "$PWD/.pytest-linux-verification"
export PHASE7_MODEL_HASH_REGISTRY=/workspace/crypto2-persistent/model_hash_registry
uv run python -m crypto_ai.phase7.readiness --config configs/phase7/research_core20_primary_v1.toml \
  --run-root "$PHASE7_ARTIFACT_ROOT/phase7a-core20-primary-93f987736b1a79d26b773957"
```

Smoke run (one model; needs your approval): the one-model preparation and training commands in the
reconciliation doc, with `PHASE7_METRICS_EVERY=25` so the console table prints.

Pilot (one horizon × one target across all 16 folds; needs your approval): copy
`configs/phase7/hardening_v1.toml`, set `pilot_horizon_minutes = 60`,
`pilot_target_type = "raw"` (use the exact target-type string from `ExperimentSpec`), optionally
`fold_gate_folds = 3` and `abort_after_worse_checks = 3`, then
`export PHASE7_HARDENING_CONFIG=<copy>` before the multi-fold entry point
(`scripts/run_phase7a_pipeline.py` / the worker script). Confirm that entry point's exact flags on
RunPod before the first paid run. To stop cleanly: `touch "$RUN_ROOT/STOP_PHASE7"`. When the run
ends: `uv run python -m crypto_ai.phase7.hardening <report-root>/phase7b_results.csv`.
