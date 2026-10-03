"""Local synthetic hardening evidence, not Linux/Gold/GPU qualification."""

from __future__ import annotations

import errno
import json
import os
import socket
import subprocess
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import (
    artifacts,
    device_evidence,
    resources,
    telemetry,
    training,
    verify_linux,
)
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json
from crypto_ai.phase7.config import PathConfig, stable_hash
from crypto_ai.phase7.economics import ThresholdSet
from crypto_ai.phase7.equivalence import REQUIRED_LIMITS, assess_equivalence
from crypto_ai.phase7.models import Phase7ModelBundle, masked_rows, save_model
from crypto_ai.phase7.prepared_cache import cleanup_cache_plan
from crypto_ai.phase7.recovery import (
    inspect_spec_artifacts,
    model_receipt_path,
    publish_model_receipt,
    reconcile_spec_checkpoint,
)
from crypto_ai.phase7.run_lease import RunLease, RunLeaseError, owned_run, owner_liveness
from crypto_ai.phase7.runtime import RuntimePaths


def artifact_fixture(root: Path, boundary: int = 3):
    """Serialize a synthetic bundle, without any estimator fit or market data."""
    identity = {
        "experiment_id": "G0-synthetic",
        "fold_id": "fold-synthetic",
        "gold_dataset_id": "SYNTHETIC",
        "gold_manifest_sha256": "a" * 64,
        "model_backend_semantics": "cpu",
        "training_source_identity": training.training_source_identity(),
        "configuration_hash": "fixture",
    }
    store = CheckpointStore(root / "checkpoints", root.name)
    model_path, report_path = root / "model.joblib", root / "report.json"
    arguments = dict(
        model_path=model_path,
        report_path=report_path,
        checkpoint_store=store,
        stage="train/fold/spec",
        expected_identity=identity,
    )
    if not boundary:
        return arguments
    publication = {
        "run_identity": root.name,
        "mode": "production",
        "fold_id": identity["fold_id"],
        "spec_id": identity["experiment_id"],
        "state": "MODEL_REPORT_PUBLICATION_V1",
    }
    calibration = {"method": "identity"}
    thresholds = asdict(ThresholdSet("global", {"global": None}))
    components = training._frozen_test_identity_components(
        model_identity="synthetic-model",
        calibrator_identity=stable_hash(calibration),
        thresholds=thresholds,
    )
    metadata = {
        "model_identity": "synthetic-model",
        "compute_backend": "cpu",
        "scientific_input_identity": identity,
        "publication": publication,
    }
    model = Phase7ModelBundle(
        "G0", ("f",), "raw_future_return", {}, {}, (), False, True, {}, {}, metadata
    )
    save_model(model, model_path)
    receipt = publish_model_receipt(model_path, identity, publication)
    if boundary == 1:
        return arguments
    report = {
        "status": "COMPLETE",
        "spec": {"name": identity["experiment_id"], "architecture": "G0"},
        "fold_id": identity["fold_id"],
        "model": metadata,
        "checkpoint_identity": identity,
        "publication": publication,
        "calibration": {"selected": calibration},
        "thresholds": thresholds,
        "calibrator_identity": stable_hash(calibration),
        "threshold_identity": stable_hash(thresholds),
        "frozen_identity_components": components,
        "frozen_identity_before_test": stable_hash(components),
        "test_metrics": {"fixture_only": True},
        "economic": {"no_trade": True},
        "segment_rows": {"test": 1},
        "test_used_for_selection": False,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
        "july_2026_used": False,
        "model_artifact_sha256": file_sha256(model_path),
        "model_receipt_sha256": file_sha256(receipt),
    }
    report["report_identity"] = stable_hash(report, length=64)
    atomic_json(report_path, report)
    if boundary == 3:
        store.complete(arguments["stage"], [model_path, report_path, receipt], identity)
    return arguments


