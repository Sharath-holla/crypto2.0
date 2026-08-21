from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pyarrow as pa

from crypto_ai.phase5.config import ScheduleConfig

_US_PER_MINUTE = 60_000_000


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("walk-forward timestamps must be timezone-aware")
    return value.astimezone(UTC)


def add_calendar_months(value: datetime, months: int) -> datetime:
    value = _utc(value)
    absolute = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(absolute, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


@dataclass(frozen=True)
class FoldPlan:
    fold_id: str
    index: int
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    calibration_start: datetime
    calibration_end: datetime
    test_start: datetime
    test_end: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in self.__dict__.items()
        }


def _fold_id(index: int, boundaries: tuple[datetime, ...]) -> str:
    identity = [value.isoformat() for value in boundaries]
    suffix = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:12]
    return f"fold-{index:03d}-{suffix}"


def plan_folds(
    data_start: datetime,
    data_end: datetime,
    holdout_start: datetime,
    schedule: ScheduleConfig,
) -> tuple[FoldPlan, ...]:
    data_start, data_end, holdout_start = map(_utc, (data_start, data_end, holdout_start))
    effective_end = min(data_end, holdout_start)
    plans: list[FoldPlan] = []
    index = 0
    while True:
        train_start = add_calendar_months(data_start, index * schedule.step_months)
        train_end = add_calendar_months(train_start, schedule.train_months)
        validation_end = add_calendar_months(train_end, schedule.validation_months)
        calibration_end = add_calendar_months(validation_end, schedule.calibration_months)
        test_end = add_calendar_months(calibration_end, schedule.test_months)
        if test_end > effective_end:
            break
        boundaries = (train_start, train_end, validation_end, calibration_end, test_end)
        plans.append(
            FoldPlan(
                fold_id=_fold_id(index, boundaries),
                index=index,
                train_start=train_start,
                train_end=train_end,
                validation_start=train_end,
                validation_end=validation_end,
                calibration_start=validation_end,
                calibration_end=calibration_end,
                test_start=calibration_end,
                test_end=test_end,
            )
        )
        index += 1
    if any(plan.test_end > holdout_start for plan in plans):
        raise AssertionError("fold planner crossed the prospective holdout")
    return tuple(plans)


@dataclass(frozen=True)
class FoldData:
    train: pa.Table
    validation: pa.Table
    calibration: pa.Table
    _test: pa.Table
    report: dict[str, Any]

    def release_test(self, *, frozen_identity: str) -> pa.Table:
        if not frozen_identity:
            raise ValueError("test release requires a frozen model/calibrator/policy identity")
        return self._test


@dataclass(frozen=True)
class HardenedFoldData:
    """Phase 5.1 fold with calibration fitting and policy selection isolated."""

    train: pa.Table
    validation: pa.Table
    calibration_a: pa.Table
    calibration_b: pa.Table
    _test: pa.Table
    report: dict[str, Any]

    def release_test(self, *, frozen_identity: str) -> pa.Table:
        if not frozen_identity:
            raise ValueError("test release requires a frozen model/calibrator/policy identity")
        return self._test


def _times(table: pa.Table, column: str) -> np.ndarray:
    return table.column(column).combine_chunks().cast(pa.int64()).to_numpy()


def _range(table: pa.Table, start: datetime, end: datetime) -> pa.Table:
    values = _times(table, "feature_time")
    start_us, end_us = int(start.timestamp() * 1_000_000), int(end.timestamp() * 1_000_000)
    return table.filter(pa.array((values >= start_us) & (values < end_us)))


def _prepare_previous(table: pa.Table, next_start: datetime) -> tuple[pa.Table, int]:
    before = table.num_rows
    boundary_us = int(next_start.timestamp() * 1_000_000)
    kept = table.filter(pa.array(_times(table, "label_end_time") < boundary_us))
    return kept, before - kept.num_rows


