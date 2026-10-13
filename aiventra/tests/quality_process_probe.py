"""Disposable worker-process recovery probe; deterministic transports only.

Invoked by test_quality. Never imports or executes the candidate repository.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("root", type=Path)
    parser.add_argument("mode", choices=["crash", "tick"])
    args = parser.parse_args()
    root = args.root.resolve()
    if not root.is_relative_to((Path.cwd() / "data/pytest-temp").resolve()):
        raise RuntimeError("Recovery probe requires private pytest storage")
    from company_os import gateway, quality
    from company_os.config import settings
    from company_os.db import make_engine
    from company_os.providers import Response
    from company_os.workflows import tick
    from sqlalchemy.orm import sessionmaker
    from test_quality import tool_result

    config = settings()
    config.database_url = args.database
    config.required_database_backend = "sqlite"
    config.ai_spending_mode = "ZERO_COST_ONLY"
    config.mock_enabled = True
    config.repository_root, config.artifact_root = root / "repositories", root / "artifacts"
    config.s3_bucket, config.oidc_issuer = "", ""
    config.scheduler_concurrency = 4
    original = gateway.fixture

    def fixture(schema, context):
        if schema == "QualityAssessment":
            return Response(
                {
                    "verdict": "PASS",
                    "summary": "DETERMINISTIC PROCESS RECOVERY ASSESSMENT; not live AI.",
                    "checked_cases": [c["id"] for c in context["cases"]],
                    "findings": [],
                },
                0,
                0,
            )
        return original(schema, context)

    gateway.fixture = fixture

    async def run(request):
        result = tool_result(request)
        target = root / (str(request.job_id) + ".fixture-result.json")
        if target.exists():
            raise AssertionError("Duplicate execution dispatch after interrupted worker")
        target.write_text(json.dumps(result), encoding="utf-8")
        if args.mode == "crash":
            os._exit(17)  # After durable remote-shaped receipt; before worker saves its response.
        return result

    async def stored(job_id):
        return json.loads((root / (job_id + ".fixture-result.json")).read_text())

    async def deny(*args, **kwargs):
        raise AssertionError("Process recovery fixture prohibits outbound network")

    import httpx

    httpx.AsyncHTTPTransport.handle_async_request = deny
    quality.run_snapshot, quality.stored_result = run, stored
    engine = make_engine(args.database)
    try:
        assert asyncio.run(tick(sessionmaker(engine, expire_on_commit=False)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
