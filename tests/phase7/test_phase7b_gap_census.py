"""Added by Claude (2026-11-02, finding M-06): read-only gap census, incl. Gold-only fallback."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from crypto_ai.phase5.config import ScheduleConfig
from crypto_ai.phase5.folds import plan_folds
from crypto_ai.phase7.folds import IneligibleFoldError, PostTrainDataGapError
from crypto_ai.phase7.readiness import gap_census, observed_gaps_from_times

STEP = 5 * 60 * 1_000_000


def _us(moment: datetime) -> int:
    return int(moment.timestamp() * 1_000_000)


def test_observed_gaps_find_only_holes_larger_than_one_step() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    complete = [_us(start + timedelta(minutes=5 * n)) for n in range(10)]
    holed = [value for index, value in enumerate(complete) if index not in (4, 5)]
    gaps = observed_gaps_from_times({"aaausdt": complete, "BBBUSDT": holed}, step_microseconds=STEP)
    assert [(gap.symbol, gap.start, gap.end) for gap in gaps] == [
        ("BBBUSDT", start + timedelta(minutes=20), start + timedelta(minutes=30))
    ]
    assert gaps[0].partition == "GOLD_OBSERVED"


def test_census_labels_source_and_flags_blocked_folds() -> None:
    plans = plan_folds(
        datetime(2022, 1, 1, tzinfo=UTC),
        datetime(2026, 7, 1, tzinfo=UTC),
        datetime(2026, 8, 1, tzinfo=UTC),
        ScheduleConfig(),
    )
    victim = plans[3]
    middle = victim.test_start + timedelta(days=1)
    gaps = observed_gaps_from_times(
        {
            "AAAUSDT": [
                _us(middle - timedelta(minutes=5)),
                _us(middle + timedelta(minutes=30)),
            ]
        },
        step_microseconds=STEP,
    )
    report = gap_census(plans, gaps, source="GOLD_OBSERVED_TIMESTAMPS")
    by_id = {fold["fold_id"]: fold for fold in report["folds"]}
    assert report["source"] == "GOLD_OBSERVED_TIMESTAMPS"
    assert report["schema"] == "phase7_gap_census_v1"
    assert by_id[victim.fold_id]["can_run"] is False
    assert by_id[victim.fold_id]["gap_symbols"] == ["AAAUSDT"]
    assert report["runnable_fold_count"] == len(plans) - report["blocked_fold_count"]


def test_post_train_gap_error_is_typed_and_not_ineligible() -> None:
    gaps = [
        {
            "symbol": "AAAUSDT",
            "interval": "5m",
            "partition": "2025-03",
            "start": "2025-03-01T00:00:00+00:00",
            "end": "2025-03-01T01:00:00+00:00",
        }
    ]
    error = PostTrainDataGapError("fold_07", gaps)
    assert isinstance(error, ValueError) and not isinstance(error, IneligibleFoldError)
    assert error.fold_id == "fold_07" and error.symbols == ["AAAUSDT"]
    text = str(error)
    assert "post-TRAIN data-quality gaps" in text and "AAAUSDT" in text and "2025-03" in text
