from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np

from crypto_ai.phase5.config import CalibrationConfig
from crypto_ai.research.metrics import prediction_buckets

# CHANGED BY CLAUDE (2026-11-02, finding L-03): the method (identity vs linear) is now chosen on
# a deterministic held-out tail of the Cal-A rows, then the chosen method is refit on all of
# Cal-A. The fraction is a module constant rather than a config key because new keys would
# change the frozen Phase 7 config hash (93f987736b1a79d26b773957) and invalidate caches.
SELECTION_HOLDOUT_FRACTION = 0.25
# Rows are in feature-time order, so the held-out part is the LAST quarter (never shuffled).


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
    *,
    selection_holdout_fraction: float = 0.0,
) -> tuple[Calibrator, dict[str, Any]]:
    # CHANGED BY CLAUDE (2026-11-02, finding L-03): ``selection_holdout_fraction`` is opt-in
    # (default 0.0 = the original in-sample behaviour) so historical Phase 5 results reproduce
    # unchanged; Phase 7 training passes SELECTION_HOLDOUT_FRACTION.
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
    # OLD CODE (kept for reference): choose by in-sample MAE on the same Cal-A rows.
    # selected = min(candidates, key=lambda item: (item.selection_mae, item.method))
    selection_source = "calibration_only"
    holdout_count = int(len(raw) * selection_holdout_fraction)
    fit_count = len(raw) - holdout_count
    holdout_mae: dict[str, float] = {}
    if holdout_count >= 2 and fit_count >= max(2, config.minimum_samples // 2):
        for method in (candidate.method for candidate in candidates):
            trial = _fit_candidate(method, raw[:fit_count], target[:fit_count])
            if trial is not None:
                holdout_mae[method] = float(
                    np.mean(np.abs(trial.apply(raw[fit_count:]) - target[fit_count:]))
                )
    if holdout_mae:
        chosen = min(holdout_mae, key=lambda method: (holdout_mae[method], method))
        selected = next(item for item in candidates if item.method == chosen)
        selection_source = "calibration_a_heldout_tail"
    else:
        selected = min(candidates, key=lambda item: (item.selection_mae, item.method))
    calibrated = selected.apply(raw)
    diagnostics = {
        # OLD CODE (kept for reference): "selection_source": "calibration_only",
        "selection_source": selection_source,
        "heldout_fraction": selection_holdout_fraction if holdout_mae else 0.0,
        "heldout_mae": holdout_mae,
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
