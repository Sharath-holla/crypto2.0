"""Training-only observer: no TEST inputs, no model selection, no Aiventra dependency."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from crypto_ai.phase7.hardening import (
    FitAbortedError,
    console_line,
    current_config,
    fixed_threshold_precision_recall,
    record_latest_fit,
    trend_flag,
)
from crypto_ai.research.metrics import directional_accuracy


@dataclass(frozen=True)
class TrainingMetricScope:
    directory: Path
    identity: dict[str, Any]
    period: int = 25


_SCOPE: ContextVar[TrainingMetricScope | None] = ContextVar("phase7_fit_metrics", default=None)
_OUTPUT_LOCK = threading.Lock()


def reporting_period() -> int:
    period = int(os.environ.get("PHASE7_METRICS_EVERY", "25"))
    if period < 1:
        raise ValueError("PHASE7_METRICS_EVERY must be a positive integer")
    return period


@contextmanager
def training_metric_scope(directory: Path, **identity: Any) -> Iterator[None]:
    token = _SCOPE.set(TrainingMetricScope(directory, identity, reporting_period()))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def display_metrics(actual: np.ndarray, predicted: np.ndarray) -> list[tuple[str, float, bool]]:
    """Read LightGBM's existing fit predictions; never call model.predict here."""
    residual = predicted - actual
    # CHANGED BY CLAUDE (2026-11-02, Phase 3 item 5): fixed-threshold precision/recall are added
    # AFTER the existing metrics (the first metric, L2, still drives early stopping). They are
    # diagnostics on whatever rows LightGBM evaluates (TRAIN or VALIDATION), never TEST.
    extra: list[tuple[str, float, bool]] = []
    settings = current_config()
    if settings.console_precision_recall:
        scores = fixed_threshold_precision_recall(
            actual, predicted, settings.fixed_threshold_bps, max_rows=settings.metric_max_rows
        )
        # 0.0 when a score is undefined (no signals / no real moves): LightGBM needs a number.
        extra = [
            ("fixed_precision", float(scores["precision"] or 0.0), True),
            ("fixed_recall", float(scores["recall"] or 0.0), True),
        ]
    return [
        ("mae", float(np.mean(np.abs(residual))), False),
        ("rmse", float(np.sqrt(np.mean(residual * residual))), False),
        # CHANGED BY CLAUDE (2026-11-02, finding L-01): zero actuals excluded from the denominator.
        # OLD CODE (kept for reference):
        # ("directional_accuracy", float(np.mean(np.sign(actual) == np.sign(predicted))), True),
        ("directional_accuracy", directional_accuracy(actual, predicted), True),
        *extra,
    ]


