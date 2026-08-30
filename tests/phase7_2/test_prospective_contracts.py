from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_ai.phase7_2.challengers import (
    TRIAL_FAMILIES,
    CalibrationMethod,
    CalibrationPlan,
    ExperimentTrial,
    MatchedCoverage,
    ModelComparisonKey,
    OpportunityScore,
    TreeChallengerSpec,
    TreeEstimatorFamily,
)
from crypto_ai.phase7_2.metrics import brier_score, ndcg_at_k, pinball_loss
from crypto_ai.phase7_2.prospective import ProspectiveSymbolPolicy, default_capture_plan
from crypto_ai.phase7_2.schemas import (
    BBOObservation,
    DataQualityStatus,
    DepthSummary,
    EventContext,
    ExchangeSymbolMetadata,
    LiquidationEvent,
    LiquidationSide,
    OpenInterestObservation,
)


def _times() -> tuple[datetime, datetime, datetime]:
    event = datetime(2026, 8, 29, tzinfo=UTC)
    return event, event + timedelta(seconds=1), event + timedelta(seconds=2)


def test_open_interest_schema_is_forward_only_and_serializable() -> None:
    event, received, available = _times()
    row = OpenInterestObservation(
        symbol="BTCUSDT",
        event_time=event,
        received_time=received,
        availability_time=available,
        source="binance-usdm-public",
        quality_status=DataQualityStatus.VALID,
        open_interest=Decimal("123.456"),
        open_interest_value=Decimal("12000000.01"),
    )
    assert OpenInterestObservation.model_validate_json(row.to_json()) == row
    assert row.training_eligibility == "FORWARD_ONLY"


def test_bbo_schema_enforces_exact_book_arithmetic() -> None:
    event, received, available = _times()
    row = BBOObservation(
        symbol="BTCUSDT",
        event_time=event,
        received_time=received,
        availability_time=available,
        source="binance-usdm-public",
        quality_status=DataQualityStatus.VALID,
        bid=Decimal("99"),
        ask=Decimal("101"),
        bid_quantity=Decimal("2"),
        ask_quantity=Decimal("3"),
        mid=Decimal("100"),
        spread=Decimal("2"),
        spread_bps=Decimal("200"),
        sequence=1,
    )
    assert BBOObservation.model_validate_json(row.to_json()) == row
    with pytest.raises(ValidationError, match="mid/spread"):
        BBOObservation.model_validate({**row.model_dump(), "mid": Decimal("99")})


def test_depth_summary_and_liquidation_event_round_trip() -> None:
    event, received, available = _times()
    common = {
        "symbol": "ETHUSDT",
        "event_time": event,
        "received_time": received,
        "availability_time": available,
        "source": "binance-usdm-public",
        "quality_status": DataQualityStatus.VALID,
    }
    depth = DepthSummary(
        **common,
        depth_10bps_bid=Decimal("10"),
        depth_10bps_ask=Decimal("9"),
        depth_25bps_bid=Decimal("20"),
        depth_25bps_ask=Decimal("18"),
        depth_50bps_bid=Decimal("40"),
        depth_50bps_ask=Decimal("36"),
        imbalance=Decimal("0.05"),
        microprice=Decimal("100.1"),
        spread=Decimal("0.2"),
        sequence_healthy=True,
    )
    liquidation = LiquidationEvent(
        **common,
        side=LiquidationSide.SELL,
        price=Decimal("100"),
        quantity=Decimal("2"),
        notional=Decimal("200"),
    )
    assert DepthSummary.model_validate_json(depth.to_json()) == depth
    assert LiquidationEvent.model_validate_json(liquidation.to_json()) == liquidation


def test_exchange_metadata_has_effective_and_availability_time() -> None:
    event, _, available = _times()
    metadata = ExchangeSymbolMetadata(
        symbol="BTCUSDT",
        effective_from=event,
        effective_to=None,
        availability_time=available,
        trading_status="TRADING",
        onboard_time=event - timedelta(days=1),
        delist_time=None,
        tick_size=Decimal("0.1"),
        quantity_step=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        minimum_notional=Decimal("5"),
        funding_interval_minutes=480,
        contract_type="PERPETUAL",
        source_version="exchange-info-2026-08-29",
    )
    assert ExchangeSymbolMetadata.model_validate_json(metadata.to_json()) == metadata


