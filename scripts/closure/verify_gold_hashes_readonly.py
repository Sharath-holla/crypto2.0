"""Read-only Gold manifest + SHA-256 verification (standard library only).

Written by Claude (2026-11-06, closure). Opens Gold files for reading only; writes ONE evidence JSON
at --output. It checks the manifest contract and the SHA-256 of every partition file recorded in
the manifest, and that no unlisted file exists below the dataset directory. Schema, physical
columns and Parquet row counts need pyarrow and are checked by scripts/validate_phase7_gold.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

EXPECTED = {
    "dataset_id": "gold-phase7-0cbf2910e8d96c9d19826598",
    "partitions": 138,
    "features": 109,
    "row_count": 50_352_548,
    "feature_version": "multiasset_features_v2",
    "target_version": "multiasset_targets_v2",
    "research_cutoff": "2026-07-01T00:00:00+00:00",
    "prospective_holdout_start": "2026-08-01T00:00:00+00:00",
}


SUMMARY_KEYS = (
    "row_count",
    "feature_version",
    "target_version",
    "research_cutoff",
    "prospective_holdout_start",
    "prospective_holdout_status",
    "prospective_holdout_used",
    "prospective_holdout_evaluation_authorized",
    "july_2026_used",
    "registry_hash",
    "universe_hash",
    "classification",
    "storage_mode",
    "partitioned_by",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:  # read-only
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold-dataset-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.gold_dataset_dir.resolve()
    manifest_path = root / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    errors: list[str] = []

    def expect(name: str, actual: object, wanted: object) -> None:
        if actual != wanted:
            errors.append(f"{name}: expected {wanted!r}, found {actual!r}")

    expect("dataset_id", manifest.get("dataset_id"), EXPECTED["dataset_id"])
    expect("partition_files", len(manifest.get("partition_files", [])), EXPECTED["partitions"])
    expect("feature_columns", len(manifest.get("feature_columns", [])), EXPECTED["features"])
    expect("row_count", manifest.get("row_count"), EXPECTED["row_count"])
    expect("feature_version", manifest.get("feature_version"), EXPECTED["feature_version"])
    expect("target_version", manifest.get("target_version"), EXPECTED["target_version"])
    expect("research_cutoff", manifest.get("research_cutoff"), EXPECTED["research_cutoff"])
    holdout = {
        "prospective_holdout_start": EXPECTED["prospective_holdout_start"],
        "prospective_holdout_status": "LOCKED_UNUSED",
        "prospective_holdout_used": False,
        "prospective_holdout_evaluation_authorized": False,
        "july_2026_used": False,
    }
    for key, wanted in holdout.items():
        expect(key, manifest.get(key), wanted)
    chunk_rows = sum(int(chunk["row_count"]) for chunk in manifest.get("chunks", []))
    expect("sum(chunk row_count)", chunk_rows, EXPECTED["row_count"])
    chunk_parts = sum(int(chunk["partition_count"]) for chunk in manifest.get("chunks", []))
    expect("sum(chunk partition_count)", chunk_parts, EXPECTED["partitions"])

    listed = {}
    for record in manifest["partition_files"]:
        path = (root / record["path"]).resolve()
        if not path.is_relative_to(root):
            errors.append(f"path escapes dataset root: {record['path']}")
            continue
        listed[path] = record["sha256"]
    on_disk = {p.resolve() for p in (root / "dataset").rglob("*") if p.is_file()}
    unlisted = sorted(str(p.relative_to(root)) for p in on_disk - set(listed))
    missing = sorted(str(p.relative_to(root)) for p in set(listed) - on_disk)
    if unlisted:
        errors.append(f"{len(unlisted)} unlisted file(s) on disk")
    if missing:
        errors.append(f"{len(missing)} listed file(s) missing")

    started = time.time()
    mismatches, hashed, total_bytes = [], 0, 0
    for index, (path, wanted) in enumerate(sorted(listed.items()), 1):
        if path not in on_disk:
            continue
        actual = sha256_file(path)
        hashed += 1
        total_bytes += path.stat().st_size
        if actual != wanted:
            relative = str(path.relative_to(root))
            mismatches.append({"path": relative, "expected": wanted, "actual": actual})
        if index % 10 == 0:
            elapsed = time.time() - started
            print(f"hashed {index}/{len(listed)} ({elapsed:.0f}s)", file=sys.stderr, flush=True)
    if mismatches:
        errors.append(f"{len(mismatches)} SHA-256 mismatch(es)")

    evidence = {
        "verifier": "scripts/closure/verify_gold_hashes_readonly.py",
        "mode": "READ_ONLY_STDLIB",
        "dataset_dir": str(root),
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "dataset_id": manifest.get("dataset_id"),
        "partitions_listed": len(listed),
        "files_hashed": hashed,
        "bytes_hashed": total_bytes,
        "unlisted_files": unlisted,
        "missing_files": missing,
        "sha256_mismatches": mismatches,
        "manifest_summary": {
            key: manifest.get(key)
            for key in SUMMARY_KEYS
        },
        "feature_count": len(manifest.get("feature_columns", [])),
        "errors": errors,
        "verdict": "GOLD_HASH_VERIFICATION_PASS" if not errors else "GOLD_HASH_VERIFICATION_FAIL",
        "not_checked_here": "Parquet schema, physical columns, per-file row counts (need pyarrow)",
        "duration_seconds": round(time.time() - started, 1),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(evidence["verdict"])
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
