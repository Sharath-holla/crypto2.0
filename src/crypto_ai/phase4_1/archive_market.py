from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import uuid
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.binance import (
    ArchiveDataset,
    ArchiveObject,
    BinanceArchiveClient,
    monthly_objects,
)
from crypto_ai.data.binance.client import _utc_from_exchange_timestamp
from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.storage import file_sha256
from crypto_ai.domain import interval_milliseconds
from crypto_ai.phase4.market_data import (
    MARKET_DATA_SCHEMA_VERSION,
    DerivativesMarketDataClient,
    MarketDataKind,
    market_data_schema,
    validate_market_table,
)

ARCHIVE_MARKET_PARSER_VERSION = "2.1.0"

_ARCHIVE_DATASETS = {
    MarketDataKind.MARK_KLINE: ArchiveDataset.MARK_PRICE_KLINES,
    MarketDataKind.INDEX_KLINE: ArchiveDataset.INDEX_PRICE_KLINES,
    MarketDataKind.PREMIUM_KLINE: ArchiveDataset.PREMIUM_PRICE_KLINES,
}


def _hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _atomic_write(path: Path, table: pa.Table) -> str:
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable market dataset: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        pq.write_table(table, temporary, compression="zstd", write_statistics=True)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return file_sha256(path)


def _parse_archive_table(
    content: bytes,
    *,
    archive_object: ArchiveObject,
    kind: MarketDataKind,
    start: datetime,
    end: datetime,
    ingested_at: datetime,
) -> pa.Table:
    step = timedelta(milliseconds=interval_milliseconds(archive_object.interval))
    rows: list[dict[str, Any]] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        member = next(item for item in archive.infolist() if not item.is_dir())
        with archive.open(member) as raw_stream:
            text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8", newline="")
            for line_number, raw in enumerate(csv.reader(text_stream), start=1):
                if line_number == 1 and raw and not raw[0].strip().lstrip("-").isdigit():
                    continue
                if len(raw) < 5:
                    raise ValueError(
                        f"Archive {archive_object.filename} line {line_number} "
                        f"has only {len(raw)} fields"
                    )
                try:
                    event_time = _utc_from_exchange_timestamp(raw[0])
                    if event_time < start or event_time >= end:
                        continue
                    rows.append(
                        {
                            "symbol": archive_object.symbol,
                            "event_time": event_time,
                            "availability_time": event_time + step,
                            "open": Decimal(raw[1]),
                            "high": Decimal(raw[2]),
                            "low": Decimal(raw[3]),
                            "close": Decimal(raw[4]),
                            "source": f"binance_usdm_{kind.value}_archive",
                            "ingested_at": ingested_at,
                        }
                    )
                except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(
                        f"Invalid {kind.value} row in {archive_object.filename} line {line_number}"
                    ) from exc
    return pa.Table.from_pylist(rows, schema=market_data_schema(kind))