def test_lease_rejects_second_writer_and_preserves_owner(tmp_path):
    root = tmp_path / "production-run"
    with RunLease(root, root.name, {"science": "one"}, mode="production") as first:
        original = first.path.read_bytes()
        assert owner_liveness(first.owner) == "LIVE"
        with (
            pytest.raises(RunLeaseError, match="active filesystem"),
            RunLease(root, root.name, {"science": "one"}, mode="production"),
        ):
            pytest.fail("second writer entered")
        assert first.path.read_bytes() == original
        with RunLease(
            tmp_path / "benchmark-only-fixture", "benchmark-only-fixture", {}, mode="benchmark"
        ):
            pass
    assert not first.path.exists()
    assert (root / ".phase7-run-lease.guard").is_file()


def test_nested_lease_only_same_thread_and_identity(tmp_path):
    root = tmp_path / "run"
    with owned_run(root, root.name, {"science": 1}, mode="production") as first:
        with owned_run(root, root.name, {"science": 1}, mode="production") as nested:
            assert nested is first
        with (
            pytest.raises(RunLeaseError),
            owned_run(root, root.name, {"science": 2}, mode="production"),
        ):
            pass

        def other_thread():
            with owned_run(root, root.name, {"science": 1}, mode="production"):
                pass

        with ThreadPoolExecutor(1) as pool, pytest.raises(RunLeaseError):
            pool.submit(other_thread).result()


