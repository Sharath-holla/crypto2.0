from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


class FailureClass(StrEnum):
    CONTRACT_VIOLATION = "CONTRACT_VIOLATION"
    DATA_STALE = "DATA_STALE"
    EVENT_SEQUENCE_GAP = "EVENT_SEQUENCE_GAP"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MetricPoint:
    name: str
    value: Decimal
    unit: str
    observed_at: datetime
    labels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.unit.strip():
            raise ValueError("metric name and unit are required")
        _require_utc(self.observed_at, "observed_at")
        keys = [key for key, _ in self.labels]
        if len(keys) != len(set(keys)):
            raise ValueError("metric label keys must be unique")


@dataclass(frozen=True, slots=True)
class HealthReport:
    component: str
    status: HealthStatus
    observed_at: datetime
    reason_codes: tuple[str, ...] = ()
    source_sequence: int | None = None

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("health component is required")
        _require_utc(self.observed_at, "observed_at")
        if self.status != HealthStatus.HEALTHY and not self.reason_codes:
            raise ValueError("non-healthy status requires a reason code")


@dataclass(frozen=True, slots=True)
class Alert:
    alert_id: str
    severity: Severity
    code: str
    message: str
    observed_at: datetime
    correlation_id: str

    def __post_init__(self) -> None:
        for name in ("alert_id", "code", "message", "correlation_id"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        _require_utc(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class FailureContext:
    failure_class: FailureClass
    component: str
    operation: str
    observed_at: datetime
    retry_count: int
    state_consistent: bool

    def __post_init__(self) -> None:
        if not self.component.strip() or not self.operation.strip():
            raise ValueError("failure component and operation are required")
        if self.retry_count < 0:
            raise ValueError("retry count cannot be negative")
        _require_utc(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class FailureDisposition:
    block_new_actions: bool
    quarantine_component: bool
    reconciliation_required: bool
    retry_allowed: bool
    operator_action_required: bool
    reason_code: str

    def __post_init__(self) -> None:
        if not self.reason_code.strip():
            raise ValueError("failure disposition reason is required")


@runtime_checkable
class ObservabilitySink(Protocol):
    def metric(self, point: MetricPoint) -> None: ...

    def health(self, report: HealthReport) -> None: ...

    def alert(self, alert: Alert) -> None: ...


@runtime_checkable
class FailurePolicy(Protocol):
    def decide(self, context: FailureContext) -> FailureDisposition: ...


class FailClosedFoundationPolicy:
    """Pure policy for architecture tests; it has no external side effects."""

    _RECONCILE = {
        FailureClass.EVENT_SEQUENCE_GAP,
        FailureClass.RECONCILIATION_REQUIRED,
    }
    _QUARANTINE = {
        FailureClass.CONTRACT_VIOLATION,
        FailureClass.DATA_STALE,
        FailureClass.UNKNOWN,
    }

    def decide(self, context: FailureContext) -> FailureDisposition:
        reconcile = context.failure_class in self._RECONCILE or not context.state_consistent
        quarantine = context.failure_class in self._QUARANTINE
        retry_allowed = (
            context.failure_class == FailureClass.DEPENDENCY_UNAVAILABLE
            and context.retry_count < 3
            and context.state_consistent
        )
        return FailureDisposition(
            block_new_actions=True,
            quarantine_component=quarantine,
            reconciliation_required=reconcile,
            retry_allowed=retry_allowed,
            operator_action_required=quarantine or reconcile or not retry_allowed,
            reason_code=f"FAIL_CLOSED_{context.failure_class}",
        )
