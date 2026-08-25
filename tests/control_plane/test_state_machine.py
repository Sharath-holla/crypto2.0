from decimal import Decimal

import pytest

from crypto_ai.control_plane.state_machine import (
    ConcurrencyConflict,
    OrderAggregate,
    OrderEvent,
    OrderStatus,
    PositionAggregate,
    PositionEvent,
    PositionStatus,
    apply_order_command,
    apply_order_event,
    apply_position_event,
    ratchet_stop,
)


def _submitting() -> OrderAggregate:
    state = OrderAggregate("intent-1", Decimal("2"))
    state = apply_order_command(
        state, command_id="validate", command="VALIDATE", expected_version=0
    )
    return apply_order_command(state, command_id="submit", command="SUBMIT", expected_version=1)


def test_duplicate_command_is_idempotent_and_two_writers_conflict() -> None:
    state = OrderAggregate("intent-1", Decimal("1"))
    validated = apply_order_command(
        state, command_id="same", command="VALIDATE", expected_version=0
    )
    assert (
        apply_order_command(validated, command_id="same", command="VALIDATE", expected_version=0)
        == validated
    )
    with pytest.raises(ConcurrencyConflict):
        apply_order_command(
            validated, command_id="other-writer", command="SUBMIT", expected_version=0
        )


def test_partial_fill_then_cancel_and_fill_cancel_race() -> None:
    state = apply_order_event(_submitting(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = apply_order_event(state, OrderEvent("partial", 2, "PARTIAL_FILL", Decimal("0.5")))
    state = apply_order_command(
        state, command_id="cancel", command="CANCEL", expected_version=state.version
    )
    filled = apply_order_event(state, OrderEvent("fill", 3, "FILL", Decimal("2")))
    assert filled.status == OrderStatus.FILLED
    assert (
        apply_order_event(filled, OrderEvent("late-cancel", 4, "CANCELLED")).status
        == OrderStatus.FILLED
    )


def test_out_of_order_and_duplicate_events_do_not_rewind_state() -> None:
    state = apply_order_event(_submitting(), OrderEvent("ack", 2, "ACKNOWLEDGED"))
    assert apply_order_event(state, OrderEvent("stale", 1, "CANCELLED")) == state
    assert apply_order_event(state, OrderEvent("ack", 2, "ACKNOWLEDGED")) == state


def test_unknown_state_requires_reconciliation_and_stop_is_monotonic() -> None:
    state = apply_order_event(_submitting(), OrderEvent("unknown", 1, "RECONCILE_UNKNOWN"))
    assert state.status == OrderStatus.UNKNOWN_RECONCILE_REQUIRED
    assert ratchet_stop(side="LONG", current=Decimal("102"), candidate=Decimal("98")) == Decimal(
        "102"
    )
    assert ratchet_stop(side="SHORT", current=Decimal("98"), candidate=Decimal("102")) == Decimal(
        "98"
    )


def test_position_replay_handles_partial_exit_and_manual_exchange_close() -> None:
    state = PositionAggregate("BTCUSDT")
    state = apply_position_event(state, PositionEvent("intent", 1, "ENTRY_INTENT"))
    state = apply_position_event(state, PositionEvent("entry", 2, "ENTRY_FILL", Decimal("2")))
    state = apply_position_event(
        state,
        PositionEvent(
            "protect",
            3,
            "PROTECTION_ACK",
            protected_quantity=Decimal("2"),
            stop_price=Decimal("95"),
        ),
    )
    state = apply_position_event(state, PositionEvent("exit", 4, "EXIT_INTENT"))
    state = apply_position_event(state, PositionEvent("partial", 5, "REDUCE_FILL", Decimal("1")))
    assert state.status == PositionStatus.REDUCING
    reconciled = apply_position_event(
        state, PositionEvent("manual-close", 6, "RECONCILE_SNAPSHOT", Decimal("0"))
    )
    assert reconciled.status == PositionStatus.CLOSED
    assert reconciled.absolute_quantity == 0
