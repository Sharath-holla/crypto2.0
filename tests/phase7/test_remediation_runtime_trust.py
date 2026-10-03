from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai.data.storage import file_sha256
from crypto_ai.phase7 import preflight, training
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json, checkpoint_metadata_compatible
from crypto_ai.phase7.config import Phase7Config, stable_hash
from crypto_ai.phase7.runtime import resolve_runtime_input_path
from scripts import run_phase7a_lightning


def test_legacy_source_input_remapping_preserves_bytes_and_refuses_root_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "persistent" / "data" / "silver.json"
    source.parent.mkdir(parents=True)
    source.write_text('{"status":"PASS"}', encoding="utf-8")
    before = file_sha256(source)
    monkeypatch.setenv("PHASE7_DATA_ROOT", str(source.parent))
    monkeypatch.setenv("PHASE7_LEGACY_DATA_ROOT", "/historical/repo/data")
    mapped = resolve_runtime_input_path("/historical/repo/data/silver.json")
    assert mapped == source
    assert file_sha256(mapped) == before
    with pytest.raises(ValueError, match="escaped"):
        resolve_runtime_input_path("/historical/repo/data/../outside.json")


def test_legacy_absolute_checkpoint_maps_without_rewriting_evidence(tmp_path: Path) -> None:
    artifact = atomic_json(tmp_path / "new-artifacts" / "result.json", {"status": "complete"})
    store = CheckpointStore(
        tmp_path / "checkpoints", "run", legacy_roots=(("/legacy/artifacts", artifact.parent),)
    )
    payload = {
        "status": "complete",
        "run_identity": "run",
        "stage": "train",
        "files": [{"path": "/legacy/artifacts/result.json", "sha256": file_sha256(artifact)}],
        "metadata": {"gold_dataset_id": "gold"},
    }
    payload["checkpoint_hash"] = stable_hash(payload)
    path = atomic_json(store.checkpoint_path("train"), payload)
    before = path.read_bytes()
    assert store.is_complete("train", expected_metadata={"gold_dataset_id": "gold"})
    assert path.read_bytes() == before
    artifact.write_text("changed", encoding="utf-8")
    assert not store.is_complete("train")


def test_execution_context_differences_do_not_change_resume_compatibility() -> None:
    science = {"gold_dataset_id": "gold", "model_backend_semantics": "cpu"}
    actual = {**science, "execution_context": {"driver": "different", "path": "/other"}}
    assert checkpoint_metadata_compatible(actual, science)
    assert not checkpoint_metadata_compatible({**actual, "gold_dataset_id": "other"}, science)


def test_top_level_training_resume_cannot_bypass_scientific_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    monkeypatch.setattr(training, "training_source_identity", lambda: {"manifest_sha256": "source"})
    metadata = {
        "scientific_resume_identity": training.training_stage_resume_identity(),
        "execution_context": {"driver": "other", "git_commit": "docs-only"},
    }
    training.validate_training_stage_resume(metadata)
    with pytest.raises(ValueError, match="per-model checkpoint review"):
        training.validate_training_stage_resume({"completed_reports": 48})
    monkeypatch.setattr(
        training, "training_source_identity", lambda: {"manifest_sha256": "changed"}
    )
    with pytest.raises(ValueError, match="incompatible scientific identity"):
        training.validate_training_stage_resume(metadata)


def test_top_level_training_resume_rejects_changed_gold_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    monkeypatch.setattr(training, "training_source_identity", lambda: {"manifest_sha256": "source"})
    monkeypatch.setattr(training, "_load_gold_manifest", lambda _: {"dataset_id": "gold"})
    path = tmp_path / "gold.json"
    path.write_text("original", encoding="utf-8")
    config = Phase7Config()
    metadata = {
        "scientific_resume_identity": training.training_stage_resume_identity(
            config=config,
            gold_manifest_path=path,
        )
    }
    training.validate_training_stage_resume(metadata, config=config, gold_manifest_path=path)
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible scientific identity"):
        training.validate_training_stage_resume(metadata, config=config, gold_manifest_path=path)


def test_preflight_refuses_unverified_gold_hash_report(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "dataset_id": "gold",
                "manifest_sha256": "sha",
                "holdout_status": "LOCKED_UNUSED",
                "partition_hashes_verified": False,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="stale, or incompatible"):
        preflight._validated_gold_report(path, dataset_id="gold", manifest_sha256="sha")


def test_preflight_no_create_handles_missing_roots_without_creating_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable in run_phase7a_lightning.REQUIRED_RUNTIME_VARIABLES:
        if variable.endswith("_ROOT"):
            monkeypatch.setenv(variable, str(tmp_path / variable))
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    monkeypatch.setenv("PHASE7_LGBM_DEVICE", "cpu")
    report = preflight.build_preflight_report(
        Path("configs/phase7/research_core20_primary_v1.toml"),
        create_outputs=False,
        run_backend_smoke=False,
    )
    assert report["status"] == "FAIL"
    assert report["training_readiness"] == "NOT_READY"
    assert not list(tmp_path.iterdir())


def test_runtime_model_and_report_overrides_preserve_config_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = Phase7Config()
    identity = config.configuration_hash
    monkeypatch.setenv("PHASE7_MODEL_ROOT", str(tmp_path / "models"))
    monkeypatch.setenv("PHASE7_REPORT_ROOT", str(tmp_path / "reports"))
    run = tmp_path / "artifacts" / "run-identity"
    assert training.experiment_output_root(run, kind="model", config=config) == (
        tmp_path / "models" / "run-identity" / "models"
    )
    assert training.experiment_output_root(run, kind="report", config=config) == (
        tmp_path / "reports" / "run-identity" / "models"
    )
    assert config.configuration_hash == identity


def test_lightning_entrypoint_requires_explicit_runtime_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in run_phase7a_lightning.REQUIRED_RUNTIME_VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr("sys.argv", ["run_phase7a_lightning"])
    with pytest.raises(RuntimeError, match="runtime variables are required"):
        run_phase7a_lightning.main()
