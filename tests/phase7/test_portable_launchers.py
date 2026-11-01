"""Launchers must not embed host paths or GNU-only assumptions (defect 13)."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIBRARY = ROOT / "scripts" / "lib" / "phase7_portable.sh"
LAUNCHERS = (
    ROOT / "scripts" / "run_phase7a_worker.sh",
    ROOT / "scripts" / "run_phase7_worker.sh",
    ROOT / "scripts" / "rotate_phase7_run_log.sh",
)

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX shell launchers")


def _bash(snippet: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "{LIBRARY}"; {snippet}'],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _executable(path: Path, body: str = "#!/usr/bin/env bash\nexit 0\n") -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_launchers_contain_no_host_specific_paths_or_gnu_only_calls() -> None:
    for script in (*LAUNCHERS, LIBRARY):
        text = script.read_text(encoding="utf-8")
        assert "/home/nssharath123" not in text, script.name
        assert "stat -c" not in text, script.name
        assert "gcloud" not in text and "systemctl" not in text and "sudo" not in text
    for script in LAUNCHERS[:2]:
        text = script.read_text(encoding="utf-8")
        assert "/usr/bin/time -v" not in text, script.name


def test_uv_is_resolved_from_path(tmp_path: Path) -> None:
    uv = _executable(tmp_path / "uv")
    result = _bash("phase7_resolve_uv", {"PATH": f"{tmp_path}:/usr/bin:/bin"})
    assert result.returncode == 0
    assert result.stdout.strip() == str(uv)


def test_validated_environment_variable_wins_over_path(tmp_path: Path) -> None:
    chosen = _executable(tmp_path / "custom-uv")
    result = _bash("phase7_resolve_uv", {"PATH": "/usr/bin:/bin", "PHASE7_UV_BIN": str(chosen)})
    assert result.returncode == 0 and result.stdout.strip() == str(chosen)


@pytest.mark.parametrize("kind", ["missing", "directory", "not-executable"])
def test_invalid_uv_override_fails_closed_without_falling_back(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "uv-override"
    if kind == "directory":
        path.mkdir()
    elif kind == "not-executable":
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o644)
    _executable(tmp_path / "uv")  # present on PATH, must not be used
    result = _bash(
        "phase7_resolve_uv",
        {"PATH": f"{tmp_path}:/usr/bin:/bin", "PHASE7_UV_BIN": str(path)},
    )
    assert result.returncode != 0 and result.stdout.strip() == ""
    assert "PHASE7_UV_BIN" in result.stderr


def test_missing_uv_fails_with_actionable_message(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run(
        ["/bin/bash", "-c", f'source "{LIBRARY}"; phase7_resolve_uv'],
        env={"PATH": str(empty)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "PHASE7_UV_BIN" in result.stderr


def test_file_size_uses_no_gnu_stat(tmp_path: Path) -> None:
    sample = tmp_path / "sample.log"
    sample.write_bytes(b"x" * 1234)
    result = _bash(f'phase7_file_size "{sample}"', {"PATH": "/usr/bin:/bin"})
    assert result.stdout.strip() == "1234"
    missing = _bash(f'phase7_file_size "{tmp_path}/absent"', {"PATH": "/usr/bin:/bin"})
    assert missing.stdout.strip() == "0"


def test_gnu_time_prefix_is_empty_when_unavailable_and_set_when_usable(tmp_path: Path) -> None:
    unavailable = _bash(
        'phase7_gnu_time_prefix "$1"',
        {"PATH": "/usr/bin:/bin", "PHASE7_GNU_TIME_BIN": str(tmp_path / "no-time")},
    )
    assert unavailable.returncode == 0 and unavailable.stdout.strip() == ""
    bsd_like = _executable(tmp_path / "bsd-time", "#!/usr/bin/env bash\nexit 64\n")
    rejected = _bash(
        'phase7_gnu_time_prefix "$1"',
        {"PATH": "/usr/bin:/bin", "PHASE7_GNU_TIME_BIN": str(bsd_like)},
    )
    assert rejected.stdout.strip() == ""
    gnu_like = _executable(tmp_path / "gnu-time")
    accepted = _bash(
        f'phase7_gnu_time_prefix "{tmp_path}/usage.txt"',
        {"PATH": "/usr/bin:/bin", "PHASE7_GNU_TIME_BIN": str(gnu_like)},
    )
    assert accepted.stdout.strip() == f"{gnu_like} -v -o {tmp_path}/usage.txt"


@pytest.mark.parametrize("script", LAUNCHERS, ids=lambda path: path.name)
def test_launchers_are_syntactically_valid_bash(script: Path) -> None:
    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0
