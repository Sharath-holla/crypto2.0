from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.features.baseline import _ema, _rsi, _segments
from crypto_ai.phase4.asof import causal_asof_join
from crypto_ai.phase4.features import ExternalTables

FEATURE_V2_1_VERSION = "2.1.0"
MINIMUM_HISTORY_ROWS = 2_016  # seven days at 5m

FEATURE_GROUPS_V2_1: dict[str, tuple[str, ...]] = {
    "price": (
        "return_5m",
        "return_15m",
        "return_30m",
        "return_1h",
        "return_2h",
        "return_4h",
        "log_return_5m",
        "candle_range_pct",
        "candle_body_pct",
        "wick_balance_pct",
    ),
    "trend": (
        "ema20_distance",
        "ema50_distance",
        "ema100_distance",
        "ema20_50_spread",
        "ema20_slope_1h",
        "ema50_slope_1h",
    ),
    "momentum": ("rsi14", "stochastic_k14", "positive_return_share_1h"),
    "volatility": (
        "realized_volatility_30m",
        "realized_volatility_1h",
        "realized_volatility_4h",
        "realized_volatility_1d",
        "atr14_pct",
        "range_volatility_1h",
        "volatility_ratio_1h_1d",
    ),
    "volume": (
        "log_quote_volume",
        "relative_base_volume",
        "relative_quote_volume",
        "relative_trade_count",
        "average_trade_quote",
        "base_volume_change_1h",
    ),
    "taker_flow": (
        "taker_buy_base_share",
        "taker_sell_base_share",
        "taker_buy_quote_share",
        "taker_sell_quote_share",
        "taker_flow_imbalance_base",
        "taker_flow_imbalance_quote",
        "taker_flow_imbalance_15m",
        "taker_flow_imbalance_1h",
        "taker_buy_share_change_1h",
        "taker_flow_price_alignment_1h",
    ),
    "regime": (
        "trend_score_4h",
        "volatility_zscore_7d",
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    ),
    "time": ("hour_sin", "hour_cos", "weekend_flag"),
    "funding": ("funding_rate", "funding_change_8h", "funding_age_hours"),
    "mark_index_basis": (
        "contract_mark_basis",
        "mark_index_basis",
        "mark_index_basis_change_1h",
        "mark_index_basis_zscore_7d",
        "mark_return_1h",
        "index_return_1h",
    ),
    "open_interest": (
        "open_interest_log_change_5m",
        "open_interest_change_1h",
        "open_interest_age_minutes",
    ),
}

CORE_GROUPS_V2_1 = (
    "price",
    "trend",
    "momentum",
    "volatility",
    "volume",
    "taker_flow",
    "regime",
    "time",
)


@dataclass(frozen=True, slots=True)
class FeatureV2_1Result:
    values: dict[str, np.ndarray]
    columns: tuple[str, ...]
    groups: tuple[str, ...]
    valid_mask: np.ndarray
    group_available: dict[str, np.ndarray]
    diagnostics: dict[str, object]


def _to_float(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _lag_return(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) > lag:
        numerator = values[lag:]
        denominator = values[:-lag]
        target = result[lag:]
        valid = np.isfinite(numerator) & np.isfinite(denominator) & (denominator != 0)
        target[valid] = numerator[valid] / denominator[valid] - 1.0
    return result


def _lag_difference(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) > lag:
        result[lag:] = values[lag:] - values[:-lag]
    return result


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) < window:
        return result
    finite = np.isfinite(values)
    cleaned = np.where(finite, values, 0.0)
    sums = np.concatenate(([0.0], np.cumsum(cleaned, dtype=np.float64)))
    counts = np.concatenate(([0], np.cumsum(finite, dtype=np.int64)))
    window_sums = sums[window:] - sums[:-window]
    window_counts = counts[window:] - counts[:-window]
    target = result[window - 1 :]
    valid = window_counts == window
    target[valid] = window_sums[valid] / window
    return result


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) < window or window < 2:
        return result
    finite = np.isfinite(values)
    cleaned = np.where(finite, values, 0.0)
    sums = np.concatenate(([0.0], np.cumsum(cleaned, dtype=np.float64)))
    squares = np.concatenate(([0.0], np.cumsum(cleaned * cleaned, dtype=np.float64)))
    counts = np.concatenate(([0], np.cumsum(finite, dtype=np.int64)))
    window_sums = sums[window:] - sums[:-window]
    window_squares = squares[window:] - squares[:-window]
    window_counts = counts[window:] - counts[:-window]
    variance = (window_squares - window_sums * window_sums / window) / (window - 1)
    target = result[window - 1 :]
    valid = window_counts == window
    target[valid] = np.sqrt(np.maximum(variance[valid], 0.0))
    return result


