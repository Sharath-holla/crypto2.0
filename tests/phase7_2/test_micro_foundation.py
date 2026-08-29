from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from crypto_ai.phase7_2.config import MicroContextToggle
from crypto_ai.phase7_2.micro import (
    CausalAggregationError,
    aggregate_1m_to_5m,
    build_micro_1m_context,
)
from crypto_ai.phase7_2.schemas import CanonicalMarket1m, DataQualityStatus


def test_canonical_1m_schema_preserves_exact_values_and_round_trips(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    row = one_minute_rows[0]
    assert row.taker_sell_base == Decimal("5")
    assert row.taker_sell_quote == Decimal("500")
    assert CanonicalMarket1m.model_validate_json(row.to_json()) == row


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 6, 30), datetime(2026, 6, 30, tzinfo=timezone(timedelta(hours=1)))],
)
def test_canonical_1m_schema_requires_utc(
    one_minute_rows: tuple[CanonicalMarket1m, ...], timestamp: datetime
) -> None:
    with pytest.raises(ValidationError, match="UTC"):
        one_minute_rows[0].model_copy(update={"interval_start": timestamp}, deep=True).__class__(
            **{
                **one_minute_rows[0].model_dump(),
                "interval_start": timestamp,
            }
        )


def test_exact_1m_to_5m_aggregation(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    result = aggregate_1m_to_5m(
        one_minute_rows,
        as_of=one_minute_rows[-1].availability_time,
    )
    assert result.interval_start == one_minute_rows[0].interval_start
    assert result.interval_end == one_minute_rows[-1].interval_end
    assert result.availability_time == one_minute_rows[-1].availability_time
    assert result.open == Decimal("100")
    assert result.high == Decimal("105.5")
    assert result.low == Decimal("99.5")
    assert result.close == Decimal("105")
    assert result.volume == Decimal("60")
    assert result.quote_volume == Decimal("6000")
    assert result.trade_count == 510
    assert result.taker_buy_base == Decimal("35")
    assert result.taker_buy_quote == Decimal("3000")


def test_5m_bar_is_unavailable_until_final_1m_row(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    with pytest.raises(CausalAggregationError, match="not yet available"):
        aggregate_1m_to_5m(
            one_minute_rows,
            as_of=one_minute_rows[-1].availability_time - timedelta(microseconds=1),
        )


def test_incomplete_5m_window_is_rejected(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    with pytest.raises(CausalAggregationError, match="exactly five"):
        aggregate_1m_to_5m(one_minute_rows[:-1])


def test_gap_inside_1m_window_is_rejected(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    replacement = one_minute_rows[-1].model_copy(
        update={
            "interval_start": one_minute_rows[-1].interval_start + timedelta(minutes=1),
            "interval_end": one_minute_rows[-1].interval_end + timedelta(minutes=1),
            "availability_time": one_minute_rows[-1].availability_time + timedelta(minutes=1),
        }
    )
    with pytest.raises(CausalAggregationError, match="gap"):
        aggregate_1m_to_5m((*one_minute_rows[:-1], replacement))


def test_duplicate_1m_row_is_rejected(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    with pytest.raises(CausalAggregationError, match="duplicate"):
        aggregate_1m_to_5m((*one_minute_rows[:4], one_minute_rows[3]))


def test_out_of_order_input_is_rejected(one_minute_rows: tuple[CanonicalMarket1m, ...]) -> None:
    with pytest.raises(CausalAggregationError, match="out-of-order"):
        aggregate_1m_to_5m(tuple(reversed(one_minute_rows)))


def test_bad_quality_invalidates_aggregation(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    invalid = one_minute_rows[2].model_copy(update={"quality_status": DataQualityStatus.MISSING})
    with pytest.raises(CausalAggregationError, match="quality"):
        aggregate_1m_to_5m((*one_minute_rows[:2], invalid, *one_minute_rows[3:]))


def test_micro_context_is_disabled_by_default(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    result = build_micro_1m_context(
        one_minute_rows,
        feature_time=one_minute_rows[-1].availability_time,
    )
    assert result.enabled is False
    assert result.features == {}


def test_enabled_micro_context_is_compact_causal_and_finite(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    result = build_micro_1m_context(
        one_minute_rows,
        feature_time=one_minute_rows[-1].availability_time,
        config=MicroContextToggle(enabled=True),
    )
    assert result.enabled is True
    assert len(result.features) == 17
    assert result.features["return_5m"] == pytest.approx(0.05)
    assert 0 <= result.features["volume_concentration_5m"] <= 1


def test_micro_context_rejects_future_observation(
    one_minute_rows: tuple[CanonicalMarket1m, ...],
) -> None:
    with pytest.raises(CausalAggregationError, match="not yet available"):
        build_micro_1m_context(
            one_minute_rows,
            feature_time=one_minute_rows[-1].interval_end,
            config=MicroContextToggle(enabled=True),
        )
