"""Disk planning and sequential prepared-cache release for small writable allowances.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-low-memory-training). Operational only: it never
reads market data into a model and never changes a cache's contents.

``plan``    projects peak simultaneous disk use from MEASURED bytes per fold row (synthetic
            full-scale runs of the committed low-memory profile) and the free space measured now.
``release`` deletes a published prepared cache ONLY when every report that references it is
            terminal (``COMPLETE`` or ``INELIGIBLE``), no partial/unknown report references it, the
            operator passes ``--confirm`` and the run is offline. Before deletion the cache
            manifest (per-file SHA-256, identity, shapes) is copied to a receipt directory, so a
            later re-preparation can be checked byte-for-byte against the released cache.
            The repository's conservative ``cleanup_cache_entries`` keeps refusing referenced
            caches; this command is the explicit, audited exception for completed work.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

# Measured (experiments/phase7_low_memory/results/repo_profile_*.json): 4,922,887 rows ->
# spill 5.52 GB, cache 8.91 GB; 5,783,040 rows -> spill 6.49 GB, cache 10.58 GB.
SPILL_BYTES_PER_FOLD_ROW = 1_122
CACHE_BYTES_PER_FOLD_ROW = 1_830
SAFETY_BYTES = 2 * 10**9
TERMINAL_STATUSES = frozenset({"COMPLETE", "INELIGIBLE"})


def plan(*, free_bytes: int, fold_rows: int, pending_input_bytes: int = 0) -> dict[str, Any]:
    spill = fold_rows * SPILL_BYTES_PER_FOLD_ROW
    cache = fold_rows * CACHE_BYTES_PER_FOLD_ROW
    peak = pending_input_bytes + spill + cache
    return {
        "free_bytes_now": free_bytes,
        "pending_input_bytes": pending_input_bytes,
        "fold_rows": fold_rows,
        "estimated_spill_bytes": spill,
        "estimated_cache_bytes": cache,
        "estimated_peak_additional_bytes": peak,
        "safety_bytes": SAFETY_BYTES,
        "projected_minimum_free_bytes": free_bytes - peak,
        "fits": free_bytes - peak >= SAFETY_BYTES,
        "basis": "MEASURED_BYTES_PER_ROW_FROM_SYNTHETIC_FULL_SCALE_RUNS",
        "sequential_rule": "at most one published cache plus one spill set at a time; release a "
        "cache only after all of its specifications are terminal",
    }


MODEL_AND_REPORT_ALLOWANCE_BYTES = 300 * 10**6
LOG_ALLOWANCE_BYTES = 300 * 10**6


def directory_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
            except OSError:
                continue
    return total


def budget(
    *,
    probe: Path,
    fold_rows: int,
    data_bytes_pending: int,
    occupied: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """Peak simultaneous disk use for ONE fold/horizon/target preparation plus its training.

    Free space is measured on the filesystem that holds ``probe`` (the writable allowance), not
    the device size. Already-occupied items (repository, virtualenv, uv cache, staged data) are
    reported for transparency; they are already excluded from ``free``.
    """

    free = shutil.disk_usage(probe).free
    planned = {
        "dataset_still_to_download": data_bytes_pending,
        "spill_unfiltered_fold_segments": fold_rows * SPILL_BYTES_PER_FOLD_ROW,
        "prepared_cache_tables_and_matrices": fold_rows * CACHE_BYTES_PER_FOLD_ROW,
        "models_reports_checkpoints": MODEL_AND_REPORT_ALLOWANCE_BYTES,
        "logs_and_telemetry": LOG_ALLOWANCE_BYTES,
        "filesystem_safety_margin": SAFETY_BYTES,
    }
    peak = sum(planned.values())
    return {
        "free_bytes_now": free,
        "already_occupied_bytes": {
            name: directory_bytes(path) for name, path in (occupied or {}).items()
        },
        "planned_additional_bytes": planned,
        "planned_peak_bytes": peak,
        "projected_free_at_peak_bytes": free - peak + SAFETY_BYTES,
        "fits": free >= peak,
        "basis": "MEASURED_BYTES_PER_ROW_FROM_SYNTHETIC_FULL_SCALE_RUNS; spill and cache sizes "
        "are the same for staged and unstaged preparation (staged filtered tables and matrices "
        "are adopted into the cache by rename)",
        "rule": "stop before an operation whose planned peak does not fit; never delete a cache "
        "whose reports are not all terminal",
    }


def _reports_referencing(cache_id: str, report_roots: tuple[Path, ...]) -> list[dict[str, Any]]:
    found = []
    for root in report_roots:
        for path in root.rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            if cache_id not in text:
                continue
            payload = json.loads(text)
            found.append({"path": str(path), "status": payload.get("status"), "payload": payload})
    return found


def release(
    *,
    cache_root: Path,
    cache_id: str,
    report_roots: tuple[Path, ...],
    receipt_dir: Path,
    confirm: bool,
    offline: bool,
) -> dict[str, Any]:
    from crypto_ai.phase7.prepared_cache import PreparedDataCache, _directory_size

    if len(cache_id) != 64 or any(ch not in "0123456789abcdef" for ch in cache_id):
        raise ValueError(f"invalid prepared-cache ID: {cache_id!r}")
    if not offline:
        raise RuntimeError("release requires --offline: stop every training process first")
    root = cache_root.resolve()
    target = root / cache_id
    if target.is_symlink() or not target.is_dir() or target.resolve().parent != root:
        raise ValueError("cache entry is missing, aliased or outside the cache root")
    if not report_roots:
        raise ValueError("at least one report root is required")
    references = _reports_referencing(cache_id, report_roots)
    reports = [item for item in references if item["path"].endswith("report.json")]
    if not reports:
        raise RuntimeError("no report references this cache; refusing to release unused work")
    blocking = [item["path"] for item in references if item["status"] not in TERMINAL_STATUSES]
    blocking = [path for path in blocking if path.endswith("report.json")]
    if blocking:
        raise RuntimeError(f"cache is referenced by non-terminal reports: {blocking}")
    summary = {
        "cache_id": cache_id,
        "bytes": _directory_size(target),
        "reports": [{"path": item["path"], "status": item["status"]} for item in reports],
        "manifest": json.loads((target / "manifest.json").read_text(encoding="utf-8")),
        "released_at_unix": time.time(),
        "dry_run": not confirm,
    }
    if not confirm:
        return summary
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt = receipt_dir / f"{cache_id}.release.json"
    receipt.write_text(json.dumps(summary, indent=1, sort_keys=True), encoding="utf-8")
    with PreparedDataCache(root, "auto")._publication_lock("publication"):
        shutil.rmtree(target)
    summary["receipt"] = str(receipt)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    planner = commands.add_parser("plan")
    planner.add_argument("--path", type=Path, required=True)
    planner.add_argument("--fold-rows", type=int, required=True)
    planner.add_argument("--pending-input-bytes", type=int, default=0)
    budgeter = commands.add_parser("budget")
    budgeter.add_argument("--path", type=Path, required=True)
    budgeter.add_argument("--fold-rows", type=int, required=True)
    budgeter.add_argument("--data-bytes-pending", type=int, default=0)
    budgeter.add_argument("--occupied", action="append", default=[], help="LABEL=PATH")
    releaser = commands.add_parser("release")
    releaser.add_argument("--cache-root", type=Path, required=True)
    releaser.add_argument("--cache-id", required=True)
    releaser.add_argument("--report-root", type=Path, action="append", required=True)
    releaser.add_argument("--receipt-dir", type=Path, required=True)
    releaser.add_argument("--confirm", action="store_true")
    releaser.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "budget":
        occupied = dict(
            (item.split("=", 1)[0], Path(item.split("=", 1)[1])) for item in args.occupied
        )
        result = budget(
            probe=args.path,
            fold_rows=args.fold_rows,
            data_bytes_pending=args.data_bytes_pending,
            occupied=occupied,
        )
        print(json.dumps(result, indent=1))
        return 0 if result["fits"] else 2
    if args.command == "plan":
        result = plan(
            free_bytes=shutil.disk_usage(args.path).free,
            fold_rows=args.fold_rows,
            pending_input_bytes=args.pending_input_bytes,
        )
        print(json.dumps(result, indent=1))
        return 0 if result["fits"] else 2
    result = release(
        cache_root=args.cache_root,
        cache_id=args.cache_id,
        report_roots=tuple(args.report_root),
        receipt_dir=args.receipt_dir,
        confirm=args.confirm,
        offline=args.offline,
    )
    result.pop("manifest", None)
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
