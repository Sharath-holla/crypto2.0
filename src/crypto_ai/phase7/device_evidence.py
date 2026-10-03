"""Conservative fitted-backend + live PID/device attestation; never CPU retry."""

from __future__ import annotations

import os
import re
import subprocess
import time
from threading import Event, Thread
from typing import Any


def process_device_snapshot() -> dict[str, Any]:
    try:
        outcome = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        )
        processes = []
        for line in outcome.stdout.splitlines():
            fields = [item.strip() for item in line.split(",")]
            if len(fields) == 3 and int(fields[0]) == os.getpid():
                processes.append(
                    {
                        "pid": int(fields[0]),
                        "gpu_uuid": fields[1],
                        "vram_bytes": int(float(fields[2]) * 1024**2),
                    }
                )
        return {
            "status": "OBSERVED" if processes else "NO_CURRENT_PID_EVIDENCE",
            "processes": processes,
            "process_vram_bytes": sum(p["vram_bytes"] for p in processes),
            "sample_time_monotonic": time.monotonic(),
        }
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {
            "status": "UNVERIFIABLE",
            "error_type": type(exc).__name__,
            "process_vram_bytes": None,
            "processes": [],
        }


def attest_fitted_device(
    estimator: Any, requested: str, samples: list[dict[str, Any]]
) -> dict[str, Any]:
    """Requested parameters alone cannot authorize actual_backend=GPU."""
    native = estimator.booster_.model_to_string()
    match = re.search(r"\[device_type:\s*(cpu|gpu|cuda)\]", native)
    actual = match.group(1) if match else None
    observed = [
        p
        for sample in samples
        for p in sample.get("processes", [])
        if p.get("pid") == os.getpid() and p.get("gpu_uuid") and p.get("vram_bytes", 0) > 0
    ]
    if requested not in {"gpu", "cuda"} or actual != requested or not observed:
        raise RuntimeError(
            "GPU fit is unverified: native fitted backend and independent "
            "live PID/device evidence required"
        )
    return {
        "status": "PASS",
        "actual_backend": actual,
        "pid": os.getpid(),
        "evidence_method": "NATIVE_FITTED_BOOSTER_PLUS_NVIDIA_LIVE_PROCESS",
        "sampled_peak_process_vram_bytes": max(p["vram_bytes"] for p in observed),
        "devices": sorted({p["gpu_uuid"] for p in observed}),
        "samples": samples,
        "not_a_continuous_peak_claim": True,
    }


def fit_with_device_evidence(estimator: Any, backend: Any, *args: Any, **kwargs: Any) -> Any:
    if not backend.gpu_requested:
        estimator.fit(*args, **kwargs)
        return estimator
    from crypto_ai.phase7.backend import _backend_error, gpu_snapshot

    samples = []
    stop = Event()

    def sample_during_fit():
        while not stop.is_set():
            samples.append(process_device_snapshot())
            stop.wait(0.1)

    sampler = Thread(target=sample_during_fit, daemon=True, name="phase7-device-evidence")
    started = time.monotonic()
    sampler.start()
    try:
        estimator.fit(*args, **kwargs)
        samples.append(process_device_snapshot())
        evidence = attest_fitted_device(estimator, backend.name, samples)
        evidence["hardware_driver_snapshot"] = gpu_snapshot()
        evidence["fit_elapsed_seconds"] = time.monotonic() - started
        estimator.phase7_device_evidence_ = evidence
    except Exception as exc:
        raise _backend_error(backend, exc) from exc
    finally:
        stop.set()
        sampler.join(timeout=3)
    return estimator
