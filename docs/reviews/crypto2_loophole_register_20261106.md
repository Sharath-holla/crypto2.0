> **Independent audit update:** Original findings below are preserved from concurrent commit
> `c249e28`. The independent register appended below supersedes conflicting dispositions.
> In particular, Core20 is not selected from today's survivors, M-01 is not quantitatively
> cleared, and report-only recording of hardening settings is not a resume compatibility check.

# Crypto 2.0: loophole register (2026-11-06)

Severity is my judgement. "Sci" = scientific blocker for trusting results; "RP" = blocker for paid
RunPod training. Evidence: CV = code-verified, DV = data-verified, INF = inference.

| ID | Sev | Area / where | Problem | Why it matters / bias direction | Evidence | Fix + test | Sci | RP |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LH-01 | HIGH | Selection: 48 specs x 16 folds | Winner's curse. Best-of-48 on a noisy metric is biased upward; Bonferroni on validation skill is the only correction | Inflates apparent edge | CV (`hardening.rank_specs_with_correction`) | Precommit one primary spec + criteria; report DSR/PBO-style adjustments; test: ranking never uses Test | YES | NO |
| LH-02 | HIGH | Costs: `config.CostConfig` | No funding; flat bps slippage independent of volatility/size; fills at open | Net PnL optimistic, worst for longer holds and fast markets | CV | Add funding series cost and a volatility-scaled slippage sensitivity; synthetic-PnL tests | YES | NO |
| LH-03 | HIGH | Gates | Full pytest, ruff, `uv sync`, `verify_linux` not proven on the branch tip | Unknown regressions reach paid compute | TEST gap | Run them (section 23 of the repair report) | NO | **YES** |
| LH-04 | MED | M-01 residual: Gold inner join with labels | Rows near series ends missing in Gold because labels were unavailable could alter other symbols' cross-section at those timestamps | Small, bounded to the last 2+h bars of each symbol and delisting events | CV + INF; size NOT measured | Count affected (symbol, time) rows per horizon/fold; fold-edge test | YES (until measured) | NO |
| LH-05 | MED | L-04 `models.py` H0 | H0 corrections fit on the early-stopping validation set | H0 results mildly optimistic; no Test leakage | CV | Dedicated correction slice or label H0 results accordingly | NO | NO |
| LH-06 | MED | Hyperparameters | `min_child_samples=100`, weak L1/L2 for noisy data; single seed | More noise fitting; seed variance hidden | CV; judgement INF | Small sensitivity grid on Fold 1 validation only; 3 seeds | NO | NO |
| LH-07 | MED | Universe | Core20 fixed at 2022-01-01 from coins that exist today | Survivorship: dead/delisted coins absent; probably flatters momentum-type signals | INF (selection of survivors not re-read) | Quantify via listing history; document as limit | YES (limit) | NO |
| LH-08 | MED | Target | L2 on raw returns is outlier-driven | Fits a few extreme bars; RMSE gains may be tail artefacts | INF | Report robust metrics (rank IC, winsorised error) alongside | NO | NO |
| LH-09 | MED | Success criteria | Placeholders (10/16 folds) | Post-hoc rationalisation risk if edited after results | CV | Owner signs numbers before any grid | YES | NO |
| LH-10 | MED | Silver | Local mirror completeness unknown; download in progress | A gap census on partial data is meaningless | DV (progress log) | Verify against remote inventory when the download ends | NO | **YES** for Gold rebuilds only |
| LH-11 | LOW | Cache | No test that a context-semantics change invalidates the cache (it should, via source hashes) | A future refactor could bypass the hash binding | CV | Add test mutating the context source hash | NO | NO |
| LH-12 | LOW | Results table | No seed / best_iteration / fit seconds columns | Weaker audit trail | CV | Add columns from model metadata | NO | NO |
| LH-13 | LOW | Metrics | Cross-sectional IC absent from the validation baselines | Cannot compare IC vs baselines per fold | CV | Compute per-timestamp IC with min-assets guard | NO | NO |
| LH-14 | LOW | CPU vs GPU | Equivalence unproven | Mixed-backend runs could differ | CV (code records "not bitwise") | Choose CPU for the smoke run | NO | NO |
| LH-15 | LOW | Legacy order code | `live_trader.py` etc. still in the repo | Accidental execution | CV | Headers + isolation test exist; move to a separate repo (owner decision) | NO | NO |
| LH-16 | INFO | Config hash | Phase 7B settings outside it (recorded in reports) | Resume with different pilot settings | CV | Compare `hardening_config` across reports | NO | NO |
| LH-17 | INFO | Duplicate inference | `data/` vs `pipeline/inference.py` differ in one rule | Confusion only | CV | Deferred | NO | NO |
| LH-18 | INFO | Regime coverage | No regime segmentation of results | One regime could carry the average | INF | Report per-fold volatility regime using past-only definitions | NO | NO |


