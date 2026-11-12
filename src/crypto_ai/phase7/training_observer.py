"""Training-time diagnostics, health assessment and console formatting (monitoring ONLY).

Added by Claude (2026-11-08, pre-RunPod architecture hardening). Split out of ``training.py`` /
``training_metrics.py`` so that model fitting, the LightGBM callback, regression diagnostics,
action diagnostics, telemetry persistence and formatting are separate, individually testable
concerns. This module imports NumPy and the two pure metric modules only (no LightGBM, no
PyArrow at import time, no hardening import at module level, no circular dependency).

What is monitored (Train and VALIDATION rows only - TEST, Cal-A, Cal-B, July and August are never
passed to anything here):

* DEVELOPMENT_METRIC     train / validation RMSE and MAE, best iteration, rounds since best.
* DESCRIPTIVE_VALIDATION_DIAGNOSTIC  Pearson / Spearman / directional accuracy, prediction
  distribution, cross-sectional IC and the LONG / SHORT action diagnostics from
  ``action_metrics`` - computed from the model's own predictions on a (deterministic) sample of the
  Validation rows. None of these steers or stops a fit; early stopping stays on native L2.

Everything here is best-effort observation: a failure in this module is recorded and degrades
monitoring, it never changes a prediction, a stopping decision or a published result.
"""

from __future__ import annotations

import contextlib
import math
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from crypto_ai.phase7.action_metrics import (
    ActionThresholds,
    action_diagnostics,
    effective_scale_vector,
    to_raw_returns,
)
from crypto_ai.phase7.action_metrics import definitions as action_definitions
from crypto_ai.phase7.regression_diagnostics import cross_sectional_spearman, regression_snapshot

TELEMETRY_SCHEMA_VERSION = "training_telemetry_v1"
METRIC_CLASS_DEVELOPMENT = "DEVELOPMENT_METRIC"
METRIC_CLASS_DESCRIPTIVE = "DESCRIPTIVE_VALIDATION_DIAGNOSTIC"
TARGET_UNITS_RAW = "RAW_RETURN_DECIMAL"
TARGET_UNITS_NORMALIZED = "VOLATILITY_NORMALIZED_BY_EX_ANTE_SCALE"
MONITOR_SUBSAMPLE_SEED = 20_261_108
HARD_FAILURE, WARNING, INFORMATIONAL = "HARD_FAILURE", "WARNING", "INFORMATIONAL"
HEURISTIC_NOTICE = (
    "HEURISTIC labels from configurable thresholds. Not a significance test, not selection "
    "evidence, not a profitability statement; they never stop, select or tune a fit."
)
GIB = 1024**3

