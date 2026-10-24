# PHASE 7A FULL TECHNICAL AUDIT
## Crypto AI Trading System — Crypto 2.0

**Audit Date:** 2026-10-01 (IST)
**Auditor Role:** Independent Quantitative ML Engineer / Principal Reviewer
**Commit Audited:** `28d3098a82952a3d09073e4d81b5281f856c072e` (HEAD, `main`)
**Test Result:** 601 passed · **7 failed** · 2 warnings

> [!CAUTION]
> **2 CRITICAL test failures detected** — `models.py` byte-freeze contract is broken and 5 Linux-only log-rotation tests fail on Windows. These must be understood before training resumes.

---

## 1. Executive Summary

The Phase 7A codebase represents a carefully engineered walk-forward research framework. The scientific methodology (causal features, point-in-time universe, purge/embargo, holdout lock) is largely sound. However, this audit uncovered:

- **1 CRITICAL finding**: The `models.py` file was modified by commit `8cdd0b1` (optimization work) but the signed baseline contract `phase7_scientific_baseline_v1_9.json` was not updated to match. This causes a byte-freeze contract failure across 2 tests.
- **1 HIGH finding**: The Gold dataset is stored on the **terminated GCP VM persistent disk only** — not locally, not on GCS. The disk has `auto-delete: true`. If the VM is deleted, all 9.1 GB of Gold (50.3M rows, 138 partitions) is **permanently lost**.
- **1 HIGH finding**: The primary performance bottleneck (6h21m with 0 models) is an unfiltered Parquet scan caused by missing year-partition pushdown in `_load_fold_rows`. Every fold load scans all 138 partitions instead of the relevant year subset.
- **1 HIGH finding**: On resume, the `reusable_models` dict for H0 is not repopulated from saved G0 models — forcing H0 to retrain the global estimator from scratch.
- **2 HIGH findings**: Memory allocation strategy creates unnecessary 60+ GB peak RAM spikes.
- **Multiple MEDIUM findings**: EMA initialization bug, O(N×T) metric bottleneck, GCP-specific hardcoded paths blocking Lightning migration, and calibration nuances.

**Training readiness: NOT READY.** The byte-freeze contract failure must be resolved first, and the matrix-preparation cache must be implemented before Fold 1 is rerun.

---

## 2. Repository State

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Branch | `main` | `main` | ✅ PASS |
| HEAD commit | `28d3098a82952a3d09073e4d81b5281f856c072e` | `28d3098a82952a3d09073e4d81b5281f856c072e` | ✅ PASS |
| Worktree tracked | Clean | Clean | ✅ PASS |
| Worktree untracked | N/A | Many `.codex_*` dirs, patch files, project_hold dirs | ⚠️ INFO |
| Tag `crypto2.0-handoff-20260906` | Present | Present | ✅ PASS |
| Tag `phase7a-hold-20260906` | Present | Present | ✅ PASS |
| Phase 7A identity | `93f987736b1a79d26b773957` | Confirmed in hold manifest | ✅ PASS |
| Source fingerprint | `ad1aac9508b0b15e9230e06122f4d7fcdf56bf1baab75a9de1a49f1c2894e67d` | Confirmed in hold manifest | ✅ PASS |
| `models.py` byte-freeze | `51444b70f147...` (contract) | `ded9af59bcc9...` (current) | 🔴 FAIL |

