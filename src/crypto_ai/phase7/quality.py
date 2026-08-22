from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pyarrow as pa

from crypto_ai.domain import interval_milliseconds
from crypto_ai.phase7.registry import CoverageSummary, SymbolRegistry
from crypto_ai.phase7.universe import SymbolDescriptor


def _times(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


def _floats(table: pa.Table, name: str) -> np.ndarray:
    return np.asarray(table.column(name).combine_chunks().to_pylist(), dtype=np.float64)


def assess_symbol_quality(
    candles: pa.Table,
    *,
    interval: str,
    expected_start: datetime,
    expected_end: datetime,
) -> CoverageSummary:
    if (
        expected_start.tzinfo is None
        or expected_end.tzinfo is None
        or expected_start >= expected_end
    ):
        raise ValueError("quality range must be timezone-aware and non-empty")
    step_us = interval_milliseconds(interval) * 1_000
    start_us = int(expected_start.astimezone(UTC).timestamp() * 1_000_000)
    end_us = int(expected_end.astimezone(UTC).timestamp() * 1_000_000)
    times = _times(candles, "open_time")
    in_range = (times >= start_us) & (times < end_us)
    times = times[in_range]
    unique = np.unique(times)
    duplicate_count = len(times) - len(unique)
    expected_rows = max(0, (end_us - start_us + step_us - 1) // step_us)
    gap_count = max(0, int(expected_rows) - len(unique))
    opens = _floats(candles, "open")[in_range]
    highs = _floats(candles, "high")[in_range]
    lows = _floats(candles, "low")[in_range]
    closes = _floats(candles, "close")[in_range]
    volume_name = "quote_volume" if "quote_volume" in candles.column_names else "base_volume"
    volumes = _floats(candles, volume_name)[in_range]
    finite = (
        np.isfinite(opens)
        & np.isfinite(highs)
        & np.isfinite(lows)
        & np.isfinite(closes)
        & np.isfinite(volumes)
    )
    valid_ohlc = (
        (opens > 0)
        & (highs >= np.maximum(opens, closes))
        & (lows <= np.minimum(opens, closes))
        & (lows > 0)
        & (volumes >= 0)
    )
    invalid = int(np.count_nonzero(~(finite & valid_ohlc)))
    warnings: list[str] = []
    if gap_count:
        warnings.append("missing_candles_not_filled")
    if np.count_nonzero(volumes == 0):
        warnings.append("zero_volume_candles_present")
    return CoverageSummary(
        first_timestamp=(
            datetime.fromtimestamp(int(np.min(unique)) / 1_000_000, tz=UTC) if len(unique) else None
        ),
        last_timestamp=(
            datetime.fromtimestamp(int(np.max(unique)) / 1_000_000, tz=UTC) if len(unique) else None
        ),
        expected_rows=int(expected_rows),
        actual_rows=len(unique),
        coverage_ratio=(len(unique) / expected_rows if expected_rows else None),
        gap_count=gap_count,
        duplicate_count=duplicate_count,
        invalid_count=invalid,
        zero_volume_count=int(np.count_nonzero(volumes == 0)),
        warnings=tuple(warnings),
    )


def _return_mapping(table: pa.Table, symbol: str, before_us: int) -> dict[int, float]:
    symbols = np.asarray(table.column("symbol").combine_chunks().to_pylist(), dtype=object)
    times = _times(table, "open_time")
    closes = _floats(table, "close")
    rows = np.flatnonzero((symbols == symbol) & (times < before_us))
    rows = rows[np.argsort(times[rows], kind="mergesort")]
    result: dict[int, float] = {}
    for previous, current in zip(rows, rows[1:], strict=False):
        if closes[previous] > 0:
            result[int(times[current])] = float(closes[current] / closes[previous] - 1.0)
    return result


def build_point_in_time_descriptors(
    daily_candles: pa.Table,
    registry: SymbolRegistry,
    *,
    as_of: datetime,
    lookback_days: int,
) -> list[SymbolDescriptor]:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("descriptor as_of must be timezone-aware")
    cutoff = as_of.astimezone(UTC)
    cutoff_us = int(cutoff.timestamp() * 1_000_000)
    start = cutoff - timedelta(days=lookback_days)
    start_us = int(start.timestamp() * 1_000_000)
    symbols = np.asarray(daily_candles.column("symbol").combine_chunks().to_pylist(), dtype=object)
    times = _times(daily_candles, "open_time")
    quote_volume = _floats(daily_candles, "quote_volume")
    trade_count = _floats(daily_candles, "trade_count")
    closes = _floats(daily_candles, "close")
    funding = (
        _floats(daily_candles, "funding_rate")
        if "funding_rate" in daily_candles.column_names
        else np.full(daily_candles.num_rows, np.nan)
    )
    btc_returns = _return_mapping(daily_candles, "BTCUSDT", cutoff_us)
    descriptors: list[SymbolDescriptor] = []
    registry_map = registry.by_symbol()
    for symbol in sorted(set(symbols.tolist())):
        record = registry_map.get(str(symbol))
        if record is None or not record.exists_at(cutoff - timedelta(microseconds=1)):
            continue
        rows = np.flatnonzero((symbols == symbol) & (times >= start_us) & (times < cutoff_us))
        rows = rows[np.argsort(times[rows], kind="mergesort")]
        if len(rows) < 2:
            continue
        returns = closes[rows][1:] / closes[rows][:-1] - 1.0
        paired = [
            (float(returns[index - 1]), btc_returns[int(times[rows[index]])])
            for index in range(1, len(rows))
            if int(times[rows[index]]) in btc_returns
        ]
        if len(paired) >= 2:
            left = np.asarray([item[0] for item in paired])
            right = np.asarray([item[1] for item in paired])
            variance = float(np.var(right, ddof=1))
            beta = float(np.cov(left, right, ddof=1)[0, 1] / variance) if variance > 0 else None
            correlation = (
                float(np.corrcoef(left, right)[0, 1])
                if np.ptp(left) > 0 and np.ptp(right) > 0
                else None
            )
        else:
            beta = correlation = None
        expected = max(1, lookback_days)
        observed_times = np.unique(times[rows])
        gap_count = max(0, expected - len(observed_times))
        descriptors.append(
            SymbolDescriptor(
                symbol=str(symbol),
                as_of=cutoff,
                source_max_time=datetime.fromtimestamp(
                    int(np.max(times[rows])) / 1_000_000, tz=UTC
                ),
                trailing_quote_volume=float(np.median(quote_volume[rows])),
                realized_volatility=float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0,
                trade_intensity=float(np.median(trade_count[rows])),
                funding_variability=(
                    float(np.nanstd(funding[rows], ddof=1))
                    if np.count_nonzero(np.isfinite(funding[rows])) > 1
                    else None
                ),
                btc_beta=beta,
                btc_correlation=correlation,
                history_days=(cutoff - record.available_from).total_seconds() / 86_400,
                coverage_ratio=min(1.0, len(observed_times) / expected),
                gap_count=gap_count,
                duplicate_count=len(rows) - len(observed_times),
                invalid_count=0,
                warnings=("daily_discovery_gaps" if gap_count else "",),
            )
        )
    return [
        item.model_copy(update={"warnings": tuple(value for value in item.warnings if value)})
        for item in descriptors
    ]