def _coverage(table: pa.Table, start: datetime, end: datetime, interval: str) -> dict[str, Any]:
    step_us = interval_milliseconds(interval) * 1_000
    start_us = int(start.astimezone(UTC).timestamp() * 1_000_000)
    end_us = int(end.astimezone(UTC).timestamp() * 1_000_000)
    first_us = ((start_us + step_us - 1) // step_us) * step_us
    expected_rows = max(0, (end_us - first_us + step_us - 1) // step_us)
    observed = table.column("event_time").combine_chunks().cast(pa.int64()).to_numpy()
    missing_examples: list[str] = []
    if len(observed):
        augmented = np.concatenate(
            [
                np.asarray([first_us - step_us], dtype=np.int64),
                observed,
                np.asarray([end_us], dtype=np.int64),
            ]
        )
        for previous, current in zip(augmented, augmented[1:], strict=False):
            candidate = int(previous + step_us)
            while candidate < int(current) and len(missing_examples) < 20:
                missing_examples.append(
                    datetime.fromtimestamp(candidate / 1_000_000, tz=UTC).isoformat()
                )
                candidate += step_us
    missing_rows = max(0, int(expected_rows) - table.num_rows)
    return {
        "expected_rows": int(expected_rows),
        "observed_rows": table.num_rows,
        "missing_rows": missing_rows,
        "coverage_ratio": table.num_rows / expected_rows if expected_rows else 0.0,
        "missing_examples": missing_examples,
        "status": "PASS" if missing_rows == 0 else "FAIL",
    }


def _missing_ranges(
    table: pa.Table, start: datetime, end: datetime, interval: str
) -> list[tuple[datetime, datetime]]:
    step_us = interval_milliseconds(interval) * 1_000
    start_us = int(start.astimezone(UTC).timestamp() * 1_000_000)
    end_us = int(end.astimezone(UTC).timestamp() * 1_000_000)
    first_us = ((start_us + step_us - 1) // step_us) * step_us
    expected = np.arange(first_us, end_us, step_us, dtype=np.int64)
    observed = table.column("event_time").combine_chunks().cast(pa.int64()).to_numpy()
    missing = np.setdiff1d(expected, observed, assume_unique=True)
    if not len(missing):
        return []
    breaks = np.flatnonzero(np.diff(missing) != step_us) + 1
    groups = np.split(missing, breaks)
    return [
        (
            datetime.fromtimestamp(int(group[0]) / 1_000_000, tz=UTC),
            datetime.fromtimestamp(int(group[-1] + step_us) / 1_000_000, tz=UTC),
        )
        for group in groups
    ]


def ingest_archive_market_data(
    client: BinanceArchiveClient,
    *,
    kind: MarketDataKind,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime,
    output_root: Path,
    gap_fill_request_json: Callable[[str, dict[str, object] | None], Any] | None = None,
) -> Path:
    """Build checksum-addressed Bronze lineage and canonical Silver from public archives."""

    if kind not in _ARCHIVE_DATASETS:
        raise ValueError("Archive market ingestion supports mark, index, or premium klines")
    if start.tzinfo is None or end.tzinfo is None or start >= end:
        raise ValueError("archive market range must be timezone-aware with start < end")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    captured = datetime.now(UTC)
    tables: list[pa.Table] = []
    provenance: list[dict[str, Any]] = []
    objects = monthly_objects(
        _ARCHIVE_DATASETS[kind],
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
    )
    for archive_object in objects:
        content, metadata = client.fetch_object_bytes(archive_object)
        tables.append(
            _parse_archive_table(
                content,
                archive_object=archive_object,
                kind=kind,
                start=start,
                end=end,
                ingested_at=captured,
            )
        )
        provenance.append(metadata)
    if not tables:
        raise ValueError("archive market request selected no monthly objects")
    table = pa.concat_tables(tables).sort_by([("event_time", "ascending")])
    archive_coverage = _coverage(table, start, end, interval)
    gap_ranges = _missing_ranges(table, start, end, interval)
    gap_fill_table: pa.Table | None = None
    if gap_ranges and gap_fill_request_json is not None:
        adapter = DerivativesMarketDataClient(gap_fill_request_json)
        gap_tables = [
            adapter.fetch(
                kind,
                symbol=symbol,
                start=gap_start,
                end=gap_end,
                interval=interval,
                ingested_at=captured,
            )
            for gap_start, gap_end in gap_ranges
        ]
        gap_fill_table = pa.concat_tables(gap_tables)
        table = pa.concat_tables([table, gap_fill_table]).sort_by([("event_time", "ascending")])
    validation = validate_market_table(table, kind)
    coverage = _coverage(table, start, end, interval)
    if coverage["status"] != "PASS":
        remaining_ranges = _missing_ranges(table, start, end, interval)
        failure_path = (
            output_root.resolve()
            / "coverage_failures"
            / f"{kind.value}-{start.date().isoformat()}-{end.date().isoformat()}.json"
        )
        write_manifest(
            failure_path,
            {
                "kind": kind.value,
                "request_range": {"start": start.isoformat(), "end": end.isoformat()},
                "archive_coverage": archive_coverage,
                "final_coverage": coverage,
                "attempted_rest_gap_ranges": [
                    {"start": left.isoformat(), "end": right.isoformat()}
                    for left, right in gap_ranges
                ],
                "remaining_missing_ranges": [
                    {"start": left.isoformat(), "end": right.isoformat()}
                    for left, right in remaining_ranges
                ],
            },
        )
        if gap_fill_request_json is None:
            raise ValueError(
                f"{kind.value} archive coverage is incomplete: {coverage['missing_rows']} "
                f"rows missing; details: {failure_path}"
            )
        coverage["status"] = "WARN"
        coverage["missing_behavior"] = (
            "reported and left missing after archive plus official REST; never synthesized"
        )

    source_identity = {
        "kind": kind.value,
        "symbol": symbol,
        "interval": interval,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "upstream_sha256": [item["upstream_sha256"] for item in provenance],
        "archive_coverage": archive_coverage,
        "rest_gap_ranges": [
            {"start": gap_start.isoformat(), "end": gap_end.isoformat()}
            for gap_start, gap_end in gap_ranges
        ],
        "rest_gap_content_hash": (
            _hash(gap_fill_table.drop(["ingested_at"]).to_pylist())
            if gap_fill_table is not None
            else None
        ),
        "parser_version": ARCHIVE_MARKET_PARSER_VERSION,
    }
    bronze_version = f"market-bronze-v2-1-{_hash(source_identity)}"
    bronze_dir = output_root.resolve() / "bronze" / kind.value / bronze_version
    bronze_manifest = bronze_dir / "manifest.json"
    if not bronze_manifest.exists():
        gap_fill_record = None
        if gap_fill_table is not None:
            gap_fill_path = bronze_dir / "rest_gap_fill.parquet"
            gap_fill_checksum = _atomic_write(gap_fill_path, gap_fill_table)
            gap_fill_record = {
                "file": gap_fill_path.name,
                "sha256": gap_fill_checksum,
                "row_count": gap_fill_table.num_rows,
                "source": "Binance USD-M public REST",
                "ranges": source_identity["rest_gap_ranges"],
            }
        write_manifest(
            bronze_manifest,
            {
                "dataset_version": bronze_version,
                "layer": "bronze",
                "representation": "immutable-upstream-zip",
                "kind": kind.value,
                "symbol": symbol,
                "interval": interval,
                "request_range": {"start": start.isoformat(), "end": end.isoformat()},
                "archive_count": len(provenance),
                "archives": provenance,
                "archive_coverage": archive_coverage,
                "rest_gap_fill": gap_fill_record,
                "row_count": table.num_rows,
                "coverage": coverage,
                "parser_version": ARCHIVE_MARKET_PARSER_VERSION,
            },
        )

    silver_identity = {
        "source_version": bronze_version,
        "source_identity": source_identity,
        "validation": validation,
        "coverage": coverage,
        "transformation": "archive-canonical-sort-v2.1",
    }
    silver_version = f"market-silver-v2-1-{_hash(silver_identity)}"
    silver_dir = output_root.resolve() / "silver" / kind.value / silver_version
    silver_path = silver_dir / "dataset.parquet"
    silver_manifest = silver_dir / "manifest.json"
    existing = read_manifest(silver_manifest)
    if existing is not None:
        if not silver_path.exists() or file_sha256(silver_path) != existing.get("sha256"):
            raise ValueError(f"Existing archive Silver dataset is incomplete: {silver_dir}")
        return silver_manifest

    metadata = dict(table.schema.metadata or {})
    metadata.update(
        {
            b"layer": b"silver",
            b"dataset_version": silver_version.encode(),
            b"source_dataset_version": bronze_version.encode(),
            b"parser_version": ARCHIVE_MARKET_PARSER_VERSION.encode(),
        }
    )
    checksum = _atomic_write(silver_path, table.replace_schema_metadata(metadata))
    write_manifest(
        silver_manifest,
        {
            "dataset_version": silver_version,
            "layer": "silver",
            "kind": kind.value,
            "symbol": symbol,
            "interval": interval,
            "source_manifest": str(bronze_manifest),
            "source_dataset_version": bronze_version,
            "validation": validation,
            "coverage": coverage,
            "row_count": table.num_rows,
            "file": "dataset.parquet",
            "sha256": checksum,
            "schema_version": MARKET_DATA_SCHEMA_VERSION,
            "parser_version": ARCHIVE_MARKET_PARSER_VERSION,
        },
    )
    return silver_manifest
