"""Added by Claude (2026-11-02, finding L-03): calibrator method chosen on a held-out Cal-A tail."""

from __future__ import annotations

import numpy as np
import pytest

from crypto_ai.phase5.calibration import SELECTION_HOLDOUT_FRACTION, fit_calibrator
from crypto_ai.phase5.config import CalibrationConfig


def _regime_shift_data() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(0)
    raw = rng.normal(0.0, 0.01, 400)
    actual = raw.copy()
    cut = int(400 * (1 - SELECTION_HOLDOUT_FRACTION))
    actual[:cut] = 3.0 * raw[:cut] + 0.005  # linear looks great in-sample, then stops working
    return raw, actual


def test_default_selection_is_unchanged_in_sample() -> None:
    raw, actual = _regime_shift_data()
    selected, diagnostics = fit_calibrator(raw, actual, CalibrationConfig())
    assert diagnostics["selection_source"] == "calibration_only"
    assert selected.method == "linear"


def test_heldout_tail_prefers_the_method_that_generalizes() -> None:
    raw, actual = _regime_shift_data()
    selected, diagnostics = fit_calibrator(
        raw, actual, CalibrationConfig(), selection_holdout_fraction=SELECTION_HOLDOUT_FRACTION
    )
    assert diagnostics["selection_source"] == "calibration_a_heldout_tail"
    assert selected.method == "identity"
    assert diagnostics["heldout_mae"]["identity"] < diagnostics["heldout_mae"]["linear"]
    assert selected.sample_count == 400  # the chosen method is refit on all of Cal-A


def test_small_segments_fall_back_to_in_sample() -> None:
    raw, actual = _regime_shift_data()
    config = CalibrationConfig(minimum_samples=100)
    _selected, diagnostics = fit_calibrator(
        raw[:100], actual[:100], config, selection_holdout_fraction=0.9
    )
    assert diagnostics["selection_source"] == "calibration_only"


# --- CHANGED BY CLAUDE (2026-11-06, closure): Cal-A internal split purged by label_end_time ---
_MINUTE_US = 60 * 1_000_000


def _timed(n: int, horizon_minutes: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    raw, actual = _regime_shift_data()
    raw, actual = raw[:n], actual[:n]
    times = np.arange(n, dtype=np.int64) * 15 * _MINUTE_US  # one 15-minute bar per row
    ends = times + horizon_minutes * _MINUTE_US
    return raw, actual, times, ends


@pytest.mark.parametrize("horizon", [15, 30, 60, 120])
def test_fit_rows_whose_label_reaches_the_heldout_tail_are_purged(horizon: int) -> None:
    raw, actual, times, ends = _timed(400, horizon)
    _sel, diag = fit_calibrator(
        raw,
        actual,
        CalibrationConfig(),
        selection_holdout_fraction=SELECTION_HOLDOUT_FRACTION,
        feature_times=times,
        label_end_times=ends,
        embargo=0,
    )
    purge = diag["label_end_purge"]
    boundary = purge["boundary_time"]
    assert purge["applied"] and boundary == times[300]
    # label_end strictly before boundary => the last surviving row ends before the held-out tail.
    expected_kept = int(np.sum((times[:300] < boundary) & (ends[:300] < boundary)))
    assert purge["fit_rows_after_purge"] == expected_kept
    assert purge["purged_rows"] == 300 - expected_kept
    assert purge["purged_rows"] > 0  # every horizon here leaks at least one fit row
    assert diag["selection_source"] == "calibration_a_heldout_tail_label_end_purged"


def test_longer_horizon_purges_more_rows() -> None:
    purged = []
    for horizon in (15, 30, 60, 120):
        raw, actual, times, ends = _timed(400, horizon)
        _sel, diag = fit_calibrator(
            raw,
            actual,
            CalibrationConfig(),
            selection_holdout_fraction=SELECTION_HOLDOUT_FRACTION,
            feature_times=times,
            label_end_times=ends,
        )
        purged.append(diag["label_end_purge"]["purged_rows"])
    assert purged == sorted(purged) and purged[0] < purged[-1]


def test_embargo_extends_the_purge() -> None:
    raw, actual, times, ends = _timed(400, 60)
    kwargs = dict(
        selection_holdout_fraction=SELECTION_HOLDOUT_FRACTION,
        feature_times=times,
        label_end_times=ends,
    )
    _s, base = fit_calibrator(raw, actual, CalibrationConfig(), embargo=0, **kwargs)
    _s, wide = fit_calibrator(raw, actual, CalibrationConfig(), embargo=60 * _MINUTE_US, **kwargs)
    assert wide["label_end_purge"]["purged_rows"] > base["label_end_purge"]["purged_rows"]


def test_no_surviving_fit_rows_falls_back_to_identity() -> None:
    raw, actual, times, ends = _timed(400, 120)
    # labels so long that every fit row overlaps the held-out tail
    ends = times + 10_000 * 15 * _MINUTE_US
    selected, diag = fit_calibrator(
        raw,
        actual,
        CalibrationConfig(),
        selection_holdout_fraction=SELECTION_HOLDOUT_FRACTION,
        feature_times=times,
        label_end_times=ends,
    )
    assert selected.method == "identity" and selected.slope == 1.0 and selected.intercept == 0.0
    assert diag["selection_source"] == "identity_fallback_insufficient_purged_fit_rows"
    assert diag["heldout_mae"] == {}


def test_times_must_be_supplied_together_and_match_shape() -> None:
    raw, actual, times, ends = _timed(400, 60)
    with pytest.raises(ValueError):
        fit_calibrator(raw, actual, CalibrationConfig(), feature_times=times)
    with pytest.raises(ValueError):
        fit_calibrator(
            raw, actual, CalibrationConfig(), feature_times=times[:-1], label_end_times=ends[:-1]
        )


def test_calibration_inputs_are_calibration_a_only() -> None:
    import inspect

    params = set(inspect.signature(fit_calibrator).parameters)
    assert not {"calibration_b", "test", "cal_b", "test_table"} & params
