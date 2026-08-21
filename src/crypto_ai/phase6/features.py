from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.features.baseline import _ema, _rsi, _segments
from crypto_ai.phase4.asof import causal_asof_join
from crypto_ai.phase4.features import ExternalTables
from crypto_ai.phase4_1.features import (
    FEATURE_GROUPS_V2_1,
    _lag_return,
    _rolling_max,
    _rolling_mean,
    _rolling_min,
    _rolling_std,
    _safe_divide,
    _to_float,
    generate_features_v2_1,
)
from crypto_ai.phase6.config import FEATURE_RESEARCH_VERSION

FEATURE_GROUPS_V3_RESEARCH: dict[str, tuple[str, ...]] = {
    **FEATURE_GROUPS_V2_1,
    "higher_timeframe_12h": (
        "htf_12h_return",
        "htf_12h_log_return",
        "htf_12h_range_pct",
        "htf_12h_body_ratio",
        "htf_12h_upper_wick_ratio",
        "htf_12h_lower_wick_ratio",
        "htf_12h_close_location",
        "htf_12h_ema20_distance",
        "htf_12h_ema20_50_spread",
        "htf_12h_ema20_slope_3bar",
        "htf_12h_rsi14",
        "htf_12h_roc4",
        "htf_12h_realized_vol_1d",
        "htf_12h_realized_vol_3d",
        "htf_12h_realized_vol_7d",
        "htf_12h_atr14_pct",
        "htf_12h_relative_quote_volume",
        "htf_12h_volume_zscore",
        "htf_12h_trade_count_intensity",
        "htf_12h_taker_buy_share",
        "htf_12h_taker_sell_share",
        "htf_12h_taker_flow_imbalance",
    ),
    "higher_timeframe_1d": (
        "htf_1d_return",
        "htf_1d_log_return",
        "htf_1d_range_pct",
        "htf_1d_body_ratio",
        "htf_1d_upper_wick_ratio",
        "htf_1d_lower_wick_ratio",
        "htf_1d_close_location",
        "htf_1d_ema20_distance",
        "htf_1d_ema50_distance",
        "htf_1d_ema100_distance",
        "htf_1d_ema200_distance",
        "htf_1d_ema20_50_spread",
        "htf_1d_ema50_200_spread",
        "htf_1d_ema20_slope_5d",
        "htf_1d_rsi14",
        "htf_1d_roc7",
        "htf_1d_realized_vol_3d",
        "htf_1d_realized_vol_7d",
        "htf_1d_realized_vol_30d",
        "htf_1d_atr14_pct",
        "htf_1d_volatility_zscore",
        "htf_1d_volatility_of_volatility",
        "htf_1d_relative_quote_volume",
        "htf_1d_volume_zscore",
        "htf_1d_trade_count_intensity",
        "htf_1d_taker_buy_share",
        "htf_1d_taker_sell_share",
        "htf_1d_taker_flow_imbalance",
        "htf_1d_distance_from_20d_high",
        "htf_1d_distance_from_20d_low",
        "htf_1d_distance_from_60d_high",
        "htf_1d_distance_from_60d_low",
        "htf_1d_drawdown_from_60d_high",
    ),
    "cross_timeframe": (
        "trend_alignment_score",
        "trend_conflict_score",
        "short_bounce_in_daily_bear",
        "return_5m_over_daily_volatility",
        "return_1h_over_daily_volatility",
        "return_4h_over_7d_volatility",
        "atr14_over_price_context",
    ),
    "market_stress_research": (
        "stress_daily_drawdown",
        "stress_daily_volatility",
        "stress_12h_volume_shock",
        "stress_negative_taker_flow",
    ),
}

NEW_FEATURE_GROUPS = (
    "higher_timeframe_12h",
    "higher_timeframe_1d",
    "cross_timeframe",
    "market_stress_research",
)


@dataclass(frozen=True, slots=True)
class FeatureV3ResearchResult:
    values: dict[str, np.ndarray]
    columns: tuple[str, ...]
    groups: tuple[str, ...]
    valid_mask: np.ndarray
    source_time_12h_us: np.ndarray
    availability_time_12h_us: np.ndarray
    source_time_1d_us: np.ndarray
    availability_time_1d_us: np.ndarray
    diagnostics: dict[str, object]


