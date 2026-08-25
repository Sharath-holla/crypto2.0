from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass, replace
from decimal import Decimal
from enum import StrEnum


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTING = "SUBMITTING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN_RECONCILE_REQUIRED = "UNKNOWN_RECONCILE_REQUIRED"


class PositionStatus(StrEnum):
    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN = "OPEN"
    REDUCING = "REDUCING"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    RECONCILING = "RECONCILING"
    ERROR_SAFE = "ERROR_SAFE"


class ConcurrencyConflict(ValueError):
    """Raised when a second writer uses a stale aggregate version."""


class IdempotencyConflict(ValueError):
    """Raised when an existing idempotency key is reused for different work."""


@dataclass(frozen=True, slots=True)
class OrderEvent:
    event_id: str
    sequence: int
    kind: str
    cumulative_filled: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class OrderSnapshot:
    snapshot_id: str
    sequence: int
    status: OrderStatus
    cumulative_filled: Decimal


@dataclass(frozen=True, slots=True)
class OrderAggregate:
    order_intent_id: str
    quantity: Decimal
    status: OrderStatus = OrderStatus.CREATED
    cumulative_filled: Decimal = Decimal("0")
    version: int = 0
    last_sequence: int = -1
    processed_event_ids: tuple[str, ...] = ()
    processed_command_ids: tuple[str, ...] = ()
    event_fingerprints: tuple[tuple[str, str], ...] = ()
    command_fingerprints: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class PositionEvent:
    event_id: str
    sequence: int
    kind: str
    absolute_quantity: Decimal = Decimal("0")
    protected_quantity: Decimal = Decimal("0")
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class PositionAggregate:
    symbol: str
    side: str = "LONG"
    status: PositionStatus = PositionStatus.FLAT
    absolute_quantity: Decimal = Decimal("0")
    protected_quantity: Decimal = Decimal("0")
    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None
    safe_error_reason: str | None = None
    version: int = 0
    last_sequence: int = -1
    processed_event_ids: tuple[str, ...] = ()
    processed_command_ids: tuple[str, ...] = ()
    event_fingerprints: tuple[tuple[str, str], ...] = ()
    command_fingerprints: tuple[tuple[str, str], ...] = ()

    @property
    def protection_healthy(self) -> bool:
        return self.absolute_quantity == 0 or (
            self.protected_quantity >= self.absolute_quantity
            and self.stop_price is not None
            and self.safe_error_reason is None
        )


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    snapshot_id: str
    known_open_order_ids: tuple[str, ...]
    observed_open_order_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AccountReconciliation:
    healthy: bool
    unknown_exchange_order_ids: tuple[str, ...]
    missing_exchange_order_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SystemHealth:
    network_connected: bool = False
    market_data_fresh: bool = False
    reconciliation_healthy: bool = False
    single_writer_lease: bool = False
    kill_switch_active: bool = True


def _digest(*values: object) -> str:
    encoded = "|".join(str(value) for value in values).encode()
    return hashlib.sha256(encoded).hexdigest()


def _check_idempotency(records: tuple[tuple[str, str], ...], key: str, fingerprint: str) -> bool:
    existing = dict(records).get(key)
    if existing is None:
        return False
    if existing != fingerprint:
        raise IdempotencyConflict(f"idempotency key {key!r} was reused with different payload")
    return True


def make_exchange_client_order_id(strategy_decision_id: str, order_intent_id: str) -> str:
    """Derive a stable retry-safe client ID without credentials or venue state."""

    if not strategy_decision_id or not order_intent_id:
        raise ValueError("strategy decision and order intent IDs are required")
    return f"ca-{_digest(strategy_decision_id, order_intent_id)[:28]}"


