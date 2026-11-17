from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parents[2] / "scripts/closure"
sys.path.insert(0, str(HERE))
import runpod_phase7_ops as ops  # noqa: E402
import runpod_stop_controller_phase7 as controller  # noqa: E402
from runpod_wallet_policy_phase7 import decision, policy  # noqa: E402


def session(wallet=10):
    now = datetime.now(UTC)
    return {
        "wallet_usd_at_start": wallet,
        "max_session_usd": 5,
        "all_in_usd_per_hour_upper_bound": 0.6,
        "session_start_utc": (now - timedelta(seconds=1)).isoformat(),
        "hard_stop_utc": (now + timedelta(hours=4)).isoformat(),
    }


@pytest.mark.parametrize("wallet", [10, 2.50])
def test_wallet_with_headroom_continues(wallet):
    value = decision(session(wallet), wallet_usd=wallet)
    assert value["action"] == "CONTINUE" and value["absolute_floor_usd"] == 1


@pytest.mark.parametrize("wallet", [1.75, 1.70])
def test_low_wallet_requests_bounded_checkpoint(wallet):
    value = decision(session(wallet), wallet_usd=wallet)
    assert value["reason"] == "LOW_WALLET_PREEMPTION"
    assert value["action"] == "CHECKPOINT_AND_STOP" and 0 < value["grace_seconds"] <= 90


def test_final_dollar_means_emergency_no_evidence_delay():
    value = decision(session(1.02), wallet_usd=1.02)
    assert value["action"] == "EMERGENCY_STOP" and value["grace_seconds"] == 0


def test_delayed_billing_and_decline_cannot_hide_elapsed_cost():
    c = session(3)
    c["session_start_utc"] = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
    value = decision(c, wallet_usd=3, billed_usd=0)
    assert value["effective_wallet_usd"] < 1.3 and value["action"] != "CONTINUE"


def test_identified_bill_is_more_conservative_than_wallet():
    value = decision(session(3), wallet_usd=3, billed_usd=1.5)
    assert value["effective_wallet_usd"] == 1.5 and value["action"] != "CONTINUE"


@pytest.mark.parametrize("wallet,healthy", [(None, True), (10, False)])
def test_wallet_or_billing_api_failure_stops(wallet, healthy):
    value = decision(session(), wallet_usd=wallet, api_healthy=healthy)
    assert value["action"] == "EMERGENCY_STOP" and value["grace_seconds"] == 0


def test_dynamic_high_rate_trigger_includes_lag_shutdown_and_export():
    c = session(20)
    c["all_in_usd_per_hour_upper_bound"] = 50
    value = decision(c, wallet_usd=10)
    assert value["effective_trigger_usd"] > 9
    with pytest.raises(ValueError, match="FLOOR"):
        policy({"wallet_policy": {"absolute_floor_usd": 0}})


def test_configured_trigger_is_never_silently_lowered():
    c = session(3)
    c["wallet_policy"] = {"checkpoint_trigger_usd": 2.75}
    assert decision(c, wallet_usd=2.7)["action"] == "CHECKPOINT_AND_STOP"


def test_deadline_takes_priority_over_grace():
    c = session()
    c["hard_stop_utc"] = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    value = decision(c, wallet_usd=10)
    assert value["reason"] == "HARD_DEADLINE" and value["grace_seconds"] == 0


