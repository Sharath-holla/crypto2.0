> **Independent audit update:** Earlier scores below are preserved from concurrent commit
> `c249e28`. The independent scorecard appended below replaces them as this audit's conclusion.
> Ratings are judgments about the inspected design, not measurements of profitable performance.

# Crypto 2.0: architecture scorecard (2026-11-06)

Scores are my OPINION after reading the code paths listed in the audit, 0-10. "Not verified" means
I did not read enough to score with confidence; those carry a ? and a lower bound.

| Subsystem | Score | Basis |
| --- | --- | --- |
| Data acquisition | 6? | Binance archive, gap-aware; Silver completeness on the Mac unknown |
| Data lineage | 8 | manifests, 138/138 Gold hashes verified (DATA-VERIFIED), registry/universe hashes |
| Bronze / Silver / Gold | 7 / 6? / 8 | Gold verified; Silver not hash-checked |
| Feature engineering | 6? | 109 features, causal HTF; formulas not all re-derived |
| HTF feature timing | 7 | completed-bar design + coverage contract tests exist; not re-proven by a fresh synthetic test this round |
| Cross-sectional context | 7 | label-independent fold context v4; M-01 edge unmeasured |
| Target construction | 8 | timing CODE-VERIFIED; raw target is the plain choice |
| Universe design | 5? | Core20 fixed at 2022; survivorship exposure not quantified |
| Split / purge / embargo / folds | 8 | label-end purge, 120-min embargo, 16 rolling folds |
| Leakage protection | 8 | strong guards; residual M-01 and L-04 |
| LightGBM model choice | 7 | sensible primary family |
| Model configuration / hyperparameter strategy | 5 / 3 | single frozen config, no sensitivity plan |
| Calibration | 7 | Cal-A only, held-out selection |
| Threshold selection | 6 | Cal-B only, non-overlap, but max-expectancy over a 5-point grid is itself a mild selection |
| Baselines | 6 | zero + Ridge on identical rows now; no rank/market baselines |
| Regression metrics | 8 | zero-actual handled; IC present |
| Trading metrics | 6 | now wired; per-trade Sharpe only |
| Cost / slippage | 5 | flat tier bps; no volatility/size dependence |
| Funding | 1 | not modelled |
| Execution assumptions | 6 | one-bar delay; open-price fills |
| Multiple-testing control | 4 | Bonferroni on validation skill only; no DSR/PBO/SPA |
| Model selection | 6 | non-Test ranking possible; success numbers still placeholders |
| Holdout design | 9 | locked constants, no code path found |
| Cache identity | 8 | source/config/environment bound; no context-change test |
| Reproducibility | 7 | deterministic CPU, one seed |
| Experiment tracking | 6 | custom JSON + CSV; adequate without SaaS |
| Artifact integrity | 7 | external hash anchor (local trust) |
| Concurrency / crash recovery | 8 | lease, atomic markers, recovery tools |
| RunPod portability | 6 | launchers fixed; Linux gate unrun |
| Monitoring | 7 | readable line + JSONL |
| Results reporting | 7 | CSV + reports |
| Scientific documentation | 7 | extensive, some stale |
| Production safety | 7 | legacy order code isolated by headers + test |

| Aggregate | Score |
| --- | --- |
| OVERALL SCIENTIFIC | 6.5 / 10 |
| ENGINEERING | 8 / 10 |
| STATISTICAL RIGOR | 5 / 10 |
| TRADING REALISM | 5 / 10 |
| REPRODUCIBILITY | 7.5 / 10 |
| RUNPOD READINESS | 6 / 10 (gates unrun) |


---

# Independent architecture scorecard — 6 November 2026

**OPINION/RECOMMENDATION.** 0=unusable/absent for the intended purpose; 5=useful with material
limits; 8=strong tested design; 10=exceptional evidence including relevant production-scale
validation. Scores are not probabilities and are not a mechanical average of test counts. The
scores explicitly discount absent actual-data qualification. Source facts are detailed in the
training companion and IA register; references are in the literature companion.

