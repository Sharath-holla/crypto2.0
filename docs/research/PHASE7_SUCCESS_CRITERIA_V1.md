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

## 5. Smoke run (one CPU fold, one spec)

`architecture-G0-A6-60m-raw`, Fold 1. Pass = the pipeline completes with a COMPLETE, identity-stamped
result row, the result set validates (`result_integrity.validate_result_set`), no test access
violation, no holdout access, and finite metrics. A smoke run carries **no** scientific conclusion:
`PLUMBING_AND_SCIENCE_SMOKE_ONLY`.

## 6. Non-claims

Net-of-cost results exclude funding (not modelled -> `FUNDING_NOT_MODELLED`), use static scenario
costs (not measured slippage), and report trade-level statistics, not portfolio Sharpe/drawdown.
