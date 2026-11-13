"""ADDED BY CLAUDE (2026-11-13): disk planning and audited release of completed caches."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai.phase7 import low_memory_disk

CACHE_ID = "a" * 64


def _cache(root: Path) -> Path:
    entry = root / CACHE_ID
    entry.mkdir(parents=True)
    (entry / "manifest.json").write_text(json.dumps({"cache_id": CACHE_ID, "files": {}}))
    (entry / "train.arrow").write_bytes(b"x" * 1000)
    return entry


def _report(root: Path, name: str, status: str) -> None:
    path = root / name / "report.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": status, "prepared_cache_id": CACHE_ID}))


def test_plan_uses_measured_bytes_per_row_and_fails_when_tight() -> None:
    fold0 = low_memory_disk.plan(
        free_bytes=29 * 10**9, fold_rows=4_922_887, pending_input_bytes=10_998_003_736
    )
    assert fold0["fits"] is True
    assert 14.0e9 < fold0["estimated_spill_bytes"] + fold0["estimated_cache_bytes"] < 14.6e9
    worst = low_memory_disk.plan(
        free_bytes=29 * 10**9, fold_rows=5_783_040, pending_input_bytes=10_998_003_736
    )
    assert worst["fits"] is False


def test_release_refuses_unless_offline_confirmed_and_all_reports_terminal(tmp_path) -> None:
    cache_root, reports, receipts = tmp_path / "cache", tmp_path / "reports", tmp_path / "receipts"
    entry = _cache(cache_root)
    kwargs = {
        "cache_root": cache_root,
        "cache_id": CACHE_ID,
        "report_roots": (reports,),
        "receipt_dir": receipts,
    }
    reports.mkdir()
    with pytest.raises(RuntimeError, match="no report references"):
        low_memory_disk.release(**kwargs, confirm=True, offline=True)
    _report(reports, "g0", "COMPLETE")
    _report(reports, "c0", "STARTED")
    with pytest.raises(RuntimeError, match="offline"):
        low_memory_disk.release(**kwargs, confirm=True, offline=False)
    with pytest.raises(RuntimeError, match="non-terminal"):
        low_memory_disk.release(**kwargs, confirm=True, offline=True)
    (reports / "c0" / "report.json").write_text(
        json.dumps({"status": "INELIGIBLE", "prepared_cache_id": CACHE_ID})
    )
    dry = low_memory_disk.release(**kwargs, confirm=False, offline=True)
    assert dry["dry_run"] is True and entry.exists()
    done = low_memory_disk.release(**kwargs, confirm=True, offline=True)
    assert not entry.exists()
    receipt = json.loads(Path(done["receipt"]).read_text())
    assert receipt["manifest"]["cache_id"] == CACHE_ID and receipt["bytes"] == 1000 + len(
        (json.dumps({"cache_id": CACHE_ID, "files": {}})).encode()
    )


def test_release_rejects_bad_ids_and_aliases(tmp_path) -> None:
    with pytest.raises(ValueError, match="invalid"):
        low_memory_disk.release(
            cache_root=tmp_path,
            cache_id="../x",
            report_roots=(tmp_path,),
            receipt_dir=tmp_path,
            confirm=True,
            offline=True,
        )
    (tmp_path / "real").mkdir()
    (tmp_path / CACHE_ID).symlink_to(tmp_path / "real")
    with pytest.raises(ValueError, match="aliased"):
        low_memory_disk.release(
            cache_root=tmp_path,
            cache_id=CACHE_ID,
            report_roots=(tmp_path,),
            receipt_dir=tmp_path,
            confirm=True,
            offline=True,
        )


def test_budget_counts_every_component_and_refuses_unsafe_plans(tmp_path) -> None:
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo/file").write_bytes(b"x" * 4096)
    result = low_memory_disk.budget(
        probe=tmp_path,
        fold_rows=4_922_887,
        data_bytes_pending=10_998_003_736,
        occupied={"repo": tmp_path / "repo"},
    )
    assert result["already_occupied_bytes"] == {"repo": 4096}
    assert set(result["planned_additional_bytes"]) == {
        "dataset_still_to_download",
        "spill_unfiltered_fold_segments",
        "prepared_cache_tables_and_matrices",
        "models_reports_checkpoints",
        "logs_and_telemetry",
        "filesystem_safety_margin",
    }
    assert result["planned_peak_bytes"] == sum(result["planned_additional_bytes"].values())
    huge = low_memory_disk.budget(probe=tmp_path, fold_rows=10**9, data_bytes_pending=0)
    assert huge["fits"] is False
