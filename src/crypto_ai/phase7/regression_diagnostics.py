"""Regression diagnostics for live / post-fit monitoring (descriptive, Validation only).

Added by Claude (2026-11-08, pre-RunPod architecture hardening). Standard library + NumPy only.

All functions are pure: they read arrays and return plain numbers. A statistic that cannot be
computed (constant input, fewer than two rows, no non-zero actuals) is returned as ``None`` with a
reason, never as a fake 0.0. Metrics here are class ``DEVELOPMENT_METRIC`` or
``DESCRIPTIVE_VALIDATION_DIAGNOSTIC``: none of them selects a model, stops a fit, or is evidence.
"""

from __future__ import annotations

from typing import Any

import numpy as np

QUANTILES = (0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99)
CROSS_SECTION_MIN_SYMBOLS = 5  # same floor as hardening.XS_IC_MIN_SYMBOLS
NOT_DEFINED_XS = "NOT_DEFINED"
_SNAPSHOT_KEYS = (
    "rmse",
    "mae",
    "pearson",
    "spearman",
    "directional_accuracy",
    "prediction_mean",
    "prediction_std",
    "prediction_min",
    "prediction_max",
    "prediction_near_zero_fraction",
    "actual_std",
    "prediction_actual_std_ratio",
)


def average_ranks(values: np.ndarray) -> np.ndarray:
    """1-based average ranks (ties share the mean rank), vectorised, O(n log n)."""

    data = np.asarray(values, dtype=np.float64)
    count = len(data)
    if count == 0:
        return np.empty(0, dtype=np.float64)
    order = np.argsort(data, kind="mergesort")
    ordered = data[order]
    starts_mask = np.empty(count, dtype=bool)
    starts_mask[0] = True
    starts_mask[1:] = ordered[1:] != ordered[:-1]
    run_id = np.cumsum(starts_mask) - 1
    starts = np.flatnonzero(starts_mask)
    ends = np.append(starts[1:], count)
    mean_rank = (starts + ends - 1) / 2.0 + 1.0
    ranks = np.empty(count, dtype=np.float64)
    ranks[order] = mean_rank[run_id]
    return ranks


def pearson(left: np.ndarray, right: np.ndarray) -> float | None:
    """Pearson correlation, or None when it is mathematically undefined."""

    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("correlation inputs must be aligned one-dimensional arrays")
    if len(a) < 2 or np.ptp(a) == 0.0 or np.ptp(b) == 0.0:
        return None  # exactly constant input: floating-point centring would invent variance
    a = a - a.mean()
    b = b - b.mean()
    denominator = float(np.sqrt(np.dot(a, a) * np.dot(b, b)))
    if not np.isfinite(denominator) or denominator == 0.0:
        return None
    value = float(np.dot(a, b)) / denominator
    return float(min(1.0, max(-1.0, value))) if np.isfinite(value) else None


def spearman(left: np.ndarray, right: np.ndarray) -> float | None:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("correlation inputs must be aligned one-dimensional arrays")
    return pearson(average_ranks(a), average_ranks(b))


