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
        x[:400], y[:400], x[400:], y[400:], model[400:], np.ones(200, dtype=bool),
        config=HardeningConfig(),
    )
    assert out["delta_vs_zero"]["rmse"] < 0  # model beats zero
    assert out["lightgbm"]["spearman_ic"] > 0.9
    assert out["zero_return"]["spearman_ic"] is None
    assert "directional_accuracy_nonzero" in out["delta_vs_ridge"]
    assert out["ridge"]["spearman_ic"] is not None


def test_results_table_has_provenance_columns() -> None:
    for name in ("run_id", "configuration_hash", "code_version", "gold_dataset_id", "status",
                 "delta_rmse_vs_zero", "delta_rmse_vs_ridge"):
        assert name in RESULT_COLUMNS
    assert len(RESULT_COLUMNS) == len(set(RESULT_COLUMNS))
