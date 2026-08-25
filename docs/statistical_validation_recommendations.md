# Statistical validation recommendations

These are future research gates, not changes to the frozen Phase 7 baseline.

## Required before a champion claim

1. Freeze a hypothesis family before reading aggregate TEST economics: model
   family, target, horizon, feature set, universe view, and cost tier.
2. Report fold distributions and dependence-aware intervals, not only pooled
   metrics. Use a stationary or moving-block bootstrap with block length chosen
   from return/signal autocorrelation and rerun sensitivity across plausible
   lengths.
3. Use White's Reality Check or Hansen's SPA within each declared family.
   Report the number of tried configurations, abandoned trials, and the full
   candidate set supplied to the test.
4. Report Deflated Sharpe Ratio and Probability of Backtest Overfitting as
   diagnostics. Neither converts a flawed execution model into valid evidence.
5. Use Diebold-Mariano tests for paired forecast-loss comparisons, with a
   horizon-consistent HAC variance estimate. For cross-sectional forecasts,
   also report timestamp-level IC distributions and symbol-clustered intervals.
6. Keep TEST out of calibration, thresholding, estimator eligibility, cluster
   fitting and feature choice. Cal-A fits calibration; Cal-B selects frozen
   policy thresholds. Any post-TEST change starts a new research generation.
7. Report selection-adjusted results both gross and at all frozen cost tiers,
   plus turnover, capacity proxy, concentration, funding sensitivity and
   latency stress. No-trade is a valid outcome.

## Drift and prospective monitoring

- Monitor input missingness, PSI/KS or energy-distance shifts, prediction
  distribution, calibration error, coverage, IC, turnover and realized cost.
- Separate alerts from actions. Drift detection may quarantine or request
  review; it must not autonomously promote a challenger.
- Run champion and challenger on identical shadow inputs. Promotion requires a
  predeclared observation minimum, paired statistics, cost/reconciliation
  health, and human approval. Rollback must be immediate and versioned.
- Keep August 2026 untouched until a separately authorized prospective
  evaluation protocol exists. Prospective evaluation is one-shot; it is not a
  new tuning segment.

## Model-family recommendation

LightGBM remains the Phase 7 baseline: it is efficient, handles nonlinear tabular
interactions, and already has controlled fold/model identities. Target v2 now
provides the required post-signal timing; XGBoost and CatBoost may be registered
as matched Phase 8 tabular challengers only after the initial LightGBM baseline
and trial family are frozen. The Phase 8 sequence candidate should be a small
causal TCN first, then a compact PatchTST challenger. TFT is justified only if
static covariates and multi-horizon probabilistic outputs materially help;
iTransformer is exploratory. LSTM/GRU are reference baselines, not presumed
upgrades.

RL is not recommended as the primary return forecaster. A later use may be
execution scheduling, inventory/risk budgeting or sizing inside hard risk
limits, trained in a calibrated simulator and shadowed before any authority.
