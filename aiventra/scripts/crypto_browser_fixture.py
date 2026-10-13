"""Explicit DEMO fixture with real canonical adapter and disposable owner database."""

import asyncio
import base64
import os
import subprocess
from pathlib import Path
from uuid import uuid4


async def main():
    root = Path(__file__).resolve().parents[1]
    repo = root.parent
    os.chdir(root)
    private = root / "data/pytest-temp" / ("crypto-browser-" + str(uuid4()))
    private.mkdir(parents=True, exist_ok=False)
    token = "synthetic-crypto-browser-" + uuid4().hex
    for key in list(os.environ):
        if key.endswith("_API_KEY") or key in {"GITHUB_TOKEN", "GH_TOKEN", "AIVENTRA_GITHUB_TOKEN"}:
            os.environ[key] = ""
    os.environ.update(
        DATABASE_URL="sqlite:///" + (private / "fixture.db").as_posix(),
        REQUIRED_DATABASE_BACKEND="sqlite",
        APP_ENV="test",
        ISOLATED_TEST_ENVIRONMENT="true",
        AI_SPENDING_MODE="ZERO_COST_ONLY",
        EXECUTION_ENABLED="false",
        MOCK_ENABLED="false",
        EMBEDDING_PROVIDER="disabled",
        JWT_SECRET="synthetic-crypto-browser-auth-32-characters",
        PROVIDER_SECRET_KEY=base64.urlsafe_b64encode(b"c" * 32).decode(),
        OWNER_EMAIL="crypto-owner@fixture.test",
        OWNER_PASSWORD="synthetic-crypto-browser-password",
        ARTIFACT_ROOT=str(private / "artifacts"),
        REPOSITORY_ROOT=str(private / "repositories"),
        WEB_ORIGIN="http://localhost:3004",
        CRYPTO_ADAPTER_URL="http://127.0.0.1:8021",
        CRYPTO_ADAPTER_TOKEN=token,
        CRYPTO_REPO_ROOT=str(repo),
        CRYPTO_PERSISTENT_ROOT=str(private / "science"),
        CRYPTO_CONTROL_ROOT=str(private / "control"),
        CRYPTO_DEMO_FIXTURE_STATE="1",
        AIVENTRA_API_URL="http://127.0.0.1:8004",
        OIDC_ISSUER="",
        GITHUB_PUBLICATION_REPOSITORIES="",
        FIXTURE_CATALOG_ENABLED="false",
    )
    for key, folder in {
        "GOLD": "gold",
        "PHASE7_DATA": "data",
        "HISTORICAL": "historical",
        "CHECKPOINT": "checkpoints",
        "CACHE": "cache",
        "MODEL": "models",
        "REPORT": "reports",
        "LOG": "logs",
        "VERIFICATION": "verification",
    }.items():
        os.environ[f"CRYPTO_{key}_ROOT"] = str(private / "science" / folder)
    os.environ.pop("PHASE7_ALLOW_CLOUD_RESEARCH", None)
    os.environ.pop("CRYPTO_ENABLE_SCIENTIFIC_JOBS", None)
    import httpx
    import uvicorn
    from alembic import command
    from alembic.config import Config
    from company_os.api import app
    from company_os.config import settings
    from company_os.db import SessionLocal, engine
    from company_os.health import heartbeat
    from company_os.organization import seed

    original = httpx.AsyncHTTPTransport.handle_async_request

    async def loopback_only(transport, request):
        if request.url.scheme != "http" or request.url.host != "127.0.0.1" or request.url.port != 8021:
            raise httpx.ConnectError("Crypto browser fixture prohibits external network")
        return await original(transport, request)

    def deny(*_args, **_kwargs):
        raise httpx.ConnectError("Crypto browser fixture prohibits external network")

    httpx.HTTPTransport.handle_request = deny
    httpx.AsyncHTTPTransport.handle_async_request = loopback_only
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    with SessionLocal() as session:
        settings().crypto_project_org_id = seed(session).id
    os.environ["CRYPTO_PROJECT_ORG_ID"] = settings().crypto_project_org_id
    python = repo / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    with (private / "adapter.log").open("ab") as output:
        adapter = subprocess.Popen(
            [str(python), "-m", "integration.crypto_aiventra.service", "--port", "8021"],
            cwd=repo,
            env=dict(os.environ),
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    worker_id = str(uuid4())

    async def worker():
        while True:
            with SessionLocal() as session:
                heartbeat(session, worker_id)
            await asyncio.sleep(0.25)

    work = asyncio.create_task(worker())
    try:
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8004, log_level="warning")).serve()
    finally:
        work.cancel()
        adapter.terminate()
        adapter.wait(timeout=10)
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
