import base64
import hashlib
from uuid import uuid4

import httpx
import pytest
from company_os import models as m
from company_os.config import settings
from company_os.publication import GitHub
from company_os.repository_imports import discover
from sqlalchemy import select

from tests.test_staffing import project_plan


@pytest.fixture
def github_reader(monkeypatch):
    monkeypatch.setattr(settings(), "github_publication_repositories", "example/safe")
    monkeypatch.setattr(settings(), "github_publication_token_env", "TEST_READONLY_GITHUB_TOKEN")
    monkeypatch.setenv("TEST_READONLY_GITHUB_TOKEN", "fixture-token-never-sent-to-model")
    requests = []
    raw = b'{"name":"harmless-fixture","scripts":{"test":"node --test"}}'
    sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()

    def handle(request):
        assert request.method == "GET", "Read-only discovery attempted a mutation"
        assert request.url.host == "api.github.com"
        requests.append(str(request.url))
        path = request.url.path
        if path.endswith("/safe/"):
            return httpx.Response(404, json={"message": "Incorrect repository metadata endpoint"})
        data = {"default_branch": "main"}
        if path.endswith("/branches"):
            data = [{"name": "main"}, {"name": "feature/safe"}]
        elif "/git/ref/" in path:
            data = {"object": {"sha": "a" * 40}}
        elif "/git/commits/" in path:
            data = {"tree": {"sha": "b" * 40}}
        elif "/git/trees/" in path:
            data = {
                "tree": [
                    {"path": name, "type": "blob", "mode": "100644", "size": len(raw), "sha": sha}
                    for name in ["package.json", "tests/safe.test.js", ".env", "private.key"]
                ]
            }
        elif "/git/blobs/" in path:
            data = {"encoding": "base64", "content": base64.b64encode(raw).decode()}
        return httpx.Response(200, json=data)

    original = GitHub.__init__
    clients = []

    def init(self, repository, client=None):
        injected = client or httpx.AsyncClient(transport=httpx.MockTransport(handle))
        clients.append(injected)
        original(self, repository, injected)

    monkeypatch.setattr(GitHub, "__init__", init)
    return requests


async def test_readonly_import_branch_provenance_idempotency_restart_and_coding_gate(
    http, company, requirement, github_reader
):
    project, _ = await project_plan(http, company, requirement)
    body = {
        "request_id": str(uuid4()),
        "repository": "https://github.com/example/safe.git",
        "branch": "feature/safe",
    }
    path = f"/projects/{project['id']}/github-import"
    response = http.post(path, json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["report"]["branch"] == "feature/safe" and row["report"]["technology_stack"] == [
        "JavaScript/TypeScript"
    ]
    assert row["report"]["files"] == ["package.json", "tests/safe.test.js"]
    assert "fixture-token" not in response.text and "baseline_tests" in row["report"]
    count = len(github_reader)
    assert http.post(path, json=body).json()["id"] == row["id"] and len(github_reader) == count
    assert http.post(path, json={**body, "branch": "main"}).status_code == 409
    company["factory"].kw["bind"].dispose()
    with company["factory"]() as session:
        assert session.get(m.Repository, row["id"]).baseline_commit == "a" * 40
        artifact = session.get(m.Artifact, row["report"]["artifact_id"])
        assert artifact.project_id == project["id"] and "fixture-token" not in artifact.content
        record = session.scalar(
            select(m.BusinessRecord).where(m.BusinessRecord.kind == "github_repository_import")
        )
        assert (
            http.patch(f"/records/{record.id}", json={"version": 1, "status": "reviewed"}).status_code == 409
        )
    denied = http.post(
        f"/projects/{project['id']}/coding",
        json={
            "repository_id": row["id"],
            "objective": "Implement approved harmless fixture behavior",
            "acceptance": ["Tests pass"],
            "test_suite": "node-test",
            "mode": "mock",
        },
    )
    assert denied.status_code == 409


async def test_unauthorized_repo_and_project_never_make_github_requests(
    http, company, requirement, github_reader
):
    project, _ = await project_plan(http, company, requirement)
    body = {"request_id": str(uuid4()), "repository": "other/private"}
    assert http.post(f"/projects/{project['id']}/github-import", json=body).status_code == 422
    assert not github_reader
    assert (
        http.post("/projects/foreign/github-import", json={**body, "repository": "example/safe"}).status_code
        == 404
    )
    assert not github_reader
    with company["factory"]() as session:
        assert not session.scalar(select(m.Repository))


async def test_default_branch_is_discovered_from_metadata(github_reader):
    result = await discover("example/safe")
    assert result["default_branch"] == result["branch"] == "main" and result["read_only"]


async def test_corrupt_blob_leaves_no_saved_import(http, company, requirement, github_reader, monkeypatch):
    project, _ = await project_plan(http, company, requirement)
    original = GitHub.request

    async def corrupt(self, method, path, *args, **kwargs):
        result = await original(self, method, path, *args, **kwargs)
        if path.startswith("git/blobs/"):
            result["content"] = base64.b64encode(b"Different untrusted content").decode()
        return result

    monkeypatch.setattr(GitHub, "request", corrupt)
    response = http.post(
        f"/projects/{project['id']}/github-import",
        json={"request_id": str(uuid4()), "repository": "example/safe"},
    )
    assert response.status_code == 422
    with company["factory"]() as session:
        assert not session.scalar(select(m.Repository))
