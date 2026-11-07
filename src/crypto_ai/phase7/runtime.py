from __future__ import annotations

import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import psutil

from crypto_ai.phase7.config import PathConfig, ResourceConfig

CacheMode = Literal["auto", "rebuild", "read_only", "disabled"]


def resolve_runtime_input_path(value: str | Path) -> Path:
    """Relocate an explicitly mapped immutable input without rewriting its manifest."""

    original = str(value).replace("\\", "/")
    mappings: list[tuple[str, Path]] = []
    for family in ("DATA", "ARTIFACT", "GOLD", "MODEL", "REPORT"):
        old = os.environ.get(f"PHASE7_LEGACY_{family}_ROOT", "").strip()
        if not old:
            continue
        new = os.environ.get(f"PHASE7_{family}_ROOT", "").strip()
        if not new:
            raise ValueError(f"PHASE7_{family}_ROOT is required for legacy input remapping")
        mappings.append((old.replace("\\", "/").rstrip("/") + "/", Path(new).resolve()))
    for prefix, root in sorted(mappings, key=lambda item: -len(item[0])):
        if original.startswith(prefix):
            resolved = (root / original[len(prefix) :]).resolve()
            if not resolved.is_relative_to(root):
                raise ValueError("legacy input reference escaped the configured runtime root")
            return resolved
    return Path(value).expanduser().resolve()


def _environment_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else default.expanduser().resolve()


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    data_root: Path
    gold_root: Path
    artifact_root: Path
    cache_root: Path
    checkpoint_root: Path
    model_root: Path
    report_root: Path
    log_root: Path

    @classmethod
    def resolve(cls, paths: PathConfig) -> RuntimePaths:
        artifact_root = _environment_path("PHASE7_ARTIFACT_ROOT", paths.artifact_root)
        return cls(
            data_root=_environment_path("PHASE7_DATA_ROOT", paths.data_root),
            gold_root=_environment_path("PHASE7_GOLD_ROOT", paths.gold_root),
            artifact_root=artifact_root,
            cache_root=_environment_path("PHASE7_CACHE_ROOT", artifact_root / "prepared_cache"),
            checkpoint_root=_environment_path("PHASE7_CHECKPOINT_ROOT", paths.checkpoint_root),
            model_root=_environment_path("PHASE7_MODEL_ROOT", artifact_root / "models"),
            report_root=_environment_path("PHASE7_REPORT_ROOT", artifact_root / "reports"),
            log_root=_environment_path("PHASE7_LOG_ROOT", artifact_root / "logs"),
        )

    def validate(self, *, require_gold: bool = True, create_outputs: bool = True) -> list[str]:
        errors: list[str] = []
        for name in (
            "artifact_root",
            "cache_root",
            "checkpoint_root",
            "model_root",
            "report_root",
            "log_root",
        ):
            output = getattr(self, name).resolve()
            if any(
                output.is_relative_to(source.resolve()) or source.resolve().is_relative_to(output)
                for source in (self.gold_root, self.data_root)
            ):
                errors.append(f"{name} overlaps protected Gold/Silver input roots: {output}")
        if errors:
            return errors  # Do not even create/probe output directories on an unsafe mapping.
        if require_gold and (not self.gold_root.is_dir() or not os.access(self.gold_root, os.R_OK)):
            errors.append(f"Gold root is not a readable directory: {self.gold_root}")
        for name in (
            "artifact_root",
            "cache_root",
            "checkpoint_root",
            "model_root",
            "report_root",
            "log_root",
        ):
            path = getattr(self, name)
            try:
                if create_outputs:
                    path.mkdir(parents=True, exist_ok=True)
                if not path.is_dir():
                    raise OSError("not a directory")
                if create_outputs:
                    with tempfile.NamedTemporaryFile(
                        prefix=".phase7-write-test-", dir=path, delete=True
                    ):
                        pass
                elif not os.access(path, os.R_OK | os.W_OK):
                    raise OSError("directory access check failed (write probe not performed)")
            except OSError as exc:
                errors.append(f"{name} is not writable ({path}): {exc}")
        return errors

    def payload(self) -> dict[str, str]:
        return {key: str(value) for key, value in asdict(self).items()}

    def checkpoint_roots(self) -> tuple[tuple[str, Path], ...]:
        return tuple(
            (name, getattr(self, name))
            for name in ("data_root", "artifact_root", "gold_root", "model_root", "report_root")
        )

    def legacy_checkpoint_roots(self) -> tuple[tuple[str, Path], ...]:
        """Explicit source-root mappings; hashes still validate migrated bytes."""

        return tuple(
            (value, getattr(self, name))
            for name in ("data_root", "artifact_root", "gold_root", "model_root", "report_root")
            if (value := os.environ.get(f"PHASE7_LEGACY_{name.upper()}", "").strip())
        )


