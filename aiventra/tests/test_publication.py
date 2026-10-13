"""Git metadata + controlled GitHub protocol fixtures, never live publication evidence."""

import base64
import hashlib
import json
from uuid import uuid4

import httpx
import pytest
from company_os import models as m
from company_os import publication
from company_os.config import settings
from company_os.db import now, uid
from company_os.engineering import prepare_pull_request
from company_os.organization import agent_for
from company_os.repositories import apply_files, git, worktree
from company_os.security import digest
from sqlalchemy import select
from test_agent_planning import draft_project

pytestmark = pytest.mark.usefixtures("contract_inference")


@pytest.fixture
async def publishable(http, company, requirement, monkeypatch):
    project, _ = await draft_project(http, company, requirement)
    root = settings().repository_root / "publication-fixture"
    root.mkdir(parents=True)
    git(root, "init")
    git(root, "config", "user.email", "fixture@local.invalid")
    git(root, "config", "user.name", "Explicit publication fixture")
    (root / "README.md").write_text("Harmless metadata fixture\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-m", "Fixture baseline")
    base = git(root, "rev-parse", "HEAD")
    task_id = uid()
    workspace = settings().repository_root / ".worktrees" / project["id"] / task_id
    worktree(root, workspace, task_id, base)
    apply_files(workspace, [{"path": "feature.txt", "content": "Harmless approved fixture change\n"}])
    git(workspace, "add", "-A")
    tree = git(workspace, "write-tree")
    with company["factory"]() as session:
        developer = agent_for(session, company["org"].id, "Backend Developer")
        reviewer = agent_for(session, company["org"].id, "Code Reviewer")
        qa = agent_for(session, company["org"].id, "QA Director")
        repository = m.Repository(
            id=uid(),
            org_id=developer.org_id,
            project_id=project["id"],
            name="Fixture",
            path=str(root),
            baseline_commit=base,
        )
        session.add(repository)
        session.flush()
        task = m.Task(
            id=task_id,
            org_id=developer.org_id,
            project_id=project["id"],
            assigned_agent_id=developer.id,
            objective="Add a harmless feature for publication protocol verification",
            kind="coding",
            status="completed",
            payload={
                "repository_id": repository.id,
                "baseline_commit": base,
                "mode": "live",
                "test_suite": "python-unittest",
                "repair_limit": 1,
            },
            acceptance=["Explicit fixture metadata only"],
        )
        session.add(task)
        session.flush()
        workflow = m.Workflow(
            id=uid(), org_id=task.org_id, task_id=task.id, kind="coding", mode="live", status="completed"
        )
        session.add(workflow)
        session.flush()
        provider = m.Provider(
            id=uid(),
            org_id=task.org_id,
            name="Explicit publication evidence fixture",
            kind="ollama",
            base_url="http://localhost:11434",
            credential_env="",
        )
        session.add(provider)
        session.flush()
        model = m.ModelConfig(
            id=uid(), org_id=task.org_id, provider_id=provider.id, identifier="fixture-not-a-live-model"
        )
        session.add(model)
        session.flush()
        run = m.ModelRun(
            id=uid(),
            org_id=task.org_id,
            workflow_id=workflow.id,
            task_id=task.id,
            agent_id=reviewer.id,
            model_id=model.id,
            status="succeeded",
            step_name="fixture-review",
            attempt=1,
            routing_reason="Explicit fixture",
            response={"approved": True},
        )
        author = m.ModelRun(
            id=uid(),
            org_id=task.org_id,
            workflow_id=workflow.id,
            task_id=task.id,
            agent_id=developer.id,
            model_id=model.id,
            status="succeeded",
            step_name="fixture-author",
            attempt=1,
            routing_reason="Explicit fixture",
        )
        execution = m.Execution(
            id=uid(),
            org_id=task.org_id,
            task_id=task.id,
            agent_id=qa.id,
            workspace=str(workspace),
            command=["fixture-only"],
            environment="Explicit dedicated Docker protocol fixture; no actual Docker execution",
            status="completed",
            exit_code=0,
            logs="Explicit fixture\nRan 1 test\nOK",
        )
        session.add_all([run, author, execution])
        task.evidence = {
            "baseline_commit": base,
            "candidate_tree": tree,
            "execution_id": execution.id,
            "runner_job_id": execution.id,
            "reviewer_approved": True,
            "build_exit_code": 0,
            "reviews": [{"review_run_id": run.id, "author_run_id": author.id, "approved": True}],
        }
        session.add(
            m.Approval(
                org_id=task.org_id,
                category="repository_change",
                subject_id=task.id,
                subject_hash=digest(task.payload),
                version=task.version,
                owner_id=company["owner"].id,
                expires_at=now() + 3600,
            )
        )
        session.flush()
        prepare_pull_request(session, task, session.get(m.Project, project["id"]), developer, workspace, tree)
        session.commit()
    monkeypatch.setattr(settings(), "github_publication_repositories", "fixture-owner/fixture-repo")
    monkeypatch.setenv("AIVENTRA_GITHUB_TOKEN", "explicit-controlled-publication-credential")
    state = {"calls": [], "manifest": None, "branch": None, "pull": None, "fault": None}

    def handler(request):
        path = request.url.path.removeprefix("/repos/fixture-owner/fixture-repo/")
        body = json.loads(request.content) if request.content else None
        state["calls"].append((request.method, path, body))
        assert request.headers["authorization"] == "Bearer explicit-controlled-publication-credential"
        manifest = state["manifest"]
        if path in {"", "/repos/fixture-owner/fixture-repo"}:
            result = {"permissions": {"push": True}}
        elif path == "git/ref/heads/main":
            result = {"object": {"sha": "0" * 40 if state["fault"] == "base" else base}}
        elif path.startswith("git/ref/heads/"):
            if state["fault"] == "branch":
                result = {"object": {"sha": "0" * 40}}
            elif state["branch"]:
                result = {"object": {"sha": state["branch"]}}
            else:
                return httpx.Response(404)
        elif path == "git/blobs":
            content = base64.b64decode(body["content"])
            result = {"sha": hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()}
            if state["fault"] == "blob":
                result["sha"] = "0" * 40
            if state["fault"] == "paused":
                with company["factory"]() as session:
                    session.get(m.Organization, company["org"].id).paused = True
                    session.commit()
        elif path == "git/commits/" + base:
            result = {"tree": {"sha": git(root, "rev-parse", "HEAD^{tree}")}}
        elif path == "git/trees":
            assert body["tree"] == manifest["entries"]
            result = {"sha": "0" * 40 if state["fault"] == "tree" else tree}
        elif path == "git/commits":
            assert body == manifest["commit"]
            result = {"sha": "0" * 40 if state["fault"] == "commit" else manifest["head_commit"]}
        elif path == "git/refs":
            assert request.method == "POST" and "force" not in body
            state["branch"] = body["sha"]
            result = {"object": {"sha": body["sha"]}}
        elif path == "pulls" and request.method == "GET":
            result = [state["pull"]] if state["pull"] else []
        elif path == "pulls" and request.method == "POST":
            assert body["draft"] is True and body["base"] == "main"
            state["pull"] = {
                "number": 1,
                "html_url": "https://github.com/fixture-owner/fixture-repo/pull/1",
                "draft": True,
                "state": "open",
                "head": {"sha": manifest["head_commit"]},
                "base": {"ref": "main", "sha": base},
            }
            if state["fault"] == "lost_response":
                state["fault"] = None
                raise httpx.ReadTimeout("Controlled lost-response fixture")
            result = state["pull"]
        elif path == "pulls/1":
            result = state["pull"]
        elif path.endswith("/check-runs"):
            result = {
                "total_count": 1,
                "check_runs": [{"id": 1, "name": "fixture", "status": "completed", "conclusion": "failure"}],
            }
        elif path.endswith("/status"):
            result = {"state": "failure", "statuses": []}
        elif path == "pulls/1/reviews":
            result = [
                {
                    "id": 2,
                    "state": "CHANGES_REQUESTED",
                    "body": "Add a fixture regression case",
                    "commit_id": manifest["head_commit"],
                }
            ]
        elif path == "pulls/1/comments":
            result = []
        else:
            raise AssertionError(f"Unexpected fixture request: {request.method} {path}")
        return httpx.Response(200, json=result)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    original = publication.GitHub

    class FixtureGitHub(original):
        def __init__(self, repository, unused=None):
            super().__init__(repository, client)

    monkeypatch.setattr(publication, "GitHub", FixtureGitHub)
    yield {"task_id": task_id, "state": state, "workspace": workspace, "project": project, "root": root}
    await client.aclose()


