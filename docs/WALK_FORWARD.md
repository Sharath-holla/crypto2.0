# Phase 5 Walk-Forward Validation

Phase 5 is a retrospective, public-data research gate. It asks whether the
fixed Phase 4.1 BTC models show stable, repeatable behavior across many unseen
calendar periods. It does not authorize leverage, account access, order
submission, paper trading, shadow trading, or live deployment.

## Untouched prospective holdout

The prospective holdout begins at `2026-08-01T00:00:00Z`. Development code,
fold planning, fitting, calibration, threshold selection, test evaluation, and
reports reject or exclude every row with `feature_time` at or beyond that
boundary. Phase 5 results must be called **RETROSPECTIVE WALK-FORWARD OOS**.
They are not the sacred final holdout result. The holdout may be opened only by
a later explicit instruction after the full research policy is frozen.

## Frozen candidates

| Family | Candidate | Frozen ordered features | Purpose |
| --- | --- | ---: | --- |
| Core long history | L0 | 13 | Phase 3 baseline champion candidate |
| Core long history | L5 | 46 | Full causal core challenger |
| Derivatives overlap | D0 | 46 | Matched-range core control |
| Derivatives overlap | D2 | 55 | Funding plus mark/index/basis challenger |

L0 and L5 share every test timestamp in the primary run. D0 and D2 share every
test timestamp in the derivatives run. Cross-family results use different
historical coverage and are not treated as a direct feature-value comparison.
Each exact ordered schema and SHA-256 are frozen in the run plan and fold
manifests. The LightGBM parameters remain the single conservative Phase 4.1
configuration; there is no hyperparameter search.

## Calendar fold geometry

The primary schedule is rolling and timestamp-native:

```text
TRAIN 24 months -> VALIDATION 3 months -> CALIBRATION 3 months -> TEST 3 months
                                                               step = 3 months
```

Every range is half-open and UTC. Validation alone controls LightGBM early
stopping. Calibration alone chooses the calibration method and policy
threshold. Test is released only after a model/calibrator/policy identity is
frozen and is then used for evaluation only. Test periods cannot overlap.

At each Train -> Validation, Validation -> Calibration, and Calibration -> Test
boundary, the earlier segment drops every row satisfying
`label_end_time >= next_segment_start`. A separate 60-minute embargo removes
the leading feature rows of Validation, Calibration, and Test. Each fold
manifest records rows before purging, rows purged, rows embargoed, and rows
remaining for all four segments.

## Calibration and threshold policy

The preregistered calibration candidates are identity and linear
`intercept + slope * raw_prediction`. Both are fitted and compared on the
calibration segment only. Invalid linear fits are rejected. Artifacts record
the selected slope/intercept, sample count, candidate MAE, prediction
distributions, and before/after reliability curves.

The calibration-only threshold grid is 2, 4, 6, 8, and 10 bps above expected
non-funding costs. Its deterministic objective combines expectancy, a drawdown
penalty, and a configured low-trade penalty. A threshold is eligible only with
at least 30 non-overlapping calibration trades. If none qualifies, the frozen
policy is `NO_TRADE`; test thresholds are never relaxed to manufacture trades.

## Execution and costs

The Phase 4.1 assumptions remain frozen: 4 bps taker fee per side, 1 bp
round-trip spread, and 1 bp slippage per side, for an 11 bps non-funding base
hurdle. Actual funding events in `(entry_time, exit_time]` are applied.

Where the validated 1-minute Silver data provides both observations without a
gap, execution uses the first 1-minute open after feature availability plus the
configured one-minute latency and an exit 60 minutes later. Other periods use
the canonical Label V1 next-5-minute-open references. Every trade is tagged
`1m` or `5m`. The completed prediction candle close is never used as an
execution price. Positions are normalized, unleveraged, and non-overlapping.

Each frozen test policy is evaluated at 0x, 1x, 1.25x, 1.5x, and 2x
non-funding costs. Zero cost is diagnostic only. No scenario retunes the test
threshold.

## Outputs and resume behavior

Each deterministic run is stored under:

```text
local_artifacts/phase5/walkforward/<run-id>/
    walkforward_summary.json
    fold_metrics.parquet
    oos_predictions.parquet
    oos_trades.parquet
    threshold_history.parquet
    candidates/<candidate>/folds/<fold-id>/
        fold_manifest.json
        model.joblib
        feature_importance.json
        calibrator.json
        threshold.json
        test_predictions.parquet
        test_trades_<cost>x.parquet
        backtest.json
```

Fold directories are immutable and content/checksum validated. `--resume`
skips a valid completed fold and refuses to overwrite an invalid or mismatched
one. The pooled layer rejects duplicate candidate/test `feature_time` rows.

## Diagnostics and qualification

