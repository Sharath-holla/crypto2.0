"""Trusted broker only. Generated code never imports or runs in this process."""

import asyncio
import io
import json
import os
import secrets
import shlex
import shutil
import tarfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError

from .runner_checkout import CheckoutExecution, CheckoutInput, CheckoutScope
from .runner_protocol import SUITES, RunInput, request_digest

ROOT = Path(os.environ.get("RUNNER_STAGING_ROOT", "/jobs"))
DAEMON = os.environ.get("RUNNER_DAEMON_URL", "http://runner-daemon:2375")
TOKEN = os.environ.get("RUNNER_TOKEN", "")
LIMIT = 500000
gate = asyncio.Semaphore(2)
active: dict[str, dict] = {}


def authenticate(request: Request):
    supplied = request.headers.get("authorization", "")
    if len(TOKEN) < 32 or not secrets.compare_digest(supplied, "Bearer " + TOKEN):
        raise HTTPException(401, "Runner authentication required")


def record(job_id: str, value: dict):
    path = ROOT / "results" / (job_id + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


async def remove(client: httpx.AsyncClient, container: str):
    response = await client.delete(f"/containers/{container}", params={"force": "true", "v": "true"})
    if response.status_code != 404:
        response.raise_for_status()


def prune():
    results = sorted((ROOT / "results").glob("*.json"), key=lambda path: path.stat().st_mtime)
    for index, path in enumerate(results):
        if path.stem in active:
            continue
        if index < len(results) - 199 or time.time() - path.stat().st_mtime > 604800:
            discard_input(path.stem)
            path.unlink()


def discard_input(job_id):
    """Remove only this broker's private UUID staging child, never an arbitrary path."""
    identity = str(UUID(job_id))
    source = ROOT / identity
    if source.is_symlink() or (source.exists() and source.resolve().parent != ROOT.resolve()):
        raise RuntimeError("Runner staging integrity failed")
    if source.exists():
        for path in [source, *[p for p in source.rglob("*") if p.is_dir()]]:
            path.chmod(0o755)
        shutil.rmtree(source)


@asynccontextmanager
async def lifespan(_app):
    if len(TOKEN) < 32:
        raise RuntimeError("Generate a private RUNNER_TOKEN before starting the broker")
    ROOT.mkdir(parents=True, exist_ok=True)
    prune()
    from .runner_checkout import recover

    recover(ROOT)
    async with httpx.AsyncClient(base_url=DAEMON, trust_env=False, timeout=180) as client:
        # Dedicated daemon only: cleanup this broker's interrupted executions on restart.
        response = await client.get(
            "/containers/json",
            params={"all": "true", "filters": json.dumps({"label": ["aiventra.runner=restricted-v1"]})},
        )
        response.raise_for_status()
        for container in response.json():
            await remove(client, container["Id"])
        for path in (ROOT / "results").glob("*.json"):
            value = json.loads(path.read_text())
            if value.get("status") == "running":
                discard_input(path.stem)
                record(
                    path.stem,
                    {
                        **value,
                        "status": "interrupted",
                        "exit_code": 125,
                        "logs": "Broker restarted; execution was stopped. Owner reconciliation required.",
                        "command": [],
                        "environment": "dedicated Docker broker",
                        "job_id": path.stem,
                    },
                )
        # Only trusted startup can pull these fixed public runtime images.
        for image in sorted({row[0] for row in SUITES.values()} - {"aiventra-quality-python:1"}):
            result = await client.post("/images/create", params={"fromImage": image})
            result.raise_for_status()
            inspect = await client.get(f"/images/{image}/json")
            inspect.raise_for_status()
        # Fixed, trusted runtime template. Agents cannot supply Dockerfiles, images or packages.
        context = io.BytesIO()
        dockerfile = (
            b"FROM python:3.12-slim\nRUN pip install --no-cache-dir ruff==0.16.10\n"
            b"COPY quality_runner.py /opt/aiventra/quality_runner.py\n"
        )
        with tarfile.open(fileobj=context, mode="w") as archive:
            for name, body in (
                ("Dockerfile", dockerfile),
                ("quality_runner.py", Path(__file__).with_name("quality_runner.py").read_bytes()),
            ):
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(body), 0o444
                archive.addfile(info, io.BytesIO(body))
        built = await client.post(
            "/build",
            params={"t": "aiventra-quality-python:1", "rm": "true"},
            content=context.getvalue(),
            headers={"Content-Type": "application/x-tar"},
        )
        built.raise_for_status()
        if any(json.loads(line).get("error") for line in built.text.splitlines() if line.strip()):
            raise RuntimeError("Trusted QA runtime image build failed")
        (await client.get("/images/aiventra-quality-python:1/json")).raise_for_status()

    async def expire_checkouts():
        from .runner_checkout import expire_sources

        while True:
            await asyncio.sleep(30)
            expire_sources(ROOT)

    maintenance = asyncio.create_task(expire_checkouts())
    try:
        yield
    finally:
        maintenance.cancel()
        try:
            await maintenance
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Restricted Aiventra coding broker",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.get("/health")
async def health():
    async with httpx.AsyncClient(base_url=DAEMON, trust_env=False, timeout=5) as client:
        response = await client.get("/_ping")
        response.raise_for_status()
    return {"status": "ready", "capacity": 2, "active": len(active)}


async def stage(
    client: httpx.AsyncClient, job_id: str, source: Path, suite: str, build: bool, timeout: int
) -> dict:
    image, tests, build_command = SUITES[suite]
    command = build_command if build else tests
    name = "aiventra-" + job_id + ("-build" if build else "-test")
    # No command, image, environment or mount path comes from generated code.
    bootstrap = "cp -R /input/. /workspace/ && chmod -R u+rwX /workspace && exec " + shlex.join(command)
    config = {
        "Image": image,
        "Cmd": ["/bin/sh", "-c", bootstrap],
        "User": "10001:10001",
        "WorkingDir": "/workspace",
        "Env": ["PYTHONDONTWRITEBYTECODE=1", "LANG=C.UTF-8"],
        "Labels": {"aiventra.runner": "restricted-v1", "aiventra.job": job_id},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "SecurityOpt": ["no-new-privileges"],
            "Memory": 536870912,
            "MemorySwap": 536870912,
            "NanoCpus": 1000000000,
            "PidsLimit": 128,
            "Init": True,
            "Tmpfs": {
                "/tmp": "rw,noexec,nosuid,nodev,size=64m,uid=10001,gid=10001",
                "/workspace": "rw,nosuid,nodev,size=128m,uid=10001,gid=10001",
            },
            "Binds": [f"{source}:/input:ro"],
            "LogConfig": {"Type": "json-file", "Config": {"max-size": "512k", "max-file": "1"}},
        },
    }
    created = await client.post("/containers/create", params={"name": name}, json=config)
    created.raise_for_status()
    container = created.json()["Id"]
    state = active[job_id]
    state["container"] = container
    logs = bytearray()
    policy = {}
    code = 125
    limited = ""
    try:
        inspected = await client.get(f"/containers/{container}/json")
        inspected.raise_for_status()
        actual = inspected.json()
        host = actual["HostConfig"]
        policy = {
            "image_id": actual["Image"],
            "user": actual["Config"]["User"],
            "network": host["NetworkMode"],
            "read_only_root": host["ReadonlyRootfs"],
            "memory": host["Memory"],
            "pids": host["PidsLimit"],
            "cap_drop": host["CapDrop"],
            "security": host["SecurityOpt"],
            "cpu_nano": host["NanoCpus"],
            "tmpfs": host["Tmpfs"],
            "mount_destinations": [mount["Destination"] for mount in actual["Mounts"]],
        }
        if state["cancelled"]:
            raise asyncio.CancelledError()
        started = await client.post(f"/containers/{container}/start")
        started.raise_for_status()

        async def collect():
            pending = bytearray()
            async with client.stream(
                "GET",
                f"/containers/{container}/logs",
                params={"stdout": "true", "stderr": "true", "follow": "true"},
                timeout=timeout + 10,
            ) as stream:
                stream.raise_for_status()
                async for chunk in stream.aiter_bytes():
                    pending.extend(chunk)
                    while len(pending) >= 8:
                        length = int.from_bytes(pending[4:8], "big")
                        if length > 1_000_000:
                            raise TimeoutError("Invalid Docker log frame")
                        if len(pending) < length + 8:
                            break
                        remaining = LIMIT - len(logs)
                        logs.extend(pending[8 : 8 + min(length, remaining)])
                        del pending[: 8 + length]
                        if len(logs) >= LIMIT:
                            raise TimeoutError("Output limit reached")
            result = await client.post(f"/containers/{container}/wait")
            result.raise_for_status()
            return result.json()["StatusCode"]

        code = await asyncio.wait_for(collect(), timeout=timeout)
        if state["cancelled"]:
            code, limited = 125, "Cancelled by owner"
    except TimeoutError:
        code, limited = 124, "Execution time or output limit reached"
    finally:
        await asyncio.shield(remove(client, container))
        state["container"] = None
    return {
        "command": command,
        "exit_code": code,
        "logs": logs.decode(errors="replace") + ("\n" + limited if limited else ""),
        "policy": policy,
    }


