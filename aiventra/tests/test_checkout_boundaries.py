import asyncio
from uuid import uuid4

import httpx
import pytest
from company_os import runner_checkout as rc
from company_os import runner_service as runner
from fastapi import HTTPException

from tests.test_checkout import manifest

pytest_plugins = ["tests.test_checkout"]


async def test_broker_http_authentication_project_scope_and_explicit_execution(company, reader, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", company["root"] / "broker")
    monkeypatch.setattr(runner, "TOKEN", "test-private-runner-token-32-characters")
    monkeypatch.setattr(runner, "gate", asyncio.Semaphore(2))
    ran = []

    async def execute(data):
        ran.append(data)
        return {
            "job_id": str(data.job_id),
            "status": "completed",
            "logs": "FIXTURE Docker transport; no host execution",
        }

    monkeypatch.setattr(runner, "run_input", execute)
    data = manifest().model_dump(mode="json")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=runner.app), base_url="http://broker"
    ) as client:
        assert (await client.post("/checkouts", json=data)).status_code == 401
        client.headers["Authorization"] = "Bearer " + runner.TOKEN
        response = await client.post("/checkouts", json=data)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ready" and not ran
        path = f"/checkouts/{data['job_id']}"
        scope = {key: data[key] for key in ("org_id", "project_id")}
        assert (await client.get(path, params={**scope, "org_id": str(uuid4())})).status_code == 404
        run = {**scope, "job_id": str(uuid4()), "suite": "python-unittest"}
        assert (await client.post(path + "/execute", json={**run, "command": "arbitrary"})).status_code == 422
        assert (await client.post(path + "/execute", json=run)).status_code == 200
        assert len(ran) == 1 and "test_safe.py" in ran[0].files
        assert (await client.post(path + "/cleanup", json=scope)).json()["status"] == "cleaned"
        assert (await client.post(path + "/execute", json=run)).status_code == 409


async def test_checkout_total_retention_capacity_and_expired_cleanup(company, reader, monkeypatch):
    monkeypatch.setenv("RUNNER_CHECKOUT_MAX_RETAINED", "1")
    root, data = company["root"] / "broker", manifest()
    saved = await rc.checkout(root, data)
    with pytest.raises(HTTPException) as error:
        await rc.checkout(root, manifest())
    assert error.value.status_code == 429
    saved["expires_at"] = 0
    rc.store(root, data.job_id, saved)
    assert (await rc.checkout(root, manifest()))["status"] == "ready"
    assert not rc.source_path(root, data.job_id).exists()


async def test_readonly_capability_refuses_mutating_github_endpoints(company, reader):
    client = rc.ScopedCheckoutReader("example/safe")
    for method, path in [("POST", "git/blobs/x"), ("GET", "pulls"), ("PATCH", "git/refs/heads/main")]:
        with pytest.raises(ValueError):
            await client.request(method, path)
    assert not reader["requests"]
