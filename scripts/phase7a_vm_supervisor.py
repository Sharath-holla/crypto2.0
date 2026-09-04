#!/usr/bin/env python3
"""Phase 7A wrapper with an immutable 24-hour wall-clock authority."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts import phase7_vm_supervisor as base

SESSION = "phase7a-core20-primary"
EXPECTED_CONFIG_HASH = "93f987736b1a79d26b773957"
SUPERVISOR_VERSION = "phase7a_vm_supervisor_v1"
GRACEFUL_STOP_AFTER = timedelta(hours=23, minutes=44, seconds=30)
HARD_CAP = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class Phase7APaths(base.SupervisorPaths):
    @property
    def supervisor_root(self) -> Path:
        return self.artifact_root / "supervisor-phase7a"

    @property
    def progress(self) -> Path:
        return self.artifact_root / "progress.json"

    @property
    def worker_script(self) -> Path:
        return self.repository / "scripts/run_phase7a_worker.sh"

    @property
    def run_log(self) -> Path:
        return self.repository / "local_artifacts/phase7a-core20-primary-run.log"


@dataclass(frozen=True, slots=True)
class WallClockPolicy:
    launched_at: datetime

    def snapshot(self, now: datetime) -> dict[str, Any]:
        elapsed = max(timedelta(0), now.astimezone(UTC) - self.launched_at.astimezone(UTC))
        level = (
            base.BudgetLevel.HARD_STOP
            if elapsed >= GRACEFUL_STOP_AFTER
            else base.BudgetLevel.NORMAL
        )
        return {
            "source": "AUTHORIZED_PHASE7A_WALL_CLOCK",
            "level": level.value,
            "authorized_launch_at": self.launched_at.astimezone(UTC).isoformat(),
            "elapsed_seconds": elapsed.total_seconds(),
            "graceful_stop_after_seconds": GRACEFUL_STOP_AFTER.total_seconds(),
            "hard_cap_seconds": HARD_CAP.total_seconds(),
        }


class Phase7ASupervisor(base.Phase7VmSupervisor):
    def __init__(self, repository: Path, **kwargs: Any) -> None:
        super().__init__(
            repository,
            session=SESSION,
            expected_config_hash=EXPECTED_CONFIG_HASH,
            supervisor_version=SUPERVISOR_VERSION,
            **kwargs,
        )
        self.paths = Phase7APaths(repository.resolve())

    @staticmethod
    def _is_worker_command(command: str) -> bool:
        return base.Phase7VmSupervisor._is_worker_command(command) or (
            "run_phase7a_pipeline.py" in command
        )

    def _finish(self, exit_code: int | None, cloud_root: str) -> int:
        if exit_code == 75:
            workers = self._worker_snapshot()
            return self._budget_stop(
                "phase7a_feasibility_gate_projected_over_24h",
                self._budget_snapshot() or {},
                workers,
            )
        return super()._finish(exit_code, cloud_root)


def _runtime_authority(paths: Phase7APaths, *, create: bool) -> datetime | None:
    path = paths.supervisor_root / "runtime-authority.json"
    payload = base._read_json(path)
    if payload is not None:
        value = datetime.fromisoformat(str(payload["authorized_launch_at"]))
        if value.tzinfo is None:
            raise ValueError("Phase 7A runtime authority timestamp is not timezone-aware")
        return value.astimezone(UTC)
    if not create:
        return None
    launched_at = datetime.now(UTC)
    base._atomic_json(
        path,
        {
            "schema_version": "phase7a_runtime_authority_v1",
            "authorized_launch_at": launched_at.isoformat(),
            "graceful_stop_at": (launched_at + GRACEFUL_STOP_AFTER).isoformat(),
            "hard_stop_at": (launched_at + HARD_CAP).isoformat(),
        },
    )
    return launched_at


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("supervise", "status"))
    parser.add_argument("--repository", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    args = parser.parse_args()
    paths = Phase7APaths(args.repository.resolve())
    launched_at = _runtime_authority(paths, create=args.command == "supervise")
    policy = WallClockPolicy(launched_at) if launched_at is not None else None
    supervisor = Phase7ASupervisor(
        args.repository,
        poll_seconds=args.poll_seconds,
        budget_policy=policy,
    )
    if args.command == "status":
        print(json.dumps(supervisor.status(), indent=2, sort_keys=True, default=str))
        return 0
    cloud_root = "gs://crypto-ai-data-83921/artifacts/phase7"
    return supervisor.supervise(cloud_root)


if __name__ == "__main__":
    raise SystemExit(main())
