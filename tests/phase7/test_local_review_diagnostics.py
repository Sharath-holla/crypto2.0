"""Independent review regressions; all arrays here are synthetic unit fixtures."""

from __future__ import annotations

import numpy as np
import pytest

from crypto_ai.phase7 import experiment_identity, hardening
from crypto_ai.phase7.action_metrics import ActionThresholds, action_diagnostics
from crypto_ai.phase7.regression_diagnostics import regression_snapshot
from crypto_ai.phase7.training_observer import monitor_indices


@pytest.mark.parametrize("field", ["event_threshold_bps", "prediction_threshold_bps"])
def test_unrepresentable_raw_threshold_is_rejected(field: str) -> None:
    values = {"event_threshold_bps": 5.0, "prediction_threshold_bps": 5.0, field: 1e-323}
    with pytest.raises(ValueError, match="raw-return units"):
        ActionThresholds(**values)


def test_actions_remain_disjoint_at_zero_and_threshold_boundaries() -> None:
    values = np.array([-0.0005, 0.0, 0.0005])
    result = action_diagnostics(values, values, ActionThresholds(5.0, 5.0))
    assert result.long.predicted_count == result.short.predicted_count == 1
    assert result.no_trade_count == 1
    assert result.action_coverage == pytest.approx(2 / 3)


@pytest.mark.parametrize("seed", [0, 25, 20261108])
def test_monitor_limit_preserves_whole_uneven_cross_sections(seed: int) -> None:
    times = np.repeat(np.arange(101), [9900] + [1] * 100)
    selected = monitor_indices(len(times), 1000, times, seed=seed)
    assert selected is not None and 0 < len(selected) <= 1000
    np.testing.assert_array_equal(selected, monitor_indices(len(times), 1000, times, seed=seed))
    for time in np.unique(times[selected]):
        assert np.count_nonzero(times[selected] == time) == np.count_nonzero(times == time)


def test_oversized_cross_section_disables_diagnostics_instead_of_exceeding_limit() -> None:
    with pytest.raises(ValueError, match="MONITOR_CROSS_SECTION_EXCEEDS_ROW_LIMIT"):
        monitor_indices(2000, 1000, np.zeros(2000))


def test_monitor_rejects_timestamp_length_mismatch_before_sampling() -> None:
    with pytest.raises(ValueError, match="ROW_MISALIGNMENT"):
        monitor_indices(10, 1000, np.arange(9))


def test_prediction_distribution_includes_predictions_with_missing_actuals() -> None:
    result = regression_snapshot(np.array([1.0, np.nan]), np.array([1.0, 100.0]))
    assert result["rows_valid"] == 1
    assert result["rmse"] == 0.0
    assert result["prediction_mean"] == 50.5
    assert result["prediction_max"] == 100.0
    assert result["finite_prediction_fraction"] == 1.0


def test_prediction_distribution_available_when_no_actual_is_finite() -> None:
    result = regression_snapshot(np.array([np.nan, np.nan]), np.array([1.0, 3.0]))
    assert result["rows_valid"] == 0
    assert result["rmse"] is None
    assert result["prediction_mean"] == 2.0
    assert result["prediction_std"] == 1.0


def test_variance_ratio_compares_the_same_finite_pairs() -> None:
    result = regression_snapshot(np.array([1.0, 3.0, np.nan]), np.array([1.0, 3.0, 100.0]))
    assert result["prediction_std"] > 1.0
    assert result["prediction_actual_std_ratio"] == 1.0


def test_fit_boundary_source_changes_invalidate_experiment_control_identity(tmp_path) -> None:
    for relative in experiment_identity.EXPERIMENT_CONTROL_SOURCE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic source identity fixture\n")
    before = experiment_identity.experiment_control_identity({}, tmp_path)
    guard = tmp_path / "src/crypto_ai/phase7/fit_boundary.py"
    guard.write_text("# changed fit acceptance rule\n")
    after = experiment_identity.experiment_control_identity({}, tmp_path)
    assert before["manifest_sha256"] != after["manifest_sha256"]


def test_missing_fit_boundary_source_fails_closed(tmp_path) -> None:
    for relative in experiment_identity.EXPERIMENT_CONTROL_SOURCE_FILES:
        if relative.endswith("/fit_boundary.py"):
            continue
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# synthetic source identity fixture\n")
    with pytest.raises(RuntimeError, match="fit_boundary.py"):
        experiment_identity.experiment_control_identity({}, tmp_path)


def test_monitoring_setting_classifications_remain_consistent() -> None:
    from dataclasses import asdict

    assert set(asdict(hardening.HardeningConfig())) == set(hardening.SETTING_CLASSES)
    assert experiment_identity.MONITORING_ONLY_SETTINGS == hardening.MONITORING_ONLY_SETTINGS
