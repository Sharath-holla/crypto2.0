"""Independent, source-bound workers; runtime journals are not a second database."""

from __future__ import annotations

import hmac
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import psutil

from crypto_ai.phase7.artifacts import atomic_json

from .adapter import Crypto2Adapter, read_json
from .jobs import digest, validate_scope

TERMINAL = {"COMPLETED", "PREPARATION_COMPLETE", "FAILED", "STOPPED", "BLOCKED", "INTERRUPTED"}


def job_directory(adapter: Crypto2Adapter, job_id: str) -> Path:
    if str(UUID(job_id)) != job_id:
        raise ValueError("Canonical job UUID required")
    root = adapter.paths.runtime / "jobs"
    result = root / job_id
    if result.is_symlink() or not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("Aliased job directory refused")
    return result


def signing_key() -> bytes:
    key = os.environ.get("CRYPTO_ADAPTER_TOKEN", "")
    if len(key) < 32:
        raise ValueError("Private adapter authentication is not configured")
    return key.encode()


def signature(value) -> str:
    return hmac.new(signing_key(), digest(value).encode(), "sha256").hexdigest()


def status(adapter: Crypto2Adapter, job_id: str):
    root = job_directory(adapter, job_id)
    envelope = read_json(root / "request.json")
    state = read_json(root / "state.json")
    if envelope is None:
        raise FileNotFoundError("Job not found")
    if not hmac.compare_digest(envelope.pop("signature", ""), signature(envelope)):
        raise ValueError("Job request integrity failure")
    if state is None:
        return {
            "job_id": job_id,
            "scope_hash": envelope["scope"]["scope_hash"],
            "state": "INTERRUPTED",
            "reason": "Worker state is absent",
            "completion_verified": False,
        }
    if state["state"] in {"COMPLETED", "PREPARATION_COMPLETE"}:
        completion = read_json(root / "completion.json")
        if (
            completion is None
            or not hmac.compare_digest(completion.pop("signature", ""), signature(completion))
            or completion.get("job_id") != job_id
            or completion.get("scope_hash") != envelope["scope"]["scope_hash"]
        ):
            state = {
                **state,
                "state": "BLOCKED",
                "reason": "Completion receipt absent or corrupt",
                "completion_verified": False,
            }
    owner = state.get("worker", {})
    active = False
    try:
        process = psutil.Process(owner["pid"])
        active = (
            process.is_running()
            and process.create_time() == owner["process_start_time"]
            and process.status() not in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD}
        )
    except (psutil.Error, KeyError):
        pass
    if state["state"] == "QUEUED" and not owner and time.time() - state.get("heartbeat", 0) <= 30:
        return {**state, "scope_hash": envelope["scope"]["scope_hash"]}
    if state["state"] not in TERMINAL and (
        not active or time.time() - state.get("heartbeat", 0) > 30
    ):
        state = {
            **state,
            "state": "INTERRUPTED",
            "reason": "Worker vanished or heartbeat is stale",
            "completion_verified": False,
            "automatic_replay": False,
        }
    return {
        **state,
        "request": envelope["scope"]["request"],
        "scope_hash": envelope["scope"]["scope_hash"],
    }


def job_log(adapter, job_id):
    state = status(adapter, job_id)
    path = job_directory(adapter, job_id) / "job.log"
    if path.is_symlink():
        raise ValueError("Aliased log refused")
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - 65536))
        content = stream.read(65536).decode("utf-8", errors="replace")
    from .adapter import redact

    return {
        "job_id": job_id,
        "scope_hash": state["scope_hash"],
        "content": redact(content),
        "read_only": True,
        "truncated": path.stat().st_size > 65536,
    }


def launch_worker(command, *, root: Path, cwd: Path):
    options = (
        {"start_new_session": True}
        if os.name != "nt"
        else {
            "creationflags": subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        }
    )
    with (root / "worker.log").open("ab") as output:
        return subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            **options,
        )


def submit(adapter: Crypto2Adapter, job_id: str, scope, approval):
    validate_scope(scope, adapter)
    if (
        approval.get("scope_hash") != scope["scope_hash"]
        or approval.get("expires_at", 0) <= time.time()
        or not all(approval.get(key) for key in ("owner_id", "org_id", "approval_id"))
    ):
        raise PermissionError("Exact unexpired owner approval required")
    root = job_directory(adapter, job_id)
    envelope = {"job_id": job_id, "scope": scope, "approval": approval}
    signed = {**envelope, "signature": signature(envelope)}
    if root.exists():
        if read_json(root / "request.json") != signed:
            raise ValueError("Job idempotency conflict")
        return status(adapter, job_id)
    root.mkdir(parents=True, mode=0o700)
    atomic_json(root / "request.json", signed)
    atomic_json(
        root / "state.json",
        {
            "job_id": job_id,
            "state": "QUEUED",
            "heartbeat": time.time(),
            "completion_verified": False,
        },
    )
    command = [sys.executable, "-m", "integration.crypto_aiventra.worker", "--job-id", job_id]
    launch_worker(command, root=root, cwd=adapter.paths.repo)
    return {"job_id": job_id, "state": "QUEUED", "completion_verified": False}


def stop(adapter: Crypto2Adapter, job_id: str, approval):
    root = job_directory(adapter, job_id)
    state = status(adapter, job_id)
    if state["state"] in TERMINAL:
        return state
    if (
        approval.get("job_id") != job_id
        or approval.get("scope_hash") != state["scope_hash"]
        or approval.get("expires_at", 0) <= time.time()
    ):
        raise PermissionError("Exact stop approval required")
    command = {"action": "STOP", "approval": approval}
    atomic_json(root / "control.json", {**command, "signature": signature(command)})
    return {"job_id": job_id, "state": "STOP_REQUESTED", "completion_verified": False}
