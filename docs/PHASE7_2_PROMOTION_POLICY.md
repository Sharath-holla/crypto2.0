# Phase 7.2 challenger promotion policy v1

This policy is declared before the first Phase 7 cloud result is viewed. It
does not define one arbitrary profitability threshold and does not authorize
holdout evaluation.

A challenger may replace a baseline only when all of the following are true:

1. Inputs, timestamps, folds, universe, targets, calibration ownership and
   costs are matched or differences are the explicit registered hypothesis.
2. The primary OOS metric improves by a practically meaningful amount with a
   dependence-aware confidence interval that excludes the accepted equivalence
   region.
3. Improvement is broad across forward folds and multiple eligible symbols,
   not concentrated in one asset, month, regime or extreme event.
4. Net economics survive declared normal and stressed costs with adequate
   opportunity count and without unacceptable turnover/concentration.
5. Calibration, missing-data behavior, young/unseen-symbol behavior and data
   degradation do not materially worsen.
6. Leakage, trial count and researcher degrees of freedom are disclosed; TEST
   and the prospective holdout did not select the challenger.
7. Added compute, storage, latency, state and operational complexity are
   justified by the gain. The simpler model wins when practically equivalent.

Family-specific gates:

- CatBoost/XGBoost: same `ModelComparisonKey` intersection as LightGBM.
- Micro 1m: BTC/ETH pilot first; same 5m rows and targets; reject expansion if
  incremental matched OOS value is absent.
- Ranking: improve rank/top-k value without unacceptable turnover or loss of
  calibrated absolute forecasts.
- Competing risks: improve coherent Brier/log-loss/time-to-event quality versus
  independent and multinomial controls before any economic claim.
- Neural/ensemble: each component qualifies alone; stacker inputs are OOF and
  the combiner is shallow/constrained first.

The locked August holdout may be opened only under a future explicit evaluation
authorization after the full research plan and candidate are frozen.
