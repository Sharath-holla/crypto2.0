"""Synthetic metadata only; no market access, real fit, cloud or holdout work."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from integration.crypto_aiventra import config, jobs, runtime
from integration.crypto_aiventra.adapter import Crypto2Adapter, read_json, redact
from integration.crypto_aiventra.config import (
    CONFIG_HASH,
    GOLD_ID,
    RUN_ID,
    SOURCE_HEAD,
    CryptoPaths,
)
from integration.crypto_aiventra.verification import completion_receipt

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    # Job protocol tests use synthetic metadata/authority, not an approval of the
    # live checkout. Keep them independent of later standalone engine amendments.
    # The dedicated branch/source-drift tests below exercise the real guard.
    monkeypatch.setattr(jobs, "require_branch", lambda _root: None)
    paths = CryptoPaths(
        ROOT,
        tmp_path,
        tmp_path / "gold",
        tmp_path / "data",
        tmp_path / "historical",
        tmp_path / "checkpoints",
        tmp_path / "cache",
        tmp_path / "models",
        tmp_path / "reports",
        tmp_path / "logs",
        tmp_path / "verification",
        tmp_path / "runtime",
    )
    return Crypto2Adapter(paths)


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def request(kind="CRYPTO_RUNTIME_HEALTH"):
    return jobs.JobRequest(
        job_type=kind,
        deadline_utc=int(time.time()) + 300,
        maximum_runtime_seconds=60,
        cost_ceiling="0",
        cost_currency="INR",
    )


def test_canonical_identity_folds_specs_and_locked_holdout(adapter):
    identity = adapter.get_project_identity()
    assert identity["configuration_hash"] == CONFIG_HASH
    assert identity["run_identity"] == RUN_ID
    assert identity["folds_expected"] == 16 and identity["specs_expected"] == 48
    assert identity["features"] == 109 and identity["physical_columns"] == 130
    assert identity["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert identity["prospective_holdout_used"] is False
    assert identity["prospective_holdout_evaluation_authorized"] is False
    assert identity["july_2026_used"] is False
    assert len(adapter.get_fold_status()) == 16
    assert len(adapter.get_model_results()) == 48


def test_missing_evidence_never_becomes_success_or_fake_metrics(adapter):
    snapshot = adapter.snapshot()
    assert snapshot["dataset"]["status"] == snapshot["lineage"]["status"] == "AWAITING_EVIDENCE"
    assert snapshot["preparation"]["progress_percent"] is None
    assert all(row["metrics"] is None for row in snapshot["models"])
    assert all(
        row["models_verified_complete"] is None and row["status"] != "COMPLETE"
        for row in snapshot["folds"]
    )
    assert not adapter.paths.runtime.exists()


def test_gold_manifest_is_only_declared_metadata_not_byte_validation(adapter):
    write(
        adapter.paths.gold / GOLD_ID / "manifest.json",
        {
            "dataset_id": GOLD_ID,
            "rows": 50352548,
            "partition_files": [],
            "prospective_holdout_status": "LOCKED_UNUSED",
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
        },
    )
    result = adapter.get_dataset_status()
    assert result["status"] == "MANIFEST_PRESENT_NOT_BYTE_VALIDATED"
    assert result["byte_validation"] == "NOT_RUN" and result["market_rows_read"] is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("dataset_id", "WRONG"),
        ("prospective_holdout_used", True),
        ("prospective_holdout_evaluation_authorized", True),
    ],
)
def test_gold_mismatch_is_not_pass(adapter, key, value):
    payload = {
        "dataset_id": GOLD_ID,
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
    }
    write(adapter.paths.gold / "manifest.json", {**payload, key: value})
    assert adapter.get_dataset_status()["status"] == "CORRUPT_OR_INCONSISTENT"


def test_lineage_hashes_do_not_fake_full_closure(adapter):
    write(
        adapter.paths.historical / RUN_ID / "registry/symbol_registry.json",
        {"registry_hash": "registry-fixture"},
    )
    write(
        adapter.paths.historical / RUN_ID / "universe/core_universe.json",
        {"universe_hash": "universe-fixture"},
    )
    result = adapter.get_lineage_status()
    assert result["registry_hash"] == "registry-fixture"
    assert result["full_lineage_closure"] == "NOT_VERIFIED"
    assert result["silver_partitions_verified"] is None


def test_prepared_cache_detection_and_corruption(adapter):
    write(
        adapter.paths.cache / ("a" * 64) / "manifest.json",
        {
            "cache_id": "a" * 64,
            "identity": {"configuration_hash": CONFIG_HASH, "gold_dataset_id": GOLD_ID},
            "arrays": {},
            "tables": {},
        },
    )
    broken = adapter.paths.cache / ("b" * 64) / "manifest.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("truncated", encoding="utf-8")
    results = adapter.get_preparation_status()["entries"]
    assert results[0]["status"] == "PUBLISHED_NOT_VALIDATED"
    assert results[1]["status"] == "INCOMPLETE_OR_CORRUPT"
    assert broken.read_text() == "truncated"


def test_training_heartbeat_unknown_fields_stay_unknown(adapter):
    write(
        adapter.paths.logs / RUN_ID / "progress.json",
        {"run_identity": RUN_ID, "stage": "PREPARE", "elapsed_seconds": 123},
    )
    result = adapter.get_training_status()
    assert result["progress"]["stage"] == "PREPARE"
    assert result["actual_device"] is None and result["boosting_iteration"] is None
    write(adapter.paths.logs / RUN_ID / "progress.json", {"run_identity": "OTHER"})
    assert adapter.get_training_status()["status"] == "INCONSISTENT"


def test_regression_report_parsing_never_counts_verified_completion(adapter):
    _, folds, specs = adapter._canonical()
    path = adapter._report_path(folds[0].fold_id, specs[0].name)
    write(
        path,
        {
            "status": "COMPLETE",
            "checkpoint_identity": {
                "configuration_hash": CONFIG_HASH,
                "gold_dataset_id": GOLD_ID,
                "fold_id": folds[0].fold_id,
                "experiment_id": specs[0].name,
                "training_source_identity": adapter.get_project_identity()[
                    "scientific_source_identity"
                ],
            },
            "test_metrics": {"micro": {"mae": 0.01, "rmse": 0.02, "r2": 0.1, "pearson_ic": 0.2}},
            "july_2026_used": False,
            "prospective_holdout_status": "LOCKED_UNUSED",
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
        },
    )
    row = adapter.get_model_results()[0]
    assert row["status"] == "REPORTED_COMPLETE" and row["metrics"]["micro"]["mae"] == 0.01
    assert row["artifact_integrity"] == "NOT_VERIFIED"
    fold = adapter.get_fold_status()[0]
    assert fold["reports_reported_complete"] == 1 and fold["models_verified_complete"] is None


@pytest.mark.parametrize(
    "relative",
    [
        "../outside",
        "/absolute",
        ".env",
        "secrets/key.txt",
        "August/report.json",
        "2026-07/data.csv",
    ],
)
def test_protected_paths_refused(adapter, relative):
    with pytest.raises(ValueError):
        adapter.artifact_path("reports", relative)


def test_artifact_browser_is_read_only_bounded_and_secret_safe(adapter, monkeypatch):
    secret = "synthetic-private-marker-1234567890"
    monkeypatch.setenv("SAMPLE_API_KEY", secret)
    path = adapter.paths.logs / "worker.log"
    path.parent.mkdir(parents=True)
    path.write_text("API_KEY=" + secret + "\nstatus=PREPARE", encoding="utf-8")
    original = path.read_bytes()
    assert secret not in adapter.get_logs("logs", "worker.log")["content"]
    assert adapter.get_artifacts("logs")["entries"][0]["protected"] is True
    assert path.read_bytes() == original
    with pytest.raises(ValueError):
        adapter.artifact_path("gold", "manifest.json")


def test_alias_escape_refused(adapter):
    with pytest.raises(ValueError):
        adapter.artifact_path("reports", "nested/../../outside.json")
    with pytest.raises(ValueError):
        adapter.get_logs("models", "model.joblib")


@pytest.mark.parametrize("branch", ["main", "master", config.SOURCE_BRANCH, "other"])
def test_branch_guard_refuses_scientific_or_other_branches(monkeypatch, branch):
    monkeypatch.setattr(config, "git", lambda *_args: branch)
    with pytest.raises(PermissionError):
        config.require_branch(ROOT)


def test_source_branch_and_scientific_drift_refused(monkeypatch):
    def changed(_root, *args):
        return config.BRANCH if args[0] == "branch" else "OTHER"

    monkeypatch.setattr(config, "git", changed)
    with pytest.raises(PermissionError, match="source branch changed"):
        config.require_branch(ROOT)
    monkeypatch.setattr(
        config,
        "git",
        lambda _root, *args: (
            config.BRANCH
            if args[0] == "branch"
            else SOURCE_HEAD
            if args[0] == "rev-parse"
            else "src/crypto_ai/phase7/models.py"
        ),
    )
    with pytest.raises(PermissionError, match="Scientific source"):
        config.require_branch(ROOT)


def test_job_preview_still_refuses_real_guard_drift(adapter, monkeypatch):
    # Restore the real production guard for this explicit fail-closed test.
    monkeypatch.setattr(jobs, "require_branch", config.require_branch)
    monkeypatch.setattr(
        config,
        "git",
        lambda _root, *args: (
            config.BRANCH
            if args[0] == "branch"
            else SOURCE_HEAD
            if args[0] == "rev-parse"
            else "src/crypto_ai/phase7/models.py"
        ),
    )
    with pytest.raises(PermissionError, match="Scientific source"):
        jobs.preview(request(), adapter)
    assert not adapter.paths.runtime.exists()


def test_typed_scope_rejects_shell_holdout_and_unknown_spec(adapter):
    for kind in ("HOLDOUT_EVALUATE", "shell", "rm -rf", "CRYPTO_FOLD2_TRAIN"):
        with pytest.raises(ValueError):
            request(kind)
    with pytest.raises(ValueError):
        jobs.JobRequest(
            **{**request().model_dump(), "environment": {"PHASE7_ALLOW_CLOUD_RESEARCH": "1"}}
        )
    with pytest.raises(ValueError):
        jobs.preview(
            jobs.JobRequest(**{**request().model_dump(), "spec_id": "../../main"}), adapter
        )


def test_preview_has_exact_command_but_never_starts_a_job(adapter):
    scope = jobs.preview(request(), adapter)
    assert scope["scope_hash"] and scope["approval_required"]
    assert scope["command"][1:3] == ["-m", "integration.crypto_aiventra.operations"]
    assert not adapter.paths.runtime.exists()
    changed = {**scope, "command": ["powershell", "arbitrary"]}
    with pytest.raises(ValueError, match="checksum"):
        jobs.validate_scope(changed, adapter)


def test_heavy_scope_stays_blocked_without_scientific_gate(adapter, monkeypatch):
    monkeypatch.delenv("CRYPTO_ENABLE_SCIENTIFIC_JOBS", raising=False)
    monkeypatch.delenv("CRYPTO_SCIENTIFIC_GATE_REPORT", raising=False)
    scope = jobs.preview(request("CRYPTO_FOLD_TRAIN"), adapter)
    assert scope["execution_blockers"] and "--canary" in scope["command"]
    with pytest.raises(PermissionError):
        jobs.validate_scope(scope, adapter)


def test_scope_source_change_rejected(adapter, monkeypatch):
    scope = jobs.preview(request(), adapter)
    old = adapter.get_project_identity
    monkeypatch.setattr(adapter, "get_project_identity", lambda: {**old(), "git_commit": "OTHER"})
    with pytest.raises(ValueError, match="identity changed"):
        jobs.validate_scope(scope, adapter)


def test_job_submit_requires_exact_owner_proof_and_never_blindly_replays(adapter, monkeypatch):
    monkeypatch.setenv("CRYPTO_ADAPTER_TOKEN", "synthetic-adapter-auth-" + "x" * 32)
    scope = jobs.preview(request(), adapter)
    job_id = str(uuid4())
    with pytest.raises(PermissionError):
        runtime.submit(adapter, job_id, scope, {})
    calls = []
    monkeypatch.setattr(runtime, "launch_worker", lambda args, **_kw: calls.append(args))
    proof = {
        "approval_id": str(uuid4()),
        "owner_id": "owner",
        "org_id": "org",
        "scope_hash": scope["scope_hash"],
        "expires_at": int(time.time()) + 200,
    }
    assert runtime.submit(adapter, job_id, scope, proof)["state"] == "QUEUED"
    assert runtime.submit(adapter, job_id, scope, proof)["state"] == "QUEUED"
    assert len(calls) == 1 and "integration.crypto_aiventra.worker" in calls[0]
    with pytest.raises(ValueError):
        runtime.submit(adapter, job_id, scope, {**proof, "owner_id": "other"})


def test_stale_worker_is_interrupted_without_replay(adapter, monkeypatch):
    monkeypatch.setenv("CRYPTO_ADAPTER_TOKEN", "synthetic-adapter-auth-" + "x" * 32)
    scope, job_id = jobs.preview(request(), adapter), str(uuid4())
    envelope = {"job_id": job_id, "scope": scope, "approval": {}}
    root = runtime.job_directory(adapter, job_id)
    write(root / "request.json", {**envelope, "signature": runtime.signature(envelope)})
    write(
        root / "state.json",
        {
            "job_id": job_id,
            "state": "PREPARING",
            "worker": {"pid": os.getpid(), "process_start_time": 0},
            "heartbeat": 0,
        },
    )
    assert runtime.status(adapter, job_id)["state"] == "INTERRUPTED"
    assert runtime.status(adapter, job_id)["automatic_replay"] is False


def test_missing_completion_receipt_cannot_claim_success(adapter, monkeypatch):
    monkeypatch.setenv("CRYPTO_ADAPTER_TOKEN", "synthetic-adapter-auth-" + "x" * 32)
    scope, job_id = jobs.preview(request(), adapter), str(uuid4())
    envelope = {"job_id": job_id, "scope": scope, "approval": {}}
    root = runtime.job_directory(adapter, job_id)
    write(root / "request.json", {**envelope, "signature": runtime.signature(envelope)})
    write(
        root / "state.json", {"job_id": job_id, "state": "COMPLETED", "completion_verified": True}
    )
    assert runtime.status(adapter, job_id)["state"] == "BLOCKED"
    log = root / "job.log"
    log.write_text("process exit=0, but no result", encoding="utf-8")
    with pytest.raises(ValueError, match="receipt is absent"):
        completion_receipt(adapter, scope, log)


def test_stop_requires_exact_approval_and_preserves_evidence(adapter, monkeypatch):
    monkeypatch.setenv("CRYPTO_ADAPTER_TOKEN", "synthetic-adapter-auth-" + "x" * 32)
    job_id = str(uuid4())
    root = runtime.job_directory(adapter, job_id)
    root.mkdir(parents=True)
    monkeypatch.setattr(
        runtime, "status", lambda *_a: {"state": "TRAINING", "scope_hash": "a" * 64}
    )
    with pytest.raises(PermissionError):
        runtime.stop(adapter, job_id, {})
    result = runtime.stop(
        adapter, job_id, {"job_id": job_id, "scope_hash": "a" * 64, "expires_at": time.time() + 30}
    )
    assert result["state"] == "STOP_REQUESTED"
    assert read_json(root / "control.json")["action"] == "STOP"


def test_redaction_removes_nonfinite_and_sensitive_fields():
    assert redact({"password": "private", "mae": float("nan"), "status": "ok"}) == {
        "mae": None,
        "status": "ok",
    }


def test_control_root_cannot_overlap_protected_scientific_assets(monkeypatch, tmp_path):
    monkeypatch.setenv("CRYPTO_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("CRYPTO_GOLD_ROOT", str(tmp_path / "gold"))
    with pytest.raises(ValueError, match="overlap"):
        CryptoPaths.from_environment()


def test_stale_training_summary_is_not_completion_proof(adapter):
    scope = jobs.preview(request("CRYPTO_FOLD_TRAIN"), adapter)
    write(
        adapter.paths.historical / RUN_ID / "training_summary.json",
        {
            "completed_reports": 48,
            "prospective_holdout_status": "LOCKED_UNUSED",
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
        },
    )
    with pytest.raises(ValueError, match="Independent completion identities"):
        completion_receipt(adapter, scope, adapter.paths.runtime / "absent.log")


def test_artifact_root_cannot_list_market_data(adapter):
    object.__setattr__(adapter.paths, "reports", adapter.paths.gold)
    with pytest.raises(ValueError, match="Market data"):
        adapter.get_artifacts("reports")


def test_revoked_authority_prevents_worker_launch(adapter, monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace

    from integration.crypto_aiventra import worker

    monkeypatch.setenv("CRYPTO_ADAPTER_TOKEN", "synthetic-worker-auth-" + "x" * 32)
    scope, job_id = jobs.preview(request(), adapter), str(uuid4())
    envelope = {"job_id": job_id, "scope": scope, "approval": {"expires_at": time.time() + 200}}
    root = runtime.job_directory(adapter, job_id)
    write(root / "request.json", {**envelope, "signature": runtime.signature(envelope)})
    monkeypatch.setattr(worker, "Crypto2Adapter", lambda: adapter)
    for key, value in adapter.paths.engine_environment().items():
        monkeypatch.setenv(key, value)  # Restore the in-process worker test's environment.
    monkeypatch.setattr(worker, "authority", lambda *_args: False)
    monkeypatch.setattr(
        worker.httpx,
        "Client",
        lambda **_kwargs: nullcontext(SimpleNamespace(post=lambda *_a, **_kw: None)),
    )
    worker.supervise(job_id)
    state = read_json(root / "state.json")
    assert state["state"] == "BLOCKED" and state["completion_verified"] is False
    assert state["exit_code"] is None and not (root / "job.log").exists()


def test_pid_reuse_fence_refuses_signal(monkeypatch):
    from types import SimpleNamespace

    from integration.crypto_aiventra import worker

    monkeypatch.setattr(
        worker.psutil, "Process", lambda *_args: SimpleNamespace(create_time=lambda: 2)
    )
    with pytest.raises(PermissionError, match="PID identity changed"):
        worker.terminate_owned(SimpleNamespace(pid=123), started=1)


def test_approved_path_mapping_cannot_change(adapter):
    scope = jobs.preview(request(), adapter)
    object.__setattr__(adapter.paths, "reports", adapter.paths.reports / "other-run")
    with pytest.raises(ValueError, match="runtime input/output paths changed"):
        jobs.validate_scope(scope, adapter)


def test_approved_gate_bytes_cannot_change(adapter, monkeypatch):
    path = adapter.paths.verification / "gate.json"
    write(path, {"status": "INCOMPLETE"})
    monkeypatch.setenv("CRYPTO_SCIENTIFIC_GATE_REPORT", str(path))
    scope = jobs.preview(request(), adapter)
    write(path, {"status": "CHANGED"})
    with pytest.raises(ValueError, match="verification gate changed"):
        jobs.validate_scope(scope, adapter)


def test_secret_scan_distinguishes_public_environment_indirection():
    from integration.crypto_aiventra.verify_source import secret_values

    assert secret_values({"GITHUB_PUBLICATION_TOKEN_ENV": "AIVENTRA_GITHUB_TOKEN"}) == set()
    assert secret_values(
        {
            "GITHUB_PUBLICATION_TOKEN_ENV": "AIVENTRA_GITHUB_TOKEN",
            "ACTUAL_TOKEN": "AIVENTRA_GITHUB_TOKEN",
        }
    ) == {b"AIVENTRA_GITHUB_TOKEN"}


def test_secret_scan_still_detects_actual_configured_values():
    from integration.crypto_aiventra.verify_source import secret_values

    assert secret_values(
        {"OWNER_PASSWORD": "synthetic-private-password", "JWT_SECRET": "synthetic-private-auth"}
    ) == {b"synthetic-private-password", b"synthetic-private-auth"}


def test_resource_cpu_sample_is_measured_not_initial_zero(adapter, monkeypatch):
    import psutil

    observed = []
    monkeypatch.setattr(
        psutil, "cpu_percent", lambda *, interval: observed.append(interval) or 23.4
    )
    resources = adapter.get_resource_usage()
    assert resources["cpu_percent"] == 23.4 and observed == [0.1]
    assert resources["cpu_sample_seconds"] == 0.1
