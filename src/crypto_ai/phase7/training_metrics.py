"""Training-only observer: no TEST inputs, no model selection, no Aiventra dependency."""

from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from crypto_ai.phase7.hardening import (
    FitAbortedError,
    console_line,
    current_config,
    process_stats,
    record_latest_fit,
    trend_flag,
)
from crypto_ai.phase7.training_observer import (
    METRIC_CLASS_DESCRIPTIVE,
    METRIC_CLASS_DEVELOPMENT,
    TELEMETRY_SCHEMA_VERSION,
    HealthTracker,
    MonitorSettings,
    TrainingDiagnostics,
    ValidationDiagnosticContext,
    format_diagnostic_lines,
    json_safe,
    sample_resources,
    summarize_training_health,
)
from crypto_ai.research.metrics import directional_accuracy


@dataclass(frozen=True)
class TrainingMetricScope:
    directory: Path
    identity: dict[str, Any]
    period: int = 25
    # CHANGED BY CLAUDE (2026-11-08): optional Validation-only context for the in-fit diagnostics
    # and a registry the observers fill with a per-estimator training summary (read by training.py
    # after the fit; telemetry is never authoritative, the ledger is).
    diagnostics: ValidationDiagnosticContext | None = None
    summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    # cumulative display_metrics time across estimators (mutable holder; the scope is frozen)
    timing: dict[str, float] = field(default_factory=lambda: {"custom_metric_seconds": 0.0})


_SCOPE: ContextVar[TrainingMetricScope | None] = ContextVar("phase7_fit_metrics", default=None)
_OUTPUT_LOCK = threading.Lock()


def reporting_period() -> int:
    period = int(os.environ.get("PHASE7_METRICS_EVERY", "25"))
    if period < 1:
        raise ValueError("PHASE7_METRICS_EVERY must be a positive integer")
    return period


@contextmanager
def training_metric_scope(
    directory: Path,
    *,
    diagnostics: ValidationDiagnosticContext | None = None,
    **identity: Any,
) -> Iterator[TrainingMetricScope]:
    # CHANGED BY CLAUDE (2026-11-08): yields the scope (callers that ignore the value are unchanged)
    # OLD CODE (kept for reference):
    # def training_metric_scope(directory: Path, **identity: Any) -> Iterator[None]:
    #     token = _SCOPE.set(TrainingMetricScope(directory, identity, reporting_period()))
    #     try:
    #         yield
    scope = TrainingMetricScope(directory, identity, reporting_period(), diagnostics)
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)


def display_metrics(actual: np.ndarray, predicted: np.ndarray) -> list[tuple[str, float, bool]]:
    """Read LightGBM's existing fit predictions; never call model.predict here.

    CHANGED BY CLAUDE (2026-11-08): the pooled ``fixed_precision`` / ``fixed_recall`` pair is gone.
    LightGBM requires a float from this callback, so an undefined precision (no signals) had to be
    coerced to 0.0, and for a volatility-normalised target the values were in NORMALISED units
    while the threshold was labelled in raw bps. LONG / SHORT precision and recall are now computed
    by ``action_metrics`` on RAW returns inside the observer, with NOT_DEFINED kept as null.
    The default L2 metric is still evaluated first, so early stopping is unchanged.
    """
    started = time.perf_counter()
    residual = predicted - actual
    # OLD CODE (kept for reference): appended
    #   ("fixed_precision", float(scores["precision"] or 0.0), True),
    #   ("fixed_recall", float(scores["recall"] or 0.0), True)
    # when ``console_precision_recall`` was set, from ``fixed_threshold_precision_recall``.
    result = [
        ("mae", float(np.mean(np.abs(residual))), False),
        ("rmse", float(np.sqrt(np.mean(residual * residual))), False),
        # CHANGED BY CLAUDE (2026-11-02, finding L-01): zero actuals excluded from the denominator.
        # OLD CODE (kept for reference):
        # ("directional_accuracy", float(np.mean(np.sign(actual) == np.sign(predicted))), True),
        ("directional_accuracy", directional_accuracy(actual, predicted), True),
    ]
    # CHANGED BY CLAUDE (2026-11-08, OBS-PERF-01): LightGBM runs this Python metric on the full
    # TRAIN and VALIDATION sets EVERY round (measured +18-24% fit time on a synthetic fixture). The
    # cumulative time is recorded so the RunPod smoke measures the real cost; values are unchanged.
    scope = _SCOPE.get()
    if scope is not None:
        with contextlib.suppress(Exception), _OUTPUT_LOCK:  # timing must never break a fit
            scope.timing["custom_metric_seconds"] += time.perf_counter() - started
    return result


