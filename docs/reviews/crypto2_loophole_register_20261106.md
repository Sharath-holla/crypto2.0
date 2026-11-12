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