def prepare(http, fixture):
    response = http.post(
        f"/tasks/{fixture['task_id']}/publication-preview",
        json={"repository": "fixture-owner/fixture-repo", "base_ref": "main"},
    )
    assert response.status_code == 201, response.text
    record = response.json()
    fixture["state"]["manifest"] = record["data"]["manifest"]
    return record


def approve(http, record):
    response = http.post(
        f"/publications/{record['id']}/approve",
        json={"version": record["version"], "content_hash": record["data"]["manifest_hash"]},
    )
    assert response.status_code == 200, response.text


async def test_exact_publication_idempotency_feedback_and_bounded_owner_repair_scopes(
    http, company, publishable
):
    record = prepare(http, publishable)
    assert prepare(http, publishable)["id"] == record["id"]
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    assert (
        http.post(
            f"/publications/{record['id']}/approve", json={"version": 1, "content_hash": "a" * 64}
        ).status_code
        == 409
    )
    approve(http, record)
    response = http.post(f"/publications/{record['id']}/publish")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    assert http.post(f"/publications/{record['id']}/publish").status_code == 200
    assert prepare(http, publishable)["id"] == record["id"]
    calls = publishable["state"]["calls"]
    assert sum(method == "POST" and path == "pulls" for method, path, _ in calls) == 1
    assert all(method not in {"PATCH", "PUT", "DELETE"} for method, _, _ in calls)
    evidence = http.post(f"/publications/{record['id']}/feedback")
    assert evidence.status_code == 200, evidence.text
    feedback_hash = evidence.json()["data"]["feedback_hash"]
    assert evidence.json()["data"]["feedback"]["checks"][0]["conclusion"] == "failure"
    request_ids = [str(uuid4()), str(uuid4())]
    for request_id in request_ids:
        payload = {
            "request_id": request_id,
            "feedback_hash": feedback_hash,
            "objective": "Resolve the saved review feedback with a regression test",
        }
        repair = http.post(f"/publications/{record['id']}/repairs", json=payload)
        assert repair.status_code == 201, repair.text
        assert repair.json()["status"] == "awaiting_approval"
        assert http.post(f"/publications/{record['id']}/repairs", json=payload).json()["id"] == request_id
    assert (
        http.post(
            f"/publications/{record['id']}/repairs",
            json={
                "request_id": str(uuid4()),
                "feedback_hash": feedback_hash,
                "objective": "A third follow-up repair must be refused",
            },
        ).status_code
        == 409
    )
    with company["factory"]() as session:
        assert not list(session.scalars(select(m.Workflow).where(m.Workflow.task_id.in_(request_ids))))
    assert "explicit-controlled-publication-credential" not in response.text + evidence.text
    assert (
        http.patch(f"/records/{record['id']}", json={"version": 1, "status": "reviewed"}).status_code == 409
    )


