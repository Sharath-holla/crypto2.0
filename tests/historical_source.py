"""Read exact historical Git bytes from Git or a checksum-anchored export bundle.

The bundle is actual git-show output from the fixed September baseline commit,
not current source, model output, or market data. Missing/corrupt evidence fails.
"""

from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = "28d3098a82952a3d09073e4d81b5281f856c072e"
BUNDLE = "tests/fixtures/historical_phase7_28d3098.json"
BUNDLE_SHA256 = "d7a0882ae33001b5f14235989d46c4cf8d0dc850223f807d30ca77fb12b7edd3"


def _bundle(root: Path, commit: str) -> dict:
    data = (root / BUNDLE).read_bytes()
    if commit != COMMIT or hashlib.sha256(data).hexdigest() != BUNDLE_SHA256:
        raise ValueError("HISTORICAL_GIT_BUNDLE_IDENTITY_MISMATCH")
    result = json.loads(data)
    if result["schema"] != "historical_git_source_bundle_v1" or result["commit"] != commit:
        raise ValueError("HISTORICAL_GIT_BUNDLE_SCHEMA_MISMATCH")
    return result


def historical_blob(root: Path, commit: str, relative: str) -> bytes:
    if (root / ".git").exists():
        return subprocess.run(
            ["git", "show", f"{commit}:{relative}"], cwd=root, check=True, capture_output=True
        ).stdout
    return base64.b64decode(_bundle(root, commit)["blobs"][relative], validate=True)


def historical_phase7_paths(root: Path, commit: str) -> list[str]:
    if (root / ".git").exists():
        return subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", commit, "--", "src/crypto_ai/phase7"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
    return list(_bundle(root, commit)["phase7_tree"])
