from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from company_os import models as m
from company_os.db import now
from company_os.organization import agent_for
from company_os.security import digest
from company_os.workflows import claim, schedule, tick
from sqlalchemy import select


async def project_plan(http, company, requirement):
    for _ in range(7):
        assert await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    response = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": proposal["version"],
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert response.status_code == 200, response.text
    project = response.json()
    plan = http.get(f"/projects/{project['id']}/staffing").json()
    return project, plan


def revise(http, plan, **changes):
    content = {**deepcopy(plan["content"]), **changes}
    response = http.patch(f"/staffing/{plan['id']}", json={"version": plan["version"], "content": content})
    assert response.status_code == 200, response.text
    return response.json()


def approve(http, plan):
    response = http.post(
        f"/staffing/{plan['id']}/approve",
        json={"version": plan["version"], "content_hash": plan["content_hash"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_plan_reuses_foundation_exact_approval_and_real_fixture_artifacts(http, company, requirement):
    project, plan = await project_plan(http, company, requirement)
    assert plan["status"] == "draft" and plan["content"]["mode"] == "live"
    assert plan["estimated_micro"] is None
    assert len(plan["content"]["foundation_task_ids"]) == 4 and not plan["tasks"]
    plan = revise(http, plan, mode="mock", concurrency=2)
    stale = http.post(f"/staffing/{plan['id']}/approve", json={"version": 1, "content_hash": "a" * 64})
    assert stale.status_code == 409
    active = approve(http, plan)
    assert len(active["tasks"]) == len(plan["content"]["tasks"])
    assert {row["id"] for row in approve(http, plan)["tasks"]} == {row["id"] for row in active["tasks"]}
    for _ in range(20):
        await tick(company["factory"])
    with company["factory"]() as session:
        tasks = list(session.scalars(select(m.Task).where(m.Task.project_id == project["id"])))
        assert all(task.status == "completed" for task in tasks if task.kind == "document")
        assert all(task.status == "awaiting_repository" for task in tasks if task.kind == "coding")
        assert (
            session.scalar(
                select(m.StaffingRevision).where(
                    m.StaffingRevision.plan_id == plan["id"], m.StaffingRevision.version == 2
                )
            ).content_hash
            == plan["content_hash"]
        )
        assert (
            session.scalar(select(m.Budget).where(m.Budget.scope == f"staffing:{plan['id']}")).spent_micro
            == 0
        )


async def test_local_single_worker_draft_is_approvable_and_limits_remain_strict(
    http, company, requirement, monkeypatch
):
    from company_os.config import settings

    monkeypatch.setattr(settings(), "scheduler_concurrency", 1)
    _, plan = await project_plan(http, company, requirement)
    assert plan["content"]["concurrency"] == 1
    invalid = http.patch(
        f"/staffing/{plan['id']}",
        json={
            "version": plan["version"],
            "content": {**plan["content"], "concurrency": 2},
        },
    )
    assert invalid.status_code == 422
    assert "exceeds configured scheduler concurrency" in invalid.text
    revised = revise(http, plan, mode="mock")
    assert approve(http, revised)["content"]["concurrency"] == 1


async def test_rules_identify_ui_code_data_and_integrations(http, company, requirement):
    with company["factory"]() as session:
        row = session.get(m.Requirement, requirement["id"])
        row.text = (
            "Build web dashboard frontend and backend API with PostgreSQL database and payment integration"
        )
        session.commit()
    _, plan = await project_plan(http, company, requirement)
    assert {"design", "frontend", "backend", "data", "integration", "security"}.issubset(
        {row["key"] for row in plan["content"]["tasks"]}
    )
    assert sum(row["slots"] for row in plan["content"]["allocations"]) <= 16


async def test_invalid_cycles_caps_foreign_allocations_and_stale_revisions(http, company, requirement):
    _, plan = await project_plan(http, company, requirement)
    for bad in ("cycle", "budget", "agent", "foundation", "concurrency"):
        content = deepcopy(plan["content"])
        if bad == "cycle":
            content["tasks"][0]["depends_on"] = [content["tasks"][0]["key"]]
        elif bad == "budget":
            content["tasks"][0]["budget_micro"] = 10**10
        elif bad == "agent":
            content["allocations"][0]["agent_id"] = "foreign-agent"
        elif bad == "foundation":
            content["foundation_task_ids"] = []
        else:
            content["concurrency"] = 16
        assert (
            http.patch(
                f"/staffing/{plan['id']}", json={"version": plan["version"], "content": content}
            ).status_code
            == 422
        )
    saved = revise(http, plan, concurrency=1)
    assert saved["version"] == 2
    assert (
        http.patch(f"/staffing/{plan['id']}", json={"version": 1, "content": plan["content"]}).status_code
        == 409
    )
    assert http.get("/projects/foreign/staffing").status_code == 404


async def test_pause_resume_retains_checkpoints_and_rejects_uncertain_usage(http, company, requirement):
    _, plan = await project_plan(http, company, requirement)
    plan = approve(http, revise(http, plan, mode="mock"))
    await tick(company["factory"])
    with company["factory"]() as session:
        schedule(session)
    paused = http.post(f"/staffing/{plan['id']}/control", json={"action": "pause"})
    assert paused.status_code == 200, paused.text
    assert paused.json()["status"] == "paused"
    assert all(row["status"] == "paused" for row in paused.json()["tasks"])
    resumed = http.post(f"/staffing/{plan['id']}/control", json={"action": "resume"})
    assert resumed.status_code == 200, resumed.text
    workflows = resumed.json()["workflows"]
    workflow = workflows[0]
    assert http.post(f"/workflows/{workflow['id']}/control", json={"action": "pause"}).status_code == 200
    with company["factory"]() as session:
        model = session.scalar(select(m.ModelConfig))
        task = session.get(m.Task, workflow["task_id"])
        session.add(
            m.ModelRun(
                org_id=task.org_id,
                workflow_id=workflow["id"],
                task_id=task.id,
                agent_id=task.assigned_agent_id,
                model_id=model.id,
                step_name="document",
                attempt=1,
                status="uncertain",
                routing_reason="test interrupted usage",
            )
        )
        session.commit()
    assert http.post(f"/workflows/{workflow['id']}/control", json={"action": "resume"}).status_code == 409


async def test_distributed_claims_obey_global_agent_and_plan_limits(http, company, requirement, monkeypatch):
    _, plan = await project_plan(http, company, requirement)
    for _ in range(4):
        await tick(company["factory"])
    plan = approve(http, revise(http, plan, mode="mock", concurrency=1))
    with company["factory"]() as session:
        schedule(session)

    def compete(_):
        with company["factory"]() as session:
            row = claim(session)
            return row.id if row else None

    with ThreadPoolExecutor(max_workers=4) as pool:
        winners = [value for value in pool.map(compete, range(4)) if value]
    assert len(winners) == 1
    with company["factory"]() as session:
        running = session.get(m.Workflow, winners[0])
        assert running.capacity_agents and running.lease_until > now()
        running.lease_until = now() - 1
        session.commit()
        reclaimed = claim(session)
        assert reclaimed.id == winners[0]
        assert reclaimed.lease_token != running.lease_token or reclaimed.lease_until > now()


async def test_missing_provider_waits_without_reservations(http, company, requirement):
    _, plan = await project_plan(http, company, requirement)
    for _ in range(4):
        await tick(company["factory"])
    plan = approve(http, plan)
    await tick(company["factory"])
    current = http.get(f"/projects/{plan['project_id']}/staffing").json()
    assert any(row["status"] == "waiting_for_free_provider" for row in current["tasks"])
    assert current["budget"]["spent_micro"] == current["budget"]["reserved_micro"] == 0


async def test_reassignment_uses_approved_department_and_saved_history(http, company, requirement):
    _, plan = await project_plan(http, company, requirement)
    with company["factory"]() as session:
        alternate = agent_for(session, company["org"].id, "Requirements Analyst").id
    content = deepcopy(plan["content"])
    content["allocations"].append({"agent_id": alternate, "slots": 1})
    plan = revise(http, plan, **content)
    plan = approve(http, plan)
    task = next(row for row in plan["tasks"] if row["payload"]["plan_key"] == "requirements")
    response = http.post(
        f"/tasks/{task['id']}/assign",
        json={"version": 1, "agent_id": alternate, "reason": "Owner selected requirements specialist"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert (
        http.post(
            f"/tasks/{task['id']}/assign", json={"version": 1, "agent_id": alternate, "reason": "stale retry"}
        ).status_code
        == 409
    )
    current = http.get(f"/projects/{plan['project_id']}/staffing").json()
    assert current["history"][0]["agent_id"] == alternate


async def test_changed_approval_fences_claims(http, company, requirement):
    _, plan = await project_plan(http, company, requirement)
    for _ in range(4):
        await tick(company["factory"])
    plan = approve(http, revise(http, plan, mode="mock"))
    with company["factory"]() as session:
        schedule(session)
        saved = session.get(m.StaffingPlan, plan["id"])
        saved.content = {**saved.content, "concurrency": 4}
        assert digest(saved.content) != saved.content_hash
        session.commit()
        assert claim(session) is None