def apply_order_command(
    state: OrderAggregate,
    *,
    command_id: str,
    command: str,
    expected_version: int,
    payload_fingerprint: str = "",
) -> OrderAggregate:
    """Apply one single-writer command with idempotency and optimistic locking."""

    fingerprint = _digest(command, payload_fingerprint)
    if _check_idempotency(state.command_fingerprints, command_id, fingerprint):
        return state
    if expected_version != state.version:
        raise ConcurrencyConflict(
            f"expected aggregate version {expected_version}, found {state.version}"
        )
    transitions = {
        (OrderStatus.CREATED, "VALIDATE"): OrderStatus.VALIDATED,
        (OrderStatus.VALIDATED, "SUBMIT"): OrderStatus.SUBMITTING,
        (OrderStatus.SUBMITTING, "CANCEL"): OrderStatus.CANCEL_PENDING,
        (OrderStatus.ACKNOWLEDGED, "CANCEL"): OrderStatus.CANCEL_PENDING,
        (OrderStatus.PARTIALLY_FILLED, "CANCEL"): OrderStatus.CANCEL_PENDING,
    }
    target = transitions.get((state.status, command))
    if target is None:
        raise ValueError(f"invalid order command transition: {state.status}/{command}")
    return replace(
        state,
        status=target,
        version=state.version + 1,
        processed_command_ids=state.processed_command_ids + (command_id,),
        command_fingerprints=state.command_fingerprints + ((command_id, fingerprint),),
    )


def _record_order_event(
    state: OrderAggregate,
    event: OrderEvent,
    *,
    status: OrderStatus,
    filled: Decimal,
    fingerprint: str,
) -> OrderAggregate:
    return replace(
        state,
        status=status,
        cumulative_filled=filled,
        version=state.version + 1,
        last_sequence=max(state.last_sequence, event.sequence),
        processed_event_ids=state.processed_event_ids + (event.event_id,),
        event_fingerprints=state.event_fingerprints + ((event.event_id, fingerprint),),
    )


def apply_order_event(state: OrderAggregate, event: OrderEvent) -> OrderAggregate:
    """Fold exchange-like events deterministically; fills win cancel races."""

    fingerprint = _digest(event.sequence, event.kind, event.cumulative_filled)
    if _check_idempotency(state.event_fingerprints, event.event_id, fingerprint):
        return state
    if event.sequence < state.last_sequence:
        return state
    if event.sequence == state.last_sequence and state.last_sequence >= 0:
        return _record_order_event(
            state,
            event,
            status=OrderStatus.UNKNOWN_RECONCILE_REQUIRED,
            filled=state.cumulative_filled,
            fingerprint=fingerprint,
        )
    if state.last_sequence >= 0 and event.sequence > state.last_sequence + 1:
        return _record_order_event(
            state,
            event,
            status=OrderStatus.UNKNOWN_RECONCILE_REQUIRED,
            filled=state.cumulative_filled,
            fingerprint=fingerprint,
        )
    status = state.status
    filled = state.cumulative_filled
    if event.kind == "ACKNOWLEDGED":
        if status in {OrderStatus.SUBMITTING, OrderStatus.CANCEL_PENDING}:
            status = OrderStatus.ACKNOWLEDGED
        elif status not in {
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
        }:
            raise ValueError(f"invalid order event transition: {status}/{event.kind}")
    elif event.kind in {"PARTIAL_FILL", "FILL"}:
        if event.cumulative_filled < filled or event.cumulative_filled > state.quantity:
            raise ValueError("invalid cumulative fill quantity")
        filled = event.cumulative_filled
        status = OrderStatus.FILLED if filled == state.quantity else OrderStatus.PARTIALLY_FILLED
    elif event.kind == "CANCELLED":
        if status != OrderStatus.FILLED:
            status = OrderStatus.CANCELLED
    elif event.kind == "REJECTED" and status in {
        OrderStatus.VALIDATED,
        OrderStatus.SUBMITTING,
    }:
        status = OrderStatus.REJECTED
    elif event.kind == "EXPIRED" and status != OrderStatus.FILLED:
        status = OrderStatus.EXPIRED
    elif event.kind == "RECONCILE_UNKNOWN":
        status = OrderStatus.UNKNOWN_RECONCILE_REQUIRED
    else:
        raise ValueError(f"invalid order event transition: {status}/{event.kind}")
    return _record_order_event(
        state,
        event,
        status=status,
        filled=filled,
        fingerprint=fingerprint,
    )


