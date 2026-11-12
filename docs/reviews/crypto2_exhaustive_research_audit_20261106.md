# Crypto 2.0: exhaustive research audit (2026-11-06)

Companion files (same folder): `crypto2_loophole_register_20261106.md`,
`crypto2_literature_comparison_20261106.md`, `crypto2_architecture_scorecard_20261106.md`,
`crypto2_training_code_audit_20261106.md`.

**Scope and honesty.** Audited tip `687e697`. This session had no training, no holdout access, no
orders. The Mac test runner was offline, so no pytest/ruff result exists for the tip. I read the
target, fold-context, economics, LightGBM-parameter, calibration, test-gate, hardening and results
code, hashed the local Gold copy, and surveyed the literature by search. I did NOT line-audit all
109 feature formulas, the universe-selection code, the acquisition/Silver build, or run a
truncation (look-ahead) test on features. Where I did not verify, the text says so. Repairs made
earlier in this engagement (Phase 7A/7B/7C and the final-hardening commits) are part of the audited
code; the audit itself changed no production code. Labels: CODE-VERIFIED, DATA-VERIFIED,
RESEARCH-SUPPORTED, PRACTITIONER-OBSERVATION, INFERENCE, OPINION.

## 1. Executive summary
A carefully engineered, fail-closed research pipeline with strong leakage and holdout discipline.
The weak points are statistical (selection bias across 48 specs x 16 folds, no deflated-Sharpe or
PBO), economic (no funding, flat slippage), and untested hyperparameters. The most important
question is not whether the code leaks, but whether any signal survives 11-20 bps round-trip costs
at 15-120 minutes. Prior for a durable net edge is low (OPINION).

## 2. Final verdict
Training code: **TRAINING_CODE_CORRECT_WITH_MINOR_ISSUES**. Architecture:
**GOOD_BUT_NEEDS_HARDENING**. Status: **GO_AFTER_FIXING_SPECIFIC_BLOCKERS** (one-model smoke only;
the full grid is NOT authorised).

## 3. Architecture diagram
```
Binance archive -> Bronze (raw files, hashes)
  -> Silver (gap-aware 5m/12h/1d klines, versioned, manifests)
  -> Gold  (109 features + multiasset_targets_v2, 4 horizons, 138 parquet partitions, manifest)
  -> prepared cache (identity = config + ~50 source hashes + environment + Gold id)
  -> fold plans (16 rolling: Train | purge | Validation | Cal-A | Cal-B | Test, 120-min embargo)
  -> fold context (cross-section keyed by (symbol, feature_time), label-independent)
  -> LightGBM fit on Train, early stopping on Validation
  -> calibrator on Cal-A -> thresholds on Cal-B -> frozen identity -> release TEST once
  -> trades (non-overlap per symbol, tier costs) -> report.json + results CSV
  -> aggregation / ranking (validation only) -> [LOCKED] August holdout
```
Stage details: input/output/owner/leak vectors/failure conditions are summarised in the training
audit; every stage fails closed (typed exceptions, hash checks, lease/lock).

## 4. Training-code verdict
See `crypto2_training_code_audit_20261106.md`. Timing CODE-VERIFIED: feature at bar close, entry
one bar later, label_end `open[i+2+steps]`, no labels across gaps, cutoff enforced.

## 5. Data pipeline
DATA-VERIFIED: Gold 138/138 partitions match their SHA-256, 109 features, 50,352,548 rows, holdout
LOCKED_UNUSED. Silver exists locally (592 manifests, 577 version folders) but was not verified and
the download was still running. Gold was built from an inner join of features and labels (hence M-01).

## 6. Features
109 = 54 native + 22 (12h) + 33 (1d). HTF features use completed bars (CODE-VERIFIED in
`phase6/features._higher_timeframe_values` and its coverage-contract tests). NOT done: per-feature
formula audit and a truncation test. Redundancy is probably high (HTF duplicates); LightGBM tolerates
correlated predictors but importance is unstable (INFERENCE).

## 7. Target
Raw future return is a plain, defensible baseline. Volatility-normalised target divides by a causal
daily-volatility feature at `feature_time` (CODE-VERIFIED). Alternatives (cross-sectional rank,
market-residual, triple-barrier) are assessed in the literature file; not recommended as changes now.

## 8. Splits / folds
16 rolling folds, 24-month train, 3-month blocks; purge on actual `label_end_time`; embargo 120 min
(CODE-VERIFIED in `folds.py`). The earlier engagement also verified no overlap with tests. A
per-fold table of dates and row counts needs the fold-plan output from the Mac venv (not produced
here). Walk-forward is simpler than CPCV and gives one path; adequate for a smoke test.

