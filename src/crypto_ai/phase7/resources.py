"""Configurable execution-only admission; no empirical RAM sufficiency claim."""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path
from typing import Any

from crypto_ai.phase7.config import PathConfig
from crypto_ai.phase7.runtime import RuntimePaths, memory_snapshot


def existing_ancestor(path: Path) -> Path:
    current = path.resolve()
    while not current.exists() and current != current.parent:
        current = current.parent
    return current if current.is_dir() else current.parent


def configured_floor(primary: str, legacy: str, *, default: float = 0) -> float:
    raw = os.environ.get(primary, os.environ.get(legacy, str(default)))
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{primary}/{legacy} must be positive and finite when configured")
    # Explicit zero is rejected too; only an absent floor permits zero.
    if (primary in os.environ or legacy in os.environ) and value <= 0:
        raise ValueError(f"{primary}/{legacy} must be positive and finite when configured")
    return value


def resource_admission(
    stage: str,
    *,
    paths: RuntimePaths | None = None,
    additional_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    runtime = paths or RuntimePaths.resolve(PathConfig())
    ram_floor = configured_floor("PHASE7_MIN_FREE_RAM_GIB", "PHASE7_MIN_AVAILABLE_RAM_GB")
    disk_floor = configured_floor("PHASE7_MIN_FREE_DISK_GIB", "PHASE7_MIN_FREE_DISK_GB")
    memory = memory_snapshot()
    roots = {
        name: getattr(runtime, name)
        for name in (
            "artifact_root",
            "cache_root",
            "checkpoint_root",
            "model_root",
            "report_root",
        )
    }
    roots["temporary_root"] = Path(os.environ.get("PHASE7_TEMP_ROOT", str(runtime.cache_root)))
    roots.update({f"additional_{i}": value for i, value in enumerate(additional_roots)})
    disk = {
        name: {
            "path": str(existing_ancestor(path)),
            "free_bytes": shutil.disk_usage(existing_ancestor(path)).free,
        }
        for name, path in roots.items()
    }
    if memory["ram_available_bytes"] < ram_floor * 1024**3:
        raise MemoryError(f"{stage}: available RAM below configured {ram_floor} GiB floor")
    for name, value in disk.items():
        if value["free_bytes"] < disk_floor * 1024**3:
            raise OSError(f"{stage}: {name} free disk below configured {disk_floor} GiB floor")
    return {
        "stage": stage,
        "ram_floor_gib": ram_floor,
        "disk_floor_gib": disk_floor,
        "memory": memory,
        "filesystems": disk,
    }
