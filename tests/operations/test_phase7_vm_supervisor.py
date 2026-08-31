from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from scripts import phase7_vm_supervisor as supervisor_module
from scripts.phase7_vm_supervisor import (
    EXPECTED_CLOUD_ROOT,
    EXPECTED_CONFIG_HASH,
    BudgetLevel,
    BudgetPolicy,
    Phase7VmSupervisor,
    SupervisorStatus,
    _atomic_json,
)

ROOT = Path(__file__).resolve().parents[2]


class FakeRunner:
    def __init__(
        self,
        *,
        tmux: Sequence[bool] = (),
        pids: Sequence[tuple[str, ...]] = (),
        shutdown_code: int = 0,
        on_shutdown: Callable[[], None] | None = None,
        worker_in_session: bool = True,
    ) -> None:
        self.tmux = list(tmux)
        self.pids = list(pids)
        self.shutdown_code = shutdown_code
        self.on_shutdown = on_shutdown
        self.worker_in_session = worker_in_session
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        args: list[str],
        *,
        cwd: Path,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd.is_absolute()
        assert capture_output is True and text is True
        command = tuple(args)
        self.calls.append(command)
        returncode, stdout, stderr = 0, "", ""
        if command[:2] == ("tmux", "has-session"):
            returncode = 0 if (self.tmux.pop(0) if self.tmux else False) else 1
        elif command[:2] == ("pgrep", "-f"):
            values = self.pids.pop(0) if self.pids else ()
            returncode = 0 if values else 1
            stdout = "\n".join(values) + ("\n" if values else "")
        elif command[:2] == ("tmux", "list-panes"):
            stdout = "900\n"
        elif command[:3] == ("ps", "-o", "sid="):
            pid = command[-1]
            stdout = "777\n" if pid == "900" or self.worker_in_session else "888\n"
        elif command[:3] == ("git", "rev-parse", "HEAD"):
            stdout = "a" * 40 + "\n"
        elif command[:3] == ("git", "status", "--short"):
            stdout = "?? data/phase7/\n"
        elif command[:3] == ("sudo", "-n", "shutdown"):
            if self.on_shutdown:
                self.on_shutdown()
            returncode = self.shutdown_code
            stderr = "denied" if returncode else ""
        result = subprocess.CompletedProcess(args, returncode, stdout, stderr)
        if check and returncode:
            raise subprocess.CalledProcessError(returncode, args, stdout, stderr)
        return result


def _supervisor(
    tmp_path: Path,
    runner: FakeRunner,
    *,
    budget_policy: BudgetPolicy | None = None,
) -> Phase7VmSupervisor:
    return Phase7VmSupervisor(
        tmp_path,
        poll_seconds=0,
        run_command=runner,
        sleeper=lambda _seconds: None,
        now=lambda: datetime(2026, 8, 31, 12, tzinfo=UTC),
        budget_policy=budget_policy,
    )


def _budget_policy(
    *,
    baseline: str = "1600",
    baseline_hour: int = 12,
    actual: str | None = None,
) -> BudgetPolicy:
    return BudgetPolicy(
        baseline_inr=Decimal(baseline),
        baseline_at=datetime(2026, 8, 31, baseline_hour, tzinfo=UTC),
        hourly_inr=Decimal("70"),
        soft_inr=Decimal("2000"),
        projected_inr=Decimal("2200"),
        hard_inr=Decimal("2300"),
        actual_inr=Decimal(actual) if actual is not None else None,
    )


def _progress(path: Path, *, complete: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "worker_status": "COMPLETE" if complete else "RUNNING",
        "stage": "complete" if complete else "training",
        "last_event": "phase7_final_summary" if complete else "phase7_training_progress",
        "configuration_hash": EXPECTED_CONFIG_HASH,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "july_2026_used": False,
        "current_symbol": "FILUSDT",
        "current_fold": 3,
        "training_started": True,
        "code_commit": "a" * 40,
        "report_artifact": str(path.parent / "phase7_report.json"),
    }
    _atomic_json(path, payload)
    return payload