def reconcile_order_snapshot(state: OrderAggregate, snapshot: OrderSnapshot) -> OrderAggregate:
    """Apply a REST snapshot only when it is at least as new and consistent."""

    fingerprint = _digest(
        snapshot.sequence, snapshot.status, snapshot.cumulative_filled, "REST_SNAPSHOT"
    )
    if _check_idempotency(state.event_fingerprints, snapshot.snapshot_id, fingerprint):
        return state
    if snapshot.sequence < state.last_sequence:
        return state
    if not Decimal("0") <= snapshot.cumulative_filled <= state.quantity:
        raise ValueError("invalid REST cumulative fill quantity")
    consistent_same_sequence = (
        snapshot.sequence == state.last_sequence
        and snapshot.status == state.status
        and snapshot.cumulative_filled == state.cumulative_filled
    )
    if consistent_same_sequence:
        return state
    status = snapshot.status
    filled = snapshot.cumulative_filled
    if filled < state.cumulative_filled:
        status = OrderStatus.UNKNOWN_RECONCILE_REQUIRED
        filled = state.cumulative_filled
    elif filled == state.quantity:
        status = OrderStatus.FILLED
    elif snapshot.sequence == state.last_sequence:
        status = OrderStatus.UNKNOWN_RECONCILE_REQUIRED
    event = OrderEvent(snapshot.snapshot_id, snapshot.sequence, "REST_SNAPSHOT", filled)
    return _record_order_event(
        state,
        event,
        status=status,
        filled=filled,
        fingerprint=fingerprint,
    )


def replay_order(initial: OrderAggregate, events: Iterable[OrderEvent]) -> OrderAggregate:
    state = initial
    for event in events:
        state = apply_order_event(state, event)
    return state


def apply_position_command(
    state: PositionAggregate,
    *,
    command_id: str,
    command: str,
    expected_version: int,
    payload_fingerprint: str = "",
) -> PositionAggregate:
    fingerprint = _digest(command, payload_fingerprint)
    if _check_idempotency(state.command_fingerprints, command_id, fingerprint):
        return state
    if expected_version != state.version:
        raise ConcurrencyConflict(
            f"expected aggregate version {expected_version}, found {state.version}"
        )
    transitions = {
        (PositionStatus.FLAT, "ENTER"): PositionStatus.ENTRY_PENDING,
        (PositionStatus.CLOSED, "ENTER"): PositionStatus.ENTRY_PENDING,
        (PositionStatus.OPEN, "EXIT"): PositionStatus.EXIT_PENDING,
        (PositionStatus.REDUCING, "EXIT"): PositionStatus.EXIT_PENDING,
        (PositionStatus.OPEN, "UPDATE_PROTECTION"): PositionStatus.OPEN,
        (PositionStatus.REDUCING, "UPDATE_PROTECTION"): PositionStatus.REDUCING,
    }
    target = transitions.get((state.status, command))
    reason = state.safe_error_reason
    if command == "KILL_SWITCH" and state.status not in {
        PositionStatus.FLAT,
        PositionStatus.CLOSED,
    }:
        target = PositionStatus.ERROR_SAFE
        reason = "KILL_SWITCH_ACTIVE"
    if target is None:
        raise ValueError(f"invalid position command transition: {state.status}/{command}")
    return replace(
        state,
        status=target,
        safe_error_reason=reason,
        version=state.version + 1,
        processed_command_ids=state.processed_command_ids + (command_id,),
        command_fingerprints=state.command_fingerprints + ((command_id, fingerprint),),
    )


def _position_event_fingerprint(event: PositionEvent) -> str:
    return _digest(
        event.sequence,
        event.kind,
        event.absolute_quantity,
        event.protected_quantity,
        event.stop_price,
        event.take_profit_price,
    )