Fold and pooled outputs include MAE, RMSE, R-squared, direction accuracy,
Pearson/Spearman IC, opportunity/trade/no-trade counts, expectancy, gross/net
return, drawdown, hit rate, profit factor, exposure, reliability flags,
calibration and threshold history, moving-block predictive intervals, yearly
results, regimes, taker-flow/funding buckets, long/short behavior, cost stress,
feature PSI/median/IQR drift, prediction stability, and trade/PnL
concentration. A training-only shuffled-label LightGBM negative control runs on
the first fold of each candidate and cannot be selected.

A candidate cannot qualify without enough folds, total trades, reliable folds,
positive median-fold and pooled base expectancy, acceptable drawdown, positive
1.5x-cost expectancy, and absence of single-fold/year/regime PnL dependence.
Low-trade evidence is `INCONCLUSIVE`, not proof of profitability. D2 receives a
separate `VALUE ADDED`, `NO VALUE`, or `INCONCLUSIVE` matched comparison against
D0. The global decision is exactly one of L0/L5/D2 research champion or
`NO QUALIFIED MODEL`.

## Commands

```powershell
uv run crypto-ai walk-forward --config configs/walkforward/btc_primary_v1.toml --plan
uv run crypto-ai walk-forward --config configs/walkforward/btc_primary_v1.toml --resume
uv run crypto-ai walk-forward --config configs/walkforward/btc_derivatives_v1.toml --resume
uv run crypto-ai walk-forward-report --summary <walkforward_summary.json>
uv run crypto-ai compare-candidates `
  --primary-summary <primary-walkforward-summary.json> `
  --derivatives-summary <derivatives-walkforward-summary.json> `
  --output local_artifacts/phase5/walkforward/candidate_comparison.json
```

## Completed result

The primary run contains 17 folds; the derivatives run contains 16. L0, L5,
D0, and D2 all have negative base-cost expectancy and fail the configured
qualification gates. D2's matched value-added verdict is `INCONCLUSIVE`, and
the global decision is **NO QUALIFIED MODEL**. The prospective holdout was not
used. See `PHASE5_RESULT.md` for the exact measured evidence.

## Phase 5.1 hardening protocol

Historical `walkforward_v1` artifacts remain immutable. Phase 5.1 writes only
new `walkforward_v1_1` results and reuses every frozen v1 model. It predicts
the chronological first and second halves of each unchanged three-month outer
Calibration window from those saved models; it does not fit LightGBM again.

Cal-A fits and chooses only identity or linear calibration. The actual
`label_end_time` purge removes Cal-A labels that reach Cal-B, and a separate
60-minute embargo removes the leading Cal-B rows. After the calibrator is
frozen, Cal-B alone selects the unchanged 2/4/6/8/10 bps threshold grid. TEST
raw predictions are loaded only after the model/calibrator/policy identity is
frozen and are used only for evaluation.

Phase 5.1 separates two cost questions:

- `FIXED_POLICY_COST_STRESS` is primary. The 1x policy trade list is frozen;
  trade ID, entry, exit, and direction must be identical at 1x, 1.25x, 1.5x,
  and 2x. Only fees, assumed spread/slippage, and net PnL change. Qualification
  uses this fixed-policy result.
- `ADAPTIVE_POLICY_COST_STRESS` is secondary. Eligibility may change because
  the policy is assumed to know the stressed costs before acting.

Every economic artifact records `statistically_reliable` and a reason. Raw
profit factor may be retained, but its headline value is `null` and its
display is `INSUFFICIENT_SAMPLE` below the declared trade minimum. Trade
concentration separately reports positive-trade concentration and absolute PnL
contributions, including the largest positive and negative trades.

Qualification is always `PASS` or `FAIL`; scientific interpretation is a
separate `NEGATIVE`, `INCONCLUSIVE`, `WEAK_POSITIVE`, or
`PROMISING_UNVALIDATED` evidence status. Gates are unchanged from v1 and may
not be weakened retrospectively.

```powershell
uv run crypto-ai harden-walk-forward --config configs/walkforward/btc_primary_v1_1.toml --resume
uv run crypto-ai harden-walk-forward --config configs/walkforward/btc_derivatives_v1_1.toml --resume
uv run crypto-ai compare-hardened-candidates `
  --primary-summary <primary-hardened-summary.json> `
  --derivatives-summary <derivatives-hardened-summary.json> `
  --output local_artifacts/phase5_hardening/walkforward_v1_1/candidate_comparison.json
uv run crypto-ai verify-hardened `
  --primary-summary <primary-hardened-summary.json> `
  --derivatives-summary <derivatives-hardened-summary.json> `
  --output local_artifacts/phase5_hardening/walkforward_v1_1/verification_report.json
```
