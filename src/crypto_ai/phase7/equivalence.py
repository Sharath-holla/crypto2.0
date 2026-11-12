"""Operator-configured GPU equivalence assessment, independent of training science."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from crypto_ai.research.metrics import regression_metrics

METRICS = ("mae", "rmse", "r2", "directional_accuracy", "pearson_ic", "spearman_ic")
REQUIRED_LIMITS = {
    "prediction_correlation_min",
    "mean_abs_prediction_difference_max",
    "max_abs_prediction_difference_max",
    "coverage_delta_max",
    "best_iteration_delta_max",
    *(f"{key}_delta_max" for key in METRICS),
}


def assess_equivalence(
    actual,
    cpu,
    gpu,
    *,
    limits: dict[str, float] | None = None,
    cpu_best_iteration: int = 0,
    gpu_best_iteration: int = 0,
    cpu_coverage=None,
    gpu_coverage=None,
    policy_decisions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    limits = dict(limits or {})
    if limits.keys() - REQUIRED_LIMITS:
        raise ValueError("unknown equivalence tolerance")
    for key, value in limits.items():
        if not math.isfinite(value) or (not key.endswith("_min") and value < 0):
            raise ValueError("equivalence tolerances must be finite and nonnegative")
        if key.endswith("_min") and not -1 <= value <= 1:
            raise ValueError("correlation minimum must lie in [-1, 1]")
    actual, cpu, gpu = [np.asarray(value, dtype=np.float64) for value in (actual, cpu, gpu)]
    if (
        actual.ndim != 1
        or cpu.shape != actual.shape
        or gpu.shape != actual.shape
        or not len(actual)
    ):
        raise ValueError("comparison requires matching nonempty one-dimensional arrays")
    cpu_mask = (
        np.ones(len(actual), dtype=bool)
        if cpu_coverage is None
        else np.asarray(cpu_coverage, dtype=bool)
    )
    gpu_mask = (
        np.ones(len(actual), dtype=bool)
        if gpu_coverage is None
        else np.asarray(gpu_coverage, dtype=bool)
    )
    if cpu_mask.shape != actual.shape or gpu_mask.shape != actual.shape:
        raise ValueError("coverage shape mismatch")
    common = cpu_mask & gpu_mask
    if not common.any() or not all(
        np.all(np.isfinite(a[mask]))
        for a, mask in (
            (actual, np.ones(len(actual), dtype=bool)),
            (cpu, cpu_mask),
            (gpu, gpu_mask),
        )
    ):
        return {
            "status": "FAIL",
            "reason": "nonfinite covered data or no common observations",
            "operator_limits": limits,
            "training_ready": False,
        }
    cpu_metrics = regression_metrics(actual[common], cpu[common])
    gpu_metrics = regression_metrics(actual[common], gpu[common])
    difference = np.abs(cpu[common] - gpu[common])
    correlation = (
        None
        if np.ptp(cpu[common]) == 0 or np.ptp(gpu[common]) == 0
        else float(np.corrcoef(cpu[common], gpu[common])[0, 1])
    )
    evidence = {
        "prediction_correlation": correlation,
        "mean_abs_prediction_difference": float(np.mean(difference)),
        "max_abs_prediction_difference": float(np.max(difference)),
        "coverage_delta": float(abs(cpu_mask.mean() - gpu_mask.mean())),
        "best_iteration_delta": abs(cpu_best_iteration - gpu_best_iteration),
    }
    for key in METRICS:
        left, right = cpu_metrics[key], gpu_metrics[key]
        evidence[f"{key}_delta"] = None if left is None or right is None else abs(left - right)
    decisions = {}
    for key, bound in limits.items():
        lower = key.endswith("_min")
        observed = evidence[key[:-4]]
        decisions[key] = (
            "UNVERIFIABLE"
            if observed is None or not math.isfinite(observed)
            else "PASS"
            if (observed >= bound if lower else observed <= bound)
            else "FAIL"
        )
    status = (
        "FAIL"
        if "FAIL" in decisions.values()
        else "REVIEW_REQUIRED"
        if limits.keys() != REQUIRED_LIMITS or "UNVERIFIABLE" in decisions.values()
        else "PASS"
    )
    return {
        "status": status,
        "scope": "PREDICTION_EQUIVALENCE_ONLY",
        "training_ready": False,
        "operator_limits": limits,
        "missing_limits": sorted(REQUIRED_LIMITS - limits.keys()),
        "decisions": decisions,
        **evidence,
        "cpu_metrics": cpu_metrics,
        "gpu_metrics": gpu_metrics,
        "cpu_best_iteration": cpu_best_iteration,
        "gpu_best_iteration": gpu_best_iteration,
        "cpu_coverage": float(cpu_mask.mean()),
        "gpu_coverage": float(gpu_mask.mean()),
        "threshold_no_trade_decisions": policy_decisions
        or {"status": "NOT_EVALUATED_SYNTHETIC_SMOKE"},
        "production_policy_equivalence": "REVIEW_REQUIRED",
    }
