# Crypto 2.0: training-code audit (2026-11-06)

Audited tip: `687e697` on `fix/phase7a-final-scientific-hardening-20261106`. Labels: CODE-VERIFIED =
read in source this session or earlier sessions of this engagement; INFERENCE; OPINION. I did not
execute training and the Mac test runner was offline, so nothing here is TEST-EXECUTED on the tip.

## Verdict: TRAINING_CODE_CORRECT_WITH_MINOR_ISSUES (with three stated limits)
Limits: (1) never run end-to-end on real data in this audit; (2) M-01 edge size not measured;
(3) not every one of the 109 feature formulas was re-derived line by line (HTF completeness and
target timing were).

## Timing (CODE-VERIFIED, `phase7/targets.py`, `phase6/labels.py`)
- `feature_time = open_time[i] + 5m` (= open of bar i+1; bar i is complete).
- `entry_offset = 1 + decision_latency_bars` -> entry at `open[i+2]` for the default of 1 latency bar;
  a hard check requires `entry_time == feature_time + 5m`.
- `label_end = open[i + entry_offset + steps]`; raw return `open[label_end] / open[entry] - 1`.
- Rows need `consecutive >= target_offset` bars (no label across a gap) and `label_end < cutoff`.
- Horizons 15/30/60/120 min = 3/6/12/24 steps. Embargo 120 min; purge uses `label_end_time`.
Assessment: matches the stated formula. Entry one full bar after the decision is conservative
against realistic API latency (seconds). Residual: fills at the open price with no spread/queue
effects other than the flat tier costs.

## What enters each stage
| Stage | Rows | Owner of the data |
| --- | --- | --- |
| LightGBM fit | Train only | Train |
| Early stopping + (H0) correction | Validation | Validation (H0 shares it: L-04, documented) |
| Calibrator | Cal-A (method picked on last 25% of Cal-A, refit on all) | Cal-A |
| Thresholds | Cal-B, non-overlapping per-symbol policy, min 30 trades | Cal-B |
| Final metrics | Test, released once under a frozen identity | Test |
Test access is logged and the frozen identity is re-derived before release (CODE-VERIFIED, M-02).

## LightGBM parameters (CODE-VERIFIED in `config.ModelConfig`, `models.lightgbm_estimator_parameters`)
Reference: [LightGBM Parameters Tuning](https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html) (LEVEL B).
| Parameter | Value | Rating | Comment |
| --- | --- | --- | --- |
| objective | regression (L2) | QUESTIONABLE | Squared loss is dominated by heavy-tailed returns; no winsorisation was verified. Huber/clipped target is a candidate ablation, not a blocker |
| boosting | gbdt (default) | DEFAULT_BUT_ACCEPTABLE | |
| learning_rate | 0.02 | GOOD | Small step suits noisy targets |
| n_estimators | 500 (max 2000) | QUESTIONABLE | With lr 0.02 the cap may bind before the validation optimum on easy folds; early stopping decides |
| num_leaves | 31 | DEFAULT_BUT_ACCEPTABLE | |
| max_depth | -1 | DEFAULT_BUT_ACCEPTABLE | |
| min_child_samples | 100 | **POOR for this data size** (INFERENCE) | Millions of low-SNR rows; 100 samples per leaf lets leaves fit noise. Typical guidance for noisy tabular data is far larger; treat as a sensitivity axis |
| subsample / freq | 0.9 / 1 | GOOD | |
| colsample_bytree | 0.9 | DEFAULT_BUT_ACCEPTABLE | Many correlated features; 0.5-0.7 would add diversity (sensitivity axis) |
| reg_alpha / reg_lambda | 0.1 / 1.0 | QUESTIONABLE | Weak for noisy returns |
| early_stopping_rounds | 50 | GOOD | with lr 0.02 reasonable; first_metric_only on L2 |
| seed | `random_state=42` only | QUESTIONABLE | One seed hides variance; bagging/feature seeds derive from it |
| deterministic / force_col_wise | CPU only | GOOD | GPU path is "scientifically, not bitwise" reproducible and records it |
| max_bin, min_gain_to_split, min_sum_hessian | defaults | DEFAULT_BUT_ACCEPTABLE | |
| categorical / monotone constraints | none; symbol-id only as an ablation | GOOD | |
| sample weights | optional symbol-balanced weights | UNJUSTIFIED until compared | exists as a compare option |
Not claimed: that these values are wrong. Hyperparameters were not tuned and no evidence says they are optimal.

## Findings specific to the training path
1. (MEDIUM) One seed per spec; seed variance is invisible. 2. (MEDIUM) L-04: H0 correction fit on the early-stopping set. 3. (MEDIUM) M-01 residual: rows removed by Gold's label inner join near series ends are not counted. 4. (LOW) results table lacks seed, fit seconds, best iteration columns. 5. (LOW) CPU vs GPU equivalence untested. 6. (INFO) Source-hash cache identity means any further code edit invalidates caches: freeze code before the first paid run.

## Model choice (OPINION, with evidence in the literature file)
Keep LightGBM as the primary model family, and add a Ridge baseline (already in the code) and
a simple cross-sectional-rank baseline. Do not add deep sequence models before a baseline signal exists.
