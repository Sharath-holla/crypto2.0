"""Portable dependency compatibility, separate from machine/resource observations."""

from __future__ import annotations

import hashlib
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any

from crypto_ai.phase7.config import stable_hash


def scientific_environment_identity(repository_root: Path | None = None) -> dict[str, Any]:
    root = repository_root or Path(__file__).resolve().parents[3]
    files = {}
    for name in ("pyproject.toml", "uv.lock"):
        content = (root / name).read_bytes().replace(b"\r\n", b"\n")
        files[name] = hashlib.sha256(content).hexdigest()
    payload = {
        "schema": "phase7_dependency_compatibility_v1",
        "python": platform.python_version(),
        "packages": {
            name: version(name)
            for name in ("numpy", "pyarrow", "lightgbm", "scikit-learn", "joblib", "pydantic")
        },
        "dependency_files": files,
    }
    return {**payload, "identity": stable_hash(payload, length=64)}
