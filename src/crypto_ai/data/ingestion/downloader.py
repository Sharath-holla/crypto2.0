from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from crypto_ai import __version__
from crypto_ai.config import BinanceSettings
from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.schema import CANDLE_SCHEMA_VERSION, candles_to_table
from crypto_ai.data.storage import file_sha256, read_candle_parquet, write_immutable
from crypto_ai.data.validation import validate_candles
from crypto_ai.domain import interval_milliseconds

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DownloadRequest:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.start.utcoffset() is None:
            raise ValueError("start must include a timezone")
        if self.end.tzinfo is None or self.end.utcoffset() is None:
            raise ValueError("end must include a timezone")
        if self.start >= self.end:
            raise ValueError("start must be earlier than end")
        if self.start_utc.microsecond % 1_000 or self.end_utc.microsecond % 1_000:
            raise ValueError("start and end must be aligned to whole milliseconds")

    @property
    def start_utc(self) -> datetime:
        return self.start.astimezone(UTC)

    @property
    def end_utc(self) -> datetime:
        return self.end.astimezone(UTC)


def _epoch_milliseconds(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    delta = normalized - datetime(1970, 1, 1, tzinfo=UTC)
    return delta.days * 86_400_000 + delta.seconds * 1_000 + delta.microseconds // 1_000


def _partition_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    windows: list[tuple[datetime, datetime]] = []
    cursor = start.astimezone(UTC)
    finish = end.astimezone(UTC)
    while cursor < finish:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time(), tzinfo=UTC)
        window_end = min(finish, next_midnight)
        windows.append((cursor, window_end))
        cursor = window_end
    return windows


