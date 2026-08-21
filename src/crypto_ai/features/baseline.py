from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.research.config import FeatureConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FeatureGenerationResult:
    values: dict[str, np.ndarray]
    valid_mask: np.ndarray
    warmup_mask: np.ndarray
    unexpected_invalid_mask: np.ndarray
    contiguous_history: np.ndarray
    feature_hash: str

    @property
    def valid_count(self) -> int:
        return int(np.count_nonzero(self.valid_mask))


def _lag_return(values: np.ndarray, lag: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    result[lag:] = values[lag:] / values[:-lag] - 1.0
    return result


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return result
    cumulative = np.concatenate(([0.0], np.cumsum(values, dtype=np.float64)))
    result[window - 1 :] = (cumulative[window:] - cumulative[:-window]) / window
    return result


def _rolling_std(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    if len(values) < window:
        return result
    windows = np.lib.stride_tricks.sliding_window_view(values, window)
    result[window - 1 :] = np.std(windows, axis=1, ddof=1)
    return result


def _segments(open_times: np.ndarray, interval_us: int) -> list[tuple[int, int]]:
    if not len(open_times):
        return []
    breaks = np.flatnonzero(np.diff(open_times) != interval_us) + 1
    starts = np.concatenate(([0], breaks))
    ends = np.concatenate((breaks, [len(open_times)]))
    return [(int(start), int(end)) for start, end in zip(starts, ends, strict=True)]


def _ema(values: np.ndarray, span: int, segments: list[tuple[int, int]]) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    alpha = 2.0 / (span + 1.0)
    for start, end in segments:
        if end - start < span:
            continue
        seed_index = start + span - 1
        result[seed_index] = float(np.mean(values[start : seed_index + 1]))
        for index in range(seed_index + 1, end):
            result[index] = alpha * values[index] + (1.0 - alpha) * result[index - 1]
    return result


def _rsi(values: np.ndarray, period: int, segments: list[tuple[int, int]]) -> np.ndarray:
    result = np.full(len(values), np.nan, dtype=np.float64)
    for start, end in segments:
        if end - start <= period:
            continue
        deltas = np.diff(values[start:end])
        gains = np.maximum(deltas, 0.0)
        losses = np.maximum(-deltas, 0.0)
        average_gain = float(np.mean(gains[:period]))
        average_loss = float(np.mean(losses[:period]))
        index = start + period
        result[index] = _rsi_value(average_gain, average_loss)
        for offset in range(period, len(deltas)):
            average_gain = ((period - 1) * average_gain + gains[offset]) / period
            average_loss = ((period - 1) * average_loss + losses[offset]) / period
            index = start + offset + 1
            result[index] = _rsi_value(average_gain, average_loss)
    return result


def _rsi_value(average_gain: float, average_loss: float) -> float:
    if average_loss == 0.0:
        return 50.0 if average_gain == 0.0 else 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def generate_baseline_features(
    candles: pa.Table,
    *,
    interval: str,
    config: FeatureConfig,
) -> FeatureGenerationResult:
    started = time.perf_counter()
    logger.info(
        "Feature generation started",
        extra={
            "event": "feature_generation_started",
            "feature_version": config.version,
            "rows": candles.num_rows,
        },
    )
    interval_us = interval_milliseconds(interval) * 1_000
    open_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    opens = np.asarray(candles.column("open").combine_chunks().to_pylist(), dtype=np.float64)
    highs = np.asarray(candles.column("high").combine_chunks().to_pylist(), dtype=np.float64)
    lows = np.asarray(candles.column("low").combine_chunks().to_pylist(), dtype=np.float64)
    closes = np.asarray(candles.column("close").combine_chunks().to_pylist(), dtype=np.float64)
    volumes = np.asarray(
        candles.column("base_volume").combine_chunks().to_pylist(), dtype=np.float64
    )

    history = np.ones(len(open_times), dtype=np.int64)
    for index in range(1, len(open_times)):
        if open_times[index] - open_times[index - 1] == interval_us:
            history[index] = history[index - 1] + 1
    segments = _segments(open_times, interval_us)

    return_5m = _lag_return(closes, 1)
    log_return_5m = np.full(len(closes), np.nan, dtype=np.float64)
    log_return_5m[1:] = np.log(closes[1:] / closes[:-1])
    relative_mean = _rolling_mean(volumes, config.relative_volume_window)
    relative_volume = volumes / relative_mean
    volatility_1h = _rolling_std(log_return_5m[1:], config.volatility_1h_window)
    rolling_volatility_1h = np.full(len(closes), np.nan, dtype=np.float64)
    rolling_volatility_1h[1:] = volatility_1h
    volatility_4h = _rolling_std(log_return_5m[1:], config.volatility_4h_window)
    rolling_volatility_4h = np.full(len(closes), np.nan, dtype=np.float64)
    rolling_volatility_4h[1:] = volatility_4h
    ema20 = _ema(closes, config.ema_fast_span, segments)
    ema50 = _ema(closes, config.ema_slow_span, segments)

    values = {
        "return_5m": return_5m,
        "return_15m": _lag_return(closes, 3),
        "return_30m": _lag_return(closes, 6),
        "return_1h": _lag_return(closes, 12),
        "log_return_5m": log_return_5m,
        "candle_range_pct": (highs - lows) / opens,
        "candle_body_pct": (closes - opens) / opens,
        "relative_volume": relative_volume,
        "rolling_volatility_1h": rolling_volatility_1h,
        "rolling_volatility_4h": rolling_volatility_4h,
        "ema20_distance": closes / ema20 - 1.0,
        "ema50_distance": closes / ema50 - 1.0,
        "rsi14": _rsi(closes, config.rsi_period, segments),
    }
    selected = np.column_stack([values[name] for name in config.columns])
    finite = np.all(np.isfinite(selected), axis=1)
    minimum_history = config.minimum_history_rows
    warmup = history < minimum_history
    unexpected = ~finite & ~warmup
    valid = finite & ~warmup

    logger.info(
        "Feature generation completed",
        extra={
            "event": "feature_generation_complete",
            "feature_version": config.version,
            "rows": candles.num_rows,
            "valid_rows": int(np.count_nonzero(valid)),
            "warmup_rows": int(np.count_nonzero(warmup)),
            "unexpected_invalid_rows": int(np.count_nonzero(unexpected)),
            "duration_seconds": time.perf_counter() - started,
        },
    )
    return FeatureGenerationResult(
        values={name: values[name] for name in config.columns},
        valid_mask=valid,
        warmup_mask=warmup,
        unexpected_invalid_mask=unexpected,
        contiguous_history=history,
        feature_hash=config.config_hash,
    )