def test_grace_success_independently_verifies_receipt(tmp_path):
    calls = []

    def remote(ssh, command, payload=None, timeout=25):
        if payload:
            calls.append(payload)
            return ""
        return json.dumps(
            {
                "state": "EVIDENCE_EXPORTED",
                "request_id": calls[0]["request_id"],
                "checkpoint_path": (
                    "/workspace/phase7a-evidence/training-checkpoints/run/session/iter-025"
                ),
                "checkpoint_sha256": "a" * 64,
            }
        )

    with (
        patch.object(controller, "remote", side_effect=remote),
        patch.object(
            controller, "verify_remote_checkpoint", return_value={"verification": "PASS"}
        ) as verify,
    ):
        result = controller.graceful_checkpoint(
            [], Path("/local"), tmp_path, 2, "LOW_WALLET_PREEMPTION"
        )
    verify.assert_called_once()
    assert result["verification"] == "PASS"
    states = [
        json.loads(line)["state"] for line in (tmp_path / "events.jsonl").read_text().splitlines()
    ]
    assert states == [
        "CHECKPOINT_REQUESTED",
        "CHECKPOINT_WRITTEN",
        "CHECKPOINT_VERIFIED",
        "EVIDENCE_EXPORTED",
    ]


def test_checkpoint_timeout_is_bounded_and_has_no_fake_success(tmp_path):
    with (
        patch.object(controller, "remote", return_value=""),
        patch.object(controller.time, "monotonic", side_effect=[0, 2]),
    ):
        result = controller.graceful_checkpoint(
            [], Path("/local"), tmp_path, 1, "LOW_WALLET_PREEMPTION"
        )
    assert result is None
    assert ops.read(tmp_path / "run-state.json")["state"] == "CHECKPOINT_TIMEOUT"


def test_checkpoint_corruption_cannot_be_acknowledged(tmp_path):
    request = {}

    def remote(ssh, cmd, payload=None, timeout=25):
        if payload:
            request.update(payload)
            return ""
        return json.dumps({"state": "EVIDENCE_EXPORTED", "request_id": request["request_id"]})

    with (
        patch.object(controller, "remote", side_effect=remote),
        patch.object(controller, "verify_remote_checkpoint", side_effect=ValueError("CORRUPT")),
        pytest.raises(ValueError, match="CORRUPT"),
    ):
        controller.graceful_checkpoint([], Path("/local"), tmp_path, 5, "LOW_WALLET_PREEMPTION")
    assert not (tmp_path / "last-verified-checkpoint.json").exists()


def test_stop_api_failure_never_fabricates_exited_receipt(tmp_path):
    api = SimpleNamespace(
        call=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("API unavailable"))
    )
    with (
        patch.object(controller.time, "sleep"),
        pytest.raises(RuntimeError, match="STOP_NOT_CONFIRMED"),
    ):
        controller.stop(api, {"pod_id": "fixture"}, tmp_path, "LOW_WALLET_PREEMPTION")
    assert not (tmp_path / "stop-receipt.json").exists()


def test_restart_requires_new_exact_owner_approval(tmp_path, monkeypatch):
    identities = {"fixture": "fixture"}
    previous = {
        "logical_run_id": "run",
        "checkpoint_sha256": "a" * 64,
        "pod_id": "previous",
        "binding": {"scientific_ids": identities, "model_threads": 8},
    }
    monkeypatch.setattr("crypto_ai.phase7.preemption.verify_partial", lambda *a, **k: previous)
    monkeypatch.setattr(ops, "expected", lambda: identities)
    args = SimpleNamespace(
        checkpoint="fixture-checkpoint", approval=str(tmp_path / "approval.json")
    )
    ops.write(args.approval, {"status": "APPROVED"})
    c = {"pod_id": "new", "previous_pod_id": "previous", "model_threads": 8}
    with pytest.raises(ValueError, match="FRESH_RESUME"):
        ops.partial_for_restart(args, c)
    ops.write(
        args.approval,
        {
            "status": "APPROVED",
            "mode": "train",
            "operation": "RESUME_ONE_CPU_SMOKE_RESTART_FROM_ZERO",
            "logical_run_id": "run",
            "checkpoint_sha256": "a" * 64,
        },
    )
    assert ops.partial_for_restart(args, c) is previous
    with pytest.raises(ValueError, match="OLD_POD_REUSED"):
        ops.partial_for_restart(args, {**c, "pod_id": "previous"})
    with pytest.raises(ValueError, match="THREAD_BUDGET"):
        ops.partial_for_restart(args, {**c, "model_threads": 16})