def test_exit_zero_with_final_progress_persists_completed_before_mocked_shutdown(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "local_artifacts/phase7/supervisor/state.json"

    def assert_completed() -> None:
        assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "COMPLETED"

    runner = FakeRunner(on_shutdown=assert_completed)
    supervisor = _supervisor(tmp_path, runner)
    expected = _progress(supervisor.paths.progress, complete=True)
    for relative in ("local_artifacts/phase7", "data/gold/phase7", "data/phase7"):
        (tmp_path / relative).mkdir(parents=True, exist_ok=True)

    assert supervisor._finish(0, EXPECTED_CLOUD_ROOT) == 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["status"] == SupervisorStatus.COMPLETED
    assert state["progress"] == expected
    assert state["configuration_hash"] == EXPECTED_CONFIG_HASH
    assert len([call for call in runner.calls if call[:3] == ("gcloud", "storage", "rsync")]) == 3
    assert runner.calls[-1] == ("sudo", "-n", "shutdown", "-h", "now")


def test_genuine_failure_persists_blocked_diagnostics_before_shutdown(tmp_path: Path) -> None:
    marker = tmp_path / "local_artifacts/phase7/supervisor/BLOCKED.json"

    def assert_blocked() -> None:
        assert json.loads(marker.read_text(encoding="utf-8"))["reason"] == "worker_exit_1"

    runner = FakeRunner(on_shutdown=assert_blocked)
    supervisor = _supervisor(tmp_path, runner)
    _progress(supervisor.paths.progress, complete=False)
    supervisor.paths.run_log.parent.mkdir(parents=True, exist_ok=True)
    supervisor.paths.run_log.write_text("ERROR failure\nTraceback here\n", encoding="utf-8")
    checkpoint = tmp_path / "local_artifacts/phase7/checkpoints/run/data.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"status":"complete"}\n', encoding="utf-8")
    before = checkpoint.read_bytes()

    assert supervisor._finish(1, EXPECTED_CLOUD_ROOT) == 2
    blocked = json.loads(marker.read_text(encoding="utf-8"))
    diagnostic = json.loads(Path(blocked["diagnostic"]).read_text(encoding="utf-8"))
    assert diagnostic["stage"] == "training"
    assert diagnostic["current_symbol"] == "FILUSDT"
    assert diagnostic["current_fold"] == 3
    assert diagnostic["error_summary"] == ["ERROR failure", "Traceback here"]
    assert diagnostic["last_checkpoints"] == [str(checkpoint.resolve())]
    assert checkpoint.read_bytes() == before


def test_blocked_startup_does_not_resume_or_shutdown(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    _atomic_json(supervisor.paths.blocked, {"status": "BLOCKED", "reason": "quality"})

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 3
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)


def test_completed_startup_does_not_resume(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    _atomic_json(supervisor.paths.state, {"status": "COMPLETED"})

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 4
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)


def test_blocked_state_without_marker_does_not_resume(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    _atomic_json(supervisor.paths.state, {"status": "BLOCKED", "reason": "persisted"})

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 3
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)


def test_ready_starts_exactly_one_guarded_resume_worker(tmp_path: Path) -> None:
    runner = FakeRunner(tmux=(False,), pids=((),))
    supervisor = _supervisor(tmp_path, runner)

    supervisor._start_worker(EXPECTED_CLOUD_ROOT)
    launches = [call for call in runner.calls if call[:2] == ("tmux", "new-session")]
    assert len(launches) == 1
    command = launches[0][-1]
    assert "PHASE7_ALLOW_CLOUD_RESEARCH=1" in command
    assert f"PHASE7_CLOUD_STORAGE_ROOT={EXPECTED_CLOUD_ROOT}" in command
    assert str(supervisor.paths.worker_script) in command
    worker_script = (ROOT / "scripts/run_phase7_worker.sh").read_text(encoding="utf-8")
    assert "phase7-research" in worker_script
    assert "--resume" in worker_script
    assert "tee -a" in worker_script


def test_running_duplicate_workers_are_stopped_blocked_and_shutdown(tmp_path: Path) -> None:
    runner = FakeRunner(tmux=(True,), pids=(("11", "12"),))
    supervisor = _supervisor(tmp_path, runner)

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 2
    assert ("tmux", "kill-session", "-t", "phase7-auto") in runner.calls
    assert supervisor.paths.blocked.is_file()
    assert runner.calls[-1] == ("sudo", "-n", "shutdown", "-h", "now")


def test_worker_outside_authoritative_tmux_is_blocked(tmp_path: Path) -> None:
    runner = FakeRunner(tmux=(True,), pids=(("11",),), worker_in_session=False)
    supervisor = _supervisor(tmp_path, runner)

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 2
    assert ("tmux", "kill-session", "-t", "phase7-auto") in runner.calls
    blocked = json.loads(supervisor.paths.blocked.read_text(encoding="utf-8"))
    assert blocked["reason"] == "existing session does not contain exactly one owned worker"


def test_long_quiet_healthy_worker_is_never_treated_as_idle_or_stopped(tmp_path: Path) -> None:
    runner = FakeRunner(
        tmux=(True, True, False),
        pids=(("11",), ("11",)),
    )
    supervisor = _supervisor(tmp_path, runner)
    supervisor.paths.worker_exit.parent.mkdir(parents=True)
    supervisor.paths.worker_exit.write_text("143\n", encoding="ascii")

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 130
    assert not any(call[:2] == ("tmux", "kill-session") for call in runner.calls)
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)
    state = json.loads(supervisor.paths.state.read_text(encoding="utf-8"))
    assert state["status"] == "READY"
    assert state["resume_safe"] is True