## 9. Leakage review
| Vector | Result |
| --- | --- |
| Target timing | CODE-VERIFIED clean |
| Label-dependent fold context (M-01) | Fixed in code (union of feature rows, preview coverage check). **Residual from Gold's label inner join not measured: ACCEPTABLE_BOUNDED (provisional)** |
| Membership by future gaps | Fixed (TRAIN_HISTORY_ONLY_V2) with tests |
| Validation -> training | none (early stopping only) |
| Cal-A/Cal-B -> model | none; Cal-B only chooses thresholds |
| Test | one frozen release, access ledger, measured flag |
| July/August | flags constant; no read path found |
| Scaling/normalisation | trees need none; target scale is a causal feature |
| Missing data | non-finite rows dropped per segment with counts (`finite_row_accounting`) |

## 10-11. Model and hyperparameters
LightGBM remains the right primary family (Grinsztajn et al. 2022 for tabular data; see literature
file). `min_child_samples=100` and weak regularisation are the least justified settings; run a
small validation-only sensitivity grid and 3 seeds before a grid. See training audit table.

## 12. Calibration
Identity vs linear, now chosen on the last 25% of Cal-A and refit on all of Cal-A. Isotonic would
risk overfitting small Cal-A; keep linear. A calibration that only shrinks predictions cannot create
skill (INFERENCE).

## 13. Thresholding
Cal-B only, non-overlapping per-symbol policy, trade threshold = cost + {2,4,6,8,10} bps, minimum 30
trades, winner = best mean net expectancy. Mild selection effect from a 5-point grid and 30-trade
floor (30 trades gives a very wide confidence interval). Do not evaluate precision/recall before the
thresholds exist; the code reports action metrics only after Cal-B.

## 14. Metrics
Edge cases handled: zero actuals (explicit), NaN/constant predictions (None), empty folds (explicit
status). Cross-sectional IC exists in test metrics but not in the validation baselines. A model is
not successful because R2>0, accuracy>50% or Spearman>0; require consistency across folds and
positive cost-adjusted expectancy.

## 15. Costs and execution
CODE-VERIFIED: round trip = 2x taker (4 bps) + spread + 2x slippage = 11 / 14 / 20 bps by liquidity
tier. Funding is NOT modelled. Entry one bar after the decision at the open price. This is an
intraday, medium-frequency OHLCV strategy (not HFT). Slippage is flat and probably optimistic in
volatile bars or for the lower-liquidity tier (INFERENCE). Official funding and fee pages are linked
in the literature file; CoinSwitch's own fees were not verified.

## 16. Multiple testing
At least 48 x 16 = 768 outcomes plus any tuning. Only a Bonferroni-corrected validation ranking
exists. Applicable and worthwhile: a single precommitted primary spec, the Deflated Sharpe Ratio on
the finalist with the full trial count, and the PBO only if many comparable trials exist. White's
Reality Check/SPA only if implemented correctly. Winner's curse is the main statistical danger.

## 17-18. Reproducibility and RunPod
Deterministic CPU, one seed, recorded environment identity; a changed source file invalidates the
cache (good, but freeze code first). Hard-coded paths: only legacy `scripts/phase7_vm_supervisor.py`
uses `gcloud`; launchers were made portable in 7A. RunPod gates (uv sync, pytest, verify_linux) not run.
Memory (INFERENCE from the estimator): one horizon table is ~12.6M rows x 109 float64 = ~10 GiB;
upper-bound RAM ~37 GiB with copies. Run the estimator before preparing the cache. GPU LightGBM is not
needed and not shown equivalent: use CPU for the smoke run.

## 19-23. Literature, practitioners, X, Reddit, GitHub
See the literature file. Summary: the validation design follows López de Prado's purging and
embargo; the multiple-testing literature (Harvey-Liu-Zhu; White; Hansen; Bailey-LdP) says current
reporting is insufficient; crypto evidence is mostly daily-weekly; X not accessible; Reddit
unusable as evidence; only Freqtrade's look-ahead docs were verified among open-source projects.

## 24. Loophole register / 25. Ratings
See the register (18 items) and scorecard (overall scientific 6.5, engineering 8, statistical rigor 5,
trading realism 5, reproducibility 7.5, RunPod readiness 6).

## 26-27. Strengths and weaknesses
Strengths: label-end purging, measured test gate, locked holdout, immutable Gold with verified
hashes, cache/environment identity, lease and recovery, fail-closed validators, large test suite.
Weaknesses: selection bias control, funding and slippage realism, hyperparameter evidence, single seed,
unmeasured M-01 edge, universe survivorship, no truncation look-ahead test.

