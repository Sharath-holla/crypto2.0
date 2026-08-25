from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Protocol, runtime_checkable

from crypto_ai.contracts.versioning import SemanticVersion, canonical_sha256


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Immutable, versioned event envelope with explicit event and knowledge times."""

    event_id: str
    event_type: str
    schema_version: SemanticVersion
    aggregate_type: str
    aggregate_id: str
    sequence: int
    occurred_at: datetime
    observed_at: datetime
    producer: str
    correlation_id: str
    payload: Mapping[str, Any]
    causation_id: str | None = None

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "producer": self.producer,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"event fields cannot be blank: {', '.join(missing)}")
        if self.sequence < 0:
            raise ValueError("event sequence cannot be negative")
        _require_utc(self.occurred_at, "occurred_at")
        _require_utc(self.observed_at, "observed_at")
        if self.observed_at < self.occurred_at:
            raise ValueError("observed_at cannot precede occurred_at")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(
            {
                "event_id": self.event_id,
                "event_type": self.event_type,
                "schema_version": str(self.schema_version),
                "aggregate_type": self.aggregate_type,
                "aggregate_id": self.aggregate_id,
                "sequence": self.sequence,
                "occurred_at": self.occurred_at,
                "observed_at": self.observed_at,
                "producer": self.producer,
                "correlation_id": self.correlation_id,
                "causation_id": self.causation_id,
                "payload": dict(self.payload),
            }
        )


@dataclass(frozen=True, slots=True)
class AppendResult:
    event_id: str
    aggregate_version: int
    duplicate: bool


@runtime_checkable
class EventWriter(Protocol):
    def append(self, event: EventEnvelope, *, expected_version: int) -> AppendResult: ...


@runtime_checkable
class EventReader(Protocol):
    def read(
        self, aggregate_type: str, aggregate_id: str, *, after_sequence: int = -1
    ) -> tuple[EventEnvelope, ...]: ...


@runtime_checkable
class EventProjection(Protocol):
    @property
    def projection_name(self) -> str: ...

    def apply(self, event: EventEnvelope) -> None: ...
