from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa

from crypto_ai.phase7.artifacts import atomic_json, resource_snapshot
from crypto_ai.phase7.config import FEATURE_VERSION, TARGET_VERSION, Phase7Config

logger = logging.getLogger(__name__)

OBSERVABILITY_VERSION = "phase7_progress_v1"
_UNAVAILABLE = "N/A"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return _UNAVAILABLE
    remaining = max(0, int(seconds))
    hours, remaining = divmod(remaining, 3_600)
    minutes, seconds = divmod(remaining, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def estimate_remaining_seconds(
    completed: int,
    total: int,
    elapsed_seconds: float,
) -> float | None:
    if completed < 2 or total <= completed or elapsed_seconds <= 0:
        return None
    return elapsed_seconds / completed * (total - completed)


def current_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root.resolve(),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return _UNAVAILABLE
    return result.stdout.strip() or _UNAVAILABLE


def _value(mapping: Mapping[str, Any], *path: str) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _display(value: Any) -> str:
    if value is None:
        return _UNAVAILABLE
    if isinstance(value, float):
        return f"{value:.8g}"
    return str(value)


def oos_trade_summary(trades: pa.Table) -> dict[str, Any]:
    """Describe existing approved OOS trades without changing their calculation."""

    if not trades.num_rows:
        return {
            "trades": 0,
            "long_trades": 0,
            "short_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": None,
            "gross_return_sum": 0.0,
            "total_assumed_cost_return": 0.0,
            "net_return_sum": 0.0,
        }
    direction = [int(value) for value in trades.column("direction").to_pylist()]
    gross = [float(value) for value in trades.column("gross_return").to_pylist()]
    costs = [float(value) / 10_000 for value in trades.column("base_cost_bps").to_pylist()]
    net = [float(value) for value in trades.column("net_return").to_pylist()]
    wins = sum(value > 0 for value in net)
    losses = sum(value < 0 for value in net)
    decided = wins + losses
    return {
        "trades": trades.num_rows,
        "long_trades": sum(value > 0 for value in direction),
        "short_trades": sum(value < 0 for value in direction),
        "wins": wins,
        "losses": losses,
        "win_rate": wins / decided if decided else None,
        "gross_return_sum": sum(gross),
        "total_assumed_cost_return": sum(costs),
        "net_return_sum": sum(net),
    }


def fold_result_payload(
    report: Mapping[str, Any],
    *,
    trade_summary: Mapping[str, Any] | None = None,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Select only metrics already produced by the approved OOS evaluation."""

    spec = report.get("spec") if isinstance(report.get("spec"), Mapping) else {}
    metrics = report.get("test_metrics") if isinstance(report.get("test_metrics"), Mapping) else {}
    economic = report.get("economic") if isinstance(report.get("economic"), Mapping) else {}
    trade_summary = trade_summary or {}
    return {
        "metric_scope": "OUT_OF_SAMPLE_TEST",
        "fold_id": report.get("fold_id"),
        "research_view": report.get("research_view"),
        "model": spec.get("architecture"),
        "experiment": spec.get("name"),
        "target_type": spec.get("target_type"),
        "target_horizon_minutes": spec.get("horizon_minutes"),
        "coins_evaluated": _value(metrics, "coverage", "symbols_covered"),
        "predictions": _value(metrics, "coverage", "oos_rows"),
        "trades": economic.get("trade_count"),
        "long_trades": trade_summary.get("long_trades"),
        "short_trades": trade_summary.get("short_trades"),
        "no_trade_signals": None,
        "wins": trade_summary.get("wins"),
        "losses": trade_summary.get("losses"),
        "win_rate": trade_summary.get("win_rate"),
        "gross_return_sum": trade_summary.get("gross_return_sum"),
        "fees": None,
        "slippage": None,
        "funding": None,
        "total_assumed_cost_return": trade_summary.get("total_assumed_cost_return"),
        "net_return_sum": trade_summary.get("net_return_sum"),
        "expectancy": _value(economic, "fixed_policy_cost_stress", "1.0", "expectancy"),
        "profit_factor": None,
        "sharpe": None,
        "sortino": None,
        "max_drawdown": None,
        "calmar": None,
        "mae": _value(metrics, "micro", "mae"),
        "rmse": _value(metrics, "micro", "rmse"),
        "r2": _value(metrics, "micro", "r2"),
        "directional_accuracy": _value(metrics, "micro", "directional_accuracy"),
        "pearson_ic": _value(metrics, "micro", "pearson_ic"),
        "spearman_ic": _value(metrics, "micro", "spearman_ic"),
        "precision": None,
        "recall": None,
        "f1": None,
        "roc_auc": None,
        "pr_auc": None,
        "brier_score": None,
        "elapsed_seconds": elapsed_seconds,
    }


def _human_block(title: str, rows: Sequence[tuple[str, Any]], *, border: str = "=") -> str:
    line = border * 60
    body = [line, title, line]
    body.extend(f"{label}: {_display(value)}" for label, value in rows)
    body.append(line)
    return "\n".join(body)


class ProgressReporter:
    """Side-effect-only Phase 7 runtime reporting; never participates in science."""

    def __init__(
        self,
        config: Phase7Config,
        *,
        run_identity: str,
        run_started_at: datetime,
        repository_root: Path,
        progress_path: Path | None = None,
        heartbeat_seconds: float = 600.0,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        emit_human: bool = True,
    ) -> None:
        self.config = config
        self.run_identity = run_identity
        self.run_started_at = run_started_at.astimezone(UTC)
        self.repository_root = repository_root.resolve()
        self.progress_path = (
            progress_path or config.paths.artifact_root.resolve() / "progress.json"
        ).resolve()
        self.heartbeat_seconds = heartbeat_seconds
        self._now = now or (lambda: datetime.now(UTC))
        self._monotonic = monotonic or time.monotonic
        self._emit_human = emit_human
        self._stage_started: dict[str, float] = {}
        self._state = self._load_state()
        self._state.update(
            {
                "observability_version": OBSERVABILITY_VERSION,
                "run_identity": run_identity,
                "configuration_hash": config.configuration_hash,
                "code_commit": current_commit(self.repository_root),
                "run_started_at": self.run_started_at.isoformat(),
                "worker_status": "RUNNING",
                "prospective_holdout_status": config.prospective_holdout_status,
                "prospective_holdout_used": config.prospective_holdout_used,
                "july_2026_used": False,
            }
        )
        self._write_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.progress_path.is_file():
            return {"training_started": False, "last_completed_fold": None}
        try:
            payload = json.loads(self.progress_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"training_started": False, "last_completed_fold": None}
        if payload.get("run_identity") != self.run_identity:
            return {"training_started": False, "last_completed_fold": None}
        return dict(payload)

    def _write_state(self) -> None:
        atomic_json(self.progress_path, self._state, immutable=False)

    def emit(
        self,
        event: str,
        *,
        stage: str,
        fields: Mapping[str, Any] | None = None,
        human: str | None = None,
    ) -> dict[str, Any]:
        timestamp = self._now().astimezone(UTC)
        payload = {
            "event": event,
            "observability_version": OBSERVABILITY_VERSION,
            "stage": stage,
            "timestamp_utc": timestamp.isoformat(),
            "run_identity": self.run_identity,
            "configuration_hash": self.config.configuration_hash,
            **dict(fields or {}),
        }
        logger.info("Phase 7 progress event", extra=payload)
        if human and self._emit_human:
            print(human, flush=True)
        self._state.update(
            {
                "stage": stage,
                "last_event": event,
                "last_update": timestamp.isoformat(),
                **dict(fields or {}),
            }
        )
        self._write_state()
        return payload

    def stage_started(self, stage: str, position: int, total: int) -> dict[str, Any]:
        self._stage_started[stage] = self._monotonic()
        return self.emit(
            "phase7_stage_started",
            stage=stage,
            fields={"stage_position": position, "stages_total": total},
            human=_human_block(
                f"PHASE 7 — {stage.upper()} STARTED",
                (
                    ("Stage", f"{position} / {total}"),
                    ("Config hash", self.config.configuration_hash),
                ),
            ),
        )

    def stage_completed(
        self,
        stage: str,
        position: int,
        total: int,
        *,
        metadata: Mapping[str, Any],
        reused: bool = False,
    ) -> dict[str, Any]:
        started = self._stage_started.get(stage)
        elapsed = self._monotonic() - started if started is not None else None
        return self.emit(
            "phase7_stage_completed",
            stage=stage,
            fields={
                "stage_position": position,
                "stages_total": total,
                "elapsed_seconds": elapsed,
                "reused_checkpoint": reused,
                "stage_metadata": dict(metadata),
            },
            human=_human_block(
                f"PHASE 7 — {stage.upper()} COMPLETED",
                (
                    ("Stage", f"{position} / {total}"),
                    ("Elapsed", format_duration(elapsed)),
                    ("Reused", reused),
                ),
            ),
        )

    def progress(
        self,
        *,
        stage: str,
        completed: int,
        total: int,
        current: str,
        interval: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        stride = max(1, total // 100)
        if completed not in {1, total} and completed % stride:
            return None
        started = self._stage_started.get(stage)
        if started is None:
            started = self._monotonic()
            self._stage_started[stage] = started
        elapsed = self._monotonic() - started
        eta = estimate_remaining_seconds(completed, total, elapsed)
        percentage = completed / total * 100 if total else 0.0
        fields = {
            "current_symbol": current,
            "symbols_completed": completed,
            "symbols_total": total,
            "stage_progress": percentage,
            "interval": interval,
            "acquisition_status": status,
            "elapsed_seconds": elapsed,
            "eta_seconds_approximate": eta,
        }
        return self.emit(
            "phase7_progress",
            stage=stage,
            fields=fields,
            human=_human_block(
                f"PHASE 7 — {stage.upper()}",
                (
                    ("Progress", f"{completed} / {total} symbols ({percentage:.1f}%)"),
                    ("Current", current),
                    ("Interval", interval),
                    ("Status", status),
                    ("Elapsed", format_duration(elapsed)),
                    ("ETA (approximate)", format_duration(eta)),
                ),
            ),
        )

    def chunk_progress(
        self,
        *,
        stage: str,
        chunk: int,
        chunks_total: int,
        rows: int,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any]:
        return self.emit(
            "phase7_progress",
            stage=stage,
            fields={
                "chunk": chunk,
                "chunks_total": chunks_total,
                "rows": rows,
                "range_start": start.isoformat(),
                "range_end_exclusive": end.isoformat(),
                "stage_progress": chunk / chunks_total * 100,
            },
        )

    def training_started(
        self,
        *,
        fold_position: int,
        folds_total: int,
        spec: Mapping[str, Any],
        eligible_coins: int,
        train_rows: int,
        validation_rows: int,
        feature_count: int,
        train_start: datetime,
        train_end: datetime,
        validation_start: datetime,
        validation_end: datetime,
    ) -> dict[str, Any] | None:
        if self._state.get("training_started") is True:
            return None
        self._state["training_started"] = True
        fields = {
            "code_commit": self._state["code_commit"],
            "fold": fold_position,
            "folds_total": folds_total,
            "model": spec.get("architecture"),
            "experiment": spec.get("name"),
            "eligible_coins": eligible_coins,
            "training_rows": train_rows,
            "validation_rows": validation_rows,
            "feature_count": feature_count,
            "feature_identity": FEATURE_VERSION,
            "target_identity": TARGET_VERSION,
            "train_start": train_start.isoformat(),
            "train_end": train_end.isoformat(),
            "validation_start": validation_start.isoformat(),
            "validation_end": validation_end.isoformat(),
            "prospective_holdout_status": self.config.prospective_holdout_status,
        }
        return self.emit(
            "phase7_training_started",
            stage="training",
            fields=fields,
            human=_human_block(
                "PHASE 7 MODEL TRAINING STARTED",
                (
                    ("Timestamp", self._now().astimezone(UTC).isoformat()),
                    ("Commit", fields["code_commit"]),
                    ("Config hash", self.config.configuration_hash),
                    ("Model family", fields["model"]),
                    ("Fold", f"{fold_position} / {folds_total}"),
                    ("Eligible coins", eligible_coins),
                    ("Training rows", train_rows),
                    ("Validation rows", validation_rows),
                    ("Features", feature_count),
                    ("Target", TARGET_VERSION),
                    ("Train period", f"{train_start.isoformat()} — {train_end.isoformat()}"),
                    (
                        "Validation period",
                        f"{validation_start.isoformat()} — {validation_end.isoformat()}",
                    ),
                    ("August holdout", self.config.prospective_holdout_status),
                ),
            ),
        )

    def fold_started(
        self,
        *,
        fold_position: int,
        folds_total: int,
        research_view: str,
        eligible_coins: int,
        plan: Any,
    ) -> dict[str, Any]:
        fields = {
            "current_fold": fold_position,
            "folds_total": folds_total,
            "fold_id": plan.fold_id,
            "research_view": research_view,
            "eligible_coins": eligible_coins,
            "train_start": plan.train_start.isoformat(),
            "train_end": plan.train_end.isoformat(),
            "validation_start": plan.validation_start.isoformat(),
            "validation_end": plan.validation_end.isoformat(),
        }
        return self.emit(
            "phase7_fold_started",
            stage="training",
            fields=fields,
            human=_human_block(
                f"PHASE 7 — FOLD {fold_position} / {folds_total}",
                (
                    ("Research view", research_view),
                    ("Eligible coins", eligible_coins),
                    ("Train start", fields["train_start"]),
                    ("Train end", fields["train_end"]),
                    ("Validation start", fields["validation_start"]),
                    ("Validation end", fields["validation_end"]),
                ),
                border="-",
            ),
        )

    @contextmanager
    def model_fit(
        self,
        *,
        fold_position: int,
        folds_total: int,
        spec: Mapping[str, Any],
        feature_count: int,
        train_rows: int,
        validation_rows: int,
    ) -> Iterator[None]:
        started = self._monotonic()
        fields = {
            "current_fold": fold_position,
            "folds_total": folds_total,
            "current_model": spec.get("architecture"),
            "experiment": spec.get("name"),
            "feature_count": feature_count,
            "training_rows": train_rows,
            "validation_rows": validation_rows,
            "status": "model fit active",
        }
        self.emit(
            "phase7_model_fit_started",
            stage="training",
            fields=fields,
            human=_human_block(
                f"PHASE 7 — MODEL FIT — FOLD {fold_position} / {folds_total}",
                (
                    ("Model", fields["current_model"]),
                    ("Experiment", fields["experiment"]),
                    ("Features", feature_count),
                    ("Train rows", train_rows),
                    ("Validation rows", validation_rows),
                    ("Status", fields["status"]),
                ),
                border="-",
            ),
        )
        stopped = threading.Event()

        def heartbeat() -> None:
            while not stopped.wait(self.heartbeat_seconds):
                elapsed = self._monotonic() - started
                resources = resource_snapshot(self.repository_root)
                self.emit(
                    "phase7_training_progress",
                    stage="training",
                    fields={
                        **fields,
                        "fit_elapsed_seconds": elapsed,
                        "total_elapsed_seconds": (
                            self._now().astimezone(UTC) - self.run_started_at
                        ).total_seconds(),
                        "ram_gb": resources.get("ram_gb"),
                        "disk_free_gb": resources.get("disk_free_gb"),
                    },
                    human=_human_block(
                        "[PHASE7 HEARTBEAT]",
                        (
                            ("Stage", "training"),
                            ("Fold", f"{fold_position}/{folds_total}"),
                            ("Model", spec.get("architecture")),
                            ("Status", "model fit active"),
                            ("Fold elapsed", format_duration(elapsed)),
                            ("RAM", resources.get("ram_gb")),
                            ("Disk free GB", resources.get("disk_free_gb")),
                        ),
                    ),
                )

        thread = threading.Thread(target=heartbeat, name="phase7-progress-heartbeat", daemon=True)
        thread.start()
        fit_status = "model fit completed"
        try:
            yield
        except BaseException:
            fit_status = "model fit failed"
            raise
        finally:
            stopped.set()
            thread.join(timeout=min(5.0, self.heartbeat_seconds + 0.1))
            elapsed = self._monotonic() - started
            self.emit(
                (
                    "phase7_model_fit_completed"
                    if fit_status == "model fit completed"
                    else "phase7_model_fit_failed"
                ),
                stage="training",
                fields={**fields, "status": fit_status, "fit_elapsed_seconds": elapsed},
            )

    def fold_evaluation(
        self,
        report: Mapping[str, Any],
        *,
        trade_summary: Mapping[str, Any] | None,
        elapsed_seconds: float | None,
        fold_position: int,
        folds_total: int,
    ) -> dict[str, Any]:
        fields = fold_result_payload(
            report,
            trade_summary=trade_summary,
            elapsed_seconds=elapsed_seconds,
        )
        fields.update({"current_fold": fold_position, "folds_total": folds_total})
        return self.emit(
            "phase7_fold_evaluation",
            stage="evaluation",
            fields=fields,
            human=_human_block(
                f"FOLD {fold_position} / {folds_total} — OUT-OF-SAMPLE RESULTS",
                (
                    ("Metric scope", fields["metric_scope"]),
                    ("Model", fields["model"]),
                    ("Coins evaluated", fields["coins_evaluated"]),
                    ("Predictions", fields["predictions"]),
                    ("Trades", fields["trades"]),
                    ("LONG trades", fields["long_trades"]),
                    ("SHORT trades", fields["short_trades"]),
                    ("NO_TRADE signals", fields["no_trade_signals"]),
                    ("Wins", fields["wins"]),
                    ("Losses", fields["losses"]),
                    ("Win rate", fields["win_rate"]),
                    ("Gross return sum", fields["gross_return_sum"]),
                    ("Fees", fields["fees"]),
                    ("Slippage", fields["slippage"]),
                    ("Funding", fields["funding"]),
                    ("Total assumed cost return", fields["total_assumed_cost_return"]),
                    ("Net return sum", fields["net_return_sum"]),
                    ("Expectancy", fields["expectancy"]),
                    ("Profit factor", fields["profit_factor"]),
                    ("Sharpe", fields["sharpe"]),
                    ("Sortino", fields["sortino"]),
                    ("Maximum drawdown", fields["max_drawdown"]),
                    ("Calmar", fields["calmar"]),
                    ("MAE", fields["mae"]),
                    ("RMSE", fields["rmse"]),
                    ("Directional accuracy", fields["directional_accuracy"]),
                    ("Spearman IC", fields["spearman_ic"]),
                    ("Precision", fields["precision"]),
                    ("Recall", fields["recall"]),
                    ("F1", fields["f1"]),
                    ("ROC-AUC", fields["roc_auc"]),
                    ("PR-AUC", fields["pr_auc"]),
                    ("Brier score", fields["brier_score"]),
                    ("Elapsed", format_duration(elapsed_seconds)),
                ),
            ),
        )

    def fold_completed(self, fold_position: int, folds_total: int, fold_id: str) -> None:
        self._state["last_completed_fold"] = fold_id
        self.emit(
            "phase7_progress",
            stage="training",
            fields={
                "current_fold": fold_position,
                "folds_total": folds_total,
                "last_completed_fold": fold_id,
                "stage_progress": fold_position / folds_total * 100,
            },
        )

    def training_completed(self, summary: Mapping[str, Any]) -> dict[str, Any]:
        return self.emit(
            "phase7_training_completed",
            stage="training",
            fields={
                "folds_total": summary.get("fold_count"),
                "completed_reports": summary.get("completed_reports"),
                "ineligible_reports": summary.get("ineligible_reports"),
            },
        )

    def final_summary(
        self,
        report: Mapping[str, Any],
        training: Mapping[str, Any],
        *,
        report_path: Path,
    ) -> dict[str, Any]:
        complete_reports = [
            item for item in training.get("reports", []) if item.get("status") == "COMPLETE"
        ]
        fold_ids = sorted({str(item["fold_id"]) for item in complete_reports})
        eligible_counts = [
            len(
                set(item.get("core_eligible_symbols", []))
                | set(item.get("expansion_eligible_symbols", []))
            )
            for item in complete_reports
        ]
        feature_counts = sorted(
            {
                len(item["same_row_feature_columns"])
                for item in complete_reports
                if isinstance(item.get("same_row_feature_columns"), list)
            }
        )
        fields = {
            "code_commit": self._state["code_commit"],
            "feature_identity": FEATURE_VERSION,
            "feature_count": max(feature_counts) if feature_counts else None,
            "feature_counts_observed": feature_counts,
            "target_identity": TARGET_VERSION,
            "folds_completed": training.get("completed_fold_count"),
            "fold_range": f"{fold_ids[0]} — {fold_ids[-1]}" if fold_ids else None,
            "eligible_symbol_count_min": min(eligible_counts) if eligible_counts else None,
            "eligible_symbol_count_max": max(eligible_counts) if eligible_counts else None,
            "scorecard_rows": len(report.get("scorecard", [])),
            "total_evaluated_trades": None,
            "gross_pnl": None,
            "fees": None,
            "slippage": None,
            "funding": None,
            "net_pnl": None,
            "win_rate": None,
            "profit_factor": None,
            "expectancy": None,
            "sharpe": None,
            "sortino": None,
            "max_drawdown": None,
            "calmar": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "roc_auc": None,
            "pr_auc": None,
            "brier_score": None,
            "best_fold": None,
            "worst_fold": None,
            "qualification_performed": report.get("model_qualification_performed"),
            "qualified_model": report.get("qualified_model"),
            "july_2026_used": report.get("july_2026_used"),
            "prospective_holdout_status": report.get("prospective_holdout_status"),
            "prospective_holdout_used": report.get("prospective_holdout_used"),
            "report_artifact": str(report_path.resolve()),
        }
        self._state["worker_status"] = "COMPLETE"
        return self.emit(
            "phase7_final_summary",
            stage="complete",
            fields=fields,
            human=_human_block(
                "PHASE 7 COMPLETE",
                (
                    ("Code commit", fields["code_commit"]),
                    ("Config hash", self.config.configuration_hash),
                    ("Target", TARGET_VERSION),
                    ("Features (max actual)", fields["feature_count"]),
                    ("Folds completed", fields["folds_completed"]),
                    ("Fold range", fields["fold_range"]),
                    (
                        "Eligible coins per evaluated report",
                        (
                            f"{fields['eligible_symbol_count_min']} — "
                            f"{fields['eligible_symbol_count_max']}"
                            if fields["eligible_symbol_count_min"] is not None
                            else None
                        ),
                    ),
                    ("Total evaluated trades", fields["total_evaluated_trades"]),
                    ("Gross PnL", fields["gross_pnl"]),
                    ("Fees", fields["fees"]),
                    ("Slippage", fields["slippage"]),
                    ("Funding", fields["funding"]),
                    ("NET PnL", fields["net_pnl"]),
                    ("Win rate", fields["win_rate"]),
                    ("Profit factor", fields["profit_factor"]),
                    ("Expectancy", fields["expectancy"]),
                    ("Sharpe", fields["sharpe"]),
                    ("Sortino", fields["sortino"]),
                    ("Maximum drawdown", fields["max_drawdown"]),
                    ("Calmar", fields["calmar"]),
                    ("Precision", fields["precision"]),
                    ("Recall", fields["recall"]),
                    ("F1", fields["f1"]),
                    ("ROC-AUC", fields["roc_auc"]),
                    ("PR-AUC", fields["pr_auc"]),
                    ("Brier score", fields["brier_score"]),
                    ("Best fold", fields["best_fold"]),
                    ("Worst fold", fields["worst_fold"]),
                    ("Qualification performed", fields["qualification_performed"]),
                    ("Qualified model", fields["qualified_model"]),
                    ("July 2026 used", fields["july_2026_used"]),
                    ("August holdout status", fields["prospective_holdout_status"]),
                    ("August holdout used", fields["prospective_holdout_used"]),
                    ("Artifacts", fields["report_artifact"]),
                ),
            ),
        )