@app.post("/run")
async def run(request: Request):
    authenticate(request)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 6_000_000:
            raise HTTPException(413, "Snapshot request too large")
    try:
        data = RunInput.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "Invalid restricted runner request") from None
    return await run_input(data)


async def run_input(data: RunInput):
    job_id = str(data.job_id)
    request_hash, started_at = request_digest(data), int(time.time())
    try:
        await asyncio.wait_for(gate.acquire(), timeout=1)
    except TimeoutError:
        raise HTTPException(429, "Runner capacity reached") from None
    source = ROOT / "sources" / job_id
    owned = False
    try:
        prune()
        if (ROOT / "results" / (job_id + ".json")).exists():
            raise HTTPException(409, "Job ID already used; reconcile its stored result")
        active[job_id] = {"container": None, "cancelled": False}
        owned = True
        record(job_id, {"status": "running", "job_id": job_id, "request_hash": request_hash})
        source.mkdir(parents=True, exist_ok=False)
        for name, content in data.files.items():
            path = source.joinpath(*name.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            path.chmod(0o444)
        for folder in [source, *[p for p in source.rglob("*") if p.is_dir()]]:
            folder.chmod(0o555)
        async with httpx.AsyncClient(base_url=DAEMON, trust_env=False, timeout=15) as client:
            begin = time.monotonic()
            build = await stage(client, job_id, source, data.suite, True, data.timeout)
            result = (
                build
                if build["exit_code"]
                else await stage(
                    client,
                    job_id,
                    source,
                    data.suite,
                    False,
                    max(1, data.timeout - int(time.monotonic() - begin)),
                )
            )
        value = {
            **result,
            "build": build,
            "status": "completed",
            "job_id": job_id,
            "request_hash": request_hash,
            "started_at": started_at,
            "ended_at": int(time.time()),
            "environment": SUITES[data.suite][0]
            + "; dedicated Docker; no network; nonroot; read-only root; capped tmpfs/CPU/memory/PIDs",
        }
        record(job_id, value)
        return value
    except HTTPException:
        raise
    except (Exception, asyncio.CancelledError):
        value = {
            "status": "interrupted",
            "job_id": job_id,
            "request_hash": request_hash,
            "started_at": started_at,
            "ended_at": int(time.time()),
            "exit_code": 125,
            "logs": "Runner interrupted; inspect stored execution before retry",
            "command": [],
            "environment": "dedicated Docker broker",
        }
        record(job_id, value)
        return value
    finally:
        # Only this fixed UUID child of the private staging root is ever removed.
        if owned and source.exists():
            discard_input(job_id)
        if owned:
            active.pop(job_id, None)
        gate.release()


@app.get("/jobs/{job_id}")
async def job(job_id: UUID, request: Request):
    authenticate(request)
    path = ROOT / "results" / (str(job_id) + ".json")
    if not path.exists():
        raise HTTPException(404, "Unknown runner job")
    return json.loads(path.read_text())


@app.post("/jobs/{job_id}/cancel")
async def cancel(job_id: UUID, request: Request):
    authenticate(request)
    state = active.get(str(job_id))
    if not state:
        raise HTTPException(409, "Job is not active")
    state["cancelled"] = True
    if state["container"]:
        async with httpx.AsyncClient(base_url=DAEMON, trust_env=False, timeout=10) as client:
            await remove(client, state["container"])
    return {"status": "cancellation_requested"}


@app.post("/checkouts")
async def create_checkout(data: "CheckoutInput", request: Request):
    from .runner_checkout import checkout

    authenticate(request)
    try:
        await asyncio.wait_for(gate.acquire(), timeout=1)
    except TimeoutError:
        raise HTTPException(429, "Runner capacity reached") from None
    try:
        return await checkout(ROOT, data)
    finally:
        gate.release()


@app.get("/checkouts/{identity}")
async def read_checkout(identity: UUID, org_id: UUID, project_id: UUID, request: Request):
    from .runner_checkout import get

    authenticate(request)
    return get(ROOT, identity, org_id, project_id)


@app.post("/checkouts/{identity}/cleanup")
async def cleanup_checkout(identity: UUID, data: "CheckoutScope", request: Request):
    from .runner_checkout import cleanup, get, store

    authenticate(request)
    value = get(ROOT, identity, data.org_id, data.project_id)
    if value["status"] == "fetching":
        raise HTTPException(409, "Checkout acquisition still running")
    cleanup(ROOT, identity)
    value["status"] = "cleaned"
    store(ROOT, identity, value)
    return value


@app.post("/checkouts/{identity}/execute")
async def execute_checkout(identity: UUID, data: "CheckoutExecution", request: Request):
    from .runner_checkout import files, get

    authenticate(request)
    value = get(ROOT, identity, data.org_id, data.project_id)
    try:
        snapshot = files(ROOT, value)
        run = RunInput(job_id=data.job_id, suite=data.suite, files=snapshot, timeout=data.timeout)
    except ValueError:
        raise HTTPException(409, "Checkout unavailable or integrity changed") from None
    return await run_input(run)
