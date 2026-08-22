from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pyarrow as pa


@dataclass(frozen=True, slots=True)
class ContextQualityReport:
    status: str
    row_count: int
    duplicate_count: int
    missing_timestamp_count: int
    missing_timestamps: tuple[str, ...]
    missing_timestamps_truncated: bool
    first_timestamp: str | None
    last_timestamp: str | None


def validate_context_table(
    table: pa.Table,
    *,
    key_columns: tuple[str, ...],
    time_column: str,
    expected_step: timedelta | None = None,
) -> ContextQualityReport:
    missing_columns = [
        name for name in (*key_columns, time_column) if name not in table.column_names
    ]
    if missing_columns:
        raise ValueError(f"Context table is missing columns: {missing_columns}")
    rows = table.to_pylist()
    keys: set[tuple[object, ...]] = set()
    duplicates = 0
    times: list[datetime] = []
    previous_key: tuple[object, ...] | None = None
    for row in rows:
        key = tuple(row[name] for name in key_columns)
        if any(value is None for value in key):
            raise ValueError("Context identity columns cannot be null")
        if key in keys:
            duplicates += 1
        keys.add(key)
        if previous_key is not None and key < previous_key:
            raise ValueError("Context records must be sorted by their identity key")
        previous_key = key
        timestamp = row[time_column]
        if not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            raise ValueError("Context timestamps must be timezone-aware datetimes")
        times.append(timestamp.astimezone(UTC))
    if duplicates:
        raise ValueError(f"Context table contains {duplicates} duplicate identity keys")

    missing: list[str] = []
    total_missing = 0
    if expected_step is not None and len(times) > 1:
        for previous, current in zip(times, times[1:], strict=False):
            cursor = previous + expected_step
            while cursor < current:
                total_missing += 1
                if len(missing) < 1_000:
                    missing.append(cursor.isoformat())
                cursor += expected_step
    return ContextQualityReport(
        status="PASS",
        row_count=table.num_rows,
        duplicate_count=0,
        missing_timestamp_count=total_missing,
        missing_timestamps=tuple(missing),
        missing_timestamps_truncated=total_missing > len(missing),
        first_timestamp=times[0].isoformat() if times else None,
        last_timestamp=times[-1].isoformat() if times else None,
    )
