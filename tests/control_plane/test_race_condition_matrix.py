from decimal import Decimal

import pytest

from crypto_ai.control_plane.state_machine import (
    AccountSnapshot,
    ConcurrencyConflict,
    IdempotencyConflict,
    OrderAggregate,
    OrderEvent,
    OrderSnapshot,
    OrderStatus,
    PositionAggregate,
    PositionEvent,
    PositionStatus,
    SystemHealth,
    apply_order_command,
    apply_order_event,
    apply_position_command,
    apply_position_event,
    make_exchange_client_order_id,
    new_exposure_blockers,
    ratchet_stop,
    reconcile_account,
    reconcile_order_snapshot,
    replay_order,
    replay_position,
    validate_order_filters,
)


def _submitted(quantity: str = "2") -> OrderAggregate:
    state = OrderAggregate("intent-1", Decimal(quantity))
    state = apply_order_command(
        state, command_id="validate", command="VALIDATE", expected_version=0
    )
    return apply_order_command(
        state, command_id="submit", command="SUBMIT", expected_version=state.version
    )


def _protected_position(quantity: str = "2") -> PositionAggregate:
    state = apply_position_command(
        PositionAggregate("BTCUSDT"),
        command_id="enter",
        command="ENTER",
        expected_version=0,
    )
    state = apply_position_event(state, PositionEvent("fill", 1, "ENTRY_FILL", Decimal(quantity)))
    return apply_position_event(
        state,
        PositionEvent(
            "protect",
            2,
            "PROTECTION_ACK",
            protected_quantity=Decimal(quantity),
            stop_price=Decimal("95"),
            take_profit_price=Decimal("110"),
        ),
    )


def test_01_duplicate_dashboard_click_is_idempotent() -> None:
    state = PositionAggregate("BTCUSDT")
    entered = apply_position_command(
        state, command_id="click-1", command="ENTER", expected_version=0
    )
    assert (
        apply_position_command(entered, command_id="click-1", command="ENTER", expected_version=0)
        == entered
    )


def test_02_duplicate_strategy_decision_has_stable_client_order_id() -> None:
    first = make_exchange_client_order_id("decision-1", "intent-1")
    assert first == make_exchange_client_order_id("decision-1", "intent-1")
    assert first != make_exchange_client_order_id("decision-2", "intent-1")


def test_03_retry_after_timeout_does_not_resubmit() -> None:
    submitted = _submitted()
    assert (
        apply_order_command(submitted, command_id="submit", command="SUBMIT", expected_version=1)
        == submitted
    )


def test_04_same_idempotency_key_and_payload_returns_existing_result() -> None:
    state = OrderAggregate("intent-1", Decimal("2"))
    validated = apply_order_command(
        state,
        command_id="validate",
        command="VALIDATE",
        expected_version=0,
        payload_fingerprint="quantity=2",
    )
    assert (
        apply_order_command(
            validated,
            command_id="validate",
            command="VALIDATE",
            expected_version=0,
            payload_fingerprint="quantity=2",
        )
        == validated
    )


def test_05_same_idempotency_key_with_conflicting_payload_fails() -> None:
    state = apply_order_command(
        OrderAggregate("intent-1", Decimal("2")),
        command_id="validate",
        command="VALIDATE",
        expected_version=0,
        payload_fingerprint="quantity=2",
    )
    with pytest.raises(IdempotencyConflict):
        apply_order_command(
            state,
            command_id="validate",
            command="VALIDATE",
            expected_version=0,
            payload_fingerprint="quantity=3",
        )


def test_06_two_order_workers_cannot_submit_same_version() -> None:
    state = apply_order_command(
        OrderAggregate("intent-1", Decimal("2")),
        command_id="validate",
        command="VALIDATE",
        expected_version=0,
    )
    written = apply_order_command(
        state, command_id="worker-a", command="SUBMIT", expected_version=state.version
    )
    with pytest.raises(ConcurrencyConflict):
        apply_order_command(
            written, command_id="worker-b", command="SUBMIT", expected_version=state.version
        )


def test_07_two_position_workers_cannot_update_same_version() -> None:
    state = _protected_position()
    written = apply_position_command(
        state,
        command_id="protect-a",
        command="UPDATE_PROTECTION",
        expected_version=state.version,
    )
    with pytest.raises(ConcurrencyConflict):
        apply_position_command(
            written,
            command_id="protect-b",
            command="UPDATE_PROTECTION",
            expected_version=state.version,
        )


def test_08_partial_entry_fill_during_protection_update_fails_safe_until_covered() -> None:
    state = _protected_position("1")
    state = apply_position_event(state, PositionEvent("second-fill", 3, "ENTRY_FILL", Decimal("2")))
    assert state.status == PositionStatus.ERROR_SAFE
    assert state.safe_error_reason == "UNPROTECTED_POSITION_QUANTITY"
    state = apply_position_event(
        state,
        PositionEvent(
            "protect-two",
            4,
            "PROTECTION_ACK",
            protected_quantity=Decimal("2"),
            stop_price=Decimal("96"),
        ),
    )
    assert state.status == PositionStatus.OPEN
    assert state.protection_healthy


