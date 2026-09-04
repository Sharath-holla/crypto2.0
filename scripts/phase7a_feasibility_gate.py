#!/usr/bin/env python3
"""Fail-closed 24-hour projection gate after the real Phase 7A first fold."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def evaluate(summary: dict[str, object], launched_at: datetime, now: datetime) -> dict[str, object]:
    if summary.get("status") != "CANARY_COMPLETE" or summary.get("folds_attempted") != 1:
        raise ValueError("A complete one-fold Phase 7A canary is required")
    timings = summary.get("fold_timings")
    if not isinstance(timings, list) or len(timings) != 1 or not isinstance(timings[0], dict):
        raise ValueError("The canary does not contain exactly one measured fold timing")
    fold_seconds = float(timings[0]["wall_seconds"])
    fold_count = int(summary["fold_count"])
    if fold_count != 16 or fold_seconds <= 0:
        raise ValueError("Phase 7A requires 16 folds and a positive first-fold time")
    elapsed_seconds = max(0.0, (now.astimezone(UTC) - launched_at.astimezone(UTC)).total_seconds())
    remaining_folds = fold_count - 1
    expected_seconds = elapsed_seconds + remaining_folds * fold_seconds + 900.0
    conservative_seconds = elapsed_seconds + remaining_folds * fold_seconds * 1.35 + 1800.0
    continuation_allowed = conservative_seconds <= 85_500.0
    return {
        "status": "CONTINUE" if continuation_allowed else "PAUSED_PROJECTED_OVER_24H",
        "authorized_launch_at": launched_at.astimezone(UTC).isoformat(),
        "evaluated_at": now.astimezone(UTC).isoformat(),
        "elapsed_seconds": elapsed_seconds,
        "fold1_seconds": fold_seconds,
        "folds_total": fold_count,
        "folds_remaining": remaining_folds,
        "expected_total_seconds": expected_seconds,
        "conservative_multiplier": 1.35,
        "conservative_fixed_overhead_seconds": 1800.0,
        "conservative_total_seconds": conservative_seconds,
        "graceful_stop_deadline_seconds": 85_500,
        "hard_cap_seconds": 86_400,
        "continuation_allowed": continuation_allowed,
        "fold1_timing": timings[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    launch = json.loads(args.launch.read_text(encoding="utf-8"))
    launched_at = datetime.fromisoformat(str(launch["authorized_launch_at"]))
    if launched_at.tzinfo is None:
        raise ValueError("Authorized launch timestamp must be timezone-aware")
    result = evaluate(summary, launched_at, datetime.now(UTC))
    _atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["continuation_allowed"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
