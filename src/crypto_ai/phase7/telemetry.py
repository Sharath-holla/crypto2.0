"""Sampled runtime evidence only; values never enter scientific resume keys."""

from __future__ import annotations

import functools
import os
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_ai.phase7.config import PathConfig
from crypto_ai.phase7.resources import existing_ancestor, resource_admission
from crypto_ai.phase7.runtime import RuntimePaths, emit_event, memory_snapshot


def telemetry(stage: str, phase: str, *, started: float | None = None, **fields: Any) -> None:
    try:
        _telemetry(stage, phase, started=started, **fields)
    except Exception as exc:
        # Resource evidence is best effort; never mask an ENOSPC/publication failure.
        emit_event(
            "RUNTIME_TELEMETRY_UNAVAILABLE", stage=stage, phase=phase, error_type=type(exc).__name__
        )


def _telemetry(stage: str, phase: str, *, started: float | None = None, **fields: Any) -> None:
    paths = RuntimePaths.resolve(PathConfig())
    from crypto_ai.phase7.prepared_cache import cache_size_report

    disks = {
        name: shutil.disk_usage(existing_ancestor(getattr(paths, name))).free
        for name in ("cache_root", "checkpoint_root", "model_root", "report_root", "artifact_root")
    }
    disks["temporary_root"] = shutil.disk_usage(
        existing_ancestor(Path(os.environ.get("PHASE7_TEMP_ROOT", str(paths.cache_root))))
    ).free
    gpu = {"gpu_vram_bytes": None, "gpu_vram_status": "NOT_APPLICABLE_CPU"}
    if os.environ.get("PHASE7_LGBM_DEVICE", "cpu") != "cpu":
        from crypto_ai.phase7.device_evidence import process_device_snapshot

        sample = process_device_snapshot()
        gpu = {
            "gpu_vram_bytes": sample.get("process_vram_bytes"),
            "gpu_vram_status": sample["status"],
        }
    emit_event(
        "RUNTIME_TELEMETRY",
        stage=stage,
        phase=phase,
        timestamp=datetime.now(UTC).isoformat(),
        elapsed_seconds=None if started is None else time.monotonic() - started,
        **memory_snapshot(),
        disk_free_bytes_by_root=disks,
        cache_bytes=cache_size_report(paths.cache_root)["total_bytes"],
        model_backend=os.environ.get("PHASE7_LGBM_DEVICE", "cpu"),
        threads=os.environ.get("PHASE7_LIGHTGBM_THREADS_PER_MODEL"),
        **gpu,
        **fields,
    )


def instrument(stage: str, *, admit: bool = False):
    """Record bounded stage snapshots, not a continuous RSS/VRAM peak claim."""

    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            if admit:
                roots = (args[0].root,) if args and hasattr(args[0], "root") else ()
                resource_admission(stage, additional_roots=roots)
            started = time.monotonic()
            telemetry(stage, "START", started=started)
            try:
                result = function(*args, **kwargs)
            except BaseException:
                telemetry(stage, "FAILED", started=started)
                raise
            fields = {}
            inputs = getattr(result, "model_inputs", None)
            if inputs is not None:
                fields = {
                    "matrix_shape": list(inputs.train_x.shape),
                    "matrix_bytes": inputs.train_x.nbytes + inputs.validation_x.nbytes,
                }
            telemetry(stage, "END", started=started, **fields)
            return result

        return wrapped

    return decorate
