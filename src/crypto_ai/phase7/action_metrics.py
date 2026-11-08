"""ACTION / EVENT diagnostics for a REGRESSION forecaster (descriptive, Validation only).

Added by Claude (2026-11-08, pre-RunPod architecture hardening). Standard library + NumPy only,
so it imports and tests without LightGBM or PyArrow.

The model predicts a continuous forward return. Precision and recall are therefore SECONDARY,
explicitly defined diagnostics. They are never an optimisation target, never a selection metric,
never independent evidence and never a profitability statement. Early stopping stays on the
continuous L2 regression metric. Class: ``DESCRIPTIVE_VALIDATION_DIAGNOSTIC``.

DEFINITIONS - every comparison is in RAW decimal returns (0.0005 == 5 bps), inclusive at the
threshold, and thresholds must be finite and strictly positive so that a zero return is never an
event or an action and LONG / SHORT can never overlap:

  LONG event   actual_raw    >= +event_threshold
  SHORT event  actual_raw    <= -event_threshold
  LONG action  predicted_raw >= +prediction_threshold
  SHORT action predicted_raw <= -prediction_threshold
  NO_TRADE     every other row

  LONG  TP = predicted LONG  and LONG event      precision = TP / predicted LONG
        FP = predicted LONG  and not LONG event  recall    = TP / LONG events
        FN = not predicted LONG and LONG event   F1        = 2TP / (2TP + FP + FN)
  SHORT is the mirror image. A SHORT event in a predicted-LONG row is a LONG false positive.

A ratio whose denominator is zero is NOT_DEFINED (value ``None``), never 0.0. Support counts are
always reported next to every ratio. Rows where either value is not finite are excluded and counted.

UNITS: if the model target is volatility-normalised, predictions MUST be converted to raw returns
with the SAME divisor the forward transform used, ``max(|scale|, floor)`` (see
``targets.effective_normalization_scale``), before they reach :func:`action_diagnostics`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

ACTION_DIAGNOSTIC_VERSION = "action_diagnostics_v1_raw_decimal_inclusive_thresholds"
METRIC_CLASS = "DESCRIPTIVE_VALIDATION_DIAGNOSTIC"
RAW_UNITS = "RAW_RETURN_DECIMAL"
DEFINED = "DEFINED"
NOT_DEFINED = "NOT_DEFINED"
BPS_PER_UNIT = 10_000.0


@dataclass(frozen=True)
class ActionThresholds:
    """Predeclared diagnostic thresholds in basis points (fixed before Validation is seen)."""

    event_threshold_bps: float
    prediction_threshold_bps: float

    def __post_init__(self) -> None:
        for name in ("event_threshold_bps", "prediction_threshold_bps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{name} must be a number of basis points")
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and strictly positive (got {value!r})")
            if float(value) / BPS_PER_UNIT <= 0:
                raise ValueError(f"{name} must remain strictly positive in raw-return units")

    @property
    def event_threshold(self) -> float:
        return float(self.event_threshold_bps) / BPS_PER_UNIT

    @property
    def prediction_threshold(self) -> float:
        return float(self.prediction_threshold_bps) / BPS_PER_UNIT


def _ratio(numerator: int, denominator: int) -> tuple[float | None, str]:
    if denominator <= 0:
        return None, NOT_DEFINED
    return numerator / denominator, DEFINED


@dataclass(frozen=True)
class SideScores:
    side: str
    true_positives: int
    false_positives: int
    false_negatives: int
    predicted_count: int  # precision denominator (predicted actions on this side)
    event_count: int  # recall denominator and "support" (actual events on this side)
    precision: float | None
    recall: float | None
    f1: float | None
    precision_status: str
    recall_status: str
    f1_status: str
    precision_reason: str | None
    recall_reason: str | None
    f1_reason: str | None


def _side_scores(side: str, predicted: np.ndarray, event: np.ndarray) -> SideScores:
    tp = int(np.count_nonzero(predicted & event))
    predicted_count = int(np.count_nonzero(predicted))
    event_count = int(np.count_nonzero(event))
    fp = predicted_count - tp
    fn = event_count - tp
    precision, precision_status = _ratio(tp, predicted_count)
    recall, recall_status = _ratio(tp, event_count)
    if precision is not None and recall is not None:
        # Both defined => 2TP + FP + FN > 0, so this is the harmonic mean and may legitimately be 0.
        f1: float | None = (2 * tp) / (2 * tp + fp + fn)
        f1_status, f1_reason = DEFINED, None
    else:
        f1, f1_status = None, NOT_DEFINED
        f1_reason = "PRECISION_OR_RECALL_NOT_DEFINED"
    return SideScores(
        side=side,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        predicted_count=predicted_count,
        event_count=event_count,
        precision=precision,
        recall=recall,
        f1=f1,
        precision_status=precision_status,
        recall_status=recall_status,
        f1_status=f1_status,
        precision_reason=None if precision is not None else f"NO_PREDICTED_{side}_ACTIONS",
        recall_reason=None if recall is not None else f"NO_ACTUAL_{side}_EVENTS",
        f1_reason=f1_reason,
    )


@dataclass(frozen=True)
class ActionDiagnostics:
    thresholds: ActionThresholds
    rows_total: int
    rows_valid: int
    rows_excluded_non_finite: int
    long: SideScores
    short: SideScores
    no_trade_count: int
    action_coverage: float | None
    long_coverage: float | None
    short_coverage: float | None
    no_trade_coverage: float | None
    action_hit_rate: float | None
    action_hit_rate_status: str
    actions_scored: int
    actions_zero_actual_excluded: int
    macro_f1: float | None
    macro_f1_status: str
    version: str = ACTION_DIAGNOSTIC_VERSION
    metric_class: str = METRIC_CLASS
    units: str = RAW_UNITS

    def to_flat_dict(self) -> dict[str, Any]:
        """Flat, JSON-safe mapping (None == NOT_DEFINED) used by telemetry and reports."""

        out: dict[str, Any] = {
            "action_diagnostic_version": self.version,
            "metric_class": self.metric_class,
            "action_units": self.units,
            "event_threshold_bps": float(self.thresholds.event_threshold_bps),
            "prediction_threshold_bps": float(self.thresholds.prediction_threshold_bps),
            "action_rows_total": self.rows_total,
            "action_rows_valid": self.rows_valid,
            "action_rows_excluded_non_finite": self.rows_excluded_non_finite,
            "no_trade_count": self.no_trade_count,
            "action_coverage": self.action_coverage,
            "long_coverage": self.long_coverage,
            "short_coverage": self.short_coverage,
            "no_trade_coverage": self.no_trade_coverage,
            "action_hit_rate": self.action_hit_rate,
            "action_hit_rate_status": self.action_hit_rate_status,
            "action_hit_rate_scored": self.actions_scored,
            "action_hit_rate_zero_actual_excluded": self.actions_zero_actual_excluded,
            "macro_f1": self.macro_f1,
            "macro_f1_status": self.macro_f1_status,
        }
        for scores in (self.long, self.short):
            prefix = scores.side.lower()
            out.update(
                {
                    f"{prefix}_precision": scores.precision,
                    f"{prefix}_recall": scores.recall,
                    f"{prefix}_f1": scores.f1,
                    f"{prefix}_precision_status": scores.precision_status,
                    f"{prefix}_recall_status": scores.recall_status,
                    f"{prefix}_f1_status": scores.f1_status,
                    f"{prefix}_precision_reason": scores.precision_reason,
                    f"{prefix}_recall_reason": scores.recall_reason,
                    # "support" is the number of actual events (the recall denominator).
                    f"{prefix}_support": scores.event_count,
                    f"{prefix}_predicted_count": scores.predicted_count,
                    f"{prefix}_true_positives": scores.true_positives,
                    f"{prefix}_false_positives": scores.false_positives,
                    f"{prefix}_false_negatives": scores.false_negatives,
                }
            )
        return out


def action_diagnostics(
    actual_raw: np.ndarray, predicted_raw: np.ndarray, thresholds: ActionThresholds
) -> ActionDiagnostics:
    """LONG / SHORT / NO_TRADE event diagnostics for RAW decimal returns (see module docstring)."""

    actual = np.asarray(actual_raw, dtype=np.float64)
    predicted = np.asarray(predicted_raw, dtype=np.float64)
    if actual.ndim != 1 or actual.shape != predicted.shape:
        raise ValueError("actual and predicted must be aligned one-dimensional arrays")
    total = int(len(actual))
    finite = np.isfinite(actual) & np.isfinite(predicted)
    valid = int(np.count_nonzero(finite))
    if valid != total:
        actual, predicted = actual[finite], predicted[finite]
    event, trigger = thresholds.event_threshold, thresholds.prediction_threshold
    actual_long, actual_short = actual >= event, actual <= -event
    predicted_long, predicted_short = predicted >= trigger, predicted <= -trigger
    long_scores = _side_scores("LONG", predicted_long, actual_long)
    short_scores = _side_scores("SHORT", predicted_short, actual_short)
    n_long, n_short = long_scores.predicted_count, short_scores.predicted_count
    no_trade = valid - n_long - n_short
    acted = predicted_long | predicted_short
    moving = actual != 0.0
    scored = int(np.count_nonzero(acted & moving))
    hits = int(
        np.count_nonzero(predicted_long & (actual > 0.0))
        + np.count_nonzero(predicted_short & (actual < 0.0))
    )
    hit_rate, hit_status = _ratio(hits, scored)
    if long_scores.f1 is not None and short_scores.f1 is not None:
        macro, macro_status = (long_scores.f1 + short_scores.f1) / 2.0, DEFINED
    else:
        macro, macro_status = None, NOT_DEFINED

    def coverage(count: int) -> float | None:
        return count / valid if valid else None

    return ActionDiagnostics(
        thresholds=thresholds,
        rows_total=total,
        rows_valid=valid,
        rows_excluded_non_finite=total - valid,
        long=long_scores,
        short=short_scores,
        no_trade_count=no_trade,
        action_coverage=coverage(n_long + n_short),
        long_coverage=coverage(n_long),
        short_coverage=coverage(n_short),
        no_trade_coverage=coverage(no_trade),
        action_hit_rate=hit_rate,
        action_hit_rate_status=hit_status,
        actions_scored=scored,
        actions_zero_actual_excluded=int(np.count_nonzero(acted & ~moving)),
        macro_f1=macro,
        macro_f1_status=macro_status,
    )


# ------------------------------------------------------------------ target units -> raw returns
def effective_scale_vector(scale: np.ndarray, floor: float) -> np.ndarray:
    """Vectorised twin of ``targets.effective_normalization_scale``: max(|scale|, floor).

    Non-finite scales stay NaN (those rows are later excluded and counted). The divisor is always
    positive, so converting a prediction to raw units can never flip its sign.
    """

    floor = float(floor)
    if not np.isfinite(floor) or floor <= 0:
        raise ValueError("normalization floor must be finite and strictly positive")
    values = np.asarray(scale, dtype=np.float64)
    return np.where(np.isfinite(values), np.maximum(np.abs(values), floor), np.nan)


def to_raw_returns(predicted_target_units: np.ndarray, divisor: np.ndarray | None) -> np.ndarray:
    """Convert predictions in TARGET units to raw decimal returns (None divisor == raw target)."""

    values = np.asarray(predicted_target_units, dtype=np.float64)
    if divisor is None:
        return values
    divisor = np.asarray(divisor, dtype=np.float64)
    if divisor.shape != values.shape:
        raise ValueError("divisor must be aligned with the predictions")
    return values * divisor


def definitions() -> dict[str, str]:
    """Human-readable definitions embedded once per fit in the telemetry log."""

    return {
        "version": ACTION_DIAGNOSTIC_VERSION,
        "metric_class": METRIC_CLASS,
        "units": "RAW decimal returns; thresholds are configured in basis points (1 bp = 0.0001)",
        "long_event": "actual_raw >= +event_threshold (inclusive)",
        "short_event": "actual_raw <= -event_threshold (inclusive)",
        "long_action": "predicted_raw >= +prediction_threshold (inclusive)",
        "short_action": "predicted_raw <= -prediction_threshold (inclusive)",
        "no_trade": "every other row; zero never triggers an event or an action",
        "precision": "TP / predicted actions on that side",
        "recall": "TP / actual events on that side (support)",
        "undefined": "zero denominator => null / NOT_DEFINED, never 0.0",
        "role": "DESCRIPTIVE Validation diagnostic: not selection, not evidence, not profit",
        "early_stopping": "unchanged: continuous L2 on Validation only",
    }
