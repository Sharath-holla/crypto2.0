from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

QUALITY_VALIDATOR_VERSION = "1.1.0"
QUALITY_REPORT_SCHEMA_VERSION = "1.0.0"


class ValidationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ValidationStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class GapClassification(StrEnum):
    UNKNOWN_GAP = "UNKNOWN_GAP"


@dataclass(frozen=True, slots=True)
class ValidationContext:
    symbol: str | None
    interval: str
    source: str | None = None
    market: str | None = None
    partition: str | None = None
    range_start: datetime | None = None
    range_end: datetime | None = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


@dataclass(frozen=True, slots=True)
class ValidationResult:
    check_name: str
    status: ValidationStatus
    severity: ValidationSeverity
    message: str
    symbol: str | None = None
    interval: str | None = None
    partition: str | None = None
    observed_value: Any = None
    expected_value: Any = None
    affected_rows: int = 0
    sample_rows: tuple[Any, ...] = ()
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def code(self) -> str:
        """Backward-compatible issue identifier used by Phase 1 callers."""

        return self.check_name

    @property
    def examples(self) -> list[str]:
        return [str(value) for value in self.sample_rows]

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(slots=True)
class PartitionValidation:
    row_count: int
    interval: str
    checks: list[ValidationResult] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> ValidationStatus:
        return status_from_checks(self.checks)


def status_from_checks(checks: list[ValidationResult]) -> ValidationStatus:
    if any(check.status is ValidationStatus.FAIL for check in checks):
        return ValidationStatus.FAIL
    if any(check.status is ValidationStatus.WARN for check in checks):
        return ValidationStatus.WARN
    return ValidationStatus.PASS


@dataclass(slots=True)
class DatasetQualityReport:
    dataset_version: str
    source: str
    market: str | None
    symbol: str
    interval: str
    range_start: datetime | None
    range_end: datetime | None
    source_files: list[dict[str, Any]]
    source_manifest: str | None
    checks: list[ValidationResult]
    summary: dict[str, Any]
    policy: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    validator_version: str = QUALITY_VALIDATOR_VERSION
    report_schema_version: str = QUALITY_REPORT_SCHEMA_VERSION
    report_id: str = ""

    def __post_init__(self) -> None:
        if not self.report_id:
            identity = {
                "dataset_version": self.dataset_version,
                "validator_version": self.validator_version,
                "report_schema_version": self.report_schema_version,
                "policy": _jsonable(self.policy),
            }
            digest = hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()[:24]
            self.report_id = f"quality-{digest}"

    @property
    def overall_status(self) -> ValidationStatus:
        return status_from_checks(self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_schema_version": self.report_schema_version,
            "validator_version": self.validator_version,
            "dataset_version": self.dataset_version,
            "source": self.source,
            "market": self.market,
            "symbol": self.symbol,
            "interval": self.interval,
            "range": {
                "start": _jsonable(self.range_start),
                "end": _jsonable(self.range_end),
            },
            "created_at": _jsonable(self.created_at),
            "overall_status": self.overall_status.value,
            "source_manifest": self.source_manifest,
            "source_files": _jsonable(self.source_files),
            "policy": _jsonable(self.policy),
            "summary": _jsonable(self.summary),
            "checks": [check.to_dict() for check in self.checks],
        }

    def human_summary(self) -> str:
        fields = [
            "=" * 60,
            "DATA QUALITY REPORT",
            "=" * 60,
            f"Source:                 {self.source}",
            f"Market:                 {self.market or 'unknown'}",
            f"Symbol:                 {self.symbol}",
            f"Interval:               {self.interval}",
            f"Rows:                   {self.summary.get('observed_candles', 0)}",
            f"Expected:               {self.summary.get('expected_candles', 0)}",
            f"Missing candles:        {self.summary.get('missing_candles', 0)}",
            f"Exact duplicates:       {self.summary.get('exact_duplicates', 0)}",
            f"Conflicting duplicates: {self.summary.get('conflicting_duplicates', 0)}",
            f"Invalid OHLC:           {self.summary.get('invalid_ohlc', 0)}",
            f"Volume errors:          {self.summary.get('volume_errors', 0)}",
            f"Timestamp errors:       {self.summary.get('timestamp_errors', 0)}",
            f"Candidate outliers:     {self.summary.get('candidate_outliers', 0)}",
            f"Overall status:         {self.overall_status.value}",
            "=" * 60,
        ]
        return "\n".join(fields)