def _higher_timeframe_values(table: pa.Table, prefix: str) -> dict[str, np.ndarray]:
    open_times = table.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    step_us = int(np.min(np.diff(open_times))) if len(open_times) > 1 else 1
    segments = _segments(open_times, step_us)
    opens, highs, lows, closes = (
        _to_float(table, name) for name in ("open", "high", "low", "close")
    )
    quote_volume = _to_float(table, "quote_volume")
    trades = _to_float(table, "trade_count")
    buy_quote = _to_float(table, "taker_buy_quote_volume")
    candle_range = highs - lows
    log_returns = np.full(len(closes), np.nan)
    log_returns[1:] = np.log(closes[1:] / closes[:-1])
    previous_close = np.roll(closes, 1)
    if len(previous_close):
        previous_close[0] = closes[0]
    true_range = np.maximum.reduce(
        [highs - lows, np.abs(highs - previous_close), np.abs(lows - previous_close)]
    )
    upper = highs - np.maximum(opens, closes)
    lower = np.minimum(opens, closes) - lows
    buy_share = _safe_divide(buy_quote, quote_volume)
    result: dict[str, np.ndarray] = {
        f"htf_{prefix}_return": _lag_return(closes, 1),
        f"htf_{prefix}_log_return": log_returns,
        f"htf_{prefix}_range_pct": _safe_divide(candle_range, opens),
        f"htf_{prefix}_body_ratio": _safe_divide(closes - opens, candle_range),
        f"htf_{prefix}_upper_wick_ratio": _safe_divide(upper, candle_range),
        f"htf_{prefix}_lower_wick_ratio": _safe_divide(lower, candle_range),
        f"htf_{prefix}_close_location": _safe_divide(closes - lows, candle_range),
    }
    ema20 = _ema(closes, 20, segments)
    ema50 = _ema(closes, 50, segments)
    result[f"htf_{prefix}_ema20_distance"] = closes / ema20 - 1.0
    result[f"htf_{prefix}_ema20_50_spread"] = ema20 / ema50 - 1.0
    result[f"htf_{prefix}_rsi14"] = _rsi(closes, 14, segments)
    result[f"htf_{prefix}_relative_quote_volume"] = _safe_divide(
        quote_volume, _rolling_mean(quote_volume, 20)
    )
    result[f"htf_{prefix}_volume_zscore"] = _safe_divide(
        quote_volume - _rolling_mean(quote_volume, 60), _rolling_std(quote_volume, 60)
    )
    result[f"htf_{prefix}_trade_count_intensity"] = _safe_divide(trades, _rolling_mean(trades, 20))
    result[f"htf_{prefix}_taker_buy_share"] = buy_share
    result[f"htf_{prefix}_taker_sell_share"] = 1.0 - buy_share
    result[f"htf_{prefix}_taker_flow_imbalance"] = 2.0 * buy_share - 1.0
    result[f"htf_{prefix}_atr14_pct"] = _safe_divide(_rolling_mean(true_range, 14), closes)
    if prefix == "12h":
        result.update(
            {
                "htf_12h_ema20_slope_3bar": _lag_return(ema20, 3),
                "htf_12h_roc4": _lag_return(closes, 4),
                "htf_12h_realized_vol_1d": _rolling_std(log_returns, 2),
                "htf_12h_realized_vol_3d": _rolling_std(log_returns, 6),
                "htf_12h_realized_vol_7d": _rolling_std(log_returns, 14),
            }
        )
    else:
        ema100, ema200 = _ema(closes, 100, segments), _ema(closes, 200, segments)
        vol30 = _rolling_std(log_returns, 30)
        high20, low20 = _rolling_max(highs, 20), _rolling_min(lows, 20)
        high60, low60 = _rolling_max(highs, 60), _rolling_min(lows, 60)
        result.update(
            {
                "htf_1d_ema50_distance": closes / ema50 - 1.0,
                "htf_1d_ema100_distance": closes / ema100 - 1.0,
                "htf_1d_ema200_distance": closes / ema200 - 1.0,
                "htf_1d_ema50_200_spread": ema50 / ema200 - 1.0,
                "htf_1d_ema20_slope_5d": _lag_return(ema20, 5),
                "htf_1d_roc7": _lag_return(closes, 7),
                "htf_1d_realized_vol_3d": _rolling_std(log_returns, 3),
                "htf_1d_realized_vol_7d": _rolling_std(log_returns, 7),
                "htf_1d_realized_vol_30d": vol30,
                "htf_1d_volatility_zscore": _safe_divide(
                    vol30 - _rolling_mean(vol30, 180), _rolling_std(vol30, 180)
                ),
                "htf_1d_volatility_of_volatility": _rolling_std(vol30, 30),
                "htf_1d_distance_from_20d_high": closes / high20 - 1.0,
                "htf_1d_distance_from_20d_low": closes / low20 - 1.0,
                "htf_1d_distance_from_60d_high": closes / high60 - 1.0,
                "htf_1d_distance_from_60d_low": closes / low60 - 1.0,
                "htf_1d_drawdown_from_60d_high": closes / high60 - 1.0,
            }
        )
    return result