## 28. Critical blockers (before the smoke run)
1. Green pytest + ruff on the tip and Linux `verify_linux`. 2. Owner-signed success criteria.
3. Measure the M-01 edge (row counts) or accept it in writing. 4. Verify Silver completeness only if
Gold is rebuilt; not needed for training from verified Gold.

## 29-33. Improvements, experiments, what not to change
Do not change: targets, horizons, folds, Core20, the locked holdout, LightGBM as primary.
Cheapest progression: Stage 0 gates (above) -> Stage 1 one smoke model, Fold 1 -> Stage 2 same spec
across 16 folds with baselines and costs -> Stage 3 small architecture comparison (G0 vs P0) on
validation -> Stage 4 ablations: native only, +12h, +1d, no market context, no symbol id, raw vs
normalised target, Ridge -> Stage 5 selection with DSR on the finalist -> Stage 6 holdout, once.
Sensitivity (validation only): 3 seeds, min_child_samples {100, 1000, 5000}, cost x1/1.5/2,
threshold grid shift. Options: **A** minimal (current + the fixes above); **B** stronger (A + funding
and volatility-scaled slippage, DSR, truncation look-ahead test, rank/market baselines); **C** ideal
(B + CPCV paths, tick/order-book cost model, ensemble of tree and linear models). Recommend B; C is
costly and unjustified before a baseline signal exists.

## 34. Overall score
Scientific 6.5, engineering 8, statistical rigor 5, trading realism 5, reproducibility 7.5, RunPod 6.

## Can the results be faked, and how likely?
Probability that an apparent edge is a false discovery: I will not give a precise number (no honest
basis). OPINION: for 5-minute-bar crypto strategies net of 11-20 bps costs, the prior for a real,
durable edge is low (on the order of 10-20%), and best-of-48 selection raises the chance that a
"winner" is noise well above the nominal level. Evidence that would change my mind: positive
cost-adjusted expectancy and positive validation IC in most folds, for one precommitted spec,
beating Ridge and zero, stable across seeds and +50% costs, with a deflated-Sharpe p-value below the
precommitted bar, and then a single clean holdout.

## TOP 20 RISKS (impact / probability / difficulty to fix)
1 Winner's curse across 48 specs (H/H/M). 2 Costs and funding too optimistic (H/H/M). 3 Gates unproven on tip (H/M/L). 4 Survivorship in Core20 (M/H/M). 5 Single-seed noise (M/H/L). 6 Weak regularisation (M/M/L). 7 L2 on heavy tails (M/M/L). 8 M-01 edge (M/L/M). 9 Placeholder success criteria edited post hoc (H/M/L). 10 L-04 H0 contamination (L/H/M). 11 Regime concentration (M/M/L). 12 Thin Cal-B (30 trades) thresholds (M/M/L). 13 Feature redundancy / unstable importance (L/H/L). 14 Silver completeness (M/M/L). 15 Cache invalid after any code edit (L/H/L). 16 CPU/GPU mix (L/L/L). 17 Legacy order code in repo (H/L/L). 18 Stale docs (L/M/L). 19 No truncation look-ahead test (M/L/L). 20 Results table missing seed (L/H/L).

## TOP 20 IMPROVEMENTS (scientific value / benefit / effort)
1 Precommit one primary spec + sign criteria (H/H/L). 2 Funding cost (H/H/M). 3 Volatility-scaled slippage sensitivity (H/M/M). 4 DSR on finalist (H/H/M). 5 3 seeds (M/H/L). 6 min_child_samples/regularisation grid (M/M/L). 7 Truncation look-ahead test (H/M/L). 8 Measure M-01 edge (M/M/L). 9 Rank/market baselines (M/M/L). 10 Per-timestamp IC in baselines (M/M/L). 11 Per-fold regime report (M/M/M). 12 Huber/robust loss ablation (M/M/L). 13 Robust threshold selection (larger Cal-B floor) (M/M/L). 14 Survivorship quantification (M/M/M). 15 Seed/fit-time columns (L/M/L). 16 Context-change cache test (L/M/L). 17 CPU/GPU equivalence test (L/L/M). 18 Move legacy trading code (L/M/L). 19 Docs refresh (L/M/L). 20 CPCV for finalist (M/L/H).

## Final question
"If we train the current architecture exactly as it exists today, what is the biggest reason the
results could fool us?" **Primary: selection bias**: picking the best spec/fold pattern from 768
noisy outcomes with only a Bonferroni-on-validation guard, so a lucky configuration looks like an
edge. Next four: (2) costs without funding and with flat slippage, (3) single-seed variance,
(4) universe survivorship in Core20, (5) the unmeasured M-01 edge and H0/early-stopping overlap.

## Final status
**GO_AFTER_FIXING_SPECIFIC_BLOCKERS** (gates 28.1-28.3). Not a go for the full grid.
