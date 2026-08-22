from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
import pyarrow as pa

from crypto_ai.phase6.labels import generate_research_labels
from crypto_ai.phase7.config import TARGET_VERSION, TargetConfig


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


def generate_multiasset_targets(
    candles: pa.Table,
    feature_table: pa.Table,
    *,
    config: TargetConfig,
    research_cutoff: datetime,
) -> MultiAssetTargetResult:
    """Generate raw and ex-ante volatility-normalized targets by symbol.

    The normalization scale is read from the feature row at prediction time.
    No future volatility observation is accepted by this interface.
    """

    required_candles = {"symbol", "open_time", "open", "high", "low"}
    required_features = {"symbol", "feature_time", "daily_volatility", "atr14_pct"}
    if not required_candles.issubset(candles.column_names):
        raise ValueError("target candles are missing symbol/open_time/OHLC")
    if not required_features.issubset(feature_table.column_names):
        raise ValueError("targets require causal daily_volatility and atr14_pct feature columns")
    feature_symbols = feature_table.column("symbol").combine_chunks().to_pylist()
    feature_times = _times(feature_table, "feature_time")
    feature_scale = _floats(feature_table, "daily_volatility")
    feature_atr = _floats(feature_table, "atr14_pct")
    scale_by_key = {
        (str(symbol), int(timestamp)): (float(scale), float(atr))
        for symbol, timestamp, scale, atr in zip(
            feature_symbols, feature_times, feature_scale, feature_atr, strict=True
        )
    }
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
        feature_time_values = source_times + 5 * 60_000_000
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
            mfe = labels.values[f"mfe_long_{label}"]
            mae = labels.values[f"mae_long_{label}"]
            valid_indices = np.flatnonzero(valid)
            for index in valid_indices:
                feature_time = int(labels.feature_time_us[index])
                scale = scale_by_key.get((str(symbol), feature_time), (np.nan, np.nan))[0]
                normalized = (
                    float(raw[index]) / max(abs(float(scale)), config.normalization_floor)
                    if np.isfinite(scale)
                    else np.nan
                )
                rows.append(
                    {
                        "symbol": str(symbol),
                        "feature_time": datetime.fromtimestamp(feature_time / 1_000_000, tz=UTC),
                        "entry_time": datetime.fromtimestamp(
                            int(labels.entry_time_us[index]) / 1_000_000, tz=UTC
                        ),
                        "label_end_time": datetime.fromtimestamp(
                            int(labels.label_end_time_us[value_name][index]) / 1_000_000,
                            tz=UTC,
                        ),
                        "horizon_minutes": horizon_minutes,
                        "raw_future_return": float(raw[index]),
                        "ex_ante_volatility_scale": float(scale) if np.isfinite(scale) else None,
                        "normalized_future_return": normalized if np.isfinite(normalized) else None,
                        "mfe_long": float(mfe[index]),
                        "mae_long": float(mae[index]),
                        "mfe_short": float(labels.values[f"mfe_short_{label}"][index]),
                        "mae_short": float(labels.values[f"mae_short_{label}"][index]),
                        "target_version": TARGET_VERSION,
                    }
                )
            reasons[f"{symbol}:{label}"] = dict(labels.reason_counts[label]) | {
                "cutoff_excluded": int(
                    np.count_nonzero(
                        labels.valid[value_name] & (labels.label_end_time_us[value_name] >= cutoff)
                    )
                )
            }
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
        target_version=TARGET_VERSION,
        horizons_minutes=config.horizons_minutes,
        reason_counts=reasons,
    )