def directional_accuracy_nonzero(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Share of non-zero actuals whose predicted sign matches; None when every actual is zero.

    Same denominator policy as ``research.metrics.directional_accuracy`` (finding L-01: a zero
    actual has no direction), but "no non-zero actual" is reported as None instead of 0.0.
    A zero prediction against a non-zero actual counts as a miss.
    """

    a = np.asarray(actual, dtype=np.float64)
    p = np.asarray(predicted, dtype=np.float64)
    moving = a != 0.0
    if not np.any(moving):
        return None
    return float(np.mean(np.sign(a[moving]) == np.sign(p[moving])))


def regression_snapshot(
    actual: np.ndarray, predicted: np.ndarray, *, near_zero_abs: float = 1e-12
) -> dict[str, Any]:
    """RMSE / MAE / Pearson / Spearman / direction + prediction distribution, in the units given.

    Rows where either value is not finite are excluded and counted. The prediction distribution is
    taken over rows whose PREDICTION is finite (``finite_prediction_fraction`` is reported over all
    rows so non-finite predictions are visible even though they are excluded from the scores).
    """

    a = np.asarray(actual, dtype=np.float64)
    p = np.asarray(predicted, dtype=np.float64)
    if a.ndim != 1 or a.shape != p.shape:
        raise ValueError("actual and predicted must be aligned one-dimensional arrays")
    total = int(len(a))
    finite_prediction = np.isfinite(p)
    both = finite_prediction & np.isfinite(a)
    valid = int(np.count_nonzero(both))
    out: dict[str, Any] = {
        "rows_total": total,
        "rows_valid": valid,
        "rows_excluded_non_finite": total - valid,
        "finite_prediction_fraction": (
            float(np.count_nonzero(finite_prediction)) / total if total else None
        ),
    }
    out.update(dict.fromkeys(_SNAPSHOT_KEYS))
    out.update({f"prediction_q{int(q * 100):02d}": None for q in QUANTILES})
    out["n_zero_actuals"] = int(np.count_nonzero(a[both] == 0.0)) if valid else 0
    finite_predictions = p[finite_prediction]
    if len(finite_predictions):
        out["prediction_mean"] = float(finite_predictions.mean())
        out["prediction_std"] = (
            0.0 if np.ptp(finite_predictions) == 0.0 else float(finite_predictions.std())
        )
        out["prediction_min"] = float(finite_predictions.min())
        out["prediction_max"] = float(finite_predictions.max())
        out["prediction_near_zero_fraction"] = float(
            np.mean(np.abs(finite_predictions) <= near_zero_abs)
        )
        for q, value in zip(QUANTILES, np.quantile(finite_predictions, QUANTILES), strict=True):
            out[f"prediction_q{int(q * 100):02d}"] = float(value)
    if not valid:
        return out
    a, p = a[both], p[both]
    residual = p - a
    out["rmse"] = float(np.sqrt(np.mean(residual * residual)))
    out["mae"] = float(np.mean(np.abs(residual)))
    out["pearson"] = pearson(a, p)
    out["spearman"] = spearman(a, p)
    out["directional_accuracy"] = directional_accuracy_nonzero(a, p)
    actual_std = 0.0 if np.ptp(a) == 0.0 else float(a.std())
    out["actual_std"] = actual_std
    out["prediction_actual_std_ratio"] = (
        (0.0 if np.ptp(p) == 0.0 else float(p.std())) / actual_std if actual_std > 0.0 else None
    )
    return out


def cross_sectional_spearman(
    times: np.ndarray,
    predicted: np.ndarray,
    actual: np.ndarray,
    *,
    min_symbols: int = CROSS_SECTION_MIN_SYMBOLS,
) -> dict[str, Any]:
    """Mean per-timestamp Spearman IC, vectorised.

    Only rows that share a timestamp are ranked together, so level or trend cannot contribute.
    Timestamps with fewer than ``min_symbols`` rows, or a constant side, are skipped and counted.
    The result is ``None`` (reason ``INSUFFICIENT_CROSS_SECTION``) when no timestamp qualifies,
    for example in a 3-coin smoke where ``min_symbols`` is 5.
    """

    t = np.asarray(times).astype(np.int64)
    p = np.asarray(predicted, dtype=np.float64)
    a = np.asarray(actual, dtype=np.float64)
    if not (t.ndim == 1 and t.shape == p.shape == a.shape):
        raise ValueError("cross-sectional IC inputs must be aligned one-dimensional arrays")
    keep = np.isfinite(p) & np.isfinite(a)
    t, p, a = t[keep], p[keep], a[keep]
    result: dict[str, Any] = {
        "xs_spearman_ic_mean": None,
        "xs_spearman_ic_std": None,
        "xs_timestamps_scored": 0,
        "xs_timestamps_skipped_small": 0,
        "xs_timestamps_skipped_constant": 0,
        "xs_min_symbols": int(min_symbols),
        "xs_status": NOT_DEFINED_XS,
        "xs_reason": "INSUFFICIENT_CROSS_SECTION",
    }
    if len(t) == 0:
        return result
    order = np.argsort(t, kind="mergesort")
    t, p, a = t[order], p[order], a[order]
    starts_mask = np.empty(len(t), dtype=bool)
    starts_mask[0] = True
    starts_mask[1:] = t[1:] != t[:-1]
    starts = np.flatnonzero(starts_mask)
    sizes = np.diff(np.append(starts, len(t)))
    big = sizes >= int(min_symbols)
    result["xs_timestamps_skipped_small"] = int(np.count_nonzero(~big))
    if not np.any(big):
        return result
    group = np.repeat(np.arange(len(starts)), sizes)
    rows = big[group]
    group = group[rows]
    p, a = p[rows], a[rows]
    kept_ids, group = np.unique(group, return_inverse=True)
    sizes = sizes[kept_ids]
    offsets = np.append(0, np.cumsum(sizes))[:-1]
    rank_p = _grouped_average_ranks(group, p)
    rank_a = _grouped_average_ranks(group, a)
    centre = np.repeat((sizes + 1) / 2.0, sizes)  # average ranks always sum to n(n+1)/2
    cp, ca = rank_p - centre, rank_a - centre
    cov = np.add.reduceat(cp * ca, offsets)
    var_p = np.add.reduceat(cp * cp, offsets)
    var_a = np.add.reduceat(ca * ca, offsets)
    defined = (var_p > 0.0) & (var_a > 0.0)
    result["xs_timestamps_skipped_constant"] = int(np.count_nonzero(~defined))
    if not np.any(defined):
        return result
    ic = cov[defined] / np.sqrt(var_p[defined] * var_a[defined])
    result.update(
        xs_spearman_ic_mean=float(ic.mean()),
        xs_spearman_ic_std=float(ic.std(ddof=1)) if len(ic) > 1 else None,
        xs_timestamps_scored=int(len(ic)),
        xs_status="DEFINED",
        xs_reason=None,
    )
    return result


def _grouped_average_ranks(group: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Average ranks of ``values`` inside each (non-decreasing) ``group`` id, 1-based."""

    order = np.lexsort((values, group))
    g, v = group[order], values[order]
    count = len(v)
    new_run = np.empty(count, dtype=bool)
    new_run[0] = True
    new_run[1:] = (g[1:] != g[:-1]) | (v[1:] != v[:-1])
    run_id = np.cumsum(new_run) - 1
    starts = np.flatnonzero(new_run)
    ends = np.append(starts[1:], count)
    group_start = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
    group_start_of_row = group_start[np.cumsum(np.r_[True, g[1:] != g[:-1]]) - 1]
    first_in_group = group_start_of_row[starts]
    mean_rank = ((starts - first_in_group) + (ends - 1 - first_in_group)) / 2.0 + 1.0
    ranks = np.empty(count, dtype=np.float64)
    ranks[order] = mean_rank[run_id]
    return ranks
