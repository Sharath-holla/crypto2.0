from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.features.baseline import _ema, _rsi, _segments
from crypto_ai.phase4.asof import causal_asof_join

FEATURE_V2_VERSION = "2.0.0"

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "price": (
        "return_5m",
        "return_15m",
        "return_30m",
        "return_1h",
        "return_4h",
        "log_return_5m",
        "candle_range_pct",
        "candle_body_pct",
        "upper_wick_pct",
        "lower_wick_pct",
    ),
    "trend": (
        "ema20_distance",
        "ema50_distance",
        "ema100_distance",
        "ema20_50_spread",
        "ema20_slope_1h",
        "ema50_slope_1h",
        "sma48_distance",
    ),
    "momentum": (
        "rsi14",
        "stochastic_k14",
        "return_acceleration",
        "positive_return_share_1h",
    ),
    "volatility": (
        "rolling_volatility_1h",
        "rolling_volatility_4h",
        "atr14_pct",
        "range_volatility_1h",
        "volatility_ratio_1h_4h",
    ),
    "volume": (
        "relative_volume",
        "relative_quote_volume",
        "relative_trade_count",
        "average_trade_quote",
        "base_volume_change_1h",
    ),
    "pressure": (
        "taker_buy_base_share",
        "taker_buy_quote_share",
        "taker_sell_quote_share",
        "taker_imbalance_base",
        "taker_imbalance_quote",
        "taker_imbalance_quote_1h",
        "pressure_price_alignment_1h",
    ),
    "funding": ("funding_rate", "funding_change_8h", "funding_age_hours"),
    "basis": (
        "contract_mark_basis",
        "mark_index_basis",
        "mark_index_basis_change_1h",
        "mark_index_basis_zscore_1d",
    ),
    "open_interest": (
        "open_interest_log_change_5m",
        "open_interest_change_1h",
        "open_interest_age_minutes",
    ),
    "regime": (
        "trend_score_4h",
        "volatility_zscore_1d",
        "bull_regime",
        "bear_regime",
        "sideways_regime",
        "high_volatility_regime",
    ),
    "time": ("hour_sin", "hour_cos", "weekend_flag"),
}

CORE_GROUPS = (
    "price",
    "trend",
    "momentum",
    "volatility",
    "volume",
    "pressure",
    "regime",
    "time",
)


@dataclass(frozen=True, slots=True)
class ExternalTables:
    funding: pa.Table | None = None
    mark: pa.Table | None = None
    index: pa.Table | None = None
    open_interest: pa.Table | None = None


@dataclass(frozen=True, slots=True)
class FeatureV2Result:
    values: dict[str, np.ndarray]
    columns: tuple[str, ...]
    groups: tuple[str, ...]
    valid_mask: np.ndarray
    group_available: dict[str, np.ndarray]
    diagnostics: dict[str, object]


def _lag_return(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    result[lag:] = values[lag:] / values[:-lag] - 1.0
    return result


def _lag_difference(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    result[lag:] = values[lag:] - values[:-lag]
    return result


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) < window:
        return result
    windows = np.lib.stride_tricks.sliding_window_view(values, window)
    finite = np.all(np.isfinite(windows), axis=1)
    output = result[window - 1 :]
    output[finite] = np.mean(windows[finite], axis=1)
    return result


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan)
    if len(values) < window:
        return result
    windows = np.lib.stride_tricks.sliding_window_view(values, window)
    finite = np.all(np.isfinite(windows), axis=1)
    output = result[window - 1 :]
    output[finite] = np.std(windows[finite], axis=1, ddof=1)
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


