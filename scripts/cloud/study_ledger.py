#!/usr/bin/env python3
"""Resumable Phase 7A study ledger: 48 specifications x 16 folds (768 runs).

ADDED BY CLAUDE (2026-11-14). The ledger FILE is private run evidence (kept with the evidence and
exported to the owner's Mac), never committed. Statuses: PENDING, COMPLETE_VERIFIED, FAILED,
INELIGIBLE. A run is marked COMPLETE_VERIFIED only from its canonical report.json (status
COMPLETE) plus a RELOAD_VERIFIED record for the same model SHA-256.

  uv run python scripts/cloud/study_ledger.py init --ledger L
  uv run python scripts/cloud/study_ledger.py record --ledger L --report R --reload RL
  uv run python scripts/cloud/study_ledger.py summary --ledger L
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path


def _atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def init(ledger: Path) -> dict:
    if ledger.exists():
        return json.loads(ledger.read_text())
    from crypto_ai.phase5.folds import plan_folds
    from crypto_ai.phase7.config import load_phase7_config
    from crypto_ai.phase7.phase7a import enumerate_specs

    config = load_phase7_config(Path("configs/phase7/research_core20_primary_v1.toml"))
    folds = plan_folds(
        config.data_start, config.research_cutoff, config.prospective_holdout_start, config.schedule
    )
    specs = [s for s in enumerate_specs(config)["specs"] if s["name"].startswith("architecture-")]
    runs = {}
    for fold in folds:
        for spec in specs:
            key = f"{fold.fold_id}|{spec['name']}"
            runs[key] = {
                "fold_id": fold.fold_id,
                "spec": spec["name"],
                "cache_group": f"{fold.fold_id}|{spec['horizon_minutes']}m|{spec['target_type']}",
                "status": "PENDING",
            }
    payload = {"schema": "phase7a_study_ledger_v1", "created_unix": time.time(), "runs": runs}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    _atomic(ledger, payload)
    return payload


def record(ledger: Path, report_path: Path, reload_path: Path) -> dict:
    payload = json.loads(ledger.read_text())
    report = json.loads(report_path.read_text())
    reload_record = json.loads(reload_path.read_text())
    key = f"{report['fold_id']}|{report['spec']['name']}"
    entry = payload["runs"][key]
    verified = (
        report.get("status") == "COMPLETE"
        and reload_record.get("status") == "RELOAD_VERIFIED"
        and reload_record.get("model_sha256") == report.get("model_artifact_sha256")
        and report.get("test_used_for_selection") is False
        and report.get("prospective_holdout_used") is False
    )
    entry.update(
        {
            "status": "COMPLETE_VERIFIED" if verified else "FAILED",
            "model_sha256": report.get("model_artifact_sha256"),
            "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            "prepared_cache_id": report.get("prepared_cache_id"),
            "recorded_unix": time.time(),
        }
    )
    _atomic(ledger, payload)
    return entry


def summary(ledger: Path) -> dict:
    runs = json.loads(ledger.read_text())["runs"].values()
    counts: dict[str, int] = {}
    for run in runs:
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    groups = {r["cache_group"] for r in runs}
    done_groups = {
        g
        for g in groups
        if all(r["status"] == "COMPLETE_VERIFIED" for r in runs if r["cache_group"] == g)
    }
    return {
        "total_runs": len(list(runs)),
        "status_counts": counts,
        "cache_groups": len(groups),
        "cache_groups_complete": len(done_groups),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "record", "summary"):
        command = sub.add_parser(name)
        command.add_argument("--ledger", type=Path, required=True)
        if name == "record":
            command.add_argument("--report", type=Path, required=True)
            command.add_argument("--reload", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "init":
        init(args.ledger)
        result = summary(args.ledger)
    elif args.command == "record":
        result = record(args.ledger, args.report, args.reload)
    else:
        result = summary(args.ledger)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
