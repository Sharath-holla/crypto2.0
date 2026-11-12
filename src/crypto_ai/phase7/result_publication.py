"""Canonical completion flow for one fold/spec result (closure of IA-02 / IA-20).

CHANGED BY CLAUDE (2026-11-06, smoke-readiness closure) - new file.

Order of events for one COMPLETE fold/spec (the ledger, not the CSV, is the source of truth)::

    model + receipt  ->  report.json  ->  CANONICAL RESULT RECORD (this module, identity-checked)
        ->  HASHED RECEIPT  ->  checkpoint COMPLETE (lists result + receipt files)
        ->  CSV VIEW regenerated from the ledger

A stage is only COMPLETE if ``publish_canonical_result`` succeeded: its two files are part of the
checkpoint file list, so a checkpoint cannot be COMPLETE with a missing or altered result.
Identity is validated BEFORE anything is written; nothing is defaulted or substituted.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from crypto_ai.phase7 import result_ledger
from crypto_ai.phase7.result_integrity import (
    CANONICAL_KEY_FIELDS,
    UNIFORM_FIELDS,
    ResultIntegrityError,
)
from crypto_ai.phase7.selection_chronology import load_protocol

LEDGER_DIRNAME = "result_ledger"
SELECTION_PROTOCOL_RELATIVE_PATH = Path("configs/research/phase7_selection_chronology_v1.json")
# Everything a published record must state. These are the canonical key fields, the uniform
# experiment fields and the protocol version; ``status`` must be exactly COMPLETE.
REQUIRED_RECORD_FIELDS = tuple(
    dict.fromkeys(
        (
            *CANONICAL_KEY_FIELDS,
            *UNIFORM_FIELDS,
            "selection_protocol_version",
            "selection_protocol_sha256",
            "status",
        )
    )
)

# Test seam: crash-injection points. Production never sets this.
_fault_point: Callable[[str], None] | None = None


def _fault(name: str) -> None:
    if _fault_point is not None:
        _fault_point(name)


def selection_protocol_identity(repository_root: Path | None = None) -> dict[str, str]:
    """Version and hash of the frozen selection protocol; missing or tampered fails closed."""

    root = repository_root or Path(__file__).parents[3]
    path = root / SELECTION_PROTOCOL_RELATIVE_PATH
    if not path.is_file():
        raise ResultIntegrityError(f"SELECTION_PROTOCOL_MISSING: {path}")
    protocol = load_protocol(path)  # raises ChronologyError if tampered
    return {
        "selection_protocol_version": str(protocol["schema"]),
        "selection_protocol_sha256": str(protocol["protocol_sha256"]),
    }


def _default_row_builder(report: Mapping[str, Any]) -> dict[str, Any]:
    from crypto_ai.phase7.hardening import results_row_from_report

    return results_row_from_report(report)


def build_canonical_record(
    report: Mapping[str, Any],
    *,
    protocol_identity: Mapping[str, str],
    row_builder: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Flatten a COMPLETE report into the canonical record. Raises on any missing identity."""

    if str(report.get("status")) != "COMPLETE":
        raise ResultIntegrityError(f"NON_COMPLETE_REPORT: status={report.get('status')!r}")
    if report.get("test_used_for_selection") is not False:
        raise ResultIntegrityError("TEST_USED_FOR_SELECTION_NOT_FALSE")
    record = dict((row_builder or _default_row_builder)(report))
    record.update(protocol_identity)
    missing = [
        name
        for name in REQUIRED_RECORD_FIELDS
        if record.get(name) is None or str(record.get(name)).strip() == ""
    ]
    if missing:
        raise ResultIntegrityError(f"MISSING_IDENTITY_FIELDS: {missing}")
    return record


def publish_canonical_result(
    ledger_root: Path,
    report: Mapping[str, Any],
    *,
    protocol_identity: Mapping[str, str] | None = None,
    row_builder: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None,
) -> list[Path]:
    """Validate identity, then publish result + receipt atomically. Returns the two file paths.

    Idempotent: re-publishing the identical record changes nothing; a different record for the
    same (run, spec, fold) raises ``LedgerError`` instead of overwriting.
    """

    record = build_canonical_record(
        report,
        protocol_identity=protocol_identity or selection_protocol_identity(),
        row_builder=row_builder,
    )
    _fault("BEFORE_RESULT_WRITE")
    folder = result_ledger.write_result(ledger_root, record)
    _fault("AFTER_RECEIPT")
    result_ledger.read_result(folder)  # verify what was just published, hash included
    return [folder / "result.json", folder / "receipt.json"]


def refresh_results_view(
    ledger_root: Path, run_id: str, csv_path: Path, columns: Sequence[str]
) -> Path:
    """Regenerate the CSV purely from verified ledger records; never read the old CSV."""

    _fault("BEFORE_CSV_EXPORT")
    records = result_ledger.load_results(ledger_root, run_id)
    return result_ledger.export_csv(records, csv_path, columns)


def view_matches_ledger(
    ledger_root: Path, run_id: str, csv_path: Path, columns: Sequence[str]
) -> bool:
    """True only if the CSV equals what the ledger would regenerate (byte-for-byte)."""

    if not csv_path.is_file():
        return False
    expected = csv_path.with_name(csv_path.name + ".verify")
    try:
        records = result_ledger.load_results(ledger_root, run_id)
        result_ledger.export_csv(records, expected, columns)
        return (
            hashlib.sha256(expected.read_bytes()).digest()
            == hashlib.sha256(csv_path.read_bytes()).digest()
        )
    finally:
        expected.unlink(missing_ok=True)