def _rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) >= window:
        result[window - 1 :] = np.min(
            np.lib.stride_tricks.sliding_window_view(values, window), axis=1
        )
    return result


def _rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) >= window:
        result[window - 1 :] = np.max(
            np.lib.stride_tricks.sliding_window_view(values, window), axis=1
        )
    return result


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    return np.divide(
        numerator,
        denominator,
        out=np.full(len(numerator), np.nan),
        where=np.isfinite(denominator) & (denominator > 0),
    )


def _align(
    table: pa.Table,
    feature_times: np.ndarray,
    names: tuple[str, ...],
    maximum_age: timedelta,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    availability = table.column("availability_time").combine_chunks().cast(pa.int64()).to_numpy()
    result = causal_asof_join(
        feature_times,
        availability,
        {name: _to_float(table, name) for name in names},
        maximum_age_us=int(maximum_age.total_seconds() * 1_000_000),
    )
    return result.values, result.available, result.age_us


def _mean_duration(flags: np.ndarray, valid: np.ndarray) -> float:
    selected = flags & valid
    if not np.any(selected):
        return 0.0
    starts = selected & ~np.concatenate(([False], selected[:-1]))
    return float(np.count_nonzero(selected) / np.count_nonzero(starts))


def generate_features_v2_1(
    candles: pa.Table,
    *,
    interval: str,
    external: ExternalTables | None = None,
) -> FeatureV2_1Result:
    if interval != "5m":
        raise ValueError("Feature V2.1 is leakage-reviewed for the 5m interval")
    external = external or ExternalTables()
    interval_us = interval_milliseconds(interval) * 1_000
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    feature_times = open_times + interval_us
    segments = _segments(open_times, interval_us)
    history = np.ones(len(open_times), dtype=np.int64)
    for index in range(1, len(open_times)):
        if open_times[index] - open_times[index - 1] == interval_us:
            history[index] = history[index - 1] + 1

    opens, highs, lows, closes = (
        _to_float(candles, name) for name in ("open", "high", "low", "close")
    )
    base_volume = _to_float(candles, "base_volume")
    quote_volume = _to_float(candles, "quote_volume")
    trades = _to_float(candles, "trade_count")
    buy_base = _to_float(candles, "taker_buy_base_volume")
    buy_quote = _to_float(candles, "taker_buy_quote_volume")
    if np.any(buy_base < 0) or np.any(buy_quote < 0):
        raise ValueError("Taker-buy volume cannot be negative")
    if np.any(buy_base > base_volume) or np.any(buy_quote > quote_volume):
        raise ValueError("Taker-buy volume cannot exceed total volume")
    sell_base = base_volume - buy_base
    sell_quote = quote_volume - buy_quote
    if np.any(sell_base < 0) or np.any(sell_quote < 0):
        raise ValueError("Derived taker-sell volume cannot be negative")

    return_5m = _lag_return(closes, 1)
    return_4h = _lag_return(closes, 48)
    log_returns = np.full(len(closes), np.nan)
    log_returns[1:] = np.log(closes[1:] / closes[:-1])
    ema20 = _ema(closes, 20, segments)
    ema50 = _ema(closes, 50, segments)
    ema100 = _ema(closes, 100, segments)
    low14, high14 = _rolling_min(lows, 14), _rolling_max(highs, 14)
    range14 = high14 - low14
    previous_close = np.roll(closes, 1)
    previous_close[0] = closes[0]
    true_range = np.maximum.reduce(
        [highs - lows, np.abs(highs - previous_close), np.abs(lows - previous_close)]
    )
    candle_range = _safe_divide(highs - lows, opens)
    buy_base_share = _safe_divide(buy_base, base_volume)
    sell_base_share = _safe_divide(sell_base, base_volume)
    buy_quote_share = _safe_divide(buy_quote, quote_volume)
    sell_quote_share = _safe_divide(sell_quote, quote_volume)
    imbalance_base = _safe_divide(buy_base - sell_base, buy_base + sell_base)
    imbalance_quote = _safe_divide(buy_quote - sell_quote, buy_quote + sell_quote)
    vol1h = _rolling_std(log_returns, 12)
    vol1d = _rolling_std(log_returns, 288)
    vol7d_mean = _rolling_mean(vol1d, MINIMUM_HISTORY_ROWS)
    vol7d_std = _rolling_std(vol1d, MINIMUM_HISTORY_ROWS)
    vol_z = _safe_divide(vol1d - vol7d_mean, vol7d_std)
    trend_threshold = np.maximum(0.002, _rolling_mean(np.abs(return_4h), MINIMUM_HISTORY_ROWS))

    values: dict[str, np.ndarray] = {
        "return_5m": return_5m,
        "return_15m": _lag_return(closes, 3),
        "return_30m": _lag_return(closes, 6),
        "return_1h": _lag_return(closes, 12),
        "return_2h": _lag_return(closes, 24),
        "return_4h": return_4h,
        "log_return_5m": log_returns,
        "candle_range_pct": candle_range,
        "candle_body_pct": _safe_divide(closes - opens, opens),
        "wick_balance_pct": _safe_divide(
            (highs - np.maximum(opens, closes)) - (np.minimum(opens, closes) - lows), opens
        ),
        "ema20_distance": closes / ema20 - 1.0,
        "ema50_distance": closes / ema50 - 1.0,
        "ema100_distance": closes / ema100 - 1.0,
        "ema20_50_spread": ema20 / ema50 - 1.0,
        "ema20_slope_1h": _lag_return(ema20, 12),
        "ema50_slope_1h": _lag_return(ema50, 12),
        "rsi14": _rsi(closes, 14, segments),
        "stochastic_k14": _safe_divide(closes - low14, range14),
        "positive_return_share_1h": _rolling_mean((return_5m > 0).astype(float), 12),
        "realized_volatility_30m": _rolling_std(log_returns, 6),
        "realized_volatility_1h": vol1h,
        "realized_volatility_4h": _rolling_std(log_returns, 48),
        "realized_volatility_1d": vol1d,
        "atr14_pct": _safe_divide(_rolling_mean(true_range, 14), closes),
        "range_volatility_1h": _rolling_std(candle_range, 12),
        "volatility_ratio_1h_1d": _safe_divide(vol1h, vol1d),
        "log_quote_volume": np.log1p(quote_volume),
        "relative_base_volume": _safe_divide(base_volume, _rolling_mean(base_volume, 12)),
        "relative_quote_volume": _safe_divide(quote_volume, _rolling_mean(quote_volume, 12)),
        "relative_trade_count": _safe_divide(trades, _rolling_mean(trades, 12)),
        "average_trade_quote": _safe_divide(quote_volume, trades),
        "base_volume_change_1h": _lag_return(base_volume, 12),
        "taker_buy_base_share": buy_base_share,
        "taker_sell_base_share": sell_base_share,
        "taker_buy_quote_share": buy_quote_share,
        "taker_sell_quote_share": sell_quote_share,
        "taker_flow_imbalance_base": imbalance_base,
        "taker_flow_imbalance_quote": imbalance_quote,
        "taker_flow_imbalance_15m": _rolling_mean(imbalance_base, 3),
        "taker_flow_imbalance_1h": _rolling_mean(imbalance_base, 12),
        "taker_buy_share_change_1h": _lag_difference(buy_base_share, 12),
        "taker_flow_price_alignment_1h": _rolling_mean(
            imbalance_base * np.sign(np.nan_to_num(return_5m)), 12
        ),
        "trend_score_4h": _safe_divide(return_4h, trend_threshold),
        "volatility_zscore_7d": vol_z,
        "bull_regime": (return_4h > trend_threshold).astype(float),
        "bear_regime": (return_4h < -trend_threshold).astype(float),
        "sideways_regime": (np.abs(return_4h) <= trend_threshold).astype(float),
        "high_volatility_regime": (vol_z > 1.0).astype(float),
        "low_volatility_regime": (vol_z < -0.5).astype(float),
    }
    close_times = candles.column("close_time").combine_chunks().to_pylist()
    hours = np.asarray([item.hour + item.minute / 60.0 for item in close_times])
    values.update(
        {
            "hour_sin": np.sin(2 * np.pi * hours / 24.0),
            "hour_cos": np.cos(2 * np.pi * hours / 24.0),
            "weekend_flag": np.asarray([item.weekday() >= 5 for item in close_times], dtype=float),
        }
    )

    groups = list(CORE_GROUPS_V2_1)
    availability = {group: np.ones(len(candles), dtype=bool) for group in CORE_GROUPS_V2_1}
    diagnostics: dict[str, object] = {
        "taker_flow_semantics": "candle-level aggressive/taker flow; not order-book depth",
        "zero_base_volume_rows": int(np.count_nonzero(base_volume == 0)),
        "zero_quote_volume_rows": int(np.count_nonzero(quote_volume == 0)),
        "zero_trade_count_rows": int(np.count_nonzero(trades == 0)),
    }

    if external.funding is not None:
        aligned, available, age = _align(
            external.funding, feature_times, ("funding_rate",), timedelta(hours=12)
        )
        funding = aligned["funding_rate"]
        values.update(
            {
                "funding_rate": funding,
                "funding_change_8h": _lag_difference(funding, 96),
                "funding_age_hours": age.astype(float) / 3_600_000_000,
            }
        )
        availability["funding"] = available
        groups.append("funding")
        diagnostics["funding_coverage"] = float(np.mean(available))

    if external.mark is not None and external.index is not None:
        mark, mark_available, _ = _align(
            external.mark, feature_times, ("close",), timedelta(minutes=6)
        )
        index, index_available, _ = _align(
            external.index, feature_times, ("close",), timedelta(minutes=6)
        )
        available = mark_available & index_available
        mark_close, index_close = mark["close"], index["close"]
        mark_index = mark_close / index_close - 1.0
        basis_mean = _rolling_mean(mark_index, MINIMUM_HISTORY_ROWS)
        basis_std = _rolling_std(mark_index, MINIMUM_HISTORY_ROWS)
        values.update(
            {
                "contract_mark_basis": closes / mark_close - 1.0,
                "mark_index_basis": mark_index,
                "mark_index_basis_change_1h": _lag_difference(mark_index, 12),
                "mark_index_basis_zscore_7d": _safe_divide(mark_index - basis_mean, basis_std),
                "mark_return_1h": _lag_return(mark_close, 12),
                "index_return_1h": _lag_return(index_close, 12),
            }
        )
        availability["mark_index_basis"] = available
        groups.append("mark_index_basis")
        diagnostics["mark_index_coverage"] = float(np.mean(available))

    if external.open_interest is not None:
        aligned, available, age = _align(
            external.open_interest,
            feature_times,
            ("sum_open_interest",),
            timedelta(minutes=10),
        )
        open_interest = aligned["sum_open_interest"]
        values.update(
            {
                "open_interest_log_change_5m": _lag_difference(np.log(open_interest), 1),
                "open_interest_change_1h": _lag_return(open_interest, 12),
                "open_interest_age_minutes": age.astype(float) / 60_000_000,
            }
        )
        availability["open_interest"] = available
        groups.append("open_interest")
        diagnostics["open_interest_coverage"] = float(np.mean(available))

    columns = tuple(name for group in groups for name in FEATURE_GROUPS_V2_1[group])
    matrix = np.column_stack([values[name] for name in columns])
    valid = np.all(np.isfinite(matrix), axis=1) & (history >= MINIMUM_HISTORY_ROWS)
    for group in groups:
        valid &= availability[group]
    regime_names = (
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
        "low_volatility_regime",
    )
    diagnostics.update(
        {
            "feature_count": len(columns),
            "valid_rows": int(np.count_nonzero(valid)),
            "invalid_rows": int(len(valid) - np.count_nonzero(valid)),
            "minimum_contiguous_history_rows": MINIMUM_HISTORY_ROWS,
            "regime_distribution": {
                name: {
                    "rows": int(np.count_nonzero((values[name] > 0) & valid)),
                    "share": float(np.mean(values[name][valid] > 0)) if np.any(valid) else 0.0,
                    "average_contiguous_duration_rows": _mean_duration(values[name] > 0, valid),
                }
                for name in regime_names
            },
        }
    )
    return FeatureV2_1Result(
        values=values,
        columns=columns,
        groups=tuple(groups),
        valid_mask=valid,
        group_available=availability,
        diagnostics=diagnostics,
    )
