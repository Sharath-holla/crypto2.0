from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256, read_candle_parquet

MARKET_VALUE_COLUMNS = (
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


def _load_manifest_table(path: Path) -> tuple[pa.Table, dict[str, Any]]:
    path = path.resolve()
    manifest = read_manifest(path)
    if manifest is None:
        raise FileNotFoundError(path)
    root = path.parent.parent
    tables: list[pa.Table] = []
    for record in manifest.get("partitions", []):
        if not isinstance(record, dict) or not record.get("file"):
            continue
        file_path = root / str(record["file"])
        if file_sha256(file_path) != record.get("sha256"):
            raise ValueError(f"Transport sample checksum mismatch: {file_path}")
        tables.append(read_candle_parquet(file_path))
    if not tables:
        raise ValueError(f"Manifest contains no readable transport samples: {path}")
    return pa.concat_tables(tables).sort_by([("open_time", "ascending")]), manifest


def compare_candle_transports(
    left_manifest_path: Path,
    right_manifest_path: Path,
    *,
    output_path: Path | None = None,
) -> dict[str, Any]:
    left, left_manifest = _load_manifest_table(left_manifest_path)
    right, right_manifest = _load_manifest_table(right_manifest_path)
    identity_fields = ("market", "symbol", "interval")
    mismatch = [
        name for name in identity_fields if left_manifest.get(name) != right_manifest.get(name)
    ]
    if mismatch:
        raise ValueError(f"Transport sample identity mismatch: {mismatch}")
    common_start = max(left.column("open_time")[0].as_py(), right.column("open_time")[0].as_py())
    common_end = min(left.column("open_time")[-1].as_py(), right.column("open_time")[-1].as_py())
    left = left.filter(
        pc.and_(
            pc.greater_equal(left.column("open_time"), pa.scalar(common_start)),
            pc.less_equal(left.column("open_time"), pa.scalar(common_end)),
        )
    )
    right = right.filter(
        pc.and_(
            pc.greater_equal(right.column("open_time"), pa.scalar(common_start)),
            pc.less_equal(right.column("open_time"), pa.scalar(common_end)),
        )
    )
    left_times = left.column("open_time").combine_chunks().to_pylist()
    right_times = right.column("open_time").combine_chunks().to_pylist()
    timestamps_equal = left_times == right_times
    fields: dict[str, Any] = {}
    for name in MARKET_VALUE_COLUMNS:
        left_values = left.column(name).combine_chunks().to_pylist()
        right_values = right.column(name).combine_chunks().to_pylist()
        mismatches = [
            index
            for index, (left_value, right_value) in enumerate(
                zip(left_values, right_values, strict=False)
            )
            if left_value != right_value
        ]
        fields[name] = {
            "mismatch_count": len(mismatches),
            "examples": [
                {
                    "open_time": left_times[index].isoformat(),
                    "left": str(left_values[index]),
                    "right": str(right_values[index]),
                }
                for index in mismatches[:10]
            ],
        }
    report = {
        "schema_version": "1.0.0",
        "left_manifest": str(left_manifest_path.resolve()),
        "right_manifest": str(right_manifest_path.resolve()),
        "left_source": left_manifest.get("source"),
        "right_source": right_manifest.get("source"),
        "common_start": common_start.isoformat(),
        "common_end_inclusive": common_end.isoformat(),
        "left_rows": left.num_rows,
        "right_rows": right.num_rows,
        "timestamps_equal": timestamps_equal,
        "fields": fields,
        "equivalent": timestamps_equal
        and left.num_rows == right.num_rows
        and all(item["mismatch_count"] == 0 for item in fields.values()),
    }
    if output_path is not None:
        write_manifest(output_path, report)
    return report
