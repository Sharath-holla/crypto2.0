"""CHANGED BY CLAUDE (2026-11-06, closure): canonical completion flow, crash/resume, identity.

The ledger (not the CSV) is the source of truth. Crash points are injected through the ledger and
publication test seams; "resume" means re-running the same publication after the simulated crash.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_ai.phase7 import result_ledger, result_publication
from crypto_ai.phase7.result_integrity import (
    ResultIntegrityError,
    validate_result_set,
)
from crypto_ai.phase7.result_ledger import LedgerError

COLUMNS = ("run_id", "spec", "fold_id", "configuration_hash", "status", "expectancy")
PROTOCOL = {
    "selection_protocol_version": "phase7_selection_chronology_v1",
    "selection_protocol_sha256": "p" * 64,
}


class Crash(RuntimeError):
    pass


def _identity(fold: str = "fold-000", **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "run-1",
        "spec": "architecture-G0-A6-60m-raw",
        "fold_id": fold,
        "seed": 42,
        "architecture": "G0",
        "horizon_minutes": 60,
        "target_type": "raw",
        "feature_set": "A6",
        "gold_dataset_id": "gold-1",
        "configuration_hash": "cfg-1",
        "scientific_code_identity": "src-1",
        "hardening_identity": "hard-1",
        "baseline_contract_version": "b1",
        "backend": "cpu",
        "status": "COMPLETE",
        "expectancy": 0.001,
    }
    row.update(overrides)
    return row


def _report(fold: str = "fold-000", **overrides: object) -> dict[str, object]:
    return {
        "status": "COMPLETE",
        "test_used_for_selection": False,
        "row": _identity(fold, **overrides),
    }


def _builder(report):  # a stand-in for hardening.results_row_from_report
    return dict(report["row"])


def _publish(root: Path, report: dict[str, object]) -> list[Path]:
    return result_publication.publish_canonical_result(
        root, report, protocol_identity=PROTOCOL, row_builder=_builder
    )


@pytest.fixture(autouse=True)
def _no_leftover_faults():
    yield
    result_ledger._fault_point = None
    result_publication._fault_point = None


def test_publish_writes_result_and_hashed_receipt(tmp_path: Path) -> None:
    files = _publish(tmp_path, _report())
    assert [p.name for p in files] == ["result.json", "receipt.json"]
    record = result_ledger.read_result(files[0].parent)
    assert record["selection_protocol_version"] == PROTOCOL["selection_protocol_version"]
    assert json.loads(files[1].read_text())["result_sha256"]


@pytest.mark.parametrize("field", list(result_publication.REQUIRED_RECORD_FIELDS))
def test_every_identity_field_is_required_and_nothing_is_written(tmp_path: Path, field: str):
    report = _report()
    if field in PROTOCOL:
        protocol = {k: v for k, v in PROTOCOL.items() if k != field}
        with pytest.raises(ResultIntegrityError, match="MISSING_IDENTITY_FIELDS"):
            result_publication.publish_canonical_result(
                tmp_path, report, protocol_identity=protocol, row_builder=_builder
            )
    else:
        report["row"][field] = None if field != "seed" else ""
        with pytest.raises(ResultIntegrityError, match="MISSING_IDENTITY_FIELDS"):
            _publish(tmp_path, report)
    assert not list(tmp_path.rglob("*.json"))


@pytest.mark.parametrize("status", ["INELIGIBLE", "RUNNING", None])
def test_non_complete_report_is_never_published(tmp_path: Path, status):
    report = _report()
    report["status"] = status
    with pytest.raises(ResultIntegrityError, match="NON_COMPLETE_REPORT"):
        _publish(tmp_path, report)


def test_report_that_touched_test_for_selection_is_refused(tmp_path: Path) -> None:
    report = _report()
    report["test_used_for_selection"] = True
    with pytest.raises(ResultIntegrityError, match="TEST_USED_FOR_SELECTION"):
        _publish(tmp_path, report)


LEDGER_CRASHES = [
    "AFTER_TEMP_WRITE:result.json",  # crash after result temp write
    "AFTER_PUBLISH:result.json",  # crash after atomic publish, before receipt
    "AFTER_TEMP_WRITE:receipt.json",  # crash while writing the receipt
    "AFTER_PUBLISH:receipt.json",  # crash right after the receipt
]


@pytest.mark.parametrize("crash_at", [*LEDGER_CRASHES, "BEFORE_RESULT_WRITE", "AFTER_RECEIPT"])
def test_crash_at_every_publication_point_then_resume_is_idempotent(tmp_path: Path, crash_at: str):
    ledger = tmp_path / "ledger"
    csv_path = tmp_path / "view.csv"

    def hook(name: str) -> None:
        if name == crash_at:
            raise Crash(name)

    result_ledger._fault_point = hook
    result_publication._fault_point = hook
    with pytest.raises(Crash):
        _publish(ledger, _report())
    result_ledger._fault_point = None
    result_publication._fault_point = None

    # whatever state the crash left, no half-written record is visible as COMPLETE
    visible = result_ledger.load_results(ledger, "run-1")
    assert len(visible) == (1 if crash_at in {"AFTER_PUBLISH:receipt.json", "AFTER_RECEIPT"} else 0)

    # resume: same publication again, then the view
    _publish(ledger, _report())
    result_publication.refresh_results_view(ledger, "run-1", csv_path, COLUMNS)
    records = result_ledger.load_results(ledger, "run-1")
    assert len(records) == 1 and validate_result_set(records, strict_identity=True)
    assert result_publication.view_matches_ledger(ledger, "run-1", csv_path, COLUMNS)
    # a second resume changes nothing
    before = (ledger / "run-1").rglob("*")
    snapshot = sorted((p.name, p.stat().st_size) for p in before if p.is_file())
    _publish(ledger, _report())
    after = (ledger / "run-1").rglob("*")
    assert snapshot == sorted((p.name, p.stat().st_size) for p in after if p.is_file())


def test_crash_before_csv_export_leaves_ledger_valid_and_csv_regenerable(tmp_path: Path):
    ledger, csv_path = tmp_path / "ledger", tmp_path / "view.csv"
    _publish(ledger, _report())

    def hook(name: str) -> None:
        if name == "BEFORE_CSV_EXPORT":
            raise Crash(name)

    result_publication._fault_point = hook
    with pytest.raises(Crash):
        result_publication.refresh_results_view(ledger, "run-1", csv_path, COLUMNS)
    result_publication._fault_point = None
    assert not csv_path.exists()
    assert len(result_ledger.load_results(ledger, "run-1")) == 1
    result_publication.refresh_results_view(ledger, "run-1", csv_path, COLUMNS)
    assert result_publication.view_matches_ledger(ledger, "run-1", csv_path, COLUMNS)


def test_a_partial_or_forged_csv_is_never_authority(tmp_path: Path) -> None:
    ledger, csv_path = tmp_path / "ledger", tmp_path / "view.csv"
    _publish(ledger, _report("fold-000"))
    csv_path.write_text("run_id,spec,fold_id\nrun-1,forged,fold-099\nrun-1,forged,fold-099\n")
    assert not result_publication.view_matches_ledger(ledger, "run-1", csv_path, COLUMNS)
    result_publication.refresh_results_view(ledger, "run-1", csv_path, COLUMNS)
    text = csv_path.read_text()
    assert "forged" not in text and "fold-000" in text
    assert result_publication.view_matches_ledger(ledger, "run-1", csv_path, COLUMNS)


def test_identical_republish_is_idempotent_and_different_content_is_refused(tmp_path: Path):
    _publish(tmp_path, _report())
    _publish(tmp_path, _report())
    assert len(result_ledger.load_results(tmp_path, "run-1")) == 1
    with pytest.raises(LedgerError, match="DUPLICATE_FOLD_RESULT_WITH_DIFFERENT_CONTENT"):
        _publish(tmp_path, _report(expectancy=0.5))
    assert len(result_ledger.load_results(tmp_path, "run-1")) == 1


def test_corruption_is_detected_and_never_silently_overwritten(tmp_path: Path) -> None:
    files = _publish(tmp_path, _report())
    files[0].write_bytes(files[0].read_bytes().replace(b"0.001", b"9.999"))
    corrupted = files[0].read_bytes()
    with pytest.raises(LedgerError, match="RESULT_HASH_MISMATCH"):
        _publish(tmp_path, _report())
    with pytest.raises(LedgerError, match="RESULT_HASH_MISMATCH"):
        result_ledger.load_results(tmp_path, "run-1")
    assert files[0].read_bytes() == corrupted  # preserved for investigation, not repaired


def test_mixed_identity_cannot_resume_into_one_result_set(tmp_path: Path) -> None:
    _publish(tmp_path, _report("fold-000"))
    _publish(tmp_path, _report("fold-001", configuration_hash="cfg-OTHER"))
    records = result_ledger.load_results(tmp_path, "run-1")
    assert len(records) == 2
    with pytest.raises(ResultIntegrityError, match="MIXED_IDENTITY"):
        validate_result_set(records, strict_identity=True)


def test_duplicate_scientific_result_cannot_exist(tmp_path: Path) -> None:
    for _ in range(5):
        _publish(tmp_path, _report("fold-003"))
    assert len(list((tmp_path / "run-1").glob("*/*/result.json"))) == 1


def test_checkpoint_complete_is_bound_to_the_ledger_files(tmp_path: Path) -> None:
    artifacts = pytest.importorskip("crypto_ai.phase7.artifacts")
    ledger = tmp_path / "ledger"
    files = _publish(ledger, _report())
    store = artifacts.CheckpointStore(tmp_path / "checkpoints", "run-1")
    identity = {"fixture": "closure"}
    store.complete("train/fold-000", files, identity)
    assert store.is_complete("train/fold-000", expected_metadata=identity)
    files[0].write_bytes(files[0].read_bytes() + b" ")
    assert not store.is_complete("train/fold-000", expected_metadata=identity)


def test_training_loop_publishes_before_complete_and_run_one_no_longer_writes_csv() -> None:
    """Structural guard: the CSV append is gone from _run_one; both completion sites publish."""

    import ast

    source = (Path(__file__).parents[2] / "src/crypto_ai/phase7/training.py").read_text()
    tree = ast.parse(source)
    run_one = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_run_one"
    )
    called = {
        n.func.id
        for n in ast.walk(run_one)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "append_result_row" not in called
    publishing = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "publish_canonical_result"
    ]
    assert len(publishing) >= 2  # fresh path and adopted-orphan path
