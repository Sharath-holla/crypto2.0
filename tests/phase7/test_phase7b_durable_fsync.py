"""Added by Claude (2026-11-02, finding L-06): macOS uses F_FULLFSYNC, other systems os.fsync."""

from __future__ import annotations

import os
import sys
import types

from crypto_ai.phase7 import artifacts


def test_macos_uses_full_fsync(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []
    fake = types.SimpleNamespace(
        F_FULLFSYNC=51, fcntl=lambda fd, command: calls.append((fd, command))
    )
    monkeypatch.setitem(sys.modules, "fcntl", fake)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append((fd, -1)))
    artifacts.durable_fsync(7)
    assert calls == [(7, 51)]


def test_macos_falls_back_when_full_fsync_is_unsupported(monkeypatch) -> None:
    calls: list[tuple[int, int]] = []

    def refuse(fd: int, command: int) -> None:
        raise OSError("unsupported")

    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(F_FULLFSYNC=51, fcntl=refuse))
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append((fd, -1)))
    artifacts.durable_fsync(9)
    assert calls == [(9, -1)]


def test_other_platforms_use_plain_fsync(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(os, "fsync", lambda fd: calls.append(fd))
    artifacts.durable_fsync(3)
    assert calls == [3]


def test_fsync_file_still_works_on_a_real_file(tmp_path) -> None:
    target = tmp_path / "x.bin"
    target.write_bytes(b"data")
    artifacts.fsync_file(target)
    assert target.read_bytes() == b"data"
