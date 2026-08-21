from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyarrow as pa
import pytest

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import (
    add_calendar_months,
    calibration_split_time,
    plan_folds,
    slice_fold,
    slice_hardened_fold,
    validate_fold_plan,
)


def _table(start: datetime, days: int) -> pa.Table:
    feature = [start + timedelta(days=index) for index in range(days)]
    return pa.table(
        {
            "feature_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [value + timedelta(minutes=60) for value in feature],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "future_return_60m": [0.001] * days,
        }
    )


def test_calendar_month_addition_clamps_month_end() -> None:
    assert add_calendar_months(datetime(2024, 1, 31, tzinfo=UTC), 1) == datetime(
        2024, 2, 29, tzinfo=UTC
    )


def test_plan_is_deterministic_rolling_nonoverlapping_and_holdout_safe() -> None:
    start = datetime(2020, 1, 9, 5, 40, tzinfo=UTC)
    holdout = datetime(2026, 8, 1, tzinfo=UTC)
    schedule = ScheduleConfig(minimum_rows_per_segment=1)
    left = plan_folds(start, holdout, holdout, schedule)
    right = plan_folds(start, holdout, holdout, schedule)
    assert left == right
    assert left
    validate_fold_plan(left, holdout)
    for first, second in zip(left, left[1:], strict=False):
        assert add_calendar_months(first.train_start, 3) == second.train_start
        assert first.test_end == second.test_start
        assert add_calendar_months(first.train_start, 24) == first.train_end
        assert add_calendar_months(first.validation_start, 3) == first.validation_end
        assert add_calendar_months(first.calibration_start, 3) == first.calibration_end
        assert add_calendar_months(first.test_start, 3) == first.test_end
    assert max(item.test_end for item in left) <= holdout


def test_plan_rejects_overlapping_test_configuration() -> None:
    with pytest.raises(ValueError, match="prevent overlapping OOS"):
        ScheduleConfig(test_months=3, step_months=1)


def test_slice_purges_crossing_labels_and_embargoes_later_segment_starts() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    schedule = ScheduleConfig(
        train_months=1,
        validation_months=1,
        calibration_months=1,
        test_months=1,
        step_months=1,
        embargo_minutes=60,
        minimum_rows_per_segment=1,
    )
    plan = plan_folds(
        start, datetime(2020, 6, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), schedule
    )[0]
    feature = [
        plan.train_end - timedelta(minutes=65),
        plan.train_end - timedelta(minutes=60),
        plan.train_end - timedelta(minutes=55),
        plan.validation_start,
        plan.validation_start + timedelta(minutes=60),
        plan.validation_end - timedelta(minutes=60),
        plan.calibration_start,
        plan.calibration_start + timedelta(minutes=60),
        plan.calibration_end - timedelta(minutes=60),
        plan.test_start,
        plan.test_start + timedelta(minutes=60),
    ]
    table = pa.table(
        {
            "feature_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [value + timedelta(minutes=60) for value in feature],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "future_return_60m": [0.001] * len(feature),
        }
    )
    result = slice_fold(table, plan, schedule, datetime(2021, 1, 1, tzinfo=UTC))
    assert result.report["segments"]["train"]["purged"] == 2
    assert result.report["segments"]["validation"]["embargoed"] == 1
    assert result.report["segments"]["calibration"]["embargoed"] == 1
    assert result.report["segments"]["test"]["embargoed"] == 1
    assert result.train.column("feature_time")[0].as_py() == feature[0]


def test_test_vault_requires_frozen_identity() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    schedule = ScheduleConfig(
        train_months=1,
        validation_months=1,
        calibration_months=1,
        test_months=1,
        step_months=1,
        embargo_minutes=0,
        minimum_rows_per_segment=1,
    )
    plan = plan_folds(
        start, datetime(2020, 6, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), schedule
    )[0]
    fold = slice_fold(_table(start, 125), plan, schedule, datetime(2021, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="frozen"):
        fold.release_test(frozen_identity="")
    assert fold.release_test(frozen_identity="fixed").num_rows > 0


def test_slice_rejects_holdout_crossing_plan() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    schedule = ScheduleConfig(
        train_months=1,
        validation_months=1,
        calibration_months=1,
        test_months=1,
        step_months=1,
        minimum_rows_per_segment=1,
    )
    plan = plan_folds(
        start, datetime(2020, 6, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), schedule
    )[0]
    with pytest.raises(ValueError, match="holdout"):
        slice_fold(_table(start, 125), plan, schedule, plan.test_end - timedelta(days=1))


def test_hardened_calibration_split_is_chronological_purged_and_embargoed() -> None:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    holdout = datetime(2021, 1, 1, tzinfo=UTC)
    schedule = ScheduleConfig(
        train_months=1,
        validation_months=1,
        calibration_months=1,
        test_months=1,
        step_months=1,
        embargo_minutes=60,
        minimum_rows_per_segment=1,
    )
    plan = plan_folds(start, datetime(2020, 6, 1, tzinfo=UTC), holdout, schedule)[0]
    count = int((plan.test_end - start).total_seconds() // 300)
    feature = [start + timedelta(minutes=5 * index) for index in range(count)]
    table = pa.table(
        {
            "feature_time": pa.array(feature, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [value + timedelta(minutes=60) for value in feature],
                type=pa.timestamp("us", tz="UTC"),
            ),
            "future_return_60m": [0.0] * count,
        }
    )
    fold = slice_hardened_fold(table, plan, schedule, holdout)
    split_time = calibration_split_time(plan)
    assert fold.calibration_a.column("feature_time")[-1].as_py() < split_time
    assert fold.calibration_b.column("feature_time")[0].as_py() >= split_time + timedelta(
        minutes=60
    )
    assert (
        fold.calibration_a.column("label_end_time")[-1].as_py()
        < fold.calibration_b.column("feature_time")[0].as_py()
    )
    assert fold.report["segments"]["calibration_a"]["purged"] == 12
    assert fold.report["segments"]["calibration_b"]["embargoed"] == 12
    assert (
        fold.release_test(frozen_identity="calibrator-and-policy-frozen")
        .column("feature_time")[-1]
        .as_py()
        < holdout
    )
