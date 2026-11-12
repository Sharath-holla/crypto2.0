"""Run-lease creation must not depend on flock alone (defect 10)."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import psutil
import pytest

from crypto_ai.phase7 import run_lease
from crypto_ai.phase7.run_lease import RunLease, RunLeaseError, owner_liveness


def test_o_excl_arbitrates_when_flock_is_ineffective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate NFS-like advisory locks that never conflict and a stale exists() check."""
    root = tmp_path / "run"
    monkeypatch.setattr(run_lease, "_lock", lambda _descriptor: None)
    original_exists = Path.exists
    with RunLease(root, root.name, {"science": "one"}, mode="production") as first:
        before = first.path.read_bytes()
        monkeypatch.setattr(
            Path,
            "exists",
            lambda self: False if self.name == ".phase7-run-lease.json" else original_exists(self),
        )
        with pytest.raises(RunLeaseError, match="retained lease evidence"):
            RunLease(root, root.name, {"science": "one"}, mode="production").__enter__()
        assert first.path.read_bytes() == before
    monkeypatch.undo()
    assert not (root / ".phase7-run-lease.json").exists()


def test_lease_records_complete_owner_identity(tmp_path: Path) -> None:
    root = tmp_path / "run"
    with RunLease(root, root.name, {"science": "x"}, mode="production") as lease:
        owner = json.loads(lease.path.read_text(encoding="utf-8"))
    assert owner["pid"] == os.getpid()
    assert owner["hostname"] == socket.gethostname()
    assert owner["process_start_time"] == psutil.Process().create_time()
    assert owner["run_identity"] == root.name and owner["mode"] == "production"
    assert owner["scientific_identity"] == {"science": "x"}


def test_pod_restart_foreign_owner_is_never_auto_recovered(tmp_path: Path) -> None:
    """A lease written by another hostname (pod restart) is unknown, not dead."""
    owner = {"hostname": "previous-pod", "pid": 7, "process_start_time": 1.0}
    assert owner_liveness(owner) == "UNKNOWN_FOREIGN_HOST"
    root = tmp_path / "run"
    lease = RunLease(root, root.name, {}, mode="production")
    root.mkdir()
    lease.path.write_text(
        json.dumps({**owner, "run_identity": root.name, "mode": "production"}), encoding="utf-8"
    )
    with pytest.raises(RunLeaseError, match="retained lease evidence"):
        lease.__enter__()
    assert lease.path.is_file()


def test_unreadable_lease_evidence_blocks_and_needs_explicit_recovery(tmp_path: Path) -> None:
    root = tmp_path / "run"
    root.mkdir()
    (root / ".phase7-run-lease.json").write_text("{truncated", encoding="utf-8")
    with pytest.raises(RunLeaseError, match="retained lease evidence"):
        RunLease(root, root.name, {}, mode="production").__enter__()
    assert (root / ".phase7-run-lease.json").read_text(encoding="utf-8") == "{truncated"
