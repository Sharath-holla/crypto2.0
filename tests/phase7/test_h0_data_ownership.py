"""CHANGED BY CLAUDE (2026-11-06, closure): H0 correction rows are not the early-stopping rows."""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7.models import (
    IneligibleFoldError,
    _assert_correction_rows_disjoint_from_early_stopping,
    split_calibration_a_for_h0,
)

_MIN_US = 60 * 1_000_000


def _table(
    n_times: int, symbols: tuple[str, ...], horizon_minutes: int, start: int = 0
) -> pa.Table:
    times = np.repeat(np.arange(n_times, dtype=np.int64) * 15 * _MIN_US + start, len(symbols))
    syms = list(symbols) * n_times
    ends = times + horizon_minutes * _MIN_US
    return pa.table(
        {
            "symbol": pa.array(syms),
            "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(ends, type=pa.timestamp("us", tz="UTC")),
        }
    )


def _ints(table: pa.Table, name: str) -> np.ndarray:
    return table.column(name).combine_chunks().cast(pa.int64()).to_numpy()


@pytest.mark.parametrize("horizon", [15, 30, 60, 120])
def test_correction_labels_end_before_the_calibrator_rows_begin(horizon: int) -> None:
    cal_a = _table(200, ("A", "B"), horizon)
    correction, calibrator, report = split_calibration_a_for_h0(cal_a, embargo_us=60 * _MIN_US)
    first_calibrator = _ints(calibrator, "feature_time").min()
    assert (_ints(correction, "label_end_time") + 60 * _MIN_US < first_calibrator).all()
    assert (_ints(correction, "feature_time") < first_calibrator).all()
    # no row is in both parts; whole timestamps are never split
    assert report["correction_rows"] + report["purged_rows"] + report["calibrator_rows"] == 400
    assert report["status"] == "CALIBRATION_A1_PURGED_INDEPENDENT_OF_EARLY_STOPPING"
    assert report["ownership"]["early_stopping"] == "VALIDATION"
    assert report["ownership"]["threshold"] == "CALIBRATION_B"


def test_longer_horizon_purges_more() -> None:
    purged = [
        split_calibration_a_for_h0(_table(200, ("A",), h), embargo_us=0)[2]["purged_rows"]
        for h in (15, 30, 60, 120)
    ]
    assert purged == sorted(purged) and purged[0] < purged[-1]


def test_split_fails_closed_when_one_side_would_be_empty() -> None:
    with pytest.raises(IneligibleFoldError):
        split_calibration_a_for_h0(_table(1, ("A",), 15), embargo_us=0)
    with pytest.raises(IneligibleFoldError):
        # labels so long that no correction row survives the purge
        split_calibration_a_for_h0(_table(50, ("A",), 100_000), embargo_us=0)


def test_overlap_with_early_stopping_rows_is_rejected() -> None:
    validation = _table(30, ("A", "B"), 60)
    with pytest.raises(ValueError, match="H0_CORRECTION_OVERLAPS_EARLY_STOPPING"):
        _assert_correction_rows_disjoint_from_early_stopping(validation.slice(10, 6), validation)


def test_disjoint_rows_pass_the_overlap_check() -> None:
    validation = _table(30, ("A", "B"), 60)
    later = _table(30, ("A", "B"), 60, start=40 * 15 * _MIN_US)
    _assert_correction_rows_disjoint_from_early_stopping(later, validation)


def test_calibration_a_split_never_receives_cal_b_or_test() -> None:
    import inspect

    params = set(inspect.signature(split_calibration_a_for_h0).parameters)
    assert params == {"calibration_a", "embargo_us", "correction_fraction"}
