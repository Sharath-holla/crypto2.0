from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from crypto_ai.contracts.models import RuntimeMode


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset().total_seconds() != 0:
        raise ValueError(f"{field} must be UTC")


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderPurpose(StrEnum):
    ENTRY = "ENTRY"
    REDUCE = "REDUCE"
    EXIT = "EXIT"
    PROTECTION = "PROTECTION"


class IntentStatus(StrEnum):
    BLOCKED = "BLOCKED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class AdapterCapabilities:
    mode: RuntimeMode
    public_market_data_read: bool
    private_account_read: bool
    order_write: bool
    cancellation_write: bool

    @property
    def phase7_1b_safe(self) -> bool:
        return not (self.private_account_read or self.order_write or self.cancellation_write)


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    idempotency_key: str
    strategy_decision_id: str
    symbol: str
    side: OrderSide
    purpose: OrderPurpose
    quantity: Decimal
    created_at: datetime
    expires_at: datetime
    reduce_only: bool
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("intent_id", "idempotency_key", "strategy_decision_id", "symbol"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} is required")
        if self.quantity <= 0:
            raise ValueError("order quantity must be positive")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit price must be positive")
        for name in ("created_at", "expires_at"):
            _require_utc(getattr(self, name), name)
        if self.expires_at <= self.created_at:
            raise ValueError("order intent must expire after it is created")
        if (
            self.purpose in {OrderPurpose.REDUCE, OrderPurpose.EXIT, OrderPurpose.PROTECTION}
            and not self.reduce_only
        ):
            raise ValueError(f"{self.purpose} intent must be reduce-only")


@dataclass(frozen=True, slots=True)
class ExecutionReceipt:
    intent_id: str
    status: IntentStatus
    reason: str
    adapter_mode: RuntimeMode
    external_order_id: str | None = None


@runtime_checkable
class ExecutionAdapter(Protocol):
    @property
    def capabilities(self) -> AdapterCapabilities: ...

    def submit(self, intent: OrderIntent) -> ExecutionReceipt: ...

    def cancel(self, *, intent_id: str, idempotency_key: str) -> ExecutionReceipt: ...

    def reconcile(self) -> tuple[ExecutionReceipt, ...]: ...


class DisabledExecutionAdapter:
    """Only concrete Phase 7.1B adapter: deterministic rejection with no I/O."""

    _capabilities = AdapterCapabilities(
        mode=RuntimeMode.DISABLED,
        public_market_data_read=False,
        private_account_read=False,
        order_write=False,
        cancellation_write=False,
    )

    @property
    def capabilities(self) -> AdapterCapabilities:
        return self._capabilities

    def submit(self, intent: OrderIntent) -> ExecutionReceipt:
        return ExecutionReceipt(
            intent_id=intent.intent_id,
            status=IntentStatus.BLOCKED,
            reason="EXECUTION_DISABLED_PHASE7_1B",
            adapter_mode=RuntimeMode.DISABLED,
        )

    def cancel(self, *, intent_id: str, idempotency_key: str) -> ExecutionReceipt:
        if not intent_id.strip() or not idempotency_key.strip():
            raise ValueError("intent and idempotency identities are required")
        return ExecutionReceipt(
            intent_id=intent_id,
            status=IntentStatus.BLOCKED,
            reason="EXECUTION_DISABLED_PHASE7_1B",
            adapter_mode=RuntimeMode.DISABLED,
        )

    def reconcile(self) -> tuple[ExecutionReceipt, ...]:
        return ()