def _prior_attempts(directory: Path, estimator_key: str, current: Path) -> list[dict[str, Any]]:
    """Earlier fit logs for the same estimator in this directory (resume / retry marker).

    Every attempt writes its own ``fit-<attempt_id>.jsonl``; nothing is appended to an old log, so a
    resumed run can never duplicate rounds inside one file. The marker lets a reader pick the
    attempt that reached FIT_FINISHED. Best effort: any problem returns what was found so far.
    """

    found: list[dict[str, Any]] = []
    try:
        for path in sorted(directory.glob("fit-*.jsonl")):
            if path == current:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            if not lines or json.loads(lines[0]).get("estimator") != estimator_key:
                continue
            last = json.loads(lines[-1]) if lines[-1].strip() else {}
            found.append({"file": path.name, "last_event": last.get("event")})
    except Exception:  # a damaged old log must not stop a new attempt
        pass
    return found


def _reason_code(error: Exception) -> str:
    """A short, data-free reason: the leading UPPER_CASE code of the message, else the type."""

    head = str(error).split(":", 1)[0].strip()
    if head and head.upper() == head and head.replace("_", "").isalnum():
        return head
    return type(error).__name__


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
    # CHANGED BY CLAUDE (2026-11-06, final hardening): console monitoring state (validation only).
    best_validation_rmse: float | None = None
    best_iteration: int = 0
    started_at: float | None = None
    # CHANGED BY CLAUDE (2026-11-08, pre-RunPod hardening): run facts recorded in every telemetry
    # record, Validation-only in-fit diagnostics, telemetry health and a retry marker.
    train_rows: int | None = None
    validation_rows: int | None = None
    feature_count: int | None = None
    model_threads: int | None = None
    backend_name: str | None = None
    learning_rate: float | None = None
    diagnostics: TrainingDiagnostics | None = None
    diagnostics_status: str = "NOT_CONFIGURED"
    diagnostics_errors: int = 0
    telemetry_status: str = "OK"
    telemetry_errors: int = 0
    train_rmse_at_best: float | None = None
    check_index: int = 0
    attempt_number: int = 1
    _cached_prediction: tuple[int, np.ndarray] | None = field(default=None, repr=False)
    attempt_id: str = field(init=False)
    monitor_settings: MonitorSettings = field(init=False)
    health: HealthTracker = field(init=False)
    path: Path = field(init=False)

    def __post_init__(self) -> None:
        record_latest_fit({})  # CHANGED BY CLAUDE (2026-11-02): no stale metrics in the heartbeat
        self.attempt_id = uuid.uuid4().hex
        self.monitor_settings = MonitorSettings.from_config(current_config())
        self.health = HealthTracker(self.monitor_settings)
        self.path = self.scope.directory / f"fit-{self.attempt_id}.jsonl"
        # OLD CODE (kept for reference): self.scope.directory.mkdir(parents=True, exist_ok=True)
        # raised on failure. Telemetry is never authoritative, so a log-directory problem now
        # degrades monitoring instead of failing the fit (the ledger / model save report real I/O
        # problems themselves).
        try:
            self.scope.directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._telemetry_failed(exc)
        prior = _prior_attempts(self.scope.directory, self.estimator_key, self.path)
        self.attempt_number = len(prior) + 1
        self.emit(
            "FIT_STARTED",
            estimator=self.estimator_key,
            telemetry_schema_version=TELEMETRY_SCHEMA_VERSION,
            attempt_number=self.attempt_number,
            prior_attempts=prior,
            resumed_after_incomplete_attempt=any(
                item["last_event"] != "FIT_FINISHED" for item in prior
            ),
        )

    # ------------------------------------------------------------------ persistence
    def _telemetry_failed(self, error: Exception) -> None:
        self.telemetry_errors += 1
        if self.telemetry_status == "OK":
            self.telemetry_status = "DEGRADED"
            with _OUTPUT_LOCK:
                print(
                    f"[fit {self.estimator_key}] TELEMETRY_DEGRADED: {type(error).__name__} "
                    f"while writing {self.path.name}; fitting continues and the result ledger is "
                    "unaffected (telemetry is never authoritative)",
                    flush=True,
                )

    def emit(self, event: str, *, echo: bool = True, **fields: Any) -> None:
        record = {
            **self.scope.identity,
            "event": event,
            "estimator": self.estimator_key,
            "attempt_id": self.attempt_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "elapsed_seconds": time.monotonic() - self.started,
            "metric_scope": "TRAIN_AND_VALIDATION_ONLY",
            "test_access": "NOT_RELEASED_DURING_FIT",
            "diagnostic_weighting": "UNWEIGHTED_ROWS; native L2 retains fit weighting",
            **fields,
        }
        # OLD CODE (kept for reference): json.dumps(record, sort_keys=True, allow_nan=False) raised
        # on a NaN anywhere in a record. json_safe maps non-finite numbers to null instead.
        line = json.dumps(json_safe(record), sort_keys=True, allow_nan=False)
        error: OSError | None = None
        with _OUTPUT_LOCK:
            try:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:  # disk full / permissions: degrade, never fail the fit
                error = exc
            if echo:
                print(line, flush=True)
        if error is not None:
            self._telemetry_failed(error)

    # ------------------------------------------------------------------ binding
    def bind_validation(
        self,
        validation_x: np.ndarray,
        validation_y: np.ndarray,
        *,
        rows: np.ndarray | None,
        train_rows: int,
        feature_count: int,
        model_threads: int,
        backend_name: str,
        learning_rate: float,
    ) -> None:
        """Record run facts and (if a Validation context exists) enable the in-fit diagnostics.

        A row-alignment or unit mismatch disables the diagnostics for this estimator and says so in
        the log and on the console; it never fails or alters the fit.
        """

        self.train_rows = int(train_rows)
        self.validation_rows = int(len(validation_y))
        self.feature_count = int(feature_count)
        self.model_threads = int(model_threads)
        self.backend_name = str(backend_name)
        self.learning_rate = float(learning_rate)
        context = self.scope.diagnostics
        if context is None:
            return
        try:
            self.diagnostics = TrainingDiagnostics(
                context, self.monitor_settings, validation_x, validation_y, rows=rows
            )
        except Exception as exc:
            self.diagnostics = None
            self.diagnostics_status = f"UNAVAILABLE:{_reason_code(exc)}"
            self.emit("DIAGNOSTICS_UNAVAILABLE", reason=_reason_code(exc))
            return
        self.diagnostics_status = "ACTIVE"
        self.emit(
            "DIAGNOSTICS_BOUND",
            echo=False,
            monitor_settings=asdict(self.monitor_settings),
            **self.diagnostics.describe(),
        )

    # ------------------------------------------------------------------ per-round callback
    def __call__(self, env: Any) -> None:
        metrics: dict[str, dict[str, float]] = {}
        for dataset, name, value, *_rest in env.evaluation_result_list or ():
            if dataset not in {"train", "validation"}:
                raise ValueError("fit observer refuses non-training/validation metrics")
            if not np.isfinite(value):
                raise ValueError("non-finite fit metric")
            metrics.setdefault(dataset, {})[name] = float(value)
        iteration = env.iteration + 1
        # CHANGED BY CLAUDE (2026-11-08): the best validation round is tracked on EVERY round (it
        # used to be updated only on console rounds), so "rounds since best" matches what LightGBM's
        # early stopping sees. Strict improvement, same as early stopping. Observation only.
        validation_rmse = metrics.get("validation", {}).get("rmse")
        if validation_rmse is not None and (
            self.best_validation_rmse is None or validation_rmse < self.best_validation_rmse
        ):
            self.best_validation_rmse, self.best_iteration = validation_rmse, iteration
            self.train_rmse_at_best = metrics.get("train", {}).get("rmse")
        self.last = {
            "iteration": iteration,
            "round_limit": env.end_iteration,
            "metrics": metrics,
        }
        if env.iteration == env.begin_iteration or iteration % self.scope.period == 0:
            # CHANGED BY CLAUDE (2026-11-08): the JSON record is always written to the log, but is
            # echoed to the console only when the readable table is off (no duplicate flooding).
            # OLD CODE (kept for reference): self.emit("FIT_METRICS", **self.last)
            self.emit("FIT_METRICS", echo=not current_config().console_table, **self.last)
            lines = self._monitor_check(env, iteration, metrics)
            try:
                self._console_and_abort(iteration, env.end_iteration, metrics)
            finally:
                if lines:
                    with _OUTPUT_LOCK:
                        for line in lines:
                            print(line, flush=True)

    # ------------------------------------------------------------------ monitoring check
    def _label(self) -> str:
        return (
            f"{self.scope.identity.get('fold_id', '?')}/"
            f"{self.scope.identity.get('spec_id', '?')}/{self.estimator_key}"
        )

    def _incremental_predict(self, booster: Any, x: np.ndarray, iteration: int) -> np.ndarray:
        """Validation-sample prediction at ``iteration`` reusing the previous check's sum.

        CHANGED BY CLAUDE (2026-11-08, observer cost): a GBDT regression prediction is the sum of
        its trees (the initial average is folded into the first tree), so only trees added since
        the last check are predicted. Total cost is O(trees) instead of O(trees^2) (a full predict
        every 25 rounds was ~4-9% of a single-thread smoke fit, now <1%). Floating-point summation
        order differs from a full predict by ~1e-16 relative; this is a descriptive diagnostic.
        Non-GBDT boosting (DART changes earlier trees) falls back to a full predict.
        """

        # CHANGED BY CLAUDE (2026-11-08, defect OBS-03): LightGBM's predict() without num_threads
        # resets the OpenMP thread count to ALL cores, and the remaining training rounds then run
        # with that count (measured: 2.6x faster single-"thread" fit). Always pin the fit's own
        # thread budget so monitoring can never break the CPU admission contract.
        threads = {"num_threads": max(1, int(self.model_threads or 1))}
        boosting = str(getattr(booster, "params", {}).get("boosting", "gbdt"))
        cached = self._cached_prediction
        if (
            boosting not in {"gbdt", "gbrt"}
            or cached is None
            or cached[0] > iteration
            or cached[1].shape != (x.shape[0],)
        ):
            values = np.asarray(
                booster.predict(x, num_iteration=iteration, **threads), dtype=np.float64
            )
        elif cached[0] == iteration:
            values = cached[1]
        else:
            start = cached[0]
            delta = booster.predict(
                x, start_iteration=start, num_iteration=iteration - start, **threads
            )
            values = cached[1] + np.asarray(delta, dtype=np.float64)
        self._cached_prediction = (iteration, values)
        return values

    def _run_diagnostics(self, env: Any, iteration: int, *, cross_section: bool) -> dict | None:
        if self.diagnostics is None:
            return None
        try:
            return self.diagnostics.snapshot(
                lambda x: self._incremental_predict(env.model, x, iteration),
                cross_section=cross_section,
                include_action=current_config().console_precision_recall,
            )
        except Exception as exc:  # observation only: never break the fit
            self.diagnostics_errors += 1
            self.emit("DIAGNOSTICS_ERROR", reason=_reason_code(exc), count=self.diagnostics_errors)
            if self.diagnostics_errors >= 3:
                self.diagnostics = None
                self.diagnostics_status = "DISABLED_AFTER_REPEATED_ERRORS"
            return None

    def _monitor_check(
        self, env: Any, iteration: int, metrics: dict[str, dict[str, float]]
    ) -> list[str]:
        """Telemetry records + health flags + continuation console lines. Never raises."""

        try:
            self.check_index += 1
            every = self.monitor_settings
            due = (self.check_index - 1) % every.diagnostics_every_checks == 0
            with_xs = (self.check_index - 1) % every.xs_ic_every_checks == 0
            snapshot = self._run_diagnostics(env, iteration, cross_section=with_xs) if due else None
            resources = sample_resources(self.scope.directory)
            train, validation = metrics.get("train", {}), metrics.get("validation", {})
            rounds_since_best = iteration - self.best_iteration if self.best_iteration else 0
            health = self.health.update(
                iteration=iteration,
                train_rmse=train.get("rmse"),
                validation_rmse=validation.get("rmse"),
                best_validation_rmse=self.best_validation_rmse,
                rounds_since_best=rounds_since_best,
                snapshot=snapshot,
                resources=resources,
            )
            identity = self.scope.identity
            common = {
                "check_id": f"{self.attempt_id}:{iteration}",
                "iteration": iteration,
                "round_limit": env.end_iteration,
                "target": identity.get("target_column"),
                "horizon": identity.get("horizon_minutes"),
                "backend": self.backend_name,
            }
            telemetry = {
                **common,
                "metric_class": METRIC_CLASS_DEVELOPMENT,
                "elapsed_seconds": time.monotonic() - self.started,
                "train_rmse": train.get("rmse"),
                "validation_rmse": validation.get("rmse"),
                "validation_mae": validation.get("mae"),
                "train_l2": train.get("l2"),
                "validation_l2": validation.get("l2"),
                "best_iteration": self.best_iteration or None,
                "best_validation_score": self.best_validation_rmse,
                "best_validation_score_metric": "validation_rmse",
                "rounds_since_best": rounds_since_best,
                "relative_generalization_gap": health["relative_generalization_gap"],
                "learning_rate": self.learning_rate,
                "cpu_threads": self.model_threads,
                "train_rows": self.train_rows,
                "validation_rows": self.validation_rows,
                "feature_count": self.feature_count,
                "rss_bytes": resources["rss_bytes"],
                "effective_memory_available": resources["effective_memory_available"],
                "disk_free_bytes": resources["disk_free_bytes"],
                "health": health,
                "telemetry_status": self.telemetry_status,
                "diagnostics_status": self.diagnostics_status,
            }
            self.emit("TRAINING_TELEMETRY", echo=False, **telemetry)
            if snapshot is not None:
                regression = snapshot["regression"]
                record = {
                    **common,
                    "selection_eligible": False,
                    "independent_evidence": False,
                    "diagnostic_rows": snapshot["diagnostic_rows"],
                    "diagnostic_total_rows": snapshot["diagnostic_total_rows"],
                    "diagnostic_subsampled": snapshot["diagnostic_subsampled"],
                    "diagnostic_seconds": snapshot["diagnostic_seconds"],
                    "target_units": self.diagnostics.target_units if self.diagnostics else None,
                    "validation_pearson": regression["pearson"],
                    "validation_spearman": regression["spearman"],
                    "validation_directional_accuracy": regression["directional_accuracy"],
                    "validation_sample_rmse": regression["rmse"],
                    "validation_sample_mae": regression["mae"],
                    **{
                        key: value
                        for key, value in regression.items()
                        if key.startswith("prediction_") or key == "finite_prediction_fraction"
                    },
                    **snapshot["cross_section"],
                    **snapshot["action"],
                    "metric_class": METRIC_CLASS_DESCRIPTIVE,
                }
                self.emit("VALIDATION_DIAGNOSTICS", echo=False, **record)
            if not current_config().console_table:
                return []
            return format_diagnostic_lines(self._label(), iteration, telemetry, snapshot, health)
        except Exception as exc:  # observation only: never break the fit
            self.telemetry_errors += 1
            with _OUTPUT_LOCK:
                print(
                    f"[fit {self._label()}] MONITOR_ERROR {_reason_code(exc)} at round "
                    f"{iteration}; monitoring skipped for this check, fitting continues",
                    flush=True,
                )
            return []

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
        now = time.monotonic()
        if self.started_at is None:
            self.started_at = now
        # OLD CODE (kept for reference; best-round tracking moved to ``__call__`` so it sees every
        # round instead of only console rounds):
        # if validation_rmse is not None and (
        #     self.best_validation_rmse is None or validation_rmse < self.best_validation_rmse
        # ):
        #     self.best_validation_rmse, self.best_iteration = validation_rmse, iteration
        best_text = (
            "n/a" if self.best_validation_rmse is None else f"{self.best_validation_rmse:.4e}"
        )
        extra = (
            f"best val RMSE {best_text} @ {self.best_iteration} "
            f"(+{iteration - self.best_iteration} since) | "
            f"elapsed {now - self.started_at:.0f}s | {process_stats()}"
        )
        if settings.console_table:
            with _OUTPUT_LOCK:
                print(
                    console_line(
                        self._label(),
                        iteration,
                        round_limit,
                        metrics,
                        flag,
                        extra,
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

    # ------------------------------------------------------------------ end of fit
    def _training_summary(self, estimator: Any) -> dict[str, Any]:
        """Descriptive end-of-fit summary. Never raises; never used for selection."""

        final_snapshot: dict[str, Any] | None = None
        if self.diagnostics is not None:
            try:
                # sklearn's predict() uses the best iteration after early stopping.
                final_snapshot = self.diagnostics.snapshot(
                    lambda x: estimator.predict(
                        x, num_threads=max(1, int(self.model_threads or 1))
                    ),
                    cross_section=True,
                    include_action=current_config().console_precision_recall,
                )
            except Exception as exc:
                self.diagnostics_errors += 1
                self.emit("DIAGNOSTICS_ERROR", reason=_reason_code(exc), phase="FINAL_SNAPSHOT")
        summary = summarize_training_health(
            settings=self.monitor_settings,
            best_validation_rmse=self.best_validation_rmse,
            first_validation_rmse=self.health.first_validation_rmse,
            selected_train_rmse=self.train_rmse_at_best,
            selected_validation_rmse=self.best_validation_rmse,
            zero_baseline_rmse=self.zero_baseline_rmse,
            final_snapshot=final_snapshot,
        )
        summary.update(
            {
                "estimator": self.estimator_key,
                "attempt_id": self.attempt_id,
                "attempt_number": self.attempt_number,
                "log_file": self.path.name,
                "metric_class": METRIC_CLASS_DESCRIPTIVE,
                "selection_eligible": False,
                "best_validation_iteration_observed": self.best_iteration or None,
                "checks_recorded": self.health.checks,
                "flag_counts": dict(self.health.flag_counts),
                "telemetry_status": self.telemetry_status,
                "telemetry_errors": self.telemetry_errors,
                "diagnostics_status": self.diagnostics_status,
                "diagnostics_errors": self.diagnostics_errors,
                "final_snapshot": final_snapshot,
            }
        )
        return json_safe(summary)

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
        summary = self._training_summary(estimator)
        with _OUTPUT_LOCK:
            self.scope.summaries[self.estimator_key] = summary
        self.emit(
            "FIT_FINISHED",
            best_iteration=int(estimator.best_iteration_),
            best_scores=estimator.best_score_,
            last_round=self.last,
            stop_reason=stop_reason,
            training_summary=summary,
            scope_custom_metric_seconds=self.scope.timing.get("custom_metric_seconds"),
            fit_seconds=time.monotonic() - self.started,
        )
        if current_config().console_table:
            with _OUTPUT_LOCK:
                print(
                    f"[fit {self._label()}] FIT_SUMMARY {summary['label']} (heuristic, "
                    f"descriptive; best round {int(estimator.best_iteration_)}, stop "
                    f"{stop_reason}, telemetry {self.telemetry_status}, diagnostics "
                    f"{self.diagnostics_status})",
                    flush=True,
                )

    def fail(self, error: Exception) -> None:
        # Do not copy exception text, input data or credentials into metric logs.
        self.emit(
            "FIT_FAILED",
            error_type=type(error).__name__,
            last_round=self.last,
            telemetry_status=self.telemetry_status,
        )


def fit_observer(estimator_key: str) -> FitMetricObserver | None:
    scope = _SCOPE.get()
    return FitMetricObserver(scope, estimator_key) if scope is not None else None