def apply_position_event(state: PositionAggregate, event: PositionEvent) -> PositionAggregate:
    """Fold simulated fill/reconciliation events into authoritative position state."""

    fingerprint = _position_event_fingerprint(event)
    if _check_idempotency(state.event_fingerprints, event.event_id, fingerprint):
        return state
    if event.sequence < state.last_sequence:
        return state
    is_snapshot = event.kind == "RECONCILE_SNAPSHOT"
    if not is_snapshot and event.sequence == state.last_sequence and state.last_sequence >= 0:
        return replace(
            state,
            status=PositionStatus.RECONCILING,
            safe_error_reason="CONFLICTING_EVENT_SEQUENCE",
            version=state.version + 1,
            processed_event_ids=state.processed_event_ids + (event.event_id,),
            event_fingerprints=state.event_fingerprints + ((event.event_id, fingerprint),),
        )
    if not is_snapshot and state.last_sequence >= 0 and event.sequence > state.last_sequence + 1:
        return replace(
            state,
            status=PositionStatus.RECONCILING,
            safe_error_reason="EVENT_SEQUENCE_GAP",
            version=state.version + 1,
            last_sequence=event.sequence,
            processed_event_ids=state.processed_event_ids + (event.event_id,),
            event_fingerprints=state.event_fingerprints + ((event.event_id, fingerprint),),
        )
    quantity = event.absolute_quantity
    if quantity < 0 or event.protected_quantity < 0:
        raise ValueError("position and protection quantities cannot be negative")
    status = state.status
    protected = state.protected_quantity
    stop = state.stop_price
    take_profit = state.take_profit_price
    reason = state.safe_error_reason
    if event.kind == "ENTRY_INTENT" and status in {PositionStatus.FLAT, PositionStatus.CLOSED}:
        status = PositionStatus.ENTRY_PENDING
        quantity = state.absolute_quantity
    elif event.kind == "ENTRY_FILL" and status in {
        PositionStatus.ENTRY_PENDING,
        PositionStatus.OPEN,
        PositionStatus.ERROR_SAFE,
    }:
        if quantity <= state.absolute_quantity:
            raise ValueError("entry fill must increase authoritative position quantity")
        status = PositionStatus.OPEN
        if protected < quantity or stop is None:
            status = PositionStatus.ERROR_SAFE
            reason = "UNPROTECTED_POSITION_QUANTITY"
    elif event.kind == "PROTECTION_ACK" and state.absolute_quantity > 0:
        if event.protected_quantity < state.absolute_quantity or event.stop_price is None:
            status = PositionStatus.ERROR_SAFE
            reason = "INSUFFICIENT_PROTECTIVE_QUANTITY"
        else:
            protected = event.protected_quantity
            stop = (
                event.stop_price
                if stop is None
                else ratchet_stop(side=state.side, current=stop, candidate=event.stop_price)
            )
            take_profit = event.take_profit_price or take_profit
            reason = None
            status = (
                PositionStatus.REDUCING
                if state.status == PositionStatus.REDUCING
                else PositionStatus.OPEN
            )
        quantity = state.absolute_quantity
    elif event.kind == "PROTECTION_REJECTED" and state.absolute_quantity > 0:
        status = PositionStatus.ERROR_SAFE
        quantity = state.absolute_quantity
        reason = "PROTECTIVE_ORDER_REJECTED"
    elif event.kind == "EXIT_INTENT" and status in {
        PositionStatus.OPEN,
        PositionStatus.REDUCING,
        PositionStatus.ERROR_SAFE,
    }:
        status = PositionStatus.EXIT_PENDING
        quantity = state.absolute_quantity
    elif event.kind == "REDUCE_FILL" and status in {
        PositionStatus.OPEN,
        PositionStatus.REDUCING,
        PositionStatus.EXIT_PENDING,
        PositionStatus.ERROR_SAFE,
    }:
        if quantity > state.absolute_quantity:
            raise ValueError("reduce fill cannot increase position")
        protected = min(protected, quantity)
        if quantity == 0:
            status = PositionStatus.CLOSED
            protected = Decimal("0")
            stop = None
            take_profit = None
            reason = None
        elif protected < quantity or stop is None:
            status = PositionStatus.ERROR_SAFE
            reason = "UNPROTECTED_POSITION_QUANTITY"
        else:
            status = PositionStatus.REDUCING
            reason = None
    elif event.kind == "RECONCILE_UNKNOWN":
        status = PositionStatus.RECONCILING
        quantity = state.absolute_quantity
        reason = "RECONCILIATION_REQUIRED"
    elif event.kind == "RECONCILE_SNAPSHOT":
        if quantity == 0:
            status = PositionStatus.CLOSED
            protected = Decimal("0")
            stop = None
            take_profit = None
            reason = None
        elif protected < quantity or stop is None:
            status = PositionStatus.ERROR_SAFE
            reason = "RECONCILED_POSITION_UNPROTECTED"
        else:
            status = PositionStatus.OPEN
            reason = None
    elif event.kind == "MANUAL_ORDER_DETECTED":
        status = PositionStatus.RECONCILING
        quantity = state.absolute_quantity
        reason = "UNKNOWN_EXCHANGE_ORDER"
    elif event.kind == "NETWORK_PARTITION":
        status = PositionStatus.ERROR_SAFE
        quantity = state.absolute_quantity
        reason = "NETWORK_PARTITION"
    elif event.kind == "STALE_MARKET_DATA":
        status = PositionStatus.ERROR_SAFE
        quantity = state.absolute_quantity
        reason = "STALE_MARKET_DATA"
    elif event.kind == "ERROR":
        status = PositionStatus.ERROR_SAFE
        quantity = state.absolute_quantity
        reason = "UNCLASSIFIED_SAFE_ERROR"
    else:
        raise ValueError(f"invalid position event transition: {status}/{event.kind}")
    return replace(
        state,
        status=status,
        absolute_quantity=quantity,
        protected_quantity=protected,
        stop_price=stop,
        take_profit_price=take_profit,
        safe_error_reason=reason,
        version=state.version + 1,
        last_sequence=max(state.last_sequence, event.sequence),
        processed_event_ids=state.processed_event_ids + (event.event_id,),
        event_fingerprints=state.event_fingerprints + ((event.event_id, fingerprint),),
    )


