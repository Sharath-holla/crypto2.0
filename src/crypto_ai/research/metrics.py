from __future__ import annotations

from typing import Any

import numpy as np


def _finite_pair(actual: np.ndarray, predicted: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    actual = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)
    if actual.shape != predicted.shape:
        raise ValueError("actual and predicted must have identical shapes")
    if actual.ndim != 1 or not len(actual):
        raise ValueError("metrics require non-empty one-dimensional arrays")
    if not np.all(np.isfinite(actual)) or not np.all(np.isfinite(predicted)):
        raise ValueError("metrics do not accept NaN or infinite values")
    return actual, predicted


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    sorted_values = values[order]
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and sorted_values[end] == sorted_values[start]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _correlation(left: np.ndarray, right: np.ndarray) -> float | None:
    if len(left) < 2 or np.ptp(left) == 0.0 or np.ptp(right) == 0.0:
        return None
    value = float(np.corrcoef(left, right)[0, 1])
    return value if np.isfinite(value) else None


def regression_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    actual, predicted = _finite_pair(actual, predicted)
    residual = predicted - actual
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(np.square(residual))))
    denominator = float(np.sum(np.square(actual - np.mean(actual))))
    r2 = None if denominator == 0.0 else float(1.0 - np.sum(np.square(residual)) / denominator)
    pearson = _correlation(actual, predicted)
    spearman = _correlation(_average_ranks(actual), _average_ranks(predicted))
    return {
        "count": int(len(actual)),
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "directional_accuracy": float(np.mean(np.sign(actual) == np.sign(predicted))),
        "pearson_ic": pearson,
        "spearman_ic": spearman,
        "prediction_mean": float(np.mean(predicted)),
        "prediction_std": float(np.std(predicted, ddof=1)) if len(predicted) > 1 else 0.0,
        "actual_mean": float(np.mean(actual)),
        "actual_std": float(np.std(actual, ddof=1)) if len(actual) > 1 else 0.0,
    }


def prediction_buckets(
    actual: np.ndarray,
    predicted: np.ndarray,
    *,
    bucket_count: int = 10,
) -> list[dict[str, Any]]:
    actual, predicted = _finite_pair(actual, predicted)
    if bucket_count < 1:
        raise ValueError("bucket_count must be positive")
    ordered = np.argsort(predicted, kind="mergesort")
    groups = np.array_split(ordered, min(bucket_count, len(ordered)))
    result: list[dict[str, Any]] = []
    for number, indices in enumerate(groups, start=1):
        group_actual = actual[indices]
        group_predicted = predicted[indices]
        result.append(
            {
                "bucket": number,
                "count": int(len(indices)),
                "mean_predicted_return": float(np.mean(group_predicted)),
                "mean_realized_return": float(np.mean(group_actual)),
                "directional_hit_rate": float(
                    np.mean(np.sign(group_actual) == np.sign(group_predicted))
                ),
                "minimum_prediction": float(np.min(group_predicted)),
                "maximum_prediction": float(np.max(group_predicted)),
            }
        )
    return result


def distribution_summary(values: np.ndarray, *, near_zero_threshold: float) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("distribution requires a non-empty finite one-dimensional array")
    percentiles = np.percentile(values, [1, 5, 25, 50, 75, 95, 99])
    return {
        "count": int(len(values)),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "min": float(np.min(values)),
        "max": float(np.max(values)),
        "percentiles": {
            "p01": float(percentiles[0]),
            "p05": float(percentiles[1]),
            "p25": float(percentiles[2]),
            "p50": float(percentiles[3]),
            "p75": float(percentiles[4]),
            "p95": float(percentiles[5]),
            "p99": float(percentiles[6]),
        },
        "positive_percentage": float(np.mean(values > near_zero_threshold) * 100.0),
        "negative_percentage": float(np.mean(values < -near_zero_threshold) * 100.0),
        "near_zero_percentage": float(np.mean(np.abs(values) <= near_zero_threshold) * 100.0),
        "near_zero_threshold": near_zero_threshold,
    }


def feature_distribution(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("feature values must be one-dimensional")
    missing = np.isnan(values)
    infinite = np.isinf(values)
    finite = values[np.isfinite(values)]
    payload: dict[str, Any] = {
        "count": int(len(values)),
        "missing_count": int(np.count_nonzero(missing)),
        "missing_percentage": float(np.mean(missing) * 100.0) if len(values) else 0.0,
        "infinite_count": int(np.count_nonzero(infinite)),
    }
    if not len(finite):
        return payload | {"constant": False, "near_constant": False}
    percentiles = np.percentile(finite, [1, 5, 25, 50, 75, 95, 99])
    mean = float(np.mean(finite))
    standard_deviation = float(np.std(finite, ddof=1)) if len(finite) > 1 else 0.0
    constant = bool(np.ptp(finite) <= 1e-15)
    near_constant = bool(not constant and standard_deviation <= max(1e-12, abs(mean) * 1e-8))
    return payload | {
        "mean": mean,
        "std": standard_deviation,
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "percentiles": {
            "p01": float(percentiles[0]),
            "p05": float(percentiles[1]),
            "p25": float(percentiles[2]),
            "p50": float(percentiles[3]),
            "p75": float(percentiles[4]),
            "p95": float(percentiles[5]),
            "p99": float(percentiles[6]),
        },
        "constant": constant,
        "near_constant": near_constant,
    }