@dataclass(eq=False)
class FitMetricObserver:
    scope: TrainingMetricScope
    estimator_key: str
    order: int = 20
    before_iteration: bool = False
    started: float = field(default_factory=time.monotonic)
    last: dict[str, Any] | None = None
    # CHANGED BY CLAUDE (2026-11-02, Phase 3 items 1 and 3): console trend + optional abort rule.
    zero_baseline_rmse: float | None = None  # set by models._fit from VALIDATION targets only
    previous_validation_rmse: float | None = None
    worse_streak: int = 0
    path: Path = field(init=False)

    def __post_init__(self) -> None:
        record_latest_fit({})  # CHANGED BY CLAUDE (2026-11-02): no stale metrics in the heartbeat
        self.scope.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.scope.directory / f"fit-{uuid.uuid4().hex}.jsonl"
        self.emit("FIT_STARTED", estimator=self.estimator_key)

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            **self.scope.identity,
            "event": event,
            "estimator": self.estimator_key,
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_seconds": time.monotonic() - self.started,
            "metric_scope": "TRAIN_AND_VALIDATION_ONLY",
            "test_access": "NOT_RELEASED_DURING_FIT",
            "diagnostic_weighting": "UNWEIGHTED_ROWS; native L2 retains fit weighting",
            **fields,
        }
        line = json.dumps(record, sort_keys=True, allow_nan=False)
        with _OUTPUT_LOCK:
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")
                stream.flush()
            print(line, flush=True)

    def __call__(self, env: Any) -> None:
        metrics: dict[str, dict[str, float]] = {}
        for dataset, name, value, *_rest in env.evaluation_result_list or ():
            if dataset not in {"train", "validation"}:
                raise ValueError("fit observer refuses non-training/validation metrics")
            if not np.isfinite(value):
                raise ValueError("non-finite fit metric")
            metrics.setdefault(dataset, {})[name] = float(value)
        self.last = {
            "iteration": env.iteration + 1,
            "round_limit": env.end_iteration,
            "metrics": metrics,
        }
        if env.iteration == env.begin_iteration or (env.iteration + 1) % self.scope.period == 0:
            self.emit("FIT_METRICS", **self.last)
            self._console_and_abort(env.iteration + 1, env.end_iteration, metrics)

    def _console_and_abort(
        self, iteration: int, round_limit: int, metrics: dict[str, dict[str, float]]
    ) -> None:
        """One readable console line per check (the JSON line above is unchanged) + abort rule."""

        settings = current_config()
        validation_rmse = metrics.get("validation", {}).get("rmse")
        flag = trend_flag(self.previous_validation_rmse, validation_rmse or 0.0)
        record_latest_fit(
            {
                "estimator": self.estimator_key,
                "iteration": iteration,
                "round_limit": round_limit,
                "validation": dict(metrics.get("validation", {})),
                "trend": flag,
            }
        )
        if settings.console_table:
            with _OUTPUT_LOCK:
                print(
                    console_line(
                        f"{self.scope.identity.get('fold_id', '?')}/"
                        f"{self.scope.identity.get('spec_id', '?')}/{self.estimator_key}",
                        iteration,
                        round_limit,
                        metrics,
                        flag,
                    ),
                    flush=True,
                )
        self.previous_validation_rmse = validation_rmse
        if settings.abort_after_worse_checks and self.zero_baseline_rmse and validation_rmse:
            self.worse_streak = (
                self.worse_streak + 1 if validation_rmse > self.zero_baseline_rmse else 0
            )
            if self.worse_streak >= settings.abort_after_worse_checks:
                self.emit(
                    "FIT_ABORTED",
                    reason="VALIDATION_RMSE_WORSE_THAN_ZERO_BASELINE",
                    consecutive_checks=self.worse_streak,
                    validation_rmse=validation_rmse,
                    zero_baseline_rmse=self.zero_baseline_rmse,
                )
                raise FitAbortedError(
                    f"validation RMSE worse than the zero-return baseline for "
                    f"{self.worse_streak} consecutive checks"
                )

    def finish(self, estimator: Any) -> None:
        # Early stopping may have ended between reporting intervals. Keep last-round
        # metrics distinct from best-iteration scores rather than relabelling them.
        # LightGBM rolls the fitted booster back to its best iteration even when
        # all requested rounds ran. n_iter_ therefore cannot identify why fitting ended.
        stop_reason = "UNKNOWN"
        if self.last is not None:
            stop_reason = (
                "EARLY_STOPPING"
                if self.last["iteration"] < self.last["round_limit"]
                else "ROUND_LIMIT"
            )
        self.emit(
            "FIT_FINISHED",
            best_iteration=int(estimator.best_iteration_),
            best_scores=estimator.best_score_,
            last_round=self.last,
            stop_reason=stop_reason,
        )

    def fail(self, error: Exception) -> None:
        # Do not copy exception text, input data or credentials into metric logs.
        self.emit("FIT_FAILED", error_type=type(error).__name__, last_round=self.last)


def fit_observer(estimator_key: str) -> FitMetricObserver | None:
    scope = _SCOPE.get()
    return FitMetricObserver(scope, estimator_key) if scope is not None else None
