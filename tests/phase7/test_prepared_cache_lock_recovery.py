"""Stale prepared-cache publication lock recovery (defect 9).

No test signals or kills a real worker: dead owners are short-lived children that
exit by themselves before the lock is examined.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import psutil
import pytest

from crypto_ai.phase7.prepared_cache import PreparedDataCache

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX advisory-lock recovery")

SCHEMA = "phase7_cache_publication_lock_v1"


def _cache(tmp_path: Path) -> PreparedDataCache:
    return PreparedDataCache(tmp_path, "auto")


def _write_lock(tmp_path: Path, **overrides: object) -> Path:
    owner: dict[str, object] = {
        "schema": SCHEMA,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "process_start_time": psutil.Process().create_time(),
        "created_at": "2026-11-01T00:00:00+00:00",
        "token": "owner-token",
    }
    owner.update(overrides)
    lock = tmp_path / ".publication.lock"
    lock.write_text(json.dumps(owner), encoding="utf-8")
    return lock


def _dead_child_identity() -> tuple[int, float]:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        start = psutil.Process(child.pid).create_time()
    except psutil.NoSuchProcess:
        start = 1.0
    child.wait(timeout=30)
    return child.pid, start


def test_live_owner_is_never_broken(tmp_path: Path) -> None:
    lock = _write_lock(tmp_path)
    before = lock.read_bytes()
    with pytest.raises(TimeoutError), _cache(tmp_path)._publication_lock(
        "publication", timeout_seconds=0.3
    ):
        pass
    assert lock.read_bytes() == before


def test_dead_owner_lock_is_archived_and_acquired(tmp_path: Path) -> None:
    pid, start = _dead_child_identity()
    lock = _write_lock(tmp_path, pid=pid, process_start_time=start)
    with _cache(tmp_path)._publication_lock("publication", timeout_seconds=5.0):
        held = json.loads(lock.read_text(encoding="utf-8"))
        assert held["pid"] == os.getpid() and held["token"] != "owner-token"
    assert not lock.exists()
    archived = list(tmp_path.glob(".publication.stale.*"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text(encoding="utf-8"))["token"] == "owner-token"


def test_reused_pid_with_different_start_time_counts_as_dead(tmp_path: Path) -> None:
    _write_lock(tmp_path, process_start_time=psutil.Process().create_time() - 10_000.0)
    with _cache(tmp_path)._publication_lock("publication", timeout_seconds=5.0):
        pass
    assert len(list(tmp_path.glob(".publication.stale.*"))) == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"hostname": "some-other-pod"},
        {"process_start_time": None},
        {"schema": "unknown"},
    ],
)
def test_unprovable_liveness_fails_closed(tmp_path: Path, overrides: dict[str, object]) -> None:
    # A pid that is gone is dead whatever else is recorded, so use a dead pid only for
    # cases where the *other* evidence is what makes liveness unprovable. A live pid with
    # no recorded start time cannot be told apart from a reused pid: unprovable.
    pid = os.getpid() if overrides.get("process_start_time", 0) is None else _dead_child_identity()[0]
    lock = _write_lock(tmp_path, pid=pid, **overrides)
    before = lock.read_bytes()
    with pytest.raises(TimeoutError), _cache(tmp_path)._publication_lock(
        "publication", timeout_seconds=0.3
    ):
        pass
    assert lock.read_bytes() == before
    assert not list(tmp_path.glob(".publication.stale.*"))


@pytest.mark.parametrize("content", [b"pid=12345\n", b"", b"{not json", b"[1, 2]"])
def test_legacy_or_corrupt_lock_content_is_never_deleted(tmp_path: Path, content: bytes) -> None:
    lock = tmp_path / ".publication.lock"
    lock.write_bytes(content)
    with pytest.raises(TimeoutError), _cache(tmp_path)._publication_lock(
        "publication", timeout_seconds=0.3
    ):
        pass
    assert lock.read_bytes() == content


def test_release_removes_only_its_own_lock(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    with cache._publication_lock("publication", timeout_seconds=1.0):
        lock = tmp_path / ".publication.lock"
        lock.write_text(json.dumps({"schema": SCHEMA, "token": "someone-else"}), encoding="utf-8")
    assert json.loads(lock.read_text(encoding="utf-8"))["token"] == "someone-else"


def test_normal_release_leaves_no_lock(tmp_path: Path) -> None:
    with _cache(tmp_path)._publication_lock("publication", timeout_seconds=1.0):
        assert (tmp_path / ".publication.lock").exists()
    assert not list(tmp_path.glob("*.lock"))
