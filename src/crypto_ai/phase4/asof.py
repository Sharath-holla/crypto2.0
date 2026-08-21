from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class AsOfResult:
    values: dict[str, np.ndarray]
    available: np.ndarray
    age_us: np.ndarray
    source_indices: np.ndarray


def causal_asof_join(
    feature_time_us: np.ndarray,
    availability_time_us: np.ndarray,
    source_values: dict[str, np.ndarray],
    *,
    maximum_age_us: int,
) -> AsOfResult:
    """Align the latest already-available observation without looking ahead."""

    feature_time_us = np.asarray(feature_time_us, dtype=np.int64)
    availability_time_us = np.asarray(availability_time_us, dtype=np.int64)
    if feature_time_us.ndim != 1 or availability_time_us.ndim != 1:
        raise ValueError("as-of timestamps must be one-dimensional")
    if maximum_age_us < 0:
        raise ValueError("maximum_age_us must be non-negative")
    if len(availability_time_us) and np.any(np.diff(availability_time_us) <= 0):
        raise ValueError("source availability times must be unique and increasing")
    for name, values in source_values.items():
        if np.asarray(values).shape != availability_time_us.shape:
            raise ValueError(f"source field {name} does not match source timestamps")

    indices = np.searchsorted(availability_time_us, feature_time_us, side="right") - 1
    has_prior = indices >= 0
    safe = np.maximum(indices, 0)
    age = np.full(len(feature_time_us), -1, dtype=np.int64)
    if len(availability_time_us):
        age[has_prior] = feature_time_us[has_prior] - availability_time_us[safe[has_prior]]
    available = has_prior & (age >= 0) & (age <= maximum_age_us)
    aligned: dict[str, np.ndarray] = {}
    for name, raw in source_values.items():
        values = np.asarray(raw, dtype=np.float64)
        result = np.full(len(feature_time_us), np.nan, dtype=np.float64)
        if len(values):
            result[available] = values[safe[available]]
        aligned[name] = result
    return AsOfResult(values=aligned, available=available, age_us=age, source_indices=indices)
