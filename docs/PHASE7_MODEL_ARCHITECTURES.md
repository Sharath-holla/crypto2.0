# Phase 7 Model Architectures and Evaluation

## Research question

Phase 7 tests whether multi-asset structure generalizes better than isolated
BTC modeling. LightGBM is the primary controlled benchmark. Deep learning,
portfolio allocation, sizing, leverage, TP/SL, and live execution remain out of
scope.

## Architecture benchmark

- G0 Global: one pooled model across eligible symbols. Separate ablations test
  explicit one-hot symbol identity and equal-total-mass symbol weighting. The
  symbol-ID-off form scores eligible newer symbols directly from normalized and
  contextual features. For symbol-ID-on, an unseen symbol receives an all-zero
  vector across the TRAIN-frozen known-symbol levels; it never creates a new
  future-informed category and cannot crash prediction.
- C0 Cluster: one model per TRAIN-only cluster. Standardization and K-means are
  fit using only liquidity, volatility, BTC beta/correlation, funding
  variability, trade intensity, and history known at TRAIN end.
- P0 Per-coin: independent models only for symbols meeting minimum Train,
  Validation, and Calibration sample gates. Ineligible symbols receive an
  explicit `PER_COIN_INELIGIBLE` reason; missing coverage is never hidden.
- H0 Hybrid: a global model with symbol correction when adequately supported,
  otherwise a TRAIN-frozen cluster correction, otherwise the global output.

For a newer symbol, C0 assignment uses only its TRAIN-known descriptor. P0
remains `PER_COIN_INELIGIBLE` until all row gates pass. H0 does not force a
local correction: the symbol must meet local TRAIN and residual-support gates,
then falls back through cluster correction to the global prediction.

The checked-in cluster range is three to five, with four in
`configs/phase7/research_v1.toml`. Clusters and liquidity tiers may change by
fold but cannot change inside a fold.

## Controlled experiment matrix

The resume-safe training stage runs:

- G0/C0/P0/H0 on A6 for 15/30/60/120-minute raw and normalized targets;
- G0 symbol-ID and unbalanced-weight controls on the same rows;
- G0 A0 through A5 incremental feature ablations at 60 minutes; and
- G0 BASE/12h/1d/12h+1d controls at 60 minutes.

Within an experiment, architectures receive the same ordered feature schema
and chronological rows before architecture-specific coverage gates. Coverage
is a mandatory scorecard dimension. A separate matched comparison intersects
identical `(symbol, feature_time)` TEST coverage across G0/C0/P0/H0 and reports
matched macro metrics alongside native coverage, preventing P0 from appearing
superior merely because it covers only mature symbols.

The entire matrix runs as two separately checkpointed views:

- `CORE` for the stable pre-2022 `core_universe_v1`; and
- `EXPANDING` for eligible core symbols plus causal fold-local newer coins.

The report scorecard always includes `research_view`; results are not pooled.

## Walk-forward ownership

The inherited rolling geometry is 24 months Train, 3 Validation, 3
Calibration, and 3 TEST, stepping 3 months. The Calibration window is split
chronologically into Cal-A and Cal-B. Actual `label_end_time` purging and a
120-minute embargo protect every boundary for the longest Phase 7 target.

- Train fits model parameters, symbol balancing, clusters, and liquidity tiers.
- Validation controls LightGBM early stopping and hybrid residual structure.
- Cal-A fits identity/linear prediction calibration.
- Cal-B selects the fixed threshold grid globally, by cluster, or per coin.
- TEST is released only after model, calibrator, and threshold identities are frozen.

The permanent holdout beginning `2026-08-01T00:00:00Z` is never loaded. July
2026 is also unused because the research cutoff is exclusive July 1.

The configured dates derive 16 calendar folds; 16 is not a hard-coded model
success count. Summaries separately record calendar folds, eligible folds by
symbol/architecture/target, completed folds, skipped folds, and skip reasons.

## Predictive evaluation

Every covered TEST segment reports micro metrics, equal-symbol macro metrics,
per-coin metrics, per-cluster metrics, coverage, and timestamp-level
cross-sectional Spearman IC. It also reports 365–729, 730–1459, and 1460+
TRAIN-end age buckets using verified `available_from`. BTC up/down and relative-strength-positive/
negative conditions are diagnostic only. Test results do not retune features,
models, calibrators, thresholds, or costs.

## Economic evaluation

Liquidity tiers are TRAIN-only. Configured high/medium/lower tiers vary spread
and slippage while retaining the declared taker fee. Cal-B may select a global,
cluster, or per-coin edge threshold. Insufficient Cal-B trades produce
`NO_TRADE`.

TEST trades are non-overlapping per symbol and unleveraged. Fixed-policy stress
preserves trade ID, entry, exit, and direction at 1.0x, 1.25x, 1.5x, and 2.0x
costs. A separately labeled adaptive diagnostic lets the frozen policy know the
stressed cost before eligibility, without retuning thresholds. Reports include
asset/time concentration and MFE/MAE by liquidity tier.
This is evidence for later risk research, not a TP/SL or portfolio engine.

All configured tier values are labeled **RESEARCH COST ASSUMPTIONS**, not exact
historical realized spread or slippage.

Training is sequential across fold/experiment tasks and caps LightGBM at the
configured `model_threads`; it does not multiply outer model workers by inner
threads. On some Windows hosts joblib cannot identify physical cores and
reports a harmless logical-core fallback warning during K-means tests. The VM
resource limits remain explicit, so no platform-specific warning suppression
is required.

## Complexity and conclusion

The scorecard records completed folds, macro rank quality, coverage, trades,
and estimator count. More complex architecture is not preferred unless its
out-of-sample evidence justifies its coverage and complexity. Valid conclusions
include global generalization, cluster value, per-coin value, hybrid value, or
no architecture generalizes reliably.

No architecture is approved, qualified, or deployable until the cloud run
finishes and its artifacts are independently verified.
