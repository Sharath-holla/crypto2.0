from datetime import UTC, datetime
from decimal import Decimal

from crypto_ai.contracts.models import RuntimeMode
from crypto_ai.contracts.observability import (
    FailClosedFoundationPolicy,
    FailureClass,
    FailureContext,
    HealthStatus,
    MetricPoint,
)
from crypto_ai.contracts.views import DashboardSnapshot

NOW = datetime(2026, 6, 1, tzinfo=UTC)


def test_fail_closed_policy_blocks_contract_and_reconciliation_failures() -> None:
    policy = FailClosedFoundationPolicy()
    contract = policy.decide(
        FailureContext(FailureClass.CONTRACT_VIOLATION, "model", "predict", NOW, 0, False)
    )
    assert contract.block_new_actions
    assert contract.quarantine_component
    assert contract.reconciliation_required


def test_dependency_retry_is_bounded_and_never_unblocks_new_actions() -> None:
    policy = FailClosedFoundationPolicy()
    first = policy.decide(
        FailureContext(FailureClass.DEPENDENCY_UNAVAILABLE, "store", "read", NOW, 0, True)
    )
    exhausted = policy.decide(
        FailureContext(FailureClass.DEPENDENCY_UNAVAILABLE, "store", "read", NOW, 3, True)
    )
    assert first.retry_allowed and first.block_new_actions
    assert not exhausted.retry_allowed and exhausted.block_new_actions


def test_metric_labels_must_be_unique() -> None:
    point = MetricPoint("event_lag", Decimal("1.25"), "seconds", NOW, (("stream", "orders"),))
    assert point.value == Decimal("1.25")


def test_dashboard_contract_is_read_only_and_versioned() -> None:
    snapshot = DashboardSnapshot(
        schema_version="1.0.0",
        projection_version=0,
        as_of=NOW,
        runtime_mode=RuntimeMode.DISABLED,
        overall_health=HealthStatus.UNKNOWN,
        predictions=(),
        orders=(),
        positions=(),
        alerts=(),
    )
    assert snapshot.runtime_mode == RuntimeMode.DISABLED
    assert not hasattr(snapshot, "submit")
    assert not hasattr(snapshot, "cancel")