def _to_float(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _align(
    table: pa.Table,
    feature_times: np.ndarray,
    names: tuple[str, ...],
    maximum_age: timedelta,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    available = table.column("availability_time").combine_chunks().cast(pa.int64()).to_numpy()
    result = causal_asof_join(
        feature_times,
        available,
        {name: _to_float(table, name) for name in names},
        maximum_age_us=int(maximum_age.total_seconds() * 1_000_000),
    )
    return result.values, result.available, result.age_us


def generate_features_v2(
    candles: pa.Table,
    *,
    interval: str,
    external: ExternalTables | None = None,
) -> FeatureV2Result:
    if interval != "5m":
        raise ValueError("Feature V2 is leakage-reviewed for the 5m interval")
    external = external or ExternalTables()
    interval_us = interval_milliseconds(interval) * 1_000
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    feature_times = open_times + interval_us
    segments = _segments(open_times, interval_us)
    continuous_history = np.ones(len(open_times), dtype=np.int64)
    for index in range(1, len(open_times)):
        if open_times[index] - open_times[index - 1] == interval_us:
            continuous_history[index] = continuous_history[index - 1] + 1
    opens, highs, lows, closes = (
        _to_float(candles, name) for name in ("open", "high", "low", "close")
    )
    base_volume = _to_float(candles, "base_volume")
    quote_volume = _to_float(candles, "quote_volume")
    trades = _to_float(candles, "trade_count")
    buy_base = _to_float(candles, "taker_buy_base_volume")
    buy_quote = _to_float(candles, "taker_buy_quote_volume")
    sell_base, sell_quote = base_volume - buy_base, quote_volume - buy_quote
    if np.any(sell_base < 0) or np.any(sell_quote < 0):
        raise ValueError("Taker-buy volume cannot exceed total volume")
    if np.any(base_volume <= 0) or np.any(quote_volume <= 0) or np.any(trades <= 0):
        raise ValueError("Feature V2 requires positive volume and trade counts")

    log_returns = np.full(len(closes), np.nan)
    log_returns[1:] = np.log(closes[1:] / closes[:-1])
    ema20 = _ema(closes, 20, segments)
    ema50 = _ema(closes, 50, segments)
    ema100 = _ema(closes, 100, segments)
    sma48 = _rolling_mean(closes, 48)
    range_pct = (highs - lows) / opens
    body_pct = (closes - opens) / opens
    vol1h = np.full(len(closes), np.nan)
    vol4h = np.full(len(closes), np.nan)
    vol1h[1:] = _rolling_std(log_returns[1:], 12)
    vol4h[1:] = _rolling_std(log_returns[1:], 48)
    previous_close = np.roll(closes, 1)
    previous_close[0] = closes[0]
    true_range = np.maximum.reduce(
        [highs - lows, np.abs(highs - previous_close), np.abs(lows - previous_close)]
    )
    low14, high14 = _rolling_min(lows, 14), _rolling_max(highs, 14)
    stochastic_denominator = high14 - low14
    stochastic = np.divide(
        closes - low14,
        stochastic_denominator,
        out=np.full(len(closes), np.nan),
        where=stochastic_denominator > 0,
    )
    return_5m = _lag_return(closes, 1)
    return_4h = _lag_return(closes, 48)
    pressure_quote = (buy_quote - sell_quote) / quote_volume
    pressure_base = (buy_base - sell_base) / base_volume
    trailing_vol_mean = _rolling_mean(vol4h, 288)
    trailing_vol_std = _rolling_std(vol4h, 288)
    vol_z = np.divide(
        vol4h - trailing_vol_mean,
        trailing_vol_std,
        out=np.full(len(closes), np.nan),
        where=trailing_vol_std > 0,
    )

    values: dict[str, np.ndarray] = {
        "return_5m": return_5m,
        "return_15m": _lag_return(closes, 3),
        "return_30m": _lag_return(closes, 6),
        "return_1h": _lag_return(closes, 12),
        "return_4h": return_4h,
        "log_return_5m": log_returns,
        "candle_range_pct": range_pct,
        "candle_body_pct": body_pct,
        "upper_wick_pct": (highs - np.maximum(opens, closes)) / opens,
        "lower_wick_pct": (np.minimum(opens, closes) - lows) / opens,
        "ema20_distance": closes / ema20 - 1.0,
        "ema50_distance": closes / ema50 - 1.0,
        "ema100_distance": closes / ema100 - 1.0,
        "ema20_50_spread": ema20 / ema50 - 1.0,
        "ema20_slope_1h": _lag_return(ema20, 12),
        "ema50_slope_1h": _lag_return(ema50, 12),
        "sma48_distance": closes / sma48 - 1.0,
        "rsi14": _rsi(closes, 14, segments),
        "stochastic_k14": stochastic,
        "return_acceleration": return_5m - np.roll(return_5m, 1),
        "positive_return_share_1h": _rolling_mean((return_5m > 0).astype(float), 12),
        "rolling_volatility_1h": vol1h,
        "rolling_volatility_4h": vol4h,
        "atr14_pct": _rolling_mean(true_range, 14) / closes,
        "range_volatility_1h": _rolling_std(range_pct, 12),
        "volatility_ratio_1h_4h": vol1h / vol4h,
        "relative_volume": base_volume / _rolling_mean(base_volume, 12),
        "relative_quote_volume": quote_volume / _rolling_mean(quote_volume, 12),
        "relative_trade_count": trades / _rolling_mean(trades, 12),
        "average_trade_quote": quote_volume / trades,
        "base_volume_change_1h": _lag_return(base_volume, 12),
        "taker_buy_base_share": buy_base / base_volume,
        "taker_buy_quote_share": buy_quote / quote_volume,
        "taker_sell_quote_share": sell_quote / quote_volume,
        "taker_imbalance_base": pressure_base,
        "taker_imbalance_quote": pressure_quote,
        "taker_imbalance_quote_1h": _rolling_mean(pressure_quote, 12),
        "pressure_price_alignment_1h": _rolling_mean(
            pressure_quote * np.sign(np.nan_to_num(return_5m)), 12
        ),
        "trend_score_4h": return_4h,
        "volatility_zscore_1d": vol_z,
        "bull_regime": (return_4h > 0.002).astype(float),
        "bear_regime": (return_4h < -0.002).astype(float),
        "sideways_regime": (np.abs(return_4h) <= 0.002).astype(float),
        "high_volatility_regime": (vol_z > 0.5).astype(float),
    }
    values["return_acceleration"][0] = np.nan
    timestamps = candles.column("close_time").combine_chunks().to_pylist()
    hours = np.asarray([item.hour + item.minute / 60.0 for item in timestamps])
    values.update(
        {
            "hour_sin": np.sin(2 * np.pi * hours / 24.0),
            "hour_cos": np.cos(2 * np.pi * hours / 24.0),
            "weekend_flag": np.asarray([item.weekday() >= 5 for item in timestamps], dtype=float),
        }
    )

    groups = list(CORE_GROUPS)
    availability: dict[str, np.ndarray] = {
        name: np.ones(len(candles), dtype=bool) for name in CORE_GROUPS
    }
    diagnostics: dict[str, object] = {}

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
        contract_mark = closes / mark["close"] - 1.0
        mark_index = mark["close"] / index["close"] - 1.0
        basis_mean = _rolling_mean(mark_index, 288)
        basis_std = _rolling_std(mark_index, 288)
        values.update(
            {
                "contract_mark_basis": contract_mark,
                "mark_index_basis": mark_index,
                "mark_index_basis_change_1h": _lag_difference(mark_index, 12),
                "mark_index_basis_zscore_1d": np.divide(
                    mark_index - basis_mean,
                    basis_std,
                    out=np.full(len(closes), np.nan),
                    where=basis_std > 0,
                ),
            }
        )
        availability["basis"] = available
        groups.append("basis")
        diagnostics["basis_coverage"] = float(np.mean(available))

    if external.open_interest is not None:
        aligned, available, age = _align(
            external.open_interest,
            feature_times,
            ("sum_open_interest",),
            timedelta(minutes=10),
        )
        oi = aligned["sum_open_interest"]
        log_oi = np.log(oi)
        values.update(
            {
                "open_interest_log_change_5m": _lag_difference(log_oi, 1),
                "open_interest_change_1h": _lag_return(oi, 12),
                "open_interest_age_minutes": age.astype(float) / 60_000_000,
            }
        )
        availability["open_interest"] = available
        groups.append("open_interest")
        diagnostics["open_interest_coverage"] = float(np.mean(available))

    columns = tuple(name for group in groups for name in FEATURE_GROUPS[group])
    matrix = np.column_stack([values[name] for name in columns])
    valid = np.all(np.isfinite(matrix), axis=1) & (continuous_history >= 336)
    for group in groups:
        valid &= availability[group]
    diagnostics.update(
        {
            "feature_count": len(columns),
            "valid_rows": int(np.count_nonzero(valid)),
            "invalid_rows": int(len(valid) - np.count_nonzero(valid)),
            "minimum_contiguous_history_rows": 336,
            "regime_distribution": {
                name: float(np.mean(values[name][valid])) if np.any(valid) else 0.0
                for name in (
                    "bull_regime",
                    "bear_regime",
                    "sideways_regime",
                    "high_volatility_regime",
                )
            },
        }
    )
    return FeatureV2Result(
        values=values,
        columns=columns,
        groups=tuple(groups),
        valid_mask=valid,
        group_available=availability,
        diagnostics=diagnostics,
    )
