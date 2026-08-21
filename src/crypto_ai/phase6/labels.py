from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.phase6.config import LABEL_RESEARCH_VERSION

HORIZON_STEPS: Final[dict[str, int]] = {
    "15m": 3,
    "30m": 6,
    "1h": 12,
    "2h": 24,
    "4h": 48,
}
BARRIER_PAIRS: Final[dict[str, tuple[float, float]]] = {
    "symmetric_1_0_atr": (1.0, 1.0),
    "reward_1_5_risk_1_0_atr": (1.5, 1.0),
}
BARRIER_TIMEOUT = 0
BARRIER_TP = 1
BARRIER_SL = -1
BARRIER_AMBIGUOUS = 2
BARRIER_UNAVAILABLE = -128


@dataclass(frozen=True, slots=True)
class ResearchLabelResult:
    feature_time_us: np.ndarray
    entry_time_us: np.ndarray
    values: dict[str, np.ndarray]
    valid: dict[str, np.ndarray]
    label_end_time_us: dict[str, np.ndarray]
    entry_indices: np.ndarray
    barrier_resolution: dict[str, dict[str, int]]
    reason_counts: dict[str, dict[str, int]]


def _consecutive_forward(open_times: np.ndarray, interval_us: int) -> np.ndarray:
    result = np.zeros(len(open_times), dtype=np.int64)
    for index in range(len(open_times) - 2, -1, -1):
        if open_times[index + 1] - open_times[index] == interval_us:
            result[index] = result[index + 1] + 1
    return result


def _resolve_ambiguous_with_1m(
    outcome: np.ndarray,
    ambiguous_rows: np.ndarray,
    coarse_open_times: np.ndarray,
    entry: np.ndarray,
    upper: np.ndarray,
    lower: np.ndarray,
    minute_candles: pa.Table | None,
) -> tuple[int, int]:
    if minute_candles is None or not len(ambiguous_rows):
        return 0, int(len(ambiguous_rows))
    minute_times = minute_candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    minute_high = np.asarray(
        minute_candles.column("high").combine_chunks().to_pylist(), dtype=np.float64
    )
    minute_low = np.asarray(
        minute_candles.column("low").combine_chunks().to_pylist(), dtype=np.float64
    )
    minute_step = interval_milliseconds("1m") * 1_000
    resolved = 0
    still_ambiguous = 0
    for row in ambiguous_rows:
        coarse_time = int(coarse_open_times[row])
        left = int(np.searchsorted(minute_times, coarse_time, side="left"))
        right = int(np.searchsorted(minute_times, coarse_time + 5 * minute_step, side="left"))
        if right - left != 5 or np.any(np.diff(minute_times[left:right]) != minute_step):
            still_ambiguous += 1
            continue
        tp = np.flatnonzero(minute_high[left:right] >= entry[row] * (1.0 + upper[row]))
        sl = np.flatnonzero(minute_low[left:right] <= entry[row] * (1.0 - lower[row]))
        if not len(tp) or not len(sl):
            still_ambiguous += 1
        elif int(tp[0]) < int(sl[0]):
            outcome[row] = BARRIER_TP
            resolved += 1
        elif int(sl[0]) < int(tp[0]):
            outcome[row] = BARRIER_SL
            resolved += 1
        else:
            still_ambiguous += 1
    return resolved, still_ambiguous


