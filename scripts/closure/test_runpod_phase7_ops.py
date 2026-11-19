"""Operator safety tests only: mocks/temporary files, no cache build or model fit."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runpod_phase7_ops as ops  # noqa: E402
import runpod_select_host_phase7 as hosts  # noqa: E402
import runpod_stop_controller_phase7 as controller  # noqa: E402


@pytest.mark.parametrize(
    "method,path,payload",
    [("GET", "/v2/pods/test", None), ("POST", "/graphql", {"query": "query { myself { id } }"})],
)
@pytest.mark.parametrize(
    "first_failure",
    [TimeoutError(), urllib.error.HTTPError("fixture", 503, "unavailable", None, None)],
)
def test_read_only_api_retries_one_timeout_with_shorter_budget(
    tmp_path, method, path, payload, first_failure
):
    key = tmp_path / "key"
    key.write_text("fixture-only")
    key.chmod(0o600)
    api = controller.API(key)
    from unittest.mock import MagicMock

    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"status":"RUNNING"}'
    with (
        patch.object(
            controller.urllib.request, "urlopen", side_effect=[first_failure, response]
        ) as send,
        patch.object(controller.time, "sleep") as sleep,
    ):
        assert api.call(method, path, payload) == {"status": "RUNNING"}
    assert send.call_count == 2
    assert all(call.kwargs["timeout"] == 6 for call in send.call_args_list)
    sleep.assert_called_once_with(0.5)


@pytest.mark.parametrize("failure", [TimeoutError(), urllib.error.URLError("fixture-unavailable")])
def test_api_read_exhaustion_fails_closed_and_mutations_are_not_replayed(tmp_path, failure):
    key = tmp_path / "key"
    key.write_text("fixture-only")
    key.chmod(0o600)
    api = controller.API(key)
    for method, path, payload, attempts in (
        ("GET", "/v2/pods/test", None, 2),
        ("POST", "/v2/pods", {"name": "never-replay-create"}, 1),
        ("POST", "/graphql", {"query": "mutation { change }"}, 1),
    ):
        with (
            patch.object(controller.urllib.request, "urlopen", side_effect=failure) as send,
            patch.object(controller.time, "sleep"),
            pytest.raises(RuntimeError, match="NETWORK_UNAVAILABLE"),
        ):
            api.call(method, path, payload)
        assert send.call_count == attempts


def test_api_permission_denial_is_not_retried(tmp_path):
    key = tmp_path / "key"
    key.write_text("fixture-only")
    key.chmod(0o600)
    with (
        patch.object(
            controller.urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError("fixture", 403, "denied", None, None),
        ) as send,
        pytest.raises(RuntimeError, match="HTTP_403"),
    ):
        controller.API(key).call("GET", "/v2/pods/test")
    send.assert_called_once()


@pytest.fixture
def approved():
    value = ops.read(ops.DOC / "RUNPOD_COST_AND_STOP_CONTRACT_TEMPLATE_20261118.json")
    value.update(
        status="APPROVED",
        owner="TEST_FIXTURE_ONLY",
        pod_id="testpod123",
        compute_usd_per_hour=0.5,
        all_in_usd_per_hour_upper_bound=0.6,
        max_session_usd=2,
        wallet_usd_at_start=10,
        identified_cumulative_usd_at_start=1.2,
        hard_stop_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        session_start_utc=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )
    return value


@pytest.mark.parametrize("index", [0, 5, 10, 15])
def test_contract_binds_one_canonical_fold(tmp_path, approved, index):
    approved.update(fold_index=index, fold=ops.CANONICAL_FOLDS[index])
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(approved))
    assert ops.selected_fold(ops.contract(path)) == (index, ops.CANONICAL_FOLDS[index])


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"fold_index": 5}, "CONTRACT_FOLD_ID_MISMATCH"),
        ({"fold_index": 5, "fold": "fold-010-01be2e390a0b"}, "CONTRACT_FOLD_ID_MISMATCH"),
        ({"fold_index": 16, "fold": "fold-015-ed49f0aadaf7"}, "CONTRACT_FOLD_INDEX_INVALID"),
        ({"fold_index": -1}, "CONTRACT_FOLD_INDEX_INVALID"),
        ({"fold_index": "5", "fold": "fold-005-2cf830b9f251"}, "CONTRACT_FOLD_INDEX_INVALID"),
        ({"fold_index": True}, "CONTRACT_FOLD_INDEX_INVALID"),
    ],
)
def test_contract_fold_mismatch_fails_closed(tmp_path, approved, change, error):
    approved.update(change)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(approved))
    with pytest.raises(ValueError, match=error):
        ops.contract(path)


def test_contract_without_fold_index_is_fold_zero(approved):
    approved.pop("fold_index", None)
    assert ops.selected_fold(approved) == (0, ops.FOLD)


def test_unapproved_template_refused():
    with pytest.raises(ValueError, match="OWNER_SESSION_APPROVAL_REQUIRED"):
        ops.contract(ops.DOC / "RUNPOD_COST_AND_STOP_CONTRACT_TEMPLATE_20261118.json")


def test_approved_fixture_validates_without_network(tmp_path, approved):
    p = tmp_path / "contract.json"
    ops.write(p, approved)
    assert ops.contract(p)["approval"] == "LINUX_VERIFICATION_ONLY"


@pytest.mark.parametrize(
    "change",
    [
        {"max_session_usd": 18},
        {"max_session_usd": float("nan")},
        {"hard_stop_utc": "2026-01-01T00:00:00Z"},
        {"backend": "gpu"},
        {"workers": 2},
        {"spec": "grid"},
        {"volume_id": "wrong"},
        {"source_commit": "99cf12f"},
        {"provider_container_disk_gb": 149},
        {"minimum_free_ram_gib": 0},
        {"approval": "TRAIN_AND_PREPARE"},
        {"hard_stop_utc": "2026-11-19T05:00:00+05:30"},
    ],
)
def test_cost_scope_and_deadline_refusals(tmp_path, approved, change):
    approved.update(change)
    p = tmp_path / "contract.json"
    ops.write(p, approved)
    with pytest.raises((ValueError, TypeError)):
        ops.contract(p)


@pytest.mark.parametrize("stage", ops.STAGES)
def test_default_plans_do_not_execute(stage, capsys):
    with patch.object(sys, "argv", ["ops", stage]), patch.object(ops, "execute") as execute:
        assert ops.main() == 0
        execute.assert_not_called()
    assert '"status": "DRY_RUN_ONLY"' in capsys.readouterr().out


def test_controller_default_does_not_read_key_or_connect(capsys):
    with (
        patch.object(sys, "argv", ["controller", "--contract", "not-a-real-file"]),
        patch.object(controller, "API") as api,
    ):
        assert controller.main() == 0
        api.assert_not_called()
    assert '"armed": false' in capsys.readouterr().out


def test_non_linux_refused_before_mount_or_writes(tmp_path):
    with (
        patch.object(ops.platform, "system", return_value="Darwin"),
        patch.object(ops, "run") as run,
    ):
        with pytest.raises(ValueError, match="REAL_LINUX"):
            ops.local_mount(tmp_path, 200)
        run.assert_not_called()


def test_network_mount_refused_before_write(tmp_path):
    with (
        patch.object(ops.platform, "system", return_value="Linux"),
        patch.object(ops.platform, "machine", return_value="x86_64"),
        patch.object(
            ops,
            "run",
            return_value=json.dumps({"filesystems": [{"fstype": "fuse", "options": "rw"}]}),
        ),
        pytest.raises(ValueError, match="UNQUALIFIED_OR_NETWORK"),
    ):
        ops.local_mount(tmp_path, 200)


def test_region_and_gib_conversion():
    g = {
        "id": "fixture",
        "minRam": 64,
        "minVcpuCount": 8,
        "price": {"secure": 0.1},
        "dataCenters": [{"id": "EU-SE-1", "availability": "HIGH"}],
    }
    assert hosts.candidates({"gpus": [g]}, {})[0]["candidate_meets_catalog_floor"] is False
    g["minRam"] = 70
    assert hosts.candidates({"gpus": [g]}, {})[0]["candidate_meets_catalog_floor"] is True
    g["dataCenters"][0]["id"] = "US-CA-2"
    assert hosts.candidates({"gpus": [g]}, {}) == []


def test_host_price_order():
    base = {
        "minRam": 100,
        "minVcpuCount": 8,
        "dataCenters": [{"id": "EU-SE-1", "availability": "HIGH"}],
    }
    a, b = copy.deepcopy(base), copy.deepcopy(base)
    a.update(id="costlier", price={"secure": 1})
    b.update(id="cheaper", price={"secure": 0.5})
    assert [x["type"] for x in hosts.candidates({"gpus": [a, b]}, {})] == ["cheaper", "costlier"]


def test_stop_only_mutation_is_stop_and_volume_retained(tmp_path):
    class FakeAPI:
        def __init__(self):
            self.calls = []
            self.stopped = False

        def call(self, method, path, data=None):
            self.calls.append((method, path, data))
            if method == "POST":
                assert path == "/v2/pods/testpod123/action" and data == {"action": "stop"}
                self.stopped = True
                return {}
            if "network-volumes" in path:
                return {"id": ops.VOLUME}
            return {"status": "EXITED" if self.stopped else "RUNNING"}

    api = FakeAPI()
    with patch.object(controller.time, "sleep"):
        controller.stop(api, {"pod_id": "testpod123"}, tmp_path, "MOCK_DEADLINE")
    assert ops.read(tmp_path / "stop-receipt.json")["volume_preserved"] == ops.VOLUME
    assert all(m != "DELETE" for m, _, _ in api.calls)


def test_ssh_discovery_requires_trusted_hostkey():
    command = controller.ssh_args(
        {"ssh": {"direct": {"host": "127.0.0.1", "port": 22066}}}, "/unused/key"
    )
    assert "StrictHostKeyChecking=yes" in command
    assert "22066" in command and "BatchMode=yes" in command


def test_add_only_copy_refuses_changed_historical_file(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    (a / "report.json").write_text("original")
    ops.mirror_tree(a, b)
    (a / "report.json").write_text("changed")
    with pytest.raises(ValueError, match="EXISTING_EVIDENCE_CONFLICT"):
        ops.mirror_tree(a, b)
    assert (b / "report.json").read_text() == "original"


def test_copy_of_a_growing_log_is_verified_against_the_bytes_read(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    log = a / "memory_timeline.jsonl"
    log.write_text('{"round": 1}\n')
    real_read, real_copy = Path.read_bytes, ops.shutil.copy2

    def grow():  # the live guard appends right after the copier has read the file
        with log.open("a") as stream:
            stream.write('{"round": 2}\n')

    def read_then_grow(path):
        data = real_read(path)
        if path == log:
            grow()
        return data

    def copy_then_grow(src, dst, **kwargs):
        result = real_copy(src, dst, **kwargs)
        if Path(src) == log:
            grow()
        return result

    with (
        patch.object(Path, "read_bytes", read_then_grow),
        patch.object(ops.shutil, "copy2", copy_then_grow),
    ):
        ops.mirror_tree(a, b)
    assert (b / "memory_timeline.jsonl").read_text() == '{"round": 1}\n'


def test_linux_export_retains_junit_without_following_disposable_fixture_symlinks(tmp_path):
    source, target = tmp_path / "linux", tmp_path / "export"
    gate = source / ("software-gate-" + "a" * 32)
    fixtures = gate / "tmp"
    fixtures.mkdir(parents=True)
    (gate / "pytest.xml").write_text("<testsuite tests='1520' failures='0'/>")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("never export")
    (fixtures / "fixture-current").symlink_to(outside, target_is_directory=True)
    ops.mirror_linux_evidence(source, target)
    assert (target / gate.name / "pytest.xml").read_text() == (gate / "pytest.xml").read_text()
    assert not (target / gate.name / "tmp").exists()
    assert (fixtures / "fixture-current").is_symlink()
    assert (
        ops.read(target / "EXPORT_SCOPE.json")["symlinks_outside_disposable_fixtures"] == "REFUSED"
    )
    (gate / "metadata-link").symlink_to(outside / "private.txt")
    with pytest.raises(ValueError, match="SYMLINK_REFUSED"):
        ops.mirror_linux_evidence(source, tmp_path / "refused-export")


def test_linux_export_rejects_symlinked_fixture_root_and_unknown_gate(tmp_path):
    for gate_name in ("software-gate-" + "b" * 32, "unexpected-gate"):
        source = tmp_path / gate_name
        fixtures = source / gate_name / "tmp"
        fixtures.parent.mkdir(parents=True)
        fixtures.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(ValueError, match="SYMLINK_REFUSED"):
            ops.mirror_linux_evidence(source, tmp_path / (gate_name + "-export"))


def test_final_json_not_a_partial_progress_record(tmp_path):
    p = tmp_path / "log"
    p.write_text('STAGE\n{"progress": 1}\n{\n "status": "PREPARED_ONLY"\n}\n')
    assert ops.final_json(p) == {"status": "PREPARED_ONLY"}


def test_templates_use_exact_six_identity_keys_and_separate_modes():
    assert len(ops.expected()) == 6
    for mode in ("prepare", "train"):
        template = ops.read(ops.DOC / f"OWNER_{mode.upper()}_TEMPLATE_20261118.json")
        assert template["mode"] == mode and template["status"] != "APPROVED"
        assert {k: template["binding"][k] for k in ops.expected()} == ops.expected()


def test_frozen_environment_names_and_effective_thread_budget(tmp_path, approved):
    from crypto_ai.phase7.run_contract import validate_environment
    from crypto_ai.phase7.runtime import cpu_availability

    with patch.dict(os.environ, {}, clear=True):
        env = ops.environment(
            approved, tmp_path / "source", tmp_path, Path("/workspace/phase7a-transfer")
        )
    validate_environment(env)
    assert (
        int(env["PHASE7_LIGHTGBM_THREADS_PER_MODEL"]) == cpu_availability()["effective_cpu_count"]
    )
    assert env["PHASE7_MODEL_PARALLELISM"] == "1"
    assert env["PHASE7_LGBM_DEVICE"] == "cpu"


def test_canonical_cache_api_signatures_exist():
    import inspect

    from crypto_ai.phase7.prepared_cache import PreparedDataCache
    from crypto_ai.phase7.training import _prepared_cache_identity
    from crypto_ai.phase7.universe import select_fold_active_universe

    inspect.signature(PreparedDataCache.load).bind(None, {}, None)
    assert "source_identity" in inspect.signature(_prepared_cache_identity).parameters
    assert "unusable_segments" in inspect.signature(select_fold_active_universe).parameters
    assert importlib.util.find_spec("crypto_ai.phase7.identity_summary") is not None


@pytest.mark.parametrize(
    "trigger,expected_reason",
    [
        ("deadline", "HARD_DEADLINE"),
        ("budget", "SESSION_BUDGET"),
        ("complete", "NORMAL_COMPLETE"),
    ],
)
def test_controller_mock_end_to_end_stops_compute(tmp_path, approved, trigger, expected_reason):
    from argparse import Namespace

    approved["container_image"] = "test-image"
    if trigger == "deadline":
        approved["hard_stop_utc"] = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
    elif trigger == "budget":
        approved["max_session_usd"] = 0.00001
    path = tmp_path / "contract.json"
    ops.write(path, approved)

    class FakeAPI:
        stopped = False

        def call(self, method, endpoint, data=None):
            if method == "PATCH":
                assert data == {"locked": False}
                return {}
            if endpoint.endswith("/action"):
                assert data == {"action": "stop"}
                self.stopped = True
                return {}
            if endpoint == "/graphql":
                return {"data": {"myself": {"clientBalance": 10, "currentSpendPerHr": 0.6}}}
            if endpoint.startswith("/v2/billing/"):
                return {"metadata": {"totals": {"totalAmount": 0}}}
            if "network-volumes" in endpoint:
                return {"id": ops.VOLUME}
            return {
                "id": "testpod123",
                "dataCenterId": "EU-SE-1",
                "locked": False,
                "disk": 200,
                "cost": 0.5,
                "image": "test-image",
                "gpu": {"memory": 100},
                "mounts": {"network": [{"path": "/workspace", "volumeId": ops.VOLUME}]},
                "status": "EXITED" if self.stopped else "RUNNING",
                "actions": ["stop"],
                "ssh": {"direct": {"host": "127.0.0.1", "port": 22066}},
            }

    api = FakeAPI()
    args = Namespace(
        contract=str(path),
        api_key_file="UNUSED",
        state=str(tmp_path / "state"),
        ssh_key="UNUSED",
        local_root="/crypto2-session",
    )
    with (
        patch.object(controller, "API", return_value=api),
        patch.object(controller.sys, "platform", "darwin"),
        patch.object(
            controller, "remote", return_value="NORMAL_COMPLETE" if trigger == "complete" else ""
        ),
        patch.object(controller.time, "sleep"),
    ):
        controller.monitor(args)
    assert api.stopped is True
    receipt = ops.read(tmp_path / "state/stop-receipt.json")
    assert receipt["reason"] == expected_reason
    assert receipt["volume_preserved"] == ops.VOLUME


def test_expired_restart_still_stops_previously_armed_exact_contract(tmp_path, approved):
    from argparse import Namespace

    approved["hard_stop_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    path = tmp_path / "contract.json"
    ops.write(path, approved)
    args = Namespace(contract=str(path), state=str(tmp_path / "state"))
    ops.write(
        tmp_path / "state/permission-probe.json",
        {"status": "PASS", "pod_id": approved["pod_id"], "contract_sha256": ops.sha(path)},
    )
    assert controller.stop_contract(args)["pod_id"] == approved["pod_id"]


def test_expired_contract_without_prior_arm_proof_cannot_authorize_stop(tmp_path, approved):
    from argparse import Namespace

    approved["hard_stop_utc"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    path = tmp_path / "contract.json"
    ops.write(path, approved)
    args = Namespace(contract=str(path), state=str(tmp_path / "state"))
    with pytest.raises(FileNotFoundError):
        controller.stop_contract(args)


@pytest.mark.parametrize(
    ("volume", "region", "ok"),
    [
        ("kz9axr9t9v", "EU-SE-1", True),
        ("POD_CONTAINER_DISK", "EU-RO-1", True),
        ("POD_CONTAINER_DISK", "EU-SE-2", False),
        ("kz9axr9t9v", "EU-RO-1", False),
        ("other-volume", "EU-SE-1", False),
    ],
)
def test_contract_placement_is_network_volume_or_pod_local(tmp_path, approved, volume, region, ok):
    approved.update(volume_id=volume, region=region)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(approved))
    if ok:
        ops.contract(path)
    else:
        with pytest.raises(ValueError, match="SESSION_SCOPE_MISMATCH"):
            ops.contract(path)


def test_pod_local_binding_requires_region_and_no_network_volume(approved):
    approved.update(volume_id="POD_CONTAINER_DISK", region="EU-RO-1")
    pod = {"id": "testpod123", "dataCenterId": "EU-RO-1", "mounts": {"network": []}}
    with pytest.raises(ValueError, match="POD_LOCKED_OR_DISK_QUOTA_CHANGED"):
        controller.pod_binding({**pod, "locked": True, "disk": 200}, approved)
    with pytest.raises(ValueError, match="POD_BINDING_CHANGED"):
        controller.pod_binding({**pod, "dataCenterId": "EU-CZ-1"}, approved)
    with pytest.raises(ValueError, match="NETWORK_VOLUME_BINDING_CHANGED"):
        mounted = {"network": [{"path": "/workspace", "volumeId": "kz9axr9t9v"}]}
        controller.pod_binding({**pod, "mounts": mounted}, approved)