---

# Independent loophole register

All severities, likelihoods and priorities are **OPINION/RECOMMENDATION**. Evidence tags distinguish
source facts, synthetic data and inference. Line ranges are approximate at source tree `687e697`,
unchanged by documentation-only `c249e28`. “Scientific blocker” means blocks an associated discovery,
tradability or reproducibility claim; it does not automatically block a tightly labeled raw G0
engineering smoke. “RunPod blocker” means must be resolved/qualified before paid smoke under the
current handoff requirements. This register does not assert every possible defect has been found.

## IA-01 — Statistical inference (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:621-674`.
- **Function/class:** `_one_sided_p / rank_specs_with_correction`.
- **Problem:** P-values use validation skill from estimators whose best iteration was selected on that same validation set. The t test assumes a sampling model not established here; equal positive skill produces p=0. Bonferroni cannot repair invalid marginal p-values. The config correction label is returned even though the computation always multiplies by trial count.
- **Impact / bias / likelihood:** Optimistic evidence of discovery; HIGH chance of misuse if the CLI significance field is treated as a research gate. Does not itself leak TEST into an individual G0 fit.
- **How to reproduce:** Feed constant positive skill values to _one_sided_p; inspect models._fit early stopping. Independent probes also demonstrate an extreme p-value from repeated identical rows.
- **Evidence:** CODE-VERIFIED; synthetic probe duplicate_ranking. Research comparison: White/Hansen/Harvey sources in literature companion.
- **Recommended fix:** Demote this to descriptive ranking; preregister independent evaluation and dependence-aware paired loss tests. Validate supported correction names and record every trial.
- **Test required:** Null simulations must include the complete stopping/selection procedure; no significant-discovery claim from validation-only fitting diagnostics.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-02 — Aggregation (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:635-705`.
- **Function/class:** `rank_specs_with_correction / evaluate_success`.
- **Problem:** Neither helper deduplicates (run, view, spec, fold), validates report identity/status, or requires the canonical fold set. Ten copies of one fold count as ten successful folds. Rank groups only by spec name.
- **Impact / bias / likelihood:** False success and overstated significance if CSVs are duplicated, merged or replayed. Conditional likelihood MEDIUM; defect deterministic on input.
- **How to reproduce:** Run preserved probes.py: ten copies with fold_id=same-fold pass evaluate_success; ranking reports folds_seen=1 but folds_scored=10 and significant=true.
- **Evidence:** DATA-VERIFIED synthetic outputs, not model performance.
- **Recommended fix:** Rebuild a unique registered result table from immutable report/checkpoint manifests. Reject duplicates/conflicts and mixed experiments; require canonical completion before qualification.
- **Test required:** Duplicate, conflicting, missing, ineligible and cross-run rows must never increase fold count or significance.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-03 — Selection chronology (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:635-674; src/crypto_ai/phase5/folds.py:56-103`.
- **Function/class:** `rank_specs_with_correction / plan_folds`.
- **Problem:** Aggregating all folds' Validation scores to pick a spec and reporting that winner's whole historical TEST path is not sequential out-of-sample selection. Fold 0 TEST [2022-07-01,2022-10-01) is Fold 2 Validation; later selection can consume earlier TEST outcomes under a different role.
- **Impact / bias / likelihood:** Winner's historical OOS record becomes research-selection evidence, not independent confirmation. HIGH if final all-fold ranking is used to choose a purported historically deployable winner.
- **How to reproduce:** Compare probes.json folds 0 and 2. No fit required. Current helper has no as-of argument to prohibit future folds.
- **Evidence:** CODE-VERIFIED calendar and helper. INFERENCE about potential downstream misuse; sequential fixed-procedure refitting is legitimate.
- **Recommended fix:** Freeze one primary procedure now. Any dynamic selector must use only scores whose labels end before its decision time. Treat all-historical ranking as exploratory.
- **Test required:** Changing later validation outcomes must not change an earlier selected spec or earlier predictions.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-04 — Scientific identity (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/training.py:159-213,598-650,1776-1811; src/crypto_ai/phase7/hardening.py:35-81`.
- **Function/class:** `TRAINING_CRITICAL_SOURCE_FILES / checkpoint identity / current_config`.
- **Problem:** hardening.py is absent from the scientific source list. Its TOML values are not bound into fitted-model or training-stage resume identity. Per-report hardening_config is recorded but not compared when reusing completed reports. Abort/pilot/gate/baseline changes may mix in one run. The lru_cache also ignores edits to the same config path during a process.
- **Impact / bias / likelihood:** Incompatible or misleading mixed-policy experiments can be silently reused. MEDIUM likelihood after settings changes; no existing real result is alleged corrupted.
- **How to reproduce:** probes.json hardening_module_in_scientific_identity=false; compare report recording with checkpoint metadata. Two HardeningConfig instances have the same frozen Phase7Config hash. An independent temporary-copy mutation of hardening.py also preserved the actual scientific source digest.
- **Evidence:** CODE-VERIFIED. Existing earlier N-03 recording improves traceability but does not enforce compatibility.
- **Recommended fix:** Separate preparation semantics from fitted-model/selection semantics. Hash the active hardening module and policy config in model/run resume identity without invalidating unrelated immutable Gold.
- **Test required:** Changing abort, baseline, scope or selection settings must refuse incompatible model/report resume; logging-only changes may have an explicit exemption.
- **Scientific blocker:** YES; **RunPod blocker:** YES.

## IA-05 — M-01 context completeness (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/gold.py:35-61; src/crypto_ai/phase7/features.py:551-651; src/crypto_ai/phase7/training.py:456-483`.
- **Function/class:** `_joined_gold_table / build_fold_context_table / _load_fold_context_source`.
- **Problem:** All horizons are unioned after a feature/label inner join. Future path absence can erase every horizon for a symbol/time. Witness count/hash rejects partial-membership loss, but cannot detect a timestamp erased for every symbol because no witness row survives. Production incidence is not measured.
- **Impact / bias / likelihood:** Unchecked union changes past peer context; current production guard usually stops instead. HIGH significance, real frequency UNKNOWN. Classify unresolved production risk as MATERIAL_RISK, not NO_RISK or negligible.
- **How to reproduce:** Synthetic 4-symbol/260-candle fixture with one future SOL gap: 1039 feature keys -> 1014 union keys; partial loss raises M01_CONTEXT_SOURCE_INCOMPLETE. Removing a full timestamp from otherwise valid witnessed rows passes.
- **Evidence:** DATA-VERIFIED synthetic; existing independent_review_context and m01_label_perturbation tests passed. Actual 138 partitions not locally accessible.
- **Recommended fix:** Perform an independent feature-key census using verified feature-only source evidence. If incomplete, propose an identity-bound feature-only context sidecar, preserving immutable Gold; do not disable the guard.
- **Test required:** Future gap, delisting, whole-market timestamp loss, horizon changes and all fold edges must preserve available features or stop with a quantified reason.
- **Scientific blocker:** YES; **RunPod blocker:** YES.

## IA-06 — Economics: funding (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/economics.py:199-257; src/crypto_ai/phase7/hardening.py:376-424`.
- **Function/class:** `build_oos_trades / trading_metrics`.
- **Problem:** Funding charges are never deducted; output explicitly says NOT_MODELLED. A historical funding feature is not a settlement cash flow.
- **Impact / bias / likelihood:** Net returns can be biased either way; adverse carry may erase a small apparent edge. Conditional exposure occurs when a hold crosses a settlement.
- **How to reproduce:** Read net_return = gross - base_cost_bps/10000 and absence of funding timestamps in trade construction.
- **Evidence:** CODE-VERIFIED; official Binance funding source in literature companion. Actual exposure count UNKNOWN.
- **Recommended fix:** Before tradability claims, evaluate signed settlement charges on the preserved trade set with historical contract-specific schedules and mark/notional conventions.
- **Test required:** Long/short, positive/negative funding, zero/one/multiple settlements and exact-boundary tests; report funding separately.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-07 — Execution realism (HIGH)

- **File / approximate lines:** `configs/phase7/research_core20_primary_v1.toml:113-141; src/crypto_ai/phase7/economics.py:75-117,199-257`.
- **Function/class:** `CostConfig / _policy_indices / build_oos_trades`.
- **Problem:** Fee 4bps/side is unverified for the intended future account. Spread/slippage are fixed tier penalties; notional, participation, depth, partial fills and rejects are absent. open[i+2] provides timing separation but not a guaranteed fill.
- **Impact / bias / likelihood:** Apparent tradability may rely on cheap or inaccessible fills; likelihood HIGH for interpreting marginal lower-liquidity signals. No current account fee claim can be certified.
- **How to reproduce:** Costs are a function of TRAIN-frozen tier only. Vary size or volatility with the same tier: penalty remains unchanged.
- **Evidence:** CODE-VERIFIED; Binance fee page returned no numeric table. Practitioner research comparison in literature file.
- **Recommended fix:** Keep frozen costs as labeled research assumptions; later add size/volatility/participation scenarios and public executable-price evidence in a separately versioned economics study.
- **Test required:** Hand-computed fills/fees; sensitivity at 1/1.25/1.5/2x with identical trade IDs; capacity stress must change assumed impact.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-08 — Trading metric interpretation (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:376-424`.
- **Function/class:** `trading_metrics`.
- **Problem:** Per-trade mean/std and additive cumulative trade-return drawdown are not time-based portfolio Sharpe/drawdown. Multiple symbols can be concurrently active; no cash allocation, common capital denominator or mark-to-market path exists. Equal-exit ordering can affect drawdown.
- **Impact / bias / likelihood:** An impressive Sharpe/drawdown can be economically uninterpretable if presented as a funded strategy. HIGH misuse risk; metrics are currently documented as per-trade.
- **How to reproduce:** Sum two simultaneous equal-notional symbol returns: summed return has no defined starting portfolio capital. Permute tied exits to inspect additive drawdown sensitivity.
- **Evidence:** CODE-VERIFIED implementation and docstring; INFERENCE about presentation misuse.
- **Recommended fix:** Retain expectancy and per-trade descriptions. Before risk-adjusted performance claims, define an offline capital-normalized return series; no live risk engine is authorized here.
- **Test required:** Concurrent symbols, tied exits, no trades and all-win/all-loss paths with explicit metric denominators.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-09 — Verification gates (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/training.py:1249-1250,2035; src/crypto_ai/phase7/verify_linux.py:22-115`.
- **Function/class:** `local checks / verify_linux`.
- **Problem:** Current local tests pass, but Ruff lint has three E501 comments and Ruff format has two unformatted files. Full Linux gate, actual-data cache equivalence and resource profile are not verified by the Mac test suite.
- **Impact / bias / likelihood:** Paid compute would start without required engineering evidence. Lint issue itself is LOW scientific impact; the release gate is blocked.
- **How to reproduce:** Read evidence pytest.log, ruff_check.log, ruff_format.log. No code was changed to make them pass.
- **Evidence:** DATA-VERIFIED local checks: 689 targeted / 1162 full tests. Linux NOT RUN.
- **Recommended fix:** Separate repair task resolves lint/format, then run the canonical Linux software gate and real-data qualification under an authorized bounded plan.
- **Test required:** All required checks green on the exact frozen source/environment; never describe partial success as full readiness.
- **Scientific blocker:** NO; **RunPod blocker:** YES.

## IA-10 — Data evidence and equivalence (HIGH)

- **File / approximate lines:** `PROJECT_CONTEXT.md; src/crypto_ai/phase7/prepared_cache.py:534-680`.
- **Function/class:** `handoff evidence / cache validation`.
- **Problem:** Configured local Gold/cache/checkpoint roots do not exist in this audit environment. Historical 7/7 Gold and 60 candle checkpoints are documented, not freshly hash-verified here. Production M-01 counts, row attrition and cached/uncached equivalence remain unknown.
- **Impact / bias / likelihood:** Cannot certify the actual training population or RAM/disk needs. UNKNOWN likelihood of data defect; lack of evidence is not evidence of corruption.
- **How to reproduce:** RuntimePaths.resolve shows missing Gold and local_artifacts roots; no data acquired or VM started.
- **Evidence:** CODE-VERIFIED path inventory; historical claims expressly not relabeled DATA-VERIFIED.
- **Recommended fix:** After separate authority permits access, validate existing manifests/hashes before any recomputation. Reuse valid data and Gold; obtain exact fold/horizon census and equivalence evidence.
- **Test required:** Row-key/feature-order/dtype/value/mask/prediction/report equivalence on approved research rows; July and August excluded.
- **Scientific blocker:** YES; **RunPod blocker:** YES.

## IA-11 — Runtime admission coverage (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/pipeline.py:780-950; src/crypto_ai/phase7/training.py:1370-1440; scripts/run_phase7a_pipeline.py:716-722`.
- **Function/class:** `run_phase7_cloud / run_phase7_training`.
- **Problem:** The Phase7A script and benchmark dispatcher require read-only cache and an explicit RAM floor. Generic phase7-research -> run_phase7_cloud -> run_phase7_training does not enforce require_training_runtime_contract at that shared boundary. Its weaker total-RAM guard and cloud environment flag can permit preparation during training.
- **Impact / bias / likelihood:** Operator can choose a legitimate alternate CLI and bypass newer cost/resource safeguards. MEDIUM conditional likelihood; no bypass was executed.
- **How to reproduce:** Statically trace cli.py:979-991 and compare the callers found by rg require_training_runtime_contract. PHASE7_ALLOW_CLOUD_RESEARCH is an environment guard, not provider verification.
- **Evidence:** CODE-VERIFIED call graph.
- **Recommended fix:** Centralize cheap training admission in the common entrypoint while preserving a distinct explicit preparation mode and fixture-test interfaces.
- **Test required:** Every public training CLI must reject missing RAM floor/writable-cache mode before Gold scan or fit; plan modes remain side-effect free.
- **Scientific blocker:** NO; **RunPod blocker:** YES.

## IA-12 — GPU qualification enforcement (HIGH)

- **File / approximate lines:** `src/crypto_ai/phase7/gpu_qualification.py:49-116; src/crypto_ai/phase7/models.py:142-199; src/crypto_ai/phase7/backend.py:25-37`.
- **Function/class:** `qualify_gpu / _fit / resolve_lightgbm_backend`.
- **Problem:** Qualification ladder exists but is not called by the ordinary fit path. Setting PHASE7_LGBM_DEVICE=gpu|cuda chooses that backend without requiring the ladder's APPROVED evidence. CPU/GPU equivalence is not established merely by the ladder implementation.
- **Impact / bias / likelihood:** Unqualified numerical/policy changes can enter a nominally comparable experiment. MEDIUM if operator chooses GPU; no effect on a forced-CPU smoke.
- **How to reproduce:** rg qualify_gpu / gpu_training_authorized in training/launch code; backend resolution accepts the environment value directly.
- **Evidence:** CODE-VERIFIED; no GPU probe executed.
- **Recommended fix:** Pin CPU for the first scientific smoke. Later enforce evidence-bound GPU admission and policy equivalence with precommitted tolerances.
- **Test required:** Unapproved GPU/CUDA selection must fail before any real fit; numerical near-threshold changes must be assessed at policy level.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-13 — Cal-A internal validation (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase5/calibration.py:100-133`.
- **Function/class:** `fit_calibrator`.
- **Problem:** Last 25% holdout is a row-count slice, with no timestamps, symbol grouping or label-end purge. The cut can divide a timestamp's cross-section and adjacent target windows overlap. The chosen method is correctly refit on all Cal-A, but heldout_mae is not a fully isolated chronological score.
- **Impact / bias / likelihood:** Optimism in choosing identity vs linear; it does not expose Cal-B or TEST. HIGH occurrence of nearby overlapping labels, effect size UNKNOWN.
- **How to reproduce:** Inspect raw[:fit_count] / raw[fit_count:] and function arguments (no label times).
- **Evidence:** CODE-VERIFIED. The earlier report's blanket “independent held-out selection” is too strong.
- **Recommended fix:** If this selection is retained, split by unique timestamp and purge actual endpoints; report full-Cal-A reliability as in-sample diagnostics. Keep candidate family small.
- **Test required:** No shared timestamps or label windows across internal fit/selection; constant predictions and minimum sizes fail safely.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-14 — H0 validation reuse (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/models.py:526-619; src/crypto_ai/phase7/training.py:1070-1085`.
- **Function/class:** `fit_architecture / _run_one`.
- **Problem:** H0 estimates residual offsets on Validation, already used for selecting global tree iteration. Validation is therefore used to fit H0 parameters as well as select stopping. Baseline scores on that set flatter H0 relative to G0.
- **Impact / bias / likelihood:** Architecture ranking bias within development; no direct TEST leakage. Deterministic reuse whenever H0 enabled.
- **How to reproduce:** Trace hybrid_calibration=validation and mean residual corrections.
- **Evidence:** CODE-VERIFIED; metadata openly documents the dependence.
- **Recommended fix:** Exclude H0 validation superiority from confirmation. Later dedicate a pre-TEST correction slice or nested fit, with separate experiment identity.
- **Test required:** Correction fitting cannot consume its independently scored slice; preserve G0 reuse equivalence and fallback rules.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-15 — Threshold selection (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/economics.py:120-196`.
- **Function/class:** `select_cal_b_thresholds`.
- **Problem:** All five thresholds may have negative Cal-B expectancy, yet the least negative eligible candidate is selected. A no-trade candidate with zero expectancy is not compared; the only no-threshold rule is insufficient trades. Thirty trades and per-coin selection do not establish reliable positive expected return.
- **Impact / bias / likelihood:** Policy may trade known-negative development estimates; Cal-B threshold variance can generate apparently good TEST luck. MEDIUM likelihood, actual frequencies unknown.
- **How to reproduce:** Construct >=30 non-overlapping rows with large positive predictions and negative actual returns; each eligible threshold has negative expectancy, winner remains non-null.
- **Evidence:** CODE-VERIFIED winner logic; DATA-VERIFIED synthetic reproduction: all five candidate expectancies −0.0111, 30 eligible trades, selected global threshold 10bps. Not a real-data claim.
- **Recommended fix:** Before economic qualification, preregister a no-trade comparator and uncertainty/shrinkage rule. Do not tune a new rule against already viewed TEST.
- **Test required:** All-negative candidates choose no trade under the new version; tie-breaking and cost-stressed trade IDs remain deterministic.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-16 — Baselines and objective fairness (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:200-309; src/crypto_ai/phase7/models.py:414-419`.
- **Function/class:** `_ridge_predict / score_baselines / fit_architecture`.
- **Problem:** Ridge uses a strided TRAIN sample capped at 500k and unweighted loss; primary G0 uses all finite TRAIN rows and symbol-balanced weights. Both score identical covered Validation rows, but it is not an equally weighted/equally sampled training comparison. Baselines are not independently scored on TEST.
- **Impact / bias / likelihood:** An advantage can reflect different estimands or sample size; coverage differences remain across architectures. HIGH occurrence by design, magnitude unknown.
- **How to reproduce:** Read row stride, Ridge Gram matrix and G0 symbol_balanced_weights. Compare full-data versus capped training controls in later research.
- **Evidence:** CODE-VERIFIED; Ridge is already implemented, so do not recommend adding it as missing.
- **Recommended fix:** Add train-mean/recent-return/market/rank controls; align training objective or disclose difference. Fit all controls on TRAIN and score registered identical TEST keys after freeze.
- **Test required:** Baseline row-key equivalence; symbol-ID variant gets an explicitly matched identity baseline if compared; weights never depend on labels.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-17 — Normalized target inverse (LOW)

- **File / approximate lines:** `src/crypto_ai/phase7/targets.py:284-294; src/crypto_ai/phase7/training.py:653-666`.
- **Function/class:** `generate_multiasset_targets / _to_raw_predictions`.
- **Problem:** Normalized labels divide by max(abs(scale),1e-8), but reconversion multiplies the original stored scale, not that effective denominator. Zero/subfloor scales do not round-trip.
- **Impact / bias / likelihood:** Normalized-target economics can be suppressed near a tiny volatility scale. LOW practical exposure for finite A6 because other normalized feature denominators often reject zero vol; subfloor incidence unknown. Raw smoke unaffected.
- **How to reproduce:** probes.json normalization_inverse: raw .001 -> reconstructed 0, .00001, .001 for scales 0,1e-10,.01.
- **Evidence:** DATA-VERIFIED tiny deterministic computation.
- **Recommended fix:** Use the identical effective scale both ways in a separately versioned correction; first count real eligible subfloor rows.
- **Test required:** Zero/subfloor/exact-floor/ordinary/nonfinite scale inverse tests and unchanged raw-target behavior.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-18 — Diagnostic units (LOW)

- **File / approximate lines:** `src/crypto_ai/phase7/training_metrics.py:62-85`.
- **Function/class:** `display_metrics`.
- **Problem:** fixed_threshold_bps is applied directly to LightGBM target-unit arrays. For volatility_normalized specifications these values are not raw returns, so a “5 bps” event is incorrectly labeled. Undefined P/R is shown as 0 because LightGBM requires a number.
- **Impact / bias / likelihood:** Misleading live comparisons across target types; default L2 stopping remains first_metric_only, so this does not change current fitting selection.
- **How to reproduce:** Check display_metrics receives target arrays without ex-ante scales and calls fixed_threshold_precision_recall unchanged.
- **Evidence:** CODE-VERIFIED.
- **Recommended fix:** Label target-unit diagnostics explicitly or convert using aligned feature-time scales; distinguish undefined from zero in JSON reporting.
- **Test required:** Equivalent raw moves under varying scales must yield identical raw-bps events; no extra prediction pass per iteration.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-19 — Resource bound (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/resource_estimate.py:23-60`.
- **Function/class:** `estimate_spec_resources`.
- **Problem:** total_gold_rows // horizon_count is an average, not a mathematical upper bound: horizon validity differs. Fixed copy multipliers omit row-object overhead, sorting/index temporaries, LightGBM bins/histograms and duplicate Arrow/NumPy/cache buffers. A pass is not a necessary/sufficient proof of fit capacity.
- **Impact / bias / likelihood:** Can understate an unequal-horizon table and overstate Fold-1 need while missing true peak. HIGH likelihood of estimate imprecision; operational effect unknown without profiling.
- **How to reproduce:** With total rows 7 over four horizons the claimed bound is 1, yet one horizon could have 4. Production shortest horizon is expected to have at least average coverage, not at most.
- **Evidence:** CODE-VERIFIED formula; INFERENCE about unprofiled peaks.
- **Recommended fix:** Rename as heuristic and derive per-horizon/segment counts from verified manifests or footer scans; profile one preparation stage with cgroup-aware resource limits.
- **Test required:** Unbalanced horizon counts, one-row cases and measured RSS/disk high-water marks; no RESOURCES_OK claim from an unproven bound.
- **Scientific blocker:** NO; **RunPod blocker:** YES.

## IA-20 — Crash recovery of result table (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/hardening.py:536-549; src/crypto_ai/phase7/training.py:1352-1367,1813-1920`.
- **Function/class:** `append_result_row / _run_one / resume branches`.
- **Problem:** CSV append is not the atomic report/checkpoint transaction. Crash after report publication but before append allows orphan recovery/checkpoint completion without reconstructing that row; partial append/header mismatch is not validated. Analytical helpers accept arbitrary CSV contents.
- **Impact / bias / likelihood:** Missing or duplicated rows can distort the trial inventory and downstream success. MEDIUM interruption likelihood; authoritative JSON reports can recover truth if used.
- **How to reproduce:** Inspect atomic_json(report) before append_result_row and orphan recovery continue paths. Do not inject crashes into real artifacts.
- **Evidence:** CODE-VERIFIED crash-window analysis; no production corruption alleged.
- **Recommended fix:** Treat CSV as a rebuildable view of validated reports, with unique keys and schema/version checks; preserve an independent trial ledger.
- **Test required:** Crash before/during/after append, then deterministic table regeneration must equal uninterrupted output.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## IA-21 — Artifact trust (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/model_registry.py:72-87; src/crypto_ai/phase7/models.py:643-651`.
- **Function/class:** `verify_registered_model / load_model`.
- **Problem:** Unregistered joblib artifacts load by default unless PHASE7_REQUIRE_MODEL_REGISTRY=1. Registry is local mutable state keyed by resolved absolute path, so moving an artifact to /workspace loses that path anchor.
- **Impact / bias / likelihood:** Untrusted artifact deserialization risk and weaker portable trust. MEDIUM conditional probability when importing unknown models; no pretrained model was loaded in this audit.
- **How to reproduce:** Inspect UNREGISTERED return and subsequent joblib.load; a copied model has a different registry record key.
- **Evidence:** CODE-VERIFIED; trusted-source persistence caveat documented by scikit-learn.
- **Recommended fix:** Use strict verification for external artifacts and explicit portable provenance/receipt migration. Hashes prove matching bytes, not safe contents or correct science.
- **Test required:** Unknown/tampered/copied model behavior and registry absence must be explicit before deserialization.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-22 — Feature semantics and redundancy (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/features.py:836-851,878-898; src/crypto_ai/phase6/features.py:199-204; src/crypto_ai/phase7/pipeline.py:483-499`.
- **Function/class:** `generate_multiasset_features / _higher_timeframe_values / _gold_chunk`.
- **Problem:** listing_age_days and history_length_days are identical; daily distance_from_60d_high and drawdown_from_60d_high are identical. Pair statistics use consecutive observed row positions and are not reset per gap. Daily EMA200 is reseeded in each annual chunk with only 220 days' history, not continuous state.
- **Impact / bias / likelihood:** Redundancy and chunk/gap-dependent meaning complicate feature interpretation; not future leakage. Deterministic by design, real prediction effect unknown.
- **How to reproduce:** Compare formulas directly; later compare a synthetic full-history EMA with chunked seeded EMA around a year boundary.
- **Evidence:** CODE-VERIFIED formulas and chunk halo; INFERENCE on materiality.
- **Recommended fix:** Document exact definitions now; preserve immutable Gold. Later measure chunk equivalence and prune only within a new versioned ablation.
- **Test required:** Prefix invariance, gap reset and full-versus-chunked state comparison for recursive features.
- **Scientific blocker:** NO; **RunPod blocker:** NO.

## IA-23 — RunPod operations (HIGH)

- **File / approximate lines:** `scripts/phase7a_control_plane_watchdog.ps1; scripts/phase7a_vm_supervisor.py; src/crypto_ai/phase7/run_lease.py:50-72`.
- **Function/class:** `watchdog / owner_liveness`.
- **Problem:** Portable paths do not supply a verified RunPod budget/deadline/shutdown controller. Existing cloud control-plane scripts were designed for GCE. A network-volume lock from a foreign host deliberately cannot be assumed dead; mount/rename/fsync semantics are unqualified.
- **Impact / bias / likelihood:** Unbounded billing, stale lock blockage or lost artifacts on termination. MEDIUM conditional likelihood on migration; no RunPod was created or contacted via account.
- **How to reproduce:** Inspect supervisor provider commands and foreign-host fail-closed liveness. RunPod official storage docs distinguish volume lifetimes.
- **Evidence:** CODE-VERIFIED local design; external provider semantics verified in official docs. Actual provider state UNKNOWN.
- **Recommended fix:** Before a paid migration, qualify selected container/mounts, strict CPU baseline, verified immutable transfer, provider-specific independent deadline termination and off-pod evidence backup.
- **Test required:** Provider shutdown dry run under later authority, crash/restart on chosen filesystem, resource limits visible inside container and hash-preserving transfer.
- **Scientific blocker:** NO; **RunPod blocker:** YES.

## IA-24 — Universe evidence (MEDIUM)

- **File / approximate lines:** `src/crypto_ai/phase7/universe.py:240-332,386-489,565-709; src/crypto_ai/phase7/registry.py`.
- **Function/class:** `select_core_universe / select_fold_active_universe`.
- **Problem:** The earlier LH-07 claims a today-survivor universe; source contradicts that. Selection uses cutoff-known historical/current registry evidence and retains delisted candidates. However archive availability itself is not a full census of every historically tradable failed instrument, and actual selection manifests were not locally verified.
- **Impact / bias / likelihood:** Residual representativeness and archive-selection bias cannot be quantitatively excluded. UNKNOWN magnitude; do not assume HNT retention proves completeness.
- **How to reproduce:** Read causal descriptor filtering and cutoff selection, historical registry union, and handoff Core20 list. No returns enter deterministic stratified ranking.
- **Evidence:** CODE-VERIFIED algorithm; actual universe hash f71cdf65d161466037b34420 remains historical evidence only.
- **Recommended fix:** Validate historical candidate/exclusion manifests and lifecycle evidence at the frozen cutoff. Keep HNT and do not force XPIN or change membership retroactively.
- **Test required:** Future listing/delisting/liquidity changes cannot alter past membership; quantify excluded assets without selecting on future performance.
- **Scientific blocker:** YES; **RunPod blocker:** NO.

## Disposition of older claims

- LH-04's provisional bounded acceptance is **superseded** by IA-05: real incidence is unknown;
  bounded time distance is not bounded economic materiality.
- LH-07's claimed present-survivor construction is **not substantiated and contradicted by source**;
  replace with IA-24's narrower unverified historical-completeness limitation.
- LH-11's blanket “no context-change cache test” is too strong: source identity and causality tests
  exist. The concrete omission is IA-04's unbound hardening module/config, not all feature code.
- LH-16's report-only mitigation is **insufficient**; compatibility enforcement is required.
- Test release is logged, but is not strictly once-only: identical consumer/identity re-release is
  allowed and logged. `_test` is also physically held in memory/cache; the API is an ownership
  convention and audit ledger, not an adversarial security boundary.
- A 0/48 incomplete historical Fold 1 is not a failed model and is never counted as bad performance.
