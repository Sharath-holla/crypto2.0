"""CHANGED BY CLAUDE (2026-11-06, final hardening): zero-actual metrics + baseline deltas."""

from __future__ import annotations

import numpy as np

from crypto_ai.phase7.hardening import RESULT_COLUMNS, HardeningConfig, score_baselines
from crypto_ai.research.metrics import regression_metrics


def test_zero_actual_fields_are_explicit() -> None:
    actual = np.array([0.0, 0.0, 0.01, -0.02])
    predicted = np.array([0.01, -0.01, 0.02, -0.01])
    out = regression_metrics(actual, predicted)
    assert out["zero_actual_count"] == 2
    assert out["zero_actual_fraction"] == 0.5
    assert out["directional_accuracy_nonzero"] == 1.0  # only the two non-zero actuals count
    assert out["directional_accuracy"] == out["directional_accuracy_nonzero"]


def test_all_zero_actuals_do_not_divide_by_zero() -> None:
    out = regression_metrics(np.zeros(4), np.array([0.1, -0.1, 0.0, 0.2]))
    assert out["zero_actual_fraction"] == 1.0
    assert out["directional_accuracy_nonzero"] == 0.0


def test_baselines_report_deltas_and_extra_metrics() -> None:
    rng = np.random.default_rng(7)
    x = rng.normal(size=(600, 4))
    y = x[:, 0] * 2e-3 + rng.normal(scale=1e-4, size=600)
    model = y + rng.normal(scale=5e-5, size=600)  # a good "model"
    out = score_baselines(
        x[:400],
        y[:400],
        x[400:],
        y[400:],
        model[400:],
        np.ones(200, dtype=bool),
        config=HardeningConfig(),
    )
    assert out["delta_vs_zero"]["rmse"] < 0  # model beats zero
    assert out["lightgbm"]["spearman_ic"] > 0.9
    assert out["zero_return"]["spearman_ic"] is None
    assert "directional_accuracy_nonzero" in out["delta_vs_ridge"]
    assert out["ridge"]["spearman_ic"] is not None


def test_results_table_has_provenance_columns() -> None:
    for name in (
        "run_id",
        "configuration_hash",
        "code_version",
        "gold_dataset_id",
        "status",
        "delta_rmse_vs_zero",
        "delta_rmse_vs_ridge",
    ):
        assert name in RESULT_COLUMNS
    assert len(RESULT_COLUMNS) == len(set(RESULT_COLUMNS))


# --- CHANGED BY CLAUDE (2026-11-06, closure): cross-sectional IC + TRAIN-mean baseline ---
def test_cross_sectional_ic_ranks_within_each_timestamp_only() -> None:
    from crypto_ai.phase7.hardening import cross_sectional_ic

    # Level differs a lot between timestamps, but within each one the order is perfect.
    times = np.repeat([1, 2, 3], 6)
    base = np.repeat([100.0, 0.0, -50.0], 6)
    ranks = np.tile(np.arange(6, dtype=float), 3)
    out = cross_sectional_ic(times, base + ranks, ranks * 0.01)
    assert out["timestamps_scored"] == 3 and abs(out["mean_xs_spearman_ic"] - 1.0) < 1e-12
    inverted = cross_sectional_ic(times, base - ranks, ranks * 0.01)
    assert abs(inverted["mean_xs_spearman_ic"] + 1.0) < 1e-12


def test_cross_sectional_ic_skips_thin_and_constant_timestamps() -> None:
    from crypto_ai.phase7.hardening import cross_sectional_ic

    times = np.array([1, 1, 1, 2, 2, 2, 2, 2, 2])
    pred = np.array([1.0, 2.0, 3.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    actual = np.arange(9, dtype=float)
    out = cross_sectional_ic(times, pred, actual)
    assert out["timestamps_scored"] == 0 and out["timestamps_skipped"] == 2
    assert out["mean_xs_spearman_ic"] is None


def test_score_baselines_reports_train_mean_and_xs_ic_on_the_same_rows() -> None:
    rng = np.random.default_rng(1)
    n, symbols = 60, 6
    train_x = rng.normal(size=(200, 3))
    train_y = rng.normal(size=200) * 0.01 + 0.001
    val_x = rng.normal(size=(n * symbols, 3))
    val_y = rng.normal(size=n * symbols) * 0.01
    times = np.repeat(np.arange(n), symbols)
    covered = np.ones(n * symbols, dtype=bool)
    covered[::7] = False
    out = score_baselines(
        train_x, train_y, val_x, val_y, val_y.copy(), covered, validation_times=times
    )
    # CHANGED BY CLAUDE (2026-11-08): v3 = matched full-TRAIN fit-weighted Ridge.
    assert out["baseline_contract_version"].startswith("baseline_contract_v3")
    assert out["validation_rows_scored"] == int(covered.sum())
    assert out["train_mean"]["rmse"] > 0
    assert out["lightgbm"]["cross_sectional_ic"]["mean_xs_spearman_ic"] > 0.99
    assert "cross_sectional_ic" in out["ridge"]
    no_times = score_baselines(train_x, train_y, val_x, val_y, val_y.copy(), covered)
    assert no_times["lightgbm"]["cross_sectional_ic"]["status"] == "NOT_COMPUTED_NO_TIMESTAMPS"
