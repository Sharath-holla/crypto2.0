from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from crypto_ai.phase7_2.schemas import CanonicalMarket1m, DataQualityStatus

COMPETING_RISK_TARGET_VERSION = "competing_risk_targets_v1"


class IntrabarOrderStatus(StrEnum):
    ORDER_KNOWN = "ORDER_KNOWN"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class CompetingEventType(StrEnum):
    UP_FIRST = "UP_FIRST"
    DOWN_FIRST = "DOWN_FIRST"
    NO_HIT = "NO_HIT"
    AMBIGUOUS = "AMBIGUOUS"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_utc(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware UTC")
    if value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{field} must be UTC")


class BarrierOutcome(_Frozen):
    event_type: CompetingEventType
    event_time: datetime | None
    censor_time: datetime
    intrabar_order_status: IntrabarOrderStatus

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        _require_utc(self.censor_time, "censor_time")
        if self.event_time is not None:
            _require_utc(self.event_time, "event_time")
            if self.event_time > self.censor_time:
                raise ValueError("event_time cannot follow censor_time")
        if self.event_type in (CompetingEventType.UP_FIRST, CompetingEventType.DOWN_FIRST):
            if (
                self.event_time is None
                or self.intrabar_order_status is not IntrabarOrderStatus.ORDER_KNOWN
            ):
                raise ValueError("known barrier events require event_time and ORDER_KNOWN")
        elif self.event_type is CompetingEventType.AMBIGUOUS:
            if (
                self.event_time is not None
                or self.intrabar_order_status is not IntrabarOrderStatus.AMBIGUOUS
            ):
                raise ValueError("ambiguous barrier outcomes cannot invent an event time")
        elif (
            self.event_time is not None
            or self.intrabar_order_status is not IntrabarOrderStatus.NOT_APPLICABLE
        ):
            raise ValueError("NO_HIT requires no event time and NOT_APPLICABLE ordering")
        return self


class CompetingRiskTarget(_Frozen):
    symbol: str
    feature_time: datetime
    decision_time: datetime
    entry_time: datetime
    event_type: CompetingEventType
    event_time: datetime | None
    censor_time: datetime
    upper_barrier: Decimal
    lower_barrier: Decimal
    volatility_reference: Decimal
    cost_reference: Decimal
    mfe: Decimal
    mae: Decimal
    path_quality: DataQualityStatus
    intrabar_order_status: IntrabarOrderStatus
    ambiguous_intrabar: bool
    censored: bool
    included_in_cause_loss: bool
    target_version: Literal["competing_risk_targets_v1"] = COMPETING_RISK_TARGET_VERSION

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        for field in ("feature_time", "decision_time", "entry_time", "censor_time"):
            _require_utc(getattr(self, field), field)
        if self.event_time is not None:
            _require_utc(self.event_time, "event_time")
        if not self.symbol.strip() or self.symbol != self.symbol.upper():
            raise ValueError("symbol must be normalized uppercase")
        if not self.feature_time < self.decision_time <= self.entry_time < self.censor_time:
            raise ValueError("target times must follow feature < decision <= entry < censor")
        if (
            self.event_time is not None
            and not self.entry_time <= self.event_time <= self.censor_time
        ):
            raise ValueError("event_time must fall inside the target horizon")
        if self.upper_barrier <= self.lower_barrier:
            raise ValueError("upper_barrier must exceed lower_barrier")
        if self.volatility_reference < 0 or self.cost_reference < 0:
            raise ValueError("volatility and cost references cannot be negative")
        if self.mfe < 0 or self.mae > 0:
            raise ValueError("MFE must be nonnegative and MAE must be nonpositive")

        known = self.event_type in (CompetingEventType.UP_FIRST, CompetingEventType.DOWN_FIRST)
        if known:
            if self.event_time is None or self.censored or self.ambiguous_intrabar:
                raise ValueError("known event targets require an uncensored non-ambiguous event")
            if self.intrabar_order_status is not IntrabarOrderStatus.ORDER_KNOWN:
                raise ValueError("known event targets require ORDER_KNOWN")
        elif self.event_type is CompetingEventType.NO_HIT:
            if self.event_time is not None or not self.censored or self.ambiguous_intrabar:
                raise ValueError("NO_HIT targets must be cleanly censored")
            if self.intrabar_order_status is not IntrabarOrderStatus.NOT_APPLICABLE:
                raise ValueError("NO_HIT targets require NOT_APPLICABLE ordering")
        else:
            if (
                self.event_time is not None
                or not self.censored
                or not self.ambiguous_intrabar
                or self.included_in_cause_loss
            ):
                raise ValueError("ambiguous paths must be censored and excluded from cause loss")
            if self.intrabar_order_status is not IntrabarOrderStatus.AMBIGUOUS:
                raise ValueError("ambiguous paths require AMBIGUOUS ordering")
        return self


class CumulativeEventProbability(_Frozen):
    horizon_minutes: int
    up_by_horizon: Decimal
    down_by_horizon: Decimal
    no_hit_by_horizon: Decimal

    @model_validator(mode="after")
    def validate_probability(self) -> Self:
        if self.horizon_minutes <= 0:
            raise ValueError("horizon_minutes must be positive")
        values = (self.up_by_horizon, self.down_by_horizon, self.no_hit_by_horizon)
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("competing-risk probabilities must be between 0 and 1")
        if abs(sum(values, start=Decimal(0)) - Decimal(1)) > Decimal("1e-12"):
            raise ValueError("UP + DOWN + NO_HIT probabilities must equal one")
        return self


def validate_cumulative_probability_path(
    probabilities: Sequence[CumulativeEventProbability],
) -> None:
    if not probabilities:
        raise ValueError("at least one probability horizon is required")
    horizons = [row.horizon_minutes for row in probabilities]
    if horizons != sorted(horizons) or len(horizons) != len(set(horizons)):
        raise ValueError("probability horizons must be strictly increasing")
    for previous, current in zip(probabilities, probabilities[1:], strict=False):
        if current.up_by_horizon < previous.up_by_horizon:
            raise ValueError("cumulative UP probability cannot decrease")
        if current.down_by_horizon < previous.down_by_horizon:
            raise ValueError("cumulative DOWN probability cannot decrease")
        if current.no_hit_by_horizon > previous.no_hit_by_horizon:
            raise ValueError("NO_HIT probability cannot increase")


def resolve_barrier_event(
    rows: Iterable[CanonicalMarket1m],
    *,
    upper_barrier: Decimal,
    lower_barrier: Decimal,
    censor_time: datetime,
) -> BarrierOutcome:
    _require_utc(censor_time, "censor_time")
    if upper_barrier <= lower_barrier:
        raise ValueError("upper_barrier must exceed lower_barrier")
    path = tuple(rows)
    if not path:
        raise ValueError("barrier path cannot be empty")
    starts = [row.interval_start for row in path]
    if starts != sorted(starts) or len(starts) != len(set(starts)):
        raise ValueError("barrier path must be ordered and duplicate-free")
    if len({row.symbol for row in path}) != 1:
        raise ValueError("barrier path cannot mix symbols")
    if any(
        current.interval_start != previous.interval_end
        for previous, current in zip(path, path[1:], strict=False)
    ):
        raise ValueError("barrier path cannot cross a missing 1m interval")
    for row in path:
        if row.interval_end > censor_time:
            raise ValueError("barrier path extends beyond censor_time")
        if row.quality_status is not DataQualityStatus.VALID:
            raise ValueError("barrier path contains invalid data")
        hit_up = row.high >= upper_barrier
        hit_down = row.low <= lower_barrier
        if hit_up and hit_down:
            return BarrierOutcome(
                event_type=CompetingEventType.AMBIGUOUS,
                event_time=None,
                censor_time=censor_time,
                intrabar_order_status=IntrabarOrderStatus.AMBIGUOUS,
            )
        if hit_up:
            return BarrierOutcome(
                event_type=CompetingEventType.UP_FIRST,
                event_time=row.interval_end,
                censor_time=censor_time,
                intrabar_order_status=IntrabarOrderStatus.ORDER_KNOWN,
            )
        if hit_down:
            return BarrierOutcome(
                event_type=CompetingEventType.DOWN_FIRST,
                event_time=row.interval_end,
                censor_time=censor_time,
                intrabar_order_status=IntrabarOrderStatus.ORDER_KNOWN,
            )
    return BarrierOutcome(
        event_type=CompetingEventType.NO_HIT,
        event_time=None,
        censor_time=censor_time,
        intrabar_order_status=IntrabarOrderStatus.NOT_APPLICABLE,
    )
