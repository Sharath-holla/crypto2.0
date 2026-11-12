"""Worker client for the dedicated runner; no local generated-code execution path."""

from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import settings
from .db import uid
from .repositories import tracked_files
from .runner_protocol import RunInput
from .security import redact


def connection():
    config = settings()
    url = urlparse(config.runner_url)
    if (
        url.scheme not in {"http", "https"}
        or url.username
        or url.password
        or url.hostname not in {"runner", "localhost", "127.0.0.1"}
        or len(config.runner_token) < 32
    ):
        raise PermissionError("Configure the dedicated runner URL and independent authentication token")
    return config.runner_url, {"Authorization": "Bearer " + config.runner_token}


def snapshot(workspace: Path) -> dict[str, str]:
    files = {}
    for path in tracked_files(workspace, maximum=501):
        if len(files) >= 500 or path.stat().st_size > 1_000_000:
            raise PermissionError("Repository exceeds the restricted snapshot limits")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeError:
            raise PermissionError("Binary assets require a separately approved runner template") from None
        if redact(content) != content:
            raise PermissionError("Potential secret in execution snapshot; sanitize the repository first")
        files[path.relative_to(workspace).as_posix()] = content
    return files


async def stored_result(job_id: str) -> dict:
    url, headers = connection()
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=15, trust_env=False, follow_redirects=False
    ) as client:
        response = await client.get(f"/jobs/{job_id}")
        response.raise_for_status()
        return response.json()


async def cancel_job(job_id: str) -> None:
    url, headers = connection()
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=15, trust_env=False, follow_redirects=False
    ) as client:
        response = await client.post(f"/jobs/{job_id}/cancel")
        if response.status_code not in {200, 404, 409}:
            response.raise_for_status()


async def run_tests(workspace: Path, suite: str, timeout=120, job_id: str | None = None) -> dict:
    if not settings().execution_enabled:
        raise PermissionError("Dedicated Docker execution is disabled")
    data = RunInput(job_id=job_id or uid(), suite=suite, files=snapshot(workspace), timeout=timeout)
    return await run_snapshot(data)


async def run_snapshot(data: RunInput) -> dict:
    if not settings().execution_enabled:
        raise PermissionError("Dedicated Docker execution is disabled")
    url, headers = connection()
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=data.timeout + 30, trust_env=False, follow_redirects=False
    ) as client:
        response = await client.post("/run", json=data.model_dump(mode="json"))
        response.raise_for_status()
        result = response.json()
    result["logs"] = redact(str(result.get("logs", "")))[:500100]
    if result.get("build"):
        result["build"]["logs"] = redact(str(result["build"].get("logs", "")))[:500100]
    return result
