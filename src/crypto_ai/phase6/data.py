from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.data.schema import candle_schema
from crypto_ai.domain import interval_milliseconds
from crypto_ai.research.config import DatasetBuildConfig
from crypto_ai.research.gold import _load_silver

RECONCILIATION_FIELDS = (
    "open",
    "high",
    "low",
    "close",
    "base_volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
)


def load_silver_family(
    manifests: tuple[Path, ...],
    *,
    symbol: str,
    interval: str,
    end: datetime,
    start: datetime | None = None,
) -> tuple[pa.Table, list[dict[str, Any]]]:
    tables: list[pa.Table] = []
    lineage: list[dict[str, Any]] = []
    for path in manifests:
        table, manifest, files = _load_silver(
            DatasetBuildConfig(
                silver_manifest=path,
                symbol=symbol,
                interval=interval,
                start_time=start,
                end_time=end,
            )
        )
        tables.append(table)
        lineage.append(
            {
                "manifest": str(path.resolve()),
                "silver_dataset_version": manifest["silver_dataset_version"],
                "quality_status": manifest["quality_status"],
                "file_count": len(files),
                "row_count": table.num_rows,
            }
        )
    combined = pa.concat_tables(tables).sort_by([("open_time", "ascending")])
    times = combined.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    if len(times) and np.any(np.diff(times) <= 0):
        raise ValueError(f"{interval} Silver family overlaps or contains duplicates")
    cutoff_us = int(end.astimezone(UTC).timestamp() * 1_000_000)
    if len(times) and int(times[-1]) >= cutoff_us:
        raise ValueError("Silver family crossed the Phase 6 research cutoff")
    return combined, lineage


def coverage_report(table: pa.Table, interval: str) -> dict[str, Any]:
    step_us = interval_milliseconds(interval) * 1_000
    times = table.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    if not len(times):
        raise ValueError("coverage report requires rows")
    expected = int((int(times[-1]) - int(times[0])) // step_us + 1)
    unique = len(np.unique(times))
    missing = max(0, expected - unique)
    invalid = int(np.count_nonzero(np.diff(times) % step_us != 0))
    return {
        "interval": interval,
        "expected_rows": expected,
        "available_rows": table.num_rows,
        "missing_rows": missing,
        "gaps": invalid if invalid else missing,
        "duplicate_rows": table.num_rows - unique,
        "coverage_percentage": 100.0 * unique / expected,
        "first_timestamp": table.column("open_time")[0].as_py().isoformat(),
        "last_timestamp": table.column("open_time")[-1].as_py().isoformat(),
    }


def aggregate_candles(candles: pa.Table, target_interval: str) -> pa.Table:
    """Causally aggregate only complete UTC-aligned lower-timeframe groups."""

    source_times = candles.column("open_time").combine_chunks().cast(pa.int64()).to_numpy()
    if len(source_times) < 2:
        return pa.Table.from_pylist([], schema=candle_schema())
    source_step = int(np.min(np.diff(source_times)))
    target_step = interval_milliseconds(target_interval) * 1_000
    if target_step % source_step:
        raise ValueError("target interval must be an exact multiple of source interval")
    expected_rows = target_step // source_step
    buckets = source_times // target_step
    boundaries = np.concatenate(([0], np.flatnonzero(np.diff(buckets)) + 1, [len(buckets)]))
    values = candles.to_pydict()
    rows: list[dict[str, Any]] = []
    for left, right in zip(boundaries[:-1], boundaries[1:], strict=True):
        if right - left != expected_rows:
            continue
        times = source_times[left:right]
        bucket_open = int(buckets[left] * target_step)
        if (
            int(times[0]) != bucket_open
            or int(times[-1]) != bucket_open + target_step - source_step
        ):
            continue
        if np.any(np.diff(times) != source_step):
            continue
        rows.append(
            {
                "symbol": values["symbol"][left],
                "open_time": datetime.fromtimestamp(bucket_open / 1_000_000, tz=UTC),
                "close_time": datetime.fromtimestamp(
                    (bucket_open + target_step) / 1_000_000, tz=UTC
                )
                - timedelta(milliseconds=1),
                "open": values["open"][left],
                "high": max(values["high"][left:right]),
                "low": min(values["low"][left:right]),
                "close": values["close"][right - 1],
                "base_volume": sum(values["base_volume"][left:right], Decimal(0)),
                "quote_volume": sum(values["quote_volume"][left:right], Decimal(0)),
                "trade_count": sum(values["trade_count"][left:right]),
                "taker_buy_base_volume": sum(
                    values["taker_buy_base_volume"][left:right], Decimal(0)
                ),
                "taker_buy_quote_volume": sum(
                    values["taker_buy_quote_volume"][left:right], Decimal(0)
                ),
                "source": f"causal_5m_aggregation_{target_interval}",
                "ingested_at": values["ingested_at"][right - 1],
            }
        )
    return pa.Table.from_pylist(rows, schema=candle_schema())


def reconcile_direct_vs_derived(
    direct: pa.Table, derived: pa.Table, interval: str
) -> dict[str, Any]:
    direct_rows = {row["open_time"]: row for row in direct.to_pylist()}
    derived_rows = {row["open_time"]: row for row in derived.to_pylist()}
    shared = sorted(set(direct_rows) & set(derived_rows))
    discrepancy_counts = {name: 0 for name in RECONCILIATION_FIELDS}
    examples: list[dict[str, Any]] = []
    for timestamp in shared:
        left, right = direct_rows[timestamp], derived_rows[timestamp]
        different = [name for name in RECONCILIATION_FIELDS if left[name] != right[name]]
        for name in different:
            discrepancy_counts[name] += 1
        if different and len(examples) < 20:
            examples.append(
                {
                    "open_time": timestamp.isoformat(),
                    "fields": different,
                    "direct": {name: str(left[name]) for name in different},
                    "derived": {name: str(right[name]) for name in different},
                }
            )
    exact_rows = len(shared) - sum(
        bool(any(direct_rows[t][name] != derived_rows[t][name] for name in RECONCILIATION_FIELDS))
        for t in shared
    )
    return {
        "interval": interval,
        "direct_rows": direct.num_rows,
        "complete_derived_rows": derived.num_rows,
        "compared_rows": len(shared),
        "exact_match_rows": exact_rows,
        "discrepant_rows": len(shared) - exact_rows,
        "discrepancy_count_by_field": discrepancy_counts,
        "examples": examples,
        "canonical_source": "official Binance USD-M direct kline",
        "policy": "direct klines are canonical; derived candles are an independent reconciliation",
    }