# Labels returned by :func:`summarize_training_health`.
LEARNING_SIGNAL_PRESENT = "LEARNING_SIGNAL_PRESENT"
WEAK_LEARNING_SIGNAL = "WEAK_LEARNING_SIGNAL"
NO_CLEAR_VALIDATION_IMPROVEMENT = "NO_CLEAR_VALIDATION_IMPROVEMENT"
SEVERE_GENERALIZATION_GAP = "SEVERE_GENERALIZATION_GAP"
PREDICTION_COLLAPSE = "PREDICTION_COLLAPSE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ------------------------------------------------------------------------------ json hygiene
def json_safe(value: Any) -> Any:
    """Recursively convert to strict-JSON types: NaN / +-inf become None, NumPy scalars unwrap."""

    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, int):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, Sequence | set | frozenset):
        return [json_safe(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return str(value)


# ------------------------------------------------------------------------------ settings
@dataclass(frozen=True)
class MonitorSettings:
    """Resolved monitoring / heuristic settings (all MONITORING class, none touches a fit)."""

    max_rows: int = 250_000
    diagnostics_every_checks: int = 1
    xs_ic_every_checks: int = 4
    xs_ic_min_symbols: int = 5
    gap_ratio_warn: float = 0.25
    gap_ratio_severe: float = 1.0
    variance_collapse_ratio: float = 0.01
    near_constant_abs: float = 1e-12
    plateau_rounds: int = 30
    improvement_rel_tol: float = 0.001
    min_iterations: int = 50
    min_available_ram_gib: float = 1.0
    min_free_disk_gib: float = 5.0

    @classmethod
    def from_config(cls, config: Any) -> MonitorSettings:
        """Read the ``monitor_*`` / ``health_*`` fields of a HardeningConfig (duck typed)."""

        return cls(
            max_rows=int(config.monitor_max_rows),
            diagnostics_every_checks=int(config.monitor_diagnostics_every_checks),
            xs_ic_every_checks=int(config.monitor_xs_ic_every_checks),
            xs_ic_min_symbols=int(config.monitor_xs_ic_min_symbols),
            gap_ratio_warn=float(config.health_gap_ratio_warn),
            gap_ratio_severe=float(config.health_gap_ratio_severe),
            variance_collapse_ratio=float(config.health_variance_collapse_ratio),
            plateau_rounds=int(config.health_plateau_rounds),
            improvement_rel_tol=float(config.health_improvement_rel_tol),
            min_iterations=int(config.health_min_iterations),
            min_available_ram_gib=float(config.health_min_available_ram_gib),
            min_free_disk_gib=float(config.health_min_free_disk_gib),
        )


# ------------------------------------------------------------------------------ row sampling
def monitor_indices(
    n_rows: int,
    max_rows: int,
    times: np.ndarray | None = None,
    *,
    seed: int = MONITOR_SUBSAMPLE_SEED,
) -> np.ndarray | None:
    """Deterministic row sample for in-fit predictions (None == use every row).

    A random sample (fixed seed) cannot alias with the symbol interleaving the way a plain stride
    can. With ``times`` whole timestamps are kept, so each sampled cross-section stays complete and
    the cross-sectional IC remains meaningful.
    """

    if n_rows < 0 or max_rows < 1:
        raise ValueError("MONITOR_ROW_LIMIT: row count must be non-negative and limit positive")
    if times is not None and np.asarray(times).shape != (n_rows,):
        raise ValueError("ROW_MISALIGNMENT: timestamps do not match the validation row count")
    if n_rows <= max_rows:
        return None
    rng = np.random.default_rng(seed)
    if times is None:
        return np.sort(rng.choice(n_rows, size=max_rows, replace=False))
    unique_times, inverse, counts = np.unique(
        np.asarray(times), return_inverse=True, return_counts=True
    )
    # Keep complete cross-sections without letting uneven group sizes exceed the memory cap.
    # A timestamp larger than the entire cap cannot be sampled intact; omit it rather than
    # silently allocating the full validation matrix or cutting a cross-section in half.
    eligible = np.flatnonzero(counts <= max_rows)
    if not len(eligible):
        raise ValueError("MONITOR_CROSS_SECTION_EXCEEDS_ROW_LIMIT")
    order = rng.permutation(eligible)
    selected = order[np.cumsum(counts[order]) <= max_rows]
    chosen = np.zeros(len(unique_times), dtype=bool)
    chosen[selected] = True
    return np.flatnonzero(chosen[inverse.reshape(-1)])


# ------------------------------------------------------------------------------ context
@dataclass(frozen=True)
class ValidationDiagnosticContext:
    """Per-fold Validation arrays used to interpret predictions in RAW decimal returns.

    ``actual_raw`` is the raw forward return of every Validation row. ``prediction_divisor`` is
    ``max(|scale|, floor)`` per row for a volatility-normalised target (raw = prediction x divisor)
    and None for a raw target. Both are aligned with the Validation table the fit receives.
    """

    actual_raw: np.ndarray
    prediction_divisor: np.ndarray | None
    times: np.ndarray | None
    thresholds: ActionThresholds
    target_units: str

    @property
    def n_rows(self) -> int:
        return int(len(self.actual_raw))


def build_validation_context(
    table: Any,
    *,
    target_type: str,
    normalization_floor: float,
    thresholds: ActionThresholds,
    raw_column: str = "raw_future_return",
    scale_column: str = "ex_ante_volatility_scale",
    time_column: str = "feature_time",
) -> ValidationDiagnosticContext:
    """Build the context from the VALIDATION table (duck-typed PyArrow table)."""

    def floats(name: str) -> np.ndarray:
        return np.asarray(
            table.column(name).combine_chunks().to_numpy(zero_copy_only=False), dtype=np.float64
        )

    actual_raw = floats(raw_column)
    divisor: np.ndarray | None = None
    units = TARGET_UNITS_RAW
    if target_type != "raw":
        divisor = effective_scale_vector(floats(scale_column), normalization_floor)
        units = TARGET_UNITS_NORMALIZED
    times: np.ndarray | None = None
    if time_column in getattr(table, "column_names", ()):
        import pyarrow as pa

        times = table.column(time_column).combine_chunks().cast(pa.int64()).to_numpy()
    return ValidationDiagnosticContext(actual_raw, divisor, times, thresholds, units)


def try_build_validation_context(
    table: Any,
    *,
    target_type: str,
    normalization_floor: float,
    config: Any,
) -> tuple[ValidationDiagnosticContext | None, str]:
    """Best-effort context for the in-fit diagnostics: (context, status). Never raises.

    ``config`` is the HardeningConfig; its two ``training_diagnostic_*_bps`` fields are the
    predeclared thresholds. A failure disables the diagnostics only (status says why).
    """

    try:
        thresholds = ActionThresholds(
            event_threshold_bps=float(config.training_diagnostic_event_threshold_bps),
            prediction_threshold_bps=float(config.training_diagnostic_prediction_threshold_bps),
        )
        context = build_validation_context(
            table,
            target_type=target_type,
            normalization_floor=normalization_floor,
            thresholds=thresholds,
        )
    except Exception as exc:  # monitoring must never block a fit
        return None, f"UNAVAILABLE:{type(exc).__name__}"
    return context, "ACTIVE"


# ------------------------------------------------------------------------------ diagnostics
class TrainingDiagnostics:
    """Predicts a fixed Validation sample on demand and scores it (no state besides arrays)."""

    def __init__(
        self,
        context: ValidationDiagnosticContext,
        settings: MonitorSettings,
        validation_x: np.ndarray,
        validation_y: np.ndarray,
        *,
        rows: np.ndarray | None = None,
    ) -> None:
        actual_raw, divisor, times = context.actual_raw, context.prediction_divisor, context.times
        if rows is not None:
            mask = np.asarray(rows, dtype=bool)
            if mask.shape != (context.n_rows,):
                raise ValueError("ROW_MISALIGNMENT: validation mask does not match the context")
            actual_raw = actual_raw[mask]
            divisor = None if divisor is None else divisor[mask]
            times = None if times is None else times[mask]
        n = int(len(validation_y))
        if not (len(actual_raw) == n == int(validation_x.shape[0])):
            raise ValueError(
                f"ROW_MISALIGNMENT: context {len(actual_raw)} rows, "
                f"y {n}, x {validation_x.shape[0]}"
            )
        # Unit guard: the fitted target must equal raw / divisor row by row. This fails closed on
        # misaligned rows AND on a raw-vs-normalised mix-up before any metric is computed.
        target_as_raw = np.asarray(validation_y, dtype=np.float64)
        if divisor is not None:
            target_as_raw = target_as_raw * divisor
        comparable = np.isfinite(target_as_raw) & np.isfinite(actual_raw)
        if not np.allclose(
            target_as_raw[comparable], actual_raw[comparable], rtol=1e-6, atol=1e-12
        ):
            raise ValueError("TARGET_UNIT_MISMATCH: y does not equal raw / divisor on these rows")
        picked = monitor_indices(n, settings.max_rows, times)
        self.subsampled = picked is not None
        if picked is None:
            self.x, self.y, self.actual_raw, self.divisor, self.times = (
                validation_x,
                np.asarray(validation_y, dtype=np.float64),
                actual_raw,
                divisor,
                times,
            )
        else:
            self.x = np.ascontiguousarray(validation_x[picked])
            self.y = np.asarray(validation_y, dtype=np.float64)[picked]
            self.actual_raw = actual_raw[picked]
            self.divisor = None if divisor is None else divisor[picked]
            self.times = None if times is None else times[picked]
        self.total_rows = n
        self.rows = int(len(self.y))
        self.settings = settings
        self.thresholds = context.thresholds
        self.target_units = context.target_units

    def snapshot(
        self,
        predict: Callable[[np.ndarray], np.ndarray],
        *,
        cross_section: bool,
        include_action: bool = True,
    ) -> dict[str, Any]:
        started = time.monotonic()
        predicted = np.asarray(predict(self.x), dtype=np.float64)
        if predicted.shape != self.y.shape:
            raise ValueError("DIAGNOSTIC_PREDICTION_SHAPE: prediction count differs from rows")
        regression = regression_snapshot(
            self.y, predicted, near_zero_abs=self.settings.near_constant_abs
        )
        action: dict[str, Any] = {}
        if include_action:
            action = action_diagnostics(
                self.actual_raw, to_raw_returns(predicted, self.divisor), self.thresholds
            ).to_flat_dict()
        xs: dict[str, Any] = {}
        if cross_section and self.times is not None:
            xs = cross_sectional_spearman(
                self.times, predicted, self.y, min_symbols=self.settings.xs_ic_min_symbols
            )
        return {
            "regression": regression,
            "action": action,
            "cross_section": xs,
            "diagnostic_rows": self.rows,
            "diagnostic_total_rows": self.total_rows,
            "diagnostic_subsampled": self.subsampled,
            "diagnostic_seconds": time.monotonic() - started,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "rows_used": self.rows,
            "rows_total": self.total_rows,
            "subsampled": self.subsampled,
            "subsample_seed": MONITOR_SUBSAMPLE_SEED if self.subsampled else None,
            "target_units": self.target_units,
            "prediction_conversion": (
                "NONE_TARGET_IS_RAW"
                if self.divisor is None
                else "RAW = PREDICTION x max(|ex_ante_volatility_scale|, normalization_floor)"
            ),
            "event_threshold_bps": float(self.thresholds.event_threshold_bps),
            "prediction_threshold_bps": float(self.thresholds.prediction_threshold_bps),
            "cross_section_available": self.times is not None,
            "action_definitions": action_definitions(),
        }


# ------------------------------------------------------------------------------ health
def _finite(value: Any) -> bool:
    return isinstance(value, int | float) and math.isfinite(value)


class HealthTracker:
    """Non-adaptive, heuristic training-health flags. Never raises, never stops a fit."""

    def __init__(self, settings: MonitorSettings) -> None:
        self.settings = settings
        self.previous_train_rmse: float | None = None
        self.previous_validation_rmse: float | None = None
        self.first_validation_rmse: float | None = None
        self.flag_counts: dict[str, int] = {}
        self.checks = 0

    def update(
        self,
        *,
        iteration: int,
        train_rmse: float | None,
        validation_rmse: float | None,
        best_validation_rmse: float | None,
        rounds_since_best: int,
        snapshot: Mapping[str, Any] | None,
        resources: Mapping[str, Any],
    ) -> dict[str, Any]:
        s = self.settings
        flags: list[dict[str, str]] = []

        def add(severity: str, code: str, detail: str) -> None:
            flags.append({"severity": severity, "code": code, "detail": detail})
            self.flag_counts[code] = self.flag_counts.get(code, 0) + 1

        if not (_finite(train_rmse) and _finite(validation_rmse)):
            add(HARD_FAILURE, "NON_FINITE_METRICS", "train or validation RMSE missing/non-finite")
        regression = (snapshot or {}).get("regression") or {}
        fraction = regression.get("finite_prediction_fraction")
        if fraction is not None and fraction < 1.0:
            add(HARD_FAILURE, "NON_FINITE_PREDICTIONS", f"finite fraction {fraction:.6f}")
        gap = None
        if _finite(train_rmse) and _finite(validation_rmse) and train_rmse > 0:
            gap = (validation_rmse - train_rmse) / train_rmse
            if iteration >= s.min_iterations and gap >= s.gap_ratio_warn:
                add(
                    WARNING,
                    "TRAIN_VALIDATION_GAP_HIGH",
                    f"validation RMSE is {gap:+.1%} vs train (threshold {s.gap_ratio_warn:.0%}); "
                    "periods differ in volatility, so this is a rough guide only",
                )
        if regression:
            std = regression.get("prediction_std")
            ratio = regression.get("prediction_actual_std_ratio")
            if _finite(std) and std <= s.near_constant_abs:
                add(WARNING, "PREDICTIONS_NEAR_CONSTANT", f"prediction std {std:.3e}")
            elif (
                iteration >= s.min_iterations
                and _finite(ratio)
                and ratio < s.variance_collapse_ratio
            ):
                add(
                    WARNING,
                    "PREDICTION_VARIANCE_COLLAPSE",
                    f"prediction std is {ratio:.2%} of target std (threshold "
                    f"{s.variance_collapse_ratio:.0%})",
                )
        tol = s.improvement_rel_tol
        previous = self.previous_validation_rmse
        if (
            _finite(validation_rmse)
            and previous is not None
            and validation_rmse < previous * (1 - tol)
        ):
            add(
                INFORMATIONAL,
                "VALIDATION_LOSS_IMPROVING",
                f"{previous:.4e} -> {validation_rmse:.4e}",
            )
        if rounds_since_best >= s.plateau_rounds:
            add(INFORMATIONAL, "VALIDATION_LOSS_PLATEAU", f"{rounds_since_best} rounds since best")
        if (
            _finite(train_rmse)
            and _finite(validation_rmse)
            and _finite(best_validation_rmse)
            and self.previous_train_rmse is not None
            and rounds_since_best > 0
            and validation_rmse > best_validation_rmse * (1 + tol)
            and train_rmse < self.previous_train_rmse * (1 - tol)
        ):
            add(WARNING, "OVERFITTING_PATTERN", "train RMSE still falling while validation worsens")
        available = resources.get("effective_memory_available")
        if _finite(available) and available < s.min_available_ram_gib * GIB:
            add(WARNING, "MEMORY_PRESSURE", f"{available / GIB:.2f} GiB available")
        free = resources.get("disk_free_bytes")
        if _finite(free) and free < s.min_free_disk_gib * GIB:
            add(WARNING, "DISK_PRESSURE", f"{free / GIB:.1f} GiB free")
        if self.first_validation_rmse is None and _finite(validation_rmse):
            self.first_validation_rmse = float(validation_rmse)
        if _finite(train_rmse):
            self.previous_train_rmse = float(train_rmse)
        if _finite(validation_rmse):
            self.previous_validation_rmse = float(validation_rmse)
        self.checks += 1
        return {
            "hard_failures": [f for f in flags if f["severity"] == HARD_FAILURE],
            "warnings": [f for f in flags if f["severity"] == WARNING],
            "informational": [f for f in flags if f["severity"] == INFORMATIONAL],
            "relative_generalization_gap": gap,
            "heuristic_notice": HEURISTIC_NOTICE,
        }


def summarize_training_health(
    *,
    settings: MonitorSettings,
    best_validation_rmse: float | None,
    first_validation_rmse: float | None,
    selected_train_rmse: float | None,
    selected_validation_rmse: float | None,
    zero_baseline_rmse: float | None,
    final_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """One DESCRIPTIVE label for a finished fit, with the numbers that produced it.

    ``selected_*`` are the train / validation RMSE at the iteration LightGBM keeps (the best
    validation round), so the generalisation gap describes the model that is actually saved.
    """

    regression = (final_snapshot or {}).get("regression") or {}
    vs_zero = (
        1.0 - best_validation_rmse / zero_baseline_rmse
        if _finite(best_validation_rmse) and _finite(zero_baseline_rmse) and zero_baseline_rmse > 0
        else None
    )
    vs_first = (
        1.0 - best_validation_rmse / first_validation_rmse
        if _finite(best_validation_rmse)
        and _finite(first_validation_rmse)
        and first_validation_rmse > 0
        else None
    )
    gap = (
        (selected_validation_rmse - selected_train_rmse) / selected_train_rmse
        if _finite(selected_train_rmse)
        and _finite(selected_validation_rmse)
        and selected_train_rmse > 0
        else None
    )
    spearman = regression.get("spearman")
    std = regression.get("prediction_std")
    ratio = regression.get("prediction_actual_std_ratio")
    reasons: list[str] = []
    if not _finite(best_validation_rmse):
        label = INSUFFICIENT_DATA
        reasons.append("no validation RMSE was observed")
    elif (_finite(std) and std <= settings.near_constant_abs) or (
        _finite(ratio) and ratio < settings.variance_collapse_ratio
    ):
        label = PREDICTION_COLLAPSE
        reasons.append("final predictions are (nearly) constant relative to the target")
    elif gap is not None and gap >= settings.gap_ratio_severe:
        label = SEVERE_GENERALIZATION_GAP
        reasons.append(f"validation RMSE exceeds train RMSE by {gap:+.1%}")
    elif (
        vs_zero is not None
        and vs_zero > 0
        and vs_first is not None
        and vs_first >= settings.improvement_rel_tol
        and (spearman is None or spearman > 0)
    ):
        label = LEARNING_SIGNAL_PRESENT
        reasons.append("validation RMSE beat the zero baseline and improved during the fit")
    elif vs_zero is not None and vs_zero > 0:
        label = WEAK_LEARNING_SIGNAL
        reasons.append("validation RMSE beat the zero baseline by a small or unconfirmed margin")
    else:
        label = NO_CLEAR_VALIDATION_IMPROVEMENT
        reasons.append("validation RMSE did not clearly beat the zero baseline")
    return {
        "label": label,
        "reasons": reasons,
        "heuristic_notice": HEURISTIC_NOTICE,
        "inputs": {
            "best_validation_rmse": best_validation_rmse,
            "first_check_validation_rmse": first_validation_rmse,
            "train_rmse_at_selected_iteration": selected_train_rmse,
            "validation_rmse_at_selected_iteration": selected_validation_rmse,
            "zero_baseline_validation_rmse": zero_baseline_rmse,
            "relative_improvement_vs_zero_baseline": vs_zero,
            "relative_improvement_since_first_check": vs_first,
            "relative_generalization_gap": gap,
            "final_validation_spearman": spearman,
            "final_prediction_std": std,
            "final_prediction_actual_std_ratio": ratio,
        },
        "thresholds": {
            "improvement_rel_tol": settings.improvement_rel_tol,
            "gap_ratio_severe": settings.gap_ratio_severe,
            "variance_collapse_ratio": settings.variance_collapse_ratio,
            "near_constant_abs": settings.near_constant_abs,
        },
    }


# Operational fields that legitimately differ between two identical runs (attempt ids, log names,
# wall-clock timings, machine resource flags, telemetry I/O health). They stay in the JSONL log and
# are left out of the training report so a rerun of the same inputs yields the same report.
_VOLATILE_SUMMARY_KEYS = frozenset(
    {"attempt_id", "attempt_number", "log_file", "telemetry_status", "telemetry_errors"}
)
_RESOURCE_FLAG_CODES = frozenset({"MEMORY_PRESSURE", "DISK_PRESSURE"})


def report_view(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Deterministic part of an end-of-fit summary for the (reproducible) training report."""

    out = {key: value for key, value in summary.items() if key not in _VOLATILE_SUMMARY_KEYS}
    out["flag_counts"] = {
        code: count
        for code, count in (summary.get("flag_counts") or {}).items()
        if code not in _RESOURCE_FLAG_CODES
    }
    snapshot = summary.get("final_snapshot")
    if isinstance(snapshot, Mapping):
        out["final_snapshot"] = {k: v for k, v in snapshot.items() if k != "diagnostic_seconds"}
    out["operational_fields_in_telemetry_log_only"] = sorted(
        _VOLATILE_SUMMARY_KEYS | {"diagnostic_seconds", *_RESOURCE_FLAG_CODES}
    )
    return out


# ------------------------------------------------------------------------------ resources
def sample_resources(directory: Path) -> dict[str, Any]:
    """RSS, container-aware available RAM and free disk. Best effort; never raises."""

    out: dict[str, Any] = {
        "rss_bytes": None,
        "effective_memory_available": None,
        "ram_total_bytes": None,
        "disk_free_bytes": None,
    }
    try:
        from crypto_ai.phase7.runtime import memory_snapshot

        snapshot = memory_snapshot()
        out["rss_bytes"] = int(snapshot["process_rss_bytes"])
        out["effective_memory_available"] = int(snapshot["ram_available_bytes"])
        out["ram_total_bytes"] = int(snapshot["ram_total_bytes"])
    except Exception:  # monitoring must never break a fit
        pass
    with contextlib.suppress(Exception):
        out["disk_free_bytes"] = int(shutil.disk_usage(directory).free)
    return out


# ------------------------------------------------------------------------------ formatting
def _num(value: Any, digits: int = 4) -> str:
    if not _finite(value):
        return "N/A"
    value = float(value)
    return f"{value:.2e}" if value != 0 and abs(value) < 1e-3 else f"{value:+.{digits}f}"


def _plain(value: Any, digits: int = 4) -> str:
    return "N/A" if not _finite(value) else f"{float(value):.{digits}f}"


def _pct(value: Any) -> str:
    return "N/A" if not _finite(value) else f"{100 * float(value):.1f}%"


def _gib(value: Any) -> str:
    return "N/A" if not _finite(value) else f"{float(value) / GIB:.1f} GiB"


def _count(value: Any) -> str:
    return "N/A" if not _finite(value) else f"{int(value):,}"


def _elapsed(seconds: Any) -> str:
    if not _finite(seconds):
        return "N/A"
    total = int(seconds)
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def format_side(prefix: str, name: str, action: Mapping[str, Any]) -> str:
    """One LONG / SHORT row. Undefined ratios print N/A; support counts explain why."""

    def part(label: str, key: str) -> str:
        return f"{label} {_plain(action.get(f'{prefix}_{key}'), 3):>5}"

    return (
        f"{name:<5} {part('precision', 'precision')}  {part('recall', 'recall')}  "
        f"{part('F1', 'f1')}  | predicted {_count(action.get(f'{prefix}_predicted_count'))}"
        f" | actual events (support) {_count(action.get(f'{prefix}_support'))}"
    )


def format_diagnostic_lines(
    label: str,
    iteration: int,
    telemetry: Mapping[str, Any],
    diagnostics: Mapping[str, Any] | None,
    health: Mapping[str, Any],
) -> list[str]:
    """Readable block printed under the main round line every monitoring check.

    VALIDATION rows only. Nothing here is TEST, nothing selects or stops a fit, and nothing here is
    a profitability statement. Undefined values print ``N/A``.
    """

    indent = f"[fit {label}]   "
    lines = [
        f"[fit {label}] ---- round {iteration}/{telemetry.get('round_limit')} | elapsed "
        f"{_elapsed(telemetry.get('elapsed_seconds'))} | backend {telemetry.get('backend')} "
        f"x{telemetry.get('cpu_threads')} threads | lr {telemetry.get('learning_rate')} ----",
        f"{indent}loss        train RMSE {_num(telemetry.get('train_rmse'))}  validation RMSE "
        f"{_num(telemetry.get('validation_rmse'))}  validation MAE "
        f"{_num(telemetry.get('validation_mae'))}  gap (val-train)/train "
        f"{_pct(telemetry.get('relative_generalization_gap'))}",
        f"{indent}best        validation RMSE {_num(telemetry.get('best_validation_score'))} at "
        f"round {telemetry.get('best_iteration') or 'N/A'} | rounds since best "
        f"{telemetry.get('rounds_since_best')} (early stopping: validation L2 only)",
    ]
    if diagnostics is not None:
        reg, action = diagnostics["regression"], diagnostics.get("action") or {}
        sampled = "fixed subsample" if diagnostics.get("diagnostic_subsampled") else "all rows"
        xs = diagnostics.get("cross_section") or {}
        if xs.get("xs_status") == "DEFINED":
            xs_text = (
                f"  xs-IC {_num(xs.get('xs_spearman_ic_mean'))} "
                f"({_count(xs.get('xs_timestamps_scored'))} timestamps)"
            )
        elif xs:
            xs_text = f"  xs-IC N/A (< {xs.get('xs_min_symbols')} assets per timestamp)"
        else:
            xs_text = "  xs-IC not computed this check"
        lines += [
            f"{indent}validation  [DESCRIPTIVE, {sampled}, n="
            f"{_count(diagnostics['diagnostic_rows'])} of "
            f"{_count(diagnostics['diagnostic_total_rows'])}]  Pearson "
            f"{_num(reg.get('pearson'))}  Spearman {_num(reg.get('spearman'))}  direction "
            f"{_plain(reg.get('directional_accuracy'))}{xs_text}",
            f"{indent}predictions mean {_num(reg.get('prediction_mean'))}  std "
            f"{_num(reg.get('prediction_std'))} ({_pct(reg.get('prediction_actual_std_ratio'))} "
            f"of target std)  range [{_num(reg.get('prediction_min'))}, "
            f"{_num(reg.get('prediction_max'))}]  finite "
            f"{_pct(reg.get('finite_prediction_fraction'))}",
        ]
        if action:
            event_bps = action["event_threshold_bps"]
            trigger_bps = action["prediction_threshold_bps"]
            lines += [
                f"{indent}actions     [raw return; event |actual| >= {event_bps:g} bps, action "
                f"|predicted| >= {trigger_bps:g} bps; DESCRIPTIVE, not selection, not profit]",
                f"{indent}  {format_side('long', 'LONG', action)}",
                f"{indent}  {format_side('short', 'SHORT', action)}",
                f"{indent}  coverage {_pct(action.get('action_coverage'))}  NO_TRADE "
                f"{_pct(action.get('no_trade_coverage'))}  action direction hit-rate "
                f"{_plain(action.get('action_hit_rate'), 3)}",
            ]
    lines.append(
        f"{indent}resources   RSS {_gib(telemetry.get('rss_bytes'))}  available RAM "
        f"{_gib(telemetry.get('effective_memory_available'))}  free disk "
        f"{_gib(telemetry.get('disk_free_bytes'))}  | rows train "
        f"{_count(telemetry.get('train_rows'))} validation "
        f"{_count(telemetry.get('validation_rows'))} | {telemetry.get('feature_count')} features"
    )
    rendered = [
        f"{flag['severity']} {flag['code']} ({flag['detail']})"
        for group in ("hard_failures", "warnings", "informational")
        for flag in health.get(group, [])
    ]
    if rendered:
        lines.append(f"{indent}health      [heuristic] " + " | ".join(rendered))
    return lines


# ------------------------------------------------------------------------------ resolved config
_UNITS = {
    "training_diagnostic_event_threshold_bps": ("bps (raw return)", "DIAGNOSTIC_DEFINITION"),
    "training_diagnostic_prediction_threshold_bps": ("bps (raw return)", "DIAGNOSTIC_DEFINITION"),
    "fixed_threshold_bps": ("bps (LEGACY, unused by the live path)", "LEGACY"),
    "monitor_max_rows": ("rows", "MONITORING"),
    "monitor_diagnostics_every_checks": ("checks", "MONITORING"),
    "monitor_xs_ic_every_checks": ("checks", "MONITORING"),
    "monitor_xs_ic_min_symbols": ("symbols", "MONITORING"),
    "health_gap_ratio_warn": ("ratio", "MONITORING"),
    "health_gap_ratio_severe": ("ratio", "MONITORING"),
    "health_variance_collapse_ratio": ("ratio", "MONITORING"),
    "health_plateau_rounds": ("boosting rounds", "MONITORING"),
    "health_improvement_rel_tol": ("relative", "MONITORING"),
    "health_min_iterations": ("boosting rounds", "MONITORING"),
    "health_min_available_ram_gib": ("GiB", "MONITORING"),
    "health_min_free_disk_gib": ("GiB", "MONITORING"),
}


def resolved_monitor_manifest(environ: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """Every monitoring-relevant setting: resolved value, unit, class and where it came from."""

    from dataclasses import asdict

    from crypto_ai.phase7.hardening import CONFIG_ENV, current_config

    env = os.environ if environ is None else environ
    defaults = asdict(type(current_config())())
    resolved = asdict(current_config())
    config_path = env.get(CONFIG_ENV)
    in_file: set[str] = set()
    if config_path:
        try:
            import tomllib

            data = tomllib.loads(Path(config_path).read_text(encoding="utf-8"))
            in_file = set(data.get("hardening", data))
        except Exception:
            in_file = set()
    rows: list[dict[str, Any]] = []
    for name, (unit, setting_class) in _UNITS.items():
        if name not in resolved:
            continue
        rows.append(
            {
                "name": name,
                "value": resolved[name],
                "default": defaults[name],
                "unit": unit,
                "class": setting_class,
                "source": f"TOML:{config_path}" if name in in_file else "DEFAULT",
            }
        )
    period = env.get("PHASE7_METRICS_EVERY")
    rows.append(
        {
            "name": "PHASE7_METRICS_EVERY",
            "value": int(period) if period else 25,
            "default": 25,
            "unit": "boosting rounds between console / telemetry checks",
            "class": "MONITORING",
            "source": "ENV" if period else "DEFAULT",
        }
    )
    return json_safe(rows)
