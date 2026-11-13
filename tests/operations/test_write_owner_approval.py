"""ADDED BY CLAUDE (2026-11-13): approval writer prints by default and binds production values."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location(
    "write_owner_approval", ROOT / "scripts/cloud/write_owner_approval.py"
)
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


@pytest.fixture
def fixed_binding(monkeypatch):
    from crypto_ai.phase7 import run_contract

    monkeypatch.setattr(run_contract, "approval_binding", lambda *a, **k: {"fixture": k["mode"]})


def _args(tmp_path: Path, *extra: str) -> list[str]:
    deadline = (datetime.now(UTC) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        "--mode",
        "prepare",
        "--owner",
        "fixture owner",
        "--deadline",
        deadline,
        "--cost-ceiling",
        "5",
        "--currency",
        "USD",
        "--output",
        str(tmp_path / "approval.json"),
        *extra,
    ]


def test_prints_without_writing_unless_confirmed(tmp_path, fixed_binding, capsys) -> None:
    assert writer.main(_args(tmp_path)) == 0
    assert not (tmp_path / "approval.json").exists()
    assert "NOT WRITTEN" in capsys.readouterr().out
    assert writer.main(_args(tmp_path, "--confirm")) == 0
    written = json.loads((tmp_path / "approval.json").read_text())
    assert written["binding"] == {"fixture": "prepare"} and written["status"] == "APPROVED"
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        writer.main(_args(tmp_path, "--confirm"))


def test_rejects_non_utc_or_past_deadlines(tmp_path, fixed_binding) -> None:
    args = _args(tmp_path)
    args[args.index("--deadline") + 1] = "2026-11-14T18:00:00+05:30"
    with pytest.raises(SystemExit, match="UTC"):
        writer.main(args)
    args[args.index("--deadline") + 1] = "2020-01-01T00:00:00Z"
    with pytest.raises(SystemExit, match="past"):
        writer.main(args)
