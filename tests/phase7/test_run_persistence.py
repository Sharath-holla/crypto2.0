"""ADDED BY CLAUDE (2026-11-13): export/restore of completed run artifacts (no training)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai.phase7 import run_persistence


def _run(root: Path) -> Path:
    run = root / "benchmark-only-abc"
    (run / "checkpoints/benchmark-only-abc").mkdir(parents=True)
    (run / "checkpoints/benchmark-only-abc/models.json").write_text('{"complete": true}')
    report = run / "report/models/core/fold-000/architecture-G0-A6-60m-raw/report.json"
    report.parent.mkdir(parents=True)
    report.write_text(json.dumps({"status": "COMPLETE"}))
    model = run / "model/models/core/fold-000/architecture-G0-A6-60m-raw/model.joblib"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"model-bytes")
    (run / "prepared_cache").mkdir()
    (run / "prepared_cache/train_x.npy").write_bytes(b"x" * 100)
    (run / ".low-memory-spill-1-a").mkdir()
    (run / ".low-memory-spill-1-a/OWNER.json").write_text("{}")
    (run / "matrix.arrow").write_bytes(b"arrow")
    return run


def test_export_is_dry_run_by_default_and_excludes_bulk_data(tmp_path: Path) -> None:
    run = _run(tmp_path)
    destination = tmp_path / "persisted"
    dry = run_persistence.export({"run": run}, destination, metadata={}, execute=False)
    assert dry["dry_run"] is True and dry["file_count"] == 3 and not destination.exists()
    done = run_persistence.export({"run": run}, destination, metadata={"spec": "G0"}, execute=True)
    assert done["file_count"] == 3
    manifest = json.loads((destination / "PERSISTED_MANIFEST.json").read_text())
    paths = {item["path"] for item in manifest["files"]}
    assert not any("prepared_cache" in p or "spill" in p or p.endswith(".arrow") for p in paths)


def test_restore_verifies_hashes_and_refuses_conflicts(tmp_path: Path) -> None:
    run = _run(tmp_path)
    destination = tmp_path / "persisted"
    run_persistence.export({"run": run}, destination, metadata={}, execute=True)
    target = tmp_path / "new-session" / "benchmark-only-abc"
    dry = run_persistence.restore(destination, {"run": target}, execute=False)
    assert dry["copy"] == 3 and not target.exists()
    run_persistence.restore(destination, {"run": target}, execute=True)
    assert run_persistence.status(target)["reports"] == {
        "report/models/core/fold-000/architecture-G0-A6-60m-raw/report.json": "COMPLETE"
    }
    assert run_persistence.restore(destination, {"run": target}, execute=True)["identical"] == 3
    (target / "model/models/core/fold-000/architecture-G0-A6-60m-raw/model.joblib").write_bytes(
        b"tampered"
    )
    with pytest.raises(RuntimeError, match="RESTORE_CONFLICT"):
        run_persistence.restore(destination, {"run": target}, execute=True)
    stored = next(destination.rglob("model.joblib"))
    stored.write_bytes(b"corrupt")
    with pytest.raises(RuntimeError, match="PERSISTED_ARTIFACT_CORRUPT"):
        run_persistence.restore(destination, {"run": tmp_path / "other"}, execute=False)
