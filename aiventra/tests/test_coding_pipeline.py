import subprocess

import pytest
from company_os.config import settings
from company_os.db import now, uid
from company_os.engineering import candidate_tree, passed_tests, prepare_pull_request
from company_os.models import (
    Agent,
    Approval,
    Artifact,
    BusinessRecord,
    Execution,
    Project,
    Proposal,
    Requirement,
    Task,
)
from company_os.repositories import apply_files, git, worktree
from company_os.workflows import tick
from sqlalchemy import select


@pytest.mark.parametrize("baseline_success,baseline_exit", [(True, 0), (False, 0), (False, 1)])
@pytest.mark.parametrize("review_count", [1, 2])
async def test_c_isolated_patch_and_independent_fixture_review_cannot_certify_live_code(
    http, company, requirement, monkeypatch, baseline_success, baseline_exit, review_count
):
    for _ in range(7):
        await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    project = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": 1,
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    ).json()
    repo = settings().repository_root / "baseline"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("Test baseline repository\n")
    for args in (
        ["init"],
        ["config", "user.email", "test@local.invalid"],
        ["config", "user.name", "Test Fixture"],
        ["add", "README.md"],
        ["commit", "-m", "test baseline"],
    ):
        subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True, timeout=20)
    imported = http.post(
        "/repositories",
        json={"project_id": project["id"], "name": "Test baseline", "relative_path": "baseline"},
    )
    assert imported.status_code == 201, imported.text
    task = http.post(
        f"/projects/{project['id']}/coding",
        json={
            "repository_id": imported.json()["id"],
            "objective": "Create a decimal-safe quote calculation with regression tests",
            "acceptance": ["Decimal arithmetic preserves precision"],
            "mode": "mock",
            "test_suite": "python-unittest",
            "review_count": review_count,
        },
    ).json()
    assert (
        http.post(f"/tasks/{task['id']}/approve", json={"content_hash": task["approval_hash"]}).status_code
        == 200
    )

    async def runner_fixture(*_args, **_kwargs):
        return {
            "command": ["python", "-m", "unittest"],
            "environment": "MOCKED runner contract: not Docker evidence",
            "exit_code": baseline_exit,
            "logs": "MOCKED runner contract\nRan 1 test\nOK"
            if baseline_success
            else "MOCKED runner contract\nRan 0 tests\nOK",
        }

    monkeypatch.setattr("company_os.engineering.run_tests", runner_fixture)
    for _ in range(12):
        await tick(company["factory"])
    state = http.get("/state").json()
    executed = next(row for row in state["tasks"] if row["id"] == task["id"])
    workflow = next(row for row in state["workflows"] if row["task_id"] == task["id"])
    if not baseline_success:
        assert executed["status"] == "failed" and executed["evidence"].get("baseline_passed") is False, (
            workflow["last_error"]
        )
        assert not any(row["task_id"] == task["id"] for row in state["runs"])
        assert not any(row["task_id"] == task["id"] for row in state["artifacts"])
        return
    assert executed["status"] == "failed", workflow["last_error"]  # Fixture review cannot certify code.
    assert executed["evidence"]["reviewer_approved"] is False
    assert len(executed["evidence"]["reviews"]) == review_count
    assert all(
        row["diversity"] == "same_model_independent_context" for row in executed["evidence"]["reviews"]
    )
    assert not (repo / "quote.py").exists()
    workspace = settings().repository_root / ".worktrees" / project["id"] / task["id"]
    assert (workspace / "quote.py").exists()
    results = [row for row in state["executions"] if row["task_id"] == task["id"]]
    assert len(results) == 2
    assert all(row["agent_id"] != executed["assigned_agent_id"] for row in results)
    assert any(row["kind"] == "code_diff" and row["task_id"] == task["id"] for row in state["artifacts"])


