"""Detached trusted-command supervisor with deadlines and approval revocation fences."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import signal
import subprocess
import time

import httpx
import psutil

from crypto_ai.phase7.artifacts import atomic_json

from .adapter import Crypto2Adapter, read_json
from .jobs import HEAVY, validate_scope
from .runtime import job_directory, signature


class ResourceFloorError(PermissionError):
    """Declared minimum free resources are unavailable; no automatic retry."""


def authority(job_id: str, scope_hash: str) -> bool:
    # Fixed loopback transport, no proxy/redirect or browser credentials.
    from urllib.parse import urlsplit

    url = os.environ.get("AIVENTRA_API_URL", "http://127.0.0.1:8010")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "::1"}
        or parsed.username
        or parsed.path
    ):
        raise ValueError("Private authority endpoint must be a loopback HTTP origin")
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=3) as client:
        response = client.get(
            url + f"/crypto/internal/jobs/{job_id}/authority",
            headers={"Authorization": "Bearer " + os.environ["CRYPTO_ADAPTER_TOKEN"]},
        )
        response.raise_for_status()
        evidence = response.json()
        return evidence.get("authorized") is True and evidence.get("scope_hash") == scope_hash


def terminate_owned(process: subprocess.Popen, started: float):
    try:
        observed = psutil.Process(process.pid)
        if observed.create_time() != started or observed.ppid() != os.getpid():
            raise PermissionError("PID identity changed; refusing to signal unrelated process")
        if os.name == "nt":
            for child in observed.children(recursive=True):
                child.terminate()
            observed.terminate()
        else:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            if observed.create_time() != started:
                raise PermissionError("PID changed during stop") from None
            if os.name == "nt":
                for child in observed.children(recursive=True):
                    child.kill()
                observed.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass


def supervise(job_id: str):
    adapter = Crypto2Adapter()
    root = job_directory(adapter, job_id)
    envelope = read_json(root / "request.json")
    if envelope is None or not hmac.compare_digest(
        envelope.pop("signature", ""), signature(envelope)
    ):
        raise PermissionError("Worker request integrity failure")
    scope, approval = envelope["scope"], envelope["approval"]
    request = validate_scope(scope, adapter)
    # This detached process must resolve completion artifacts exactly as its child does.
    # Never mutate the API/adapter parent's environment or scientific configuration.
    os.environ.update(adapter.paths.engine_environment())
    worker = {"pid": os.getpid(), "process_start_time": psutil.Process().create_time()}
    state = {
        "job_id": job_id,
        "state": "QUEUED",
        "worker": worker,
        "started_at": time.time(),
        "completion_verified": False,
        "command": scope["command"],
        "run_identity": scope["run_identity"],
        "configuration_hash": scope["configuration_hash"],
        "fold_id": scope["fold_id"],
        "spec_id": request.spec_id,
        "exit_code": None,
        "cost_observed": None,
        "log_path": str(root / "job.log"),
        "artifact_path": str(root),
    }

    def publish():
        state.update(heartbeat=time.time(), resources=adapter.get_resource_usage())
        atomic_json(root / "state.json", state, immutable=False)

    publish()
    child = None

    def resource_floor():
        resources = adapter.get_resource_usage()
        if (
            resources["ram_available_bytes"] < request.minimum_free_ram_gib * 1024**3
            or resources["disk_free_bytes"] < request.minimum_free_disk_gib * 1024**3
        ):
            raise ResourceFloorError("Approved free RAM/disk floor is not available")

    try:
        if approval["expires_at"] <= time.time() or not authority(job_id, scope["scope_hash"]):
            raise PermissionError("Owner/job authorization is not current")
        resource_floor()
        environment = dict(os.environ)
        environment.update(adapter.paths.engine_environment())
        environment.update(
            PHASE7_MIN_FREE_RAM_GIB=str(request.minimum_free_ram_gib),
            PHASE7_MIN_FREE_DISK_GIB=str(request.minimum_free_disk_gib),
            PHASE7_TOTAL_CPU_THREADS=str(request.cpu_threads),
            PHASE7_MODEL_PARALLELISM="1",
            PHASE7_LIGHTGBM_THREADS_PER_MODEL=str(request.cpu_threads),
            PHASE7_LGBM_DEVICE="cpu",
            PHASE7_CACHE_MODE="auto",
        )
        if request.job_type in HEAVY:
            environment["PHASE7_ALLOW_CLOUD_RESEARCH"] = "1"
        else:
            environment.pop("PHASE7_ALLOW_CLOUD_RESEARCH", None)
        state["state"] = (
            "PREPARING"
            if "CACHE" in request.job_type
            else "TRAINING"
            if "TRAIN" in request.job_type
            else "EVALUATING"
        )
        with (root / "job.log").open("ab") as output:
            child = subprocess.Popen(
                scope["command"],
                cwd=adapter.paths.repo,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            child_start = psutil.Process(child.pid).create_time()
            state["child"] = {"pid": child.pid, "process_start_time": child_start}
            publish()
            deadline = min(
                request.deadline_utc,
                time.time() + request.maximum_runtime_seconds,
                approval["expires_at"],
            )
            while child.poll() is None:
                validate_scope(scope, adapter)
                resource_floor()
                control = read_json(root / "control.json")
                if control:
                    claimed = control.pop("signature", "")
                    if (
                        not hmac.compare_digest(claimed, signature(control))
                        or control["approval"]["scope_hash"] != scope["scope_hash"]
                    ):
                        raise PermissionError("Stop control integrity mismatch")
                    terminate_owned(child, child_start)
                    state.update(
                        state="STOPPED", reason="Explicit owner stop", exit_code=child.returncode
                    )
                    publish()
                    return
                if time.time() >= deadline:
                    raise TimeoutError("Approved job deadline/runtime elapsed")
                if not authority(job_id, scope["scope_hash"]):
                    raise PermissionError("Owner approval revoked or source/scope changed")
                publish()
                time.sleep(1)
        state["exit_code"] = child.returncode
        if child.returncode != 0:
            raise RuntimeError("Canonical command failed; inspect retained redacted log")
        # A command's exit alone does not establish missing scientific completion.
        from .verification import completion_receipt

        validate_scope(scope, adapter)
        if not authority(job_id, scope["scope_hash"]):
            raise PermissionError("Authority changed before completion publication")
        receipt = completion_receipt(adapter, scope, root / "job.log")
        completion = {
            "job_id": job_id,
            "scope_hash": scope["scope_hash"],
            "receipt": receipt,
            "receipt_hash": __import__("hashlib")
            .sha256(json.dumps(receipt, sort_keys=True, default=str).encode())
            .hexdigest(),
        }
        atomic_json(root / "completion.json", {**completion, "signature": signature(completion)})
        state.update(
            state="PREPARATION_COMPLETE" if "CACHE" in request.job_type else "COMPLETED",
            completion_verified=True,
            ended_at=time.time(),
            receipt=receipt,
        )
    except Exception as exc:
        if child is not None and child.poll() is None:
            terminate_owned(child, child_start)
        state.update(
            state="BLOCKED" if isinstance(exc, PermissionError) else "FAILED",
            reason=type(exc).__name__,
            ended_at=time.time(),
            completion_verified=False,
            exit_code=None if child is None else child.returncode,
        )
    publish()
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=3) as client:
            client.post(
                os.environ.get("AIVENTRA_API_URL", "http://127.0.0.1:8010")
                + f"/crypto/internal/jobs/{job_id}/receipt",
                headers={"Authorization": "Bearer " + os.environ["CRYPTO_ADAPTER_TOKEN"]},
            )
    except httpx.HTTPError:
        pass  # The signed durable receipt can be reconciled after API recovery.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    supervise(parser.parse_args().job_id)


if __name__ == "__main__":
    main()
