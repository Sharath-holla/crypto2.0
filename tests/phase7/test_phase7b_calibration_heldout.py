"""Added by Claude (2026-11-02, finding L-03): calibrator method chosen on a held-out Cal-A tail."""

from __future__ import annotations

import numpy as np

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
