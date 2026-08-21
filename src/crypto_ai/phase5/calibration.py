from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from crypto_ai.phase5.config import CalibrationConfig
from crypto_ai.research.metrics import prediction_buckets


@dataclass(frozen=True)
class Calibrator:
    method: str
    slope: float
    intercept: float
    sample_count: int
    selection_mae: float

    def apply(self, raw_predictions: np.ndarray) -> np.ndarray:
        values = np.asarray(raw_predictions, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("calibrator does not accept non-finite predictions")
        return self.intercept + self.slope * values

    @property
    def identity_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "slope": self.slope,
            "intercept": self.intercept,
            "sample_count": self.sample_count,
            "selection_mae": self.selection_mae,
        }


def _fit_candidate(method: str, raw: np.ndarray, actual: np.ndarray) -> Calibrator | None:
    if method == "identity":
        slope, intercept = 1.0, 0.0
    elif method == "linear":
        if np.ptp(raw) <= 1e-15:
            return None
        design = np.column_stack((raw, np.ones(len(raw), dtype=np.float64)))
        slope, intercept = np.linalg.lstsq(design, actual, rcond=None)[0]
    else:
        raise ValueError(f"unknown calibration method: {method}")
    calibrated = intercept + slope * raw
    if not np.all(np.isfinite(calibrated)):
        return None
    return Calibrator(
        method=method,
        slope=float(slope),
        intercept=float(intercept),
        sample_count=len(raw),
        selection_mae=float(np.mean(np.abs(calibrated - actual))),
    )


def fit_calibrator(
    raw_predictions: np.ndarray,
    actual: np.ndarray,
    config: CalibrationConfig,
) -> tuple[Calibrator, dict[str, Any]]:
    raw = np.asarray(raw_predictions, dtype=np.float64)
    target = np.asarray(actual, dtype=np.float64)
    if raw.shape != target.shape or raw.ndim != 1:
        raise ValueError("calibration predictions and actuals must be matching vectors")
    if len(raw) < config.minimum_samples:
        raise ValueError("calibration segment is below minimum_samples")
    if not np.all(np.isfinite(raw)) or not np.all(np.isfinite(target)):
        raise ValueError("calibration inputs must be finite")
    candidates = [
        candidate
        for method in config.methods
        if (candidate := _fit_candidate(method, raw, target)) is not None
    ]
    if not candidates:
        raise ValueError("no valid calibration candidate")
    selected = min(candidates, key=lambda item: (item.selection_mae, item.method))
    calibrated = selected.apply(raw)
    diagnostics = {
        "selection_source": "calibration_only",
        "candidates": [candidate.to_dict() for candidate in candidates],
        "selected": selected.to_dict(),
        "raw_prediction_distribution": _distribution(raw),
        "calibrated_prediction_distribution": _distribution(calibrated),
        "reliability_before": prediction_buckets(
            target, raw, bucket_count=config.reliability_buckets
        ),
        "reliability_after": prediction_buckets(
            target, calibrated, bucket_count=config.reliability_buckets
        ),
    }
    return selected, diagnostics


def _distribution(values: np.ndarray) -> dict[str, float | int]:
    return {
        "count": len(values),
        "mean": float(np.mean(values)),
        "std": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "minimum": float(np.min(values)),
        "p05": float(np.percentile(values, 5)),
        "median": float(np.median(values)),
        "p95": float(np.percentile(values, 95)),
        "maximum": float(np.max(values)),
    }
