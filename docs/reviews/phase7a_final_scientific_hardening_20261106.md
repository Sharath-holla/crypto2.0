# Phase 7A final scientific hardening: readiness report (2026-11-06)

Written by Claude. Evidence labels: CODE-VERIFIED (read in source), DATA-VERIFIED (computed on the
local Gold copy), TEST-EXECUTED (ran under pytest on the owner's Mac), NOT-EXECUTED (written, not run).

## 1. Executive verdict

**NOT_READY_FOR_RUNPOD** (gates pending, not a known scientific defect). No known blocking leakage
was found, but the required gates are not yet proven on the current branch tip: the Mac test runner
was offline for the last three rounds, so pytest and ruff have NOT been run on the commits after
`a8efe3a` (that commit: 1150 passed, ruff clean). `uv sync --frozen` and `verify_linux` have never
been run on Linux. Once those pass, the verdict becomes READY_WITH_EXPLICIT_LIMITATIONS (section 22).

## 2. Starting branch and commit
`fix/phase7c-architecture-20261105` at `0eb9296` (contains reconciliation `a99f14c`, verified as an
ancestor; working tree clean apart from the untracked `Claude outputs/` helper folder).
Requested name `fix/phase7a-final-scientific-hardening-20261106` was created from that tip.

## 3. Ending branch and commits
Branch `fix/phase7a-final-scientific-hardening-20261106`: `d3c8da7` (metrics, baselines, results
columns, console line), `687e697` (resource estimator). Earlier this lineage: `a8efe3a`, `0eb9296`
and the Phase 7B/7C commits. Nothing pushed (GitHub is unreachable from the sandbox).

## 4-8. Findings: status, root cause, code, tests (see also `docs/phase7b_hardening_report.md`)

| Item | Status | Evidence |
| --- | --- | --- |
| A. environment / full suite | **PENDING** | Mac `.venv` suite last run at `a8efe3a` (TEST-EXECUTED); `uv` is not reachable from my sandbox; Linux gate never run |
| B. Silver / data lineage | **PARTIAL** | section 12-14 |
| C. M-01 label independence | **FIXED in code; residual not quantified** | label-perturbation test exists (TEST-EXECUTED earlier); horizon-invariance and fold-edge row counts NOT yet measured |
| D. M-02 test gate | **FIXED** | measured access ledger + identity re-derivation (`folds.release_test`, `training._run_one`) |
| E. M-06 gap census | **FIXED (tool); not run on real Silver** | needs the Mac venv + complete Silver |
| F. M-08 order isolation | **GUARDED** | LEGACY headers; static import-isolation test over phase5/6/7/research |
| G. L-01 zero actuals | **FIXED** | `directional_accuracy_nonzero`, `zero_actual_count`, `zero_actual_fraction` added (`d3c8da7`); old key kept |
| H. L-03 calibrator selection | **FIXED (opt-in, on in Phase 7)** | selects on the last 25% of Cal-A, refits on all Cal-A; Cal-B/Test untouched |
| I. L-04 H0 vs early stopping | **DOCUMENTED, NOT FIXED** | H0 corrections still fit on the early-stopping validation set; needs a new slice |
| J. L-05 overlap check | **FIXED** | max/min comparison |
| K. L-06 macOS fsync | **FIXED** | `durable_fsync` with `F_FULLFSYNC` |
| L. L-07 asserts | **FIXED** | explicit exceptions + source scan test |
| M. L-08 artifact trust | **FIXED (local trust)** | hash anchor outside the model folder, checked before unpickling |
| N. L-09 README | **PARTIAL** | branch, historical labels, RunPod flow; runbook not fully rewritten |
| O. L-10 inference duplicates | **DEFERRED** | diff documented; only `main_signal.py` imports one copy |
| P. Console monitoring | **DONE** | train/val RMSE+MAE, best val RMSE, rounds since improvement, elapsed, peak RSS, free disk; JSONL kept |
| Q. Precision/recall/F1 | **DONE at the right layer** | fixed-threshold monitoring (validation, labelled) and post-Cal-B action metrics |
| R. Baselines | **DONE** | zero + Ridge on identical rows: MAE, RMSE, directional (non-zero), Pearson, Spearman, deltas. Cross-sectional IC NOT in the validation baselines |
| S. Experiment gate | **DONE (opt-in)** | fold gate, abort rule (now handled cleanly), stop file, pilot filter; all validation-only |
| T. Multiple testing | **PARTIAL** | Bonferroni-corrected validation ranking; NO deflated Sharpe, PBO or SPA implemented |
| U. Results table | **DONE** | CSV with run id, config hash, code version, Gold id, status, baselines, deltas; seed, fit seconds and best iteration NOT yet columns |
| V. Costs | **CODE-VERIFIED** | fees/spread/slippage applied per trade (tier round trip 11/14/20 bps); funding NOT modelled; Sharpe/drawdown/profit factor now computed (were `None`) |
| W. Universe freeze | **NOT RE-AUDITED** | see audit docs |
| X. Holdout paths | **CODE-VERIFIED** | flags are constants; no August access path found in training; not exhaustively re-searched this round |
| Y. Cache identity | **CODE-VERIFIED** | identity binds ~50 source hashes, config hash, environment (OS/arch); a dedicated "context change invalidates cache" test was NOT added |
| Z. Concurrency | **EXISTING** | run lease, publication lock, atomic markers pre-exist; no new multiprocessing test added |
| Resource estimate | **DONE** | `python -m crypto_ai.phase7.resource_estimate` |

New defects found by me this week (all fixed): N-01 Ridge baseline NaN, N-02 unhandled
`FitAbortedError`, N-03 hardening settings not recorded in reports.

## 9-11. Tests executed
- TEST-EXECUTED on the Mac `.venv` at `a8efe3a`: `pytest` 1150 passed; `ruff check` and `ruff format --check` clean.
- NOT-EXECUTED under pytest/ruff since then: `test_phase7c_*`, `test_phase7a_final_*`, `test_phase7a_resource_estimate.py`. Their pure logic was executed in an isolated harness (Python 3.10 VM, stubbed imports) and passed. Ruff line length and import order were checked by hand only.

## 11. Linux status
LINUX_PENDING: `uv sync --locked --extra dev`, full pytest, `verify_linux`. MAC_PASS: only the suite at `a8efe3a`.

## 12-14. Data lineage (read-only, owner's Mac copy; the Lightning download was still running)
- **Gold** `gold-phase7-0cbf2910e8d96c9d19826598` (DATA-VERIFIED): 138/138 partition files exist and every SHA-256 matches the manifest (9.67 GB). 109 features, `multiasset_targets_v2`, `multiasset_features_v2`, 50,352,548 rows, cutoff 2026-07-01, holdout `LOCKED_UNUSED`, used=false, authorized=false, `july_2026_used` false.
- **Silver**: `data/phase7/silver/binance/{klines,manifests,versions}` present locally (592 manifest files, 577 version folders). NOT hash-verified and no per-fold gap census was run (needs the Mac venv). The download log's last entry (Nov 5 18:36 UTC) still showed ~48,868 files pending, so completeness is UNKNOWN.
- Bronze/market folders exist; not inspected further.

## 15-21. Holdout, M-01, test gate, cache, baselines, monitoring, economics
Holdout flags remain constants in `config.holdout_status_payload()`; no code path in training reads August. M-01 classification: **ACCEPTABLE_BOUNDED (provisional)**: fold context is built from all feature rows keyed by (symbol, feature_time) and verified against preview coverage, but the number of rows that Gold's label inner join removed near the end of each series was not measured, so it cannot yet be called NEGLIGIBLE. Test gate: measured, not literal. Economics: see section V.

## 22. Known remaining risks
Suite/Linux gates unproven on tip; Silver completeness unknown; L-04 H0 contamination; M-01 edge size unmeasured; funding not modelled; no deflated-Sharpe/PBO; success numbers are placeholders; cache invalidation on context change has no dedicated test; CPU vs GPU equivalence not tested.

## 23. Exact next steps (nothing was executed)
1. Mac: double-click the test runner, then `pytest -q`, `ruff check .`, `ruff format --check .` on this branch.
2. RunPod: `git checkout fix/phase7a-final-scientific-hardening-20261106 && uv sync --locked --extra dev && uv run pytest -q && uv run python -m crypto_ai.phase7.verify_linux --repository "$PWD" --output-root "$PWD/.pytest-linux-verification"`.
3. Estimate (read-only): `uv run python -m crypto_ai.phase7.resource_estimate --manifest "$PHASE7_GOLD_ROOT/<dataset>/manifest.json" --path /workspace`.
4. Only if 1-3 pass and you approve, the smoke run (not executed here), taken from `docs/PHASE7A_RECONCILIATION_2026_11_01.md`:
```
export PHASE7_CACHE_MODE=auto
uv run python -m crypto_ai.phase7.benchmark_one_spec --spec-id architecture-G0-A6-60m-raw \
  --output-root /workspace/crypto2-benchmark-isolated --execute --prepare-only
export PHASE7_CACHE_MODE=read_only PHASE7_METRICS_EVERY=25
uv run python -m crypto_ai.phase7.benchmark_one_spec --spec-id architecture-G0-A6-60m-raw \
  --output-root /workspace/crypto2-benchmark-isolated --execute
```
These commands are copied from the reconciliation document, not re-derived from the CLI after the changes; confirm with `--help` first.