@pytest.mark.parametrize("fault", ["base", "branch", "blob", "tree", "commit"])
async def test_remote_mismatch_never_publishes_a_pr_or_force_updates(http, publishable, fault):
    record = prepare(http, publishable)
    approve(http, record)
    publishable["state"]["fault"] = fault
    response = http.post(f"/publications/{record['id']}/publish")
    assert response.status_code == 409
    assert publishable["state"]["pull"] is None
    assert not any(method in {"PATCH", "PUT", "DELETE"} for method, _, _ in publishable["state"]["calls"])


async def test_lost_pr_response_reconciles_without_duplicate_publication(http, company, publishable):
    record = prepare(http, publishable)
    approve(http, record)
    publishable["state"]["fault"] = "lost_response"
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    with company["factory"]() as session:
        approval = session.scalar(
            select(m.Approval).where(
                m.Approval.category == "github_publication", m.Approval.subject_id == record["id"]
            )
        )
        approval.expires_at = now() - 1
        session.commit()
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    assert (
        http.post(
            f"/tasks/{publishable['task_id']}/publication-preview",
            json={"repository": "fixture-owner/fixture-repo", "base_ref": "main"},
        ).status_code
        == 409
    )
    with company["factory"]() as session:
        # Restore authorization only in this explicit protocol fixture to test
        # recovery after reopening connections; production cannot extend it.
        session.get(m.Approval, approval.id).expires_at = now() + 3600
        session.commit()
    company["factory"].kw["bind"].dispose()
    assert http.post(f"/publications/{record['id']}/publish").status_code == 200
    assert sum(method == "POST" and path == "pulls" for method, path, _ in publishable["state"]["calls"]) == 1


