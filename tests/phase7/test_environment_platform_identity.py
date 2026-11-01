"""M-09: numerical artifacts are bound to the OS family and architecture (defect 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_ai.phase7 import environment


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "uv.lock").write_text("lock\n", encoding="utf-8")
    monkeypatch.setattr(environment, "version", lambda name: f"1.0.0+{name}")
    return tmp_path


def _identity(repository: Path, monkeypatch: pytest.MonkeyPatch, system: str, machine: str) -> str:
    monkeypatch.setattr(environment.platform, "system", lambda: system)
    monkeypatch.setattr(environment.platform, "machine", lambda: machine)
    return environment.scientific_environment_identity(repository)["identity"]


def test_identity_is_stable_for_identical_platform(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _identity(repository, monkeypatch, "Linux", "x86_64") == _identity(
        repository, monkeypatch, "Linux", "x86_64"
    )


@pytest.mark.parametrize(
    ("other_system", "other_machine"),
    [("Darwin", "arm64"), ("Linux", "aarch64"), ("Darwin", "x86_64"), ("Windows", "AMD64")],
)
def test_other_platforms_are_not_production_compatible(
    repository: Path, monkeypatch: pytest.MonkeyPatch, other_system: str, other_machine: str
) -> None:
    production = _identity(repository, monkeypatch, "Linux", "x86_64")
    assert _identity(repository, monkeypatch, other_system, other_machine) != production


def test_payload_records_platform_and_excludes_resource_observations(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(environment.platform, "system", lambda: "Linux")
    monkeypatch.setattr(environment.platform, "machine", lambda: "x86_64")
    payload = environment.scientific_environment_identity(repository)
    assert payload["numerical_platform"]["system"] == "Linux"
    assert payload["numerical_platform"]["machine"] == "x86_64"
    assert payload["schema"] == "phase7_dependency_platform_compatibility_v2"
    for forbidden in ("hostname", "ram", "disk", "gpu", "cpu_count"):
        assert forbidden not in str(payload).lower()
