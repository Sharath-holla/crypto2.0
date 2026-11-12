"""Disposable ordinary browser application; never attaches to the owner's database."""

import asyncio
import base64
import os
from pathlib import Path
from uuid import uuid4


async def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    private = root / "data" / "pytest-temp" / ("browser-" + str(uuid4()))
    private.mkdir(parents=True, exist_ok=False)
    from dotenv import load_dotenv

    load_dotenv(root / ".env")
    for key in list(os.environ):
        if key.endswith("_API_KEY") or key in {"AIVENTRA_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"}:
            os.environ[key] = ""  # Prevent dotenv from repopulating it at application import.
    os.environ.update(
        {
            "DATABASE_URL": "sqlite:///" + (private / "fixture.db").as_posix(),
            "REQUIRED_DATABASE_BACKEND": "sqlite",
            "APP_ENV": "test",
            "ISOLATED_TEST_ENVIRONMENT": "true",
            "FIXTURE_CATALOG_ENABLED": "true",
            "AI_SPENDING_MODE": "ZERO_COST_ONLY",
            "SCHEDULER_CONCURRENCY": "4",
            "EXECUTION_ENABLED": "false",
            "JWT_SECRET": "isolated-browser-auth-secret-32-characters",
            "PROVIDER_SECRET_KEY": base64.urlsafe_b64encode(b"b" * 32).decode(),
            "OWNER_EMAIL": "browser-owner@fixture.test",
            "OWNER_PASSWORD": "isolated-browser-password",
            "ARTIFACT_ROOT": str(private / "artifacts"),
            "REPOSITORY_ROOT": str(private / "repositories"),
            "EMBEDDING_PROVIDER": "deterministic_test",
            "MOCK_ENABLED": "true",
            "OIDC_ISSUER": "",
            "WEB_ORIGIN": "http://localhost:3002",
            "GITHUB_PUBLICATION_REPOSITORIES": "",
            "GITHUB_PUBLICATION_TOKEN_ENV": "BROWSER_DISABLED_GITHUB_TOKEN",
        }
    )
    import httpx
    import uvicorn
    from alembic import command
    from alembic.config import Config
    from company_os.api import app
    from company_os.db import SessionLocal, engine
    from company_os.health import heartbeat
    from company_os.organization import seed
    from company_os.workflows import tick

    def deny(*args, **kwargs):
        raise httpx.ConnectError("Isolated browser fixture prohibits outbound network")

    async def deny_async(*args, **kwargs):
        deny()

    httpx.HTTPTransport.handle_request = deny
    httpx.AsyncHTTPTransport.handle_async_request = deny_async
    command.upgrade(Config(str(root / "alembic.ini")), "head")
    with SessionLocal() as session:
        seed(session)
    worker_id = str(uuid4())

    async def worker():
        while True:
            with SessionLocal() as session:
                heartbeat(session, worker_id)
            await tick(SessionLocal)
            await asyncio.sleep(0.25)

    work = asyncio.create_task(worker())
    try:
        await uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8002, log_level="warning")).serve()
    finally:
        work.cancel()
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