def test_09_partial_fill_followed_by_cancel_preserves_filled_quantity() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = apply_order_event(state, OrderEvent("partial", 2, "PARTIAL_FILL", Decimal("0.5")))
    state = apply_order_command(
        state, command_id="cancel", command="CANCEL", expected_version=state.version
    )
    state = apply_order_event(state, OrderEvent("cancelled", 3, "CANCELLED"))
    assert state.status == OrderStatus.CANCELLED
    assert state.cumulative_filled == Decimal("0.5")


def test_10_fill_arriving_while_cancel_pending_wins() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = apply_order_command(
        state, command_id="cancel", command="CANCEL", expected_version=state.version
    )
    state = apply_order_event(state, OrderEvent("fill", 2, "FILL", Decimal("2")))
    assert state.status == OrderStatus.FILLED


def test_11_cancel_then_later_fill_cannot_erase_exposure() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = apply_order_command(
        state, command_id="cancel", command="CANCEL", expected_version=state.version
    )
    state = apply_order_event(state, OrderEvent("cancelled", 2, "CANCELLED"))
    state = apply_order_event(state, OrderEvent("late-fill", 3, "FILL", Decimal("2")))
    assert state.status == OrderStatus.FILLED


def test_12_websocket_fill_before_rest_submit_response_does_not_rewind() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ws-fill", 1, "FILL", Decimal("2")))
    state = apply_order_event(state, OrderEvent("late-ack", 2, "ACKNOWLEDGED"))
    assert state.status == OrderStatus.FILLED


def test_13_newer_rest_snapshot_is_authoritative() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = reconcile_order_snapshot(
        state, OrderSnapshot("rest", 2, OrderStatus.FILLED, Decimal("2"))
    )
    assert state.status == OrderStatus.FILLED


def test_14_stale_rest_snapshot_is_ignored() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 2, "ACKNOWLEDGED"))
    stale = OrderSnapshot("stale", 1, OrderStatus.CREATED, Decimal("0"))
    assert reconcile_order_snapshot(state, stale) == state


def test_15_duplicate_websocket_event_is_idempotent() -> None:
    event = OrderEvent("ack", 1, "ACKNOWLEDGED")
    state = apply_order_event(_submitted(), event)
    assert apply_order_event(state, event) == state


def test_16_out_of_order_event_does_not_rewind_state() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 2, "ACKNOWLEDGED"))
    assert apply_order_event(state, OrderEvent("old", 1, "CANCELLED")) == state


def test_17_event_sequence_gap_requires_reconciliation() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = apply_order_event(state, OrderEvent("gap", 3, "CANCELLED"))
    assert state.status == OrderStatus.UNKNOWN_RECONCILE_REQUIRED


def test_18_crash_before_submit_leaves_no_submitted_state() -> None:
    state = apply_order_command(
        OrderAggregate("intent-1", Decimal("2")),
        command_id="validate",
        command="VALIDATE",
        expected_version=0,
    )
    assert state.status == OrderStatus.VALIDATED
    assert "submit" not in state.processed_command_ids


def test_19_crash_after_submit_before_ack_is_recovered_by_rest() -> None:
    state = _submitted()
    client_id = make_exchange_client_order_id("decision-1", state.order_intent_id)
    recovered = reconcile_order_snapshot(
        state, OrderSnapshot("rest-ack", 1, OrderStatus.ACKNOWLEDGED, Decimal("0"))
    )
    assert client_id == make_exchange_client_order_id("decision-1", state.order_intent_id)
    assert recovered.status == OrderStatus.ACKNOWLEDGED


def test_20_restart_event_replay_reproduces_order_state() -> None:
    events = (
        OrderEvent("ack", 1, "ACKNOWLEDGED"),
        OrderEvent("partial", 2, "PARTIAL_FILL", Decimal("1")),
        OrderEvent("fill", 3, "FILL", Decimal("2")),
    )
    assert replay_order(_submitted(), events) == replay_order(_submitted(), events)


def test_21_reconnect_snapshot_recovers_disconnected_fill() -> None:
    state = apply_order_event(_submitted(), OrderEvent("ack", 1, "ACKNOWLEDGED"))
    state = reconcile_order_snapshot(
        state, OrderSnapshot("reconnect", 2, OrderStatus.FILLED, Decimal("2"))
    )
    assert state.status == OrderStatus.FILLED


def test_22_manual_exchange_close_is_authoritative() -> None:
    state = _protected_position()
    state = apply_position_event(
        state, PositionEvent("manual-close", 3, "RECONCILE_SNAPSHOT", Decimal("0"))
    )
    assert state.status == PositionStatus.CLOSED
    assert state.absolute_quantity == 0


def test_23_manual_exchange_order_forces_reconciliation() -> None:
    result = reconcile_account(AccountSnapshot("account", ("known-1",), ("known-1", "manual-1")))
    assert not result.healthy
    assert result.unknown_exchange_order_ids == ("manual-1",)


