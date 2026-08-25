from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pyarrow as pa

from crypto_ai.phase6.labels import generate_research_labels
from crypto_ai.phase7.config import TARGET_VERSION, TargetConfig

TARGET_V1 = "multiasset_targets_v1"
FIVE_MINUTES_US = 5 * 60_000_000


@dataclass(frozen=True, slots=True)
class MultiAssetTargetResult:
    table: pa.Table
    target_version: str
    horizons_minutes: tuple[int, ...]
    reason_counts: dict[str, dict[str, int]]


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def _cutoff_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("target cutoff must be timezone-aware")
    return int(value.astimezone(UTC).timestamp() * 1_000_000)


def _validate_inputs(candles: pa.Table, feature_table: pa.Table) -> None:
    required_candles = {"symbol", "open_time", "open", "high", "low"}
    required_features = {"symbol", "feature_time", "daily_volatility", "atr14_pct"}
    if not required_candles.issubset(candles.column_names):
        raise ValueError("target candles are missing symbol/open_time/OHLC")
    if not required_features.issubset(feature_table.column_names):
        raise ValueError("targets require causal daily_volatility and atr14_pct feature columns")


def _scale_lookup(feature_table: pa.Table) -> dict[tuple[str, int], tuple[float, float]]:
    return {
        (str(symbol), int(timestamp)): (float(scale), float(atr))
        for symbol, timestamp, scale, atr in zip(
            feature_table.column("symbol").combine_chunks().to_pylist(),
            _times(feature_table, "feature_time"),
            _floats(feature_table, "daily_volatility"),
            _floats(feature_table, "atr14_pct"),
            strict=True,
        )
    }


def _consecutive_forward(open_times: np.ndarray) -> np.ndarray:
    consecutive = np.zeros(len(open_times), dtype=np.int64)
    for index in range(len(open_times) - 2, -1, -1):
        if int(open_times[index + 1]) - int(open_times[index]) == FIVE_MINUTES_US:
            consecutive[index] = consecutive[index + 1] + 1
    return consecutive


def _finish(
    rows: list[dict[str, object]],
    *,
    target_version: str,
    config: TargetConfig,
    reasons: dict[str, dict[str, int]],
    cutoff: int,
) -> MultiAssetTargetResult:
    table = pa.Table.from_pylist(rows).sort_by(
        [("feature_time", "ascending"), ("symbol", "ascending"), ("horizon_minutes", "ascending")]
    )
    keys = list(
        zip(
            table.column("symbol").to_pylist(),
            _times(table, "feature_time").tolist(),
            table.column("horizon_minutes").to_pylist(),
            strict=True,
        )
    )
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate multi-asset target primary key")
    if table.num_rows and int(np.max(_times(table, "label_end_time"))) >= cutoff:
        raise AssertionError("Phase 7 target crossed the research cutoff")
    return MultiAssetTargetResult(
        table=table,
        target_version=target_version,
        horizons_minutes=config.horizons_minutes,
        reason_counts=reasons,
    )


def _target_row(
    *,
    symbol: str,
    feature_time: int,
    entry_time: int,
    label_end_time: int,
    horizon_minutes: int,
    raw: float,
    scale: float,
    normalized: float,
    mfe_long: float,
    mae_long: float,
    mfe_short: float,
    mae_short: float,
    target_version: str,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "feature_time": datetime.fromtimestamp(feature_time / 1_000_000, tz=UTC),
        "entry_time": datetime.fromtimestamp(entry_time / 1_000_000, tz=UTC),
        "label_end_time": datetime.fromtimestamp(label_end_time / 1_000_000, tz=UTC),
        "horizon_minutes": horizon_minutes,
        "raw_future_return": raw,
        "ex_ante_volatility_scale": scale if np.isfinite(scale) else None,
        "normalized_future_return": normalized if np.isfinite(normalized) else None,
        "mfe_long": mfe_long,
        "mae_long": mae_long,
        "mfe_short": mfe_short,
        "mae_short": mae_short,
        "target_version": target_version,
    }


