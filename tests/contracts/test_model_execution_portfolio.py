from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from crypto_ai.contracts.execution import (
    DisabledExecutionAdapter,
    ExecutionAdapter,
    IntentStatus,
    OrderIntent,
    OrderPurpose,
    OrderSide,
)
from crypto_ai.contracts.models import (
    ModelArchitecture,
    ModelContract,
    ModelDeploymentMetadata,
    ModelLifecycle,
    PredictionEnvelope,
    RuntimeMode,
)
from crypto_ai.contracts.portfolio import (
    ExposureProposal,
    PortfolioDecision,
    PortfolioDecisionStatus,
    PortfolioPolicy,
    PortfolioSnapshot,
    PositionView,
)
from crypto_ai.contracts.versioning import SemanticVersion

DIGEST = "a" * 64
FEATURE_TIME = datetime(2026, 6, 1, 10, tzinfo=UTC)


def _prediction(**changes: object) -> PredictionEnvelope:
    base = {
        "prediction_id": "prediction-1",
        "contract_version": SemanticVersion(1, 0, 0),
        "model_id": "phase7-g0",
        "model_version": "candidate-1",
        "symbol": "BTCUSDT",
        "feature_time": FEATURE_TIME,
        "emitted_at": FEATURE_TIME + timedelta(seconds=1),
        "earliest_action_time": FEATURE_TIME + timedelta(minutes=5),
        "horizon_minutes": 60,
        "decision_latency_bars": 1,
        "bar_interval_minutes": 5,
        "target_version": "multiasset_targets_v2",
        "input_lineage_sha256": DIGEST,
        "expected_return": Decimal("0.0012"),
    }
    base.update(changes)
    return PredictionEnvelope(**base)  # type: ignore[arg-type]


def test_prediction_contract_enforces_one_complete_bar_latency() -> None:
    prediction = _prediction()
    assert prediction.earliest_action_time == prediction.feature_time + timedelta(minutes=5)
    with pytest.raises(ValueError, match="declared decision latency"):
        _prediction(earliest_action_time=FEATURE_TIME)


def test_prediction_requires_forecast_or_explicit_no_trade_reason() -> None:
    no_trade = _prediction(expected_return=None, no_trade_reason="INSUFFICIENT_COVERAGE")
    assert no_trade.no_trade_reason == "INSUFFICIENT_COVERAGE"
    with pytest.raises(ValueError, match="requires"):
        _prediction(expected_return=None)
    with pytest.raises(ValueError, match="mutually exclusive"):
        _prediction(no_trade_reason="CONFLICT")