async def test_changed_candidate_and_missing_connector_refuse_publication(http, publishable, monkeypatch):
    monkeypatch.delenv("AIVENTRA_GITHUB_TOKEN")
    assert (
        http.post(
            f"/tasks/{publishable['task_id']}/publication-preview",
            json={"repository": "fixture-owner/fixture-repo"},
        ).status_code
        == 409
    )
    monkeypatch.setenv("AIVENTRA_GITHUB_TOKEN", "explicit-controlled-publication-credential")
    record = prepare(http, publishable)
    approve(http, record)
    (publishable["workspace"] / "feature.txt").write_text("Changed after approval\n")
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    assert publishable["state"]["branch"] is None


async def test_invalid_independent_evidence_is_refused_before_any_github_request(http, company, publishable):
    from copy import deepcopy

    for fault in (
        "empty_tests",
        "qa_is_author",
        "missing_job",
        "review_denied",
        "author_failed",
        "mock_review",
    ):
        with company["factory"]() as session:
            task = session.get(m.Task, publishable["task_id"])
            original = deepcopy(task.evidence)
            execution = session.get(m.Execution, task.evidence["execution_id"])
            review = session.get(m.ModelRun, task.evidence["reviews"][0]["review_run_id"])
            author = session.get(m.ModelRun, task.evidence["reviews"][0]["author_run_id"])
            model = session.get(m.ModelConfig, review.model_id)
            provider = session.get(m.Provider, model.provider_id)
            logs, qa_id = execution.logs, execution.agent_id
            if fault == "empty_tests":
                execution.logs = "Ran 0 tests\nOK"
            elif fault == "qa_is_author":
                execution.agent_id = task.assigned_agent_id
            elif fault == "missing_job":
                task.evidence = {**original, "runner_job_id": None}
            elif fault == "review_denied":
                review.response = {"approved": False}
            elif fault == "author_failed":
                author.status = "failed"
            else:
                provider.kind = "mock"
            session.commit()
        response = http.post(
            f"/tasks/{publishable['task_id']}/publication-preview",
            json={"repository": "fixture-owner/fixture-repo"},
        )
        assert response.status_code == 409, (fault, response.text)
        assert not publishable["state"]["calls"]
        with company["factory"]() as session:
            session.get(m.Task, task.id).evidence = original
            saved = session.get(m.Execution, execution.id)
            saved.logs, saved.agent_id = logs, qa_id
            session.get(m.ModelRun, review.id).response = {"approved": True}
            session.get(m.ModelRun, author.id).status = "succeeded"
            session.get(m.Provider, provider.id).kind = "ollama"
            session.commit()


async def test_pause_during_publication_fences_external_writes_and_retains_recovery_state(
    http, company, publishable
):
    record = prepare(http, publishable)
    approve(http, record)
    publishable["state"]["fault"] = "paused"
    response = http.post(f"/publications/{record['id']}/publish")
    assert response.status_code == 409
    assert publishable["state"]["branch"] is None and publishable["state"]["pull"] is None
    with company["factory"]() as session:
        assert session.get(m.BusinessRecord, record["id"]).status == "needs_reconciliation"


@pytest.mark.parametrize("category", ["github_publication", "repository_change", "project"])
async def test_expired_approval_refuses_remote_writes(http, company, publishable, category):
    record = prepare(http, publishable)
    approve(http, record)
    with company["factory"]() as session:
        query = select(m.Approval).where(m.Approval.org_id == company["org"].id)
        if category != "project":
            query = query.where(m.Approval.category == category)
        else:
            query = query.where(m.Approval.category == "proposal")
        approvals = list(session.scalars(query))
        assert approvals
        for approval in approvals:
            approval.expires_at = now() - 1
        session.commit()
    before = len(publishable["state"]["calls"])
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    assert len(publishable["state"]["calls"]) == before
    if category == "github_publication":
        assert (
            http.post(
                f"/publications/{record['id']}/approve",
                json={"version": record["version"], "content_hash": record["data"]["manifest_hash"]},
            ).status_code
            == 409
        )