@pytest.mark.parametrize("exit_code", [129, 130, 143])
def test_manual_signal_is_interruption_not_scientific_failure(
    tmp_path: Path, exit_code: int
) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    _progress(supervisor.paths.progress, complete=False)

    assert supervisor._finish(exit_code, EXPECTED_CLOUD_ROOT) == 130
    assert not supervisor.paths.blocked.exists()
    assert list((supervisor.paths.supervisor_root / "interruptions").glob("*.json"))
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)


def test_clear_blocked_archives_evidence_without_starting_worker(tmp_path: Path) -> None:
    runner = FakeRunner(tmux=(False,), pids=((),))
    supervisor = _supervisor(tmp_path, runner)
    _atomic_json(supervisor.paths.blocked, {"status": "BLOCKED", "reason": "fixed"})

    state = supervisor.clear_blocked("validated fix abc123")
    assert state["status"] == "READY"
    assert not supervisor.paths.blocked.exists()
    assert Path(state["cleared_marker"]).is_file()
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)


def test_atomic_runtime_state_has_no_partial_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    _atomic_json(path, {"status": "READY", "value": 1})
    _atomic_json(path, {"status": "RUNNING", "value": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "status": "RUNNING",
        "value": 2,
    }
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_failed_diagnostic_persistence_prevents_unsafe_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    original = supervisor_module._atomic_json

    def fail_diagnostic(path: Path, payload: dict[str, object]) -> None:
        if "diagnostics" in path.parts:
            raise OSError("disk write failed")
        original(path, payload)

    monkeypatch.setattr(supervisor_module, "_atomic_json", fail_diagnostic)
    with pytest.raises(OSError, match="disk write failed"):
        supervisor._finish(1, EXPECTED_CLOUD_ROOT)
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)


