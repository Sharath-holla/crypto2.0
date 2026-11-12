"""Scoped GitHub transport fixtures, real SQLite receipts; no live GitHub mutation/inference."""

import base64
import hashlib
from uuid import uuid4

import httpx
import pytest
from company_os import models as m
from company_os import runner_checkout as rc
from company_os.config import settings
from company_os.db import now
from company_os.publication import GitHub
from fastapi import HTTPException

from tests.test_staffing import project_plan


def manifest():
    return rc.CheckoutInput(
        job_id=uuid4(),
        org_id=uuid4(),
        project_id=uuid4(),
        repository="example/safe",
        branch="main",
        commit="a" * 40,
    )


@pytest.fixture
def reader(monkeypatch):
    monkeypatch.setattr(settings(), "github_publication_repositories", "example/safe")
    monkeypatch.setattr(settings(), "github_publication_token_env", "TEST_CHECKOUT_TOKEN")
    monkeypatch.setenv("TEST_CHECKOUT_TOKEN", "fixture-reader-credential")
    source = (
        b"import unittest\nclass Safe(unittest.TestCase):\n def test_sum(self): self.assertEqual(2+3,5)\n"
    )
    sha = hashlib.sha1(b"blob " + str(len(source)).encode() + b"\0" + source).hexdigest()
    fixture = {
        "requests": [],
        "tree": [{"path": "test_safe.py", "mode": "100644", "type": "blob", "sha": sha, "size": len(source)}],
        "source": source,
        "ref": "a" * 40,
        "truncated": False,
    }

    async def request(self, method, path, body=None, missing=False):
        assert method == "GET" and body is None
        fixture["requests"].append(path)
        if path.startswith("git/ref/"):
            return {"object": {"sha": fixture["ref"]}}
        if path.startswith("git/commits/"):
            return {"tree": {"sha": "b" * 40}}
        if path.startswith("git/trees/"):
            return {"tree": fixture["tree"], "truncated": fixture["truncated"]}
        return {"encoding": "base64", "content": base64.b64encode(fixture["source"]).decode()}

    monkeypatch.setattr(GitHub, "request", request)
    return fixture


async def test_checkout_is_readonly_scoped_idempotent_and_restart_safe(company, reader):
    root, data = company["root"] / "broker", manifest()
    value = await rc.checkout(root, data)
    assert value["status"] == "ready" and value["commit"] == "a" * 40
    assert "Not executed" in value["execution"] and not (rc.source_path(root, data.job_id) / ".git").exists()
    assert rc.files(root, value)["test_safe.py"] == reader["source"].decode()
    count = len(reader["requests"])
    assert await rc.checkout(root, data) == value and len(reader["requests"]) == count
    rc.recover(root)
    assert rc.get(root, data.job_id, data.org_id, data.project_id) == value
    with pytest.raises(HTTPException) as denied:
        rc.get(root, data.job_id, uuid4(), data.project_id)
    assert denied.value.status_code == 404
    changed = data.model_copy(update={"commit": "c" * 40})
    with pytest.raises(HTTPException):
        await rc.checkout(root, changed)
    assert "fixture-reader" not in rc.receipt_path(root, data.job_id).read_text()
    rc.cleanup(root, data.job_id)
    assert not rc.source_path(root, data.job_id).exists()


@pytest.mark.parametrize(
    "case",
    [
        "traversal",
        "hook",
        "secret",
        "symlink",
        "submodule",
        "case_collision",
        "moved",
        "blob_hash",
        "truncated",
        "size",
        "branch",
        "token",
    ],
)
async def test_checkout_rejects_unsafe_source_without_workspace(company, reader, monkeypatch, case):
    data = manifest()
    item = reader["tree"][0]
    if case == "traversal":
        item["path"] = "../escape.py"
    if case == "hook":
        item["path"] = ".git/hooks/post-checkout"
    if case == "secret":
        item["path"] = ".env"
    if case == "symlink":
        item["mode"] = "120000"
    if case == "submodule":
        item["type"] = "commit"
    if case == "case_collision":
        reader["tree"].append({**item, "path": "TEST_SAFE.py"})
    if case == "moved":
        reader["ref"] = "c" * 40
    if case == "blob_hash":
        reader["source"] = b"changed"
    if case == "truncated":
        reader["truncated"] = True
    if case == "size":
        item["size"] = 1000001
    if case == "branch":
        data = data.model_copy(update={"branch": "main/../other"})
    if case == "token":
        monkeypatch.delenv("TEST_CHECKOUT_TOKEN")
    root = company["root"] / "broker"
    value = await rc.checkout(root, data)
    assert value["status"] == "failed" and not rc.source_path(root, data.job_id).exists()


async def test_checkout_integrity_expiry_interruption_and_timeout(company, reader, monkeypatch):
    root, data = company["root"] / "broker", manifest()
    value = await rc.checkout(root, data)
    path = rc.source_path(root, data.job_id) / "test_safe.py"
    path.chmod(0o600)
    path.write_text("changed")
    with pytest.raises(ValueError):
        rc.files(root, value)
    value["expires_at"] = 0
    rc.store(root, data.job_id, value)
    assert rc.get(root, data.job_id, data.org_id, data.project_id)["status"] == "expired"
    other = manifest()
    rc.store(
        root,
        other.job_id,
        {
            **other.model_dump(mode="json"),
            "status": "fetching",
            "created_at": now(),
            "expires_at": now() + 60,
        },
    )
    rc.source_path(root, other.job_id).mkdir(parents=True)
    rc.recover(root)
    assert rc.get(root, other.job_id, other.org_id, other.project_id)["status"] == "interrupted"

    async def timeout(*args):
        raise TimeoutError()

    monkeypatch.setattr(rc, "acquire", timeout)
    assert (await rc.checkout(root, manifest()))["status"] == "failed"


