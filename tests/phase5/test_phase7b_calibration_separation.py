"""Added by Claude (2026-11-02, finding L-05): Cal-A/Cal-B overlap uses max/min, not last/first."""

from __future__ import annotations

import pyarrow as pa
import pytest

from crypto_ai.phase5.folds import check_calibration_separation

US = 1_000_000


def _table(feature_times: list[int], label_ends: list[int]) -> pa.Table:
    kind = pa.timestamp("us", tz="UTC")
    return pa.table(
        {
            "feature_time": pa.array([t * US for t in feature_times], type=kind),
            "label_end_time": pa.array([t * US for t in label_ends], type=kind),
        }
    )


def test_clean_separation_passes() -> None:
    check_calibration_separation(_table([1, 2, 3], [4, 5, 6]), _table([10, 11], [12, 13]))


def test_unsorted_cal_a_with_late_row_is_caught() -> None:
    # The LAST row looks fine (3) but a middle row (20) is after Cal-B starts (10).
    with pytest.raises(ValueError, match="strictly before"):
        check_calibration_separation(_table([1, 20, 3], [4, 25, 6]), _table([10, 11], [12, 13]))


def test_unsorted_cal_b_with_early_row_is_caught() -> None:
    # Cal-B's FIRST row looks fine (50) but its minimum (2) overlaps Cal-A.
    with pytest.raises(ValueError, match="strictly before"):
        check_calibration_separation(_table([1, 3], [4, 6]), _table([50, 2], [52, 4]))


def test_label_overlap_is_caught_by_the_maximum_label_end() -> None:
    with pytest.raises(ValueError, match="labels overlap"):
        check_calibration_separation(_table([1, 2, 3], [4, 99, 6]), _table([10, 11], [12, 13]))
