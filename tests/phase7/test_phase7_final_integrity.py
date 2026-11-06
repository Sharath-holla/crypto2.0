"""CHANGED BY CLAUDE (2026-11-06, final architecture repair): IA-01/02/03/04/20 regression tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from crypto_ai.phase7 import result_ledger as ledger
from crypto_ai.phase7.experiment_identity import experiment_control_identity
from crypto_ai.phase7.result_integrity import (
    CANONICAL_KEY_FIELDS,
    ResultIntegrityError,
    reject_duplicates,
    validate_result_set,
)
from crypto_ai.phase7.selection_chronology import (
    ChronologyError,
    assert_rows_selection_eligible,
    build_selection_protocol,
    fold_calendar,
    load_protocol,
    overlap_matrix,
    write_protocol,
)

FOLDS = [f"fold-{i:03d}" for i in range(16)]


def _row(fold: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "run_id": "run-1",
        "spec": "architecture-G0-A6-60m-raw",
        "fold_id": fold,
        "seed": "42",
        "architecture": "G0",
        "horizon_minutes": "60",
        "target_type": "raw",
        "feature_set": "A6",
        "gold_dataset_id": "gold-1",
        "configuration_hash": "cfg-1",
        "scientific_code_identity": "src-1",
        "hardening_identity": "hard-1",
        "baseline_contract_version": "b1",
        "backend": "cpu",
        "status": "COMPLETE",
    }
    row.update(overrides)
    return row


def _full(**overrides: object) -> list[dict[str, object]]:
    return [_row(fold, **overrides) for fold in FOLDS]


def test_complete_unique_set_is_accepted() -> None:
    assert len(validate_result_set(_full(), expected_fold_ids=FOLDS)) == 16
    assert set(CANONICAL_KEY_FIELDS) >= {"run_id", "spec", "fold_id", "seed", "backend"}


def test_ten_copies_of_one_fold_are_rejected_not_counted() -> None:
    with pytest.raises(ResultIntegrityError, match="DUPLICATE_RESULT"):
        reject_duplicates([_row("fold-000")] * 10)


def test_replayed_or_crash_resumed_row_is_rejected() -> None:
    rows = _full()
    rows.append(dict(rows[3]))  # same result replayed after a crash-resume
    with pytest.raises(ResultIntegrityError, match="DUPLICATE_RESULT"):
        validate_result_set(rows, expected_fold_ids=FOLDS)


def test_missing_fold_is_rejected() -> None:
    with pytest.raises(ResultIntegrityError, match="FOLD_SET_MISMATCH"):
        validate_result_set(_full()[:-1], expected_fold_ids=FOLDS)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gold_dataset_id", "gold-2"),
        ("configuration_hash", "cfg-2"),
        ("hardening_identity", "hard-2"),
        ("scientific_code_identity", "src-2"),
        ("seed", "7"),
        ("backend", "gpu"),
    ],
)
def test_mixed_identity_is_rejected(field: str, value: str) -> None:
    rows = _full()
    rows[5][field] = value
    with pytest.raises(ResultIntegrityError, match="MIXED_IDENTITY"):
        validate_result_set(rows, expected_fold_ids=FOLDS)


def test_missing_identity_and_non_complete_rows_are_rejected() -> None:
    rows = _full()
    rows[0]["configuration_hash"] = ""
    with pytest.raises(ResultIntegrityError, match="MISSING_IDENTITY_FIELDS"):
        validate_result_set(rows)
    rows = _full()
    rows[1]["status"] = "INELIGIBLE"
    with pytest.raises(ResultIntegrityError, match="NON_COMPLETE_ROWS"):
        validate_result_set(rows)


# ------------------------------------------------------------------------------ chronology
@dataclass(frozen=True)
class _Plan:
    fold_id: str
    train_start: datetime
    train_end: datetime
    validation_start: datetime
    validation_end: datetime
    calibration_start: datetime
    calibration_end: datetime
    test_start: datetime
    test_end: datetime


def _months(base: datetime, months: int) -> datetime:
    total = base.year * 12 + base.month - 1 + months
    return base.replace(year=total // 12, month=total % 12 + 1)


def _plans(count: int = 16) -> list[_Plan]:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    plans = []
    for i in range(count):
        t0 = _months(start, 3 * i)
        t1, v1, c1, e1 = (_months(t0, m) for m in (24, 27, 30, 33))
        plans.append(_Plan(FOLDS[i], t0, t1, t1, v1, v1, c1, c1, e1))
    return plans


def test_overlap_matrix_shows_fold0_test_reused_as_fold2_validation() -> None:
    matrix = overlap_matrix(fold_calendar(_plans()))
    reuse = [
        r
        for r in matrix
        if r["test_of_fold"] == "fold-000"
        and r["reused_by_fold"] == "fold-002"
        and r["reused_as"] == "VALIDATION"
    ]
    assert reuse, "fold 0 TEST months are fold 2 VALIDATION months in this calendar"


def test_protocol_requires_evaluation_strictly_after_development() -> None:
    calendar = fold_calendar(_plans())
    with pytest.raises(ChronologyError, match="EVALUATION_NOT_AFTER_DEVELOPMENT"):
        build_selection_protocol(  # an evaluation fold whose TEST precedes development data
            calendar, development_fold_ids=FOLDS[3:8], evaluation_fold_ids=[FOLDS[1]],
            selection_policy_version="v1",
        )
    protocol = build_selection_protocol(
        calendar, development_fold_ids=FOLDS[:4], evaluation_fold_ids=FOLDS[10:],
        selection_policy_version="v1",
    )
    assert protocol["holdout"] == {
        "status": "LOCKED_UNUSED", "used": False, "evaluation_authorized": False,
    }


def test_protocol_roles_cannot_be_conflicting_or_unknown() -> None:
    calendar = fold_calendar(_plans())
    with pytest.raises(ChronologyError):
        build_selection_protocol(
            calendar, development_fold_ids=FOLDS[:4], evaluation_fold_ids=[FOLDS[3]],
            selection_policy_version="v1",
        )
    with pytest.raises(ChronologyError):
        build_selection_protocol(
            calendar, development_fold_ids=["nope"], evaluation_fold_ids=FOLDS[10:],
            selection_policy_version="v1",
        )


def test_protocol_is_immutable_and_tamper_evident(tmp_path) -> None:
    calendar = fold_calendar(_plans())
    first = build_selection_protocol(
        calendar, development_fold_ids=FOLDS[:4], evaluation_fold_ids=FOLDS[10:],
        selection_policy_version="v1",
    )
    other = build_selection_protocol(
        calendar, development_fold_ids=FOLDS[:5], evaluation_fold_ids=FOLDS[10:],
        selection_policy_version="v1",
    )
    path = write_protocol(tmp_path / "selection_chronology.json", first)
    write_protocol(path, first)  # same content: idempotent
    with pytest.raises(ChronologyError, match="PROTOCOL_IMMUTABLE"):
        write_protocol(path, other)
    assert load_protocol(path)["protocol_sha256"] == first["protocol_sha256"]
    data = json.loads(path.read_text())
    data["development_folds"].append("fold-009")
    path.write_text(json.dumps(data))
    with pytest.raises(ChronologyError, match="PROTOCOL_TAMPERED"):
        load_protocol(path)


def test_selector_rejects_evaluation_and_unregistered_folds() -> None:
    calendar = fold_calendar(_plans())
    protocol = build_selection_protocol(
        calendar, development_fold_ids=FOLDS[:4], evaluation_fold_ids=FOLDS[10:],
        selection_policy_version="v1",
    )
    assert_rows_selection_eligible([_row(FOLDS[0]), _row(FOLDS[3])], protocol)
    with pytest.raises(ChronologyError, match="EVALUATION_FOLD_IN_SELECTION"):
        assert_rows_selection_eligible([_row(FOLDS[12])], protocol)
    with pytest.raises(ChronologyError, match="FOLD_NOT_IN_PROTOCOL"):
        assert_rows_selection_eligible([_row(FOLDS[6])], protocol)


# ------------------------------------------------------------------------------ identity
def test_control_identity_binds_active_settings_and_source() -> None:
    a = experiment_control_identity({"abort_after_worse_checks": 0})
    b = experiment_control_identity({"abort_after_worse_checks": 3})
    assert a["manifest_sha256"] != b["manifest_sha256"]
    assert a["manifest_sha256"] == experiment_control_identity(
        {"abort_after_worse_checks": 0}
    )["manifest_sha256"]
    assert any(item["path"].endswith("hardening.py") for item in a["files"])


def test_control_identity_changes_when_hardening_source_changes(tmp_path) -> None:
    from crypto_ai.phase7.experiment_identity import EXPERIMENT_CONTROL_SOURCE_FILES

    for relative in EXPERIMENT_CONTROL_SOURCE_FILES:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# stub\n")
    before = experiment_control_identity({}, tmp_path)["manifest_sha256"]
    (tmp_path / EXPERIMENT_CONTROL_SOURCE_FILES[0]).write_text("# edited abort rule\n")
    assert experiment_control_identity({}, tmp_path)["manifest_sha256"] != before


def test_hardening_is_control_identity_not_cache_identity() -> None:
    """hardening.py edits must not invalidate prepared caches (they are not cache-critical)."""

    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "src/crypto_ai/phase7/training.py").read_text()
    start = text.index("TRAINING_CRITICAL_SOURCE_FILES = (")
    block = text[start : text.index(")\nEXECUTION_CONTEXT_SOURCE_FILES")]
    assert "phase7/hardening.py" not in block
    assert "phase7/features.py" in block and "phase7/cross_section.py" in block


# ------------------------------------------------------------------------------ ledger
def _record(fold: str = "fold-000", **extra: object) -> dict[str, object]:
    return {"run_id": "run-1", "spec": "spec-a", "fold_id": fold, "status": "COMPLETE", **extra}


def test_result_is_complete_only_after_receipt(tmp_path) -> None:
    folder = ledger.write_result(tmp_path, _record(value=1))
    assert ledger.is_complete(tmp_path, "run-1", "spec-a", "fold-000")
    (folder / "receipt.json").unlink()  # crash between result and receipt
    assert not ledger.is_complete(tmp_path, "run-1", "spec-a", "fold-000")
    assert ledger.load_results(tmp_path, "run-1") == []


def test_corrupt_result_is_detected(tmp_path) -> None:
    folder = ledger.write_result(tmp_path, _record(value=1))
    (folder / "result.json").write_text('{"tampered": true}')
    assert not ledger.is_complete(tmp_path, "run-1", "spec-a", "fold-000")
    with pytest.raises(ledger.LedgerError, match="RESULT_HASH_MISMATCH"):
        ledger.load_results(tmp_path, "run-1")


def test_duplicate_resume_is_idempotent_but_conflict_is_refused(tmp_path) -> None:
    ledger.write_result(tmp_path, _record(value=1))
    ledger.write_result(tmp_path, _record(value=1))  # identical replay: no second record
    assert len(ledger.load_results(tmp_path, "run-1")) == 1
    with pytest.raises(ledger.LedgerError, match="DIFFERENT_CONTENT"):
        ledger.write_result(tmp_path, _record(value=2))


def test_csv_is_a_derived_view(tmp_path) -> None:
    ledger.write_result(tmp_path / "results", _record("fold-000", value=1))
    ledger.write_result(tmp_path / "results", _record("fold-001", value=2))
    records = ledger.load_results(tmp_path / "results", "run-1")
    path = ledger.export_csv(records, tmp_path / "view.csv", ["fold_id", "value"])
    assert path.read_text().splitlines()[0] == "fold_id,value"
    path.unlink()  # deleting the view loses nothing
    assert len(ledger.load_results(tmp_path / "results", "run-1")) == 2


def test_trial_ledger_never_forgets_failed_trials(tmp_path) -> None:
    path = tmp_path / "trials.jsonl"
    ledger.register_trial(path, {"trial_id": "t1", "purpose": "smoke"})
    ledger.register_trial(path, {"trial_id": "t1", "purpose": "smoke"})  # idempotent
    ledger.register_trial(path, {"trial_id": "t2", "purpose": "seed sensitivity"})
    ledger.set_status(path, "t1", "STARTED")
    ledger.set_status(path, "t1", "FAILED", "oom")
    assert ledger.current_status(path, "t1") == "FAILED"
    assert ledger.trial_denominator(path) == 2  # failed trials still count
    with pytest.raises(ledger.LedgerError, match="ILLEGAL_TRANSITION"):
        ledger.set_status(path, "t2", "COMPLETED")
    with pytest.raises(ledger.LedgerError, match="TRIAL_ID_REUSED"):
        ledger.register_trial(path, {"trial_id": "t1", "purpose": "something else"})
    with pytest.raises(ledger.LedgerError, match="TRIAL_NOT_REGISTERED"):
        ledger.set_status(path, "t9", "STARTED")
