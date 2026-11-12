"""Exercise production write/lock primitives on an isolated target filesystem directory."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from crypto_ai.phase7.artifacts import atomic_json, fsync_directory
from crypto_ai.phase7.prepared_cache import PreparedDataCache
from crypto_ai.phase7.run_lease import RunLease

_CHILD = """
import sys
from pathlib import Path
from crypto_ai.phase7.prepared_cache import PreparedDataCache
from crypto_ai.phase7.run_lease import RunLease, RunLeaseError
root = Path(sys.argv[2])
try:
    if sys.argv[1] == "cache":
        with PreparedDataCache(root, "auto")._publication_lock("probe", timeout_seconds=0.1):
            pass
    else:
        with RunLease(root, root.name, {"probe": True}, mode="production"):
            pass
except (TimeoutError, RunLeaseError):
    sys.exit(0 if sys.argv[3] == "blocked" else 3)
sys.exit(4 if sys.argv[3] == "blocked" else 0)
"""


def qualify_filesystem(root: Path, *, require_linux: bool = True) -> dict[str, Any]:
    if require_linux and (
        sys.platform != "linux" or platform.machine().lower() not in {"x86_64", "amd64"}
    ):
        return {
            "status": "FAIL",
            "reason": "genuine Linux/x86_64 required",
            "filesystem_validation": "NOT_RUN",
        }
    isolated = root.resolve() / f"phase7-filesystem-probe-{uuid.uuid4().hex}"
    isolated.mkdir(parents=True)
    target = isolated / "atomic.json"
    atomic_json(target, {"generation": 1})
    atomic_json(target, {"generation": 2}, immutable=False)
    if json.loads(target.read_text()) != {"generation": 2}:
        raise ValueError("ATOMIC_RENAME_READBACK_FAILED")
    source = isolated / "unpublished"
    source.mkdir()
    (source / "entry").write_text("probe")
    fsync_directory(source)
    published = isolated / "published"
    source.rename(published)
    fsync_directory(isolated)
    if (published / "entry").read_text() != "probe":
        raise ValueError("DIRECTORY_RENAME_READBACK_FAILED")
    cache_root = isolated / "cache-lock"
    cache_root.mkdir()
    cache = PreparedDataCache(cache_root, "auto")
    lease_root = isolated / "probe-run"

    def child(kind: str, path: Path, expected: str) -> None:
        outcome = subprocess.run(
            [sys.executable, "-c", _CHILD, kind, str(path), expected],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if outcome.returncode:
            raise RuntimeError(
                f"{kind} cross-process exclusion/release failed: "
                f"{outcome.returncode}: {outcome.stderr}"
            )

    with cache._publication_lock("probe"):
        child("cache", cache_root, "blocked")
    child("cache", cache_root, "available")
    with RunLease(lease_root, lease_root.name, {"probe": True}, mode="production"):
        child("lease", lease_root, "blocked")
    child("lease", lease_root, "available")
    result = {
        "status": "PASS",
        "os": platform.platform(),
        "machine": platform.machine(),
        "path": str(isolated),
        "device_id": os.stat(isolated).st_dev,
        "checks": [
            "file_fsync",
            "atomic_file_replace",
            "directory_rename",
            "directory_fsync",
            "cross_process_cache_lock_exclusion_and_release",
            "cross_process_run_lease_flock_exclusion_and_release",
        ],
        "scope": (
            "primitive functional verification; "
            "no power-loss guarantee or model/cache qualification"
        ),
    }
    atomic_json(isolated / "qualification.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help="isolated directory on the intended local cache/output filesystem",
    )
    args = parser.parse_args()
    result = qualify_filesystem(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
