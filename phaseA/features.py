"""
Feature Engineering — Phase A
Corrected version of the original Calculate_Requried_Data function.

Bugs fixed (all were self-referential denominator issues — not true look-ahead,
but they cause spike/regime features to understate their own magnitude):

  1. volume_spike     — denominator now uses shift(1).rolling(20) not rolling(20)
  2. trade_size_spike — same fix, 24-period window
  3. volatility_regime— baseline rolling(100) now uses shift(1)
  4. range_expansion  — range_ma20 baseline now uses shift(1).rolling(20)
  5. volume_ma20      — shifted before rolling so liquidity_shock is uncontaminated

All other features confirmed safe:
  - cvd_24 / cvd_ratio_24: rolling sum of CLOSED-candle taker data — no leakage
  - vwap_24 / vwap_dev:    rolling over closed candles — no leakage
  - rolling_sharpe:        window [t-23..t] entirely in the past; label is t+1+ — safe
  - market_return:         cross-symbol mean of return_1 at same timestamp — safe in
                           batch training; Phase B will gate on candle completion
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _grp(df: pd.DataFrame, col: str):
    """Return a GroupBy object on 'symbol' for the given column."""
    return df.groupby("symbol", group_keys=False)[col]


def _lagged_rolling_mean(df: pd.DataFrame, col: str, window: int) -> pd.Series:
    """
    Compute rolling mean that EXCLUDES the current observation.
    shift(1) first so the window covers [t-window .. t-1], not [t-window+1 .. t].
    This is the canonical fix for all spike-ratio denominators.
    """
    return _grp(df, col).transform(
        lambda x: x.shift(1).rolling(window, min_periods=window // 2).mean()
    )


# ── Main function ─────────────────────────────────────────────────────────────

def engineer_features(data: pd.DataFrame, timeframe: str = "1h") -> pd.DataFrame:
    """
    Compute all trading features from a multi-symbol OHLCV dataframe.

    Required input columns:
        symbol, timestamp, open, high, low, close, volume,
        quote_volume, taker_buy_quote, trades

    Parameters
    ----------
    data : pd.DataFrame
        Sorted by (symbol, timestamp) before calling this function.
    timeframe : str
        Informational only; used in log messages.

    Returns
    -------
    pd.DataFrame
        Original dataframe with all feature columns appended.
        Intermediate helper columns (tr, rolling_high_20, etc.) are dropped.
        Inf values replaced with NaN. Rows are NOT dropped here — the caller
        (train.py) decides when to dropna so it can align with labels.
    """
    data = data.copy()

    # ── 1. Returns / momentum ─────────────────────────────────────────────────
    for lag in [1, 3, 6, 12, 24]:
        data[f"return_{lag}"] = _grp(data, "close").pct_change(lag)

    # ── 2. EMA trend structure ────────────────────────────────────────────────
    data["ema20"] = _grp(data, "close").transform(
        lambda x: x.ewm(span=20, adjust=False).mean()
    )
    data["ema50"] = _grp(data, "close").transform(
        lambda x: x.ewm(span=50, adjust=False).mean()
    )
    data["ema_diff"]  = data["ema20"] - data["ema50"]
    data["ema_slope"] = _grp(data, "ema20").pct_change()

    # ── 3. True Range / ATR ───────────────────────────────────────────────────
    prev_close = _grp(data, "close").shift(1)
    data["_tr"] = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - prev_close).abs(),
            (data["low"]  - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Use Wilder's EMA (span=14) — matches TradingView's ATR(14)
    data["atr_14"] = _grp(data, "_tr").transform(
        lambda x: x.ewm(span=14, adjust=False).mean()
    )
    data["atr_ratio"] = data["atr_14"] / data["close"].replace(0, np.nan)

    # ── 4. Order flow ─────────────────────────────────────────────────────────
    data["taker_sell_quote"] = data["quote_volume"] - data["taker_buy_quote"]
    data["net_taker_volume"] = data["taker_buy_quote"] - data["taker_sell_quote"]
    data["buy_pressure"] = (
        data["taker_buy_quote"] / data["quote_volume"].replace(0, np.nan)
    )

    # CVD: rolling sum over [t-23 .. t] — all closed candles. Safe.
    data["cvd_24"] = _grp(data, "net_taker_volume").transform(
        lambda x: x.rolling(24, min_periods=12).sum()
    )
    _rolling_qvol_24 = _grp(data, "quote_volume").transform(
        lambda x: x.rolling(24, min_periods=12).sum()
    )
    data["cvd_ratio_24"] = data["cvd_24"] / _rolling_qvol_24.replace(0, np.nan)

    # ── 5. Volatility-adjusted returns ────────────────────────────────────────
    _safe_atr_ratio = data["atr_ratio"].replace(0, np.nan)
    data["vol_adj_return_1"]  = data["return_1"]  / _safe_atr_ratio
    data["vol_adj_return_6"]  = data["return_6"]  / _safe_atr_ratio
    data["vol_adj_return_12"] = data["return_12"] / _safe_atr_ratio

    # ── 6. Volume / liquidity ─────────────────────────────────────────────────
    # BUG FIXED (1/5): shift(1) ensures current volume is NOT in its own baseline.
    _vol_baseline_20 = _lagged_rolling_mean(data, "quote_volume", 20)
    data["volume_spike"] = data["quote_volume"] / _vol_baseline_20.replace(0, np.nan)

    _safe_trades = data["trades"].replace(0, 1)
    data["avg_trade_size"] = data["quote_volume"] / _safe_trades

    # BUG FIXED (2/5): same shift(1) fix for trade size spike.
    _size_baseline_24 = _lagged_rolling_mean(data, "avg_trade_size", 24)
    data["trade_size_spike"] = data["avg_trade_size"] / _size_baseline_24.replace(0, np.nan)

    data["volume_change"] = _grp(data, "quote_volume").pct_change()

    # BUG FIXED (5/5): volume_ma20 uses shift(1) so liquidity_shock denominator
    # does not contain the current candle's volume.
    data["volume_ma20"] = _grp(data, "volume").transform(
        lambda x: x.shift(1).rolling(20, min_periods=10).mean()
    )
    data["liquidity_shock"] = data["volume"] / data["volume_ma20"].replace(0, np.nan)

    # ── 7. Momentum ───────────────────────────────────────────────────────────
    data["momentum_3"] = _grp(data, "close").pct_change(3)
    data["momentum_4"] = _grp(data, "close").diff(4)
    data["momentum_6"] = _grp(data, "close").pct_change(6)
    data["vol_adj_momentum_4"] = data["momentum_4"] / data["atr_14"].replace(0, np.nan)
    data["price_acceleration"] = data["momentum_3"] - data["momentum_6"]

    # ── 8. VWAP ───────────────────────────────────────────────────────────────
    # Rolling VWAP over 24 closed candles. current candle (close[t], vol[t]) is
    # known at candle close — no look-ahead.
    _pv = data["close"] * data["volume"]
    _pv_sum = (
        _pv.groupby(data["symbol"])
        .transform(lambda x: x.rolling(24, min_periods=12).sum())
    )
    _v_sum = (
        data["volume"]
        .groupby(data["symbol"])
        .transform(lambda x: x.rolling(24, min_periods=12).sum())
    )
    data["vwap_24"] = _pv_sum / _v_sum.replace(0, np.nan)
    data["vwap_dev"] = (data["close"] - data["vwap_24"]) / data["vwap_24"].replace(0, np.nan)

    # ── 9. Volatility regime ──────────────────────────────────────────────────
    data["volatility_24"] = _grp(data, "return_1").transform(
        lambda x: x.rolling(24, min_periods=12).std()
    )
    # BUG FIXED (3/5): baseline uses shift(1) so current vol doesn't normalise itself.
    _vol_baseline_100 = _grp(data, "volatility_24").transform(
        lambda x: x.shift(1).rolling(100, min_periods=50).mean()
    )
    data["volatility_regime"] = data["volatility_24"] / _vol_baseline_100.replace(0, np.nan)

    # ── 10. Market structure ──────────────────────────────────────────────────
    _rolling_high = _grp(data, "high").transform(
        lambda x: x.rolling(20, min_periods=10).max()
    )
    _rolling_low = _grp(data, "low").transform(
        lambda x: x.rolling(20, min_periods=10).min()
    )
    _rng = (_rolling_high - _rolling_low).replace(0, np.nan)

    data["range_position"] = (data["close"] - _rolling_low) / _rng
    data["dist_from_high"]  = data["close"] / _rolling_high.replace(0, np.nan)
    data["dist_from_low"]   = data["close"] / _rolling_low.replace(0, np.nan)

    data["_range"] = data["high"] - data["low"]
    # BUG FIXED (4/5): range_ma20 uses shift(1) so breakout candles don't
    # dampen their own expansion ratio.
    _range_ma20 = _grp(data, "_range").transform(
        lambda x: x.shift(1).rolling(20, min_periods=10).mean()
    )
    data["range_expansion"] = data["_range"] / _range_ma20.replace(0, np.nan)

    # ── 11. Efficiency ratio (Kaufman) ────────────────────────────────────────
    _net_move   = _grp(data, "close").transform(lambda x: (x - x.shift(10)).abs())
    _total_move = _grp(data, "close").transform(
        lambda x: x.diff().abs().rolling(10, min_periods=5).sum()
    )
    data["efficiency_ratio"] = _net_move / _total_move.replace(0, np.nan)

    # ── 12. Trend strength ────────────────────────────────────────────────────
    data["trend_strength"] = data["ema_diff"].abs() / data["close"].replace(0, np.nan)

    # ── 13. Rolling Sharpe ────────────────────────────────────────────────────
    # Window [t-23..t] — all past returns. Label horizon is t+1 onwards.
    # No leakage. Meaningful at 4h (24 bars = 4 trading days).
    _r_mean = _grp(data, "return_1").transform(
        lambda x: x.rolling(24, min_periods=12).mean()
    )
    _r_std = _grp(data, "return_1").transform(
        lambda x: x.rolling(24, min_periods=12).std()
    )
    data["rolling_sharpe"] = _r_mean / _r_std.replace(0, np.nan)

    # ── 14. Market / session context ──────────────────────────────────────────
    # Cross-symbol equal-weight return at same timestamp. Safe in batch mode.
    # Phase B will gate on all-symbols-closed before computing this.
    data["market_return"] = data.groupby("timestamp")["return_1"].transform("mean")

    data["_daily_date"] = pd.to_datetime(data["timestamp"]).dt.date
    _daily_open = data.groupby(["symbol", "_daily_date"])["open"].transform("first")
    data["daily_return"] = (data["close"] - _daily_open) / _daily_open.replace(0, np.nan)

    # ── 15. Pre-clip extreme-tail features ───────────────────────────────────
    # Hard-clip 4 features before RobustScaler sees them. During black-swan
    # events (LUNA/FTX/exchange glitches) these produce values so extreme they
    # overwhelm the scaler even at quantile_range=(5,95).
    _CLIP_BOUNDS = {
        "rolling_sharpe":  (-6.0,  6.0),
        "cvd_ratio_24":    (-1.0,  1.0),
        "volume_spike":    ( 0.0, 20.0),
        "liquidity_shock": ( 0.0, 20.0),
    }
    for col, (lo, hi) in _CLIP_BOUNDS.items():
        if col in data.columns:
            data[col] = data[col].clip(lower=lo, upper=hi)

    # ── 16. Clean up helper columns ───────────────────────────────────────────
    _drop = [c for c in data.columns if c.startswith("_")]
    data.drop(columns=_drop, inplace=True)
    data.replace([np.inf, -np.inf], np.nan, inplace=True)

    n_features = len([c for c in data.columns
                      if c not in ("symbol", "timestamp", "open", "high",
                                   "low", "close", "volume", "quote_volume",
                                   "taker_buy_quote", "trades")])
    logger.info(
        f"[features] {timeframe} | shape={data.shape} | features_computed={n_features}"
    )
    return data