def cache_mode_from_environment() -> CacheMode:
    value = os.environ.get("PHASE7_CACHE_MODE", "auto").strip().lower()
    if value not in {"auto", "rebuild", "read_only", "disabled"}:
        raise ValueError("PHASE7_CACHE_MODE must be one of auto, rebuild, read_only, or disabled")
    return value  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class ComputeBudget:
    total_cpu_threads: int
    model_parallelism: int
    lightgbm_threads_per_model: int

    @classmethod
    def resolve(cls, resources: ResourceConfig) -> ComputeBudget:
        available = effective_cpu_count()
        total = int(os.environ.get("PHASE7_TOTAL_CPU_THREADS", available))
        parallelism = int(
            os.environ.get("PHASE7_MODEL_PARALLELISM", min(resources.max_workers, total))
        )
        requested_threads = int(
            os.environ.get("PHASE7_LIGHTGBM_THREADS_PER_MODEL", resources.model_threads)
        )
        if min(total, parallelism, requested_threads) < 1:
            raise ValueError("Phase 7 compute budget values must be positive")
        if total > available:
            raise ValueError(
                f"PHASE7_TOTAL_CPU_THREADS={total} exceeds detected logical CPUs={available} "
                "(effective affinity/cgroup ceiling)"
            )
        if total < parallelism:
            raise ValueError(
                f"PHASE7_TOTAL_CPU_THREADS={total} is less than "
                f"PHASE7_MODEL_PARALLELISM={parallelism}"
            )
        threads = min(requested_threads, max(1, total // parallelism))
        if parallelism * threads > total:
            raise RuntimeError("resolved Phase 7 compute budget oversubscribes CPU threads")
        return cls(total, parallelism, threads)


def git_commit(repository_root: Path | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def cpu_availability() -> dict[str, Any]:
    """Conservative whole-thread budget, including affinity and fractional cgroup quotas."""
    from crypto_ai.phase7.resource_estimate import cgroup_limits

    host = os.cpu_count() or 1
    try:
        affinity = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity = None
    quota = cgroup_limits().get("cgroup_cpu_quota_cpus")
    ceilings = [host]
    if affinity is not None:
        ceilings.append(max(1, affinity))
    if quota is not None:
        ceilings.append(max(1, math.floor(quota)))
    return {
        "host_cpu_count": host,
        "affinity_cpu_count": affinity,
        "cgroup_cpu_quota_cpus": quota,
        "effective_cpu_count": min(ceilings),
    }


def effective_cpu_count() -> int:
    return int(cpu_availability()["effective_cpu_count"])


def _container_adjusted_memory(total: int, available: int) -> tuple[int, int]:
    """CHANGED BY CLAUDE (2026-11-06, RunPod review): psutil reports HOST memory.

    Inside a container (RunPod, Docker, Kubernetes) the cgroup limit is the real ceiling, so the
    RAM floor, the preflight and the telemetry must use it. Without a readable cgroup limit (macOS,
    bare metal) the psutil values are returned unchanged.
    """

    from crypto_ai.phase7.resource_estimate import cgroup_limits

    limits = cgroup_limits()
    limit = limits.get("cgroup_memory_limit_bytes")
    if not limit:
        return total, available
    current = limits.get("cgroup_memory_current_bytes")
    # A finite ceiling without usage telemetry cannot prove available container memory.
    remaining = 0 if current is None else max(int(limit) - int(current), 0)
    remaining = min(remaining, limits.get("cgroup_memory_available_bytes", remaining))
    return min(total, int(limit)), min(available, remaining)


def system_snapshot(path: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(path)
    vm = psutil.virtual_memory()
    # OLD CODE: "ram_total_bytes": int(vm.total), "ram_available_bytes": int(vm.available)
    ram_total, ram_available = _container_adjusted_memory(int(vm.total), int(vm.available))
    return {
        "python": platform.python_version(),
        "os": platform.platform(),
        "cpu_count": effective_cpu_count(),
        **cpu_availability(),
        "host_ram_total_bytes": int(vm.total),
        "ram_total_bytes": ram_total,
        "ram_available_bytes": ram_available,
        "disk_total_bytes": usage.total,
        "disk_free_bytes": usage.free,
    }


_PEAK_RSS_BYTES = 0


def memory_snapshot() -> dict[str, int]:
    """Return current process/host memory and the observed process RSS peak."""

    global _PEAK_RSS_BYTES
    rss = int(psutil.Process().memory_info().rss)
    _PEAK_RSS_BYTES = max(_PEAK_RSS_BYTES, rss)
    vm = psutil.virtual_memory()
    # CHANGED BY CLAUDE (2026-11-06, RunPod review): container-aware RAM.
    # OLD CODE: "ram_available_bytes": int(vm.available), "ram_total_bytes": int(vm.total)
    ram_total, ram_available = _container_adjusted_memory(int(vm.total), int(vm.available))
    return {
        "process_rss_bytes": rss,
        "process_peak_rss_bytes": _PEAK_RSS_BYTES,
        "ram_available_bytes": ram_available,
        "ram_total_bytes": ram_total,
    }


def emit_event(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, sort_keys=True, default=str), flush=True)
