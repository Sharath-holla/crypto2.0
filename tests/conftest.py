"""Shared pytest fixtures (added by Claude, 2026-11-02, finding L-08)."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_model_hash_registry(tmp_path_factory, monkeypatch):
    """Keep every test's model hash registry out of the real home directory."""

    from crypto_ai.phase7.model_registry import REGISTRY_ENV

    monkeypatch.setenv(REGISTRY_ENV, str(tmp_path_factory.mktemp("model-hash-registry")))
    monkeypatch.delenv("PHASE7_REQUIRE_MODEL_REGISTRY", raising=False)
