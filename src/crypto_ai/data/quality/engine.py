from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from crypto_ai.data.ingestion.manifest import read_manifest, write_manifest
from crypto_ai.data.quality.checks import validate_partition
from crypto_ai.data.quality.models import (
    DatasetQualityReport,
    ValidationContext,
    ValidationResult,
    ValidationSeverity,
    ValidationStatus,
)
from crypto_ai.data.quality.policy import QualityPolicy
from crypto_ai.data.schema import schema_errors
from crypto_ai.data.storage import file_sha256
from crypto_ai.domain import interval_milliseconds

logger = logging.getLogger(__name__)

_ROW_SOURCES = {
    "spot": "binance_spot_rest",
    "usdm": "binance_usdm_futures_rest",
}


@dataclass(slots=True)
class _Boundary:
    path: Path
    declared_start: datetime | None
    declared_end: datetime | None
    minimum: datetime
    maximum: datetime
    first_row: dict[str, Any]
    last_row: dict[str, Any]


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"Manifest timestamp must include a timezone: {value}")
    return parsed.astimezone(UTC)


def _metadata(table: pa.Table) -> dict[str, str]:
    return {
        key.decode("utf-8"): value.decode("utf-8")
        for key, value in (table.schema.metadata or {}).items()
    }


def _check(
    name: str,
    status: ValidationStatus,
    severity: ValidationSeverity,
    message: str,
    *,
    symbol: str,
    interval: str,
    partition: str | None = None,
    observed: Any = None,
    expected: Any = None,
    affected: int = 0,
    samples: list[Any] | tuple[Any, ...] = (),
) -> ValidationResult:
    return ValidationResult(
        check_name=name,
        status=status,
        severity=severity,
        symbol=symbol,
        interval=interval,
        partition=partition,
        message=message,
        observed_value=observed,
        expected_value=expected,
        affected_rows=affected,
        sample_rows=tuple(samples),
    )