def _align_higher(
    source: pa.Table,
    feature_times: np.ndarray,
    values: dict[str, np.ndarray],
    interval: str,
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    step_us = interval_milliseconds(interval) * 1_000
    source_times = source.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    availability = source_times + step_us
    aligned = causal_asof_join(feature_times, availability, values, maximum_age_us=step_us)
    safe = np.maximum(aligned.source_indices, 0)
    aligned_source = np.full(len(feature_times), -1, dtype=np.int64)
    aligned_available = np.full(len(feature_times), -1, dtype=np.int64)
    if len(source_times):
        aligned_source[aligned.available] = source_times[safe[aligned.available]]
        aligned_available[aligned.available] = availability[safe[aligned.available]]
    return aligned.values, aligned.available, aligned_source, aligned_available


def generate_features_v3_research(
    candles_5m: pa.Table,
    candles_12h: pa.Table,
    candles_1d: pa.Table,
    *,
    external: ExternalTables | None = None,
) -> FeatureV3ResearchResult:
    base = generate_features_v2_1(candles_5m, interval="5m", external=external)
    values = dict(base.values)
    open_times = candles_5m.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    feature_times = open_times + interval_milliseconds("5m") * 1_000
    raw12 = _higher_timeframe_values(candles_12h, "12h")
    raw1d = _higher_timeframe_values(candles_1d, "1d")
    aligned12, available12, source12, availability12 = _align_higher(
        candles_12h, feature_times, raw12, "12h"
    )
    aligned1d, available1d, source1d, availability1d = _align_higher(
        candles_1d, feature_times, raw1d, "1d"
    )
    values.update(aligned12)
    values.update(aligned1d)
    signs = np.column_stack(
        [
            np.sign(values["ema20_distance"]),
            np.sign(values["htf_12h_ema20_distance"]),
            np.sign(values["htf_1d_ema20_distance"]),
        ]
    )
    sign_count = np.count_nonzero(np.isfinite(signs), axis=1)
    alignment = np.divide(
        np.nansum(signs, axis=1),
        sign_count,
        out=np.full(len(signs), np.nan),
        where=sign_count > 0,
    )
    finite_min = np.min(np.where(np.isfinite(signs), signs, np.inf), axis=1)
    finite_max = np.max(np.where(np.isfinite(signs), signs, -np.inf), axis=1)
    conflict = np.where(sign_count > 0, (finite_max - finite_min) / 2.0, np.nan)
    daily_vol = values["htf_1d_realized_vol_30d"]
    vol7d = values["htf_1d_realized_vol_7d"]
    cross = {
        "trend_alignment_score": alignment,
        "trend_conflict_score": conflict,
        "short_bounce_in_daily_bear": (
            (values["return_1h"] > 0) & (values["htf_1d_ema20_distance"] < 0)
        ).astype(float),
        "return_5m_over_daily_volatility": _safe_divide(values["return_5m"], daily_vol),
        "return_1h_over_daily_volatility": _safe_divide(values["return_1h"], daily_vol),
        "return_4h_over_7d_volatility": _safe_divide(values["return_4h"], vol7d),
        "atr14_over_price_context": _safe_divide(values["atr14_pct"], values["htf_1d_atr14_pct"]),
    }
    values.update(cross)
    values.update(
        {
            "stress_daily_drawdown": -np.minimum(values["htf_1d_drawdown_from_60d_high"], 0.0),
            "stress_daily_volatility": np.maximum(values["htf_1d_volatility_zscore"], 0.0),
            "stress_12h_volume_shock": np.maximum(values["htf_12h_volume_zscore"], 0.0),
            "stress_negative_taker_flow": np.maximum(-values["htf_12h_taker_flow_imbalance"], 0.0),
        }
    )
    groups = (*base.groups, *NEW_FEATURE_GROUPS)
    columns = tuple(name for group in groups for name in FEATURE_GROUPS_V3_RESEARCH[group])
    if len(columns) != len(set(columns)):
        raise AssertionError("Phase 6 feature names must be unique")
    if any(any(token in name for token in ("future", "target", "mfe", "mae")) for name in columns):
        raise ValueError("Target-derived fields are forbidden from Phase 6 features")
    valid = base.valid_mask & available12 & available1d
    for name in columns:
        valid &= np.isfinite(values[name])
    diagnostics = dict(base.diagnostics) | {
        "feature_version": FEATURE_RESEARCH_VERSION,
        "feature_count": len(columns),
        "12h_available_rows": int(np.count_nonzero(available12)),
        "1d_available_rows": int(np.count_nonzero(available1d)),
        "valid_rows": int(np.count_nonzero(valid)),
        "completed_candle_policy": "availability_time=open_time+interval; as-of <= feature_time",
    }
    return FeatureV3ResearchResult(
        values=values,
        columns=columns,
        groups=groups,
        valid_mask=valid,
        source_time_12h_us=source12,
        availability_time_12h_us=availability12,
        source_time_1d_us=source1d,
        availability_time_1d_us=availability1d,
        diagnostics=diagnostics,
    )