def replay_position(
    initial: PositionAggregate, events: Iterable[PositionEvent]
) -> PositionAggregate:
    state = initial
    for event in events:
        state = apply_position_event(state, event)
    return state


def reconcile_account(snapshot: AccountSnapshot) -> AccountReconciliation:
    known = set(snapshot.known_open_order_ids)
    observed = set(snapshot.observed_open_order_ids)
    unknown = tuple(sorted(observed - known))
    missing = tuple(sorted(known - observed))
    return AccountReconciliation(
        healthy=not unknown and not missing,
        unknown_exchange_order_ids=unknown,
        missing_exchange_order_ids=missing,
    )


def new_exposure_blockers(
    health: SystemHealth, position: PositionAggregate | None = None
) -> tuple[str, ...]:
    blockers: list[str] = []
    if health.kill_switch_active:
        blockers.append("KILL_SWITCH_ACTIVE")
    if not health.network_connected:
        blockers.append("NETWORK_DISCONNECTED")
    if not health.market_data_fresh:
        blockers.append("STALE_MARKET_DATA")
    if not health.reconciliation_healthy:
        blockers.append("RECONCILIATION_UNHEALTHY")
    if not health.single_writer_lease:
        blockers.append("SINGLE_WRITER_LEASE_MISSING")
    if position is not None and not position.protection_healthy:
        blockers.append("POSITION_PROTECTION_UNHEALTHY")
    return tuple(blockers)


def validate_order_filters(*, quantity: Decimal, step_size: Decimal, minimum: Decimal) -> None:
    if quantity <= 0 or step_size <= 0 or minimum <= 0:
        raise ValueError("order filter quantities must be positive")
    if quantity < minimum or quantity % step_size != 0:
        raise ValueError("order quantity violates frozen exchange filters")


def ratchet_stop(*, side: str, current: Decimal, candidate: Decimal) -> Decimal:
    """Return a monotonic stop; long stops never fall and short stops never rise."""

    if side == "LONG":
        return max(current, candidate)
    if side == "SHORT":
        return min(current, candidate)
    raise ValueError(f"unknown side: {side}")
