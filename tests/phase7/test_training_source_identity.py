from __future__ import annotations

from pathlib import Path

import pytest

from crypto_ai.phase7 import training
from crypto_ai.phase7.artifacts import CheckpointStore, atomic_json


def _single_source_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    source = tmp_path / "critical.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(training, "TRAINING_CRITICAL_SOURCE_FILES", ("critical.py",))
    return tmp_path, source


def test_same_code_is_checkpoint_reusable_and_irrelevant_artifacts_do_not_change_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _source = _single_source_fixture(tmp_path, monkeypatch)
    identity = training.training_source_identity(root)
    assert training.training_source_identity(root) == identity

    (root / "runtime-report.json").write_text('{"timestamp": "later"}\n', encoding="utf-8")
    assert training.training_source_identity(root) == identity

    artifact = atomic_json(root / "artifact.json", {"status": "complete"})
    store = CheckpointStore(root / "checkpoints", "source-identity-test")
    metadata = {"training_source_identity": identity}
    store.complete("train/fold-000", [artifact], metadata)
    assert store.is_complete("train/fold-000", expected_metadata=metadata)


def test_training_critical_source_change_rejects_old_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, source = _single_source_fixture(tmp_path, monkeypatch)
    old_identity = training.training_source_identity(root)
    artifact = atomic_json(root / "artifact.json", {"status": "complete"})
    store = CheckpointStore(root / "checkpoints", "source-change-test")
    store.complete("train/fold-000", [artifact], {"training_source_identity": old_identity})

    source.write_text("VALUE = 2\n", encoding="utf-8")
    new_identity = training.training_source_identity(root)
    assert new_identity["manifest_sha256"] != old_identity["manifest_sha256"]
    assert not store.is_complete(
        "train/fold-000", expected_metadata={"training_source_identity": new_identity}
    )


def test_corrupted_source_identity_is_rejected(tmp_path: Path) -> None:
    artifact = atomic_json(tmp_path / "artifact.json", {"status": "complete"})
    store = CheckpointStore(tmp_path / "checkpoints", "corrupt-identity-test")
    valid = {
        "training_source_identity": {
            "algorithm": training.TRAINING_SOURCE_IDENTITY_ALGORITHM,
            "files": [{"path": "critical.py", "sha256": "a" * 64}],
            "manifest_sha256": "b" * 64,
        }
    }
    store.complete("train/fold-000", [artifact], valid)
    corrupt = {
        "training_source_identity": {
            **valid["training_source_identity"],
            "manifest_sha256": "0" * 64,
        }
    }
    assert not store.is_complete("train/fold-000", expected_metadata=corrupt)


def test_missing_training_critical_source_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(training, "TRAINING_CRITICAL_SOURCE_FILES", ("missing.py",))
    with pytest.raises(RuntimeError, match="training-critical source file is missing"):
        training.training_source_identity(tmp_path)