def _embargo(table: pa.Table, start: datetime, minutes: int) -> tuple[pa.Table, int]:
    if minutes == 0:
        return table, 0
    before = table.num_rows
    embargo_end_us = int(start.timestamp() * 1_000_000) + minutes * _US_PER_MINUTE
    kept = table.filter(pa.array(_times(table, "feature_time") >= embargo_end_us))
    return kept, before - kept.num_rows


def slice_fold(
    table: pa.Table,
    plan: FoldPlan,
    schedule: ScheduleConfig,
    holdout_start: datetime,
) -> FoldData:
    holdout_start = _utc(holdout_start)
    if plan.test_end > holdout_start:
        raise ValueError("fold test period crosses the prospective holdout")
    raw = {
        "train": _range(table, plan.train_start, plan.train_end),
        "validation": _range(table, plan.validation_start, plan.validation_end),
        "calibration": _range(table, plan.calibration_start, plan.calibration_end),
        "test": _range(table, plan.test_start, plan.test_end),
    }
    train, train_purged = _prepare_previous(raw["train"], plan.validation_start)
    validation, validation_purged = _prepare_previous(raw["validation"], plan.calibration_start)
    calibration, calibration_purged = _prepare_previous(raw["calibration"], plan.test_start)
    validation, validation_embargoed = _embargo(
        validation, plan.validation_start, schedule.embargo_minutes
    )
    calibration, calibration_embargoed = _embargo(
        calibration, plan.calibration_start, schedule.embargo_minutes
    )
    test, test_embargoed = _embargo(raw["test"], plan.test_start, schedule.embargo_minutes)
    prepared = {"train": train, "validation": validation, "calibration": calibration, "test": test}
    too_small = {
        name: value.num_rows
        for name, value in prepared.items()
        if value.num_rows < schedule.minimum_rows_per_segment
    }
    if too_small:
        raise ValueError(f"{plan.fold_id} has undersized segments: {too_small}")
    holdout_us = int(holdout_start.timestamp() * 1_000_000)
    for name, segment in prepared.items():
        if np.any(_times(segment, "feature_time") >= holdout_us):
            raise ValueError(f"{name} contains prospective holdout rows")
    report = {
        "fold_id": plan.fold_id,
        "boundaries": plan.to_dict(),
        "embargo_minutes": schedule.embargo_minutes,
        "segments": {
            "train": {
                "before": raw["train"].num_rows,
                "purged": train_purged,
                "embargoed": 0,
                "remaining": train.num_rows,
            },
            "validation": {
                "before": raw["validation"].num_rows,
                "purged": validation_purged,
                "embargoed": validation_embargoed,
                "remaining": validation.num_rows,
            },
            "calibration": {
                "before": raw["calibration"].num_rows,
                "purged": calibration_purged,
                "embargoed": calibration_embargoed,
                "remaining": calibration.num_rows,
            },
            "test": {
                "before": raw["test"].num_rows,
                "purged": 0,
                "embargoed": test_embargoed,
                "remaining": test.num_rows,
            },
        },
    }
    return FoldData(train, validation, calibration, test, report)


def calibration_split_time(plan: FoldPlan) -> datetime:
    """Return the timestamp midpoint of the frozen outer calibration window."""

    return plan.calibration_start + (plan.calibration_end - plan.calibration_start) / 2