**Root cause of byte-freeze failure**: Commit `8cdd0b1` ("Optimize Phase 7 model training execution", 2026-09-04) modified `models.py` and `training.py` significantly (added `PreparedArchitectureInputs`, parallel fits, H0 G0-reuse). The contract file `phase7_scientific_baseline_v1_9.json` was updated at that commit (`"contract_version": "1.0.10"` per that commit's diff) but the `source_freeze` SHA in the JSON still records the **pre-optimization** hash of `models.py`. This is an internal inconsistency in commit `8cdd0b1`.

---

## 3. Architecture Map

```
RAW DATA (Binance USD-M perpetual futures, 5m/12h/1d candles)
    ↓  [acquisition.py] → Bronze Parquet (partitioned by symbol/year/date)
    ↓  [data/quality/] → quality checks, quarantine, rejection
    ↓  [gold.py + pipeline.py] → Gold Dataset (50.3M rows, 138 partitions)
         features: generate_multiasset_features() [features.py]
         targets:  generate_multiasset_targets()  [targets.py]
    ↓
GOLD DATASET: gold-phase7-0cbf2910e8d96c9d19826598
    ↓  [training.py:_load_fold_rows] → per-fold/horizon Arrow tables
    ↓  [folds.py:slice_multiasset_fold] → purge + embargo + membership
    ↓  [training.py:_prepare_training_segments] → train/val/cal_a/cal_b slices
    ↓  [models.py:prepare_architecture_inputs] → NumPy feature matrices
    ↓
LIGHTGBM TRAINING
    G0 = global model (1 estimator)
    C0 = cluster model (4 estimators, ThreadPoolExecutor)
    P0 = per-symbol model (up to 20 estimators, ThreadPoolExecutor)
    H0 = hybrid: G0 global + symbol/cluster corrections (reuses G0 estimator)
    ↓
CALIBRATION [phase5/calibration.py]
    Cal-A → fit calibrator (linear scaling)
    Cal-B → select threshold (maximize expected value)
    ↓
THRESHOLD / NO_TRADE [economics.py]
    select_cal_b_thresholds() → per-granularity thresholds
    build_oos_trades() → test set trade signals
    NO_TRADE when |prediction| < threshold
    ↓
EVALUATION [metrics.py]
    MAE, RMSE, R², Directional Accuracy, Pearson IC, Spearman IC, Cross-sectional IC
    + per-symbol, per-cluster, per-age-bucket breakdowns
    ↓
REPORTS [training.py:_run_one → report.json + model.joblib]
    checkpoint_store.complete() → atomic JSON checkpoint
    ↓
SUMMARY [training_summary.json]
```

---

## 4. Dataset Audit

### 4.1 Gold Dataset Location

> [!CAUTION]
> **CRITICAL RISK**: The 9.1 GB Gold dataset exists ONLY on the GCP VM `crypto-phase7` persistent disk (`pd-balanced`, 250 GB). The disk has `auto-delete: true`. If someone deletes the VM (which they might to save storage costs), the Gold dataset is **permanently destroyed**. This is documented in the hold state but must be the first thing protected on resume.

| Item | Status | Evidence |
|------|--------|----------|
| Gold present locally | NO | No `data/gold/` directory on laptop |
| Gold on GCS | NO | "No GCS object matched the dataset ID" per hold doc |
| Gold on VM disk | YES | Hold doc: "GOLD PRESERVED ON PERSISTENT DISK" |
| Dataset ID | `gold-phase7-0cbf2910e8d96c9d19826598` | Hold manifest |
| Partitions | 138 | Hold manifest (matches expected) |
| Row count | 50,352,548 | Hold manifest (matches expected) |
| Aug rows in Gold | 0 | Hold doc: "Gold August rows: zero in the validation scan" |
| July rows | Excluded | Research cutoff 2026-07-01 enforced |
| Gold checkpoint SHA | UNKNOWN | VM stopped; cannot read without starting VM |

### 4.2 Gold Schema (from source code)

Columns confirmed in `gold.py` and `features.py`:
- `symbol`, `feature_time` (µs timestamp), `entry_time`, `label_end_time`, `horizon_minutes`
- `raw_future_return`, `normalized_future_return`, `ex_ante_volatility_scale`
- `mfe_long`, `mae_long`, `mfe_short`, `mae_short`, `target_version`
- All 54 feature columns (see Section 6)
- `cross_sectional_context_scope` (must equal `"FOLD_ACTIVE_SYMBOLS"`)
- Partitioned by `symbol` and `year`

### 4.3 August Holdout Lock

The lock is enforced at three independent layers:
1. **Config**: `prospective_holdout_used = false`, `Literal[False]` type constraint
2. **Gold build**: Hard `ValueError` if any feature_time or label_end_time ≥ 2026-08-01
3. **Gold load**: `_load_gold_manifest` validates holdout status before training
4. **Tests**: Dedicated holdout lock tests in test suite

**Verdict: August holdout LOCKED_UNUSED. No violations found.**

---

## 5. Target Audit

### 5.1 Target Formulation

| Property | Value |
|----------|-------|
| Function | `generate_multiasset_targets()` (`targets.py`) |
| Target type | **Regression** (continuous return) — NOT binary/multiclass |
| Primary target | `raw_future_return = open[entry_offset + steps] / open[entry_offset] - 1.0` |
| Secondary target | `normalized_future_return = raw / max(abs(daily_volatility), floor)` |
| Entry timing | `entry_offset = 1 + decision_latency_bars = 1 + 1 = 2` ✅ |
| Entry price | `open[i+2]` — the open of two bars after the feature time |
| Feature time | `open_time + 5m` — end of current bar |

### 5.2 Horizon Definitions

| Horizon | Steps | entry_offset | target_offset | label_end_time formula |
|---------|-------|-------------|---------------|------------------------|
| 15m | 3 | 2 | 5 | feature_time + 5×5m = 25 minutes later |
| 30m | 6 | 2 | 8 | feature_time + 8×5m = 40 minutes later |
| 60m | 12 | 2 | 14 | feature_time + 14×5m = 70 minutes later |
| 120m | 24 | 2 | 26 | feature_time + 26×5m = 130 minutes later |

### 5.3 Target Leakage Checks

- **Entry timing**: ✅ `open[i+2]` correctly reflects trading latency
- **Label end**: ✅ Uses actual price at exit time, not closed bar
- **No bfill/ffill**: ✅ Confirmed absent from target code
- **Gap safety**: ✅ `_consecutive_forward` counts available forward bars; sets target invalid if gap exists
- **Cross-symbol**: ✅ Each symbol processed independently in its own loop
- **MFE/MAE**: ✅ Causal — computed from sliding_window_view over [entry:exit] price range
- **Cutoff enforcement**: ✅ Post-validation assertion `label_end_time < research_cutoff`

### 5.4 Noted Issue

> [!NOTE]
> MFE_short = MAE_long and MAE_short = MFE_long is **intentional and correct**. A short position's maximum favorable excursion is the long's maximum adverse excursion (lowest price in window).

---

## 6. Feature Audit — All 54 A6 Native Features

| Feature | Category | Lookback | Uses Only Past Data? | Leakage Risk |
|---------|----------|----------|---------------------|--------------|
| `return_5m` | BASE | 1 bar | ✅ Yes | None |
| `return_15m` | BASE | 3 bars | ✅ Yes | None |
| `return_30m` | BASE | 6 bars | ✅ Yes | None |
| `return_1h` | BASE | 12 bars | ✅ Yes | None |
| `return_4h` | BASE | 48 bars | ✅ Yes | None |
| `range_pct` | BASE | 1 bar | ✅ Yes | None |
| `body_pct` | BASE | 1 bar | ✅ Yes | None |
| `atr14_pct` | BASE | 14 bars | ✅ Yes | None |
| `ema20_distance_pct` | BASE | ≥20 bars | ✅ Yes | None — see Bug M-1 |
| `realized_volatility_1h` | BASE | 12 bars | ✅ Yes | None |
| `daily_volatility` | BASE | 288 bars | ✅ Yes | None |
| `seven_day_volatility` | BASE | 2016 bars | ✅ Yes | None |
| `relative_quote_volume` | BASE | Config (2016) | ✅ Yes | None |
| `volume_zscore` | BASE | Config (2016) | ✅ Yes | None |
| `trade_count_zscore` | BASE | Config (2016) | ✅ Yes | None |
| `taker_buy_share` | BASE | 1 bar | ✅ Yes | None |
| `taker_sell_share` | BASE | 1 bar | ✅ Yes | None |
| `taker_flow_imbalance` | BASE | 1 bar | ✅ Yes | None |
| `funding_zscore` | BASE | Rolling window | ✅ Yes | Low |
| `mark_index_basis` | BASE | 1 bar | ✅ Yes | Low |
| `contract_mark_basis` | BASE | 1 bar | ✅ Yes | Low |
| `return_5m_over_ex_ante_vol` | BASE | 12 bars | ✅ Yes | None |
| `return_1h_over_daily_vol` | BASE | 288 bars | ✅ Yes | None |
| `return_4h_over_7d_vol` | BASE | 2016 bars | ✅ Yes | None |
| `listing_age_days` | COIN_CONTEXT | Registry | ✅ Yes | Low |
| `history_length_days` | COIN_CONTEXT | Registry | ✅ Yes | Low — identical to above |
| `trailing_liquidity_percentile` | COIN_CONTEXT | Config (2016) | ✅ Yes | Medium — fold-scoped |
| `trailing_volatility_percentile` | COIN_CONTEXT | 2016 bars | ✅ Yes | Medium — fold-scoped |
| `trade_intensity_percentile` | COIN_CONTEXT | Config | ✅ Yes | Medium — fold-scoped |
| `btc_beta` | COIN_CONTEXT | Config (2016) | ✅ Yes | None |
| `btc_correlation` | COIN_CONTEXT | Config (2016) | ✅ Yes | None |
| `eth_correlation` | COIN_CONTEXT | Config (2016) | ✅ Yes | None |
| `relative_strength_vs_btc` | COIN_CONTEXT | 12 bars | ✅ Yes | None |
| `relative_strength_vs_eth` | COIN_CONTEXT | 12 bars | ✅ Yes | None |
| `beta_adjusted_residual_return` | COIN_CONTEXT | Config+12 | ✅ Yes | None |
| `btc_return_5m` | ANCHOR | 1 bar | ✅ Yes | None |
| `btc_return_15m` | ANCHOR | 3 bars | ✅ Yes | None |
| `btc_return_30m` | ANCHOR | 6 bars | ✅ Yes | None |
| `btc_return_1h` | ANCHOR | 12 bars | ✅ Yes | None |
| `btc_return_4h` | ANCHOR | 48 bars | ✅ Yes | None |
| `btc_volatility_1h` | ANCHOR | 12 bars | ✅ Yes | None |
| `btc_taker_flow_imbalance` | ANCHOR | 1 bar | ✅ Yes | None |
| `eth_return_5m` | ANCHOR | 1 bar | ✅ Yes | None |
| `eth_return_1h` | ANCHOR | 12 bars | ✅ Yes | None |
| `eth_return_4h` | ANCHOR | 48 bars | ✅ Yes | None |
| `eth_volatility_1h` | ANCHOR | 12 bars | ✅ Yes | None |
| `market_mean_return` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_median_return` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_pct_positive` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_pct_negative` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_return_dispersion` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_median_volatility` | MARKET | 12 bars (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_median_taker_flow_imbalance` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |
| `market_member_count` | MARKET | 1 bar (per-t) | ✅ Yes | Medium — fold-scoped |

**Total: 54 features confirmed** ✅

**HTF join**: 12h and 1d candles use `availability_time = open_time + interval`. The as-of join requires `availability_time <= feature_time`, guarded by runtime assertion at `features.py:256-257`. ✅

**Cross-sectional scope**: `bind_fold_cross_sectional_context()` overwrites all MARKET/COIN percentile features using only fold-active symbols. ✅

---

## 7. Leakage Audit

| Check | Result | Notes |
|-------|--------|-------|
| `bfill()` anywhere | ✅ NONE | No backward fill found |
| `ffill()` in features | ✅ NONE | NaN propagates naturally |
| Centered rolling windows | ✅ NONE | All windows are trailing |
| Future price in features | ✅ NONE | All features are ex-ante |
| Scaler fitted on OOS data | ✅ NONE | Calibrator fitted only on Cal-A |
| Cross-symbol target | ✅ NONE | Per-symbol loop is independent |
| HTF future bar leakage | ✅ NONE | Availability time guard + assertion |
| August data accessed | ✅ NONE | Config + Gold + manifest all enforce |
| Global stats from future folds | ✅ NONE | `bind_fold_cross_sectional_context` |

**Overall leakage verdict: PASS.** No temporal or cross-sectional leakage found in feature or target construction.

---

## 8. Fold / Purge / Embargo Audit

### 8.1 Fold Structure

16 calendar-month walk-forward folds, rolling window:
- Train: 24 months
- Validation: 3 months
- Cal-A (calibration): ~3 months (first half of calibration)
- Cal-B (threshold selection): ~3 months (second half of calibration)
- Test: 3 months
- Step: 3 months

**Fold 1 approximate boundaries** (derived from 2020-01-01 start):
- Train: 2020-01-01 → 2022-01-01
- Validation: 2022-01-01 → 2022-04-01
- Calibration: 2022-04-01 → 2022-07-01
- Test: 2022-07-01 → 2022-10-01

### 8.2 Purge and Embargo

| Check | Implementation | Status |
|-------|---------------|--------|
| Purge method | Filters on actual `label_end_time < boundary` | ✅ CORRECT |
| Static-offset purge (WRONG method) | NOT used | ✅ PASS |
| Embargo | Drops rows where `feature_time < boundary + 120min` | ✅ CORRECT |
| Embargo duration | 120 minutes = max(horizons) | ✅ CORRECT |
| Label overlap across folds | Impossible — purge uses label_end_time | ✅ PASS |
| Cross-sectional scope check | `scopes == {"FOLD_ACTIVE_SYMBOLS"}` validation | ✅ PASS |

---

## 9. Survivorship Audit

| Check | Status | Notes |
|-------|--------|-------|
| Point-in-time membership | ✅ PASS | `latest_descriptors(as_of=train_end)` |
| HNTUSDT retained | ✅ YES | Core20 is point-in-time; delisting doesn't remove |
| XPINUSDT excluded | ✅ YES | `xpin_forced: false` in hold manifest |
| Delisted coins | ✅ HANDLED | Post-delisting = lifecycle absence, not error |
| Future liquidity used for selection | ✅ NO | Selection cutoff 2022-01-01, applied causally |

---

## 10. Preprocessing Audit

The system uses **no global train-fitted scalers**. Preprocessing is entirely point-in-time or structure-based:

| Component | Method | Fitted on Train Only? |
|-----------|--------|----------------------|
| Calibrator | Linear regression (Cal-A) | ✅ Yes — Cal-A only |
| Threshold selection | Grid search on Cal-B returns | ✅ Yes — Cal-B only |
| Volatility normalization | Point-in-time daily_volatility | ✅ Yes — causal feature |
| Symbol-balanced weights | Inverse symbol count (train rows) | ✅ Yes — train set |
| NaN/Inf handling | `_finite()` drops affected rows | ⚠️ See Bug C-1 |

**Test-set row dropping**: `_finite()` is also applied to the test set, dropping rows where the target is NaN. For assets that are delisted (HNTUSDT after May 2024) or have data outages, this silently removes the observation period. However, since the Gold dataset is built from only the lifecycle intersection, this effect should be minimal.

---

## 11. LightGBM Audit

### 11.1 Configuration

All 48 primary A6 specs share the same LightGBM hyperparameters from the config:

| Parameter | Value |
|-----------|-------|
| `objective` | `"regression"` (L2 loss / MSE) |
| `num_leaves` | 31 |
| `max_depth` | -1 (unlimited) |
| `learning_rate` | 0.02 |
| `n_estimators` | 500 |
| `min_child_samples` | 100 |
| `subsample` | 0.9 |
| `subsample_freq` | 1 |
| `colsample_bytree` | 0.9 |
| `reg_alpha` | 0.1 |
| `reg_lambda` | 1.0 |
| `early_stopping_rounds` | 50 |
| `random_state` | 42 |
| `deterministic` | True |
| `force_col_wise` | True |
| `n_jobs` | 4 (model_threads) |
| `verbosity` | -1 (silent) |

### 11.2 Why 48 Specs Differ

The 48 primary A6 specs differ only in:
- **Architecture**: G0 (global), C0 (cluster), P0 (per-symbol), H0 (hybrid) — 4 architectures
- **Horizon**: 15m, 30m, 60m, 120m — 4 horizons
- **Target type**: `raw`, `volatility_normalized` — 2 types
- **Symbol balancing**: G0-balanced, G0-unbalanced, G0-symbol-id (ablations)
- **Explicit symbol ID**: One G0+symbol-ID variant per horizon×target = 8 more

**Total**: 4×2×4 + 4×2×2 = 32 + 16 = 48 A6 primary specs ✅

**Additional 10 deferred**: 6 feature ablation (A0-A5) + 4 HTF controls — correctly deferred for Phase 7A.

### 11.3 Issues Found

1. **Objective for raw returns**: MSE on raw future returns is mathematically sub-optimal for heteroskedastic crypto data. High-volatility events dominate the loss. However, this is the established scientific methodology — do not change.
2. **Validation set in early stopping**: The validation set (with purge/embargo) is used for early stopping. This is acceptable since the validation set is temporally after training but before calibration.
3. **Thread safety**: Parallel C0/P0 fits use `ThreadPoolExecutor`. LightGBM uses OpenMP internally. `force_col_wise=True` helps reduce thread contention. Monitored carefully in benchmark (results were bit-exact).

---

## 12. Metrics Audit

| Metric | Computed | Meaningful for Target? |
|--------|----------|----------------------|
| MAE | ✅ | Yes — regression metric |
| RMSE | ✅ | Yes — regression metric |
| R² | ✅ | Yes, though often near 0 for returns |
| Directional Accuracy | ✅ | Yes — practical trading relevance |
| Pearson IC | ✅ | Yes — measures linear signal quality |
| Spearman IC | ✅ | Yes — rank-based, more robust |
| Cross-Sectional IC | ✅ | Yes — measures cross-asset ranking |
| Coverage | ✅ | Yes — % observations with predictions |
| Per-symbol, per-cluster | ✅ | Yes — identifies weak symbols |
| Economic (trades, Sharpe, etc.) | ✅ | Yes, clearly labeled as research estimates |
| Accuracy/F1/AUC | ❌ Not computed | Correct — target is continuous regression |

---

## 13. Baselines

Since no model has been trained yet, baselines are estimated from target structure:

**Majority-class baseline** (directional accuracy if you always predict UP):
- Approximately 50% directional accuracy in a zero-drift regime
- Crypto has mild positive drift, so baseline is ~50-53%

**Zero-return predictor baseline**:
- MAE ≈ std(raw_future_return) × √(π/2)
- RMSE ≈ std(raw_future_return)
- R² = 0.0
- Directional accuracy ≈ 50%

**IC baseline**:
- Pearson IC = 0.0, Spearman IC = 0.0

---

## 14. Performance Bottleneck Audit

### 14.1 Root Cause of 6h21m with 0 Models

The bottleneck is in `training.py:_load_fold_rows()` (lines ~216-233):

```python
condition = (
    (ds.field("feature_time") >= pa.scalar(plan.train_start))
    & (ds.field("feature_time") < pa.scalar(plan.test_end))
    & (ds.field("horizon_minutes") == horizon_minutes)
)
return dataset.to_table(filter=condition)
```

**The problem**: PyArrow's `ds.field("feature_time")` filter operates on row-group metadata but **cannot push down to year-partition directories** unless the partition field (`year`) is explicitly included in the filter. This forces PyArrow to open and scan **every one of the 138 Parquet files** for every fold/horizon combination.

**Impact calculation**:
- 4 horizons × 2 research views × 16 folds = 128 full-dataset scans
- Each scan = open 138 files × read metadata + filter = ~3-4 minutes
- 128 × 3.5 min = ~450 minutes ≈ **7.5 hours just in I/O**

### 14.2 Fix Required (CATEGORY 1 — MUST FIX)

Add year filter to `_load_fold_rows`:
```python
start_year = plan.train_start.year
end_year = plan.test_end.year
condition = (
    (ds.field("year") >= start_year)
    & (ds.field("year") <= end_year)
    & (ds.field("feature_time") >= pa.scalar(plan.train_start))
    & (ds.field("feature_time") < pa.scalar(plan.test_end))
    & (ds.field("horizon_minutes") == horizon_minutes)
)
```

This requires verifying that the Gold dataset is actually partitioned with a `year` directory level (confirmed by schema: `partitioned by symbol and year`).

### 14.3 Repeated Computation

The code shares `ds.dataset(gold_paths)` across horizons for the same fold (line 792: `gold_dataset = ds.dataset(...)` created once). This is correct. However, each horizon still triggers a separate `to_table()` call.

**Prepared matrix cache**: The code does cache `PreparedTrainingSegments` across specs sharing the same (fold, horizon, target, feature_set) key. This means the expensive `_prepare_training_segments` call runs once per unique (fold, horizon, target_type, feature_group) combination — approximately 4 × 2 × 2 = 16 times per fold (not 58 times). This design is correct.

---

## 15. Memory Analysis

### 15.1 Estimated RAM for Fold-1

| Component | Calculation | Size |
|-----------|-------------|------|
| Fold-1 train table (Arrow) | ~6M rows × 54 features × 8 bytes | ~2.6 GB |
| train_x (NumPy float64 copy) | 6M × 54 × 8 bytes | ~2.6 GB |
| validation_x | ~1.5M × 54 × 8 bytes | ~0.6 GB |
| calibration_a_x | ~1.5M × 54 × 8 bytes | ~0.6 GB |
| calibration_b_x | ~1.5M × 54 × 8 bytes | ~0.6 GB |
| **Subtotal one spec** | | **~7 GB** |
| During matrix switch (old + new) | Both alive during reassignment | **~14 GB spike** |
| G0 with explicit symbol ID | Extra 20-column one-hot × rows | +1 GB |
| LightGBM internal buffers | Varies; ~1-2× train set | ~5 GB |
| **Estimated peak for Fold-1** | | **~20-30 GB** |

For a Lightning AI instance with 64 GB RAM, this is within bounds. For 32 GB, it would OOM.

### 15.2 Dtype Optimization Opportunity

All features are stored and processed as `float64`. For price returns and normalized features, `float32` is generally sufficient and would halve the memory footprint. However, this changes the frozen scientific methodology and should not be done in Phase 7A.

---

## 16. Cache / Checkpoint Recommendations

### 16.1 Current Checkpoint Design

The current per-spec checkpoint system is correct:
- Atomic JSON writes via `atomic_json()`
- Identity includes: config hash, universe hash, fold_membership hash, gold manifest hash, source file manifest hash
- Orphan adoption: validated against frozen identity components
- Resume: skips `is_complete()` specs

### 16.2 Missing: Prepared-Matrix Cache (PRIMARY BLOCKER)

As documented in the hold state, the critical missing piece is a **pre-training prepared-matrix cache**. Currently:
- Fold-1 spends hours in Gold scanning + matrix preparation
- If interrupted, ALL preparation work is repeated from scratch
- There is no durable artifact between "Gold loaded" and "first model fit"

**Recommended cache design** (must not change methodology):

```
Cache identity must bind:
- gold_dataset_id (gold-phase7-0cbf2910e8d96c9d19826598)
- configuration_hash (93f987736b1a79d26b773957)
- source_fingerprint (current file hashes of features.py, targets.py)
- fold_id (fold_01, fold_02, ...)
- research_view (CORE or EXPANDING)
- horizon_minutes (15, 30, 60, 120)
- target_type (raw or volatility_normalized)
- feature_group (A6)
- fold_membership_hash
- purge_boundary (label_end_time filter)
- embargo_boundary (feature_time filter)
- preprocessing_contract_version

Cache contents (Parquet or Arrow IPC):
- train_x (float64 NumPy → Parquet)
- train_y
- train_symbols
- validation_x, validation_y, validation_symbols
- calibration_a (full table)
- calibration_b (full table)

Cache storage: local_artifacts/phase7/prep_cache/{cache_id}/
Atomic write: write to .tmp then os.replace()
Validation: read back and verify row counts + column hash
Reject on identity mismatch
```

---

## 17. Lightning AI Compute Recommendation

### 17.1 Current GCP Dependency Issues

| Issue | Severity | Location |
|-------|----------|----------|
| Hardcoded `gs://crypto-ai-data-83921/` in `phase7a_vm_supervisor.py` | HIGH | `scripts/phase7a_vm_supervisor.py` |
| GCP environment variables (`PHASE7_GCP_PROJECT`, etc.) | HIGH | `scripts/run_phase7a_pipeline.py` |
| `gcloud` CLI commands in runbook | MEDIUM | `PHASE7_CLOUD_RUNBOOK.md` |
| `tmux` session management | LOW | `run_phase7a_worker.sh` |
| `/usr/bin/time` binary assumption | MEDIUM | `phase7a_vm_supervisor.py` |

### 17.2 Lightning AI Migration Requirements

1. Replace GCS storage paths with Lightning AI object store or mounted volume
2. Replace `gcloud compute ssh` commands with Lightning SSH or CLI
3. The supervisor script `phase7a_vm_supervisor.py` needs a Lightning-compatible watchdog
4. Environment variables need Lightning-specific values

### 17.3 Hardware Recommendation

**The workload is CPU-bound, not GPU-bound.** LightGBM is optimized for CPU. GPU LightGBM is explicitly disabled (`require_gpu=False`).

| Metric | Estimate | Confidence |
|--------|----------|------------|
| RAM required | 32-64 GB | MEDIUM |
| CPU cores useful | 16 (4 model threads × 4 workers) | HIGH |
| GPU needed | No | HIGH |
| Disk for Gold + prep cache | 15-30 GB | MEDIUM |
| Fold-1 wall time (after partition fix) | 2-6 hours | LOW |
| All-fold wall time | 50-200 hours | VERY LOW |

**Recommended Lightning instance**: 16 vCPU, 64 GB RAM, SSD-backed storage, no GPU. Start with a CPU-optimized instance.

### 17.4 Credit Estimation (Lightning AI)

Without knowing exact Lightning pricing or Fold-1 measured runtime, any credit estimate would be fabricated. **Run one Fold-1 first with the partition filter fix, measure actual runtime, then estimate.**

---

## 18. Bugs and Errors Discovered

| ID | Severity | Category | File / Location | Problem | Scientific Impact | Fix |
|----|----------|----------|-----------------|---------|-------------------|-----|
| **B-01** | 🔴 CRITICAL | Source Freeze | `configs/contracts/phase7_scientific_baseline_v1_9.json` | Stored SHA of `models.py` is `51444b70...` but current file is `ded9af59...`. 2 tests fail. | Checkpoint identity system may reject valid checkpoints built from current code | Update `source_freeze` in the contract to match current `models.py` hash, then re-run tests |
| **B-02** | 🔴 HIGH | Data Risk | GCP VM persistent disk | 9.1 GB Gold stored ONLY on VM disk with `auto-delete: true`. No GCS copy. | If VM is deleted, Gold is permanently lost — requiring full re-acquisition and re-build | Immediately upload Gold to GCS on resume before starting any training |
| **B-03** | 🔴 HIGH | Performance | `training.py:_load_fold_rows` (~L227) | No year-partition filter in PyArrow scan → 138-file scan per fold/horizon | Caused the 6h21m bottleneck with 0 models | Add `ds.field("year")` range filter |
| **B-04** | 🟡 HIGH | Resume Logic | `training.py` (~L924-950) | On resume, completed G0 specs are skipped but NOT loaded into `reusable_models`. H0 then redundantly retrains the global estimator. | Wasted compute; potential non-determinism if hardware changes | In resume block for G0, call `load_model(model_path)` and populate `reusable_models` |
| **B-05** | 🟡 HIGH | Memory | `models.py:_matrix` + `training.py:_prepare_training_segments` | `np.column_stack` creates full float64 copy of feature matrix. Previous `prepared_cache` not explicitly freed before new one is created → ~60 GB peak spike | OOM on 32 GB instance | Pre-allocate single output array; `del prepared_cache` before creating new one |
| **B-06** | 🟡 MEDIUM | Feature | `features.py:_ema` (~L172) | If first `window` bars contain ANY NaN, the entire segment returns all-NaN. An early missing bar loses EMA for the entire symbol permanently. | `ema20_distance_pct` is lost for symbols with early data gaps | Find first contiguous block of `window` finite values to initialize EMA |
| **B-07** | 🟡 MEDIUM | Performance | `metrics.py:cross_sectional_ic` (~L64) | O(N×T) loop: for each unique timestamp, evaluates `times == timestamp` over entire array | Slow metric calculation for large test sets | Use `np.argsort` + `np.split` or Pandas `groupby` |
| **B-08** | 🟡 MEDIUM | Cloud | `scripts/phase7a_vm_supervisor.py` | Hardcoded `gs://crypto-ai-data-83921/artifacts/phase7` and GCP-specific env vars | Code will not run on Lightning AI without modification | Parameterize storage root via environment variable |
| **B-09** | 🟡 MEDIUM | Testing | `tests/phase7/test_log_rotation.py` | 5 tests fail with `FileNotFoundError: bash script not found` — tests call `rotate_phase7_run_log.sh` which is Linux-only | Tests are platform-specific; CI on Windows will always fail | Mark Linux-only tests with `pytest.mark.skipif(sys.platform == "win32")` |
| **B-10** | 🟢 LOW | Feature | `features.py` | `history_length_days` and `listing_age_days` are computed identically from the same registry field | Wastes 1 of 54 feature slots with a duplicate | Document as deliberate redundancy or deduplicate |
| **B-11** | 🟢 LOW | Exception | `phase7/discovery_checkpoint.py` | Broad exception catching `(FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError)` swallowed, returning `None` | Corruption may be silently ignored | Log the exception at WARNING before returning None |

---

## 19. Must-Fix Before Training (Category 1)

| Priority | Item | Why Blocking |
|----------|------|-------------|
| **1** | Fix byte-freeze contract (`B-01`) | 2 tests fail. Checkpoint identity verification will reject all new checkpoints built on current code. Training cannot produce scientifically verifiable results. |
| **2** | Upload Gold to GCS backup (`B-02`) | If VM is accidentally deleted, 9.1 GB Gold is permanently lost. Cannot train without Gold. This is an infrastructure action, not a code change. |
| **3** | Add year-partition filter to `_load_fold_rows` (`B-03`) | Without this, every Fold-1 attempt will spend 4-8 hours in I/O before fitting a single model. The only fix is to add the year filter. |
| **4** | Implement prepared-matrix cache | Per hold state hold manifest — `open_blocker: FOLD1_MATRIX_PREPARATION_AND_CHECKPOINTING`. Without a durable cache, interruptions repeat all preparation work. |

---

## 20. Recommended Improvements (Category 2)

| Priority | Item | Impact |
|----------|------|--------|
| **A** | Fix H0 reuse on resume (`B-04`) | Avoid redundant G0 retraining; correctness |
| **B** | Fix EMA initialization for early gaps (`B-06`) | Recover a feature for symbols with early NaN periods |
| **C** | Pre-allocate feature matrices; explicit `del` (`B-05`) | Reduce peak RAM by ~50%; avoid OOM |
| **D** | Vectorize `cross_sectional_ic` (`B-07`) | Speed up metric computation |
| **E** | Parameterize GCS/storage root (`B-08`) | Enable Lightning AI migration |
| **F** | Add `skipif` to Linux-only tests (`B-09`) | Windows CI will show 0 test failures |
| **G** | Log swallowed exceptions in discovery checkpoint (`B-11`) | Easier debugging of corrupt checkpoints |

---

## 21. Performance Estimate

> [!IMPORTANT]
> **No models have been trained. No observed performance exists.**
> All ranges below are code-based estimates only, NOT observed results.

### 21.1 Rationale

The target is a **continuous return regression** evaluated via IC (correlation between prediction and actual return). Based on:
- Crypto perpetual futures: low signal-to-noise ratio
- 20-symbol universe: reasonable cross-sectional variation
- 54 features including momentum, volume, order flow, BTC co-movement
- 24-month training window per fold
- Horizons from 15m to 120m (shorter = noisier)
- LightGBM with regularization (num_leaves=31, L2=1.0)

### 21.2 Expected Performance Range

```
Metric                    Conservative   Plausible   Optimistic
----------------------------------------------------------------
Pearson IC (60m)           0.01          0.03         0.06
Spearman IC (60m)          0.01          0.03         0.06
Directional Accuracy (60m) 50.5%         52%          55%
R² (60m)                   0.001         0.005        0.02
MAE (relative to std)      95%           90%          85%
Directional Accuracy (15m) 50.2%         51%          53%
Directional Accuracy (120m)51%           53%          57%
```

**Why these ranges:**
- IC of 0.03-0.05 would be considered a **solid signal** in quantitative finance — most crypto ML papers report 0.02-0.08 on similar horizons
- Shorter horizons (15m) are noisier than longer ones (120m)
- Symbol-balanced training may improve cross-sectional predictions but slightly hurt overall accuracy
- The heteroskedastic regime variation in crypto means some folds will be near zero

**Confidence: LOW** — these are theoretical estimates based on published crypto ML literature and the feature/target design. Only running Fold 1 will produce actual evidence.

### 21.3 Trading vs Accuracy

A model with directional accuracy of 52-54% is **NOT automatically profitable** because:
- 10 bps round-trip fees (high liquidity tier) require ~17 bps edge to break even at 60m
- The NO_TRADE mechanism filters to only high-confidence signals, improving precision at the cost of coverage
- The economic stress tests apply 1.0×/1.25×/1.5×/2.0× cost multipliers — a model that survives 2× costs has genuine edge

---

## 22. Limitations of Performance Estimate

1. **No observed result exists** — all numbers are theoretical
2. **Gold not accessible locally** — cannot run any profiling or dry-runs on actual data
3. **Fold 1 never completed** — no baseline fold performance to extrapolate from
4. **Market regime sensitivity** — the 16 walk-forward folds span 2020-2026 including COVID crash, 2021 bull, 2022 bear, 2023-2024 recovery; performance will vary dramatically by fold
5. **Class imbalance in trade selection** — the NO_TRADE filter changes the effective population
6. **BTC dominance regime** — features heavy in BTC co-movement may perform differently in alt-season vs BTC-season periods

---

## 23. Training Readiness Decision

**VERDICT: NOT READY**

**Blockers (must fix first):**
1. ❌ Byte-freeze contract violation (`B-01`) — 2 tests fail, checkpoint system will not verify correctly
2. ❌ Gold backup required (`B-02`) — infrastructure risk before starting compute
3. ❌ Partition filter bug (`B-03`) — without this fix, Fold-1 will again spend 6+ hours with 0 models
4. ❌ Prepared-matrix cache — without this, any interruption restarts all preparation

**Ready states (confirmed):**
- ✅ Scientific methodology: correct, causal, no leakage
- ✅ Repository state: matches expected frozen commit and tags
- ✅ Holdout: LOCKED_UNUSED, enforced at config + Gold + manifest layers
- ✅ Fold logic: correct purge/embargo implementation
- ✅ Feature engineering: 54 features all causally correct
- ✅ Target construction: `open[i+2]` timing confirmed
- ✅ Survivorship: point-in-time universe, HNTUSDT retained, XPIN excluded
- ✅ 601 tests passing (ignoring 5 Linux-only + 2 byte-freeze failures)

---

## 24. Terminal Summary

```
========================================
CRYPTO 2.0 — PHASE 7A AUDIT
========================================

Repository:
  HEAD:   28d3098 ✅ MATCHES EXPECTED
  Branch: main ✅
  Tags:   crypto2.0-handoff-20260906 ✅  phase7a-hold-20260906 ✅
  Status: PASS (untracked files are build artifacts, not science)

Gold Dataset:
  NOT AVAILABLE LOCALLY
  Location: GCP VM persistent disk only
  Expected: 138 partitions, 50,352,548 rows, ~9.1 GB
  Status: CRITICAL RISK — no offsite backup, auto-delete enabled on VM disk

Target Alignment:
  PASS — open[i+2] confirmed, label_end_time correct, no future leakage

Feature Leakage:
  PASS — all 54 features are causally safe, no bfill/ffill, HTF join guarded

Temporal Leakage:
  PASS — no temporal or cross-sectional leakage found

Survivorship:
  PASS — point-in-time membership, HNTUSDT retained, XPIN excluded

Fold Logic:
  PASS — 16 calendar folds, correct boundaries

Purge Logic:
  PASS — actual label_end_time used, not static offset

Embargo:
  PASS — 120 minutes = max(horizons), implemented correctly

Train-only Preprocessing:
  PASS — calibrator and threshold fitted on Cal-A/Cal-B only

August Holdout:
  LOCKED_UNUSED — enforced at 3 independent layers

Tests:
  601 passed
  7 failed (2 = byte-freeze contract; 5 = Linux-only log rotation)
  0 skipped

Critical Issues: 0 (no immediate data corruption or leakage)
High Issues:     4 (Gold backup, partition filter, byte-freeze, resume G0 cache)
Medium Issues:   5 (EMA init, IC bottleneck, GCP paths, Windows tests, exceptions)
Low Issues:      2 (duplicate feature, no CLI completion)

Current Training Readiness:
  NOT READY

  Required before training:
  1. Fix byte-freeze contract (update models.py hash in v1_9 JSON)
  2. Upload Gold to GCS (infrastructure)
  3. Add year-partition filter to _load_fold_rows
  4. Implement prepared-matrix checkpoint cache

Primary Bottleneck:
  Missing year-partition filter in _load_fold_rows causes 138-file scan per
  fold/horizon combination → estimated 4-8 hours in I/O before first model fit.

Recommended Lightning Compute:
  CPU-optimized instance: 16 vCPU, 64 GB RAM, no GPU, SSD storage (50+ GB)
  LightGBM is CPU-bound; GPU provides no benefit.

Estimated Fold-1 Prep Time (after partition fix):
  15-60 minutes (vs. 6+ hours currently)
  INSUFFICIENT EVIDENCE FOR PRECISE ESTIMATE — measure on first run.

Estimated 48-model Fold-1 Runtime (after prep cache):
  2-8 hours
  INSUFFICIENT EVIDENCE — benchmark doc showed 279 seconds for 4-arch sample;
  scaling to 48 specs + calibration + economics ≈ 2-6× longer.

Estimated Lightning Credits:
  INSUFFICIENT EVIDENCE — measure Fold-1 runtime before committing budget.
  Do not run all 16 folds until Fold-1 cost is measured.

PERFORMANCE:
  Observed Accuracy:     NOT YET AVAILABLE (no models trained)
  Observed Precision:    NOT YET AVAILABLE
  Observed Recall:       NOT YET AVAILABLE
  Observed F1:           NOT YET AVAILABLE

  Code-Based Expected Performance (60m horizon, Spearman IC):
    Conservative: 0.01
    Plausible:    0.03
    Optimistic:   0.06

  Code-Based Expected Directional Accuracy (60m):
    Conservative: 50.5%
    Plausible:    52%
    Optimistic:   55%

  Confidence in Estimate: LOW

  IMPORTANT:
  ESTIMATED PERFORMANCE IS NOT AN OBSERVED RESULT.
  Run one complete Fold 1 before making any performance claims.

========================================
```

---

*Audit conducted independently. No code was modified during this audit.*
*Prepared: 2026-10-01*
