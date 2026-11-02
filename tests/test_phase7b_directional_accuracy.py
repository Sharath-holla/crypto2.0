"""Added by Claude (2026-11-02, finding L-01): zero actuals do not count as direction misses."""

from __future__ import annotations

import numpy as np
import pytest

from crypto_ai.phase7.training_metrics import display_metrics
from crypto_ai.research.metrics import directional_accuracy, regression_metrics

ACTUAL = np.array([0.0, 0.0, 0.01, -0.02, 0.03, -0.01])
PREDICTED = np.array([0.1, -0.1, 0.02, -0.01, -0.02, -0.03])


def test_zero_actuals_leave_the_denominator() -> None:
    assert directional_accuracy(ACTUAL, PREDICTED) == pytest.approx(3 / 4)


def test_regression_metrics_reports_zero_count_separately() -> None:
    metrics = regression_metrics(ACTUAL, PREDICTED)
    assert metrics["directional_accuracy"] == pytest.approx(3 / 4)
    assert metrics["n_zero_actuals"] == 2


def test_live_display_metric_uses_the_same_definition() -> None:
    shown = {name: value for name, value, _flag in display_metrics(ACTUAL, PREDICTED)}
    assert shown["directional_accuracy"] == pytest.approx(3 / 4)


def test_all_zero_actuals_do_not_crash() -> None:
    zeros = np.zeros(4)
    assert directional_accuracy(zeros, np.ones(4)) == 0.0
    assert regression_metrics(zeros, np.ones(4))["n_zero_actuals"] == 4
