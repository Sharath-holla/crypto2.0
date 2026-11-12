"""Verify a committed source export without transferring its .git directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from crypto_ai.data.storage import file_sha256


def verify_source_freeze(repository: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != "phase7_committed_source_export_v1":
        raise ValueError("SOURCE_FREEZE_SCHEMA_MISMATCH")
    records = manifest["files"]
    if not records or len({r["path"] for r in records}) != len(records):
        raise ValueError("SOURCE_FREEZE_EMPTY_OR_DUPLICATE")
    content = json.dumps(records, sort_keys=True).encode()
    if hashlib.sha256(content).hexdigest() != manifest["files_sha256"]:
        raise ValueError("SOURCE_FREEZE_MANIFEST_MISMATCH")
    root = repository.resolve()
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("SOURCE_FREEZE_PATH_ESCAPE")
        path = root / relative
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            raise ValueError("SOURCE_FREEZE_PATH_ESCAPE")
        if (
            not path.is_file()
            or path.stat().st_size != record["bytes"]
            or file_sha256(path) != record["sha256"]
        ):
            raise ValueError(f"SOURCE_FREEZE_FILE_MISMATCH: {relative}")
    return {
        "status": "PASS",
        "commit": manifest["commit"],
        "files": len(records),
        "files_sha256": manifest["files_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = verify_source_freeze(
        args.repository, args.manifest or args.repository / "source-freeze.json"
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
