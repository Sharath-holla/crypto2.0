"""Dependency + numerical-platform compatibility, separate from resource observations.

Prepared matrices and fitted models are float64 numerical artifacts.  Their bits can
differ across operating systems, CPU architectures and BLAS builds, so the OS family
and machine architecture are part of the identity: an artifact generated on a Mac
(darwin/arm64) is never silently reusable by the Linux/x86_64 production run.  Memory,
disk, GPU presence and hostnames remain excluded (they do not change scientific bits).
"""

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
        "schema": "phase7_dependency_platform_compatibility_v2",
        "python": platform.python_version(),
        "numerical_platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python_implementation": platform.python_implementation(),
        },
        "packages": {
            name: version(name)
            for name in ("numpy", "pyarrow", "lightgbm", "scikit-learn", "joblib", "pydantic")
        },
        "dependency_files": files,
    }
    return {**payload, "identity": stable_hash(payload, length=64)}
