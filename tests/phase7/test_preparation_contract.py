"""Preparation-only admission contract (no fits, cache must be writable)."""

from __future__ import annotations

import pytest

from crypto_ai.phase7.resources import (
    require_preparation_runtime_contract,
    require_training_runtime_contract,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PHASE7_CACHE_MODE", "PHASE7_MIN_FREE_RAM_GIB", "PHASE7_MIN_AVAILABLE_RAM_GB"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("mode", ["auto", "rebuild"])
def test_preparation_accepts_writable_cache_modes(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "4")
    monkeypatch.setenv("PHASE7_CACHE_MODE", mode)
    require_preparation_runtime_contract()


@pytest.mark.parametrize("mode", ["read_only", "disabled"])
def test_preparation_rejects_modes_that_cannot_publish(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "4")
    monkeypatch.setenv("PHASE7_CACHE_MODE", mode)
    with pytest.raises(ValueError, match="auto or rebuild"):
        require_preparation_runtime_contract()


def test_preparation_requires_explicit_positive_ram_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    with pytest.raises(ValueError, match="PHASE7_MIN_FREE_RAM_GIB"):
        require_preparation_runtime_contract()


def test_training_still_refuses_implicit_preparation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHASE7_MIN_FREE_RAM_GIB", "4")
    monkeypatch.setenv("PHASE7_CACHE_MODE", "auto")
    with pytest.raises(ValueError, match="read_only"):
        require_training_runtime_contract()