@pytest.mark.parametrize(
    "outcome",
    [
        "success",
        "timeout",
        "corrupt",
        "network_failure",
        "wallet_api_failure",
        "billing_api_failure",
        "already_exited",
    ],
)
def test_controller_wallet_flow_always_confirms_provider_exit(tmp_path, monkeypatch, outcome):
    c = {
        **session(2.5),
        "pod_id": "fixture-pod",
        "compute_usd_per_hour": 0.5,
        "provider_container_disk_gb": 200,
        "container_image": "fixture-image",
        "max_session_usd": 2,
    }
    contract = tmp_path / "approved.json"
    ops.write(contract, c)
    args = SimpleNamespace(
        contract=str(contract),
        api_key_file="UNUSED",
        ssh_key="UNUSED",
        state=str(tmp_path / "state"),
        local_root="/fixture-local",
    )

    class API:
        stopped = outcome == "already_exited"
        wallets = 0
        mutations = []

        def call(self, method, path, payload=None):
            if method != "GET":
                self.mutations.append((method, path, payload))
            if path == "/graphql":
                if outcome == "wallet_api_failure":
                    raise RuntimeError("wallet unavailable")
                self.wallets += 1
                return {
                    "data": {
                        "myself": {
                            "clientBalance": 2.5 if self.wallets == 1 else 1.7,
                            "currentSpendPerHr": 0.6,
                        }
                    }
                }
            if path.startswith("/v2/billing"):
                if outcome == "billing_api_failure":
                    raise RuntimeError("billing unavailable")
                return {"metadata": {"totals": {"totalAmount": 0}}}
            if "network-volumes" in path:
                return {"id": ops.VOLUME}
            if method == "POST" and path.endswith("/action"):
                assert payload == {"action": "stop"}
                self.stopped = True
                return {}
            return {
                "id": c["pod_id"],
                "dataCenterId": "EU-SE-1",
                "locked": False,
                "disk": 200,
                "cost": 0.5,
                "image": "fixture-image",
                "gpu": {"memory": 100},
                "status": "EXITED" if self.stopped else "RUNNING",
                "actions": ["stop"],
                "mounts": {"network": [{"path": "/workspace", "volumeId": ops.VOLUME}]},
                "ssh": {"direct": {"host": "127.0.0.1", "port": 22066}},
            }

    api = API()

    def checkpoint(ssh, local, state, seconds, reason):
        if outcome in {"corrupt", "network_failure"}:
            raise ValueError(outcome)
        if outcome == "timeout":
            return None
        result = {
            "completed_rounds": 25,
            "best_iteration": 20,
            "best_validation_rmse": 0.01,
            "checkpoint_path": (
                "/workspace/phase7a-evidence/training-checkpoints/fixture/session/iter-25"
            ),
            "cache_retained": True,
        }
        ops.write(state / "last-verified-checkpoint.json", result)
        return result

    monkeypatch.setattr(controller, "contract", lambda path: c)
    monkeypatch.setattr(controller, "API", lambda path: api)
    monkeypatch.setattr(controller.sys, "platform", "darwin")
    monkeypatch.setattr(controller, "remote", lambda *a, **k: "")
    monkeypatch.setattr(controller.time, "sleep", lambda seconds: None)
    with patch.object(controller, "graceful_checkpoint", side_effect=checkpoint) as graceful:
        controller.monitor(args)
    assert (
        api.stopped
        and ops.read(tmp_path / "state/stop-receipt.json")["provider_status"] == "EXITED"
    )
    assert all(payload != {"action": "start"} for _, _, payload in api.mutations)
    if outcome in {"wallet_api_failure", "billing_api_failure", "already_exited"}:
        graceful.assert_not_called()
    else:
        graceful.assert_called_once()
