"""Disposable worker crash probe. No candidate code, models or network are executed."""

import argparse
import asyncio
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("root", type=Path)
    parser.add_argument("mode", choices=["crash", "crash_before", "tick"])
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to((Path.cwd() / "data/pytest-temp").resolve()):
        raise RuntimeError("Probe requires private pytest storage")
    from company_os import deployment_adapter
    from company_os.config import settings
    from company_os.db import make_engine
    from company_os.workflows import tick
    from sqlalchemy.orm import sessionmaker

    config = settings()
    config.database_url, config.required_database_backend = args.database, "sqlite"
    config.ai_spending_mode, config.mock_enabled = "ZERO_COST_ONLY", True
    config.repository_root, config.artifact_root = root / "repositories", root / "artifacts"
    config.s3_bucket, config.oidc_issuer, config.scheduler_concurrency = "", "", 4
    original = deployment_adapter.submit
    original_advance = deployment_adapter.advance

    async def submit(*values):
        if args.mode == "crash_before":
            os._exit(17)
        await original(*values)
        os._exit(17)  # Adapter receipt durable, workflow acknowledgement absent.

    def advance(session, *values):
        original_advance(session, *values)
        session.commit()
        os._exit(17)  # Simulate an external state advancing before checkpoint.

    async def deny(*args, **kwargs):
        raise AssertionError("Deployment process probe prohibits networking")

    import httpx

    httpx.AsyncHTTPTransport.handle_async_request = deny
    if args.mode in {"crash", "crash_before"}:
        deployment_adapter.submit = submit
        deployment_adapter.advance = advance
    engine = make_engine(args.database)
    try:
        assert asyncio.run(tick(sessionmaker(engine, expire_on_commit=False)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
