"""Durable planning integration with explicitly labeled deterministic adapters."""

from uuid import uuid4

import pytest
from company_os import models as m
from company_os.workflows import tick
from sqlalchemy import select


async def draft_project(http, company, requirement):
    for _ in range(7):
        await tick(company["factory"])
    proposal = next(
        row for row in http.get("/state").json()["proposals"] if row["requirement_id"] == requirement["id"]
    )
    response = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": proposal["version"],
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert response.status_code == 200
    project = response.json()
    # Keep automatic foundation work out of this fixture's three-step order.
    with company["factory"]() as session:
        for task in session.scalars(select(m.Task).where(m.Task.project_id == project["id"])):
            task.status = "paused"
        session.commit()
    plan = http.get(f"/projects/{project['id']}/staffing").json()
    return project, plan


def start(http, project, plan, **overrides):
    return http.post(
        "/agent-planning",
        json={
            "request_id": str(uuid4()),
            "project_id": project["id"],
            "plan_version": plan["version"],
            "plan_hash": plan["content_hash"],
            "objective": "Create an evidence-based architecture and delivery plan",
            "mode": "mock",
            **overrides,
        },
    )


async def test_saved_handoffs_restart_draft_and_exact_staffing_approval(http, company, requirement):
    project, plan = await draft_project(http, company, requirement)
    request_id = str(uuid4())
    response = start(http, project, plan, request_id=request_id)
    assert response.status_code == 201, response.text
    assert start(http, project, plan, request_id=request_id).json()["work"]["id"] == request_id
    assert (
        start(
            http, project, plan, request_id=request_id, objective="Different planning objective"
        ).status_code
        == 409
    )
    workflow_id = response.json()["workflow"]["id"]
    for index in range(3):
        assert await tick(company["factory"])
        # New connections after each durable checkpoint, without clearing database records.
        company["factory"].kw["bind"].dispose()
        with company["factory"]() as session:
            assert session.get(m.Workflow, workflow_id).step == index + 1
    state = http.get("/state").json()
    work = next(w for w in state["agent_work"] if w["id"] == request_id)
    assert len(work["result"]["document_ids"]) == 3 and work["result"]["approval_required"]
    assert work["result"]["mode"] == "mock"
    handoffs = [row for row in state["messages"] if row["correlation_id"] == request_id]
    assert len(handoffs) == 2 and all(row["status"] == "acknowledged" for row in handoffs)
    assert all(row["content"]["artifact_id"] in work["result"]["document_ids"] for row in handoffs)
    revised = http.get(f"/projects/{project['id']}/staffing").json()
    assert revised["version"] == plan["version"] + 1 and revised["status"] == "draft"
    assert not revised["tasks"] and revised["content"]["planner"] == f"agent-chain:{request_id}"
    assert (
        http.post(
            f"/staffing/{plan['id']}/approve",
            json={
                "version": plan["version"],
                "content_hash": plan["content_hash"],
            },
        ).status_code
        == 409
    )
    # Owner may edit the generated draft, retaining its source provenance.
    edited = http.patch(
        f"/staffing/{plan['id']}", json={"version": revised["version"], "content": revised["content"]}
    )
    assert edited.status_code == 200, edited.text
    current = edited.json()
    approved = http.post(
        f"/staffing/{plan['id']}/approve",
        json={
            "version": current["version"],
            "content_hash": current["content_hash"],
        },
    )
    assert approved.status_code == 200 and len(approved.json()["tasks"]) == 1


async def test_changed_draft_fences_planning_without_overwrite(http, company, requirement):
    project, plan = await draft_project(http, company, requirement)
    response = start(http, project, plan)
    assert response.status_code == 201
    assert await tick(company["factory"])
    edited = http.patch(
        f"/staffing/{plan['id']}", json={"version": plan["version"], "content": plan["content"]}
    )
    assert edited.status_code == 200
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        assert workflow.status == "needs_attention" and workflow.step == 1
        assert session.get(m.StaffingPlan, plan["id"]).content_hash == edited.json()["content_hash"]
    assert start(http, project, plan).status_code == 409


async def test_no_provider_waits_without_fake_documents_or_plan_revision(http, company, requirement):
    project, plan = await draft_project(http, company, requirement)
    response = start(http, project, plan, mode="live")
    assert response.status_code == 201
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        assert workflow.status == "waiting_for_free_provider" and workflow.step == 0
        assert not session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
        assert session.get(m.StaffingPlan, plan["id"]).version == plan["version"]


@pytest.mark.parametrize("invalid", ["cycle", "model", "role", "tools"])
async def test_invalid_generated_plan_does_not_complete_checkpoint(
    http, company, requirement, monkeypatch, invalid
):
    from company_os import gateway

    project, plan = await draft_project(http, company, requirement)
    response = start(http, project, plan)
    workflow_id = response.json()["workflow"]["id"]
    original = gateway.fixture

    def invalid_plan(schema, context):
        answer = original(schema, context)
        if schema == "ProjectPlanResult":
            task = answer.data["tasks"][0]
            if invalid == "cycle":
                task["depends_on"] = [task["key"]]
            elif invalid == "model":
                task["recommended_model_id"] = "unknown-model"
            elif invalid == "role":
                task["role"] = "CEO"
            else:
                task["required_tools"] = ["deploy"]
        return answer

    monkeypatch.setattr(gateway, "fixture", invalid_plan)
    for _ in range(3):
        assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, workflow_id)
        assert workflow.step == 2 and workflow.status != "completed"
        assert not session.scalar(
            select(m.WorkflowStep).where(
                m.WorkflowStep.workflow_id == workflow_id, m.WorkflowStep.name == "planning_2"
            )
        )
        assert session.get(m.StaffingPlan, plan["id"]).version == plan["version"]


@pytest.mark.usefixtures("contract_inference")
async def test_local_admission_busy_does_not_spend_or_consume_attempt(
    http, company, requirement, monkeypatch
):
    from company_os.config import settings
    from company_os.db import now, uid

    monkeypatch.setattr(settings(), "ollama_context_tokens", 32768)
    project, plan = await draft_project(http, company, requirement)
    with company["factory"]() as session:
        provider = m.Provider(
            id=uid(),
            org_id=company["org"].id,
            name="Fixture local",
            kind="ollama",
            base_url="http://localhost:11434",
            credential_env="",
        )
        session.add(provider)
        session.flush()
        model = m.ModelConfig(
            id=uid(),
            org_id=provider.org_id,
            provider_id=provider.id,
            identifier="fixture",
            capabilities=["structured"],
            quality=95,
            context_tokens=32768,
            sensitivity="confidential",
        )
        session.add(model)
        session.flush()
        agent = session.scalar(select(m.Agent).where(m.Agent.role == "CEO"))
        occupied = m.Workflow(
            id=uid(),
            org_id=provider.org_id,
            kind="diagnostic",
            mode="live",
            status="running",
            lease_until=now() + 180,
            lease_token=uid(),
            capacity_agents=[agent.id],
        )
        session.add(occupied)
        session.flush()
        session.add(
            m.ModelRun(
                org_id=provider.org_id,
                workflow_id=occupied.id,
                agent_id=agent.id,
                model_id=model.id,
                step_name="fixture-occupied",
                attempt=1,
                routing_reason="Fixture",
            )
        )
        session.commit()
        model_id = model.id
    response = start(http, project, plan, mode="live", model_override=model_id)
    assert response.status_code == 201
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response.json()["workflow"]["id"])
        assert workflow.status == "queued" and workflow.attempts == 0 and workflow.step == 0
        assert "local inference slot" in workflow.last_error
        assert not session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
