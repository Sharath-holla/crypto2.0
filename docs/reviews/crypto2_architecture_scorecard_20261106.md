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
