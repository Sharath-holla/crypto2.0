"""Added by Claude (2026-11-08, pre-RunPod hardening): training observer, action diagnostics,
regression diagnostics, units, undefined metrics, isolation, telemetry, identity and fit boundary.

Every expected value in the action-diagnostic tests is calculated by hand in the comments.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, fields, replace
from pathlib import Path

import numpy as np
import pyarrow as pa
import pytest

from crypto_ai.phase7 import action_metrics as am
from crypto_ai.phase7 import hardening as h
from crypto_ai.phase7 import regression_diagnostics as rd
from crypto_ai.phase7 import training_observer as obs
from crypto_ai.phase7.config import ModelConfig, Phase7Config
from crypto_ai.phase7.experiment_identity import (
    MONITORING_ONLY_SETTINGS as IDENTITY_MONITORING_ONLY,
)
from crypto_ai.phase7.experiment_identity import experiment_control_identity
from crypto_ai.phase7.fit_boundary import (
    assert_fit_matrices,
    assert_fit_segments,
    prediction_health,
    sample_weight_summary,
)
from crypto_ai.phase7.targets import effective_normalization_scale

ROOT = Path(__file__).resolve().parents[2]


def thresholds(bps: float = 25.0, prediction_bps: float | None = None) -> am.ActionThresholds:
    return am.ActionThresholds(bps, bps if prediction_bps is None else prediction_bps)


# ------------------------------------------------------------------ action diagnostics: by hand
def test_long_example_from_the_brief_matches_hand_calculation() -> None:
    # threshold 25 bps = 0.0025 for events and actions.
    # actual    [+0.003, +0.002, -0.001, +0.004] -> LONG events     [T, F, F, T]  (2 events)
    # predicted [+0.004, -0.001, +0.003, +0.005] -> LONG actions    [T, F, T, T]  (3 actions)
    # TP = rows 0, 3 = 2; FP = row 2 = 1; FN = 0
    # precision 2/3, recall 2/2 = 1, F1 = 2*2 / (2*2 + 1 + 0) = 0.8
    actual = np.array([0.003, 0.002, -0.001, 0.004])
    predicted = np.array([0.004, -0.001, 0.003, 0.005])
    out = am.action_diagnostics(actual, predicted, thresholds()).to_flat_dict()
    assert (out["long_true_positives"], out["long_false_positives"]) == (2, 1)
    assert out["long_false_negatives"] == 0
    assert out["long_precision"] == pytest.approx(2 / 3)
    assert out["long_recall"] == pytest.approx(1.0)
    assert out["long_f1"] == pytest.approx(0.8)
    assert out["long_support"] == 2 and out["long_predicted_count"] == 3
    # No row is <= -0.0025 on either side: SHORT precision and recall are NOT_DEFINED, not 0.
    assert out["short_precision"] is None and out["short_precision_status"] == am.NOT_DEFINED
    assert out["short_recall"] is None and out["short_recall_reason"] == "NO_ACTUAL_SHORT_EVENTS"
    assert out["short_f1"] is None
    # 3 actions (all LONG) out of 4 rows; NO_TRADE = 1.
    assert out["action_coverage"] == pytest.approx(0.75)
    assert out["no_trade_coverage"] == pytest.approx(0.25)
    # Action direction hit-rate: actions on rows 0, 2, 3; actual > 0 on rows 0 and 3 -> 2/3.
    assert out["action_hit_rate"] == pytest.approx(2 / 3)
    assert out["metric_class"] == "DESCRIPTIVE_VALIDATION_DIAGNOSTIC"
    assert out["action_units"] == "RAW_RETURN_DECIMAL"


def test_short_mirror_example_matches_hand_calculation() -> None:
    # Mirror image of the LONG case: every sign flipped -> identical SHORT scores.
    actual = -np.array([0.003, 0.002, -0.001, 0.004])
    predicted = -np.array([0.004, -0.001, 0.003, 0.005])
    out = am.action_diagnostics(actual, predicted, thresholds()).to_flat_dict()
    assert out["short_precision"] == pytest.approx(2 / 3)
    assert out["short_recall"] == pytest.approx(1.0)
    assert out["short_f1"] == pytest.approx(0.8)
    assert out["short_support"] == 2
    assert out["long_precision"] is None and out["long_recall"] is None


def test_mixed_long_short_cross_errors() -> None:
    # 10 bps thresholds (0.001).
    # row  actual   predicted  LONG ev  SHORT ev  LONG act  SHORT act
    #  0   +0.002   +0.002       T         F         T         F    LONG TP
    #  1   -0.002   +0.002       F         T         T         F    LONG FP, SHORT FN
    #  2   -0.002   -0.002       F         T         F         T    SHORT TP
    #  3   +0.002   -0.002       T         F         F         T    SHORT FP, LONG FN
    #  4   +0.0005  +0.0005      F         F         F         F    NO_TRADE
    out = am.action_diagnostics(
        np.array([0.002, -0.002, -0.002, 0.002, 0.0005]),
        np.array([0.002, 0.002, -0.002, -0.002, 0.0005]),
        thresholds(10.0),
    ).to_flat_dict()
    assert out["long_precision"] == pytest.approx(0.5) and out["long_recall"] == pytest.approx(0.5)
    assert out["short_precision"] == pytest.approx(0.5)
    assert out["short_recall"] == pytest.approx(0.5)
    assert out["long_f1"] == pytest.approx(0.5) and out["macro_f1"] == pytest.approx(0.5)
    assert out["no_trade_count"] == 1 and out["action_coverage"] == pytest.approx(0.8)
    assert out["action_hit_rate"] == pytest.approx(0.5)


def test_all_correct_and_all_wrong() -> None:
    actual = np.array([0.01, -0.01, 0.01, -0.01])
    right = am.action_diagnostics(actual, actual.copy(), thresholds()).to_flat_dict()
    assert right["long_precision"] == right["long_recall"] == right["long_f1"] == 1.0
    assert right["short_precision"] == right["short_recall"] == right["short_f1"] == 1.0
    wrong = am.action_diagnostics(actual, -actual, thresholds()).to_flat_dict()
    # Defined denominators, zero true positives: a GENUINE 0.0, distinct from NOT_DEFINED.
    assert wrong["long_precision"] == 0.0 and wrong["long_precision_status"] == am.DEFINED
    assert wrong["long_recall"] == 0.0 and wrong["long_f1"] == 0.0
    assert wrong["action_hit_rate"] == 0.0


def test_no_predicted_actions_is_not_defined_and_never_zero() -> None:
    actual = np.array([0.01, -0.01, 0.0])
    out = am.action_diagnostics(actual, np.zeros(3), thresholds()).to_flat_dict()
    for side in ("long", "short"):
        assert out[f"{side}_precision"] is None
        assert out[f"{side}_precision_status"] == am.NOT_DEFINED
        assert out[f"{side}_recall"] == 0.0  # events exist, none captured: genuine zero
        assert out[f"{side}_f1"] is None
    assert out["action_hit_rate"] is None and out["action_hit_rate_status"] == am.NOT_DEFINED
    assert out["action_coverage"] == 0.0 and out["no_trade_coverage"] == 1.0


def test_no_actual_events_is_not_defined() -> None:
    out = am.action_diagnostics(np.zeros(3), np.array([0.01, -0.01, 0.0]), thresholds())
    flat = out.to_flat_dict()
    assert flat["long_recall"] is None and flat["long_recall_reason"] == "NO_ACTUAL_LONG_EVENTS"
    assert flat["long_precision"] == 0.0  # one LONG action, not an event: genuine zero
    # The two actions have zero actual return: no direction, excluded from the hit-rate.
    assert flat["action_hit_rate"] is None
    assert flat["action_hit_rate_zero_actual_excluded"] == 2


def test_ties_exactly_on_threshold_are_inclusive_and_zero_is_never_an_event() -> None:
    t = thresholds(5.0)  # 0.0005
    actual = np.array([0.0005, -0.0005, 0.0, 0.00049])
    predicted = np.array([0.0005, -0.0005, 0.0, 0.00049])
    out = am.action_diagnostics(actual, predicted, t).to_flat_dict()
    assert out["long_support"] == 1 and out["long_predicted_count"] == 1
    assert out["short_support"] == 1 and out["short_predicted_count"] == 1
    assert out["no_trade_count"] == 2  # the exact zero and the just-below-threshold row


def test_non_finite_rows_are_excluded_and_counted() -> None:
    actual = np.array([0.01, np.nan, 0.01, np.inf])
    predicted = np.array([0.01, 0.01, np.nan, 0.01])
    out = am.action_diagnostics(actual, predicted, thresholds()).to_flat_dict()
    assert out["action_rows_total"] == 4 and out["action_rows_valid"] == 1
    assert out["action_rows_excluded_non_finite"] == 3
    assert out["long_precision"] == 1.0 and out["long_support"] == 1


def test_empty_input_is_all_not_defined() -> None:
    out = am.action_diagnostics(np.array([]), np.array([]), thresholds()).to_flat_dict()
    assert out["action_coverage"] is None and out["long_precision"] is None
    assert out["long_recall"] is None and out["macro_f1"] is None


@pytest.mark.parametrize("bad", [0.0, -5.0, float("nan"), float("inf"), True, "5"])
def test_thresholds_must_be_finite_positive_numbers(bad) -> None:
    with pytest.raises(ValueError):
        am.ActionThresholds(bad, 5.0)
    with pytest.raises(ValueError):
        am.ActionThresholds(5.0, bad)


def test_misaligned_inputs_raise() -> None:
    with pytest.raises(ValueError, match="aligned"):
        am.action_diagnostics(np.zeros(3), np.zeros(4), thresholds())


def test_bps_threshold_is_really_raw_bps() -> None:
    # 5 bps == 0.0005 raw. 0.0004 must not trigger; 0.0006 must.
    t = thresholds(5.0)
    assert t.event_threshold == pytest.approx(0.0005)
    out = am.action_diagnostics(np.array([0.0004, 0.0006]), np.array([0.0004, 0.0006]), t)
    assert out.long.event_count == 1 and out.long.predicted_count == 1


# ------------------------------------------------------------------ normalized -> raw units
@pytest.mark.parametrize(
    ("scale", "expected"),
    [(0.02, 0.02), (0.001, 0.001), (0.0004, 0.001), (0.0, 0.001), (-0.02, 0.02)],
    ids=["above_floor", "equal_floor", "below_floor", "zero", "negative"],
)
def test_effective_scale_vector_matches_forward_divisor(scale: float, expected: float) -> None:
    floor = 0.001
    vector = am.effective_scale_vector(np.array([scale]), floor)
    assert vector[0] == pytest.approx(expected)
    assert vector[0] == pytest.approx(effective_normalization_scale(scale, floor))
    assert vector[0] > 0  # the divisor is positive: conversion can never flip a sign


def test_effective_scale_vector_keeps_nan_and_rejects_bad_floor() -> None:
    assert np.isnan(am.effective_scale_vector(np.array([np.nan]), 0.001)[0])
    for floor in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError):
            am.effective_scale_vector(np.array([0.01]), floor)


def test_normalized_predictions_are_converted_to_raw_before_bps_thresholds() -> None:
    floor = 0.001
    raw_actual = np.array([0.003, 0.002, -0.001, 0.004])
    raw_predicted = np.array([0.004, -0.001, 0.003, 0.005])
    scale = np.array([0.02, 0.001, 0.0004, 0.0])  # above / equal / below floor / zero
    divisor = am.effective_scale_vector(scale, floor)
    normalized_predicted = raw_predicted / divisor  # what a normalized model would output
    converted = am.to_raw_returns(normalized_predicted, divisor)
    assert np.allclose(converted, raw_predicted) and np.all(
        np.sign(converted) == np.sign(raw_predicted)
    )
    t = thresholds()
    expected = am.action_diagnostics(raw_actual, raw_predicted, t).to_flat_dict()
    assert am.action_diagnostics(raw_actual, converted, t).to_flat_dict() == expected
    # The old defect: thresholding NORMALISED values as if they were raw bps gives different
    # answers (row 0: normalised 0.2 vs raw 0.004). Units are not interchangeable.
    wrong = am.action_diagnostics(raw_actual, normalized_predicted, t).to_flat_dict()
    assert wrong != expected


def test_to_raw_returns_requires_alignment() -> None:
    assert np.array_equal(am.to_raw_returns(np.array([1.0]), None), np.array([1.0]))
    with pytest.raises(ValueError, match="aligned"):
        am.to_raw_returns(np.array([1.0, 2.0]), np.array([1.0]))


def _validation_table(raw: np.ndarray, scale: np.ndarray, times: np.ndarray) -> pa.Table:
    return pa.table(
        {
            "raw_future_return": raw,
            "ex_ante_volatility_scale": scale,
            "feature_time": pa.array(times, type=pa.timestamp("us", tz="UTC")),
        }
    )


def test_validation_context_and_unit_guard_fail_closed() -> None:
    floor = 0.001
    raw = np.array([0.003, -0.002, 0.001, 0.004])
    scale = np.array([0.02, 0.001, 0.0004, 0.0])
    table = _validation_table(raw, scale, np.arange(4) * 300_000_000)
    context = obs.build_validation_context(
        table, target_type="normalized", normalization_floor=floor, thresholds=thresholds()
    )
    assert context.target_units == obs.TARGET_UNITS_NORMALIZED
    normalized_y = raw / np.maximum(np.abs(scale), floor)
    x = np.zeros((4, 1))
    diag = obs.TrainingDiagnostics(context, obs.MonitorSettings(), x, normalized_y)
    assert diag.describe()["prediction_conversion"].startswith("RAW = PREDICTION x max(")
    # Feeding RAW y to a normalised context (unit mix-up) is refused.
    with pytest.raises(ValueError, match="TARGET_UNIT_MISMATCH"):
        obs.TrainingDiagnostics(context, obs.MonitorSettings(), x, raw)
    # Row misalignment is refused.
    with pytest.raises(ValueError, match="ROW_MISALIGNMENT"):
        obs.TrainingDiagnostics(context, obs.MonitorSettings(), x[:3], normalized_y[:3])
    raw_context = obs.build_validation_context(
        table, target_type="raw", normalization_floor=floor, thresholds=thresholds()
    )
    assert raw_context.prediction_divisor is None
    assert raw_context.target_units == obs.TARGET_UNITS_RAW


def test_snapshot_of_normalized_model_scores_actions_in_raw_units() -> None:
    floor = 0.001
    raw = np.array([0.003, 0.002, -0.001, 0.004])
    scale = np.array([0.02, 0.001, 0.0004, 0.0])
    divisor = np.maximum(np.abs(scale), floor)
    context = obs.build_validation_context(
        _validation_table(raw, scale, np.arange(4)),
        target_type="normalized",
        normalization_floor=floor,
        thresholds=thresholds(),
    )
    diag = obs.TrainingDiagnostics(context, obs.MonitorSettings(), np.zeros((4, 1)), raw / divisor)
    raw_predicted = np.array([0.004, -0.001, 0.003, 0.005])
    snapshot = diag.snapshot(lambda _x: raw_predicted / divisor, cross_section=False)
    assert snapshot["action"]["long_precision"] == pytest.approx(2 / 3)
    assert snapshot["action"]["long_f1"] == pytest.approx(0.8)


# ------------------------------------------------------------------ regression diagnostics
def test_correlations_are_none_when_undefined() -> None:
    assert rd.pearson(np.ones(5), np.arange(5.0)) is None
    assert rd.spearman(np.arange(5.0), np.full(5, 2.0)) is None
    assert rd.pearson(np.array([1.0]), np.array([2.0])) is None
    assert rd.directional_accuracy_nonzero(np.zeros(3), np.ones(3)) is None
    assert rd.spearman(np.arange(5.0), np.arange(5.0) ** 3) == pytest.approx(1.0)


def test_average_ranks_handle_ties() -> None:
    assert rd.average_ranks(np.array([3.0, 1.0, 3.0, 2.0])).tolist() == [3.5, 1.0, 3.5, 2.0]


def test_regression_snapshot_values_and_constant_predictions() -> None:
    actual = np.array([0.01, -0.02, 0.03, 0.0])
    out = rd.regression_snapshot(actual, np.zeros(4))
    assert out["rmse"] == pytest.approx(math.sqrt(np.mean(actual**2)))
    assert out["prediction_std"] == 0.0 and out["pearson"] is None
    assert out["prediction_near_zero_fraction"] == 1.0
    assert out["directional_accuracy"] == 0.0  # zero predictions miss every non-zero actual
    assert out["n_zero_actuals"] == 1
    nan = rd.regression_snapshot(actual, np.array([np.nan, 0.0, 0.0, 0.0]))
    assert nan["finite_prediction_fraction"] == pytest.approx(0.75)
    assert nan["rows_excluded_non_finite"] == 1
    empty = rd.regression_snapshot(np.array([]), np.array([]))
    assert empty["rmse"] is None and empty["finite_prediction_fraction"] is None


def test_cross_sectional_ic_matches_reference_and_uses_same_timestamp_only() -> None:
    rng = np.random.default_rng(7)
    times = np.repeat(np.arange(40), 8)
    actual = rng.normal(size=len(times))
    predicted = actual * 0.3 + rng.normal(size=len(times))
    fast = rd.cross_sectional_spearman(times, predicted, actual, min_symbols=5)
    reference = h.cross_sectional_ic(times, predicted, actual, min_symbols=5)
    assert fast["xs_spearman_ic_mean"] == pytest.approx(reference["mean_xs_spearman_ic"])
    assert fast["xs_timestamps_scored"] == reference["timestamps_scored"] == 40
    # A per-timestamp level shift (common to all assets) cannot change a cross-sectional IC.
    shifted = rd.cross_sectional_spearman(times, predicted + times * 100.0, actual, min_symbols=5)
    assert shifted["xs_spearman_ic_mean"] == pytest.approx(fast["xs_spearman_ic_mean"])


def test_cross_sectional_ic_small_and_constant_cross_sections() -> None:
    times = np.repeat(np.arange(3), 3)  # 3 assets per timestamp < 5
    small = rd.cross_sectional_spearman(times, np.arange(9.0), np.arange(9.0), min_symbols=5)
    assert small["xs_status"] == "NOT_DEFINED" and small["xs_spearman_ic_mean"] is None
    assert small["xs_timestamps_skipped_small"] == 3
    times = np.repeat(np.arange(2), 5)
    constant = rd.cross_sectional_spearman(times, np.zeros(10), np.arange(10.0), min_symbols=5)
    assert constant["xs_status"] == "NOT_DEFINED"
    assert constant["xs_timestamps_skipped_constant"] == 2


# ------------------------------------------------------------------ JSON / console / health
def test_json_safe_maps_non_finite_to_null() -> None:
    out = obs.json_safe({"a": float("nan"), "b": np.float64(np.inf), "c": [np.int64(3)]})
    assert out == {"a": None, "b": None, "c": [3]}
    json.dumps(out, allow_nan=False)


def test_console_shows_na_for_undefined_with_support_counts() -> None:
    action = am.action_diagnostics(np.array([0.01]), np.array([0.0]), thresholds()).to_flat_dict()
    line = obs.format_side("long", "LONG", action)
    assert "precision   N/A" in line and "actual events (support) 1" in line
    assert "predicted 0" in line


def test_monitor_indices_are_deterministic_and_keep_whole_timestamps() -> None:
    times = np.repeat(np.arange(1000), 10)
    first = obs.monitor_indices(len(times), 2_000, times)
    assert first is not None and np.array_equal(
        first, obs.monitor_indices(len(times), 2_000, times)
    )
    kept_times, counts = np.unique(times[first], return_counts=True)
    assert np.all(counts == 10) and 150 <= len(kept_times) <= 250
    assert obs.monitor_indices(100, 1_000) is None


def test_health_flags_are_descriptive_and_classified() -> None:
    settings = obs.MonitorSettings(min_iterations=0, plateau_rounds=5)
    tracker = obs.HealthTracker(settings)
    tracker.update(
        iteration=1,
        train_rmse=1.0,
        validation_rmse=1.0,
        best_validation_rmse=1.0,
        rounds_since_best=0,
        snapshot=None,
        resources={"effective_memory_available": 0, "disk_free_bytes": 0},
    )
    out = tracker.update(
        iteration=10,
        train_rmse=0.5,
        validation_rmse=1.5,
        best_validation_rmse=1.0,
        rounds_since_best=9,
        snapshot={"regression": {"prediction_std": 0.0, "finite_prediction_fraction": 0.5}},
        resources={},
    )
    codes = {
        f["code"]: f["severity"] for group in out.values() if isinstance(group, list) for f in group
    }
    assert codes["NON_FINITE_PREDICTIONS"] == obs.HARD_FAILURE
    assert codes["TRAIN_VALIDATION_GAP_HIGH"] == obs.WARNING
    assert codes["PREDICTIONS_NEAR_CONSTANT"] == obs.WARNING
    assert codes["OVERFITTING_PATTERN"] == obs.WARNING
    assert codes["VALIDATION_LOSS_PLATEAU"] == obs.INFORMATIONAL
    assert out["relative_generalization_gap"] == pytest.approx(2.0)
    assert tracker.flag_counts["MEMORY_PRESSURE"] == 1 and tracker.flag_counts["DISK_PRESSURE"] == 1


def test_training_health_summary_labels() -> None:
    settings = obs.MonitorSettings()
    base = dict(
        settings=settings,
        first_validation_rmse=1.0,
        selected_train_rmse=0.9,
        selected_validation_rmse=0.95,
        zero_baseline_rmse=1.0,
    )
    good = {
        "regression": {"spearman": 0.05, "prediction_std": 0.1, "prediction_actual_std_ratio": 0.1}
    }
    learn = obs.summarize_training_health(best_validation_rmse=0.95, final_snapshot=good, **base)
    assert learn["label"] == obs.LEARNING_SIGNAL_PRESENT
    flat = obs.summarize_training_health(best_validation_rmse=1.01, final_snapshot=good, **base)
    assert flat["label"] == obs.NO_CLEAR_VALIDATION_IMPROVEMENT
    collapsed = {"regression": {"prediction_std": 0.0}}
    assert (
        obs.summarize_training_health(best_validation_rmse=0.95, final_snapshot=collapsed, **base)[
            "label"
        ]
        == obs.PREDICTION_COLLAPSE
    )
    none = obs.summarize_training_health(best_validation_rmse=None, final_snapshot=None, **base)
    assert none["label"] == obs.INSUFFICIENT_DATA
    assert "HEURISTIC" in learn["heuristic_notice"]


def test_report_view_drops_operational_fields() -> None:
    view = obs.report_view(
        {
            "label": "X",
            "attempt_id": "a",
            "log_file": "f",
            "telemetry_status": "OK",
            "flag_counts": {"MEMORY_PRESSURE": 2, "VALIDATION_LOSS_PLATEAU": 1},
            "final_snapshot": {"diagnostic_seconds": 1.2, "regression": {}},
        }
    )
    assert "attempt_id" not in view and "log_file" not in view
    assert view["flag_counts"] == {"VALIDATION_LOSS_PLATEAU": 1}
    assert "diagnostic_seconds" not in view["final_snapshot"]


# ------------------------------------------------------------------ real LightGBM observer
def _fit_fixture(n_train: int = 600, n_val: int = 200, seed: int = 3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n_train + n_val, 4))
    y = 0.002 * x[:, 0] + rng.normal(scale=0.002, size=len(x))
    times = np.repeat(np.arange((n_train + n_val) // 5), 5)[: len(x)] * 300_000_000
    return x[:n_train], y[:n_train], x[n_train:], y[n_train:], times[n_train:]


def _context(validation_y: np.ndarray, times: np.ndarray, bps: float = 5.0):
    table = _validation_table(validation_y, np.full(len(validation_y), 0.01), times)
    return obs.build_validation_context(
        table, target_type="raw", normalization_floor=0.001, thresholds=thresholds(bps)
    )


def _records(directory: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(directory.glob("fit-*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_diagnostics_never_change_the_fit_or_early_stopping(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import training_metric_scope

    monkeypatch.setenv("PHASE7_METRICS_EVERY", "2")
    train_x, train_y, val_x, val_y, times = _fit_fixture()
    config = ModelConfig(n_estimators=60, early_stopping_rounds=5, min_child_samples=5)
    kwargs = dict(config=config, model_threads=1, sample_weight=None)
    reference = models._fit(train_x, train_y, val_x, val_y, **kwargs)
    fits = []
    for index, bps in enumerate((1.0, 50.0)):  # very different diagnostic thresholds
        directory = tmp_path / f"run{index}"
        with training_metric_scope(directory, diagnostics=_context(val_y, times, bps)) as scope:
            fits.append(models._fit(train_x, train_y, val_x, val_y, **kwargs))
        records = _records(directory)
        assert any(r["event"] == "VALIDATION_DIAGNOSTICS" for r in records)
        summary = scope.summaries["global"]
        assert summary["diagnostics_status"] == "ACTIVE"
        # The observer's best round (every round, strict improvement) == LightGBM early stopping.
        assert summary["best_validation_iteration_observed"] == fits[-1].best_iteration_
    for fit in fits:
        assert fit.best_iteration_ == reference.best_iteration_
        assert np.array_equal(fit.predict(val_x), reference.predict(val_x))
    assert list(fits[0].evals_result_["validation"])[0] == "l2"


def test_telemetry_records_carry_the_required_schema(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import training_metric_scope

    monkeypatch.setenv("PHASE7_METRICS_EVERY", "5")
    train_x, train_y, val_x, val_y, times = _fit_fixture()
    config = ModelConfig(n_estimators=30, early_stopping_rounds=10, min_child_samples=5)
    with training_metric_scope(
        tmp_path,
        diagnostics=_context(val_y, times),
        fold_id="fold-000",
        spec_id="architecture-G0-A6-60m-raw",
        architecture="G0",
        target_column="raw_future_return",
        horizon_minutes=60,
    ):
        models._fit(
            train_x, train_y, val_x, val_y, config=config, model_threads=1, sample_weight=None
        )
    records = _records(tmp_path)
    telemetry = [r for r in records if r["event"] == "TRAINING_TELEMETRY"]
    diagnostics = [r for r in records if r["event"] == "VALIDATION_DIAGNOSTICS"]
    assert telemetry and diagnostics
    for key in [
        "timestamp",
        "iteration",
        "elapsed_seconds",
        "spec_id",
        "fold_id",
        "architecture",
        "target",
        "horizon",
        "backend",
        "train_rmse",
        "validation_rmse",
        "validation_mae",
        "best_iteration",
        "best_validation_score",
        "rounds_since_best",
        "rss_bytes",
        "effective_memory_available",
        "disk_free_bytes",
        "metric_class",
        "learning_rate",
        "cpu_threads",
        "train_rows",
        "validation_rows",
        "feature_count",
    ]:
        assert key in telemetry[-1], key
    assert telemetry[-1]["metric_class"] == "DEVELOPMENT_METRIC"
    for key in [
        "validation_pearson",
        "validation_spearman",
        "validation_directional_accuracy",
        "long_precision",
        "long_recall",
        "long_f1",
        "long_support",
        "short_precision",
        "short_recall",
        "short_f1",
        "short_support",
        "action_coverage",
        "prediction_mean",
        "prediction_std",
        "prediction_min",
        "prediction_max",
    ]:
        assert key in diagnostics[-1], key
    assert diagnostics[-1]["metric_class"] == "DESCRIPTIVE_VALIDATION_DIAGNOSTIC"
    assert diagnostics[-1]["selection_eligible"] is False
    assert diagnostics[-1]["independent_evidence"] is False
    assert all(r["metric_scope"] == "TRAIN_AND_VALIDATION_ONLY" for r in records)
    # Check ids are unique: one record per check per attempt, no duplicated rounds.
    ids = [r["check_id"] for r in telemetry]
    assert len(ids) == len(set(ids))


def test_diagnostics_only_predict_validation_rows(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import training_metric_scope

    monkeypatch.setenv("PHASE7_METRICS_EVERY", "3")
    train_x, train_y, val_x, val_y, times = _fit_fixture()
    seen: list[np.ndarray] = []
    original = obs.TrainingDiagnostics.snapshot

    def spy(self, predict, **kwargs):
        def wrapped(x):
            seen.append(np.asarray(x))
            return predict(x)

        return original(self, wrapped, **kwargs)

    monkeypatch.setattr(obs.TrainingDiagnostics, "snapshot", spy)
    with training_metric_scope(tmp_path, diagnostics=_context(val_y, times)):
        models._fit(
            train_x,
            train_y,
            val_x,
            val_y,
            config=ModelConfig(n_estimators=20, min_child_samples=5),
            model_threads=1,
            sample_weight=None,
        )
    assert seen
    for matrix in seen:  # exactly the Validation matrix, never TRAIN (or any other) rows
        assert np.array_equal(matrix, val_x)


def test_telemetry_write_failure_degrades_but_never_fails_the_fit(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import training_metric_scope

    train_x, train_y, val_x, val_y, times = _fit_fixture()
    config = ModelConfig(n_estimators=20, min_child_samples=5)
    reference = models._fit(
        train_x, train_y, val_x, val_y, config=config, model_threads=1, sample_weight=None
    )
    real_open = Path.open

    def failing_open(self, *args, **kwargs):
        if self.name.startswith("fit-") and self.suffix == ".jsonl":
            raise OSError(28, "No space left on device")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    with training_metric_scope(tmp_path, diagnostics=_context(val_y, times)) as scope:
        fitted = models._fit(
            train_x, train_y, val_x, val_y, config=config, model_threads=1, sample_weight=None
        )
    assert np.array_equal(fitted.predict(val_x), reference.predict(val_x))
    assert scope.summaries["global"]["telemetry_status"] == "DEGRADED"
    assert not list(tmp_path.glob("fit-*.jsonl"))  # no log file, so no fabricated completion


def test_diagnostic_errors_are_contained(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import training_metric_scope

    monkeypatch.setenv("PHASE7_METRICS_EVERY", "1")
    train_x, train_y, val_x, val_y, times = _fit_fixture()

    def broken(self, predict, **kwargs):
        raise RuntimeError("BOOM")

    monkeypatch.setattr(obs.TrainingDiagnostics, "snapshot", broken)
    with training_metric_scope(tmp_path, diagnostics=_context(val_y, times)) as scope:
        models._fit(
            train_x,
            train_y,
            val_x,
            val_y,
            config=ModelConfig(n_estimators=20, min_child_samples=5),
            model_threads=1,
            sample_weight=None,
        )
    assert scope.summaries["global"]["diagnostics_status"] == "DISABLED_AFTER_REPEATED_ERRORS"


def test_resumed_attempt_writes_a_new_log_with_a_resume_marker(tmp_path) -> None:
    from crypto_ai.phase7.training_metrics import FitMetricObserver, TrainingMetricScope

    scope = TrainingMetricScope(tmp_path, {"fold_id": "f"})
    first = FitMetricObserver(scope, "global")
    first.fail(RuntimeError("crash"))  # interrupted attempt: never reached FIT_FINISHED
    second = FitMetricObserver(scope, "global")
    assert second.path != first.path and second.attempt_number == 2
    started = json.loads(second.path.read_text().splitlines()[0])
    assert started["event"] == "FIT_STARTED"
    assert started["resumed_after_incomplete_attempt"] is True
    assert started["prior_attempts"] == [{"file": first.path.name, "last_event": "FIT_FAILED"}]
    # The first log is untouched (nothing appended by the second attempt).
    assert [json.loads(x)["event"] for x in first.path.read_text().splitlines()] == [
        "FIT_STARTED",
        "FIT_FAILED",
    ]


def test_observer_modules_never_reference_held_out_segments() -> None:
    for name in ("training_observer.py", "action_metrics.py", "regression_diagnostics.py"):
        source = (ROOT / "src/crypto_ai/phase7" / name).read_text()
        for forbidden in ("release_test", "calibration_a", "calibration_b", "_test", "holdout"):
            assert forbidden not in source, (name, forbidden)


# ------------------------------------------------------------------ identity semantics
def test_every_hardening_setting_is_classified_and_lists_agree() -> None:
    assert set(h.SETTING_CLASSES) == {item.name for item in fields(h.HardeningConfig)}
    assert h.MONITORING_ONLY_SETTINGS == IDENTITY_MONITORING_ONLY


def test_monitoring_changes_do_not_change_control_identity_but_definitions_do() -> None:
    base = h.HardeningConfig()
    digest = experiment_control_identity(asdict(base))["manifest_sha256"]
    monitoring = replace(
        base, monitor_max_rows=10_000, health_plateau_rounds=7, console_table=False
    )
    assert experiment_control_identity(asdict(monitoring))["manifest_sha256"] == digest
    definition = replace(base, training_diagnostic_event_threshold_bps=10.0)
    assert experiment_control_identity(asdict(definition))["manifest_sha256"] != digest
    baseline = replace(base, baseline_ridge_alpha=2.0)
    assert experiment_control_identity(asdict(baseline))["manifest_sha256"] != digest


def test_hardening_settings_never_enter_the_prepared_matrix_identity(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7.preparation_identity import preparation_source_identity

    before = preparation_source_identity()["manifest_sha256"]
    toml = tmp_path / "h.toml"
    toml.write_text(
        "[hardening]\nmonitor_max_rows = 5000\ntraining_diagnostic_event_threshold_bps = 9.0\n"
    )
    monkeypatch.setenv(h.CONFIG_ENV, str(toml))
    h._cached_config.cache_clear()
    try:
        assert h.current_config().monitor_max_rows == 5000
        assert preparation_source_identity()["manifest_sha256"] == before
    finally:
        monkeypatch.delenv(h.CONFIG_ENV)
        h._cached_config.cache_clear()
    for name in (
        "training_observer.py",
        "action_metrics.py",
        "regression_diagnostics.py",
        "fit_boundary.py",
    ):
        from crypto_ai.phase7.preparation_identity import PREPARATION_SOURCE_FILES

        assert f"src/crypto_ai/phase7/{name}" not in PREPARATION_SOURCE_FILES


def test_lightgbm_parameters_change_the_configuration_identity() -> None:
    base = Phase7Config()
    changed = base.model_copy(
        update={"models": base.models.model_copy(update={"learning_rate": 0.03})}
    )
    assert changed.configuration_hash != base.configuration_hash


def test_new_hardening_values_are_validated() -> None:
    with pytest.raises(ValueError):
        h.HardeningConfig(training_diagnostic_event_threshold_bps=0.0)
    with pytest.raises(ValueError):
        h.HardeningConfig(monitor_max_rows=10)
    with pytest.raises(ValueError):
        h.HardeningConfig(health_min_free_disk_gib=float("nan"))


def test_resolved_monitor_manifest_lists_units_classes_and_sources(monkeypatch) -> None:
    monkeypatch.setenv("PHASE7_METRICS_EVERY", "50")
    rows = {row["name"]: row for row in obs.resolved_monitor_manifest()}
    assert rows["PHASE7_METRICS_EVERY"]["value"] == 50
    assert rows["PHASE7_METRICS_EVERY"]["source"] == "ENV"
    event = rows["training_diagnostic_event_threshold_bps"]
    assert event["class"] == "DIAGNOSTIC_DEFINITION" and event["unit"].startswith("bps")


# ------------------------------------------------------------------ fit boundary
def test_fit_matrices_are_checked_before_lightgbm() -> None:
    x, y = np.zeros((4, 2)), np.zeros(4)
    assert_fit_matrices(x, y, x, y, np.ones(4))
    with pytest.raises(ValueError, match="FIT_BOUNDARY_ROWS"):
        assert_fit_matrices(x, y[:3], x, y, None)
    with pytest.raises(ValueError, match="FIT_BOUNDARY_DTYPE"):
        assert_fit_matrices(x.astype(np.float32), y, x, y, None)
    with pytest.raises(ValueError, match="FIT_BOUNDARY_FEATURE_COUNT"):
        assert_fit_matrices(x, y, np.zeros((4, 3)), y, None)
    bad = x.copy()
    bad[2, 1] = np.nan
    with pytest.raises(ValueError, match="FIT_BOUNDARY_NON_FINITE"):
        assert_fit_matrices(bad, y, x, y, None)
    with pytest.raises(ValueError, match="FIT_BOUNDARY_WEIGHTS"):
        assert_fit_matrices(x, y, x, y, np.array([1.0, 0.0, 1.0, 1.0]))
    with pytest.raises(ValueError, match="FIT_BOUNDARY_ROWS"):
        assert_fit_matrices(x, y, x, y, np.ones(3))


def _segment(symbols: list[str], minutes: list[int], end_offset: int = 60):
    from types import SimpleNamespace

    us = 60_000_000
    table = pa.table(
        {
            "symbol": symbols,
            "feature_time": pa.array([m * us for m in minutes], type=pa.timestamp("us", tz="UTC")),
            "label_end_time": pa.array(
                [(m + end_offset) * us for m in minutes], type=pa.timestamp("us", tz="UTC")
            ),
        }
    )
    return table, SimpleNamespace(
        symbols=np.asarray(symbols, dtype=object), y=np.zeros(len(symbols))
    )


def _inputs(train, validation):
    from types import SimpleNamespace

    return SimpleNamespace(
        feature_columns=("f",),
        target_column="raw_future_return",
        train_y=train[1].y,
        validation_y=validation[1].y,
        train_symbols=train[1].symbols,
        validation_symbols=validation[1].symbols,
    )


def test_fit_segments_detect_duplicates_order_and_purge() -> None:
    train = _segment(["A", "B", "A"], [0, 0, 5])
    validation = _segment(["A", "B"], [200, 200])
    summary = assert_fit_segments(
        train[0],
        validation[0],
        model_inputs=_inputs(train, validation),
        feature_columns=("f",),
        target_column="raw_future_return",
        validation_start_us=100 * 60_000_000,
    )
    assert summary["train_rows"] == 3 and summary["train_labels_end_before_validation_start"]
    with pytest.raises(ValueError, match="FIT_BOUNDARY_PURGE"):
        assert_fit_segments(
            train[0],
            validation[0],
            model_inputs=_inputs(train, validation),
            feature_columns=("f",),
            target_column="raw_future_return",
            validation_start_us=30 * 60_000_000,
        )
    duplicated = _segment(["A", "A"], [0, 0])
    with pytest.raises(ValueError, match="FIT_BOUNDARY_DUPLICATE_ROWS"):
        assert_fit_segments(
            duplicated[0],
            validation[0],
            model_inputs=_inputs(duplicated, validation),
            feature_columns=("f",),
            target_column="raw_future_return",
        )
    swapped = _inputs(train, validation)
    swapped.train_symbols = np.asarray(["B", "A", "A"], dtype=object)
    with pytest.raises(ValueError, match="FIT_BOUNDARY_SYMBOL_ORDER"):
        assert_fit_segments(
            train[0],
            validation[0],
            model_inputs=swapped,
            feature_columns=("f",),
            target_column="raw_future_return",
        )
    with pytest.raises(ValueError, match="FIT_BOUNDARY_FEATURE_ORDER"):
        assert_fit_segments(
            train[0],
            validation[0],
            model_inputs=_inputs(train, validation),
            feature_columns=("g",),
            target_column="raw_future_return",
        )


def test_prediction_health_and_weight_summary() -> None:
    ok = prediction_health(np.array([0.1, 0.2, np.nan]), np.array([True, True, False]), rows=3)
    assert ok["status"] == "OK" and ok["covered_rows"] == 2
    constant = prediction_health(np.zeros(3), np.ones(3, dtype=bool), rows=3)
    assert constant["status"] == "WARNING_CONSTANT_PREDICTIONS"  # a warning, not an error
    with pytest.raises(ValueError, match="PREDICTION_BOUNDARY_NON_FINITE"):
        prediction_health(np.array([np.nan]), np.array([True]), rows=1)
    with pytest.raises(ValueError, match="PREDICTION_BOUNDARY_ROWS"):
        prediction_health(np.zeros(2), np.ones(2, dtype=bool), rows=3)
    from crypto_ai.phase7.models import symbol_balanced_weights

    symbols = np.asarray(["A", "A", "A", "B"], dtype=object)
    summary = sample_weight_summary(symbol_balanced_weights(symbols), symbols)
    assert summary["uses_target_information"] is False
    assert summary["per_symbol"]["A"]["total_weight_share"] == pytest.approx(0.5)
    assert summary["mean"] == pytest.approx(1.0)
    assert sample_weight_summary(None, symbols)["status"] == "UNWEIGHTED"


# ------------------------------------------------------------------ matched Ridge (v3)
def test_matched_ridge_equals_closed_form_weighted_ridge_on_all_rows() -> None:
    rng = np.random.default_rng(11)
    x = rng.normal(size=(1_000, 3)) * np.array([1.0, 10.0, 0.1]) + np.array([0.0, 5.0, -1.0])
    y = x @ np.array([0.01, -0.002, 0.3]) + rng.normal(scale=0.01, size=1_000)
    w = rng.uniform(0.2, 2.0, size=1_000)
    blocked = h.matched_ridge_predict(x, y, x[:50], alpha=1.0, sample_weight=w, block_rows=97)
    mean = (w[:, None] * x).sum(0) / w.sum()
    scale = np.sqrt((w[:, None] * (x - mean) ** 2).sum(0) / w.sum())
    z = (x - mean) / scale
    y_mean = (w * y).sum() / w.sum()
    beta = np.linalg.solve(z.T @ (w[:, None] * z) + np.eye(3), z.T @ (w * (y - y_mean)))
    assert np.allclose(blocked, z[:50] @ beta + y_mean, rtol=1e-10, atol=1e-12)


def test_matched_ridge_unweighted_equals_v2_ridge_when_no_subsampling() -> None:
    rng = np.random.default_rng(5)
    x = rng.normal(size=(300, 4))
    y = x[:, 0] * 0.01 + rng.normal(scale=0.01, size=300)
    legacy = h._ridge_predict(x, y, x, alpha=1.0, max_rows=10_000)
    assert np.allclose(h.matched_ridge_predict(x, y, x, alpha=1.0), legacy, rtol=1e-10)


def test_score_baselines_v3_uses_fit_weights_and_names_the_approximation() -> None:
    rng = np.random.default_rng(9)
    train_x, val_x = rng.normal(size=(400, 3)), rng.normal(size=(100, 3))
    train_y = train_x[:, 0] * 0.01 + rng.normal(scale=0.01, size=400)
    val_y = val_x[:, 0] * 0.01
    weights = np.where(np.arange(400) < 100, 3.0, 1.0)
    out = h.score_baselines(
        train_x,
        train_y,
        val_x,
        val_y,
        val_y * 0.5,
        np.ones(100, dtype=bool),
        config=h.HardeningConfig(baseline_max_rows=1_000),
        train_weight=weights,
        weight_policy="SYMBOL_BALANCED_SAME_AS_GLOBAL_FIT",
    )
    assert out["baseline_contract_version"] == h.BASELINE_CONTRACT_VERSION
    assert out["ridge"]["train_rows_used"] == 400
    assert out["ridge"]["weight_policy"] == "SYMBOL_BALANCED_SAME_AS_GLOBAL_FIT"
    expected = h.matched_ridge_predict(train_x, train_y, val_x, alpha=1.0, sample_weight=weights)
    assert out["ridge"]["rmse"] == pytest.approx(float(np.sqrt(np.mean((expected - val_y) ** 2))))
    approximate = out["ridge_approximate_v2_strided_unweighted"]
    assert approximate["status"] == "APPROXIMATE_NOT_MATCHED_AUDIT_ONLY"
    weighted_mean = float((weights * train_y).sum() / weights.sum())
    assert out["train_mean"]["rmse"] == pytest.approx(
        float(np.sqrt(np.mean((val_y - weighted_mean) ** 2)))
    )
    assert out["baseline_fairness"]["independent_evidence"] is False


def test_incremental_validation_prediction_matches_full_predict(tmp_path, monkeypatch) -> None:
    from crypto_ai.phase7 import models
    from crypto_ai.phase7.training_metrics import FitMetricObserver, TrainingMetricScope

    train_x, train_y, val_x, val_y, _times = _fit_fixture()
    fitted = models._fit(
        train_x,
        train_y,
        val_x,
        val_y,
        config=ModelConfig(n_estimators=40, min_child_samples=5),
        model_threads=1,
        sample_weight=None,
    )
    booster = fitted.booster_
    observer = FitMetricObserver(TrainingMetricScope(tmp_path, {}), "global")
    for iteration in (1, 7, 7, 25, 40):
        incremental = observer._incremental_predict(booster, val_x, iteration)
        full = booster.predict(val_x, num_iteration=iteration)
        assert np.allclose(incremental, full, rtol=1e-12, atol=1e-15)
    # Going backwards (a new fit or early-stopping rewind) falls back to a full predict.
    assert np.allclose(
        observer._incremental_predict(booster, val_x, 3), booster.predict(val_x, num_iteration=3)
    )


def test_in_fit_predictions_pin_the_fit_thread_budget(tmp_path) -> None:
    """Defect OBS-03: predict() without num_threads resets OpenMP to all cores mid-fit."""

    from crypto_ai.phase7.training_metrics import FitMetricObserver, TrainingMetricScope

    calls: list[dict] = []

    class FakeBooster:
        params = {"boosting": "gbdt"}

        def predict(self, x, **kwargs):
            calls.append(kwargs)
            return np.zeros(len(x))

    observer = FitMetricObserver(TrainingMetricScope(tmp_path, {}), "global")
    observer.model_threads = 3
    x = np.zeros((4, 2))
    observer._incremental_predict(FakeBooster(), x, 5)
    observer._incremental_predict(FakeBooster(), x, 9)
    assert [call["num_threads"] for call in calls] == [3, 3]
    assert calls[1]["start_iteration"] == 5 and calls[1]["num_iteration"] == 4


@pytest.mark.parametrize("bad", [0, -1, True, 2.5])
def test_matched_ridge_rejects_malformed_block_sizes(bad) -> None:
    x, y = np.zeros((4, 1)), np.zeros(4)
    with pytest.raises(ValueError, match="block_rows"):
        h.matched_ridge_predict(x, y, x, alpha=1.0, block_rows=bad)
