"""CHANGED BY CLAUDE (2026-11-06, closure): one admission function for every official path."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from crypto_ai.phase7.admission import (
    CANONICAL_ENTRYPOINTS,
    AdmissionError,
    admit_official_training,
    assert_backend_admitted,
    reject_noncanonical,
)
from crypto_ai.phase7.backend import resolve_lightgbm_backend
from crypto_ai.phase7.config import Phase7Config, load_phase7_config

ROOT = Path(__file__).parents[2]
CONFIG = ROOT / "configs/phase7/research_core20_primary_v1.toml"


@pytest.fixture
def smoke_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> pytest.MonkeyPatch:
    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    monkeypatch.setenv("PHASE7_MIN_FREE_DISK_GIB", "1")
    monkeypatch.setenv("PHASE7_CACHE_MODE", "read_only")
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    monkeypatch.setenv("PHASE7_MODEL_PARALLELISM", "1")
    monkeypatch.setenv("PHASE7_TOTAL_CPU_THREADS", "1")
    from crypto_ai.phase7 import run_contract, runtime

    monkeypatch.setattr(
        runtime,
        "system_snapshot",
        lambda _: {
            "ram_total_bytes": 64 * 1024**3,
            "cpu_count": 8,
            "disk_total_bytes": 150_000_000_000,
        },
    )

    # Synthetic owner contract for admission unit tests only, never a real-run approval.
    monkeypatch.setattr(run_contract, "approval_binding", lambda *args: {"fixture": "one-smoke"})
    approval = tmp_path / "test-only-approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema": "phase7_owner_smoke_approval_v1",
                "status": "APPROVED",
                "owner": "unit test fixture",
                "binding": {"fixture": "one-smoke"},
                "mode": "train",
                "stop_deadline_utc": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "cost_ceiling": 1,
                "cost_currency": "USD",
            }
        )
    )
    monkeypatch.setenv("PHASE7_OWNER_APPROVAL_FILE", str(approval))
    return monkeypatch


def _admit(tmp_path: Path, **kwargs):
    config = load_phase7_config(CONFIG)
    defaults = {
        "entrypoint": "benchmark_one_spec",
        "config": config,
        "mode": "train",
        "output_root": tmp_path / "isolated",
        "smoke": True,
    }
    defaults.update(kwargs)
    return admit_official_training(**defaults)


def test_generic_phase7_research_is_not_a_training_entrypoint() -> None:
    with pytest.raises(AdmissionError, match="NON_CANONICAL_RESEARCH_ENTRYPOINT"):
        reject_noncanonical("crypto-ai phase7-research")
    assert {"benchmark_one_spec", "run_phase7a_pipeline"} == CANONICAL_ENTRYPOINTS


@pytest.mark.parametrize("stage", ["train", None])
def test_run_phase7_cloud_refuses_training_stages(monkeypatch, stage) -> None:
    from crypto_ai.phase7.pipeline import run_phase7_cloud

    monkeypatch.setenv("PHASE7_ALLOW_CLOUD_RESEARCH", "1")
    with pytest.raises(AdmissionError, match="NON_CANONICAL_RESEARCH_ENTRYPOINT"):
        run_phase7_cloud(Phase7Config(), stage=stage, resume=False)


def test_noncanonical_entrypoint_fails_before_any_other_check(tmp_path, smoke_env) -> None:
    with pytest.raises(AdmissionError, match="NON_CANONICAL_RESEARCH_ENTRYPOINT"):
        _admit(tmp_path, entrypoint="python -c train")


def test_cpu_smoke_is_admitted_with_a_full_record(tmp_path, smoke_env) -> None:
    record = _admit(tmp_path)
    assert record["status"] == "ADMITTED" and record["backend"] == "cpu"
    assert record["model_parallelism"] == 1 and record["smoke"] is True
    assert record["holdout"]["prospective_holdout_status"] == "LOCKED_UNUSED"
    assert record["holdout"]["prospective_holdout_used"] is False
    assert record["selection_protocol_version"] == "phase7_selection_chronology_v1"
    assert len(record["experiment_control_identity"]) == 64
    assert record["resolved_configuration"] == load_phase7_config(CONFIG).model_dump(mode="json")
    assert record["hardening_settings"]
    assert record["resource_floors_gib"] == {"available_ram": 1, "free_disk": 1}
    assert record["runtime_paths"] and record["compute_budget"] and record["owner_approval"]


@pytest.mark.parametrize("device", ["gpu", "cuda"])
def test_gpu_request_fails_closed_for_the_cpu_smoke(tmp_path, smoke_env, device) -> None:
    smoke_env.setenv("PHASE7_LGBM_DEVICE", device)
    with pytest.raises(AdmissionError, match="SMOKE_REQUIRES_CPU"):
        _admit(tmp_path)


def test_a_second_logical_worker_is_refused_for_the_smoke(tmp_path, smoke_env) -> None:
    smoke_env.setenv("PHASE7_TOTAL_CPU_THREADS", "2")
    smoke_env.setenv("PHASE7_MODEL_PARALLELISM", "2")
    with pytest.raises(AdmissionError, match="SMOKE_REQUIRES_ONE_WORKER"):
        _admit(tmp_path)


@pytest.mark.parametrize(
    "name,value",
    [
        ("PHASE7_CACHE_MODE", "auto"),  # implicit preparation during training
        ("PHASE7_CACHE_MODE", "rebuild"),
    ],
)
def test_training_requires_a_read_only_cache(tmp_path, smoke_env, name, value) -> None:
    smoke_env.setenv(name, value)
    with pytest.raises(AdmissionError, match="RUNTIME_CONTRACT"):
        _admit(tmp_path)


def test_missing_ram_or_disk_floor_is_refused(tmp_path, smoke_env) -> None:
    smoke_env.delenv("PHASE7_MIN_FREE_RAM_GIB")
    with pytest.raises(AdmissionError, match="RUNTIME_CONTRACT"):
        _admit(tmp_path)
    smoke_env.setenv("PHASE7_MIN_FREE_RAM_GIB", "1")
    smoke_env.delenv("PHASE7_MIN_FREE_DISK_GIB")
    with pytest.raises(AdmissionError, match="RUNTIME_CONTRACT"):
        _admit(tmp_path)


def test_preparation_mode_needs_a_writable_cache_mode(tmp_path, smoke_env) -> None:
    with pytest.raises(AdmissionError, match="RUNTIME_CONTRACT"):
        _admit(tmp_path, mode="prepare")  # cache is read_only
    smoke_env.setenv("PHASE7_CACHE_MODE", "auto")
    import os

    path = Path(os.environ["PHASE7_OWNER_APPROVAL_FILE"])
    approval = json.loads(path.read_text())
    approval["mode"] = "prepare"
    path.write_text(json.dumps(approval))
    assert _admit(tmp_path, mode="prepare")["mode"] == "prepare"


def test_output_root_must_be_isolated_from_the_production_artifact_root(tmp_path, smoke_env):
    from crypto_ai.phase7.runtime import RuntimePaths

    production = RuntimePaths.resolve(load_phase7_config(CONFIG).paths).artifact_root
    with pytest.raises(AdmissionError, match="OUTPUT_ROOT_NOT_ISOLATED"):
        _admit(tmp_path, output_root=production)
    with pytest.raises(AdmissionError, match="OUTPUT_ROOT_REQUIRED"):
        _admit(tmp_path, output_root=None)


def test_unapproved_config_is_refused(tmp_path, smoke_env) -> None:
    other = Phase7Config()
    assert other.configuration_hash != "93f987736b1a79d26b773957"
    with pytest.raises(AdmissionError, match="CONFIG_NOT_APPROVED"):
        _admit(tmp_path, config=other)


def test_gpu_backend_needs_an_approved_qualification_file(tmp_path, monkeypatch) -> None:
    gpu = resolve_lightgbm_backend("gpu")
    monkeypatch.delenv("PHASE7_GPU_APPROVAL_FILE", raising=False)
    with pytest.raises(AdmissionError, match="GPU_NOT_QUALIFIED"):
        assert_backend_admitted(gpu)
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"status": "COMPUTED", "evidence_hash": "x"}))
    monkeypatch.setenv("PHASE7_GPU_APPROVAL_FILE", str(approval))
    with pytest.raises(AdmissionError, match="GPU_NOT_QUALIFIED"):
        assert_backend_admitted(gpu)
    approval.write_text(json.dumps({"status": "APPROVED", "evidence_hash": "abc"}))
    assert_backend_admitted(gpu)  # explicit recorded approval
    assert_backend_admitted(resolve_lightgbm_backend("cpu"))  # CPU is never blocked


def test_every_official_entrypoint_uses_the_shared_admission_function() -> None:
    entrypoints = ("src/crypto_ai/phase7/benchmark_one_spec.py", "scripts/run_phase7a_pipeline.py")
    for relative in entrypoints:
        assert "admit_official_training" in (ROOT / relative).read_text(), relative
    training = (ROOT / "src/crypto_ai/phase7/training.py").read_text()
    assert "assert_backend_admitted(resolve_lightgbm_backend())" in training


def test_missing_owner_contract_refuses_real_execution(tmp_path, smoke_env):
    smoke_env.delenv("PHASE7_OWNER_APPROVAL_FILE")
    with pytest.raises(AdmissionError, match="OWNER_APPROVAL_REQUIRED"):
        _admit(tmp_path)


def test_unknown_environment_and_full_grid_are_refused(tmp_path, smoke_env):
    smoke_env.setenv("PHASE7_CAHCE_MODE", "read_only")
    with pytest.raises(AdmissionError, match="UNKNOWN_PHASE7_ENVIRONMENT"):
        _admit(tmp_path)
    smoke_env.delenv("PHASE7_CAHCE_MODE")
    with pytest.raises(AdmissionError, match="FULL_GRID_NOT_AUTHORIZED"):
        _admit(tmp_path, smoke=False)