def _dataset_version(identity: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()[:24]
    return f"dataset-{digest}"


class QualityEngine:
    def __init__(self, policy: QualityPolicy | None = None) -> None:
        self.policy = policy or QualityPolicy()

    def validate_manifest(self, manifest_path: Path) -> DatasetQualityReport:
        started = time.perf_counter()
        manifest_path = manifest_path.resolve()
        manifest = read_manifest(manifest_path)
        if manifest is None:
            raise FileNotFoundError(f"Manifest does not exist: {manifest_path}")

        source = str(manifest.get("source", "unknown"))
        market = str(manifest.get("market")) if manifest.get("market") is not None else None
        symbol = str(manifest.get("symbol", "unknown"))
        interval = str(manifest.get("interval", "unknown"))
        range_start = _parse_datetime(manifest.get("start"))
        range_end = _parse_datetime(manifest.get("end"))
        root = manifest_path.parent.parent
        declared_row_source = manifest.get("row_source")
        row_source = (
            str(declared_row_source)
            if declared_row_source is not None
            else _ROW_SOURCES.get(market or "")
        )

        logger.info(
            "Dataset validation started",
            extra={
                "event": "validation_started",
                "symbol": symbol,
                "interval": interval,
                "manifest": str(manifest_path),
            },
        )

        checks: list[ValidationResult] = []
        source_files: list[dict[str, Any]] = []
        boundaries: list[_Boundary] = []
        metric_totals: dict[str, int] = {
            "observed_candles": 0,
            "exact_duplicates": 0,
            "conflicting_duplicates": 0,
            "invalid_ohlc": 0,
            "volume_errors": 0,
            "timestamp_errors": 0,
            "candidate_outliers": 0,
            "zero_volume_count": 0,
            "schema_errors": 0,
        }

        partitions = manifest.get("partitions")
        if not isinstance(partitions, list):
            partitions = []
            checks.append(
                _check(
                    "manifest_partitions",
                    ValidationStatus.FAIL,
                    ValidationSeverity.CRITICAL,
                    "Manifest partitions must be a list",
                    symbol=symbol,
                    interval=interval,
                    observed=type(manifest.get("partitions")).__name__,
                    expected="list",
                )
            )

        manifest_locations = manifest.get("file_locations", [])
        record_locations = [
            record.get("file")
            for record in partitions
            if isinstance(record, dict) and record.get("file")
        ]
        if not isinstance(manifest_locations, list) or sorted(manifest_locations) != sorted(
            record_locations
        ):
            checks.append(
                _check(
                    "manifest_file_list",
                    ValidationStatus.FAIL,
                    ValidationSeverity.ERROR,
                    "Manifest file_locations differs from partition file records",
                    symbol=symbol,
                    interval=interval,
                    observed=manifest_locations,
                    expected=record_locations,
                )
            )

        for record in partitions:
            if not isinstance(record, dict) or not record.get("file"):
                if isinstance(record, dict) and record.get("status") == "empty":
                    checks.append(
                        _check(
                            "empty_partition",
                            ValidationStatus.FAIL,
                            ValidationSeverity.ERROR,
                            "Manifest contains an empty requested partition",
                            symbol=symbol,
                            interval=interval,
                            partition=str(record.get("partition_key")),
                        )
                    )
                continue
            relative = Path(str(record["file"]))
            path = root / relative
            partition_name = str(record.get("partition_key", relative.as_posix()))
            declared_start = _parse_datetime(record.get("start"))
            declared_end = _parse_datetime(record.get("end"))
            expected_checksum = record.get("sha256")
            source_entry: dict[str, Any] = {
                "path": str(path),
                "relative_path": relative.as_posix(),
                "manifest_sha256": expected_checksum,
                "manifest_row_count": record.get("row_count"),
            }

            if not path.exists():
                source_entry["status"] = "missing"
                source_files.append(source_entry)
                checks.append(
                    _check(
                        "missing_referenced_file",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        "Manifest-referenced Parquet file does not exist",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                        observed=str(path),
                        expected="existing readable file",
                    )
                )
                continue

            actual_checksum = file_sha256(path)
            source_entry["sha256"] = actual_checksum
            if expected_checksum != actual_checksum:
                checks.append(
                    _check(
                        "manifest_checksum",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        "Parquet checksum differs from the immutable manifest",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                        observed=actual_checksum,
                        expected=expected_checksum,
                    )
                )

            try:
                table = pq.ParquetFile(path).read()
            except Exception as exc:
                source_entry["status"] = "unreadable"
                source_entry["error"] = str(exc)
                source_files.append(source_entry)
                checks.append(
                    _check(
                        "unreadable_parquet",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        f"Parquet file cannot be read: {type(exc).__name__}: {exc}",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                    )
                )
                continue

            source_entry["status"] = "readable"
            source_entry["row_count"] = table.num_rows
            source_entry["metadata"] = _metadata(table)
            source_files.append(source_entry)
            metric_totals["observed_candles"] += table.num_rows

            if table.num_rows == 0:
                checks.append(
                    _check(
                        "unexpected_empty_file",
                        ValidationStatus.FAIL,
                        ValidationSeverity.ERROR,
                        "A completed partition contains zero rows",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                        observed=0,
                        expected="> 0",
                    )
                )
            if record.get("row_count") != table.num_rows:
                checks.append(
                    _check(
                        "manifest_row_count",
                        ValidationStatus.FAIL,
                        ValidationSeverity.ERROR,
                        "Manifest partition row count differs from Parquet",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                        observed=table.num_rows,
                        expected=record.get("row_count"),
                    )
                )

            file_metadata = _metadata(table)
            metadata_expected = {
                "market": market,
                "symbol": symbol,
                "interval": interval,
                "requested_start": declared_start.isoformat() if declared_start else None,
                "requested_end": declared_end.isoformat() if declared_end else None,
            }
            mismatches = {
                key: {"observed": file_metadata.get(key), "expected": value}
                for key, value in metadata_expected.items()
                if value is not None and file_metadata.get(key) != value
            }
            if mismatches:
                checks.append(
                    _check(
                        "file_metadata_consistency",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        "Parquet metadata differs from its manifest partition identity",
                        symbol=symbol,
                        interval=interval,
                        partition=partition_name,
                        observed=mismatches,
                        expected=metadata_expected,
                    )
                )

            partition_validation = validate_partition(
                table,
                ValidationContext(
                    symbol=symbol,
                    interval=interval,
                    source=(
                        str(record["row_source"])
                        if record.get("row_source") is not None
                        else row_source
                    ),
                    market=market,
                    partition=partition_name,
                    range_start=declared_start,
                    range_end=declared_end,
                ),
                self.policy,
            )
            checks.extend(partition_validation.checks)
            stage_metrics = {
                "schema_check_complete": {
                    "schema_errors": partition_validation.metrics.get("schema_errors", 0)
                },
                "timestamp_check_complete": {
                    "timestamp_errors": partition_validation.metrics.get("timestamp_errors", 0)
                },
                "gap_check_complete": {
                    "missing_candles": partition_validation.metrics.get(
                        "number_of_missing_candles", 0
                    )
                },
                "duplicate_check_complete": {
                    "duplicate_count": partition_validation.metrics.get("duplicate_count", 0)
                },
                "outlier_check_complete": {
                    "candidate_outliers": partition_validation.metrics.get("candidate_outliers", 0)
                },
            }
            for event, values in stage_metrics.items():
                logger.info(
                    "Partition validation stage completed",
                    extra={
                        "event": event,
                        "symbol": symbol,
                        "interval": interval,
                        "partition": partition_name,
                        "row_count": table.num_rows,
                        **values,
                    },
                )
            for key in metric_totals:
                if key == "observed_candles":
                    continue
                metric_totals[key] += int(partition_validation.metrics.get(key, 0))

            if not schema_errors(table.schema) and table.num_rows:
                ordered = table.sort_by([("open_time", "ascending")])
                first_row = ordered.slice(0, 1).to_pylist()[0]
                last_row = ordered.slice(ordered.num_rows - 1, 1).to_pylist()[0]
                boundaries.append(
                    _Boundary(
                        path=path,
                        declared_start=declared_start,
                        declared_end=declared_end,
                        minimum=first_row["open_time"],
                        maximum=last_row["open_time"],
                        first_row=first_row,
                        last_row=last_row,
                    )
                )

        manifest_row_count = manifest.get("row_count")
        if manifest_row_count != metric_totals["observed_candles"]:
            checks.append(
                _check(
                    "manifest_total_row_count",
                    ValidationStatus.FAIL,
                    ValidationSeverity.ERROR,
                    "Manifest total row count differs from readable Parquet rows",
                    symbol=symbol,
                    interval=interval,
                    observed=metric_totals["observed_candles"],
                    expected=manifest_row_count,
                )
            )

        checks.extend(self._cross_partition_checks(boundaries, symbol, interval))
        checks.extend(
            self._manifest_range_checks(
                boundaries,
                range_start,
                range_end,
                symbol,
                interval,
            )
        )

        expected_candles = 0
        if range_start is not None and range_end is not None:
            interval_delta = timedelta(milliseconds=interval_milliseconds(interval))
            expected_candles = int((range_end - range_start) / interval_delta)
        duplicate_rows = metric_totals["exact_duplicates"] + metric_totals["conflicting_duplicates"]
        missing_candles = max(
            0,
            expected_candles - (metric_totals["observed_candles"] - duplicate_rows),
        )
        summary = {
            **metric_totals,
            "expected_candles": expected_candles,
            "missing_candles": missing_candles,
            "file_count": len(source_files),
            "missing_file_count": sum(entry.get("status") == "missing" for entry in source_files),
            "unreadable_file_count": sum(
                entry.get("status") == "unreadable" for entry in source_files
            ),
            "manifest_mismatch_count": sum(
                check.check_name.startswith("manifest_")
                or check.check_name == "file_metadata_consistency"
                for check in checks
                if check.status is ValidationStatus.FAIL
            ),
        }
        identity = {
            "manifest": str(manifest_path),
            "manifest_run_id": manifest.get("run_id"),
            "source_files": [
                {
                    "relative_path": entry.get("relative_path"),
                    "sha256": entry.get("sha256", "MISSING"),
                }
                for entry in source_files
            ],
        }
        report = DatasetQualityReport(
            dataset_version=_dataset_version(identity),
            source=source,
            market=market,
            symbol=symbol,
            interval=interval,
            range_start=range_start,
            range_end=range_end,
            source_files=source_files,
            source_manifest=str(manifest_path),
            checks=checks,
            summary=summary,
            policy=self.policy.model_dump(mode="json"),
        )
        if report.overall_status is ValidationStatus.FAIL:
            logger.error(
                "Dataset validation failed",
                extra={
                    "event": "validation_failed",
                    "symbol": symbol,
                    "interval": interval,
                    "failed_check_count": sum(
                        check.status is ValidationStatus.FAIL for check in checks
                    ),
                },
            )
        logger.info(
            "Dataset validation completed",
            extra={
                "event": "validation_completed",
                "symbol": symbol,
                "interval": interval,
                "row_count": metric_totals["observed_candles"],
                "status": report.overall_status.value,
                "duration_seconds": time.perf_counter() - started,
            },
        )
        return report

    def validate_file(
        self,
        path: Path,
        *,
        symbol: str,
        interval: str,
        source: str,
        market: str | None = None,
        range_start: datetime | None = None,
        range_end: datetime | None = None,
    ) -> DatasetQualityReport:
        path = path.resolve()
        started = time.perf_counter()
        logger.info(
            "File validation started",
            extra={
                "event": "validation_started",
                "symbol": symbol,
                "interval": interval,
                "partition": str(path),
            },
        )
        checks: list[ValidationResult] = []
        source_files: list[dict[str, Any]] = [{"path": str(path)}]
        if not path.exists():
            checks.append(
                _check(
                    "missing_file",
                    ValidationStatus.FAIL,
                    ValidationSeverity.CRITICAL,
                    "Parquet file does not exist",
                    symbol=symbol,
                    interval=interval,
                    observed=str(path),
                )
            )
            checksum = "MISSING"
            metrics: dict[str, Any] = {"observed_candles": 0}
        else:
            checksum = file_sha256(path)
            source_files[0]["sha256"] = checksum
            try:
                table = pq.ParquetFile(path).read()
            except Exception as exc:
                checks.append(
                    _check(
                        "unreadable_parquet",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        f"Parquet file cannot be read: {type(exc).__name__}: {exc}",
                        symbol=symbol,
                        interval=interval,
                    )
                )
                metrics = {"observed_candles": 0}
            else:
                partition = validate_partition(
                    table,
                    ValidationContext(
                        symbol=symbol,
                        interval=interval,
                        source=source,
                        market=market,
                        partition=path.name,
                        range_start=range_start,
                        range_end=range_end,
                    ),
                    self.policy,
                )
                checks.extend(partition.checks)
                metrics = {"observed_candles": table.num_rows, **partition.metrics}
                source_files[0]["row_count"] = table.num_rows
        expected = int(metrics.get("number_of_expected_candles", metrics["observed_candles"]))
        summary = {
            **metrics,
            "expected_candles": expected,
            "missing_candles": int(metrics.get("number_of_missing_candles", 0)),
            "file_count": 1,
        }
        report = DatasetQualityReport(
            dataset_version=_dataset_version({"path": str(path), "sha256": checksum}),
            source=source,
            market=market,
            symbol=symbol,
            interval=interval,
            range_start=range_start,
            range_end=range_end,
            source_files=source_files,
            source_manifest=None,
            checks=checks,
            summary=summary,
            policy=self.policy.model_dump(mode="json"),
        )
        logger.info(
            "File validation completed",
            extra={
                "event": "validation_completed",
                "symbol": symbol,
                "interval": interval,
                "partition": str(path),
                "row_count": metrics["observed_candles"],
                "status": report.overall_status.value,
                "duration_seconds": time.perf_counter() - started,
            },
        )
        return report

    def write_report(self, report: DatasetQualityReport, output_root: Path) -> Path:
        path = output_root.resolve() / f"{report.report_id}.json"
        write_manifest(path, report.to_dict())
        return path

    def _cross_partition_checks(
        self,
        boundaries: list[_Boundary],
        symbol: str,
        interval: str,
    ) -> list[ValidationResult]:
        if len(boundaries) < 2:
            return [
                _check(
                    "cross_partition_continuity",
                    ValidationStatus.PASS,
                    ValidationSeverity.INFO,
                    "Fewer than two readable partitions; no boundary pair to compare",
                    symbol=symbol,
                    interval=interval,
                )
            ]
        checks: list[ValidationResult] = []
        original = list(boundaries)
        ordered = sorted(
            boundaries,
            key=lambda item: item.declared_start or item.minimum,
        )
        if original != ordered:
            checks.append(
                _check(
                    "out_of_order_partitions",
                    ValidationStatus.FAIL,
                    ValidationSeverity.ERROR,
                    "Manifest partition records are not chronological",
                    symbol=symbol,
                    interval=interval,
                )
            )
        interval_delta = timedelta(milliseconds=interval_milliseconds(interval))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if (
                previous.declared_end is not None
                and current.declared_start is not None
                and current.declared_start < previous.declared_end
            ):
                checks.append(
                    _check(
                        "overlapping_partition_ranges",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        "Declared partition ranges overlap",
                        symbol=symbol,
                        interval=interval,
                        partition=current.path.name,
                        observed=current.declared_start,
                        expected=f">= {previous.declared_end.isoformat()}",
                    )
                )
            expected_next = previous.maximum + interval_delta
            if current.minimum == previous.maximum:
                exact = current.first_row == previous.last_row
                checks.append(
                    _check(
                        "cross_partition_exact_duplicate"
                        if exact
                        else "cross_partition_conflicting_duplicate",
                        ValidationStatus.FAIL,
                        ValidationSeverity.ERROR if exact else ValidationSeverity.CRITICAL,
                        "Adjacent partitions repeat the same candle identity",
                        symbol=symbol,
                        interval=interval,
                        partition=current.path.name,
                        observed=current.minimum,
                        expected=expected_next,
                        affected=1,
                    )
                )
            elif current.minimum < expected_next:
                checks.append(
                    _check(
                        "cross_partition_overlap",
                        ValidationStatus.FAIL,
                        ValidationSeverity.CRITICAL,
                        "Adjacent Parquet partitions overlap",
                        symbol=symbol,
                        interval=interval,
                        partition=current.path.name,
                        observed=current.minimum,
                        expected=expected_next,
                    )
                )
            elif current.minimum > expected_next:
                missing = int((current.minimum - expected_next) / interval_delta)
                checks.append(
                    _check(
                        "cross_partition_gap",
                        ValidationStatus.FAIL,
                        ValidationSeverity.ERROR,
                        "A candle gap exists across adjacent partition boundaries",
                        symbol=symbol,
                        interval=interval,
                        partition=current.path.name,
                        observed=missing,
                        expected=0,
                        affected=missing,
                        samples=[expected_next],
                    )
                )
        if not checks:
            checks.append(
                _check(
                    "cross_partition_continuity",
                    ValidationStatus.PASS,
                    ValidationSeverity.INFO,
                    "Adjacent partitions are chronological and continuous",
                    symbol=symbol,
                    interval=interval,
                )
            )
        return checks

    def _manifest_range_checks(
        self,
        boundaries: list[_Boundary],
        range_start: datetime | None,
        range_end: datetime | None,
        symbol: str,
        interval: str,
    ) -> list[ValidationResult]:
        if not boundaries or range_start is None or range_end is None:
            return []
        interval_ms = interval_milliseconds(interval)
        interval_delta = timedelta(milliseconds=interval_ms)
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        start_ms = int((range_start - epoch) / timedelta(milliseconds=1))
        first_ms = ((start_ms + interval_ms - 1) // interval_ms) * interval_ms
        expected_min = epoch + timedelta(milliseconds=first_ms)
        end_ms = int((range_end - epoch) / timedelta(milliseconds=1))
        expected_count = ((end_ms - 1 - first_ms) // interval_ms) + 1 if first_ms < end_ms else 0
        expected_max = (
            expected_min + (expected_count - 1) * interval_delta if expected_count > 0 else None
        )
        actual_min = min(item.minimum for item in boundaries)
        actual_max = max(item.maximum for item in boundaries)
        if actual_min != expected_min or actual_max != expected_max:
            return [
                _check(
                    "manifest_timestamp_range",
                    ValidationStatus.FAIL,
                    ValidationSeverity.ERROR,
                    "Manifest requested range differs from observed candle boundaries",
                    symbol=symbol,
                    interval=interval,
                    observed={"minimum": actual_min, "maximum": actual_max},
                    expected={"minimum": expected_min, "maximum": expected_max},
                )
            ]
        return [
            _check(
                "manifest_timestamp_range",
                ValidationStatus.PASS,
                ValidationSeverity.INFO,
                "Manifest range matches observed candle boundaries",
                symbol=symbol,
                interval=interval,
            )
        ]
