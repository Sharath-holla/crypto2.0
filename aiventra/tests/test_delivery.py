"""Real persisted final-review orchestration using explicitly deterministic adapters."""

import hashlib
from uuid import uuid4

import pytest
from company_os import delivery
from company_os import models as m
from company_os.db import now, uid
from company_os.security import digest, token_for
from company_os.workflows import tick
from sqlalchemy import select
from test_agent_planning import draft_project
from test_staffing import approve, revise


async def ready_project(http, company, requirement):
    project, plan = await draft_project(http, company, requirement)
    approve(http, revise(http, plan, mode="mock"))
    with company["factory"]() as session:
        for task in session.scalars(select(m.Task).where(m.Task.project_id == project["id"])):
            if task.status == "paused":
                task.status = "ready"
                task.payload = {**task.payload, "mode": "mock"}
        session.commit()
    for _ in range(20):
        await tick(company["factory"])
    response = http.get(f"/projects/{project['id']}/delivery-readiness?mode=mock")
    assert response.status_code == 200
    evidence = response.json()
    assert evidence["ready"], evidence["blockers"]
    return project, evidence


def start(http, project, evidence, **overrides):
    return http.post(
        f"/projects/{project['id']}/final-review",
        json={
            "request_id": str(uuid4()),
            "source_hash": evidence["source_hash"],
            "mode": "mock",
            **overrides,
        },
    )


async def test_five_saved_reviews_handoffs_pause_restart_and_no_fixture_delivery(http, company, requirement):
    project, evidence = await ready_project(http, company, requirement)
    assert evidence["manifest"]["sources"] and evidence["manifest"]["acceptance"]
    with company["factory"]() as session:
        for source in evidence["manifest"]["sources"]:
            recovered = "\n\n".join(
                evidence["manifest"]["content_blocks"][key] for key in source["paragraphs"]
            )
            assert recovered == session.get(m.Artifact, source["artifact_id"]).content
    live = http.get(f"/projects/{project['id']}/delivery-readiness").json()
    assert not live["ready"] and any("fixture" in item for item in live["blockers"])
    assert start(http, project, live, mode="live").status_code == 409
    request_id = str(uuid4())
    response = start(http, project, evidence, request_id=request_id)
    assert response.status_code == 201, response.text
    workflow_id = response.json()["workflow"]["id"]
    record_id = response.json()["review"]["id"]
    assert start(http, project, evidence, request_id=request_id).json()["work"]["id"] == request_id
    assert start(http, project, evidence).status_code == 409  # No duplicate active chain.
    assert start(http, project, evidence, request_id=request_id, budget_micro=600000).status_code == 409
    assert http.patch(f"/records/{record_id}", json={"version": 1, "status": "reviewed"}).status_code == 409
    assert await tick(company["factory"])
    paused = http.post(f"/workflows/{workflow_id}/control", json={"action": "pause"})
    assert paused.status_code == 200
    assert not await tick(company["factory"])
    assert http.post(f"/workflows/{workflow_id}/control", json={"action": "resume"}).status_code == 200
    for _ in range(4):
        company["factory"].kw["bind"].dispose()
        assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, workflow_id)
        record = session.get(m.BusinessRecord, record_id)
        work = session.get(m.AgentWork, request_id)
        assert workflow.status == "completed" and workflow.step == 5
        assert record.status == "fixture_reviewed" and len(record.data["reviews"]) == 5
        assert [row["role"] for row in record.data["reviews"]] == delivery.ROLES
        assert work.result["delivery_released"] is work.result["client_accepted"] is False
        assert session.get(m.Project, project["id"]).status == "active"
        for review in record.data["reviews"]:
            artifact = session.get(m.Artifact, review["artifact_id"])
            run = session.get(m.ModelRun, review["run_id"])
            assert artifact.sha256 == review["sha256"] and run.cost_micro == 0
            assert run.status == "succeeded" and review["mode"] == "mock"
            assert "deterministic" in review["summary"].lower()
        messages = list(session.scalars(select(m.Message).where(m.Message.correlation_id == request_id)))
        assert len(messages) == 4 and all(row.status == "acknowledged" for row in messages)
        assert not session.scalar(select(m.Approval).where(m.Approval.category == "delivery"))


@pytest.mark.parametrize("change", ["document", "approval", "task", "budget"])
async def test_changed_evidence_fences_next_review(http, company, requirement, change):
    project, evidence = await ready_project(http, company, requirement)
    assert start(http, project, evidence, source_hash="a" * 64).status_code == 409
    response = start(http, project, evidence)
    assert response.status_code == 201
    assert await tick(company["factory"])
    with company["factory"]() as session:
        if change == "document":
            task = session.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
            artifact = session.get(m.Artifact, task.evidence["artifact_id"])
            artifact.content += " Changed after first review"
        elif change == "approval":
            plan = session.scalar(select(m.StaffingPlan).where(m.StaffingPlan.project_id == project["id"]))
            approval = session.scalar(select(m.Approval).where(m.Approval.subject_id == plan.id))
            approval.expires_at = now() - 1
        elif change == "task":
            task = session.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
            task.version += 1
        else:
            budget = session.scalar(select(m.Budget).where(m.Budget.scope == f"project:{project['id']}"))
            budget.limit_micro += 1
        session.commit()
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        record = session.get(m.BusinessRecord, response.json()["review"]["id"])
        assert workflow.status == "needs_attention" and workflow.step == 1
        assert record.status == "reviewing" and len(record.data["reviews"]) == 1


