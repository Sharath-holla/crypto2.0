"""Regression tests for ``scripts/rotate_phase7_run_log.sh``.

The rotation must bound log growth without ever losing evidence or blocking
worker startup.
"""

from __future__ import annotations

import gzip
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROTATE_SCRIPT = REPO_ROOT / "scripts" / "rotate_phase7_run_log.sh"


def _run_rotate(log_path: Path, mb: int = 1, keep: int = 2) -> int:
    env = dict(os.environ)
    env["PHASE7_LOG_ROTATE_MB"] = str(mb)
    env["PHASE7_LOG_ROTATE_KEEP"] = str(keep)
    result = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), str(log_path)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return result.returncode


def _read_gz(path: Path) -> bytes:
    with gzip.open(path, "rb") as fh:
        return fh.read()


def test_large_log_is_rotated_and_preserved(tmp_path: Path) -> None:
    log = tmp_path / "phase7-cloud-run.log"
    payload = b"evidence-line\n" * 120_000  # ~1.7 MB, above the 1 MB threshold
    log.write_bytes(payload)
    assert _run_rotate(log, mb=1) == 0
    # Live log moved away (worker's tee will recreate it); archive holds data.
    assert not log.exists()
    archive = tmp_path / "phase7-cloud-run.log.1.gz"
    assert archive.exists()
    assert _read_gz(archive) == payload


def test_generations_shift_and_oldest_drops(tmp_path: Path) -> None:
    log = tmp_path / "phase7-cloud-run.log"
    log.write_bytes(b"x" * (2 * 1024 * 1024))
    (tmp_path / "phase7-cloud-run.log.1.gz").write_bytes(b"oldest-generation")
    assert _run_rotate(log, mb=1, keep=2) == 0
    # Previous .1.gz moved to .2.gz; new .1.gz is the rotated log.
    assert (tmp_path / "phase7-cloud-run.log.2.gz").read_bytes() == b"oldest-generation"
    assert (tmp_path / "phase7-cloud-run.log.1.gz").exists()
    assert not (tmp_path / "phase7-cloud-run.log.3.gz").exists()
    # Third rotation: .2.gz drops off entirely.
    log.write_bytes(b"y" * (2 * 1024 * 1024))
    assert _run_rotate(log, mb=1, keep=2) == 0
    assert not (tmp_path / "phase7-cloud-run.log.3.gz").exists()


def test_small_log_is_left_untouched(tmp_path: Path) -> None:
    log = tmp_path / "phase7-cloud-run.log"
    log.write_bytes(b"small")
    assert _run_rotate(log, mb=512) == 0
    assert log.read_bytes() == b"small"
    assert not (tmp_path / "phase7-cloud-run.log.1.gz").exists()


def test_missing_log_is_a_noop(tmp_path: Path) -> None:
    assert _run_rotate(tmp_path / "does-not-exist.log") == 0


def test_rotation_failure_restores_live_log(tmp_path: Path) -> None:
    """If compression fails, the original log must be restored intact."""
    log = tmp_path / "phase7-cloud-run.log"
    payload = b"z" * (2 * 1024 * 1024)
    log.write_bytes(payload)
    # Force gzip to fail while mv/stat/pgrep still work: prepend a fake bin
    # dir whose gzip exits non-zero.
    fake_bin = tmp_path / "fakebin"
    fake_bin.mkdir()
    (fake_bin / "gzip").write_text("#!/usr/bin/env bash\nexit 1\n")
    (fake_bin / "gzip").chmod(0o755)
    env = dict(os.environ)
    env["PHASE7_LOG_ROTATE_MB"] = "1"
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        ["bash", str(ROTATE_SCRIPT), str(log)],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
    assert log.exists()
    assert log.read_bytes() == payload
    assert not (tmp_path / "phase7-cloud-run.log.1.gz").exists()