def test_c_prepares_verified_candidate_as_unpublished_pull_request_draft(company, http, monkeypatch):
    from company_os.security import digest

    org_id, client_id, owner_id = company["org"].id, company["client"].id, company["owner"].id
    root = company["root"] / "sample-repository"
    root.mkdir()
    (root / "README.md").write_text("Harmless sample repository\n", encoding="utf-8")
    for args in (
        ["init"],
        ["config", "user.email", "test@local.invalid"],
        ["config", "user.name", "Test Fixture"],
        ["add", "README.md"],
        ["commit", "-m", "baseline"],
    ):
        subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True, timeout=20)
    baseline = git(root, "rev-parse", "HEAD")
    task_id = uid()
    workspace = company["root"] / "repositories" / ".worktrees" / "sample-project" / task_id
    assert worktree(root, workspace, task_id, baseline) == baseline
    apply_files(workspace, [{"path": "src/feature.py", "content": "def enabled():\n    return True\n"}])
    tree = candidate_tree(workspace)

    with company["factory"]() as session:
        agent = session.scalar(select(Agent).where(Agent.org_id == org_id, Agent.role == "Backend Developer"))
        requirement = Requirement(
            id=uid(), org_id=org_id, client_id=client_id, title="Sample change", text="Verify draft"
        )
        proposal = Proposal(
            id=uid(),
            org_id=org_id,
            requirement_id=requirement.id,
            version=1,
            content={"recommendation": "Sample"},
            content_hash=digest({"recommendation": "Sample"}),
        )
        session.add(requirement)
        session.flush()
        session.add(proposal)
        session.flush()
        approval = Approval(
            id=uid(),
            org_id=org_id,
            category="project",
            subject_id=proposal.id,
            subject_hash=proposal.content_hash,
            version=1,
            owner_id=owner_id,
            expires_at=now() + 3600,
        )
        session.add(approval)
        session.flush()
        project = Project(
            id=uid(),
            org_id=org_id,
            client_id=client_id,
            proposal_id=proposal.id,
            approval_id=approval.id,
            name="Sample project",
            selected_alternative="Sample",
        )
        task = Task(
            id=task_id,
            org_id=org_id,
            project_id=project.id,
            assigned_agent_id=agent.id,
            objective="Add a harmless sample feature",
            kind="coding",
            payload={"mode": "mock"},
            evidence={
                "baseline_commit": baseline,
                "execution_id": uid(),
                "reviews": [{"review_run_id": uid()}],
            },
        )
        session.add_all([project, task])
        session.flush()
        prepare_pull_request(session, task, project, agent, workspace, tree)
        session.commit()

        draft = task.evidence["pull_request"]
        record = session.scalar(
            select(BusinessRecord).where(
                BusinessRecord.project_id == project.id,
                BusinessRecord.kind == "pull_request_draft",
                BusinessRecord.title == task.objective,
            )
        )
        assert draft["publication"] == "prepared_not_published"
        assert draft["mode"] == "mock"
        assert "deterministic test adapter" in draft["body"]
        assert draft["base_commit"] == baseline and draft["head_commit"] != baseline
        assert draft["branch"] == f"aiventra/{task_id}"
        assert record.data["head_commit"] == draft["head_commit"]
        artifact = session.get(Artifact, draft["artifact_id"])
        assert artifact.kind == "pull_request_draft" and "src/feature.py" in artifact.content
        assert "deterministic test adapter" in artifact.content
        execution_id = uid()
        session.add(
            Execution(
                id=execution_id,
                org_id=org_id,
                task_id=task_id,
                agent_id=agent.id,
                workspace=str(workspace),
                command=["python", "-m", "unittest"],
                environment="dedicated Docker broker",
                commit_hash=baseline,
                status="running",
            )
        )
        session.commit()

    assert not (root / "src/feature.py").exists()
    assert git(workspace, "rev-parse", "HEAD") == draft["head_commit"]

    async def recovered_result(_job_id):
        return {
            "status": "interrupted",
            "exit_code": 125,
            "command": ["python", "-m", "unittest"],
            "environment": "dedicated Docker broker",
            "build": {"exit_code": 0, "logs": "build completed"},
            "logs": "Captured before broker restart",
        }

    monkeypatch.setattr("company_os.sandbox.stored_result", recovered_result)
    reconciled = http.post(f"/executions/{execution_id}/reconcile")
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["status"] == "interrupted"
    assert reconciled.json()["exit_code"] == 125
    assert "Captured before broker restart" in reconciled.json()["logs"]


def test_c_test_pass_requires_nonempty_suite_and_successful_build():
    result = {"exit_code": 0, "logs": "Ran 1 test\nOK", "build": {"exit_code": 0}}
    assert passed_tests(result, "python-unittest")
    assert not passed_tests({**result, "build": {"exit_code": 1}}, "python-unittest")
    assert not passed_tests({**result, "logs": "Ran 0 tests\nOK"}, "python-unittest")