async def test_interrupted_request_lease_recovery_and_owner_only_authorization(http, company, publishable):
    from company_os.security import token_for

    record = prepare(http, publishable)
    approve(http, record)
    with company["factory"]() as session:
        saved = session.get(m.BusinessRecord, record["id"])
        saved.status = "publishing"
        saved.data = {**saved.data, "lease_token": "interrupted-worker-fixture", "lease_until": now() + 300}
        session.commit()
    assert http.post(f"/publications/{record['id']}/publish").status_code == 409
    assert publishable["state"]["branch"] is None
    with company["factory"]() as session:
        saved = session.get(m.BusinessRecord, record["id"])
        saved.data = {**saved.data, "lease_until": now() - 1}
        session.commit()
    assert http.post(f"/publications/{record['id']}/publish").status_code == 200
    with company["factory"]() as session:
        client = m.User(
            id=uid(),
            org_id=company["org"].id,
            role="client",
            client_id=company["client"].id,
            email="publication-client@fixture.invalid",
        )
        session.add(client)
        session.flush()
        token = token_for(client, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get("/operations/github").status_code == 403
    for action in ("approve", "publish", "feedback", "repairs"):
        assert http.post(f"/publications/{record['id']}/{action}", json={}).status_code == 403


async def test_exact_authorization_binds_manifest_task_revision_and_evidence(http, company, publishable):
    from copy import deepcopy

    record = prepare(http, publishable)
    approve(http, record)
    for changed in ("manifest", "task_version", "evidence"):
        with company["factory"]() as session:
            saved = session.get(m.BusinessRecord, record["id"])
            task = session.get(m.Task, publishable["task_id"])
            original_data, original_evidence = deepcopy(saved.data), deepcopy(task.evidence)
            original_version = task.version
            if changed == "manifest":
                data = deepcopy(saved.data)
                data["manifest"]["head_commit"] = "0" * 40
                saved.data = data
            elif changed == "task_version":
                task.version += 1
            else:
                task.evidence = {**task.evidence, "build_exit_code": 1}
            session.commit()
        before = len(publishable["state"]["calls"])
        assert http.post(f"/publications/{record['id']}/publish").status_code == 409
        assert len(publishable["state"]["calls"]) == before
        with company["factory"]() as session:
            session.get(m.BusinessRecord, record["id"]).data = original_data
            task = session.get(m.Task, publishable["task_id"])
            task.version, task.evidence = original_version, original_evidence
            session.commit()


@pytest.mark.parametrize(
    "path,content",
    [
        (".ENV", b"private=example"),
        ("binary.dat", b"\x00hidden"),
        ("image.dat", b"\xff\xfe"),
        (".GitHub/workflows/test.yml", b"privileged workflow"),
    ],
)
def test_unapproved_binary_secret_and_privileged_paths_are_refused(tmp_path, path, content):
    root = tmp_path / "path-scope-fixture"
    root.mkdir()
    git(root, "init")
    git(root, "config", "user.name", "Explicit fixture")
    git(root, "config", "user.email", "fixture@local.invalid")
    (root / "README.md").write_text("Harmless baseline\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Baseline")
    base = git(root, "rev-parse", "HEAD")
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    git(root, "add", ".")
    git(root, "commit", "-m", "Explicit rejected fixture")
    with pytest.raises(publication.PublicationError):
        publication.changes(root, base, git(root, "rev-parse", "HEAD"))


def test_canonical_remote_commit_is_a_real_git_object(tmp_path):
    root = tmp_path / "object-fixture"
    root.mkdir()
    git(root, "init")
    sha, body = publication.commit_spec(
        "a" * 40, "b" * 40, "fixture-publication", "fixture-task", "c" * 40, 1700000000
    )
    raw = f"tree {body['tree']}\nparent {body['parents'][0]}\nauthor Aiventra approved publication <aiventra@local.invalid> 1700000000 +0000\ncommitter Aiventra approved publication <aiventra@local.invalid> 1700000000 +0000\n\n{body['message']}".encode()
    candidate = root / "object.txt"
    candidate.write_bytes(raw)
    assert git(root, "hash-object", "-t", "commit", str(candidate)) == sha
    data = "café\n".encode()
    candidate.write_bytes(data)
    blob = git(root, "hash-object", "-w", str(candidate))
    assert git(root, "cat-file", "blob", blob, raw=True) == data
    assert git(root, "cat-file", "blob", blob) == "café"
