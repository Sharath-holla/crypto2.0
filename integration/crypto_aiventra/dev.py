"""One-command local development; no science, inference, models or cloud startup."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import time
from pathlib import Path

import httpx
import psutil

from crypto_ai.phase7.artifacts import atomic_json

from .adapter import read_json
from .config import CryptoPaths, require_branch


def python_at(root: Path) -> Path:
    return root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")


def private_environment(paths: CryptoPaths):
    aiventra = paths.repo / "aiventra"
    python = python_at(aiventra)
    if not python.is_file():
        raise ValueError("Install the separate locked Aiventra environment first")
    subprocess.run([str(python), "scripts/configure.py"], cwd=aiventra, check=True)
    # Values remain in memory/private ignored configuration; never display them.
    script = (
        "import json; from dotenv import dotenv_values; "
        "print(json.dumps(dict(dotenv_values('.env'))))"
    )
    result = subprocess.run(
        [str(python), "-c", script], cwd=aiventra, check=True, capture_output=True, text=True
    )
    configured = {
        key: value for key, value in json.loads(result.stdout).items() if value is not None
    }
    profile = aiventra / ".env.crypto-integration"
    if profile.is_symlink():
        raise ValueError("Private integration profile must not be aliased")
    if profile.exists():
        token = profile.read_text(encoding="utf-8").strip()
    else:
        token = secrets.token_urlsafe(48)
        descriptor = os.open(profile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(token + "\n")
    if len(token) < 32:
        raise ValueError("Private integration profile is invalid")
    environment = {
        **os.environ,
        **configured,
        **{
            name: str(value)
            for name, value in {
                "CRYPTO_REPO_ROOT": paths.repo,
                "CRYPTO_PERSISTENT_ROOT": paths.persistent,
                "CRYPTO_GOLD_ROOT": paths.gold,
                "CRYPTO_PHASE7_DATA_ROOT": paths.data,
                "CRYPTO_HISTORICAL_ROOT": paths.historical,
                "CRYPTO_CHECKPOINT_ROOT": paths.checkpoints,
                "CRYPTO_CACHE_ROOT": paths.cache,
                "CRYPTO_MODEL_ROOT": paths.models,
                "CRYPTO_REPORT_ROOT": paths.reports,
                "CRYPTO_LOG_ROOT": paths.logs,
                "CRYPTO_VERIFICATION_ROOT": paths.verification,
                "CRYPTO_CONTROL_ROOT": paths.runtime,
            }.items()
        },
        "CRYPTO_ADAPTER_TOKEN": token,
        "AI_SPENDING_MODE": "ZERO_COST_ONLY",
        "MOCK_ENABLED": "false",
        "EXECUTION_ENABLED": "false",
        "EMBEDDING_PROVIDER": "disabled",
        "REQUIRED_DATABASE_BACKEND": "sqlite",
        "NEXT_TELEMETRY_DISABLED": "1",
        "DATABASE_URL": "sqlite:///./data/company.db",
    }
    environment.pop("PHASE7_ALLOW_CLOUD_RESEARCH", None)
    environment.pop("CRYPTO_ENABLE_SCIENTIFIC_JOBS", None)
    environment.pop("CRYPTO_DEMO_FIXTURE_STATE", None)
    return environment


def initialize(paths, environment):
    root, python = paths.repo / "aiventra", python_at(paths.repo / "aiventra")
    database = root / "data/company.db"
    if not database.exists():
        subprocess.run(
            [str(python), "-m", "alembic", "upgrade", "head"], cwd=root, env=environment, check=True
        )
    script = (
        "from company_os.db import SessionLocal; from company_os.organization import seed; "
        "s=SessionLocal(); org=seed(s); print(org.id); s.close()"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )
    environment["CRYPTO_PROJECT_ORG_ID"] = result.stdout.strip()


def start(paths, api_port, web_port, adapter_port):
    require_branch(paths.repo)
    state_path = paths.runtime / "development-services.json"
    if state_path.exists():
        old = read_json(state_path)
        if old and any(psutil.pid_exists(item["pid"]) for item in old.get("services", [])):
            raise ValueError(
                "Managed services already exist; inspect status, do not start duplicate servers"
            )
    for port in (api_port, web_port, adapter_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))  # Never kill an unrelated port owner.
    environment = private_environment(paths)
    environment.update(
        WEB_ORIGIN=f"http://127.0.0.1:{web_port}",
        API_INTERNAL_URL=f"http://127.0.0.1:{api_port}",
        AIVENTRA_API_URL=f"http://127.0.0.1:{api_port}",
        CRYPTO_ADAPTER_URL=f"http://127.0.0.1:{adapter_port}",
    )
    initialize(paths, environment)
    web, aiventra = paths.repo / "aiventra/apps/web", paths.repo / "aiventra"
    node = shutil.which("node")
    if not node or not (web / "node_modules/next/dist/bin/next").is_file():
        raise ValueError("Install the separate locked frontend dependencies first")
    services = [
        (
            "adapter",
            paths.repo,
            [
                str(python_at(paths.repo)),
                "-m",
                "integration.crypto_aiventra.service",
                "--port",
                str(adapter_port),
            ],
        ),
        (
            "api",
            aiventra,
            [
                str(python_at(aiventra)),
                "-m",
                "uvicorn",
                "company_os.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
        ),
        ("workflow", aiventra, [str(python_at(aiventra)), "-m", "company_os.workflows"]),
        (
            "web",
            web,
            [
                node,
                str(web / "node_modules/next/dist/bin/next"),
                "dev",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(web_port),
            ],
        ),
    ]
    paths.runtime.mkdir(parents=True, exist_ok=True)
    records = []
    options = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    )
    for name, cwd, command in services:
        with (paths.runtime / f"development-{name}.log").open("ab") as output:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                **options,
            )
        records.append(
            {
                "name": name,
                "pid": process.pid,
                "process_start_time": psutil.Process(process.pid).create_time(),
                "command": command,
            }
        )
    result = {
        "services": records,
        "frontend": environment["WEB_ORIGIN"],
        "backend": environment["AIVENTRA_API_URL"],
        "adapter": environment["CRYPTO_ADAPTER_URL"],
        "scientific_jobs_started": 0,
        "inference_started": False,
    }
    atomic_json(state_path, result, immutable=False)
    deadline = time.monotonic() + 120
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=3) as client:
        while time.monotonic() < deadline:
            try:
                api = client.get(result["backend"] + "/health/ready")
                frontend = client.get(result["frontend"])
                adapter = client.get(
                    result["adapter"] + "/health",
                    headers={"Authorization": "Bearer " + environment["CRYPTO_ADAPTER_TOKEN"]},
                )
                if api.status_code == frontend.status_code == adapter.status_code == 200:
                    return {**result, "status": "RUNNING", "adapter_health": "PASS"}
            except httpx.HTTPError:
                pass
            time.sleep(1)
    return {**result, "status": "NOT_READY", "inspect_logs": str(paths.runtime)}


def stop(paths):
    state = read_json(paths.runtime / "development-services.json") or {}
    stopped = []
    for record in reversed(state.get("services", [])):
        try:
            process = psutil.Process(record["pid"])
            if process.create_time() != record["process_start_time"]:
                raise PermissionError("Managed service PID was reused; refusing unrelated process")
            marker = {
                "adapter": "integration.crypto_aiventra.service",
                "api": "company_os.api:app",
                "workflow": "company_os.workflows",
                "web": "next/dist/bin/next",
            }[record["name"]]
            if marker not in " ".join(process.cmdline()).replace("\\", "/"):
                raise PermissionError("Managed service command changed")
            candidates = process.children(recursive=True) + [process]
            for candidate in reversed(candidates):
                command = " ".join(candidate.cmdline()).replace("\\", "/")
                if marker in command or record["name"] == "web":
                    candidate.terminate()  # Never terminate detached scientific job workers.
            stopped.append(record["name"])
        except psutil.NoSuchProcess:
            pass
    return {
        "stopped_services": stopped,
        "data_deleted": False,
        "scientific_workers_signaled": False,
    }


def status(paths):
    state = read_json(paths.runtime / "development-services.json")
    if not state:
        return {"status": "NOT_RUNNING"}
    services = []
    for record in state["services"]:
        try:
            process = psutil.Process(record["pid"])
            active = process.is_running() and process.create_time() == record["process_start_time"]
        except psutil.Error:
            active = False
        services.append({**record, "process_active": active})
    return {
        **state,
        "services": services,
        "status": "PROCESSES_ACTIVE"
        if all(item["process_active"] for item in services)
        else "NOT_RUNNING",
        "readiness": "NOT_PROBED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status"), nargs="?", default="start")
    parser.add_argument("--api-port", type=int, default=8010)
    parser.add_argument("--web-port", type=int, default=3010)
    parser.add_argument("--adapter-port", type=int, default=8011)
    args = parser.parse_args()
    paths = CryptoPaths.from_environment()
    require_branch(paths.repo)
    if args.action == "start":
        result = start(paths, args.api_port, args.web_port, args.adapter_port)
    elif args.action == "stop":
        result = stop(paths)
    else:
        result = status(paths)
    print(json.dumps(result, indent=2))
    return 0 if result.get("status") != "NOT_READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
