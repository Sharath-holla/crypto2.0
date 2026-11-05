# Phase 7C architecture review (read + targeted fixes)

Written by Claude on 2026-11-05/06. Branch `fix/phase7c-architecture-20261105`, on top of
`fix/phase7b-hardening-20261102` (`a8efe3a`). Every changed line has a "CHANGED BY CLAUDE" comment
and the old code is kept as a comment. No training, no data, nothing touching August or July.

## How much is verified (read this first)

- **The Mac test runner was not running** during this round, so the full suite was **not** re-run
  after these edits. Last full run (before Phase 7C): 1150 passed, ruff clean.
- What I did run: Python syntax checks on all edited files, the Ridge fix executed in isolation
  (finite with NaN input; byte-identical to the old formula on clean input), and the structural
  tests executed against the edited source. The new test files themselves have **not** been run
  under pytest yet.
- To finish: double-click `Start test runner (double-click once).command`, then I run `pytest -q`,
  `ruff check .` and `ruff format --check .` and commit.

## 1. Old audit items: re-checked against the source

All of these were already fixed by Phase 7A or 7B on this lineage; I confirmed it in the code, so
no change was needed: H-01 (Gold validator producer order, cherry-picked as `79c717b`), H-02
(portable launchers), H-03 (training scope is a parameter, not a monkey-patch), H-04 (grouped
`cross_section.py`, no per-timestamp full scan), M-01 (fold context built from all feature rows),
M-04 (stale publication lock), M-07 (date guard in `research_scope.py`), M-09 (OS and CPU
architecture bound into the environment identity), L-02 (`finite_row_accounting` in every report).

## 2. New defects found and fixed

| ID | Where | Problem | Fix | Test |
| --- | --- | --- | --- | --- |
| N-01 | `hardening._ridge_predict` (my Phase 3 code) | One NaN feature value made every Ridge weight NaN, so the Ridge baseline score became NaN and could poison the results CSV and ranking | Standardise ignoring missing values, set them to the training mean; clean data gives the identical result | `test_phase7c_ridge_nan.py` |
| N-02 | `training.py` run loop vs. `FitAbortedError` | The optional abort rule (`abort_after_worse_checks`) raises from inside the LightGBM callback; nothing caught it, so enabling it crashed the whole run with a stack trace | Caught around `_run_one`: stop cleanly, no report and no checkpoint for that spec (it retries on resume), partial summary names the spec | `test_phase7c_fit_abort_handled.py` (structural: the loop needs real fold data) |
| N-03 | Phase 7B settings vs. the frozen config hash | Pilot filter, fold gate, abort rule and thresholds change what a run does but are outside the config hash, so two runs could differ silently | Every report now records `phase7b.hardening_config` | same file |

Also corrected: the Phase 7B report said the results CSV is in "the run's report root"; it is
`<report-root>/<run>/models/phase7b_results.csv`.

## 3. Reviewed, no defect found

`economics.py` (threshold selection, non-overlap policy, cost stress) is consistent: the same
`_policy_indices` is used for Cal-B and out-of-sample, costs use the tier round-trip, thresholds
come only from Cal-B. `models._fit` early stopping: the train set is skipped by LightGBM's own
rule when passed as the first eval set; the equivalence test (I-02) already guards this.

## 4. Architecture improvements: proposals only (not done, need your decision)

1. **`training.py` is 2,100+ lines** (orchestration, cache handling, metrics, reporting). Splitting
   report assembly out of `_run_one` would make it testable without real data. Not done: it
   changes source hashes, so it must happen before the first paid run, and it is a restructure.
2. **A real loop-level test** for stop file, fold gate and abort rule using a tiny synthetic fold
   fixture. This needs a small fixture builder; worth doing before the pilot.
3. **Config home for Phase 7B settings.** They live outside the frozen config hash on purpose
   (so caches stay valid), and N-03 now records them. If you would rather have them inside the
   hash, that is a one-time cache reset: cheap now, expensive later.
4. Still open from before: M-08 (move legacy trading code), L-10 (two inference files), the
   Silver decision, and the placeholder success numbers.