def test_24_rejected_protective_order_enters_error_safe() -> None:
    state = apply_position_command(
        PositionAggregate("BTCUSDT"),
        command_id="enter",
        command="ENTER",
        expected_version=0,
    )
    state = apply_position_event(state, PositionEvent("fill", 1, "ENTRY_FILL", Decimal("1")))
    state = apply_position_event(state, PositionEvent("reject", 2, "PROTECTION_REJECTED"))
    assert state.status == PositionStatus.ERROR_SAFE
    assert state.safe_error_reason == "PROTECTIVE_ORDER_REJECTED"


def test_25_partial_reduce_only_fill_keeps_remaining_quantity_protected() -> None:
    state = _protected_position("2")
    state = apply_position_command(
        state, command_id="exit", command="EXIT", expected_version=state.version
    )
    state = apply_position_event(
        state, PositionEvent("partial-exit", 3, "REDUCE_FILL", Decimal("1"))
    )
    assert state.status == PositionStatus.REDUCING
    assert state.protected_quantity == Decimal("1")
    assert state.protection_healthy


def test_26_stop_updates_cannot_loosen_long_or_short_protection() -> None:
    assert ratchet_stop(side="LONG", current=Decimal("102"), candidate=Decimal("98")) == Decimal(
        "102"
    )
    assert ratchet_stop(side="SHORT", current=Decimal("98"), candidate=Decimal("102")) == Decimal(
        "98"
    )


def test_27_exchange_filter_change_rejects_invalid_quantity() -> None:
    validate_order_filters(
        quantity=Decimal("1.0"), step_size=Decimal("0.1"), minimum=Decimal("0.1")
    )
    with pytest.raises(ValueError):
        validate_order_filters(
            quantity=Decimal("1.05"), step_size=Decimal("0.1"), minimum=Decimal("0.1")
        )


def test_28_network_partition_blocks_new_exposure() -> None:
    assert "NETWORK_DISCONNECTED" in new_exposure_blockers(SystemHealth(network_connected=False))


def test_29_stale_market_data_blocks_new_exposure() -> None:
    assert "STALE_MARKET_DATA" in new_exposure_blockers(SystemHealth(market_data_fresh=False))


def test_30_kill_switch_during_partial_fill_never_marks_position_closed() -> None:
    state = _protected_position("1")
    state = apply_position_event(state, PositionEvent("second-fill", 3, "ENTRY_FILL", Decimal("2")))
    state = apply_position_command(
        state, command_id="kill", command="KILL_SWITCH", expected_version=state.version
    )
    assert state.status == PositionStatus.ERROR_SAFE
    assert state.absolute_quantity == Decimal("2")
    assert state.safe_error_reason == "KILL_SWITCH_ACTIVE"


def test_31_database_transaction_version_conflict_fails() -> None:
    state = _protected_position()
    with pytest.raises(ConcurrencyConflict):
        apply_position_command(
            state,
            command_id="stale-writer",
            command="UPDATE_PROTECTION",
            expected_version=state.version - 1,
        )


def test_32_position_replay_is_deterministic() -> None:
    initial = apply_position_command(
        PositionAggregate("BTCUSDT"),
        command_id="enter",
        command="ENTER",
        expected_version=0,
    )
    events = (
        PositionEvent("fill", 1, "ENTRY_FILL", Decimal("1")),
        PositionEvent(
            "protect",
            2,
            "PROTECTION_ACK",
            protected_quantity=Decimal("1"),
            stop_price=Decimal("95"),
        ),
    )
    assert replay_position(initial, events) == replay_position(initial, events)


def test_33_retried_fill_event_cannot_create_duplicate_exposure() -> None:
    event = OrderEvent("fill", 1, "FILL", Decimal("2"))
    state = apply_order_event(_submitted(), event)
    replayed = apply_order_event(state, event)
    assert replayed.cumulative_filled == Decimal("2")
    assert replayed == state


def test_34_order_cancellation_never_falsely_closes_position() -> None:
    position = _protected_position()
    order = apply_order_event(_submitted(), OrderEvent("cancel", 1, "CANCELLED"))
    assert order.status == OrderStatus.CANCELLED
    assert position.status == PositionStatus.OPEN
    assert position.absolute_quantity == Decimal("2")


def test_35_unprotected_position_has_explicit_alarm_and_blocks_exposure() -> None:
    state = apply_position_command(
        PositionAggregate("BTCUSDT"),
        command_id="enter",
        command="ENTER",
        expected_version=0,
    )
    state = apply_position_event(state, PositionEvent("fill", 1, "ENTRY_FILL", Decimal("1")))
    assert state.status == PositionStatus.ERROR_SAFE
    assert state.safe_error_reason == "UNPROTECTED_POSITION_QUANTITY"
    assert "POSITION_PROTECTION_UNHEALTHY" in new_exposure_blockers(SystemHealth(), state)
