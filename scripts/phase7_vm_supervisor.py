#!/usr/bin/env python3
"""Cost-aware supervisor for the manually authorized Phase 7 VM batch run.

The supervisor is deliberately not a boot service. A BLOCKED marker prevents a
manual supervisor invocation from starting Phase 7, so the VM can be started
for diagnosis with the research worker stopped.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Any

SESSION = "phase7-auto"
SUPERVISOR_VERSION = "phase7_vm_supervisor_v1_1_1"
EXPECTED_CLOUD_ROOT = "gs://crypto-ai-data-83921/artifacts/phase7"
EXPECTED_CONFIG_HASH = "cc550337f1f4ee4654124bf6"
INTERRUPTION_EXIT_CODES = frozenset({129, 130, 143})


class SupervisorStatus(StrEnum):
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    BUDGET_STOPPED = "BUDGET_STOPPED"


class BudgetLevel(StrEnum):
    NORMAL = "NORMAL"
    SOFT_WARNING = "SOFT_WARNING"
    PROJECTED_LIMIT = "PROJECTED_LIMIT"
    HARD_STOP = "HARD_STOP"


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    baseline_inr: Decimal
    baseline_at: datetime
    hourly_inr: Decimal
    soft_inr: Decimal
    projected_inr: Decimal
    hard_inr: Decimal
    actual_inr: Decimal | None = None

    @classmethod
    def from_environment(cls) -> BudgetPolicy:
        names = {
            "baseline_inr": "PHASE7_BUDGET_BASELINE_INR",
            "baseline_at": "PHASE7_BUDGET_BASELINE_AT_UTC",
            "hourly_inr": "PHASE7_BUDGET_HOURLY_INR",
            "soft_inr": "PHASE7_BUDGET_SOFT_INR",
            "projected_inr": "PHASE7_BUDGET_PROJECTED_INR",
            "hard_inr": "PHASE7_BUDGET_HARD_INR",
        }
        missing = [environment for environment in names.values() if not os.getenv(environment)]
        if missing:
            raise ValueError(f"Missing required Phase 7 budget settings: {', '.join(missing)}")
        try:
            baseline_at = datetime.fromisoformat(os.environ[names["baseline_at"]])
            if baseline_at.tzinfo is None:
                raise ValueError("budget baseline timestamp must include a UTC offset")
            values = {
                name: Decimal(os.environ[environment])
                for name, environment in names.items()
                if name != "baseline_at"
            }
            supplied_actual = os.getenv("PHASE7_ACTUAL_BILLING_INR", "").strip()
            actual = Decimal(supplied_actual) if supplied_actual else None
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid Phase 7 budget setting: {exc}") from exc
        policy = cls(
            baseline_at=baseline_at.astimezone(UTC),
            actual_inr=actual,
            **values,
        )
        if not (
            Decimal("0")
            <= policy.baseline_inr
            < policy.soft_inr
            < policy.projected_inr
            < policy.hard_inr
        ):
            raise ValueError("Phase 7 budget thresholds must be strictly increasing")
        if policy.hourly_inr <= 0 or (actual is not None and actual < 0):
            raise ValueError("Phase 7 budget rates and actual billing must be non-negative")
        return policy

    def snapshot(self, now: datetime) -> dict[str, Any]:
        elapsed_seconds = max(
            Decimal("0"),
            Decimal(str((now.astimezone(UTC) - self.baseline_at).total_seconds())),
        )
        elapsed_hours = elapsed_seconds / Decimal("3600")
        estimate = self.baseline_inr + elapsed_hours * self.hourly_inr
        effective = max(estimate, self.actual_inr or Decimal("0"))
        if effective >= self.hard_inr:
            level = BudgetLevel.HARD_STOP
        elif effective >= self.projected_inr:
            level = BudgetLevel.PROJECTED_LIMIT
        elif effective >= self.soft_inr:
            level = BudgetLevel.SOFT_WARNING
        else:
            level = BudgetLevel.NORMAL
        source = (
            "CONSERVATIVE_ESTIMATE"
            if self.actual_inr is None
            else "MAX_OF_ACTUAL_AND_CONSERVATIVE_ESTIMATE"
        )
        return {
            "source": source,
            "level": level.value,
            "baseline_spend_inr": float(self.baseline_inr),
            "baseline_at_utc": self.baseline_at.isoformat(),
            "conservative_hourly_inr": float(self.hourly_inr),
            "elapsed_hours": round(float(elapsed_hours), 4),
            "estimated_spend_inr": round(float(estimate), 2),
            "actual_billing_inr": (float(self.actual_inr) if self.actual_inr is not None else None),
            "effective_spend_inr": round(float(effective), 2),
            "soft_warning_inr": float(self.soft_inr),
            "projected_limit_inr": float(self.projected_inr),
            "hard_stop_inr": float(self.hard_inr),
        }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


@dataclass(frozen=True, slots=True)
class SupervisorPaths:
    repository: Path

    @property
    def artifact_root(self) -> Path:
        return self.repository / "local_artifacts/phase7"

    @property
    def supervisor_root(self) -> Path:
        return self.artifact_root / "supervisor"

    @property
    def state(self) -> Path:
        return self.supervisor_root / "state.json"

    @property
    def blocked(self) -> Path:
        return self.supervisor_root / "BLOCKED.json"

    @property
    def progress(self) -> Path:
        return self.artifact_root / "progress.json"

    @property
    def worker_exit(self) -> Path:
        return self.supervisor_root / "worker-exit-code"

    @property
    def worker_script(self) -> Path:
        return self.repository / "scripts/run_phase7_worker.sh"

    @property
    def run_log(self) -> Path:
        return self.repository / "local_artifacts/phase7-cloud-run.log"


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class Phase7VmSupervisor:
    def __init__(
        self,
        repository: Path,
        *,
        poll_seconds: float = 30.0,
        run_command: RunCommand = subprocess.run,
        sleeper: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
        budget_policy: BudgetPolicy | None = None,
    ) -> None:
        self.paths = SupervisorPaths(repository.resolve())
        self.poll_seconds = poll_seconds
        self._run = run_command
        self._sleep = sleeper
        self._now = now or (lambda: datetime.now(UTC))
        self.budget_policy = budget_policy

    def _timestamp(self) -> str:
        return self._now().astimezone(UTC).isoformat()

    def _command(
        self,
        args: Sequence[str],
        *,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        return self._run(
            list(args),
            cwd=self.paths.repository,
            check=check,
            capture_output=True,
            text=True,
        )

    def _state(self, status: SupervisorStatus, **fields: Any) -> dict[str, Any]:
        payload = {
            "supervisor_version": SUPERVISOR_VERSION,
            "status": status.value,
            "updated_at": self._timestamp(),
            "session": SESSION,
            "configuration_hash": EXPECTED_CONFIG_HASH,
            **fields,
        }
        _atomic_json(self.paths.state, payload)
        return payload

    def _tmux_exists(self) -> bool:
        return self._command(("tmux", "has-session", "-t", SESSION)).returncode == 0

    def _worker_pids(self) -> tuple[str, ...]:
        result = self._command(("pgrep", "-f", "[c]rypto-ai phase7-research"))
        if result.returncode not in {0, 1}:
            raise RuntimeError(f"pgrep failed: {result.stderr.strip()}")
        return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())

    def _process_session_id(self, pid: str) -> str | None:
        result = self._command(("ps", "-o", "sid=", "-p", pid))
        if result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value or None

    def _session_contains_workers(self, worker_pids: Sequence[str]) -> bool:
        panes = self._command(("tmux", "list-panes", "-t", SESSION, "-F", "#{pane_pid}"))
        if panes.returncode != 0:
            return False
        pane_pids = tuple(line.strip() for line in panes.stdout.splitlines() if line.strip())
        pane_sessions = {
            session_id
            for pane_pid in pane_pids
            if (session_id := self._process_session_id(pane_pid)) is not None
        }
        return bool(pane_sessions) and all(
            self._process_session_id(pid) in pane_sessions for pid in worker_pids
        )

    def _git_head(self) -> str | None:
        result = self._command(("git", "rev-parse", "HEAD"))
        return result.stdout.strip() if result.returncode == 0 else None

    def _archive_stale_exit(self) -> None:
        if not self.paths.worker_exit.exists():
            return
        history = self.paths.supervisor_root / "history"
        history.mkdir(parents=True, exist_ok=True)
        stamp = self._timestamp().replace(":", "").replace("+00:00", "Z")
        os.replace(self.paths.worker_exit, history / f"worker-exit-{stamp}.txt")

    def _start_worker(self, cloud_root: str) -> None:
        if self._tmux_exists() or self._worker_pids():
            raise RuntimeError("Refusing to start a duplicate Phase 7 worker")
        self._archive_stale_exit()
        self.paths.supervisor_root.mkdir(parents=True, exist_ok=True)
        command = (
            f"env PHASE7_ALLOW_CLOUD_RESEARCH=1 "
            f"PHASE7_CLOUD_STORAGE_ROOT={cloud_root} "
            f"/bin/bash {self.paths.worker_script}"
        )
        self._command(
            (
                "tmux",
                "new-session",
                "-d",
                "-s",
                SESSION,
                "-c",
                str(self.paths.repository),
                command,
            ),
            check=True,
        )

    def _progress(self) -> dict[str, Any] | None:
        return _read_json(self.paths.progress)

    def _latest_checkpoint(self) -> dict[str, Any] | None:
        root = self.paths.repository / "local_artifacts/phase7/checkpoints"
        if not root.is_dir():
            return None
        candidates = sorted(
            (path for path in root.rglob("*.json") if path.is_file()),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        for path in candidates:
            payload = _read_json(path)
            if payload is None:
                continue
            return {
                "path": str(path.resolve()),
                "run_identity": payload.get("run_identity"),
                "stage": payload.get("stage"),
                "status": payload.get("status"),
                "completed_at": payload.get("completed_at"),
                "checkpoint_hash": payload.get("checkpoint_hash"),
            }
        return None

    def _runtime_metadata(self, worker_pids: Sequence[str] | None = None) -> dict[str, Any]:
        progress = self._progress()
        pids = tuple(worker_pids) if worker_pids is not None else self._worker_pids()
        return {
            "git_head": self._git_head(),
            "worker_pids": list(pids),
            "stage": (progress or {}).get("stage"),
            "current_symbol": (progress or {}).get("current_symbol"),
            "current_fold": (progress or {}).get("current_fold"),
            "current_model": (progress or {}).get("current_model"),
            "last_completed_fold": (progress or {}).get("last_completed_fold"),
            "progress_artifact": str(self.paths.progress.resolve()),
            "progress": progress,
            "checkpoint_identity": self._latest_checkpoint(),
            "prospective_holdout_status": (progress or {}).get("prospective_holdout_status"),
            "prospective_holdout_used": (progress or {}).get("prospective_holdout_used"),
            "prospective_holdout_evaluation_authorized": False,
            "july_2026_used": (progress or {}).get("july_2026_used"),
            "budget": self._budget_snapshot(),
        }

    def _budget_snapshot(self) -> dict[str, Any] | None:
        if self.budget_policy is None:
            return None
        return self.budget_policy.snapshot(self._now())

    def _recent_evidence(self, relative: str, limit: int = 20) -> list[str]:
        root = self.paths.repository / relative
        if not root.is_dir():
            return []
        files = sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.stat().st_mtime_ns,
            reverse=True,
        )
        return [str(path.resolve()) for path in files[:limit]]

    def _diagnostic_payload(self, reason: str, exit_code: int | None) -> dict[str, Any]:
        status = self._command(("git", "status", "--short"))
        disk = shutil.disk_usage(self.paths.repository)
        log_tail: list[str] = []
        if self.paths.run_log.is_file():
            with self.paths.run_log.open(encoding="utf-8", errors="replace") as handle:
                log_tail = handle.readlines()[-200:]
        progress = self._progress()
        error_summary = [
            line.rstrip("\n")
            for line in log_tail
            if "Traceback" in line or "ERROR" in line or "Error" in line
        ][-50:]
        return {
            "supervisor_version": SUPERVISOR_VERSION,
            "status": SupervisorStatus.BLOCKED.value,
            "blocked_at": self._timestamp(),
            "reason": reason,
            "worker_exit_code": exit_code,
            "git_head": self._git_head(),
            "git_status": status.stdout.splitlines(),
            "stage": (progress or {}).get("stage"),
            "current_symbol": (progress or {}).get("current_symbol"),
            "current_fold": (progress or {}).get("current_fold"),
            "progress": progress,
            "progress_artifact": str(self.paths.progress.resolve()),
            "checkpoint_identity": self._latest_checkpoint(),
            "last_checkpoints": self._recent_evidence("local_artifacts/phase7/checkpoints"),
            "quality_evidence": self._recent_evidence("data/phase7/quality"),
            "quarantine_evidence": self._recent_evidence("data/phase7/quarantine"),
            "reconciliation_evidence": self._recent_evidence("data/phase7/reconciliation"),
            "run_log": str(self.paths.run_log.resolve()),
            "run_log_tail": [line.rstrip("\n") for line in log_tail],
            "error_summary": error_summary,
            "prospective_holdout_status": (progress or {}).get("prospective_holdout_status"),
            "prospective_holdout_used": (progress or {}).get("prospective_holdout_used"),
            "prospective_holdout_evaluation_authorized": False,
            "july_2026_used": (progress or {}).get("july_2026_used"),
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
            "raw_evidence_mutated": False,
        }

    def _mark_blocked(self, reason: str, exit_code: int | None) -> dict[str, Any]:
        payload = self._diagnostic_payload(reason, exit_code)
        stamp = payload["blocked_at"].replace(":", "").replace("+00:00", "Z")
        diagnostic = self.paths.supervisor_root / "diagnostics" / f"blocked-{stamp}.json"
        _atomic_json(diagnostic, payload)
        marker = payload | {"diagnostic": str(diagnostic.resolve())}
        _atomic_json(self.paths.blocked, marker)
        return self._state(
            SupervisorStatus.BLOCKED,
            failure_timestamp=payload["blocked_at"],
            reason=reason,
            worker_exit_code=exit_code,
            git_head=payload["git_head"],
            stage=payload["stage"],
            current_symbol=payload["current_symbol"],
            current_fold=payload["current_fold"],
            checkpoint_identity=payload["checkpoint_identity"],
            error_summary=payload["error_summary"],
            quality_evidence=payload["quality_evidence"],
            quarantine_evidence=payload["quarantine_evidence"],
            reconciliation_evidence=payload["reconciliation_evidence"],
            run_log=payload["run_log"],
            prospective_holdout_status=payload["prospective_holdout_status"],
            prospective_holdout_used=payload["prospective_holdout_used"],
            prospective_holdout_evaluation_authorized=False,
            july_2026_used=payload["july_2026_used"],
            diagnostic=str(diagnostic.resolve()),
            worker_started=False,
        )

    def _shutdown(self) -> None:
        flush = self._command(("sync",))
        if flush.returncode != 0:
            raise RuntimeError("Filesystem flush failed; refusing to shut down VM")
        result = self._command(("sudo", "-n", "shutdown", "-h", "now"))
        if result.returncode != 0:
            current = _read_json(self.paths.state) or {}
            current["shutdown_error"] = result.stderr.strip() or "shutdown command failed"
            current["shutdown_requested_at"] = self._timestamp()
            _atomic_json(self.paths.state, current)
            raise RuntimeError("VM shutdown command failed")

    def _budget_stop(
        self,
        reason: str,
        budget: dict[str, Any],
        worker_pids: Sequence[str],
    ) -> int:
        fields = {
            "budget_stopped_at": self._timestamp(),
            "reason": reason,
            "worker_stop_requested": bool(worker_pids),
            **self._runtime_metadata(worker_pids),
            "budget": budget,
        }
        self._state(SupervisorStatus.BUDGET_STOPPED, **fields)
        forced = False
        if self._tmux_exists():
            self._command(("tmux", "send-keys", "-t", SESSION, "C-c"))
            for _ in range(12):
                if not self._tmux_exists():
                    break
                self._sleep(5.0)
            if self._tmux_exists():
                self._command(("tmux", "kill-session", "-t", SESSION))
                forced = True
        exit_code = self._read_exit_code() if worker_pids else None
        self._state(
            SupervisorStatus.BUDGET_STOPPED,
            worker_stop_forced=forced,
            worker_exit_code=exit_code,
            **fields,
        )
        self._shutdown()
        return 5

    def _backup(self, cloud_root: str) -> tuple[dict[str, str], ...]:
        sources = (
            (self.paths.artifact_root, f"{cloud_root}/local_artifacts"),
            (self.paths.repository / "data/gold/phase7", f"{cloud_root}/gold"),
            (self.paths.repository / "data/phase7", f"{cloud_root}/data"),
        )
        records: list[dict[str, str]] = []
        for source, destination in sources:
            if not source.exists():
                continue
            self._command(
                (
                    "gcloud",
                    "storage",
                    "rsync",
                    "--recursive",
                    str(source.resolve()),
                    destination,
                ),
                check=True,
            )
            records.append({"source": str(source.resolve()), "destination": destination})
        self._command(("gcloud", "storage", "ls", "--recursive", f"{cloud_root}/**"), check=True)
        return tuple(records)

    def _read_exit_code(self) -> int | None:
        for _ in range(10):
            if self.paths.worker_exit.is_file():
                try:
                    return int(self.paths.worker_exit.read_text(encoding="ascii").strip())
                except (OSError, ValueError):
                    return None
            self._sleep(0.5)
        return None

    def _finish(self, exit_code: int | None, cloud_root: str) -> int:
        progress = self._progress()
        if exit_code in INTERRUPTION_EXIT_CODES:
            payload = self._diagnostic_payload(
                "intentional_or_infrastructure_interruption", exit_code
            )
            stamp = payload["blocked_at"].replace(":", "").replace("+00:00", "Z")
            interruption = (
                self.paths.supervisor_root / "interruptions" / f"interruption-{stamp}.json"
            )
            payload["status"] = "INTERRUPTED"
            _atomic_json(interruption, payload)
            self._state(
                SupervisorStatus.READY,
                reason="intentional_or_infrastructure_interruption",
                worker_exit_code=exit_code,
                interruption=str(interruption.resolve()),
                worker_started=False,
                resume_safe=True,
            )
            return 130
        complete = bool(
            exit_code == 0
            and progress
            and progress.get("worker_status") == "COMPLETE"
            and progress.get("stage") == "complete"
            and progress.get("last_event") == "phase7_final_summary"
            and progress.get("configuration_hash") == EXPECTED_CONFIG_HASH
            and progress.get("code_commit") == self._git_head()
            and progress.get("prospective_holdout_status") == "LOCKED_UNUSED"
            and progress.get("prospective_holdout_used") is False
            and progress.get("july_2026_used") is False
        )
        if not complete:
            reason = (
                f"worker_exit_{exit_code}"
                if exit_code not in {None, 0}
                else "worker_exited_without_proven_phase7_completion"
            )
            self._mark_blocked(reason, exit_code)
            self._shutdown()
            return 2
        completion_fields = {
            "completed_at": self._timestamp(),
            "worker_exit_code": exit_code,
            "final_commit": self._git_head(),
            "completion_status": "PROVEN_COMPLETE",
            "progress": progress,
            "progress_artifact": str(self.paths.progress.resolve()),
            "final_report_artifact": progress.get("report_artifact"),
            "last_checkpoint": self._latest_checkpoint(),
            "prospective_holdout_status": progress.get("prospective_holdout_status"),
            "prospective_holdout_used": progress.get("prospective_holdout_used"),
            "prospective_holdout_evaluation_authorized": False,
            "july_2026_used": progress.get("july_2026_used"),
            "worker_started": False,
        }
        self._state(
            SupervisorStatus.COMPLETED,
            backups_pending=True,
            **completion_fields,
        )
        try:
            backups = self._backup(cloud_root)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            self._mark_blocked(f"completion_backup_failed: {exc}", exit_code)
            self._shutdown()
            return 2
        self._state(
            SupervisorStatus.COMPLETED,
            backups_pending=False,
            backups=list(backups),
            **completion_fields,
        )
        self._shutdown()
        return 0

    def supervise(self, cloud_root: str) -> int:
        if cloud_root != EXPECTED_CLOUD_ROOT:
            raise ValueError(f"Unexpected Phase 7 cloud root: {cloud_root}")
        existing_state = _read_json(self.paths.state) or {}
        if self.paths.blocked.exists():
            if existing_state.get("status") != SupervisorStatus.BLOCKED.value:
                marker = _read_json(self.paths.blocked) or {}
                self._state(
                    SupervisorStatus.BLOCKED,
                    failure_timestamp=marker.get("blocked_at"),
                    reason=marker.get("reason", "existing BLOCKED marker"),
                    diagnostic=marker.get("diagnostic"),
                    worker_started=False,
                )
            return 3
        if existing_state.get("status") == SupervisorStatus.BLOCKED.value:
            return 3
        if existing_state.get("status") == SupervisorStatus.COMPLETED.value:
            return 4
        if existing_state.get("status") == SupervisorStatus.BUDGET_STOPPED.value:
            existing = self._tmux_exists()
            pids = self._worker_pids()
            if existing or pids:
                budget = existing_state.get("budget") or self._budget_snapshot() or {}
                return self._budget_stop(
                    "existing_budget_stop_enforced",
                    budget,
                    pids,
                )
            return 5

        existing = self._tmux_exists()
        pids = self._worker_pids()
        if existing:
            if len(pids) != 1 or not self._session_contains_workers(pids):
                self._command(("tmux", "kill-session", "-t", SESSION))
                self._mark_blocked(
                    "existing session does not contain exactly one owned worker", None
                )
                self._shutdown()
                return 2
        elif pids:
            self._mark_blocked("orphan Phase 7 worker exists outside phase7-auto", None)
            self._shutdown()
            return 2
        budget = self._budget_snapshot()
        if budget and (
            budget["level"] == BudgetLevel.HARD_STOP.value
            or (not existing and budget["level"] == BudgetLevel.PROJECTED_LIMIT.value)
        ):
            reason = (
                "hard_budget_threshold_reached"
                if budget["level"] == BudgetLevel.HARD_STOP.value
                else "preflight_projected_budget_limit_reached"
            )
            return self._budget_stop(reason, budget, pids)
        if not existing:
            self._start_worker(cloud_root)

        self._state(
            SupervisorStatus.RUNNING,
            worker_started=True,
            existing_worker=existing,
            cloud_storage_root=cloud_root,
            **self._runtime_metadata(pids if existing else ()),
        )
        previous_stage = (self._progress() or {}).get("stage")
        while self._tmux_exists():
            pids = self._worker_pids()
            if len(pids) > 1 or (len(pids) == 1 and not self._session_contains_workers(pids)):
                self._command(("tmux", "kill-session", "-t", SESSION))
                reason = (
                    "duplicate Phase 7 workers detected"
                    if len(pids) > 1
                    else "Phase 7 worker is not owned by phase7-auto"
                )
                self._mark_blocked(reason, None)
                self._shutdown()
                return 2
            progress = self._progress() or {}
            current_stage = progress.get("stage")
            budget = self._budget_snapshot()
            new_expensive_stage = current_stage != previous_stage and current_stage in {
                "data",
                "gold",
                "train",
                "training",
            }
            if budget and (
                budget["level"] == BudgetLevel.HARD_STOP.value
                or (budget["level"] == BudgetLevel.PROJECTED_LIMIT.value and new_expensive_stage)
            ):
                reason = (
                    "hard_budget_threshold_reached"
                    if budget["level"] == BudgetLevel.HARD_STOP.value
                    else f"projected_budget_limit_before_{current_stage}"
                )
                return self._budget_stop(reason, budget, pids)
            self._state(
                SupervisorStatus.RUNNING,
                worker_started=True,
                cloud_storage_root=cloud_root,
                **self._runtime_metadata(pids),
            )
            previous_stage = current_stage
            self._sleep(self.poll_seconds)
        return self._finish(self._read_exit_code(), cloud_root)

    def clear_blocked(self, reason: str) -> dict[str, Any]:
        if self._tmux_exists() or self._worker_pids():
            raise RuntimeError("Cannot clear BLOCKED while a Phase 7 worker exists")
        if not reason.strip():
            raise ValueError("Clearing BLOCKED requires an audit reason")
        marker = _read_json(self.paths.blocked)
        if marker is None:
            return self._state(
                SupervisorStatus.READY,
                clear_reason=reason,
                worker_started=False,
            )
        cleared = self.paths.supervisor_root / "cleared"
        cleared.mkdir(parents=True, exist_ok=True)
        stamp = self._timestamp().replace(":", "").replace("+00:00", "Z")
        destination = cleared / f"BLOCKED-{stamp}.json"
        os.replace(self.paths.blocked, destination)
        return self._state(
            SupervisorStatus.READY,
            clear_reason=reason,
            cleared_marker=str(destination.resolve()),
            worker_started=False,
        )

    def clear_budget_stopped(self, reason: str) -> dict[str, Any]:
        if self._tmux_exists() or self._worker_pids():
            raise RuntimeError("Cannot clear BUDGET_STOPPED while a Phase 7 worker exists")
        if not reason.strip():
            raise ValueError("Clearing BUDGET_STOPPED requires an audit reason")
        state = _read_json(self.paths.state) or {}
        if state.get("status") != SupervisorStatus.BUDGET_STOPPED.value:
            raise RuntimeError("Current supervisor state is not BUDGET_STOPPED")
        cleared = self.paths.supervisor_root / "cleared"
        stamp = self._timestamp().replace(":", "").replace("+00:00", "Z")
        archived = cleared / f"BUDGET_STOPPED-{stamp}.json"
        _atomic_json(archived, state)
        return self._state(
            SupervisorStatus.READY,
            clear_reason=reason,
            cleared_budget_state=str(archived.resolve()),
            worker_started=False,
        )

    def status(self) -> dict[str, Any]:
        return {
            "state": _read_json(self.paths.state),
            "blocked": _read_json(self.paths.blocked),
            "tmux_session_exists": self._tmux_exists(),
            "worker_pids": list(self._worker_pids()),
            "progress": self._progress(),
            "budget": self._budget_snapshot(),
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("supervise", "status", "clear-blocked", "clear-budget-stop"),
    )
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--reason", default="")
    return parser


def main() -> int:
    args = _parser().parse_args()
    budget_policy = BudgetPolicy.from_environment() if args.command == "supervise" else None
    supervisor = Phase7VmSupervisor(
        args.repository,
        poll_seconds=args.poll_seconds,
        budget_policy=budget_policy,
    )
    if args.command == "status":
        print(json.dumps(supervisor.status(), indent=2, sort_keys=True, default=str))
        return 0
    if args.command == "clear-blocked":
        print(
            json.dumps(
                supervisor.clear_blocked(args.reason),
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    if args.command == "clear-budget-stop":
        print(
            json.dumps(
                supervisor.clear_budget_stopped(args.reason),
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
        return 0
    cloud_root = os.environ.get("PHASE7_CLOUD_STORAGE_ROOT", "").strip()
    return supervisor.supervise(cloud_root)


if __name__ == "__main__":
    raise SystemExit(main())
