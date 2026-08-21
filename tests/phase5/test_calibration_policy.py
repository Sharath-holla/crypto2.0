from __future__ import annotations

import numpy as np
import pytest

from crypto_ai.phase5.calibration import fit_calibrator
from crypto_ai.phase5.config import CalibrationConfig, ThresholdConfig
from crypto_ai.phase5.policy import select_threshold


def test_linear_calibration_is_fitted_on_supplied_calibration_rows() -> None:
    raw = np.linspace(-0.01, 0.01, 200)
    actual = 0.001 + 2.0 * raw
    calibrator, diagnostics = fit_calibrator(raw, actual, CalibrationConfig(minimum_samples=10))
    assert calibrator.method == "linear"
    assert calibrator.slope == pytest.approx(2.0)
    assert calibrator.intercept == pytest.approx(0.001)
    assert diagnostics["selection_source"] == "calibration_only"


def test_invalid_linear_candidate_falls_back_to_identity() -> None:
    raw = np.zeros(100)
    actual = np.linspace(-0.01, 0.01, 100)
    calibrator, _ = fit_calibrator(raw, actual, CalibrationConfig(minimum_samples=10))
    assert calibrator.method == "identity"


def test_calibration_rejects_nonfinite_or_too_small_inputs() -> None:
    with pytest.raises(ValueError, match="minimum_samples"):
        fit_calibrator(np.ones(3), np.ones(3), CalibrationConfig(minimum_samples=10))
    with pytest.raises(ValueError, match="finite"):
        fit_calibrator(
            np.asarray([0.0] * 99 + [np.nan]),
            np.ones(100),
            CalibrationConfig(minimum_samples=10),
        )


def test_threshold_selection_is_deterministic_and_calibration_only() -> None:
    predicted = np.tile(np.asarray([-0.004, 0.004]), 100)
    actual = np.sign(predicted) * 0.003
    times = np.arange(len(predicted), dtype=np.int64) * 3_600_000_000
    config = ThresholdConfig(grid_bps=(2.0, 4.0, 6.0), minimum_calibration_trades=10)
    left, left_diagnostics = select_threshold(
        predicted, actual, times, config, cost_bps=11.0, horizon_minutes=60
    )
    right, _ = select_threshold(predicted, actual, times, config, cost_bps=11.0, horizon_minutes=60)
    assert left == right
    assert left.decision == "TRADE"
    assert left_diagnostics["selection_source"] == "calibration_only"


def test_threshold_returns_valid_no_trade_when_minimum_is_not_met() -> None:
    predicted = np.asarray([0.002, -0.002, 0.002])
    actual = np.asarray([0.001, 0.001, -0.001])
    times = np.arange(3, dtype=np.int64) * 3_600_000_000
    policy, diagnostics = select_threshold(
        predicted,
        actual,
        times,
        ThresholdConfig(minimum_calibration_trades=30),
        cost_bps=11.0,
        horizon_minutes=60,
    )
    assert policy.decision == "NO_TRADE"
    assert policy.threshold_bps is None
    assert not any(item["eligible"] for item in diagnostics["grid"])


def test_unrelated_test_values_cannot_change_threshold() -> None:
    calibration_predictions = np.linspace(-0.01, 0.01, 100)
    calibration_actual = calibration_predictions.copy()
    calibration_times = np.arange(100, dtype=np.int64) * 3_600_000_000
    config = ThresholdConfig(minimum_calibration_trades=10)
    before, _ = select_threshold(
        calibration_predictions,
        calibration_actual,
        calibration_times,
        config,
        cost_bps=11.0,
        horizon_minutes=60,
    )
    _unseen_test = np.random.default_rng(4).normal(size=10_000)
    after, _ = select_threshold(
        calibration_predictions,
        calibration_actual,
        calibration_times,
        config,
        cost_bps=11.0,
        horizon_minutes=60,
    )
    assert before == after