@pytest.mark.parametrize(
    "boundary,state", [(1, "MODEL_ONLY"), (2, "MODEL_REPORT"), (3, "COMPLETE")]
)
def test_process_kill_retains_lease_and_publication_boundary(tmp_path, boundary, state):
    root = tmp_path / "killed-run"
    code = (
        "from pathlib import Path; import time; "
        "from crypto_ai.phase7.run_lease import RunLease; "
        "from tests.phase7.test_pre_lightning_hardening import artifact_fixture; "
        f"root=Path({str(root)!r}); lease=RunLease(root,root.name,{{}},mode='production'); "
        f"lease.__enter__(); artifact_fixture(root,{boundary}); print('KILL_BOUNDARY',flush=True); "
        "time.sleep(45)"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    try:
        while True:
            line = child.stdout.readline()
            if "KILL_BOUNDARY" in line:
                break
            if not line:
                pytest.fail(child.stderr.read())
        with pytest.raises(RunLeaseError), RunLease(root, root.name, {}, mode="production"):
            pass
        child.kill()
        child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
        child.stdout.close()
        child.stderr.close()
    # Release the Windows process handle before proving PID death; a retained
    # kernel object can still expose the old creation time after wait().
    del child
    args = artifact_fixture(root, 0)
    assert inspect_spec_artifacts(**args)["state"] == state
    lease = RunLease(root, root.name, {}, mode="production")
    digest = file_sha256(lease.path)
    with pytest.raises(RunLeaseError, match="checksum"):
        lease.recover(expected_sha256="f" * 64, reason="reviewed crash")
    archive = lease.recover(expected_sha256=digest, reason="reviewed synthetic process-kill")
    assert file_sha256(archive) == digest and not lease.path.exists()
    with RunLease(root, root.name, {}, mode="production"):
        pass


def test_stale_age_does_not_authorize_live_recovery(tmp_path):
    root = tmp_path / "retained"
    lease = RunLease(root, root.name, {}, mode="production")
    owner = {
        "pid": os.getpid(),
        "process_start_time": __import__("psutil").Process().create_time(),
        "hostname": socket.gethostname(),
        "run_identity": root.name,
        "mode": "production",
        "acquired_at": "1900-01-01T00:00:00Z",
    }
    atomic_json(lease.path, owner)
    with pytest.raises(RunLeaseError, match="proven dead"):
        lease.recover(
            expected_sha256=file_sha256(lease.path),
            reason="very old",
            confirm_foreign_owner_dead=True,
        )
    assert lease.path.is_file()


def test_foreign_lease_requires_explicit_owner_dead_confirmation(tmp_path):
    root = tmp_path / "foreign"
    lease = RunLease(root, root.name, {}, mode="production")
    atomic_json(
        lease.path,
        {"hostname": "other-host", "pid": 1, "run_identity": root.name, "mode": "production"},
    )
    digest = file_sha256(lease.path)
    with pytest.raises(RunLeaseError, match="proven dead"):
        lease.recover(expected_sha256=digest, reason="owner review")
    assert lease.recover(
        expected_sha256=digest,
        reason="owner confirmed host stopped",
        confirm_foreign_owner_dead=True,
    ).exists()


@pytest.mark.parametrize(
    "boundary,state", [(0, "NONE"), (1, "MODEL_ONLY"), (2, "MODEL_REPORT"), (3, "COMPLETE")]
)
def test_artifact_states_are_read_only(tmp_path, boundary, state):
    args = artifact_fixture(tmp_path / "run", boundary)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    assert inspect_spec_artifacts(**args)["state"] == state
    assert before == {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}


def test_explicit_reconciliation_without_fit_or_gold(tmp_path, monkeypatch):
    root = tmp_path / "run"
    args = artifact_fixture(root, 2)
    monkeypatch.setattr(training, "fit_architecture", lambda *_a, **_k: pytest.fail("fit"))
    monkeypatch.setattr(training, "_load_gold_manifest", lambda *_a: pytest.fail("Gold"))
    evidence = [args["model_path"], args["report_path"], model_receipt_path(args["model_path"])]
    original = {p: p.read_bytes() for p in evidence}
    result = reconcile_spec_checkpoint(run_root=root, mode="production", **args)
    assert result["state"] == "COMPLETE"
    assert original == {p: p.read_bytes() for p in evidence}
    checkpoint = args["checkpoint_store"].checkpoint_path(args["stage"])
    checkpoint_bytes = checkpoint.read_bytes()
    assert (
        reconcile_spec_checkpoint(run_root=root, mode="production", **args)["state"] == "COMPLETE"
    )
    assert checkpoint.read_bytes() == checkpoint_bytes


def test_model_only_cannot_reconcile_or_invent_metrics(tmp_path):
    root = tmp_path / "run"
    args = artifact_fixture(root, 1)
    with pytest.raises(ValueError, match="MODEL_ONLY"):
        reconcile_spec_checkpoint(run_root=root, mode="production", **args)
    assert not args["report_path"].exists()
    assert not args["checkpoint_store"].checkpoint_path(args["stage"]).exists()


@pytest.mark.parametrize("artifact", ["model", "report", "receipt", "checkpoint"])
def test_truncation_is_preserved_and_corrupt(tmp_path, artifact):
    args = artifact_fixture(tmp_path / "run")
    paths = {
        "model": args["model_path"],
        "report": args["report_path"],
        "receipt": model_receipt_path(args["model_path"]),
        "checkpoint": args["checkpoint_store"].checkpoint_path(args["stage"]),
    }
    target = paths[artifact]
    target.write_bytes(target.read_bytes()[:10])
    original = target.read_bytes()
    assert inspect_spec_artifacts(**args)["state"] == "CORRUPT"
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "key",
    [
        "experiment_id",
        "fold_id",
        "gold_dataset_id",
        "gold_manifest_sha256",
        "model_backend_semantics",
        "configuration_hash",
        "training_source_identity",
    ],
)
def test_wrong_expected_identity_never_deserializes(tmp_path, monkeypatch, key):
    args = artifact_fixture(tmp_path / "run", 2)
    args["expected_identity"] = {**args["expected_identity"], key: "WRONG"}
    monkeypatch.setattr(
        "crypto_ai.phase7.models.load_model", lambda *_: pytest.fail("untrusted deserialize")
    )
    assert inspect_spec_artifacts(**args)["state"] == "INCONSISTENT"


def test_model_hash_checked_before_deserialization(tmp_path, monkeypatch):
    args = artifact_fixture(tmp_path / "run", 2)
    args["model_path"].write_bytes(b"CORRUPT")
    monkeypatch.setattr(
        "crypto_ai.phase7.models.load_model", lambda *_: pytest.fail("untrusted deserialize")
    )
    assert inspect_spec_artifacts(**args)["state"] == "CORRUPT"


@pytest.mark.parametrize("mask", [[1, 1, 1, 1], [0, 1, 1, 0], [1, 0, 1, 0], [0, 0, 0, 0]])
def test_masked_rows_exact_float64_order_and_contiguous_views(mask):
    array = np.arange(12, dtype=np.float64).reshape(4, 3)
    selected = np.asarray(mask, dtype=bool)
    result = masked_rows(array, selected)
    assert result.dtype == np.float64 and np.array_equal(result, array[selected])
    if selected.all() or mask == [0, 1, 1, 0]:
        assert np.shares_memory(result, array)


