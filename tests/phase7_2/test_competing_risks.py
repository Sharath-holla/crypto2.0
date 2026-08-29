from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_ai.phase7_2.competing_risks import (
    CompetingEventType,
    CompetingRiskTarget,
    CumulativeEventProbability,
    IntrabarOrderStatus,
    resolve_barrier_event,
    validate_cumulative_probability_path,
)
from crypto_ai.phase7_2.schemas import CanonicalMarket1m, DataQualityStatus


def _with_range(row: CanonicalMarket1m, low: str, high: str) -> CanonicalMarket1m:
    return row.model_copy(update={"low": Decimal(low), "high": Decimal(high)})


def test_resolves_up_first(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    rows = (_with_range(one_minute_rows[0], "99", "106"), *one_minute_rows[1:])
    outcome = resolve_barrier_event(
        rows,
        upper_barrier=Decimal("106"),
        lower_barrier=Decimal("95"),
        censor_time=one_minute_rows[-1].interval_end,
    )
    assert outcome.event_type is CompetingEventType.UP_FIRST
    assert outcome.event_time == one_minute_rows[0].interval_end


def test_resolves_down_first(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    rows = (_with_range(one_minute_rows[0], "94", "102"), *one_minute_rows[1:])
    outcome = resolve_barrier_event(
        rows,
        upper_barrier=Decimal("110"),
        lower_barrier=Decimal("95"),
        censor_time=one_minute_rows[-1].interval_end,
    )
    assert outcome.event_type is CompetingEventType.DOWN_FIRST


def test_no_hit_is_censored(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    outcome = resolve_barrier_event(
        one_minute_rows,
        upper_barrier=Decimal("200"),
        lower_barrier=Decimal("50"),
        censor_time=one_minute_rows[-1].interval_end,
    )
    assert outcome.event_type is CompetingEventType.NO_HIT
    assert outcome.event_time is None
    assert outcome.intrabar_order_status is IntrabarOrderStatus.NOT_APPLICABLE


def test_same_minute_double_touch_is_ambiguous(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    rows = (_with_range(one_minute_rows[0], "94", "106"), *one_minute_rows[1:])
    outcome = resolve_barrier_event(
        rows,
        upper_barrier=Decimal("106"),
        lower_barrier=Decimal("95"),
        censor_time=one_minute_rows[-1].interval_end,
    )
    assert outcome.event_type is CompetingEventType.AMBIGUOUS
    assert outcome.event_time is None
    assert outcome.intrabar_order_status is IntrabarOrderStatus.AMBIGUOUS


def test_competing_risk_target_enforces_timing_and_ambiguity(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    entry = one_minute_rows[0].interval_start
    target = CompetingRiskTarget(
        symbol="BTCUSDT",
        feature_time=entry - timedelta(minutes=10),
        decision_time=entry - timedelta(minutes=5),
        entry_time=entry,
        event_type=CompetingEventType.AMBIGUOUS,
        event_time=None,
        censor_time=entry + timedelta(minutes=5),
        upper_barrier=Decimal("106"),
        lower_barrier=Decimal("95"),
        volatility_reference=Decimal("0.02"),
        cost_reference=Decimal("0.001"),
        mfe=Decimal("0.06"),
        mae=Decimal("-0.06"),
        path_quality=DataQualityStatus.VALID,
        intrabar_order_status=IntrabarOrderStatus.AMBIGUOUS,
        ambiguous_intrabar=True,
        censored=True,
        included_in_cause_loss=False,
    )
    assert target.target_version == "competing_risk_targets_v1"
    with pytest.raises(ValidationError, match="excluded"):
        CompetingRiskTarget.model_validate({**target.model_dump(), "included_in_cause_loss": True})


def test_probability_sum_invariant() -> None:
    row = CumulativeEventProbability(
        horizon_minutes=30,
        up_by_horizon=Decimal("0.2"),
        down_by_horizon=Decimal("0.3"),
        no_hit_by_horizon=Decimal("0.5"),
    )
    assert row.no_hit_by_horizon == Decimal("0.5")
    with pytest.raises(ValidationError, match="equal one"):
        CumulativeEventProbability(
            horizon_minutes=30,
            up_by_horizon=Decimal("0.2"),
            down_by_horizon=Decimal("0.3"),
            no_hit_by_horizon=Decimal("0.4"),
        )


def test_cumulative_probabilities_must_be_monotone() -> None:
    valid = [
        CumulativeEventProbability(
            horizon_minutes=30,
            up_by_horizon=Decimal("0.2"),
            down_by_horizon=Decimal("0.1"),
            no_hit_by_horizon=Decimal("0.7"),
        ),
        CumulativeEventProbability(
            horizon_minutes=60,
            up_by_horizon=Decimal("0.3"),
            down_by_horizon=Decimal("0.2"),
            no_hit_by_horizon=Decimal("0.5"),
        ),
    ]
    validate_cumulative_probability_path(valid)
    invalid = [
        valid[0],
        CumulativeEventProbability(
            horizon_minutes=60,
            up_by_horizon=Decimal("0.1"),
            down_by_horizon=Decimal("0.2"),
            no_hit_by_horizon=Decimal("0.7"),
        ),
    ]
    with pytest.raises(ValueError, match="UP probability"):
        validate_cumulative_probability_path(invalid)