class HistoricalDownloader:
    def __init__(self, settings: BinanceSettings, client: Any) -> None:
        self.settings = settings
        self.client = client
        self.root = settings.output_root.resolve()
        self.source_identity = str(getattr(client, "source_identity", "binance"))
        self.row_source = getattr(client, "row_source", None)
        self.source_transport = getattr(client, "source_transport", None)

    def download(self, request: DownloadRequest) -> Path:
        start = request.start_utc
        end = request.end_utc
        run_id = self._run_id(start, end)
        manifest_path = self.root / "manifests" / f"{run_id}.json"
        manifest = read_manifest(manifest_path) or self._new_manifest(run_id, start, end)
        self._assert_manifest_identity(manifest, run_id)
        manifest["status"] = "in_progress"
        manifest["last_updated_at"] = datetime.now(UTC).isoformat()
        write_manifest(manifest_path, manifest)

        try:
            if not manifest.get("instrument_metadata"):
                instrument = self.client.fetch_exchange_info(self.settings.symbol)
                instrument_path = self._write_instrument_snapshot(run_id, instrument)
                manifest["instrument_metadata"] = {
                    "file": instrument_path.relative_to(self.root).as_posix(),
                    "sha256": file_sha256(instrument_path),
                }
                write_manifest(manifest_path, manifest)

            records_by_key = {
                record["partition_key"]: record
                for record in manifest.get("partitions", [])
                if isinstance(record, dict) and "partition_key" in record
            }
            for partition_start, partition_end in _partition_windows(start, end):
                key = self._partition_key(partition_start, partition_end)
                existing = records_by_key.get(key)
                if existing and self._verified_record(existing):
                    logger.info(
                        "Skipping validated Binance partition",
                        extra={"event": "partition_resume", "partition_key": key},
                    )
                    continue

                record = self._download_partition(partition_start, partition_end)
                if existing is None:
                    manifest.setdefault("partitions", []).append(record)
                else:
                    existing.clear()
                    existing.update(record)
                records_by_key[key] = record
                manifest["last_updated_at"] = datetime.now(UTC).isoformat()
                write_manifest(manifest_path, manifest)

            self._finalize_manifest(manifest)
            write_manifest(manifest_path, manifest)
            logger.info(
                "Binance ingestion completed",
                extra={
                    "event": "ingestion_complete",
                    "manifest": str(manifest_path),
                    "row_count": manifest["row_count"],
                    "status": manifest["status"],
                },
            )
            return manifest_path
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["last_updated_at"] = datetime.now(UTC).isoformat()
            manifest["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
            write_manifest(manifest_path, manifest)
            raise

    def _run_id(self, start: datetime, end: datetime) -> str:
        identity = {
            "source": self.source_identity,
            "market": self.settings.market.value,
            "symbol": self.settings.symbol,
            "interval": self.settings.interval,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": __version__,
        }
        suffix = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[
            :16
        ]
        return (
            f"{self.settings.market.value}-{self.settings.symbol.lower()}-"
            f"{self.settings.interval}-{suffix}"
        )

    def _new_manifest(
        self,
        run_id: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        manifest = {
            "run_id": run_id,
            "source": self.source_identity,
            "market": self.settings.market.value,
            "symbol": self.settings.symbol,
            "interval": self.settings.interval,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "downloaded_at": now,
            "last_updated_at": now,
            "row_count": 0,
            "file_locations": [],
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": __version__,
            "status": "in_progress",
            "instrument_metadata": None,
            "partitions": [],
        }
        if self.row_source is not None:
            manifest["row_source"] = str(self.row_source)
        if self.source_transport is not None:
            manifest["source_transport"] = str(self.source_transport)
        return manifest

    def _assert_manifest_identity(self, manifest: dict[str, Any], run_id: str) -> None:
        expected = {
            "run_id": run_id,
            "source": self.source_identity,
            "market": self.settings.market.value,
            "symbol": self.settings.symbol,
            "interval": self.settings.interval,
            "schema_version": CANDLE_SCHEMA_VERSION,
            "ingestion_version": __version__,
        }
        mismatches = [key for key, value in expected.items() if manifest.get(key) != value]
        if mismatches:
            raise ValueError(f"Manifest identity mismatch for: {', '.join(mismatches)}")

    def _partition_key(self, start: datetime, end: datetime) -> str:
        return f"{_epoch_milliseconds(start)}-{_epoch_milliseconds(end)}"

    def _partition_path(self, start: datetime, end: datetime) -> Path:
        filename = f"part-{self._partition_key(start, end)}.parquet"
        parent = self.root / "klines"
        if self.source_transport is not None:
            parent = parent / f"transport={self.source_transport}"
        return (
            parent
            / f"market={self.settings.market.value}"
            / f"symbol={self.settings.symbol}"
            / f"interval={self.settings.interval}"
            / f"date={start.date().isoformat()}"
            / filename
        )

    def _verified_record(self, record: dict[str, Any]) -> bool:
        if record.get("status") == "empty":
            return True
        if record.get("status") != "complete" or not record.get("file"):
            return False
        path = self.root / record["file"]
        if not path.exists():
            return False
        actual_checksum = file_sha256(path)
        if actual_checksum != record.get("sha256"):
            raise ValueError(f"Checksum mismatch for immutable partition {path}")
        table = read_candle_parquet(path)
        if table.num_rows != record.get("row_count"):
            raise ValueError(f"Row-count mismatch for immutable partition {path}")
        return True

    def _download_partition(self, start: datetime, end: datetime) -> dict[str, Any]:
        key = self._partition_key(start, end)
        path = self._partition_path(start, end)
        if path.exists():
            table = self._verify_orphan_partition(path, start, end)
            checksum = file_sha256(path)
            quality = validate_candles(table, self.settings.interval)
            quality_dict = quality.to_dict()
            self._add_range_coverage(quality_dict, table, start, end)
            return self._partition_record(
                key, start, end, table.num_rows, quality_dict, path, checksum
            )

        captured_at = datetime.now(UTC)
        candles = self.client.fetch_klines(
            symbol=self.settings.symbol,
            interval=self.settings.interval,
            start=start,
            end=end,
            ingested_at=captured_at,
        )
        source_metadata = self._source_metadata(start, end)
        if not candles:
            logger.warning(
                "Binance returned no candles for partition",
                extra={"event": "empty_partition", "partition_key": key},
            )
            record = {
                "partition_key": key,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "status": "empty",
                "row_count": 0,
                "file": None,
                "sha256": None,
                "quality": {
                    "is_valid": False,
                    "row_count": 0,
                    "interval": self.settings.interval,
                    "duplicate_count": 0,
                    "gap_count": self._expected_rows(start, end),
                    "errors": [
                        {
                            "code": "empty_requested_range",
                            "message": "No candles were returned for the requested partition",
                            "examples": [],
                        }
                    ],
                    "warnings": [],
                },
            }
            if source_metadata:
                record["source_metadata"] = source_metadata
            return record

        table = candles_to_table(candles)
        quality = validate_candles(table, self.settings.interval)
        self._add_range_coverage(quality_dict := quality.to_dict(), table, start, end)
        checksum = write_immutable(
            path,
            table,
            metadata={
                "source": self.source_identity,
                "market": self.settings.market.value,
                "symbol": self.settings.symbol,
                "interval": self.settings.interval,
                "requested_start": start.isoformat(),
                "requested_end": end.isoformat(),
                "ingestion_version": __version__,
            },
        )
        record = self._partition_record(
            key, start, end, table.num_rows, quality_dict, path, checksum
        )
        if source_metadata:
            record["source_metadata"] = source_metadata
        return record

    def _source_metadata(self, start: datetime, end: datetime) -> dict[str, Any] | None:
        provider = getattr(self.client, "source_metadata", None)
        if provider is None:
            return None
        metadata = provider(start, end)
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("source_metadata must return a dictionary or None")
        return metadata

    def _verify_orphan_partition(
        self,
        path: Path,
        start: datetime,
        end: datetime,
    ):
        parquet_file = pq.ParquetFile(path)
        metadata = parquet_file.schema_arrow.metadata or {}
        expected = {
            b"market": self.settings.market.value,
            b"symbol": self.settings.symbol,
            b"interval": self.settings.interval,
            b"requested_start": start.isoformat(),
            b"requested_end": end.isoformat(),
        }
        mismatches = [
            key.decode("ascii")
            for key, value in expected.items()
            if metadata.get(key, b"").decode("utf-8") != value
        ]
        if mismatches:
            raise ValueError(
                f"Existing immutable partition metadata mismatch for {path}: "
                f"{', '.join(mismatches)}"
            )
        return read_candle_parquet(path)

    def _partition_record(
        self,
        key: str,
        start: datetime,
        end: datetime,
        row_count: int,
        quality: dict[str, Any],
        path: Path,
        checksum: str,
    ) -> dict[str, Any]:
        return {
            "partition_key": key,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "status": "complete",
            "row_count": row_count,
            "file": path.relative_to(self.root).as_posix(),
            "sha256": checksum,
            "quality": quality,
        }

    def _expected_rows(self, start: datetime, end: datetime) -> int:
        interval_ms = interval_milliseconds(self.settings.interval)
        start_ms = _epoch_milliseconds(start)
        end_ms = _epoch_milliseconds(end)
        first_aligned = ((start_ms + interval_ms - 1) // interval_ms) * interval_ms
        if first_aligned >= end_ms:
            return 0
        return ((end_ms - 1 - first_aligned) // interval_ms) + 1

    def _add_range_coverage(
        self,
        quality: dict[str, Any],
        table,
        start: datetime,
        end: datetime,
    ) -> None:
        expected_count = self._expected_rows(start, end)
        actual = {_epoch_milliseconds(timestamp) for timestamp in table["open_time"].to_pylist()}
        interval_ms = interval_milliseconds(self.settings.interval)
        start_ms = _epoch_milliseconds(start)
        end_ms = _epoch_milliseconds(end)
        first_aligned = ((start_ms + interval_ms - 1) // interval_ms) * interval_ms
        expected = set(range(first_aligned, end_ms, interval_ms))
        missing = sorted(expected - actual)
        if missing:
            quality["is_valid"] = False
            quality["gap_count"] = len(missing)
            quality["errors"].append(
                {
                    "code": "missing_requested_interval",
                    "message": (
                        f"Requested range expected {expected_count} candles but "
                        f"{len(missing)} aligned timestamps were absent"
                    ),
                    "examples": [
                        datetime.fromtimestamp(value / 1_000, tz=UTC).isoformat()
                        for value in missing[:10]
                    ],
                }
            )

    def _write_instrument_snapshot(self, run_id: str, payload: dict[str, Any]) -> Path:
        path = (
            self.root
            / "instruments"
            / f"market={self.settings.market.value}"
            / f"symbol={self.settings.symbol}"
            / f"snapshot-{run_id}.json"
        )
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
                encoding="utf-8",
            )
            if path.exists():
                raise ValueError(f"Instrument snapshot appeared during write: {path}")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return path

    def _finalize_manifest(self, manifest: dict[str, Any]) -> None:
        partitions = manifest.get("partitions", [])
        files = [record["file"] for record in partitions if record.get("file")]
        manifest["file_locations"] = files
        manifest["row_count"] = sum(int(record.get("row_count", 0)) for record in partitions)
        invalid = [
            record for record in partitions if not record.get("quality", {}).get("is_valid", False)
        ]
        manifest["quality_summary"] = {
            "partition_count": len(partitions),
            "invalid_partition_count": len(invalid),
            "is_valid": not invalid,
        }
        manifest["status"] = "completed" if not invalid else "completed_with_quality_errors"
        manifest["last_updated_at"] = datetime.now(UTC).isoformat()
        manifest.pop("last_error", None)