@pytest.mark.parametrize("invalid", ["0", "-1", "nan", "inf", ""])
def test_resource_floors_reject_invalid_explicit_value(monkeypatch, invalid):
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", invalid)
    with pytest.raises(ValueError):
        resources.configured_floor("PHASE7_MIN_FREE_RAM_GIB", "PHASE7_MIN_AVAILABLE_RAM_GB")


def test_unset_ram_floor_reports_and_continues(monkeypatch):
    monkeypatch.delenv("PHASE7_MIN_FREE_RAM_GIB", raising=False)
    monkeypatch.delenv("PHASE7_MIN_AVAILABLE_RAM_GB", raising=False)
    monkeypatch.setattr(resources, "memory_snapshot", lambda: {"ram_available_bytes": 1})
    assert resources.resource_admission("PREPARE")["ram_floor_gib"] == 0


def test_ram_and_each_output_filesystem_boundary(tmp_path, monkeypatch):
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "1")
    monkeypatch.setattr(resources, "memory_snapshot", lambda: {"ram_available_bytes": 1024**3})
    runtime = RuntimePaths.resolve(PathConfig())
    names = ("artifact_root", "cache_root", "checkpoint_root", "model_root", "report_root")
    for name in names:
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setenv("PHASE7_" + name.upper(), str(path))
    temp = tmp_path / "temporary"
    temp.mkdir()
    monkeypatch.setenv("PHASE7_TEMP_ROOT", str(temp))
    runtime = RuntimePaths.resolve(PathConfig())
    monkeypatch.setattr(resources.shutil, "disk_usage", lambda _: SimpleNamespace(free=1024**3))
    assert len(resources.resource_admission("PREPARE", paths=runtime)["filesystems"]) == 6
    for name in (*names, "temporary_root"):
        rejected = temp if name == "temporary_root" else getattr(runtime, name)
        monkeypatch.setattr(
            resources.shutil,
            "disk_usage",
            lambda p, rejected=rejected: SimpleNamespace(
                free=1024**3 - 1 if p == rejected else 1024**3
            ),
        )
        with pytest.raises(OSError, match=name):
            resources.resource_admission("PREPARE", paths=runtime)
    monkeypatch.setattr(resources, "memory_snapshot", lambda: {"ram_available_bytes": 1024**3 - 1})
    with pytest.raises(MemoryError):
        resources.resource_admission("PREPARE", paths=runtime)


def test_enospc_atomic_json_preserves_protected_data(tmp_path, monkeypatch):
    protected = atomic_json(tmp_path / "protected.json", {"frozen": True})
    original = protected.read_bytes()
    monkeypatch.setattr(
        artifacts, "fsync_file", lambda *_: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full"))
    )
    with pytest.raises(OSError) as error:
        atomic_json(tmp_path / "new.json", {"new": True})
    assert error.value.errno == errno.ENOSPC
    assert not (tmp_path / "new.json").exists()
    assert not list(tmp_path.glob("*.tmp"))
    assert protected.read_bytes() == original


@pytest.mark.parametrize(
    "boundary,state",
    [("model_receipt", "MODEL_ONLY"), ("report", "MODEL_ONLY"), ("spec", "MODEL_REPORT")],
)
def test_enospc_publication_boundaries_never_complete(tmp_path, monkeypatch, boundary, state):
    root = tmp_path / "run"
    original_fsync = artifacts.fsync_file

    def fail_selected(path):
        if path.name.startswith(f".{boundary}.json."):
            raise OSError(errno.ENOSPC, "synthetic full filesystem")
        original_fsync(path)

    monkeypatch.setattr(artifacts, "fsync_file", fail_selected)
    with pytest.raises(OSError) as error:
        artifact_fixture(root, 3)
    assert error.value.errno == errno.ENOSPC
    args = artifact_fixture(root, 0)
    assert inspect_spec_artifacts(**args)["state"] == state
    assert not args["checkpoint_store"].checkpoint_path(args["stage"]).exists()
    assert args["model_path"].exists() and not list(root.rglob("*.tmp"))