async def test_api_checkout_exact_owner_approval_recovery_and_single_execution(
    http, company, requirement, monkeypatch
):
    from company_os import repository_checkouts as api

    project, _ = await project_plan(http, company, requirement)
    with company["factory"]() as session:
        repo = m.Repository(
            org_id=company["org"].id,
            project_id=project["id"],
            name="safe",
            path="remote",
            baseline_commit="a" * 40,
            report={"remote_metadata_only": True, "repository": "example/safe", "branch": "main"},
        )
        session.add(repo)
        session.commit()
        repository_id = repo.id
    calls = []
    saved = {}

    async def broker(method, path, data=None, params=None, timeout=200):
        calls.append((method, path))
        if path == "/checkouts":
            saved.update(
                {
                    **data,
                    "status": "ready",
                    "expires_at": now() + 3600,
                    "source_digest": "d" * 64,
                    "file_count": 1,
                    "bytes": 80,
                }
            )
            raise httpx.ReadTimeout("fixture interrupted HTTP response")
        if method == "GET":
            return dict(saved)
        if path.endswith("/execute"):
            return {
                "job_id": data["job_id"],
                "status": "completed",
                "exit_code": 0,
                "build": {"exit_code": 0},
                "logs": "FIXTURE runner adapter only; no Docker was executed",
            }
        return {**saved, "status": "cleaned"}

    monkeypatch.setattr(api, "broker", broker)
    body = {"request_id": str(uuid4())}
    url = f"/repositories/{repository_id}/checkout"
    row = http.post(url, json=body).json()
    assert row["status"] == "interrupted"
    assert http.post(url, json=body).json()["id"] == row["id"] and len(calls) == 1
    path = f"/repository-checkouts/{row['id']}"
    row = http.post(path + "/reconcile").json()
    assert row["status"] == "ready"
    assert http.get(f"/repositories/{repository_id}/checkouts").json()[0]["id"] == row["id"]
    assert http.patch(f"/records/{row['id']}", json={"version": 1, "status": "reviewed"}).status_code == 409
    command = {
        "request_id": str(uuid4()),
        "version": row["version"],
        "source_digest": "f" * 64,
        "suite": "python-unittest",
    }
    assert http.post(path + "/approve-execution", json=command).status_code == 409
    command["source_digest"] = "d" * 64
    approval = http.post(path + "/approve-execution", json=command)
    assert approval.status_code == 200, approval.text
    approval = approval.json()
    execution = {"request_id": str(uuid4()), "approval_id": approval["id"]}
    monkeypatch.setattr(settings(), "execution_enabled", False)
    assert http.post(path + "/execute", json=execution).status_code == 409
    monkeypatch.setattr(settings(), "execution_enabled", True)
    with company["factory"]() as session:
        session.get(m.Approval, approval["id"]).expires_at = 0
        session.commit()
    assert http.post(path + "/execute", json=execution).status_code == 403
    command["request_id"] = str(uuid4())
    execution["approval_id"] = http.post(path + "/approve-execution", json=command).json()["id"]
    with company["factory"]() as session:
        checkout = session.get(m.BusinessRecord, row["id"])
        checkout.data = {**checkout.data, "receipt": {**checkout.data["receipt"], "source_digest": "e" * 64}}
        session.commit()
    assert http.post(path + "/execute", json=execution).status_code == 403
    with company["factory"]() as session:
        checkout = session.get(m.BusinessRecord, row["id"])
        checkout.data = {**checkout.data, "receipt": {**checkout.data["receipt"], "source_digest": "d" * 64}}
        session.commit()
    result = http.post(path + "/execute", json=execution)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "completed" and "FIXTURE" in result.text
    assert http.get(path + "/executions").json()[0]["id"] == result.json()["id"]
    assert http.get(f"/repository-checkout-executions/{result.json()['id']}").json()["status"] == "completed"

    async def recovered(identity):
        return {
            "job_id": identity,
            "status": "completed",
            "exit_code": 0,
            "logs": "FIXTURE recovered saved result",
        }

    monkeypatch.setattr("company_os.sandbox.stored_result", recovered)
    reconciliation = f"/repository-checkout-executions/{result.json()['id']}/reconcile"
    assert http.post(reconciliation).json()["status"] == "completed"

    async def unavailable(identity):
        raise httpx.ReadTimeout("fixture runner read interrupted")

    monkeypatch.setattr("company_os.sandbox.stored_result", unavailable)
    assert http.post(reconciliation).status_code == 409
    count = len(calls)
    assert (
        http.post(path + "/execute", json=execution).json()["id"] == result.json()["id"]
        and len(calls) == count
    )
    assert http.post(path + "/execute", json={**execution, "request_id": str(uuid4())}).status_code == 409
    company["factory"].kw["bind"].dispose()
    assert http.get(f"/repositories/{repository_id}/checkouts").json()[0]["status"] == "ready"
    assert http.post(path + "/cleanup").json()["status"] == "cleaned"
    assert (
        http.post(path + "/approve-execution", json={**command, "request_id": str(uuid4())}).status_code
        == 409
    )
    assert http.post("/repository-checkouts/foreign/reconcile").status_code == 404
