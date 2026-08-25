from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from crypto_ai.contracts.execution import OrderSide


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


class PortfolioDecisionStatus(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True, slots=True)
class PositionView:
    symbol: str
    signed_quantity: Decimal
    average_entry_price: Decimal | None
    mark_price: Decimal | None
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("position symbol is required")
        _require_utc(self.observed_at, "observed_at")
        for name in ("average_entry_price", "mark_price"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    snapshot_id: str
    schema_version: str
    as_of: datetime
    base_currency: str
    cash_balance: Decimal
    gross_notional: Decimal
    net_notional: Decimal
    positions: tuple[PositionView, ...]
    source_sequence: int

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip() or not self.schema_version.strip():
            raise ValueError("portfolio snapshot identity and version are required")
        _require_utc(self.as_of, "as_of")
        if self.gross_notional < 0:
            raise ValueError("gross notional cannot be negative")
        if self.source_sequence < 0:
            raise ValueError("portfolio source sequence cannot be negative")
        symbols = [position.symbol for position in self.positions]
        if len(symbols) != len(set(symbols)):
            raise ValueError("portfolio snapshot contains duplicate symbols")


@dataclass(frozen=True, slots=True)
class ExposureProposal:
    proposal_id: str
    prediction_id: str
    symbol: str
    side: OrderSide
    externally_supplied_quantity: Decimal
    reference_price: Decimal
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("proposal_id", "prediction_id", "symbol"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.externally_supplied_quantity <= 0 or self.reference_price <= 0:
            raise ValueError("proposal quantity and reference price must be positive")
        _require_utc(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class PortfolioDecision:
    proposal_id: str
    snapshot_id: str
    status: PortfolioDecisionStatus
    reason_codes: tuple[str, ...]
    policy_version: str

    def __post_init__(self) -> None:
        if not self.proposal_id.strip() or not self.snapshot_id.strip():
            raise ValueError("portfolio decision identities are required")
        if not self.policy_version.strip():
            raise ValueError("portfolio policy version is required")
        if self.status != PortfolioDecisionStatus.APPROVED and not self.reason_codes:
            raise ValueError("non-approved portfolio decisions require reason codes")


@runtime_checkable
class PortfolioPolicy(Protocol):
    def evaluate(
        self, snapshot: PortfolioSnapshot, proposal: ExposureProposal
    ) -> PortfolioDecision: ...


@runtime_checkable
class PortfolioReadPort(Protocol):
    def latest(self) -> PortfolioSnapshot: ...
