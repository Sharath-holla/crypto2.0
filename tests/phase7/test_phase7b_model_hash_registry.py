"""Added by Claude (2026-11-02, finding L-08): pickled models load only if their hash matches."""

from __future__ import annotations

import pytest

from crypto_ai.phase7.model_registry import (
    ModelRegistryError,
    register_model_hash,
    registry_root,
    verify_registered_model,
)
from crypto_ai.phase7.models import load_model


def test_registered_model_verifies_and_tampering_is_refused(tmp_path) -> None:
    model = tmp_path / "models" / "model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"original-bytes")
    register_model_hash(model)
    assert verify_registered_model(model) == "VERIFIED"
    model.write_bytes(b"tampered-bytes")
    with pytest.raises(ModelRegistryError, match="does not match"):
        verify_registered_model(model)


def test_load_model_refuses_a_mismatched_file_before_unpickling(tmp_path) -> None:
    model = tmp_path / "models" / "model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"not a real pickle")
    register_model_hash(model)
    model.write_bytes(b"swapped file")
    with pytest.raises(ModelRegistryError):  # raised before joblib ever sees the bytes
        load_model(model)


def test_unregistered_is_allowed_unless_required(tmp_path, monkeypatch) -> None:
    model = tmp_path / "m.joblib"
    model.write_bytes(b"x")
    assert verify_registered_model(model) == "UNREGISTERED"
    monkeypatch.setenv("PHASE7_REQUIRE_MODEL_REGISTRY", "1")
    with pytest.raises(ModelRegistryError, match="not in the hash registry"):
        verify_registered_model(model)


def test_registry_inside_the_model_folder_is_refused(tmp_path) -> None:
    model = tmp_path / "models" / "model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"x")
    with pytest.raises(ModelRegistryError, match="outside the model folder"):
        register_model_hash(model, root=tmp_path)


def test_registry_default_is_outside_any_run_folder(monkeypatch) -> None:
    monkeypatch.delenv("PHASE7_MODEL_HASH_REGISTRY", raising=False)
    assert registry_root().name == "model_hash_registry"


def test_fresh_publish_keeps_previous_hashes(tmp_path) -> None:
    model = tmp_path / "models" / "model.joblib"
    model.parent.mkdir()
    model.write_bytes(b"v1")
    record = register_model_hash(model)
    model.write_bytes(b"v2")
    register_model_hash(model)
    assert verify_registered_model(model) == "VERIFIED"
    assert len(__import__("json").loads(record.read_text())["previous_sha256"]) == 1
