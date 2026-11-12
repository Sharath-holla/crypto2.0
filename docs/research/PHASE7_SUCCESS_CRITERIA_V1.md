# Phase 7 success criteria v1 (FROZEN before any result is read)

Written by Claude (2026-11-06, IA-01/IA-03). Status: **FROZEN**. Do not edit after looking at
results; supersede with a new versioned file instead.

## 1. What a number is allowed to claim

| Class | Meaning | Example |
|---|---|---|
| `DEVELOPMENT_METRIC` | computed on data the fit or its early stopping saw | validation RMSE, validation IC |
| `SELECTION_METRIC` | used to choose a spec, threshold or calibrator | Cal-B expectancy of a threshold |
| `INDEPENDENT_EVALUATION_METRIC` | computed on data no earlier choice used | a TEST fold that no development fold re-used |

Validation is the early-stopping set, so it is **always** a development metric. Rolling folds
re-use calendar time (fold 0 TEST = fold 2 VALIDATION), so any TEST month that a later fold used as
VALIDATION/CAL is also a development month for every selection made on those later folds.

## 2. Inference

No p-values, confidence statements or "passes Bonferroni" claims are produced from development
metrics. `hardening.descriptive_ranking` returns `inference_status = NOT_INDEPENDENT` and
`p_values = NOT_APPLICABLE`. `hardening.evaluate_success` returns `DESCRIPTIVE_ONLY` and
`qualifies_as_independent_evidence = False`.

## 3. Selection protocol

A winner may be called *confirmed* only if `selection_chronology.build_selection_protocol` accepts
the split of folds into DEVELOPMENT folds and EVALUATION folds: every evaluation-fold TEST window
starts at or after the latest development TEST end, the protocol is written once to
`selection_chronology.json` (immutable, tamper-evident) and the holdout stays
`LOCKED_UNUSED` (August: `used=false`, `evaluation_authorized=false`).

## 4. Descriptive criteria (reported, never a certificate)

Computed per spec over a complete, duplicate-free, single-identity set of COMPLETE fold rows:
number of folds with net-positive fixed-policy TEST expectancy, number of folds beating the Ridge
baseline on validation, mean/median/worst fold, fraction positive. Defaults
(`configs/phase7/hardening_v1.toml`): at least 10 net-positive folds and 10 baseline-beating
folds. These are *descriptive screening thresholds*, not evidence of an edge.

## 5. Smoke run (one CPU fold, one spec) - ENGINEERING criteria only

Amended 2026-11-06 (closure) BEFORE any model result exists; the amendment only separates
engineering criteria from scientific ones. Purpose: `REGRESSION_PLUMBING_AND_PIPELINE_SMOKE`
(never `EDGE_DISCOVERY` or `PROFITABILITY_CONFIRMATION`).

Spec `architecture-G0-A6-60m-raw`, Fold 1 (fold index 0), CPU backend, one worker.

The smoke SUCCEEDS if and only if all of these hold:

1. inputs are verified (Gold hash/manifest verification PASS, cache identity matches, holdout
   `LOCKED_UNUSED`, admission record `ADMITTED`);
2. the prepared data are valid (row counts, finite masks, feature/target order, NumPy-vs-Arrow
   agreement);
3. the fit executes to completion on CPU;
4. all predictions are finite;
5. metrics compute without error;
6. artifacts persist: model, report, ledger result record and receipt, CSV view that matches the
   ledger, checkpoint COMPLETE;
7. no invariant or leak-guard failure (no TEST use for any choice, no August/July access, no
   duplicate or mixed-identity result).

The smoke does NOT succeed or fail on profitability, IC, expectancy, or beating a baseline. A
negative or zero result is a valid smoke. It supports no scientific or tradability claim
(`economic_status = REGRESSION_PLUMBING_ONLY_NO_TRADABILITY_CLAIM`, funding `NOT_MODELLED`).

### 5a. Later pilot criteria (separate, NOT part of the smoke)

A pilot uses ONE spec precommitted in `configs/research/phase7_selection_chronology_v1.json`,
development folds 1-10, evaluation folds 11-16, and is judged only by sections 2-4 above. Nothing
in the smoke result may be used to choose that spec.

## 6. Non-claims

Net-of-cost results exclude funding (not modelled -> `FUNDING_NOT_MODELLED`), use static scenario
costs (not measured slippage), and report trade-level statistics, not portfolio Sharpe/drawdown.