def test_cache_resource_admission_precedes_construction(tmp_path, monkeypatch):
    from crypto_ai.phase7.prepared_cache import PreparedDataCache
    from tests.phase7.test_prepared_cache import _fixture

    _, fold, prepared, identity = _fixture()
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "1")
    monkeypatch.setattr(
        resources.shutil, "disk_usage", lambda *_a: SimpleNamespace(free=1024**3 - 1)
    )
    root = tmp_path / "cache"
    with pytest.raises(OSError, match="CACHE_WRITE"):
        PreparedDataCache(root, "auto").write(identity, fold, prepared)
    assert not root.exists()


def test_cleanup_dry_run_protects_references_and_reports_bytes(tmp_path):
    cache, references = tmp_path / "cache", tmp_path / "references"
    references.mkdir()
    for value in ("a", "b"):
        entry = cache / (value * 64)
        entry.mkdir(parents=True)
        (entry / "matrix").write_bytes(b"123456")
    atomic_json(references / "benchmark.json", {"nested": {"prepared_cache_id": "a" * 64}})
    result = cleanup_cache_plan(cache, reference_roots=(references,))
    assert result["estimated_reclaimable_bytes"] == 6
    assert [e["reason"] for e in result["entries"]] == ["REFERENCED", "UNREFERENCED"]
    assert all((cache / (value * 64)).exists() for value in ("a", "b"))
    assert cleanup_cache_plan(cache, reference_roots=())["estimated_reclaimable_bytes"] == 0


def comparison(limits=None, gpu_delta=0):
    actual = np.linspace(-1, 1, 50)
    return assess_equivalence(
        actual,
        actual,
        actual + gpu_delta,
        limits=limits,
        cpu_best_iteration=12,
        gpu_best_iteration=12,
    )


def test_gpu_comparison_without_or_partial_limits_never_passes():
    assert comparison()["status"] == "REVIEW_REQUIRED"
    assert comparison({"prediction_correlation_min": 0.99})["status"] == "REVIEW_REQUIRED"


def test_gpu_comparison_explicit_complete_limits_pass_and_fail():
    limits = {key: 0.99 if key.endswith("_min") else 0 for key in REQUIRED_LIMITS}
    assert comparison(limits)["status"] == "PASS"
    assert comparison(limits, 0.1)["status"] == "FAIL"
    assert comparison(limits)["production_policy_equivalence"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_gpu_comparison_invalid_limit_rejected(value):
    with pytest.raises(ValueError):
        comparison({"mae_delta_max": value})


def test_device_attestation_rejects_requested_label_without_independent_process():
    estimator = SimpleNamespace(
        booster_=SimpleNamespace(model_to_string=lambda: "[device_type: cuda]")
    )
    with pytest.raises(RuntimeError, match="unverified"):
        device_evidence.attest_fitted_device(estimator, "cuda", [])
    samples = [{"processes": [{"pid": os.getpid(), "gpu_uuid": "GPU-fixture", "vram_bytes": 100}]}]
    assert device_evidence.attest_fitted_device(estimator, "cuda", samples)["status"] == "PASS"
    with pytest.raises(RuntimeError):
        device_evidence.attest_fitted_device(estimator, "gpu", samples)


def test_device_snapshot_current_pid_only(monkeypatch):
    monkeypatch.setattr(
        device_evidence.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            stdout=f"{os.getpid()}, GPU-current, 4\n{os.getpid() + 100000}, GPU-other, 900\n"
        ),
    )
    result = device_evidence.process_device_snapshot()
    assert result["process_vram_bytes"] == 4 * 1024**2
    assert result["processes"][0]["gpu_uuid"] == "GPU-current"


def test_telemetry_operational_values_do_not_change_source_identity(monkeypatch, capsys):
    identity = training.training_source_identity()
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "12")
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "99")
    telemetry.telemetry("PREPARE", "END", matrix_shape=[4, 2], matrix_bytes=64)
    sample = json.loads(capsys.readouterr().out)
    assert sample["event"] == "RUNTIME_TELEMETRY"
    assert sample["matrix_bytes"] == 64
    assert "temporary_root" in sample["disk_free_bytes_by_root"]
    assert training.training_source_identity() == identity


