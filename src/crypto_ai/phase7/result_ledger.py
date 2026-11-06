"""Immutable per-fold result records and the append-only trial ledger (IA-20, trial register).

CHANGED BY CLAUDE (2026-11-06, final architecture repair) - new file, standard library only.

The CSV is a VIEW. Authority is ``results/<run_id>/<spec_id>/<fold_id>/{result.json,receipt.json}``:
temp file -> flush -> fsync -> atomic rename, receipt carries the SHA-256 of the result. Completion
is inferred ONLY from a verified receipt, never from a CSV row. Trials are registered BEFORE they
run
and are never deleted, so the ledger is the denominator for later multiple-testing corrections.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULT_SCHEMA = "phase7_result_record_v1"
TRIAL_STATUSES = ("REGISTERED", "STARTED", "FAILED", "COMPLETED", "INVALIDATED")
_ALLOWED = {
    "REGISTERED": {"STARTED", "INVALIDATED"},
    "STARTED": {"COMPLETED", "FAILED", "INVALIDATED"},
    "FAILED": {"INVALIDATED"},
    "COMPLETED": {"INVALIDATED"},
    "INVALIDATED": set(),
}


class LedgerError(RuntimeError):
    """The ledger is inconsistent: corrupt record, bad receipt, or illegal transition."""


def _fsync_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _dir(root: Path, run_id: str, spec_id: str, fold_id: str) -> Path:
    return root / run_id / spec_id / fold_id


def write_result(root: Path, record: Mapping[str, Any]) -> Path:
    """Publish one fold/spec result atomically. Re-writing a different result is refused."""

    for field in ("run_id", "spec", "fold_id"):
        if not record.get(field):
            raise LedgerError(f"result record needs {field}")
    folder = _dir(root, str(record["run_id"]), str(record["spec"]), str(record["fold_id"]))
    folder.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"schema": RESULT_SCHEMA, **record}, sort_keys=True, default=str).encode()
    digest = hashlib.sha256(body).hexdigest()
    receipt_path = folder / "receipt.json"
    if receipt_path.exists():
        if json.loads(receipt_path.read_text())["result_sha256"] != digest:
            raise LedgerError("DUPLICATE_FOLD_RESULT_WITH_DIFFERENT_CONTENT")
        return folder
    _fsync_write(folder / "result.json", body)  # result first,
    receipt = {
        "result_sha256": digest,
        "written_at": datetime.now(UTC).isoformat(),
        "schema": RESULT_SCHEMA,
    }
    _fsync_write(receipt_path, json.dumps(receipt, sort_keys=True).encode())  # receipt LAST
    return folder


def read_result(folder: Path) -> dict[str, Any]:
    result, receipt = folder / "result.json", folder / "receipt.json"
    if not result.is_file() or not receipt.is_file():
        raise LedgerError(f"INCOMPLETE_RESULT: {folder}")
    if hashlib.sha256(result.read_bytes()).hexdigest() != json.loads(receipt.read_text())[
        "result_sha256"
    ]:
        raise LedgerError(f"RESULT_HASH_MISMATCH: {folder}")
    return json.loads(result.read_text())


def is_complete(root: Path, run_id: str, spec_id: str, fold_id: str) -> bool:
    try:
        read_result(_dir(root, run_id, spec_id, fold_id))
    except (LedgerError, OSError, ValueError):
        return False
    return True


def load_results(root: Path, run_id: str) -> list[dict[str, Any]]:
    """All verified records of a run. A half-written folder (no receipt) is skipped, a corrupt one
    raises. Stray ``*.tmp`` files are ignored."""

    records = []
    base = root / run_id
    if not base.is_dir():
        return records
    for result_path in sorted(base.glob("*/*/result.json")):
        folder = result_path.parent
        if not (folder / "receipt.json").exists():
            continue  # crash between result and receipt: not complete, will be redone
        records.append(read_result(folder))
    return records


def export_csv(records: Sequence[Mapping[str, Any]], path: Path, columns: Sequence[str]) -> Path:
    """Derived VIEW of the ledger; safe to delete and regenerate."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow({name: record.get(name) for name in columns})
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    return path


# ------------------------------------------------------------------------------ trial ledger
def _events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(path: Path, event: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def register_trial(path: Path, trial: Mapping[str, Any]) -> None:
    """Register BEFORE evaluation. The same trial_id with different content is refused."""

    trial_id = str(trial.get("trial_id", ""))
    if not trial_id:
        raise LedgerError("trial needs trial_id")
    for event in _events(path):
        if event["trial_id"] == trial_id and event["event"] == "REGISTERED":
            if event["trial"] != json.loads(json.dumps(trial, default=str)):
                raise LedgerError("TRIAL_ID_REUSED_WITH_DIFFERENT_CONTENT")
            return
    _append(
        path,
        {
            "event": "REGISTERED",
            "trial_id": trial_id,
            "at": datetime.now(UTC).isoformat(),
            "trial": dict(trial),
        },
    )


def current_status(path: Path, trial_id: str) -> str | None:
    status = None
    for event in _events(path):
        if event["trial_id"] == trial_id:
            status = event["event"] if event["event"] != "STATUS" else event["status"]
    return status


def set_status(path: Path, trial_id: str, status: str, reason: str = "") -> None:
    if status not in TRIAL_STATUSES:
        raise LedgerError(f"unknown status {status}")
    current = current_status(path, trial_id)
    if current is None:
        raise LedgerError("TRIAL_NOT_REGISTERED")
    if status not in _ALLOWED[current]:
        raise LedgerError(f"ILLEGAL_TRANSITION: {current} -> {status}")
    _append(
        path,
        {
            "event": "STATUS",
            "trial_id": trial_id,
            "status": status,
            "reason": reason,
            "at": datetime.now(UTC).isoformat(),
        },
    )


def trial_denominator(path: Path) -> int:
    """Number of distinct registered trials, failed and invalidated ones included."""

    return len({e["trial_id"] for e in _events(path) if e["event"] == "REGISTERED"})