def generate_multiasset_targets_v1(
    candles: pa.Table,
    feature_table: pa.Table,
    *,
    config: TargetConfig,
    research_cutoff: datetime,
) -> MultiAssetTargetResult:
    """Reproduce the superseded same-boundary Phase 7 target for audit only."""

    _validate_inputs(candles, feature_table)
    scale_by_key = _scale_lookup(feature_table)
    cutoff = _cutoff_us(research_cutoff)
    rows: list[dict[str, object]] = []
    reasons: dict[str, dict[str, int]] = {}
    candle_symbols = np.asarray(candles.column("symbol").combine_chunks().to_pylist(), dtype=object)
    for symbol in sorted(set(candle_symbols.tolist())):
        selected = np.flatnonzero(candle_symbols == symbol)
        source = candles.take(pa.array(selected, type=pa.int64())).sort_by(
            [("open_time", "ascending")]
        )
        source_times = _times(source, "open_time")
        feature_time_values = source_times + FIVE_MINUTES_US
        atr_scale = np.asarray(
            [
                scale_by_key.get((str(symbol), int(timestamp)), (np.nan, np.nan))[1]
                for timestamp in feature_time_values
            ]
        )
        labels = generate_research_labels(source, atr_pct=atr_scale)
        for horizon_minutes in config.horizons_minutes:
            label = (
                f"{horizon_minutes // 60}h" if horizon_minutes % 60 == 0 else f"{horizon_minutes}m"
            )
            value_name = f"forward_return_{label}"
            if value_name not in labels.values:
                raise ValueError(f"Phase 6 label engine does not support {horizon_minutes}m")
            valid = labels.valid[value_name] & (labels.label_end_time_us[value_name] < cutoff)
            raw = labels.values[value_name]
            for index in np.flatnonzero(valid):
                feature_time = int(labels.feature_time_us[index])
                scale = scale_by_key.get((str(symbol), feature_time), (np.nan, np.nan))[0]
                normalized = (
                    float(raw[index]) / max(abs(float(scale)), config.normalization_floor)
                    if np.isfinite(scale)
                    else np.nan
                )
                rows.append(
                    _target_row(
                        symbol=str(symbol),
                        feature_time=feature_time,
                        entry_time=int(labels.entry_time_us[index]),
                        label_end_time=int(labels.label_end_time_us[value_name][index]),
                        horizon_minutes=horizon_minutes,
                        raw=float(raw[index]),
                        scale=float(scale),
                        normalized=float(normalized),
                        mfe_long=float(labels.values[f"mfe_long_{label}"][index]),
                        mae_long=float(labels.values[f"mae_long_{label}"][index]),
                        mfe_short=float(labels.values[f"mfe_short_{label}"][index]),
                        mae_short=float(labels.values[f"mae_short_{label}"][index]),
                        target_version=TARGET_V1,
                    )
                )
            reasons[f"{symbol}:{label}"] = dict(labels.reason_counts[label]) | {
                "cutoff_excluded": int(
                    np.count_nonzero(
                        labels.valid[value_name] & (labels.label_end_time_us[value_name] >= cutoff)
                    )
                )
            }
    return _finish(
        rows,
        target_version=TARGET_V1,
        config=config,
        reasons=reasons,
        cutoff=cutoff,
    )


