"""Owner-authorized constrained execution, never a different scientific model."""

from __future__ import annotations

import argparse
import contextvars
import gc
import hashlib
import json
import os
import signal
import time
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

GIB = 1024**3
PROFILE_ENV = "PHASE7_RESOURCE_PROFILE"
CONSTRAINED = "constrained_48gb"
_PROBE = contextvars.ContextVar("phase7_memory_probe", default=False)


def profile() -> str:
    value = os.environ.get(PROFILE_ENV, "standard_smoke")
    if value not in {"standard_smoke", CONSTRAINED}:
        raise ValueError("UNKNOWN_RESOURCE_PROFILE")
    return value


def minimum_ram() -> int:
    # 45 GiB is a hard admission floor, not a claim that the model fits.
    # The expected 50 decimal GB allocation is 46.57 GiB; qualification adds
    # measured peak/headroom requirements and a continuously enforced guard.
    return (45 if profile() == CONSTRAINED else 64) * GIB


def record(stage: str, root: Path) -> dict[str, Any]:
    import shutil

    import psutil

    from crypto_ai.phase7.resource_estimate import cgroup_limits
    from crypto_ai.phase7.runtime import memory_snapshot

    host = psutil.virtual_memory()
    value = {
        "host_memtotal_bytes": int(host.total),
        "host_memavailable_bytes": int(host.available),
        "utc": datetime.now(UTC).isoformat(),
        "stage": stage,
        "resource_profile": profile(),
        **memory_snapshot(),
        **cgroup_limits(),
        "disk_free_bytes": shutil.disk_usage(root).free,
    }
    limit = value.get("cgroup_memory_limit_bytes")
    current = value.get("cgroup_memory_current_bytes")
    value["cgroup_ratio"] = current / limit if limit and current is not None else None
    return value


def severity(value: dict[str, Any]) -> str:
    ratio = value.get("cgroup_ratio")
    headroom = value.get("ram_available_bytes", 0)
    if ratio is None or not 0 <= ratio <= 2:
        return "STOP_TELEMETRY_UNAVAILABLE"
    if ratio >= 0.88 or headroom < 8 * GIB:
        return "STOP_MEMORY_GUARD"
    return "HIGH" if ratio >= 0.82 else "WARNING" if ratio >= 0.75 else "NORMAL"


def append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(value, default=str) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with temp.open("w") as stream:
        json.dump(value, stream, default=str)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def checkpoint(stage: str) -> dict[str, Any] | None:
    if profile() != CONSTRAINED:
        return None
    path = Path(os.environ["PHASE7_MEMORY_GUARD_CONFIG"])
    config = json.loads(path.read_text())
    heartbeat = json.loads(Path(config["heartbeat"]).read_text())
    age = time.time() - heartbeat["epoch"]
    if not 0 <= age <= 5 or heartbeat["contract_sha256"] != config["contract_sha256"]:
        raise MemoryError("FRESH_MEMORY_GUARD_REQUIRED")
    os.kill(heartbeat["guard_pid"], 0)
    value = record(stage, Path(config["local_root"]))
    value["memory_status"] = severity(value)
    append(Path(config["timeline"]), value)
    if value["memory_status"].startswith("STOP"):
        raise MemoryError("48GB_HOST_INSUFFICIENT: " + value["memory_status"])
    return value


def fit_fingerprint(
    config: Any,
    threads: int,
    train_x: Any,
    train_y: Any,
    validation_x: Any,
    validation_y: Any,
    weights: Any,
) -> dict[str, Any]:
    import numpy as np

    from crypto_ai.phase7.backend import lightgbm_estimator_parameters

    def digest(a: Any) -> str | None:
        return (
            None if a is None else hashlib.sha256(memoryview(np.ascontiguousarray(a))).hexdigest()
        )

    return {
        "parameters": lightgbm_estimator_parameters(config, model_threads=threads),
        "train_shape": list(train_x.shape),
        "validation_shape": list(validation_x.shape),
        "dtype": str(train_x.dtype),
        "validation_dtype": str(validation_x.dtype),
        "train_y_sha256": digest(train_y),
        "validation_y_sha256": digest(validation_y),
        "weight_sha256": digest(weights),
    }


