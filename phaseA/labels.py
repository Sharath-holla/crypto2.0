"""
Triple Barrier Method — Label Generator

For each bar at time t (entry at close[t]):
  Upper barrier : entry × (1 + upper_mult × atr_ratio[t])
  Lower barrier : entry × (1 − lower_mult × atr_ratio[t])
  Time  barrier : t + time_bars candles

Label:
   1  if close crosses upper barrier first   → long winner
  -1  if close crosses lower barrier first   → short winner  
   0  if time barrier expires first          → timeout / neutral

Label mapping for LightGBM (requires 0-indexed integers):
  -1 → 0  (short)
   0 → 1  (hold)
   1 → 2  (long)

The asymmetric barriers (upper_mult > lower_mult) reflect crypto's tendency to
trend upward, and the fact that downside moves tend to be sharp and fast.
"""

import logging
import numpy as np
import pandas as pd
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# Try to use Numba for ~50x speedup on the inner loop.
# Falls back to pure NumPy if Numba is not installed.
try:
    from numba import njit
    _NUMBA_AVAILABLE = True
except ImportError:
    logger.warning("Numba not installed. Triple barrier labeling will use pure NumPy (slower).")
    _NUMBA_AVAILABLE = False
    def njit(fn):          # no-op decorator
        return fn


@njit
def _triple_barrier_core(
    close: np.ndarray,
    atr_ratio: np.ndarray,
    upper_mult: float,
    lower_mult: float,
    time_bars: int,
) -> np.ndarray:
    """
    Numba-JIT inner loop. Iterates over every bar and scans the look-forward
    window to determine which barrier is hit first.

    Returns int8 array:
      1  = upper hit first
     -1  = lower hit first
      0  = timeout
    127  = sentinel (last `time_bars` rows where labels cannot be computed)
    """
    n = len(close)
    labels = np.zeros(n, dtype=np.int8)

    for i in range(n - time_bars):
        entry  = close[i]
        atr_r  = atr_ratio[i]

        if atr_r <= 0.0 or np.isnan(atr_r):
            labels[i] = 127   # cannot compute barrier — will be dropped
            continue

        upper = entry * (1.0 + upper_mult * atr_r)
        lower = entry * (1.0 - lower_mult * atr_r)

        label = 0
        for j in range(i + 1, i + time_bars + 1):
            c = close[j]
            if c >= upper:
                label = 1
                break
            if c <= lower:
                label = -1
                break

        labels[i] = label

    # Mark trailing rows that have no complete look-forward window
    for i in range(n - time_bars, n):
        labels[i] = 127

    return labels


def generate_labels(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """
    Apply triple barrier labeling to a multi-symbol dataframe.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: symbol, timestamp, close, atr_ratio
    timeframe : str
        Used to look up barrier parameters from config.

    Returns
    -------
    pd.DataFrame
        Input df with two new columns:
          label        : raw label  (-1, 0, 1)
          label_mapped : LightGBM-ready (0, 1, 2)
        Rows where labels could not be computed are dropped.
    """
    from pipeline.config_signal import BARRIER   # local import to avoid circular dependency
    cfg        = BARRIER[timeframe]
    upper_mult = float(cfg["upper_mult"])
    lower_mult = float(cfg["lower_mult"])
    time_bars  = int(cfg["time_bars"])

    results = []
    label_counts = {1: 0, 0: 0, -1: 0}

    for symbol, grp in df.groupby("symbol", sort=False):
        grp = grp.sort_values("timestamp").copy().reset_index(drop=True)

        close     = grp["close"].values.astype(np.float64)
        atr_ratio = (
            grp["atr_ratio"]
            .ffill()
            .bfill()
            .values.astype(np.float64) 
        )

        raw = _triple_barrier_core(close, atr_ratio, upper_mult, lower_mult, time_bars)

        grp["label"] = raw
        # Drop rows where barrier could not be computed (sentinel or bad atr)
        grp = grp[(grp["label"] != 127)].copy()

        for v in [-1, 0, 1]:
            label_counts[v] += (grp["label"] == v).sum()

        results.append(grp)

    if not results:
        raise ValueError(f"No labeled data produced for timeframe={timeframe}")

    out = pd.concat(results).reset_index(drop=True)

    # Map to 0-indexed integers for LightGBM
    out["label_mapped"] = out["label"].map({-1: 0, 0: 1, 1: 2}).astype(np.int8)

    total = sum(label_counts.values())
    dist_str = " | ".join(
        f"{name}={label_counts[v]} ({100*label_counts[v]/total:.1f}%)"
        for v, name in [(1, "long"), (0, "hold"), (-1, "short")]
    )
    logger.info(f"[labels] {timeframe} | total={total} | {dist_str}")

    return out


def compute_forward_returns(df: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """
    Utility: compute simple forward return (close[t+n] / close[t] - 1) per symbol.
    Useful for regression targets or post-hoc analysis.
    Not used in main pipeline but helpful for diagnostics.
    """
    def _fwd(x):
        return x.shift(-horizon_bars) / x - 1
    return df.groupby("symbol")["close"].transform(_fwd)