def slice_hardened_fold(
    table: pa.Table,
    plan: FoldPlan,
    schedule: ScheduleConfig,
    holdout_start: datetime,
) -> HardenedFoldData:
    """Create chronological Cal-A/Cal-B segments without changing outer folds."""

    holdout_start = _utc(holdout_start)
    if plan.test_end > holdout_start:
        raise ValueError("fold test period crosses the prospective holdout")
    split_time = calibration_split_time(plan)
    raw = {
        "train": _range(table, plan.train_start, plan.train_end),
        "validation": _range(table, plan.validation_start, plan.validation_end),
        "calibration_a": _range(table, plan.calibration_start, split_time),
        "calibration_b": _range(table, split_time, plan.calibration_end),
        "test": _range(table, plan.test_start, plan.test_end),
    }
    train, train_purged = _prepare_previous(raw["train"], plan.validation_start)
    validation, validation_purged = _prepare_previous(raw["validation"], plan.calibration_start)
    calibration_a, calibration_a_purged = _prepare_previous(raw["calibration_a"], split_time)
    calibration_b, calibration_b_purged = _prepare_previous(raw["calibration_b"], plan.test_start)
    validation, validation_embargoed = _embargo(
        validation, plan.validation_start, schedule.embargo_minutes
    )
    calibration_a, calibration_a_embargoed = _embargo(
        calibration_a, plan.calibration_start, schedule.embargo_minutes
    )
    calibration_b, calibration_b_embargoed = _embargo(
        calibration_b, split_time, schedule.embargo_minutes
    )
    test, test_embargoed = _embargo(raw["test"], plan.test_start, schedule.embargo_minutes)
    prepared = {
        "train": train,
        "validation": validation,
        "calibration_a": calibration_a,
        "calibration_b": calibration_b,
        "test": test,
    }
    too_small = {
        name: segment.num_rows
        for name, segment in prepared.items()
        if segment.num_rows < schedule.minimum_rows_per_segment
    }
    if too_small:
        raise ValueError(f"{plan.fold_id} has undersized hardened segments: {too_small}")
    holdout_us = int(holdout_start.timestamp() * 1_000_000)
    for name, segment in prepared.items():
        if np.any(_times(segment, "feature_time") >= holdout_us):
            raise ValueError(f"{name} contains prospective holdout rows")
    if calibration_a.num_rows and calibration_b.num_rows:
        if _times(calibration_a, "feature_time")[-1] >= _times(calibration_b, "feature_time")[0]:
            raise ValueError("Cal-A must be strictly before Cal-B")
        if _times(calibration_a, "label_end_time")[-1] >= _times(calibration_b, "feature_time")[0]:
            raise ValueError("Cal-A labels overlap Cal-B after purging")
    report = {
        "fold_id": plan.fold_id,
        "boundaries": plan.to_dict(),
        "calibration_split_time": split_time.isoformat(),
        "embargo_minutes": schedule.embargo_minutes,
        "segments": {
            "train": {
                "range": [plan.train_start.isoformat(), plan.train_end.isoformat()],
                "before": raw["train"].num_rows,
                "purged": train_purged,
                "embargoed": 0,
                "remaining": train.num_rows,
            },
            "validation": {
                "range": [plan.validation_start.isoformat(), plan.validation_end.isoformat()],
                "before": raw["validation"].num_rows,
                "purged": validation_purged,
                "embargoed": validation_embargoed,
                "remaining": validation.num_rows,
            },
            "calibration_a": {
                "range": [plan.calibration_start.isoformat(), split_time.isoformat()],
                "before": raw["calibration_a"].num_rows,
                "purged": calibration_a_purged,
                "embargoed": calibration_a_embargoed,
                "remaining": calibration_a.num_rows,
            },
            "calibration_b": {
                "range": [split_time.isoformat(), plan.calibration_end.isoformat()],
                "before": raw["calibration_b"].num_rows,
                "purged": calibration_b_purged,
                "embargoed": calibration_b_embargoed,
                "remaining": calibration_b.num_rows,
            },
            "test": {
                "range": [plan.test_start.isoformat(), plan.test_end.isoformat()],
                "before": raw["test"].num_rows,
                "purged": 0,
                "embargoed": test_embargoed,
                "remaining": test.num_rows,
            },
        },
    }
    return HardenedFoldData(
        train,
        validation,
        calibration_a,
        calibration_b,
        test,
        report,
    )


def validate_fold_plan(plans: tuple[FoldPlan, ...], holdout_start: datetime) -> None:
    holdout_start = _utc(holdout_start)
    if not plans:
        raise ValueError("walk-forward plan contains no complete folds")
    for current, following in zip(plans, plans[1:], strict=False):
        if current.test_end > following.test_start:
            raise ValueError("walk-forward test periods overlap")
        if current.index + 1 != following.index:
            raise ValueError("fold indices are not contiguous")
    if any(plan.test_end > holdout_start for plan in plans):
        raise ValueError("walk-forward plan enters the prospective holdout")