def test_linux_gate_rejects_windows_without_running_commands(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_linux.sys, "platform", "win32")
    monkeypatch.setattr(verify_linux.subprocess, "run", lambda *_a, **_k: pytest.fail("command"))
    result = verify_linux.verify_linux(tmp_path, tmp_path / "outputs")
    assert result["linux_validation"] == "NOT RUN" and result["status"] == "FAIL"
    assert not (tmp_path / "outputs").exists()


@pytest.mark.parametrize("skip_bash", [False, True])
def test_linux_gate_plan_requires_five_executed_bash_tests(tmp_path, monkeypatch, skip_bash):
    monkeypatch.setattr(verify_linux.sys, "platform", "linux")
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    commands = []

    def command(args, **kwargs):
        commands.append(args)
        assert "PHASE7_ALLOW_CLOUD_RESEARCH" not in kwargs["env"]
        assert kwargs["env"]["PHASE7_LGBM_DEVICE"] == "cpu"
        if "pytest" in args:
            suite = ET.Element("testsuite")
            for i in range(5):
                case = ET.SubElement(
                    suite, "testcase", classname="tests.phase7.test_log_rotation", name=str(i)
                )
                if skip_bash and i == 0:
                    ET.SubElement(case, "skipped")
            ET.ElementTree(suite).write(args[args.index("--junitxml") + 1])
        return SimpleNamespace(returncode=0, stdout="synthetic", stderr="")

    def preflight(*_args, **kwargs):
        assert kwargs == {
            "create_outputs": False,
            "run_backend_smoke": False,
            "verification_only": True,
        }
        return {"status": "PASS"}

    monkeypatch.setattr(verify_linux.subprocess, "run", command)
    monkeypatch.setattr(verify_linux, "build_preflight_report", preflight)
    result = verify_linux.verify_linux(tmp_path, tmp_path / "outputs")
    assert result["status"] == ("FAIL" if skip_bash else "PASS")
    assert len(commands) == 6 and result["training_ready"] is False
    assert result["gpu_smoke_test"] == result["actual_gold_byte_validation"] == "NOT RUN"


def test_verification_only_preflight_never_opens_gold_or_fits(monkeypatch):
    from crypto_ai.phase7 import preflight

    monkeypatch.setattr(
        preflight, "validate_gold_manifest", lambda *_a: pytest.fail("Gold accessed")
    )
    monkeypatch.setattr(preflight, "smoke_test_backend", lambda *_a: pytest.fail("fit executed"))
    monkeypatch.setattr(RuntimePaths, "validate", lambda *_a, **_k: [])
    root = Path(__file__).resolve().parents[2]
    result = preflight.build_preflight_report(
        root / "configs/phase7/research_core20_primary_v1.toml",
        create_outputs=False,
        run_backend_smoke=False,
        verification_only=True,
    )
    assert (
        result["gold_manifest"] is result["gold_byte_validation"] is result["backend_smoke"] is None
    )
    assert result["training_readiness"] == "NOT_READY"


def test_gpu_fit_claim_rejected_if_native_backend_cpu(monkeypatch):
    from crypto_ai.phase7 import backend

    class FakeEstimator:
        booster_ = SimpleNamespace(model_to_string=lambda: "[device_type: cpu]")
        calls = 0

        def fit(self, *_args, **_kwargs):
            self.calls += 1

    sample = {"processes": [{"pid": os.getpid(), "gpu_uuid": "GPU-fixture", "vram_bytes": 100}]}
    monkeypatch.setattr(device_evidence, "process_device_snapshot", lambda: sample)
    monkeypatch.setattr(backend, "gpu_snapshot", lambda: {"detected": True, "devices": ["fixture"]})
    estimator = FakeEstimator()
    with pytest.raises(RuntimeError, match="without CPU fallback"):
        device_evidence.fit_with_device_evidence(
            estimator, backend.resolve_lightgbm_backend("cuda")
        )
    assert estimator.calls == 1