def admit_fit(
    config: Any,
    threads: int,
    train_x: Any,
    train_y: Any,
    validation_x: Any,
    validation_y: Any,
    weights: Any,
) -> None:
    if profile() != CONSTRAINED:
        return
    gc.collect()
    checkpoint("FIT_START_MEMORY_BASELINE")
    if _PROBE.get():
        return
    guard = json.loads(Path(os.environ["PHASE7_MEMORY_GUARD_CONFIG"]).read_text())
    proof = json.loads(Path(os.environ["PHASE7_MEMORY_QUALIFICATION_FILE"]).read_text())
    if proof.get("status") != "PASS" or proof.get("contract_sha256") != guard["contract_sha256"]:
        raise MemoryError("CONSTRAINED_MEMORY_PROBE_REQUIRED")
    fingerprint = fit_fingerprint(
        config, threads, train_x, train_y, validation_x, validation_y, weights
    )
    if proof.get("fit_fingerprint") != fingerprint:
        raise MemoryError("MEMORY_PROBE_INPUT_MISMATCH")
    manifest = Path(proof["cache_manifest"])
    if hashlib.sha256(manifest.read_bytes()).hexdigest() != proof["cache_manifest_sha256"]:
        raise MemoryError("MEMORY_PROBE_CACHE_MISMATCH")


@contextmanager
def probe_scope():
    token = _PROBE.set(True)
    try:
        yield
    finally:
        _PROBE.reset(token)


def callback(env: Any) -> None:
    if profile() == CONSTRAINED:
        value = checkpoint(f"BOOSTING_ROUND_{env.iteration + 1}")
        if env.iteration == 0 or (env.iteration + 1) % 25 == 0:
            print(json.dumps({"memory_timeline": value, "round": env.iteration + 1}), flush=True)


callback.order = 24
callback.before_iteration = False


def watch(config: dict[str, Any], target: int) -> None:
    import psutil

    os.environ[PROFILE_ENV] = CONSTRAINED
    root = Path(config["local_root"])
    log = Path(config["timeline"])
    while psutil.pid_exists(target):
        value = record(config["stage"], root)
        try:
            proc = psutil.Process(target)
            value["process_tree_rss_bytes"] = sum(
                p.memory_info().rss
                for p in [proc, *proc.children(recursive=True)]
                if p.is_running()
            )
        except psutil.Error:
            continue
        value["memory_status"] = severity(value)
        append(log, value)
        atomic(
            Path(config["heartbeat"]),
            {
                "epoch": time.time(),
                "guard_pid": os.getpid(),
                "target_pid": target,
                "contract_sha256": config["contract_sha256"],
                **value,
            },
        )
        if value["memory_status"].startswith("STOP"):
            halt(config, target, value)
            return
        time.sleep(0.25)


def halt(config: dict[str, Any], target: int, value: dict[str, Any]) -> None:
    import psutil

    root = Path(config["local_root"])
    # Local control receipt first; outside-Pod controller reads it independently.
    with suppress(OSError):
        atomic(root / "control/STOP_REQUEST.json", {"reason": "RESOURCE_FAILURE", **value})
    with suppress(psutil.NoSuchProcess):
        proc = psutil.Process(target)
        victims = [*proc.children(recursive=True), proc]
        for p in victims:
            with suppress(psutil.Error):
                p.send_signal(signal.SIGTERM)
        _, alive = psutil.wait_procs(victims, timeout=3)
        for p in alive:
            with suppress(psutil.Error):
                p.kill()
    # Bounded compute stop is independent of this best-effort persistent receipt.
    with suppress(OSError):
        atomic(Path(config["emergency_evidence"]), value)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--pid", type=int, required=True)
    a = p.parse_args()
    config = json.loads(a.config.read_text())
    try:
        watch(config, a.pid)
    except Exception as exc:
        halt(
            config,
            a.pid,
            {
                "stage": config["stage"],
                "memory_status": "STOP_GUARD_FAILURE",
                "error_type": type(exc).__name__,
            },
        )
        raise


if __name__ == "__main__":
    main()
