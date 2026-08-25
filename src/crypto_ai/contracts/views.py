from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from crypto_ai.contracts.models import RuntimeMode
from crypto_ai.contracts.observability import HealthStatus


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


@dataclass(frozen=True, slots=True)
class PredictionView:
    prediction_id: str
    model_id: str
    model_version: str
    symbol: str
    feature_time: datetime
    earliest_action_time: datetime
    expected_return: Decimal | None
    no_trade_reason: str | None


@dataclass(frozen=True, slots=True)
class OrderView:
    intent_id: str
    symbol: str
    status: str
    cumulative_filled: Decimal
    last_event_sequence: int


@dataclass(frozen=True, slots=True)
class PositionView:
    symbol: str
    status: str
    signed_quantity: Decimal
    protection_healthy: bool
    last_event_sequence: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """Read-only materialized view; it carries no mutation or order methods."""

    schema_version: str
    projection_version: int
    as_of: datetime
    runtime_mode: RuntimeMode
    overall_health: HealthStatus
    predictions: tuple[PredictionView, ...]
    orders: tuple[OrderView, ...]
    positions: tuple[PositionView, ...]
    alerts: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.schema_version.strip():
            raise ValueError("dashboard schema version is required")
        if self.projection_version < 0:
            raise ValueError("projection version cannot be negative")
        _require_utc(self.as_of, "as_of")


@runtime_checkable
class DashboardQueryPort(Protocol):
    def latest(self) -> DashboardSnapshot: ...

    def at_version(self, projection_version: int) -> DashboardSnapshot: ...