@pytest.mark.parametrize("invalid", ["finding", "missing_criterion"])
async def test_findings_or_incomplete_review_never_release(http, company, requirement, monkeypatch, invalid):
    project, evidence = await ready_project(http, company, requirement)
    original = delivery.execute

    async def review(*args, **kwargs):
        result = await original(*args, **kwargs)
        if invalid == "finding":
            return result.model_copy(update={"findings": ["Requirement evidence needs owner correction"]})
        return result.model_copy(update={"checked_criteria": [999]})

    monkeypatch.setattr(delivery, "execute", review)
    response = start(http, project, evidence)
    assert response.status_code == 201
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        record = session.get(m.BusinessRecord, response.json()["review"]["id"])
        assert record.status == ("changes_required" if invalid == "finding" else "reviewing")
        assert workflow.status == ("completed" if invalid == "finding" else "needs_attention")
        assert len(record.data["reviews"]) == (1 if invalid == "finding" else 0)
        assert session.get(m.Project, project["id"]).status == "active"


async def test_readiness_rejects_missing_checkpoint_and_coding_fixtures(http, company, requirement):
    project, evidence = await ready_project(http, company, requirement)
    with company["factory"]() as session:
        task = session.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
        checkpoint = session.scalar(
            select(m.WorkflowStep).join(m.Workflow).where(m.Workflow.task_id == task.id)
        )
        checkpoint.result = {}
        session.commit()
    changed = http.get(f"/projects/{project['id']}/delivery-readiness?mode=mock").json()
    assert not changed["ready"] and any("checkpoint" in item for item in changed["blockers"])
    assert start(http, project, evidence).status_code == 409
    with company["factory"]() as session:
        task = session.get(m.Task, task.id)
        task.kind = "coding"
        session.commit()
    changed = http.get(f"/projects/{project['id']}/delivery-readiness?mode=mock").json()
    assert any("cannot certify engineering" in item for item in changed["blockers"])
    assert http.get("/projects/foreign/delivery-readiness").status_code == 404
    assert start(http, {"id": "foreign"}, evidence).status_code == 404


async def test_cancel_preserves_checkpoints_and_allows_fresh_review(http, company, requirement):
    project, evidence = await ready_project(http, company, requirement)
    response = start(http, project, evidence)
    assert response.status_code == 201
    assert await tick(company["factory"])
    work_id = response.json()["work"]["id"]
    assert http.post(f"/agent-work/{work_id}/cancel").status_code == 200
    assert not await tick(company["factory"])
    with company["factory"]() as session:
        record = session.get(m.BusinessRecord, response.json()["review"]["id"])
        assert record.status == "cancelled" and len(record.data["reviews"]) == 1
        assert session.get(m.AgentWork, work_id).result["delivery_released"] is False
    assert start(http, project, evidence).status_code == 201


@pytest.mark.parametrize("role", ["client", "foreign_owner"])
async def test_final_review_owner_and_tenant_scope(http, company, requirement, role):
    project, evidence = await ready_project(http, company, requirement)
    with company["factory"]() as session:
        org_id = company["org"].id
        if role == "foreign_owner":
            other = m.Organization(id=uid(), name="Other organization")
            session.add(other)
            session.flush()
            org_id = other.id
        user = m.User(
            id=uid(), org_id=org_id, email=f"{role}@test", role="client" if role == "client" else "owner"
        )
        session.add(user)
        session.flush()
        token = token_for(user, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    expected = 403 if role == "client" else 404
    assert http.get(f"/projects/{project['id']}/delivery-readiness").status_code == expected
    assert start(http, project, evidence).status_code == expected


async def test_disabled_reviewer_and_oversized_evidence_block_review(http, company, requirement):
    project, evidence = await ready_project(http, company, requirement)
    with company["factory"]() as session:
        agent = session.scalar(select(m.Agent).where(m.Agent.role == "CFO"))
        agent.enabled = False
        session.commit()
    assert start(http, project, evidence).status_code == 409
    with company["factory"]() as session:
        task = session.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
        artifact = session.get(m.Artifact, task.evidence["artifact_id"])
        artifact.content += "x" * 20000
        artifact.sha256 = hashlib.sha256(artifact.content.encode()).hexdigest()
        task.evidence = {**task.evidence, "sha256": artifact.sha256}
        checkpoint = session.scalar(
            select(m.WorkflowStep).join(m.Workflow).where(m.Workflow.task_id == task.id)
        )
        checkpoint.result = task.evidence
        session.commit()
    response = http.get(f"/projects/{project['id']}/delivery-readiness?mode=mock").json()
    assert not response["ready"]
    assert (
        "Evidence exceeds the bounded review context; partition the project before review"
        in response["blockers"]
    )
    assert (
        "Project manifest exceeds the bounded review context; partition before review" in response["blockers"]
    )
    assert start(http, project, response).status_code == 409
    with company["factory"]() as session:
        assert session.get(m.Artifact, artifact.id).content == artifact.content


async def test_source_changed_during_inference_cannot_publish_review(http, company, requirement, monkeypatch):
    project, evidence = await ready_project(http, company, requirement)
    original = delivery.execute

    async def changed(session, *args, **kwargs):
        result = await original(session, *args, **kwargs)
        with company["factory"]() as competing:
            task = competing.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
            task.payload = {**task.payload, "fixture_change": "changed while provider was executing"}
            competing.commit()
        return result

    monkeypatch.setattr(delivery, "execute", changed)
    response = start(http, project, evidence)
    assert response.status_code == 201
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        record = session.get(m.BusinessRecord, response.json()["review"]["id"])
        assert workflow.status == "needs_attention" and workflow.step == 0
        assert record.data["reviews"] == []
        assert not session.scalar(select(m.Artifact).where(m.Artifact.kind == "delivery_review"))
        assert digest(record.data["manifest"]) == evidence["source_hash"]
