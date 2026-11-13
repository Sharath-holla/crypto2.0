"""Persist and restore completed Phase 7 run artifacts across temporary cloud sessions.

ADDED BY CLAUDE (2026-11-13, experiment/phase7-cloud-training-prep). Operational only.

``export``  copies a run's SMALL artifacts (reports, checkpoints, models, execution manifests,
            ledgers, training-metric logs, admission/validation records) into a destination
            directory (normally inside the Git checkout, then committed and pushed) with a
            ``PERSISTED_MANIFEST.json`` of SHA-256 for every file. Prepared caches, spill files,
            Arrow/NumPy matrices and market data are never exported.
``restore`` verifies every SHA-256 in that manifest, then copies the files back under a new
            session's run root. It refuses to overwrite a different existing file, so the
            canonical resume logic (checkpoint identities) decides what is complete.
``status``  lists checkpoint stages and report statuses found under a run root.

All commands are dry runs unless ``--execute`` is given.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA = "phase7_persisted_run_v1"
INCLUDED_SUFFIXES = frozenset(
    {".json", ".jsonl", ".joblib", ".txt", ".log", ".csv", ".md", ".sha256", ".toml"}
)
EXCLUDED_PARTS = frozenset({"prepared_cache", ".transfer-state", "__pycache__"})
EXCLUDED_PREFIXES = (".low-memory-spill-",)
MAX_FILE_BYTES = 200 * 1024**2
MAX_TOTAL_BYTES = 1024**3


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _eligible(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_PARTS for part in relative.parts):
        return False
    if any(part.startswith(EXCLUDED_PREFIXES) for part in relative.parts):
        return False
    return path.is_file() and not path.is_symlink() and path.suffix in INCLUDED_SUFFIXES


def export_plan(sources: dict[str, Path]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    skipped: list[str] = []
    for label, root in sources.items():
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if not _eligible(path, root):
                skipped.append(f"{label}/{path.relative_to(root)}")
                continue
            size = path.stat().st_size
            if size > MAX_FILE_BYTES:
                raise RuntimeError(f"artifact exceeds {MAX_FILE_BYTES} bytes: {path}")
            files.append(
                {
                    "label": label,
                    "relative": str(path.relative_to(root)),
                    "bytes": size,
                    "source": str(path),
                }
            )
    total = sum(item["bytes"] for item in files)
    if total > MAX_TOTAL_BYTES:
        raise RuntimeError(f"export would be {total} bytes; refusing (> {MAX_TOTAL_BYTES})")
    return {"files": files, "bytes": total, "skipped_count": len(skipped), "skipped": skipped[:50]}


def export(
    sources: dict[str, Path], destination: Path, *, metadata: dict[str, Any], execute: bool
) -> dict[str, Any]:
    plan = export_plan(sources)
    if not execute:
        return {
            "dry_run": True,
            **{k: v for k, v in plan.items() if k != "files"},
            "file_count": len(plan["files"]),
        }
    records = []
    for item in plan["files"]:
        target = destination / item["label"] / item["relative"]
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        shutil.copyfile(item["source"], temporary)
        os.replace(temporary, target)
        digest = _sha256(target)
        if digest != _sha256(Path(item["source"])):
            raise RuntimeError(f"copy verification failed: {item['source']}")
        records.append(
            {
                "path": f"{item['label']}/{item['relative']}",
                "bytes": item["bytes"],
                "sha256": digest,
            }
        )
    manifest = {
        "schema": SCHEMA,
        "exported_at_unix": time.time(),
        "sources": {label: str(path) for label, path in sources.items()},
        "metadata": metadata,
        "files": records,
    }
    (destination / "PERSISTED_MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8"
    )
    return {
        "dry_run": False,
        "file_count": len(records),
        "bytes": plan["bytes"],
        "destination": str(destination),
    }


def restore(source: Path, targets: dict[str, Path], *, execute: bool) -> dict[str, Any]:
    manifest = json.loads((source / "PERSISTED_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise RuntimeError("not a persisted Phase 7 run")
    actions = {"copy": 0, "identical": 0}
    for record in manifest["files"]:
        stored = source / record["path"]
        if not stored.is_file() or _sha256(stored) != record["sha256"]:
            raise RuntimeError(f"PERSISTED_ARTIFACT_CORRUPT: {record['path']}")
        label, _, relative = record["path"].partition("/")
        if label not in targets:
            raise RuntimeError(f"no restore target for label {label!r}")
        target = targets[label] / relative
        if target.exists():
            if _sha256(target) != record["sha256"]:
                raise RuntimeError(f"RESTORE_CONFLICT: different file already at {target}")
            actions["identical"] += 1
            continue
        actions["copy"] += 1
        if execute:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.tmp")
            shutil.copyfile(stored, temporary)
            os.replace(temporary, target)
    return {
        "dry_run": not execute,
        **actions,
        "files": len(manifest["files"]),
        "metadata": manifest["metadata"],
    }


def status(run_root: Path) -> dict[str, Any]:
    reports = {}
    for path in sorted(run_root.rglob("report.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        reports[str(path.relative_to(run_root))] = payload.get("status")
    checkpoints = sorted(
        str(p.relative_to(run_root)) for p in run_root.rglob("*.json") if "checkpoints" in p.parts
    )
    return {"run_root": str(run_root), "reports": reports, "checkpoint_files": checkpoints}


def _pairs(values: list[str]) -> dict[str, Path]:
    result = {}
    for value in values:
        label, _, path = value.partition("=")
        if not label or not path:
            raise SystemExit(f"expected LABEL=PATH, got {value!r}")
        result[label] = Path(path)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    exporter = sub.add_parser("export")
    exporter.add_argument("--source", action="append", required=True, help="LABEL=PATH")
    exporter.add_argument("--destination", type=Path, required=True)
    exporter.add_argument("--metadata", type=Path, help="JSON file of run metadata")
    exporter.add_argument("--execute", action="store_true")
    restorer = sub.add_parser("restore")
    restorer.add_argument("--source", type=Path, required=True)
    restorer.add_argument("--target", action="append", required=True, help="LABEL=PATH")
    restorer.add_argument("--execute", action="store_true")
    show = sub.add_parser("status")
    show.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "export":
        metadata = json.loads(args.metadata.read_text()) if args.metadata else {}
        result = export(
            _pairs(args.source), args.destination, metadata=metadata, execute=args.execute
        )
    elif args.command == "restore":
        result = restore(args.source, _pairs(args.target), execute=args.execute)
    else:
        result = status(args.run_root)
    print(json.dumps(result, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