| Subsystem | /10 | Reason | Confidence |
| --- | ---: | --- | --- |
| Data acquisition | 7 | Archive/REST reconciliation and restart contracts; actual source bytes not revalidated | Medium |
| Data lineage | 8 | Exact decimal/source boundaries, manifests/checksums; missing live manifest evidence | Medium |
| Bronze | 8 | Immutable intent and schema; no concurrent raw-writer qualification proved | Medium |
| Silver | 7 | Quality/lifecycle/gap rules strong; configured local source evidence absent | Medium |
| Gold | 6 | Immutable schemas/hashes; label inner join prevents unconditional feature completeness | Medium |
| Feature engineering | 7 | 109 explicit formulas, causal transforms; some duplicates/chunk seed issues | High source / low empirical |
| HTF feature timing | 8 | Completed direct candles, per-family as-of expiry and passing synthetic tests | High source |
| Cross-sectional context | 6 | Fold-local union/witness, horizon invariance; M-01 real census outstanding | High mechanism / unknown incidence |
| Target construction | 8 | All horizons manually reconstructed; normalized inverse edge defect | High synthetic |
| Universe design | 8 | Historical PIT selection and HNT retention; archive census completeness unverified | Medium |
| Split design | 8 | Chronological, half-open UTC and label-end purge | High |
| Purging | 9 | Actual endpoint strictness, separate latency; tested | High |
| Embargo | 8 | 120m boundary gap clear; not equivalent to two-sided CPCV embargo | High |
| Fold architecture | 8 | 16 nonoverlapping TEST windows, regime breadth; role reuse matters for selector | High |
| Leakage protection | 7 | Strong ownership guards; M-01 and future-fold model-selection loopholes | Medium |
| LightGBM model choice | 8 | Practical tabular baseline plus Ridge; no demonstrated edge | Judgment |
| Model configuration | 7 | Finite float64, active bagging, CPU deterministic baseline | High source |
| Hyperparameter strategy | 5 | Frozen single configuration; cap/seed/leaf sensitivity not evidenced | Judgment |
| Calibration | 6 | Small identity/affine family; internal split lacks timestamp grouping/purge | High source |
| Threshold selection | 5 | Cal-B isolation/non-overlap strong; no all-negative/no-trade comparator or uncertainty | High source |
| Baselines | 5 | Zero/Ridge same Validation scoring rows; unequal fit budget/weighting and no TEST controls | High source |
| Regression metrics | 8 | Finite/constant/ties/zero handling; no sampling uncertainty | High |
| Trading metrics | 4 | Useful trade diagnostics, no capital-normalized time return process | High source |
| Cost modeling | 4 | Explicit 11/14/20bps stress scenarios, current fee not verified | High source / unknown reality |
| Slippage | 3 | Flat tier penalty, no size/volatility or executable quote evidence | High source |
| Funding | 1 | Explicitly NOT_MODELLED in trade cash flow | High |
| Execution assumptions | 4 | Causal delayed entry; open fill/no partials/capacity not qualified | High source |
| Multiple-testing control | 3 | Bonferroni helper uses selected validation scores; duplicates accepted | High synthetic |
| Model selection | 3 | No complete champion gate; all-fold Validation rank cannot confirm earlier TEST | High source |
| Holdout design | 9 | Strict July buffer/August flags and range guards; no holdout inspected | High source / external state unverified |
| Cache identity | 6 | Broad data/source/platform binding; hardening module/settings omitted from fitted-run identity | High source |
| Reproducibility | 6 | CPU/source/environment records strong; exact build/cgroup/real equivalence unknown | Medium |
| Experiment tracking | 6 | Custom immutable JSON useful; trial ledger/CSV recovery incomplete | High source |
| Artifact integrity | 7 | Hashes, receipts, atomic core writes; unregistered pickle load permissive | High source |
| Concurrency safety | 7 | Exclusive lease plus advisory lock; network filesystem not qualified | Medium |
| Crash recovery | 7 | Atomic cache markers and recovery receipts; CSV transaction gap | Medium |
| RunPod portability | 5 | Paths/launchers portable; provider deadline/storage/CPU gate not proven | Medium |
| Monitoring | 7 | Train/Val progress, resource snapshots; sampled RSS not continuous peak proof | High source |
| Results reporting | 5 | Detailed JSON; CSV dedup/status gaps can falsely qualify | High synthetic |
| Scientific documentation | 6 | Extensive handoff, stale absolute claims and conflicting concurrent audit | High |
| Production safety | 8 | Installable research isolated, disabled execution and passing import tests | High source |

## Aggregate ratings

| Requested aggregate | /10 | Interpretation |
| --- | ---: | --- |
| OVERALL SCIENTIFIC SCORE | **6.5** | Coherent causal research framework with unresolved inference/population gates. |
| ENGINEERING SCORE | **7.5** | Strong source/checkpoint contracts; Linux/actual-scale validation and peripheral transactions remain incomplete. |
| STATISTICAL RIGOR SCORE | **4.0** | Local chronological isolation is good; discovery inference and selection accounting are inadequate. |
| TRADING REALISM SCORE | **3.5** | Explicit research costs but no funding, capacity or portfolio return path. |
| REPRODUCIBILITY SCORE | **6.5** | Broad hashes and deterministic CPU; omitted control semantics and real equivalence gate matter. |
| RUNPOD READINESS SCORE | **4.5** | Transportable source is not a verified paid-run operational system. |

**Architecture:** GOOD_BUT_NEEDS_HARDENING. **Training/evaluation:**
TRAINING_CODE_HAS_MATERIAL_RISKS. **Final status:** GO_AFTER_FIXING_SPECIFIC_BLOCKERS.
This is conditional support for exactly one registered raw G0 smoke, not owner authorization,
a full-grid recommendation, a model-quality assessment or a holdout release. No quantitative
probability of genuine edge can be derived from these scores.