def test_event_context_is_late_fusion_metadata_only() -> None:
    event, received, available = _times()
    context = EventContext(
        event_id="event-1",
        entities=("BTCUSDT",),
        event_type="EXCHANGE_INCIDENT",
        publisher_time=event,
        first_seen_time=received,
        ingestion_time=available,
        revision_time=None,
        novelty=Decimal("0.8"),
        severity=Decimal("0.7"),
        direction_hint=None,
        horizon_hint="SHORT",
        source_quality=DataQualityStatus.VALID,
        confidence=Decimal("0.6"),
    )
    assert EventContext.model_validate_json(context.to_json()) == context


def test_prospective_capture_plan_and_symbol_policy_are_disabled() -> None:
    policy = ProspectiveSymbolPolicy(max_symbols=3)
    selected = policy.select(
        fold_active_core=("BTCUSDT", "ETHUSDT"),
        fold_active_expansion=("SOLUSDT", "NEWUSDT"),
    )
    assert selected == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert policy.enabled is False
    assert all(not item.enabled and not item.network_enabled for item in default_capture_plan())


def test_tree_challengers_share_matched_inputs_and_remain_disabled() -> None:
    common = {
        "feature_schema": "multiasset_features_v2",
        "target_schema": "multiasset_targets_v2",
        "fold_schema": "phase7_walkforward_v1",
        "universe_schema": "fold_active_symbols",
        "calibration_schema": "cal_a_cal_b_v1",
        "cost_schema": "phase7_costs_v1",
    }
    catboost = TreeChallengerSpec(TreeEstimatorFamily.CATBOOST, **common)
    xgboost = TreeChallengerSpec(TreeEstimatorFamily.XGBOOST, **common)
    assert catboost.enabled is xgboost.enabled is False
    assert catboost.training_enabled is xgboost.training_enabled is False
    assert catboost.feature_schema == xgboost.feature_schema


def test_model_comparison_identity_and_matched_coverage() -> None:
    key = ModelComparisonKey(
        symbol="BTCUSDT",
        feature_time=datetime(2025, 1, 1, tzinfo=UTC),
        target="multiasset_targets_v2:60m:raw",
        horizon_minutes=60,
        universe_version="expansion_universe_v2",
        fold_id="fold-001",
        cost_model="phase7_costs_v1",
        feature_schema="multiasset_features_v2",
    )
    assert len(key.identity_sha256) == 64
    assert MatchedCoverage(native_rows=100, matched_rows=80).matched_fraction == 0.8


def test_calibration_ownership_and_trial_registry_are_explicit() -> None:
    plan = CalibrationPlan(CalibrationMethod.ISOTONIC)
    assert plan.prediction_calibration_owner == "CAL_A"
    assert plan.policy_threshold_owner == "CAL_B"
    assert plan.enabled is False
    trial = ExperimentTrial(
        trial_family="P7_MICRO_1M",
        hypothesis="1m context adds matched OOS value",
        exact_feature_change="add micro_1m_context_v1",
        exact_target_change="none",
        exact_model_change="none",
        primary_metric="matched Spearman IC",
        promotion_rule="registered robust matched improvement",
        random_seed=42,
        data_manifest="future-manifest",
        universe="BTCUSDT,ETHUSDT",
        cost_assumptions="same as baseline",
    )
    assert trial.trial_family in TRIAL_FAMILIES
    assert TRIAL_FAMILIES["P8_TEMPORAL"] == ("RESERVED_NOT_AUTHORIZED",)


def test_opportunity_formula_is_deliberately_undefined() -> None:
    value = OpportunityScore(True, True, True, True, True)
    assert value.score is None
    with pytest.raises(ValueError, match="does not authorize"):
        OpportunityScore(True, True, True, True, True, score=1.0)


def test_optional_research_metrics_are_deterministic() -> None:
    assert brier_score([0, 1], [0.25, 0.75]) == pytest.approx(0.0625)
    assert pinball_loss([0, 2], [1, 1], quantile=0.5) == pytest.approx(0.5)
    assert ndcg_at_k([3, 2, 0], [0.9, 0.8, 0.1], k=2) == pytest.approx(1.0)