def generate_multiasset_targets(
    candles: pa.Table,
    feature_table: pa.Table,
    *,
    config: TargetConfig,
    research_cutoff: datetime,
) -> MultiAssetTargetResult:
    """Generate Phase 7 v2 targets with one complete decision-latency bar.

    Features stamped at a 5m candle close become known at ``feature_time``. The
    simulated entry is the following bar's open, strictly five minutes later.
    The older same-boundary construction remains available through
    :func:`generate_multiasset_targets_v1` solely for reproducibility.
    """

    _validate_inputs(candles, feature_table)
    scale_by_key = _scale_lookup(feature_table)
    cutoff = _cutoff_us(research_cutoff)
    rows: list[dict[str, object]] = []
    reasons: dict[str, dict[str, int]] = {}
    candle_symbols = np.asarray(candles.column("symbol").combine_chunks().to_pylist(), dtype=object)
    entry_offset = 1 + config.decision_latency_bars

    for symbol in sorted(set(candle_symbols.tolist())):
        selected = np.flatnonzero(candle_symbols == symbol)
        source = candles.take(pa.array(selected, type=pa.int64())).sort_by(
            [("open_time", "ascending")]
        )
        open_times = _times(source, "open_time")
        opens = _floats(source, "open")
        highs = _floats(source, "high")
        lows = _floats(source, "low")
        consecutive = _consecutive_forward(open_times)
        row_indices = np.arange(len(open_times), dtype=np.int64)

        for horizon_minutes in config.horizons_minutes:
            steps = horizon_minutes // 5
            target_offset = entry_offset + steps
            target_indices = row_indices + target_offset
            has_endpoint = target_indices < len(open_times)
            gap_safe = has_endpoint & (consecutive >= target_offset)
            safe_targets = np.minimum(target_indices, max(len(open_times) - 1, 0))
            label_end = np.full(len(open_times), -1, dtype=np.int64)
            if len(open_times):
                label_end[gap_safe] = open_times[safe_targets[gap_safe]]
            before_cutoff = gap_safe & (label_end < cutoff)
            count = max(0, len(open_times) - target_offset)

            mfe_long = np.full(len(open_times), np.nan)
            mae_long = np.full(len(open_times), np.nan)
            if count:
                high_windows = np.lib.stride_tricks.sliding_window_view(
                    highs[entry_offset:], steps
                )[:count]
                low_windows = np.lib.stride_tricks.sliding_window_view(lows[entry_offset:], steps)[
                    :count
                ]
                entry_prices = opens[entry_offset : entry_offset + count]
                mfe_long[:count] = np.maximum(
                    np.max(high_windows, axis=1) / entry_prices - 1.0, 0.0
                )
                mae_long[:count] = np.maximum(1.0 - np.min(low_windows, axis=1) / entry_prices, 0.0)

            for index in np.flatnonzero(before_cutoff):
                feature_time = int(open_times[index] + FIVE_MINUTES_US)
                entry_index = int(index + entry_offset)
                target_index = int(target_indices[index])
                entry_price = float(opens[entry_index])
                raw = float(opens[target_index] / entry_price - 1.0)
                scale = scale_by_key.get((str(symbol), feature_time), (np.nan, np.nan))[0]
                normalized = (
                    raw / max(abs(float(scale)), config.normalization_floor)
                    if np.isfinite(scale)
                    else np.nan
                )
                rows.append(
                    _target_row(
                        symbol=str(symbol),
                        feature_time=feature_time,
                        entry_time=int(open_times[entry_index]),
                        label_end_time=int(open_times[target_index]),
                        horizon_minutes=horizon_minutes,
                        raw=raw,
                        scale=float(scale),
                        normalized=float(normalized),
                        mfe_long=float(mfe_long[index]),
                        mae_long=float(mae_long[index]),
                        mfe_short=float(mae_long[index]),
                        mae_short=float(mfe_long[index]),
                        target_version=TARGET_VERSION,
                    )
                )
            label = (
                f"{horizon_minutes // 60}h" if horizon_minutes % 60 == 0 else f"{horizon_minutes}m"
            )
            reasons[f"{symbol}:{label}"] = {
                "valid": int(np.count_nonzero(before_cutoff)),
                "insufficient_future": int(np.count_nonzero(~has_endpoint)),
                "gap_crossing_invalidated": int(np.count_nonzero(has_endpoint & ~gap_safe)),
                "cutoff_excluded": int(np.count_nonzero(gap_safe & ~before_cutoff)),
            }

    result = _finish(
        rows,
        target_version=TARGET_VERSION,
        config=config,
        reasons=reasons,
        cutoff=cutoff,
    )
    if result.table.num_rows:
        feature_times = _times(result.table, "feature_time")
        entry_times = _times(result.table, "entry_time")
        horizons_us = (
            np.asarray(result.table.column("horizon_minutes").to_pylist(), dtype=np.int64)
            * 60_000_000
        )
        label_ends = _times(result.table, "label_end_time")
        if not np.all(entry_times == feature_times + FIVE_MINUTES_US):
            raise AssertionError("Phase 7 v2 entry must be one complete 5m bar after feature time")
        if not np.all(label_ends == entry_times + horizons_us):
            raise AssertionError("Phase 7 v2 horizon must be measured from simulated entry")
    return result