def test_zero_exit_without_final_progress_is_blocked_not_completed(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    _progress(supervisor.paths.progress, complete=False)

    assert supervisor._finish(0, EXPECTED_CLOUD_ROOT) == 2
    assert json.loads(supervisor.paths.state.read_text(encoding="utf-8"))["status"] == "BLOCKED"


def test_progress_compatibility_holdout_and_config_are_preserved(tmp_path: Path) -> None:
    runner = FakeRunner()
    supervisor = _supervisor(tmp_path, runner)
    payload = _progress(supervisor.paths.progress, complete=False)
    config_path = tmp_path / "configs/phase7/research_v1.toml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("[mode]\nname='cloud'\n", encoding="utf-8")
    before = hashlib.sha256(config_path.read_bytes()).hexdigest()

    diagnostic = supervisor._diagnostic_payload("test", 1)
    after = hashlib.sha256(config_path.read_bytes()).hexdigest()
    assert diagnostic["progress"] == payload
    assert diagnostic["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert diagnostic["prospective_holdout_used"] is False
    assert diagnostic["prospective_holdout_evaluation_authorized"] is False
    assert EXPECTED_CONFIG_HASH == "cc550337f1f4ee4654124bf6"
    assert before == after


def test_shutdown_is_always_mocked_and_failure_is_explicit(tmp_path: Path) -> None:
    runner = FakeRunner(shutdown_code=1)
    supervisor = _supervisor(tmp_path, runner)

    with pytest.raises(RuntimeError, match="shutdown command failed"):
        supervisor._shutdown()
    state = json.loads(supervisor.paths.state.read_text(encoding="utf-8"))
    assert state["shutdown_error"] == "denied"


def test_running_state_contains_progress_and_checkpoint_identity(tmp_path: Path) -> None:
    runner = FakeRunner(pids=(("11",),))
    supervisor = _supervisor(tmp_path, runner)
    _progress(supervisor.paths.progress, complete=False)
    checkpoint = tmp_path / "local_artifacts/phase7/checkpoints/run-a/data.json"
    _atomic_json(
        checkpoint,
        {
            "run_identity": "run-a",
            "stage": "data",
            "status": "complete",
            "completed_at": "2026-08-31T11:00:00+00:00",
            "checkpoint_hash": "abc",
        },
    )

    state = supervisor._state(SupervisorStatus.RUNNING, **supervisor._runtime_metadata())
    assert state["worker_pids"] == ["11"]
    assert state["stage"] == "training"
    assert state["current_symbol"] == "FILUSDT"
    assert state["current_fold"] == 3
    assert state["checkpoint_identity"]["checkpoint_hash"] == "abc"
    assert state["progress_artifact"] == str(supervisor.paths.progress.resolve())


def test_operational_contract_preserves_scientific_and_holdout_identity() -> None:
    contract = json.loads(
        (ROOT / "configs/contracts/phase7_vm_supervisor_v1.json").read_text(encoding="utf-8")
    )
    assert contract["contract_id"] == "phase7_vm_supervisor_v1"
    assert contract["operational_only"] is True
    assert contract["scientific_baseline"] == "phase7_scientific_baseline_v1_8"
    assert contract["canonical_configuration_hash"] == EXPECTED_CONFIG_HASH
    assert contract["states"] == ["READY", "RUNNING", "BLOCKED", "COMPLETED"]
    assert contract["holdout"] == {
        "july_2026_used": False,
        "prospective_holdout_evaluation_authorized": False,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
    }


def test_budget_below_threshold_allows_normal_execution() -> None:
    snapshot = _budget_policy(baseline="1900").snapshot(datetime(2026, 8, 31, 12, tzinfo=UTC))
    assert snapshot["level"] == BudgetLevel.NORMAL
    assert snapshot["effective_spend_inr"] == 1900.0


def test_budget_soft_warning_does_not_force_shutdown(tmp_path: Path) -> None:
    runner = FakeRunner(
        tmux=(True, True, False),
        pids=(("11",), ("11",)),
    )
    supervisor = _supervisor(
        tmp_path,
        runner,
        budget_policy=_budget_policy(baseline="2050"),
    )
    supervisor.paths.worker_exit.parent.mkdir(parents=True)
    supervisor.paths.worker_exit.write_text("143\n", encoding="ascii")

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 130
    assert not any(call[:2] == ("tmux", "send-keys") for call in runner.calls)
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)


def test_projected_preflight_persists_budget_stopped_before_shutdown(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "local_artifacts/phase7/supervisor/state.json"

    def assert_budget_stopped() -> None:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "BUDGET_STOPPED"
        assert state["reason"] == "preflight_projected_budget_limit_reached"

    runner = FakeRunner(tmux=(False, False), pids=((),), on_shutdown=assert_budget_stopped)
    supervisor = _supervisor(
        tmp_path,
        runner,
        budget_policy=_budget_policy(baseline="2250"),
    )

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 5
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)
    assert not supervisor.paths.blocked.exists()


def test_hard_budget_stop_interrupts_owned_worker_before_mocked_shutdown(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "local_artifacts/phase7/supervisor/state.json"

    def assert_budget_stopped() -> None:
        assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == ("BUDGET_STOPPED")

    runner = FakeRunner(
        tmux=(True, True, False),
        pids=(("11",),),
        on_shutdown=assert_budget_stopped,
    )
    supervisor = _supervisor(
        tmp_path,
        runner,
        budget_policy=_budget_policy(baseline="2250", actual="2310"),
    )
    supervisor.paths.worker_exit.parent.mkdir(parents=True)
    supervisor.paths.worker_exit.write_text("130\n", encoding="ascii")

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 5
    assert ("tmux", "send-keys", "-t", "phase7-auto", "C-c") in runner.calls
    assert not supervisor.paths.blocked.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["worker_exit_code"] == 130
    assert state["worker_stop_forced"] is False


def test_budget_stopped_startup_does_not_resume_or_shutdown(tmp_path: Path) -> None:
    runner = FakeRunner(tmux=(False,), pids=((),))
    supervisor = _supervisor(tmp_path, runner, budget_policy=_budget_policy())
    _atomic_json(supervisor.paths.state, {"status": "BUDGET_STOPPED"})

    assert supervisor.supervise(EXPECTED_CLOUD_ROOT) == 5
    assert not any(call[:2] == ("tmux", "new-session") for call in runner.calls)
    assert not any(call[:3] == ("sudo", "-n", "shutdown") for call in runner.calls)


def test_unknown_actual_billing_uses_conservative_estimate_without_crashing() -> None:
    snapshot = _budget_policy(baseline="1600", baseline_hour=6).snapshot(
        datetime(2026, 8, 31, 12, tzinfo=UTC)
    )
    assert snapshot["source"] == "CONSERVATIVE_ESTIMATE"
    assert snapshot["actual_billing_inr"] is None
    assert snapshot["estimated_spend_inr"] == 2020.0
    assert snapshot["level"] == BudgetLevel.SOFT_WARNING


def test_missing_optional_actual_billing_environment_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "PHASE7_BUDGET_BASELINE_INR": "1600",
        "PHASE7_BUDGET_BASELINE_AT_UTC": "2026-08-31T12:00:00+00:00",
        "PHASE7_BUDGET_HOURLY_INR": "70",
        "PHASE7_BUDGET_SOFT_INR": "2000",
        "PHASE7_BUDGET_PROJECTED_INR": "2200",
        "PHASE7_BUDGET_HARD_INR": "2300",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("PHASE7_ACTUAL_BILLING_INR", raising=False)

    policy = BudgetPolicy.from_environment()
    assert policy.actual_inr is None
    assert policy.snapshot(datetime(2026, 8, 31, 12, tzinfo=UTC))["level"] == (BudgetLevel.NORMAL)


def test_actual_billing_is_combined_conservatively_with_estimate() -> None:
    snapshot = _budget_policy(actual="2310").snapshot(datetime(2026, 8, 31, 12, tzinfo=UTC))
    assert snapshot["source"] == "MAX_OF_ACTUAL_AND_CONSERVATIVE_ESTIMATE"
    assert snapshot["effective_spend_inr"] == 2310.0
    assert snapshot["level"] == BudgetLevel.HARD_STOP


def test_budget_stopped_is_distinct_from_scientific_terminal_states() -> None:
    assert SupervisorStatus.BUDGET_STOPPED not in {
        SupervisorStatus.BLOCKED,
        SupervisorStatus.COMPLETED,
    }


def test_budget_successor_contract_is_operational_only() -> None:
    contract = json.loads(
        (ROOT / "configs/contracts/phase7_vm_supervisor_v1_1.json").read_text(encoding="utf-8")
    )
    assert contract["predecessor_contract_id"] == "phase7_vm_supervisor_v1"
    assert contract["operational_only"] is True
    assert contract["scientific_baseline"] == "phase7_scientific_baseline_v1_8"
    assert contract["canonical_configuration_hash"] == EXPECTED_CONFIG_HASH
    assert contract["states"][-1] == "BUDGET_STOPPED"
    assert contract["holdout"]["prospective_holdout_evaluation_authorized"] is False