def generate_research_labels(
    candles: pa.Table,
    *,
    atr_pct: np.ndarray,
    minute_candles: pa.Table | None = None,
) -> ResearchLabelResult:
    """Generate gap-safe research targets from the next 5m open.

    MFE and MAE are evaluation labels only.  Barrier outcomes use 5m bars and
    consult validated 1m overlap only when both barriers occur in one 5m bar.
    """

    interval_us = interval_milliseconds("5m") * 1_000
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    opens = np.asarray(candles.column("open").combine_chunks().to_pylist(), dtype=np.float64)
    highs = np.asarray(candles.column("high").combine_chunks().to_pylist(), dtype=np.float64)
    lows = np.asarray(candles.column("low").combine_chunks().to_pylist(), dtype=np.float64)
    atr_pct = np.asarray(atr_pct, dtype=np.float64)
    if atr_pct.shape != opens.shape:
        raise ValueError("ATR scale must align with decision candles")
    n_rows = len(opens)
    feature_time = open_times + interval_us
    entry_indices = np.arange(n_rows, dtype=np.int64) + 1
    entry_indices[-1:] = -1
    entry_time = np.full(n_rows, -1, dtype=np.int64)
    entry_time[:-1] = open_times[1:]
    consecutive = _consecutive_forward(open_times, interval_us)
    values: dict[str, np.ndarray] = {}
    valid: dict[str, np.ndarray] = {}
    ends: dict[str, np.ndarray] = {}
    reasons: dict[str, dict[str, int]] = {}
    windows: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}

    for horizon, steps in HORIZON_STEPS.items():
        target_offset = 1 + steps
        target_indices = np.arange(n_rows, dtype=np.int64) + target_offset
        mask = (target_indices < n_rows) & (consecutive >= target_offset)
        target_safe = np.minimum(target_indices, n_rows - 1)
        returns = np.full(n_rows, np.nan)
        returns[mask] = opens[target_safe[mask]] / opens[entry_indices[mask]] - 1.0
        label_end = np.full(n_rows, -1, dtype=np.int64)
        label_end[mask] = open_times[target_safe[mask]]

        favorable = np.full(n_rows, np.nan)
        adverse = np.full(n_rows, np.nan)
        short_favorable = np.full(n_rows, np.nan)
        short_adverse = np.full(n_rows, np.nan)
        count = max(0, n_rows - steps)
        if count:
            high_windows = np.lib.stride_tricks.sliding_window_view(highs[1:], steps)
            low_windows = np.lib.stride_tricks.sliding_window_view(lows[1:], steps)
            entry_price = opens[1 : count + 1]
            favorable[:count] = np.maximum(np.max(high_windows, axis=1) / entry_price - 1.0, 0.0)
            adverse[:count] = np.maximum(1.0 - np.min(low_windows, axis=1) / entry_price, 0.0)
            short_favorable[:count] = adverse[:count]
            short_adverse[:count] = favorable[:count]
            windows[horizon] = (high_windows, low_windows, entry_price)
        for name, data in (
            (f"forward_return_{horizon}", returns),
            (f"mfe_long_{horizon}", favorable),
            (f"mae_long_{horizon}", adverse),
            (f"mfe_short_{horizon}", short_favorable),
            (f"mae_short_{horizon}", short_adverse),
        ):
            values[name] = data
            valid[name] = mask & np.isfinite(data)
            ends[name] = label_end.copy()
        reasons[horizon] = {
            "valid": int(np.count_nonzero(mask)),
            "insufficient_future": int(np.count_nonzero(target_indices >= n_rows)),
            "gap_crossing_invalidated": int(
                np.count_nonzero((target_indices < n_rows) & (consecutive < target_offset))
            ),
        }

    barrier_resolution: dict[str, dict[str, int]] = {}
    horizon = "1h"
    steps = HORIZON_STEPS[horizon]
    base_valid = valid[f"forward_return_{horizon}"].copy()
    high_windows, low_windows, entry_prices = windows[horizon]
    count = len(high_windows)
    for pair_name, (up_multiple, down_multiple) in BARRIER_PAIRS.items():
        scale = atr_pct * 1.0
        upper = scale * up_multiple
        lower = scale * down_multiple
        outcome = np.full(n_rows, BARRIER_UNAVAILABLE, dtype=np.int16)
        outcome[base_valid] = BARRIER_TIMEOUT
        for row in np.flatnonzero(base_valid & np.isfinite(scale) & (scale > 0)):
            if row >= count:
                continue
            tp = np.flatnonzero(high_windows[row] >= entry_prices[row] * (1.0 + upper[row]))
            sl = np.flatnonzero(low_windows[row] <= entry_prices[row] * (1.0 - lower[row]))
            if len(tp) and len(sl):
                if int(tp[0]) < int(sl[0]):
                    outcome[row] = BARRIER_TP
                elif int(sl[0]) < int(tp[0]):
                    outcome[row] = BARRIER_SL
                else:
                    outcome[row] = BARRIER_AMBIGUOUS
            elif len(tp):
                outcome[row] = BARRIER_TP
            elif len(sl):
                outcome[row] = BARRIER_SL
        ambiguous = np.flatnonzero(outcome == BARRIER_AMBIGUOUS)
        resolved, unresolved = _resolve_ambiguous_with_1m(
            outcome,
            ambiguous,
            open_times + interval_us,
            np.where(np.arange(n_rows) < count, np.pad(entry_prices, (0, n_rows - count)), np.nan),
            upper,
            lower,
            minute_candles,
        )
        name = f"tp_before_sl_{pair_name}_1h"
        values[name] = outcome.astype(np.float64)
        valid[name] = base_valid & (outcome != BARRIER_UNAVAILABLE)
        ends[name] = ends[f"forward_return_{horizon}"].copy()
        barrier_resolution[name] = {
            "tp": int(np.count_nonzero(outcome == BARRIER_TP)),
            "sl": int(np.count_nonzero(outcome == BARRIER_SL)),
            "timeout": int(np.count_nonzero(outcome == BARRIER_TIMEOUT)),
            "ambiguous": int(np.count_nonzero(outcome == BARRIER_AMBIGUOUS)),
            "resolved_with_1m": resolved,
            "still_ambiguous_or_no_1m": unresolved,
        }

    if any(name in values for name in ("mfe", "mae")):
        raise AssertionError("label names are expected to be explicit")
    return ResearchLabelResult(
        feature_time_us=feature_time,
        entry_time_us=entry_time,
        values=values,
        valid=valid,
        label_end_time_us=ends,
        entry_indices=entry_indices,
        barrier_resolution=barrier_resolution,
        reason_counts=reasons | {"label_version": {"value": LABEL_RESEARCH_VERSION}},
    )
