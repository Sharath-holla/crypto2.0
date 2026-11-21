# Crypto 2.0 independent research audit — 6 November 2026

**Verdict: GOOD_BUT_NEEDS_HARDENING. Training/evaluation: TRAINING_CODE_HAS_MATERIAL_RISKS.
Decision: GO_AFTER_FIXING_SPECIFIC_BLOCKERS for one registered smoke model only.**

This independent audit supersedes the concurrent draft preserved below. It executed **689 targeted
and 1,162 full-suite tests**, reproduced material reporting/context mechanisms, and checked primary
research and official documentation. **Ruff lint and format fail. Linux and actual-Gold verification
remain outstanding.** No production code, real training, cloud resource or locked holdout was changed.

Read the [independent assessment](#independent-assessment) and its four companions:
[loophole register](crypto2_loophole_register_20261106.md),
[training trace and all 109 features](crypto2_training_code_audit_20261106.md),
[literature comparison](crypto2_literature_comparison_20261106.md),
[scorecard](crypto2_architecture_scorecard_20261106.md).

The preserved draft's fresh Gold-hash claim is **not independently verified here**; its today-survivor
Core20 assertion is contradicted by source; its M-01 “acceptable bounded” disposition is withdrawn;
its 10–20% edge prior is unsupported; and its proposed August release is **void**. August remains
permanently LOCKED_UNUSED, used=false, evaluation_authorized=false; July remains unused. Later
sections provide the corrected conclusions and exact evidence limits.

<details>
<summary>Preserved concurrent draft from c249e28 — historical text, not the independent conclusions</summary>

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


</details>

# Independent assessment

## 1. Executive summary

**INFERENCE:** The architecture is capable of conducting a useful signal-discovery experiment. It
has not established that any tradable signal exists. The primary CPU G0 pipeline is causally
structured and its target formula is correct in the tested synthetic examples. The project is
neither scientifically unsound by design nor ready to justify a paid 48×16 search.

The largest danger is mistaking development-selected performance for independent evidence. Added
ranking/success helpers accept duplicate folds, infer significance from the same Validation used
for early stopping, and can choose a winner using later-fold Validation that overlaps earlier
TEST. Fees, flat slippage, absent funding and non-portfolio trade statistics create a separate risk
of mistaking predictability for tradability. These are material risks even when feature timing is
correct. Findings are detailed as IA-01 through IA-24 in the register.

**CODE-VERIFIED:** Important strengths include explicit delayed entry, actual-endpoint purge,
chronological Cal-A/Cal-B, fold-local context, PIT historical membership, immutable source/Gold
contracts, atomic prepared-cache publication, model receipts, strict source identities for much of
the pipeline, measured TEST-release logging, explicit NO_TRADE and no live-order imports in the
maintained research path.

**DATA-VERIFIED (local software/synthetic only):** 689 targeted tests and 1,162 full tests passed.
Tiny computations matched all four label horizons and all 109 feature prefixes, and reproduced M-01 loss/witness behavior,
normalization inversion edge cases and duplicate-result false qualification. Lint/format failed;
no repair was made. Real Gold, real fold row counts and cache equivalence could not be certified.

## 2. Final verdict and scope

| Required question | Independent answer |
| --- | --- |
| Scientifically correct architecture? | Coherent causal design, with material selection/inference and context-completeness qualifications. |
| Training implementation correct? | Default CPU G0 timing and split ownership are supported by source/tests; whole training/evaluation receives TRAINING_CODE_HAS_MATERIAL_RISKS. |
| Hidden leakage? | No demonstrated future-price value entering the inspected native/HTF inputs; unresolved future-availability conditioning through Gold, plus future-fold selection hazards. Absolute absence cannot be certified. |
| Statistically valid evaluation? | Fold-local fixed-policy TEST is meaningful; selected all-fold “winner” significance is not established by current helpers. |
| Likely to overfit? | Material search/threshold/early-stopping risk; no measured project overfit probability. |
| Features/targets sensible? | Yes as baselines; duplicates, naming/scale and chunk-state issues should be documented, not reflexively replaced. |
| Costs/execution realistic? | Suitable labeled scenarios; insufficient to establish executable profitability. |
| Model choice appropriate? | Retain CPU LightGBM with linear/naive controls. No evidence requires deep learning. |
| Missing components? | Trial ledger, valid selector chronology, independent baseline evaluation, uncertainty, feature-only completeness evidence, funding/capacity accounting and qualified Linux/runtime contracts. |
| Unnecessary complexity? | Broad source invalidation, 48-spec search before profiling one model, fragile CSV inference, large orchestration module and duplicate features. |
| Strong/weak parts? | Strong causal ownership and durable artifacts; weak inference and market implementation evidence. |
| What can invalidate results silently? | Mixed control identity on resume, duplicate/missing CSV rows, retrospective selection using later folds, unchecked future-availability attrition. |
| Highest-value improvements? | Freeze one primary procedure; enforce complete identities/unique canonical results; validate real context/cache population before fitting. |
| Paid RunPod justified today? | No immediate launch. Conditional support for one CPU smoke after named gates and separate cost/deadline authority. |
| Probability of false discovery? | Cannot estimate posterior/PBO from architecture and zero completed reports; illustrative null calculations below are not that probability. |
| Fix before training? | Listed in section 32; no architecture rewrite or full-grid approval. |
| Research later? | Small sensitivity/ablation suite, economic realism and alternatives after basic viability. |
| Ratings? | Scientific 6.5; engineering 7.5; rigor 4; trading realism 3.5; reproducibility 6.5; RunPod readiness 4.5 out of 10 (judgments). |
| Overall verdict? | GOOD_BUT_NEEDS_HARDENING; GO_AFTER_FIXING_SPECIFIC_BLOCKERS. |

### Audited state and limits

**CODE-VERIFIED:** Repository `/Users/cortex/Projects/crypto2.0`; starting branch
`fix/phase7a-final-scientific-hardening-20261106`; starting HEAD
`0eb929676fef183a33afff2f58f15ceb2f21adc7`. Initially modified hardening.py and research/metrics.py,
untracked final-metrics test and `Claude outputs/`; training_metrics.py changed during inspection.
No staged diff was present. Another process committed `d3c8da7`, `687e697`, then documentation-only
`c249e28` during the audit. The inspected code snapshot is
`687e697530bdaecd9d981b3541a7bb60182925ff`; the later documentation base is
`c249e285248c12d6d97e1a9be3d4c4625b37f258`. A content-hash comparison verified no recorded
source/config/test/script bytes changed between that snapshot and the documentation tip. This
agent did not create those commits, alter their code, stage files or overwrite untracked owner work.
Remote origin is [Sharath-holla/crypto2.0](https://github.com/Sharath-holla/crypto2.0); no fetch,
push or cloud mutation was performed. Git status, last 30 commits, remotes, unstaged and staged
diffs were inspected. The source hash snapshot and test outputs are preserved in
[evidence_crypto2_20261106](evidence_crypto2_20261106/source_snapshot.json).

The complete root context and handoff package were read. The handoff describes historical discovery
507/507, acquisition complete, 60 candle checkpoints, Gold 7/7 with 138 partitions and 50,352,548
rows, and incomplete 0/48 Fold 1. These are **historical handoff assertions**, not fresh market-data
verification. Configured local Gold, prepared cache, checkpoint and artifact roots are absent in
this environment. `/Volumes` showed no separate market-data volume. No VM was booted, cloud
account accessed, archive acquired, full cache built or forbidden period inspected to fill this gap.
There is no independently verified current result with which to judge model performance.

This is a substantial independent source/literature/synthetic audit, **not an unconditional
production-data certification or proof that every loophole in the repository was found**. Actual
row attrition, M-01 fold incidence, regime outcomes, compute timing, provider locks and economic
results remain UNKNOWN / NOT VERIFIED. The register separates reproducible defects from these
unverified gates.

Evidence labels throughout: CODE-VERIFIED; DATA-VERIFIED (explicitly local/synthetic where relevant);
RESEARCH-SUPPORTED; PRACTITIONER-OBSERVATION; INFERENCE; OPINION/RECOMMENDATION. External factual
claims cite direct primary sources. Ratings and priorities are judgments, not measured probabilities.

## 3. Architecture diagram and stage map

```text
Public Binance USD-M archives + REST              Current + historical listing evidence
   | exact decimal/source records + checksums        | registry / cutoff-known descriptors
   v                                                  v
Immutable Bronze -> quality/lifecycle Silver -> frozen Core20 / per-fold PIT membership
                         | direct 5m,12h,1d + funding/mark/index
                         v
             causal features --------> feature-membership preview witness
                         |                       |
             future labels v2                  |
                         v                       |
         immutable Gold INNER JOIN (long format: up to four horizons per feature row)
                         |                       |
         verify hashes -> fold scan -> all-horizon feature-key union + witness check
                         |                       |
              bind frozen fold context <---------+
                         v
         TRAIN | Validation | Cal-A | Cal-B | TEST     [actual label purge + 120m gaps]
                         |
            finite ordered matrices -> atomic prepared cache / read-only mmap reload
                         |
             CPU LightGBM: TRAIN fit + Validation stop
                         v
         Cal-A affine/identity calibration -> Cal-B non-overlap cost threshold
                         v
          frozen identity -> TEST release ledger -> raw predictions / trades
                         v
         immutable model + receipt + JSON report -> checkpoint -> CSV view / summaries
                         v
             retrospective evidence and separately designed selection review
                         X
         July unused; August permanently LOCKED_UNUSED; no evaluation/live path authorized
```

**CODE-VERIFIED stage contracts:** The training companion gives the exact call chain and block
lines. The following map includes upstream and operational stages, with failure boundaries.

| Stage / owner and important entrypoint | Input -> output | Data/time assumption | Potential leak / failure |
| --- | --- | --- | --- |
| Public acquisition: `data/ingestion`, `phase7/acquisition.acquire_candle_family` | Official archives/REST -> raw partitions, manifests | UTC half-open requests, archive checksums, exact decimals | Wrong source domain or coverage claim; unavailable archive is recorded, never invented. |
| Bronze: `data/storage/parquet.write_immutable` | Decimal candle table -> immutable Parquet/hash | Preserves source/ingested time; refuses existing partition | Hash is integrity, not truth; concurrent check-then-replace requires qualified ownership. |
| Silver: `quality`, `acquisition._promote_causal_segments` | Bronze + lifecycle/gap evidence -> validated usable segments | Distinguish active gaps from pre/post lifecycle absence | Repair by synthesis prohibited; official reconciliation must retain evidence. |
| Registry: `registry.build_symbol_registry` | ExchangeInfo + historical archives -> registry/hash | Archive/current union; canonical venue USD-M | Incomplete archive census may omit failed instruments; current listing alone is insufficient. |
| Universe: `universe.select_core_universe / select_fold_active_universe` | Cutoff-known descriptors -> frozen Core20/fold membership | Core frozen at 2022-01-01; later membership TRAIN end | Future delist/gap/coverage cannot retroactively cull hard assets. |
| Feature build: `features.generate_multiasset_features / build_higher_timeframe_context` | Validated candles/derivatives -> 109 columns + helpers | Source completed by feature time; no unfinished HTF bar | Gaps reset most transforms; label-independent source availability must survive Gold. |
| Labels: `targets.generate_multiasset_targets` | Opens/path + causal scale -> four horizon targets | Entry i+2; endpoint i+2+steps; contiguous path; endpoint<cutoff | Wrong shift/off-by-one; normalized inverse edge documented. |
| Gold: `gold._joined_gold_table / build_multiasset_gold_chunks` | Features INNER JOIN targets -> partitions/manifest | Per-key/horizon uniqueness; annual chunks with halos | Future-availability conditioning and recursive feature seed/chunk effects. |
| Fold/preparation: `training._load_fold_rows`, `folds.slice_multiasset_fold` | Gold + frozen membership -> five segments | TRAIN-only tiers/clusters; actual-end purge, later 120m gap | Global/label-conditioned context or wrong membership; post-TRAIN gap stops fold. |
| Matrix/cache: `models.prepare_architecture_inputs`, `PreparedDataCache` | Finite Arrow tables -> float64 arrays/IPC/mmap | Exact feature order, target, symbol/time alignment | Stale semantics/corrupt/partial files reject; actual-scale equivalence unproved. |
| Estimator: `models.fit_architecture / _fit` | Train/Val X/y + weights -> model bundle | Val selects iteration; no Cal-B/Test fit | Reused Validation not untouched evidence; GPU admission separate. |
| Calibration: `phase5.calibration.fit_calibrator` | Covered Cal-A -> identity/affine map | Internal heldout row tail; all-Cal-A refit | Internal adjacent labels/timestamps overlap; no classification probabilities. |
| Threshold/action: `economics.select_cal_b_thresholds / _policy_indices` | Cal-B predictions + tiers -> frozen global/cluster/coin thresholds | Chronological non-overlap per symbol | Five-way selection uncertainty; no negative-expectancy/no-trade comparator. |
| TEST: `MultiAssetFoldData.release_test`, `metrics.evaluate_predictions` | Frozen objects -> predictions/IC/errors/trades | API logs consumer/hash/time/row count | Not a secure physical data boundary; later human/model selection can reuse outcomes. |
| Economics: `economics.build_oos_trades / fixed_policy_cost_stress` | Raw predictions/returns -> fixed-size trade diagnostics | Delay+fixed horizon+cost scenarios | No funding/capacity/capital path; summed return is not a funded portfolio return. |
| Artifacts: `models.save_model`, `recovery.publish_model_receipt`, `CheckpointStore.complete` | Model/report bytes -> receipts/checkpoints | Atomic core publish, hashes and identity checks | CSV not atomic with checkpoint; unregistered joblib default permissive. |
| Aggregation: `pipeline._report_stage`, `hardening.rank_specs_with_correction` | Reports/CSV -> descriptive scorecard/ranking | Mean TEST IC in report; Val skill ranking in separate helper | Different stages must not be conflated; no complete final champion gate implemented. |
| Runtime: `runtime`, `run_lease`, supervisors/preflight | Budget/paths/source environment -> admitted owned run | One logical worker, durable cache; Linux qualification | Provider/mount/deadline assumptions not proven on RunPod; generic CLI weaker gate. |

### Identity chain

Source URLs/checksums -> Bronze manifest -> Silver quality/coverage/lifecycle manifest -> registry
hash + Core/fold universe hashes -> Gold dataset ID and partition/manifest hashes -> config hash
`93f987736b1a79d26b773957` + source-content manifest + environment identity + fold/horizon/target/
ordered columns -> prepared-cache ID -> model scientific-input identity + backend semantics ->
calibrator/threshold hashes -> frozen pre-TEST identity -> serialized model/receipt hashes ->
report identity -> stage completion.

**CODE-VERIFIED:** `git_commit` alone is insufficient for dirty worktrees; content manifests cover
most critical source. **Exception:** hardening.py and active hardening config are omitted from
model/run compatibility (IA-04). Hashes do not prove causality, authenticity against an adversary,
or correct dataset construction. Resolved absolute model-registry paths complicate relocation.

## 4. Training-code verdict

TRAINING_CODE_HAS_MATERIAL_RISKS. The [training companion](crypto2_training_code_audit_20261106.md)
traces every critical G0 function from CLI through serialization, inventories all 109 inputs,
classifies parameters and defines metric edge behavior. No Cal-B label or TEST value was found
flowing into the isolated G0 fit. P0 uses Cal-A **row counts** for estimator eligibility; H0 fits
residual corrections on Validation. Thus the blanket statement “only TRAIN ever fits anything”
is false for the full architecture; the actual ownership is intentionally more nuanced.

## 5. Data pipeline review

**CODE-VERIFIED:** Binance is the sole canonical data/eventual execution venue. Spot and USD-M
retain separate raw identities. Candle schema uses decimal128(38,18) and aware UTC microseconds.
Research converts explicitly to float64; this does not silently rewrite original decimals. Source
manifests and quality/lifecycle checks are more rigorous than a simple downloaded CSV workflow.

Public funding pagination uses inclusive API endpoints converted with `end_ms-1`, then local
`[start,end)` filtering and increasing cursor. Funding event availability is its event timestamp;
mark/index close availability is source open+interval. This models event-time observability,
not proof of zero historical publication delay. The additional 5m entry latency helps timing but
does not prove exchange fills. Official API semantics were checked at
[Binance market-data docs](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data);
archive checksum conventions at [Binance's public-data repository](https://github.com/binance/binance-public-data).

Missing market history is not filled. Explicit as-of use of an already observed funding or completed
HTF value is different from inventing a missing candle. Long funding staleness (up to 24h) should be
documented as a context assumption, particularly around changed settlement intervals. Gaps can
represent quality failure, official inactivity, lifecycle boundary or corruption; source evidence,
not hindsight PnL, must determine their treatment.

**UNKNOWN:** Actual Silver completeness, 138 partition hashes, row-level quality and freeze evidence
were not independently validated. The earlier concurrent draft's local mirror counts must not be
used as this audit's fresh evidence. Valid historical checkpoints must be verified and reused before
recomputing anything; a rebuild is not an audit shortcut.

## 6. Feature review

**CODE-VERIFIED:** 54 native +22 direct completed 12h +33 direct completed 1d =109 inputs; current
physical Gold schema has 130 fields. Exact formula/lookback/source/time/NaN conventions are in the
training companion's complete table. No OI/Fear & Greed/sentiment is enabled. “Liquidity” is primarily
trailing traded quote-volume/activity, not an executable order-book estimate. Funding, mark/index
and contract/mark bases are available context; no actual perpetual cash-flow payment is implied.

Native price/flow/volatility transforms are trailing and source-completed. Anchor values join by
exact feature timestamp; HTF by completed availability with expiry, per symbol/per family. At
2021-01-02 10:05, for example, a daily candle opened Jan 2 is unavailable; Jan 1's completed bar may
be used until its expiry. Noon 12h data becomes available only when that 12h bar has completed, not
at its opening. Synthetic HTF/future perturbation/gap tests passed in the targeted suite.

No centered rolling/backfill/interpolation was found in the active Phase7 feature path. Broader
Python searches found nan_to_num in earlier Phase4/4.1 features and shifts in legacy phaseA labels;
those are not automatically leakage, and are not the Phase7 A6 inputs. The code uses NumPy
slices/windows, so searching pandas methods alone would have missed the actual implementation.
Aiventra's separate product code and every legacy line were not given a full independent scientific
proof.

**INFERENCE / recommendations:** 109 features is not inherently excessive for a regularized tree
baseline, but row count overstates independent information. Several exact duplicates and related
HTF transforms reduce interpretability. Recursive EMA chunk reseeding and pair-window gap semantics
need later equivalence study. Feature importance is descriptive, not causal; use TRAIN/development
blocked permutation or grouped ablation and assess stability, never select features on TEST SHAP.
Do not drop features or rewrite immutable Gold during this audit.

## 7. Target review

**DATA-VERIFIED (synthetic):** source `i` completes at open[i+1], entry=open[i+2], endpoint=
open[i+2+h/5]; raw return=endpoint_open/entry_open-1. The script reconstructed 15/30/60/120m exactly.
Labels require unbroken future path and endpoint<2026-07-01. Actual endpoint metadata, not a nominal
horizon alone, drives purging. MFE/MAE use future path only as diagnostics/targets, never model inputs.

Raw simple return is an interpretable primary target and signed short payoff at fixed initial
notional is its negative in this simplified linear-futures model. Log returns would change the
prediction objective and reconversion; not automatically improve edge. Normalized returns use
historical 5m-return std over 288 rows; not future volatility. The denominator floor is not used
symmetrically on inverse conversion (IA-17); raw smoke is unaffected.

**OPINION/RECOMMENDATION:** Ranking targets address relative ordering but sacrifice return units
needed for cost hurdles. Market-residual/neutral targets separate beta from relative alpha but
require TRAIN-only factor estimation and a distinct economic strategy. Quantiles address uncertainty
but introduce interval validation. Triple-barrier/meta-labeling only make sense after specifying a
causal base policy and executable barriers, with actual-end purging. Do not add barriers, final
TP/SL or target engineering because another paper uses them. Preserve current v2 as reference.

## 8. Split/fold review

**CODE-VERIFIED:** 16 rolling folds from configured calendar bounds, zero-based IDs; the operational
“Fold 1” is index 0. Train=24 calendar months, Validation=3, Calibration=3, TEST=3, step=3. Cal-A/B
split at exact elapsed midpoint, sometimes noon. All ranges half-open UTC. Within each fold,
prior-segment rows require label_end<next raw boundary; later segment's first 120m is excluded.
There is no overlap between TEST windows. There is legitimate data reuse across rolling TRAIN and
later development blocks; treating them as independent experiments is a different claim.

| Operational fold / index | TRAIN | Validation | Cal-A | Cal-B | TEST | Purge / embargo | Actual segment counts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 / 0 | 2020-01-01 → 2022-01-01 | 2022-01-01 → 2022-04-01 | 2022-04-01 → 2022-05-16T12:00 | 2022-05-16T12:00 → 2022-07-01 | 2022-07-01 → 2022-10-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 2 / 1 | 2020-04-01 → 2022-04-01 | 2022-04-01 → 2022-07-01 | 2022-07-01 → 2022-08-16 | 2022-08-16 → 2022-10-01 | 2022-10-01 → 2023-01-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 3 / 2 | 2020-07-01 → 2022-07-01 | 2022-07-01 → 2022-10-01 | 2022-10-01 → 2022-11-16 | 2022-11-16 → 2023-01-01 | 2023-01-01 → 2023-04-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 4 / 3 | 2020-10-01 → 2022-10-01 | 2022-10-01 → 2023-01-01 | 2023-01-01 → 2023-02-15 | 2023-02-15 → 2023-04-01 | 2023-04-01 → 2023-07-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 5 / 4 | 2021-01-01 → 2023-01-01 | 2023-01-01 → 2023-04-01 | 2023-04-01 → 2023-05-16T12:00 | 2023-05-16T12:00 → 2023-07-01 | 2023-07-01 → 2023-10-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 6 / 5 | 2021-04-01 → 2023-04-01 | 2023-04-01 → 2023-07-01 | 2023-07-01 → 2023-08-16 | 2023-08-16 → 2023-10-01 | 2023-10-01 → 2024-01-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 7 / 6 | 2021-07-01 → 2023-07-01 | 2023-07-01 → 2023-10-01 | 2023-10-01 → 2023-11-16 | 2023-11-16 → 2024-01-01 | 2024-01-01 → 2024-04-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 8 / 7 | 2021-10-01 → 2023-10-01 | 2023-10-01 → 2024-01-01 | 2024-01-01 → 2024-02-15T12:00 | 2024-02-15T12:00 → 2024-04-01 | 2024-04-01 → 2024-07-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 9 / 8 | 2022-01-01 → 2024-01-01 | 2024-01-01 → 2024-04-01 | 2024-04-01 → 2024-05-16T12:00 | 2024-05-16T12:00 → 2024-07-01 | 2024-07-01 → 2024-10-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 10 / 9 | 2022-04-01 → 2024-04-01 | 2024-04-01 → 2024-07-01 | 2024-07-01 → 2024-08-16 | 2024-08-16 → 2024-10-01 | 2024-10-01 → 2025-01-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 11 / 10 | 2022-07-01 → 2024-07-01 | 2024-07-01 → 2024-10-01 | 2024-10-01 → 2024-11-16 | 2024-11-16 → 2025-01-01 | 2025-01-01 → 2025-04-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 12 / 11 | 2022-10-01 → 2024-10-01 | 2024-10-01 → 2025-01-01 | 2025-01-01 → 2025-02-15 | 2025-02-15 → 2025-04-01 | 2025-04-01 → 2025-07-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 13 / 12 | 2023-01-01 → 2025-01-01 | 2025-01-01 → 2025-04-01 | 2025-04-01 → 2025-05-16T12:00 | 2025-05-16T12:00 → 2025-07-01 | 2025-07-01 → 2025-10-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 14 / 13 | 2023-04-01 → 2025-04-01 | 2025-04-01 → 2025-07-01 | 2025-07-01 → 2025-08-16 | 2025-08-16 → 2025-10-01 | 2025-10-01 → 2026-01-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 15 / 14 | 2023-07-01 → 2025-07-01 | 2025-07-01 → 2025-10-01 | 2025-10-01 → 2025-11-16 | 2025-11-16 → 2026-01-01 | 2026-01-01 → 2026-04-01 | actual endpoint / 120m | UNKNOWN for all horizons |
| 16 / 15 | 2023-10-01 → 2025-10-01 | 2025-10-01 → 2026-01-01 | 2026-01-01 → 2026-02-15 | 2026-02-15 → 2026-04-01 | 2026-04-01 → 2026-07-01 | actual endpoint / 120m | UNKNOWN for all horizons |

Exact IDs and ISO boundaries are preserved in [probe JSON](evidence_crypto2_20261106/probes.json).
No row counts have been invented. On an ideal complete grid a segment of N timestamps loses
`h/5+1` rows to strict endpoint purging and, for a later segment, up to 24 more to the 120m gap;
actual membership, lifecycle, gaps, warm-up and finite-feature requirements change this. Last
TEST's labels also obey global cutoff. Actual counts require validated existing data, not a new
acquisition/cache build in this audit.

**RESEARCH-SUPPORTED:** Purging overlapping labels is appropriate; the current leading boundary gap
is a chronological separation, not precisely the post-TEST embargo used for training on both sides
of a K-fold TEST block. CPCV creates alternative resampling paths with different assumptions and
compute cost. A causal walk-forward baseline is defensible without importing CPCV wholesale.
See [López de Prado](https://www.wiley.com/en-gb/advances-in-financial-machine-learning-p-9781119482109)
and [Bergmeir/Hyndman/Koo](https://southwest.robjhyndman.com/publications/cv-time-series/).

## 9. Leakage review, including M-01

| Channel | What was established | Remaining risk |
| --- | --- | --- |
| Future price -> native features | Trailing formulas and future-perturbation tests | Does not certify every byte of inaccessible Gold. |
| Unfinished 12h/1d -> 5m | Completion-based availability/expiry and tests | Recursive chunk seeding changes values without future leakage. |
| Future label value -> context | Context projection excludes labels; perturbation tests passed | Future label **availability** can remove upstream Gold feature keys. |
| Future universe -> fold membership | TRAIN-only descriptor/gap gate, historical registry | Actual historical candidate completeness unverified. |
| Cal-A/B -> G0 fit | No fit data path found | P0 Cal-A count eligibility; H0 Validation correction are explicit. |
| TEST -> local fit/threshold | Freeze-before-release path and logged consumer | API can be bypassed by private attribute access; no adversarial security guarantee. |
| Later folds -> retrospective winner | Exposed by calendar/helper trace | A Validation-only name does not make future outcomes safe for earlier selection. |
| July/August | Locked config/cutoff/range guards; no market access by audit | Flags alone cannot retrospectively prove external users never accessed data. |

### M-01 quantified mechanism and honest production classification

**DATA-VERIFIED (synthetic, not historical market rows):** Four symbols ×260 source bars, one SOL
candle removed at 2021-01-01 15:00. 1,039 observed feature keys became 1,014 unique keys after the
all-horizon label join: **25 keys lost**. BTC/ETH/XRP each lost five tail keys; SOL lost ten (five tail,
five pre-gap/completion-edge keys). SOL's lost observed feature times near the gap were 14:40,
14:45,14:50,14:55,15:00. Current production witness check rejected the missing-member context with
`M01_CONTEXT_SOURCE_INCOMPLETE`. Removing **all symbols at one whole timestamp** from a valid
witnessed source was accepted because no row at that timestamp retained a witness.

For a gap at g, shortest horizon15m plus latency5m can erase all horizon labels for observed
feature times as early as g−20m through g; longer-horizon-specific exclusions can extend to g−125m.
Those are local time-distance bounds, **not a bound on effect on model selection or PnL**. Terminal
history and delisting edges have analogous dependence; at a global cutoff every symbol can vanish
without a surviving peer witness. Uniform terminal exclusion alone does not establish mixed-member
feature leakage, but does condition the evaluation population.

| Requested M-01 quantity | Result |
| --- | --- |
| Synthetic affected unique keys | 25 /1039; five SOL keys at/within 20m before the removed candle, plus tails. |
| Actual affected rows | UNKNOWN; 138 Gold partitions unavailable in this environment. |
| Actual affected folds/horizons/timestamps | UNKNOWN; mechanism applies to every horizon's use of a union with absent feature keys. |
| Maximum pre-edge look distance | All-horizon union loss20m plus boundary-time case; individual120m label dependence125m. |
| Can results materially change? | Not measured. A missing peer can change multiple ranks/context values; current guard normally fails closed. |
| Classification | **MATERIAL_RISK (unresolved real incidence)**. Not NO_RISK or a justified negligible acceptance. If a real census detects incomplete witnesses, preparation is blocked until reviewed. |

No code finding justifies turning off the witness check or rebuilding immutable Gold. A separately
approved feature-only context sidecar/census could restore independently verified context while
retaining existing Gold. It must cover even timestamps with no target rows and bind exact source,
registry/universe and feature semantics. An additional independent prefix probe compared all **109 columns across 768 synthetic rows**,
with shortened fixture rolling windows and the full production feature inventory; it passed at
rtol=1e-12,atol=1e-15 with missing values compared explicitly. This strengthens observable-time
causality evidence but does not certify real Gold or production-length numerical equivalence.
A Cal-A or TEST future-label-value perturbation test alone
does not prove this stronger availability-independence property.

## 10. Model review and alternatives

**OPINION/RECOMMENDATION:** Keep LightGBM as the primary nonlinear baseline. The data is a finite
engineered table with 20 assets, not 50M independent events; training cost and decision stability
matter more than fashionable architecture. G0 pooled versus C0/P0/H0 already tests cross-asset
sharing and specialization. Symbol one-hot is an explicit control; age/history/tiers can still
encode asset-specific structure even without a symbol column.

The following are proposed research options, not changes or evidence that any will improve this
project. Relative compute/complexity are expected for this task, not measured benchmarks.
General model comparison evidence is [Grinsztajn et al.](https://arxiv.org/abs/2207.08815),
[Gorishniy et al.](https://arxiv.org/abs/2106.11959), and
[Gu/Kelly/Xiu](https://www.nber.org/papers/w25398.pdf); none establishes universal dominance here.

| Model / priority | Weakness it addresses | New risk / expected compute and complexity | Evidence and decision |
| --- | --- | --- | --- |
| Zero + TRAIN mean / immediate controls | Detects no-skill forecast and static drift | Tiny / low; mean must be TRAIN-only | Required null controls; zero already exists, mean absent from this path. |
| Linear/Ridge / immediate control | Tests whether nonlinear capacity adds value | Low / low; scaling and weighting must align | Ridge already present; improve independent identical-key scoring, not “add Ridge”. |
| Elastic Net / later optional | Sparse correlated linear features | Low–medium / moderate; penalty tuning adds trials | Only if Ridge diagnostic suggests useful linear structure; no direct project benefit proven. |
| Random Forest / optional | Alternative nonlinear variance control | Potentially high RAM / moderate; many trees and correlated rows | [Official ensemble docs](https://scikit-learn.org/stable/modules/ensemble.html); not necessary before G0. |
| ExtraTrees / optional | Different randomized partitioning | Potentially high RAM / moderate; random sensitivity | Same source; a challenger, not a cure for selection. |
| XGBoost / later one challenger | Implementation/objective robustness check | Medium / moderate extra dependency and tuning | [Official parameters](https://xgboost.readthedocs.io/en/stable/parameter.html); no a priori superiority. |
| CatBoost / later optional | Explicit asset categories/interactions | Medium / moderate; categorical statistics need chronological scrutiny | [Official categorical mechanics](https://catboost.ai/docs/en/concepts/algorithm-main-stages_cat-to-numberic); twenty symbols alone do not compel it. |
| LightGBM / retain | Efficient nonlinear interaction baseline | Current cost; leaf/stopping/seed selection risks | Current implementation plus linear controls is enough for first meaningful smoke. |
| MLP / later controlled | Smooth multivariate interactions | Medium–high / moderate; tuning, scaling and nonstationarity | Tabular benchmarks justify a possible challenger, not immediate replacement. |
| TCN / defer | Local sequence structure not captured by static windows | High / high; causal sequence/asset batching and trial burden | No task-matched evidence of incremental net edge retrieved. |
| LSTM / GRU / defer | Learned temporal state | High / high; sequence windows/purging/state resets | No demonstrated need beyond engineered histories. |
| Generic Transformer / defer | Learned long-range temporal interaction | High / high; context leakage, many tunable choices | No architecture-level reason it fixes inference or cost errors. |
| TFT / defer | Joint horizons/static+known future covariates | High / high; future covariates must actually be known | [TFT paper](https://doi.org/10.1016/j.ijforecast.2021.03.012); present market inputs are mostly observed, not known future paths. |
| PatchTST / defer | Patch representation of lag histories | High / high; changed data object and temporal encoding | [Primary paper](https://arxiv.org/abs/2211.14730); long-term benchmark gains do not prove intraday return edge. |
| TimesNet / defer | Periodic temporal variation | High / high; spurious periodic structure and added tuning | [Primary paper](https://arxiv.org/abs/2210.02186); no task-specific edge evidence. |
| N-BEATS / defer | Alternative forecast decomposition | High / high; level forecasting differs from return economics | [Primary paper](https://arxiv.org/abs/1905.10437); not compelled by current features. |
| N-HiTS / defer | Multiscale interpolation for forecasts | High / high; smooth forecast assumptions and task mismatch | [Primary paper](https://arxiv.org/abs/2201.12886); later only with a justified sequence task. |
| TabPFN / research only | Prior-driven nonlinear tabular challenger | Unprofiled / moderate-high; pretraining provenance and memory | [2025 Nature](https://doi.org/10.1038/s41586-024-08328-6), [2026 report](https://arxiv.org/abs/2609.17895); do not use obsolete blanket size limits or assume compatibility. |
| TabNet / defer | Learned sparse tabular attention | Medium–high / high tuning; feature masks are not causality | [Primary paper](https://arxiv.org/abs/1908.07442); no demonstrated incremental value here. |
| Cross-sectional factor model / useful control | Separates common market exposure from relative forecasts | Low–medium / moderate; factor selection itself can overfit | [Crypto factor paper](https://www.nber.org/papers/w25882.pdf); define factor beta causally. |
| Ranking model / later new experiment | Aligns relative ordering with cross-sectional IC | Medium / moderate; groups/labels/cost units change | Need an economically defined ranking policy; continuous expected-return hurdle is a different object. |
| Quantile model / later | Forecast uncertainty/asymmetry | Multiple fits / moderate; quantile crossing and coverage testing | Useful only with proper interval/quantile evaluation; do not call point regression calibrated probabilities. |
| Multi-task model / defer | Share information among horizons/assets | High / high; negative transfer and joint-label dependence | Justify against separate-horizon baselines before expanding architecture. |

## 11. Hyperparameter review

See the training companion's complete effective-parameter table. CPU deterministic+columnwise,
active .9 bagging/.9 features,31 leaves,.02 rate,500 trees,100 minimum child rows,L1 .1,L2 1 and
50-round Validation L2 stopping form a reasonable starting point. No empirical evidence proves
this is optimal, underfit or overfit. The claim “100 leaves' samples is certainly poor” is too
strong without effective-sample and stability measurements. Raw versus normalized labels change
loss scale and effective regularization. One seed establishes a reproducible reference, not
robustness. Official [LightGBM tuning guide](https://lightgbm.readthedocs.io/en/latest/Parameters-Tuning.html)
provides knobs, not finance-specific optimal numbers.

Record cap binding, best iteration, train/validation loss gaps and prediction/decision sensitivity.
Do not turn this audit into a large unregistered hyperparameter search before the first model.
Changing max_bin or GPU precision for speed changes numerical science and needs a new comparison.

## 12. Calibration review

**CODE-VERIFIED:** identity/affine candidates, least-squares slope/intercept, method selected by MAE
on a last-quarter row tail of Cal-A, then refit all Cal-A. Small candidate count is sensible. But
that internal tail is neither timestamp-grouped nor label-purged; nearby horizons can overlap.
Whole-Cal-A reliability after refit is in-sample descriptive. Negative slopes are possible;
calibration can reverse signs, so record stability and comparison with identity.

**Recommendation:** use a timestamp-defined purged internal split if claiming heldout method
selection. Do not blindly import Platt scaling (probabilities), unrestricted isotonic or quantile
mapping. A point estimate's units and loss must match the downstream expected-return hurdle;
probabilistic calibration requires a predictive distribution. This distinction is supported by
[Gneiting/Raftery](https://sites.stat.washington.edu/raftery/Research/PDF/Gneiting2007jasa.pdf).

## 13. Thresholding review

**CODE-VERIFIED:** LONG if calibrated raw forecast >=cost+chosen edge; SHORT mirrors; otherwise
NO_TRADE. Candidate edge grid2/4/6/8/10bps; minimum30 executable non-overlap Cal-B trades; maximize
mean net return, tie toward larger threshold. Global G0,cluster C0/H0,per-coin P0. Cal-B and TEST use
the same chronological per-symbol exclusion until actual exit. Thresholds never refit on TEST.
No minimum coverage or positive-expectancy gate exists; all-negative eligible candidates still trade.
The independent 30-trade probe reproduced this: every candidate had net expectancy **−0.0111**,
yet the selected global edge threshold was **10bps**, not NO_TRADE.

**Recommendation:** before economics qualification preregister a zero-expectancy no-trade comparator,
threshold stability/uncertainty and coverage/concentration safeguards. Prefer a broad stable region
or shrinkage to maximizing a noisy five-point estimate. Thirty trades is an eligibility floor,
not a confidence guarantee. Any optional abort/fold gate must be declared in the run identity;
retain failed/stopped trials rather than count only successes.

## 14. Precision, recall, F1 and action semantics

This is a regressor. Main forecasting quality is MAE/RMSE/skill, correlation/IC, stability and
coverage. Classification scores become meaningful only with an explicitly defined event and
frozen action rule. The training companion supplies TP/FP/TN/FN formulas for cost-clearing LONG
and SHORT events. Fixed raw-bps Train/Validation diagnostics are separate from Cal-B action
metrics; normalized-target live diagnostics currently have a unit-label issue.

Signal-level precision is not executed-trade hit rate, and no-trade is not automatically a true
negative in a three-class economic labeling scheme. Specificity, balanced accuracy and MCC are
possible after defining the event but are not implemented here; implementing them is lower value
than cost-aware expectancy/coverage and an honest null baseline.

## 15. Metrics, costs and execution review

**CODE-VERIFIED:** regression metrics reject nonfinite data and handle zero variance/ties explicitly;
cross-sectional IC averages eligible exact timestamps, >=3 assets. No dependence-adjusted IC
confidence interval is produced. Pooled Pearson can be dominated by asset scales or volatile regimes;
macro and timestamp-relative scores therefore complement it. The sampled population itself must be
audited, including attrition per symbol/segment/horizon. Current global coverage is measured after
finite filtering, so report prefilter attrition separately.

Configured costs are **11/14/20bps round trip** (8bps fees,1/2/4 spread,2/4/8 slippage). A forecast
with2bps selected edge must exceed13/16/22bps to signal under base costs. These are labeled research
assumptions, not measured account fees or market impact. The official [Binance fee page](https://www.binance.com/en/fee/futureFee)
returned no numeric fee rows to this audit; account tier/maker/taker/discount mechanics remain
unverified, and no account access was attempted. CoinSwitch-specific fees/tax are not inputs to the
canonical Binance experiment. No personal taxation claim is made.

Funding is absent even when a15–120m trade crosses settlement. The current [official funding description](https://www.binance.com/en/support/faq/detail/360033525031)
permits interval changes; do not assume every contract always settles8-hourly. Economic funding
needs signed historical settlement cash flows, not just a feature value. Slippage is not
volatility/size/depth-dependent. Bar opens are reference prices, not bid/ask fills; missing partial
fills/rejects/latency/capacity can matter. This is intraday bar-based research, not an order-book/HFT
simulator.

Per-trade mean/std, profit factor and additive exit-ordered drawdown are trade diagnostics, not
annualized portfolio Sharpe, Sortino or Calmar. Simultaneous symbols have no defined common capital
base. Fixed-policy stress preserves trade IDs and directions and is a genuine strength; adaptive
stress is separately labeled and does not retune thresholds. Preserve that distinction.

## 16. Multiple-testing review and false-discovery probability

**CODE-VERIFIED:**48 specs×16 folds=768 report opportunities, not768 independent hypotheses or
independent market histories. Within a spec, horizons overlap across rows; across specs, the same
market outcomes/feature families recur. Calibration,thresholds,seeds,manual revisions and aborted
runs add research degrees of freedom. The current Bonferroni helper only counts specs in supplied
CSV rows; it neither reconstructs all trials nor establishes valid p-values.

**Derived illustration, not a project estimate:** if48 independent null tests each have true5%
size, expected false rejections=2.4 and P(at least one)=1−.95^48=**91.47%**. Treating768 independent
null tests the same way gives approximately1−7.8e−18, but independence and the definition of one
hypothesis do not hold here. Bonferroni at48 registered hypotheses requires marginal p<=.05/48=
.00104167 for5% familywise control; valid marginal tests remain necessary. Multiplicity alone does
not give P(no edge|observed performance), which needs effect evidence, dependence assumptions and
a prior/selection model. No honest numeric posterior or PBO exists with zero completed canonical
reports.

**RESEARCH-SUPPORTED applications:** [White's Reality Check](https://doi.org/10.1111/1468-0262.00152)
and [Hansen SPA](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=264569) require aligned candidate
loss/return differences and appropriate dependence handling. [PBO/CSCV](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)
is a selection-degradation diagnostic, not a mandatory way to generate this causal history.
[DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) needs an interpretable return series,
selection accounting and distributional inputs; do not apply it mechanically to current per-trade
Sharpe. [Harvey/Liu/Zhu](https://www.nber.org/papers/w20592) supports treating broad finance searches
as a multiple-testing problem, not blindly importing one significance cutoff.

**Recommendation:** first register one primary model and decision procedure; preserve all trials.
Later use paired calendar-block/bootstrap loss/expectancy intervals resampling all symbols together,
with precommitted block-length sensitivity and candidate-family adjustment. Avoid row-iid standard
errors and asset-independent bootstrap. Holm/Bonferroni or an explicitly selected FDR procedure
can act on valid p-values; correction choice cannot fix invalid input statistics. DSR/PBO/SPA are
later tools if the needed data object exists, not a requirement to install every sophisticated test
before one smoke fit.

## 17. Reproducibility review

**CODE-VERIFIED:** stable feature order, sorted feature_time/symbol rows, deterministic CPU reference,
fixed seed, source/config hashes, OS/architecture/package identity, immutable receipts and cache
checks are valuable. Python/NumPy stochastic transforms are not used in primary deterministic feature
construction; KMeans uses the fixed seed. CPU bitwise claims remain scoped: the recorded environment
omits some compiler/BLAS/CPU-instruction/build details, and changing backend is expressly different.
Official [LightGBM reproducibility caveats](https://lightgbm.readthedocs.io/en/latest/FAQ.html) support
not promising cross-binary equality.

Prepared cache binds Gold/partitions/config/source/schema/target/fold/membership/descriptors/purge/
embargo/platform and verifies array-table alignment. Atomic marker checks and dead-owner recovery
are strong. In a temporary source copy, changing only hardening.py preserved the computed scientific hash
exactly (independent probe; production source was never edited). The omission of hardening module/active settings matters for **model and experiment**
resume; it need not force invalidation of scientifically identical prepared matrices. Preserve
this separation when proposing repairs. Local hashes/receipts are integrity/trust anchors under a
local trust model; they do not make a malicious joblib safe. Unregistered models load by default;
[scikit-learn persistence guidance](https://scikit-learn.org/stable/model_persistence.html) restricts
pickle-based loading to trusted sources.

## 18. RunPod, resources and failure recovery

**Derived size arithmetic:**50,352,548×109×8 bytes=**40.89GiB** if all long-format Gold feature rows
were materialized; dividing by four gives an **average**,10.22GiB/horizon. One fold's TRAIN matrix
is smaller; sorting,joined tables,Python-object symbols,Cal/Test tables,one-hot copies,cache IPC,
LightGBM bins/histograms and OS page cache add to peak. Total Gold rows includes repeated features
across horizons. No trustworthy peak RSS or fit-time price estimate follows from this arithmetic.

New `resource_estimate.py` calls integer average rows/horizon an upper bound and applies fixed copy
multipliers. That is a heuristic, not a necessary/sufficient capacity proof (IA-19). Unequal horizon
coverage can exceed the average; fixed multipliers may still miss native-library allocation peaks.
ComputeBudget uses os.cpu_count, which must be checked against actual container/cgroup CPU/RAM limits.
No RunPod SKU,price or required RAM is fabricated or recommended from an unmeasured fit.

**CODE-VERIFIED:** provider-neutral path overrides can relocate inputs/outputs under `/workspace`,
with logical checkpoint references and legacy-root remapping. Linux/uv/editable repository deployment
is plausible; a wheel alone is not the full scientific workspace. Model-registry absolute paths,
source/environment compatibility,baseline contracts,protected roots and bootstrap paths must be
validated after transfer. Existing GCE guest/control-plane supervision is not a tested RunPod budget
controller. The generic CLI does not enforce all newer runtime contracts (IA-11).

[RunPod official storage docs](https://docs.runpod.io/pods/storage/types) distinguish ephemeral
container disk,pod volume lifetime and independent network volumes. Do not assume all `/workspace`
mounts have equivalent locking/atomic-rename/fsync performance. Local leases intentionally fail
closed for unknown foreign-host owners. Qualify the selected filesystem and crash/restart behavior
before relying on it. Preserve off-pod evidence and separately authorized deadline shutdown. No
storage was provisioned or compute started by this audit.

CPU remains reference. A GPU fit attests fitted backend plus live PID/device evidence; no silent
CPU fallback. However the APPROVED ladder is not enforced at ordinary fit admission (IA-12).
Identical seeds or numeric correlations alone do not establish the same Cal-B thresholds/trade
policy. Pin CPU for smoke; GPU comparisons require separately registered limits and policy evidence.

## 19. Literature review

The [literature companion](crypto2_literature_comparison_20261106.md) provides verified primary
links,authors,year,evidence level,checked scope,relevance and limitations. It includes foundational
selection/validation work,crypto factor/carry evidence,modern tabular/sequence models,2025 negative
forecasting evidence and a2026 cost-aware hourly BTC preprint. Their horizons/data/OOS/cost details
are included only where actually verified; no missing backtest detail is invented.

**INFERENCE:** plausible forecast structure may live in common market moves,cross-asset relative
strength,temporary flow/liquidity effects and financing demand. These are hypotheses to test, not
results. Even a stable positive IC or lower RMSE may not clear execution costs; the2026 hourly
preprint offers a relevant caution without proving this study's edge
([Bysik/Ślepaczuk](https://arxiv.org/abs/2606.00060)). Positive weekly factor and negative univariate
forecast findings study different objects and should both be reported.

## 20. Industry/practitioner comparison

**PRACTITIONER-OBSERVATION:** AQR's [execution-cost work](https://www.aqr.com/insights/research/working-paper/trading-costs-of-asset-pricing-anomalies)
uses measured institutional transactions rather than a universal impact number; it is not a
source for crypto-specific numerical slippage. The project already separates market data,features,
models,policy and cost stress, which is a sensible research organization. The largest remaining
practical gaps are an audit-ready trial ledger, validated data movement/runtime, and market-matched
execution evidence. MLflow/W&B could organize artifacts but would not correct the current
scientific issues; custom immutable manifests are adequate if their completeness is enforced.

## 21. X/Twitter findings

**PRACTITIONER-OBSERVATION / anecdote only:** public searches produced no attributable technical
posts used here. Opening [López de Prado's profile](https://x.com/lopezdeprado) returned403. No tweets,
quotes or implied consensus were invented; the author's primary research is cited instead.

## 22. Reddit/community findings

**PRACTITIONER-OBSERVATION / anecdote only:** accessible threads discussed
[walk-forward practice](https://www.reddit.com/r/quant/comments/13q4qkk),
[CV disagreement](https://www.reddit.com/r/quant/comments/1701fzi) and
[slippage estimation](https://www.reddit.com/r/algotrading/comments/11dvm8j).
They illustrate practitioner concerns and disagreement, not scientific evidence or reliable
numerical costs. No community claim sets this audit's validity criterion.

## 23. GitHub/open-source comparison

[Qlib](https://github.com/microsoft/qlib) offers modular research workflows;
[FinRL](https://github.com/AI4Finance-Foundation/FinRL) uses a distinct RL environment/process;
[vectorbt](https://vectorbt.dev/api/portfolio/base/) exposes fee/slippage/order accounting;
[Backtrader](https://www.backtrader.com/docu/slippage/slippage/) documents broker fill assumptions;
[Freqtrade](https://github.com/freqtrade/freqtrade/blob/develop/docs/lookahead-analysis.md) documents
lookahead analysis and cross-sectional caveats. These were inspected at the architecture/API/docs
level, not fully code-audited or replicated. Learn explicit boundaries and perturbation checks;
do not copy their example splits/calendars/cost assumptions blindly. Adopting a framework is not a
necessary fix for current weaknesses.

## 24. Loophole register

[Independent IA-01–IA-24 register](crypto2_loophole_register_20261106.md) records severity,category,
file/function/lines,problem,bias/likelihood,reproduction,evidence,fix,test and scientific/RunPod
blocker status for every independent issue. HIGH severity denotes potential consequence, not proof
that a real completed result is corrupted. No current Phase7A completed result was available.

## 25. Architecture rating

The [independent scorecard](crypto2_architecture_scorecard_20261106.md) rates all 41 requested
subsystems individually with confidence. Scores reflect different goals: causal engineering can be
strong while trading realism and inference remain weak. They are not probabilities of success.

## 26. Strengths

**CODE-VERIFIED:** clear source-domain isolation and decimal precision; historical registry rather
than current-list-only membership; HNT retained; fold eligibility based on known history; actual
label endpoints plus latency; explicit purged Cal-A/B; completed HTF joins; selected finite-row
accounting; baseline/control variants; correct per-symbol non-overlap; fixed-trade cost stress;
atomic cache/model/report boundaries; corrupt/incompatible evidence fails closed; test coverage
for scientific/operational regression; no active research import of legacy order-capable modules.

**DATA-VERIFIED:**689 targeted and1162 full synthetic/unit/integration checks passed locally.
These strengthen confidence in contracts, not in edge or real-market-data completeness.

## 27. Weaknesses and unnecessary complexity

**INFERENCE:** the architecture has accumulated guards,wrappers,scopes and reports faster than
independent empirical qualification. `training.py` exceeds2100 lines and mixes scientific pipeline,
cache state,publication and reporting. A simple CSV helper can undo stronger checkpoint guarantees
if treated as qualification authority. Source hashes conservatively invalidate prepared state for
many unrelated changes while omitting one actually consequential hardening module. The48-spec grid
is large before proving one pipeline's cost/evidence. Exact feature duplicates add little scientific
content. Deferred future-model/risk interfaces must remain disabled and should not distract the
first baseline experiment. These are simplification opportunities, not authorization to refactor.

## 28. Critical blockers

No CRITICAL proven active price leak was found. There are HIGH scientific/operational blockers to
trusting broad discovery claims and to paying for an unqualified runtime. For the requested one
raw G0 smoke: missing real-data/context/cache equivalence proof; required Linux/lint/format gate;
complete run/selection identity; central admission or a narrowly enforced safe entrypoint; a frozen
single-spec diagnostic plan; and current provider/storage/deadline/cost authority. Do not treat
funding or a new deep model as a reason to rewrite the regressor before testing its plumbing.

## 29. Recommended improvements and from-scratch architecture

**OPINION/RECOMMENDATION:** preserve immutable data,scientific timing,Core20 and fixed test plan.
Fix evidence and control boundaries first. Costs below are relative implementation/compute effort,
not currency estimates.

| Option | Architecture while preserving goal/historical dataset | Expected scientific benefit | Effort / recommendation |
| --- | --- | --- | --- |
| A: minimal changes | Keep Bronze/Silver/Gold/v2/109 inputs/G0; verify feature-only context completeness; bind run controls; authoritative unique results; CPU single-spec smoke; label current economics honestly | Prevents avoidable false qualification and expensive ambiguous runs | Low–medium engineering, lowest new compute. **Choose now.** |
| B: stronger research | A + independent identical-key baseline OOS scoring, registered sequential selector, block-dependent uncertainty, feature-only source sidecar where needed, offline funding/cost-capacity scenarios, tiny ablation/sensitivity ledger | Stronger evidence separating forecast skill from selection and friction | Medium engineering/compute; choose after smoke/resource evidence, before tradability claims. |
| C: research-grade ideal | B + streamable feature store with event/knowledge times and persistent recursive states, fully versioned experiment compiler/selector, matched event-driven offline execution/capital accounting, richer path robustness and independently replicated pipeline | Strongest failure transparency and economic interpretability | High effort/data/compute and new degrees of freedom. Not justified automatically; CPCV/sequence models remain optional. |

No plan turns August into an available research resource. No cloud provider or execution deployment
is authorized by choosing an architecture option. A custom offline evaluation ledger is higher
value now than adding a SaaS tracker or RL/neural stack.

## 30. Experiments required and cheapest progression

**Proposals only; no real experiments executed here and no full-grid authorization.**

| Stage | Work | Acceptance / stop rule |
| --- | --- | --- |
| 0: evidence gates | Separate repairs; Linux full gate; verified existing Gold/checkpoints; actual feature-key/M-01 and row census; bounded preparation-only profile/equivalence if separately authorized | Zero forbidden rows; exact key/schema/dtype/mask equality or predeclared numerical tolerance; no silent attrition; no unresolved identity mismatch. Never rebuild valid acquisition/Gold. |
| 1: one smoke | Exactly architecture-G0-A6-60m-raw,first canonical fold,CORE,CPU,one logical worker; isolated smoke identity | Fit/calibrate/select/report/checkpoint complete within fresh budget; successful reload; correct ownership and finite diagnostics. Weak performance or NO_TRADE is a legitimate result. |
| 2: one precommitted procedure | Only after a new owner decision, evaluate the same chosen procedure across the canonical16 folds,with registered identical-key controls | All folds/statuses retained; no selecting the primary after viewing results; report uncertainty/concentration/coverage and honest costs. This audit does not approve that run. |
| 3: bounded mechanism study | One native-only,+12h,+1d,no-market-context comparison; symbol-ID control only if useful; raw/normalized only after scale issue review | Register the family before looking; same scored row keys or explicit matched-population comparison. Do not call incomparable finite-row populations an ablation gain. |
| 4: sensitivity | At most two extra seeds around fixed baseline; one modest leaf/penalty neighbor; fixed trade-ID cost and threshold-neighbor stress | Predeclare grids/selection rule and record all trials. No exhaustive Cartesian product of every option. |
| 5: synthesis | Review one primary procedure and explicitly labeled challengers with valid time/dependence-aware inference/economics | An unadjusted lucky fold or an invalid significance flag cannot promote a model. August still locked; no holdout stage scheduled. |

### Proposed precommitted success criteria

Engineering smoke success is **not** alpha discovery: exact registered inputs,correct chronology,
completed model/report/checkpoint,successful hash/reload,resource budget compliance and no forbidden
period access. Forecast failure is not an engineering failure.

For any later discovery study, preregister: one primary target/model/objective; complete trial family;
canonical fold set; scored row keys/coverage; how baseline comparisons use identical rows and weights;
metric/CI/resampling procedure; cost/funding/capacity scenario; minimum trade/coverage/concentration
rules; thresholds and economic accept/reject logic. A reasonable proposed statistical gate is a
positive dependence-aware95% interval for paired primary loss improvement after declared family
adjustment, plus stable timestamp IC as a secondary diagnostic. A proposed economic gate is positive
net expectancy under the registered conservative scenario with a positive dependence-aware lower
bound, adequate breadth, and no dependence on a single symbol/month. Neither threshold is selected
from current TEST outcomes. The existing10/16 success placeholders are not a valid substitute for
this protocol and can even be passed by duplicates today. Specific trade-count/coverage/capacity
numbers require declared intended exposure and measured data; inventing them here would be false
precision. These are proposals for a separately approved protocol, not changed code or guarantees.

## 31. What NOT to change

Preserve Phases1–6 and their artifacts; canonical v2 timing/horizons,actual endpoint purging,
120m gap,Core20/PIT method,retained HNT,July exclusion,permanent August lock,separate USD-M/Spot
source identity,immutable Bronze/Gold and explicit missingness. Do not remove HNT,force XPIN,
forward-fill data,rerun valid discovery/acquisition/Gold,install a fashionable neural stack,add
portfolio/leverage/risk/TP-SL engines,start live legacy files or cloud compute. Do not label the
historical0/48 incomplete Fold1 as bad predictive performance.

## 32. What to fix BEFORE training

For **one scientifically meaningful raw G0 smoke**, in order:

1. Freeze one exact source/environment tree and the named one-spec plan. Resolve current lint/format
   failures in a separate repair task; full Linux verification must pass. This macOS suite does not
   replace Linux process/filesystem/resource validation.
2. Bind hardening module/active scientific controls to model/run compatibility; freeze abort/pilot/
   scope policy. Fix result uniqueness/inference or explicitly disable all discovery/success claims
   for the smoke. Report-only config recording is insufficient for silent resume prevention.
3. Validate existing acquisition/candle/Gold identities and hashes; produce exact fold/horizon
   membership/row/attrition/M-01 census using permitted research sources. Do not accept “bounded
   risk” without data. If a feature-only source is needed, propose it separately and preserve Gold.
4. Qualify preparation/cache on the actual Linux dataset under separate bounded authority: row keys,
   feature order,dtypes,arrays,finite masks and predictions/reports; profile real RSS/disk/stage time.
   Do not rely on the average-as-upper-bound resource estimator. Full cache creation is not authorized
   by this audit.
5. Ensure the selected common training entrypoint enforces read-only cache,explicit resource floors,
   CPU backend,one logical worker and isolated smoke output. Enforce provider/container filesystem,
   artifact transfer/backup and independent deadline/cost contract before any paid resource starts.
6. Keep economics explicitly provisional. The smoke may report current cost scenarios and NO_TRADE;
   it must not assert tradable profitability, valid p-values or completed canonical qualification.

No repair or launch was done; this is the concrete review outcome for the requested separate repair
decision. A fresh owner cost/deadline authorization remains necessary under repository instructions.

## 33. What can wait until later

Funding/capacity/executable-price economics must precede any **tradable-edge** claim but need not
precede a tightly labeled regression plumbing smoke. H0 correction independence,Cal-A internal
purging,normalized inverse/subfloor census,live metric units,feature duplicates/chunk recursive
state,small seed/leaf sensitivity and stronger baseline scoring are bounded research improvements.
Actual role-safe model selection/trial accounting must precede broad comparison/qualification.
Quantile/rank/residual targets,other tree libraries,neural models,CPCV/DSR/PBO/SPA implementations,
SaaS tracking and future execution are deferred unless evidence justifies them. August is not
waiting for a future release in this plan; it remains permanently locked.

## 34. Overall score and ranked priorities

**OPINION/RECOMMENDATION:** Scientific6.5/10; engineering7.5; rigor4; trading realism3.5;
reproducibility6.5; RunPod readiness4.5. These are judgmental readiness scores, not project
profitability probabilities. The architecture is strong enough to preserve and qualify, with
conditional justification for one smoke after gates; it is not evidence for paid grid training.

### TOP 20 RISKS

Impact/probability/difficulty are qualitative judgments. Probability means likelihood of the
mechanism or misuse under the described condition, not a calibrated frequency of model failure.
UNKNOWN marks a required real-data check. Difficulty: L=small localized change/protocol,M=moderate,
H=requires actual data/provider/methodology qualification.

| Rank | Risk / register | Impact | Probability | Difficulty to fix |
| ---: | --- | --- | --- | --- |
| 1 | Development-selected validation significance / IA-01 | False discovery | High if helper trusted | M |
| 2 | Later Validation contains earlier TEST in final selection / IA-03 | Invalid historical winner confirmation | High if all-fold winner is retrospectively promoted | M |
| 3 | Unverified feature availability/M-01 / IA-05 | Context leak or preparation block | UNKNOWN real incidence | H |
| 4 | Incomplete control/source resume identity / IA-04 | Mixed scientific experiment | Medium after config/code edits | M |
| 5 | Duplicate result rows pass significance/success / IA-02 | False qualification | Medium conditional on table reuse/merge | L–M |
| 6 | Absent current Gold/cache/equivalence proof / IA-10 | Invalid population or expensive restart | UNKNOWN defect; gate definitely missing | H |
| 7 | Missing funding / IA-06 | Small apparent net edge disappears or changes sign | High exposure potential; magnitude UNKNOWN | M |
| 8 | Flat slippage/unverified fees/open fills / IA-07 | Non-executable profitability | High for marginal illiquid signals | H |
| 9 | Trade stats mistaken for portfolio stats / IA-08 | Misleading risk-adjusted results | High if headline Sharpe is reused | M |
| 10 | Generic entrypoint bypasses stronger admission / IA-11 | Cost/resource-safety failure | Medium conditional on CLI choice | M |
| 11 | RunPod storage/deadline/cgroup unqualified / IA-23 | Lost artifacts or unbounded spend | Medium on migration | H |
| 12 | Local lint/format plus Linux gate incomplete / IA-09 | Required release evidence missing | Certain current gate failure | L for style; M for Linux |
| 13 | Negative expectancy threshold forced into trading / IA-15 | Bad policy / noisy threshold selection | Medium; empirical rate UNKNOWN | L–M |
| 14 | CSV/report/checkpoint crash gap / IA-20 | Missing/biased results inventory | Medium on interrupted runs | M |
| 15 | Unequal fit budgets/weights and no independent baseline scores / IA-16 | Inflated claimed model advantage | High by design; size UNKNOWN | M |
| 16 | Cal-A internal no purge/grouping / IA-13 | Optimistic calibrator choice | High overlap mechanism; size UNKNOWN | M |
| 17 | H0 Validation refit/stop reuse / IA-14 | Favorable development comparison | Certain for H0; raw G0 unaffected | M |
| 18 | GPU approval ladder not enforced / IA-12 | Incomparable numeric/policy outputs | Medium if GPU chosen; avoid for CPU smoke | M |
| 19 | Average-based resource “upper bound” / IA-19 | Misleading capacity admission | High heuristic imprecision | L for labeling; H for profiling |
| 20 | Regime/seed/feature-state sensitivity unmeasured / IA-22 and protocol | A fragile signal mistaken for robust one | UNKNOWN real effects | M |

### TOP 20 IMPROVEMENTS

Expected value is this reviewer's judgment, conditional on eventually obtaining data access and
separate repair/compute authority. Effort refers to implementation/qualification, not automatic
approval to run it.

| Rank | Improvement | Scientific value | Expected benefit | Effort |
| ---: | --- | --- | --- | --- |
| 1 | Precommit one primary procedure and selection chronology | Very high | Prevents retroactive winner stories | Low |
| 2 | Bind hardening/run/model semantics into enforceable resume identity | Very high | Stops mixed-policy reuse | Medium |
| 3 | Establish independent feature-key/M-01 census and sidecar proposal if needed | Very high | Proves context observability population | High data qualification |
| 4 | Unique canonical report ledger; reject duplicate/mixed/incomplete folds | Very high | Prevents false success and reconstructs trials | Medium |
| 5 | Demote invalid validation p-values; preregister appropriate inference | Very high | Removes misleading “significant” flags | Low–medium |
| 6 | Validate existing Gold/checkpoints and real cache equivalence | Very high | Prevents stale/corrupt/misaligned work | High qualification |
| 7 | Finish style and full Linux gate on frozen source | High | Establishes required release baseline | Low–medium |
| 8 | Measure one actual preparation path before fit | High | Real resource/cost projection | Medium, separately bounded |
| 9 | Common strict entrypoint admission; CPU/one worker/read-only cache | High | Avoids inadvertent heavy preparation/backend drift | Medium |
| 10 | RunPod-specific verified storage/backup/deadline contract | High operational | Limits loss and uncontrolled spend | Medium–high |
| 11 | Independent matched-key zero/mean/Ridge/recent-return controls | High | Quantifies incremental signal | Medium |
| 12 | Timestamp-block paired uncertainty preserving cross-asset dependence | High | Credible intervals and hypothesis tests | Medium |
| 13 | Offline signed historical funding accounting | High economic | Corrects perpetual cash-flow omission | Medium |
| 14 | Executable-price/size/volatility cost frontier | High economic | Tests implementability/capacity | High data effort |
| 15 | Explicit no-trade comparator and robust threshold protocol | High | Avoids trading negative Cal-B estimates | Medium |
| 16 | Timestamp-grouped purged internal calibration selection | Medium | More honest method comparison | Medium |
| 17 | Rebuild CSV deterministically from authoritative report/checkpoint set | Medium–high | Restores crash-safe complete results view | Medium |
| 18 | Small seed/leaf/penalty and threshold sensitivity ledger | Medium | Exposes fragility without a giant search | Low engineering, bounded compute |
| 19 | Same-population native/HTF/context ablations and recursive-state check | Medium | Locates incremental information and chunk effects | Medium |
| 20 | DSR/PBO/SPA only after required aligned return/trial objects exist | Conditional medium | Later selection robustness with explicit assumptions | Medium–high |

### The most important question

“If we train the current architecture exactly as it exists today, what is the biggest reason the
results could fool us into believing we have an edge when we actually do not?”

**Primary answer: selecting and validating a lucky development winner as though its historical
performance were independent evidence.** The current helpers combine early-stopping-selected
Validation scores with insufficient dependence/selection accounting; later-fold Validation can
contain earlier TEST outcomes. Calling a ranking “Validation only” or applying Bonferroni does not
resolve that chronology.

The next four are: **(2)** interpreting fixed-cost,no-funding,bar-open trade scenarios as executable
net returns; **(3)** future label availability conditioning the context/evaluation population through
Gold unless the independent census clears it; **(4)** mixed-control resume or duplicated/incomplete
result tables making evidence appear more complete than it is; **(5)** treating many correlated
asset/bar/horizon observations or non-portfolio Sharpe as robust independent statistical evidence.

**Final GO/NO-GO: GO_AFTER_FIXING_SPECIFIC_BLOCKERS.** Exactly one scientifically registered raw G0
CPU smoke may be justified after section 32's gates and separate cost/deadline authority. No full
grid is authorized, no profitable model is established, and August remains permanently locked.