def test_model_contract_carries_lineage_and_cutoff_without_runtime_behavior() -> None:
    contract = ModelContract(
        contract_version=SemanticVersion(1, 0, 0),
        model_id="phase7-g0",
        model_version="candidate-1",
        architecture=ModelArchitecture.G0,
        feature_contract="multiasset_features_v2",
        target_contract="multiasset_targets_v2",
        configuration_hash="68e4b39899f8c9f0542d227b",
        code_revision="dd978b9",
        artifact_sha256=DIGEST,
        input_schema_sha256=DIGEST,
        output_schema_sha256=DIGEST,
        trained_through_exclusive=datetime(2026, 7, 1, tzinfo=UTC),
        research_cutoff_exclusive=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert len(contract.identity_sha256) == 64
    with pytest.raises(ValueError, match="cannot exceed"):
        ModelContract(
            **{
                name: getattr(contract, name)
                for name in (
                    "contract_version",
                    "model_id",
                    "model_version",
                    "architecture",
                    "feature_contract",
                    "target_contract",
                    "configuration_hash",
                    "code_revision",
                    "artifact_sha256",
                    "input_schema_sha256",
                    "output_schema_sha256",
                    "research_cutoff_exclusive",
                )
            },
            trained_through_exclusive=datetime(2026, 7, 2, tzinfo=UTC),
        )


def test_deployment_metadata_cannot_authorize_activation_without_approval() -> None:
    with pytest.raises(ValueError, match="approval"):
        ModelDeploymentMetadata(
            model_identity_sha256=DIGEST,
            lifecycle=ModelLifecycle.VALIDATED,
            requested_runtime_mode=RuntimeMode.SHADOW,
            activation_authorized=True,
            validation_report_sha256=DIGEST,
        )


def _intent() -> OrderIntent:
    return OrderIntent(
        intent_id="intent-1",
        idempotency_key="retry-safe-1",
        strategy_decision_id="decision-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        purpose=OrderPurpose.ENTRY,
        quantity=Decimal("0.001"),
        created_at=FEATURE_TIME,
        expires_at=FEATURE_TIME + timedelta(minutes=1),
        reduce_only=False,
    )


def test_only_concrete_execution_adapter_is_disabled_and_side_effect_free() -> None:
    adapter = DisabledExecutionAdapter()
    assert isinstance(adapter, ExecutionAdapter)
    assert adapter.capabilities.phase7_1b_safe
    assert adapter.submit(_intent()).status == IntentStatus.BLOCKED
    assert adapter.cancel(intent_id="intent-1", idempotency_key="cancel-1").status == (
        IntentStatus.BLOCKED
    )
    assert adapter.reconcile() == ()


def test_reduce_exit_and_protection_intents_must_be_reduce_only() -> None:
    base = _intent()
    for purpose in (OrderPurpose.REDUCE, OrderPurpose.EXIT, OrderPurpose.PROTECTION):
        with pytest.raises(ValueError, match="reduce-only"):
            OrderIntent(
                intent_id=base.intent_id,
                idempotency_key=base.idempotency_key,
                strategy_decision_id=base.strategy_decision_id,
                symbol=base.symbol,
                side=base.side,
                purpose=purpose,
                quantity=base.quantity,
                created_at=base.created_at,
                expires_at=base.expires_at,
                reduce_only=False,
            )


class _RejectingPolicy:
    def evaluate(
        self, snapshot: PortfolioSnapshot, proposal: ExposureProposal
    ) -> PortfolioDecision:
        return PortfolioDecision(
            proposal_id=proposal.proposal_id,
            snapshot_id=snapshot.snapshot_id,
            status=PortfolioDecisionStatus.REJECTED,
            reason_codes=("FOUNDATION_ONLY",),
            policy_version="portfolio_policy_contract_v1",
        )


def test_portfolio_boundary_is_an_interface_over_external_quantity() -> None:
    snapshot = PortfolioSnapshot(
        snapshot_id="portfolio-1",
        schema_version="1.0.0",
        as_of=FEATURE_TIME,
        base_currency="USDT",
        cash_balance=Decimal("1000"),
        gross_notional=Decimal("0"),
        net_notional=Decimal("0"),
        positions=(),
        source_sequence=0,
    )
    proposal = ExposureProposal(
        proposal_id="proposal-1",
        prediction_id="prediction-1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        externally_supplied_quantity=Decimal("0.001"),
        reference_price=Decimal("50000"),
        created_at=FEATURE_TIME,
    )
    policy = _RejectingPolicy()
    assert isinstance(policy, PortfolioPolicy)
    assert policy.evaluate(snapshot, proposal).status == PortfolioDecisionStatus.REJECTED


def test_portfolio_snapshot_rejects_duplicate_symbol_state() -> None:
    position = PositionView("BTCUSDT", Decimal("1"), Decimal("50000"), None, FEATURE_TIME)
    with pytest.raises(ValueError, match="duplicate"):
        PortfolioSnapshot(
            "portfolio-1",
            "1.0.0",
            FEATURE_TIME,
            "USDT",
            Decimal("0"),
            Decimal("100000"),
            Decimal("100000"),
            (position, position),
            1,
        )


def test_new_contracts_contain_no_automatic_exposure_multiplier_fields() -> None:
    contract_fields = {
        field.name
        for contract_type in (OrderIntent, ExposureProposal, PortfolioSnapshot)
        for field in fields(contract_type)
    }
    assert "leverage" not in contract_fields
    assert "leverage_multiplier" not in contract_fields
