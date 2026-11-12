from company_os.models import Approval, Artifact, Meeting, ModelRun, Project, Proposal, Task, Workflow
from company_os.security import verify_audit
from company_os.workflows import tick
from sqlalchemy import select


async def consult(company):
    for _ in range(7):
        assert await tick(company["factory"])


async def test_a_consulting_records_evidence_and_blocks_implementation(company, requirement):
    await consult(company)
    with company["factory"]() as session:
        proposal = session.scalar(select(Proposal))
        assert proposal.status == "awaiting_approval"
        assert len(proposal.content["alternatives"]) == 3
        assert all(cost["recurring_micro"] is None for cost in proposal.content["cost_comparison"])
        assert session.scalar(select(Project)) is None
        assert session.scalar(select(Approval)) is None
        assert len(session.scalars(select(ModelRun)).all()) == 7
        assert session.scalar(select(Meeting)).mode == "mock"
        assert session.scalar(select(Workflow)).status == "completed"
        assert verify_audit(session, company["org"].id)["valid"]


async def approved(http, company):
    await consult(company)
    state = http.get("/state").json()
    proposal = state["proposals"][0]
    body = {
        "version": proposal["version"],
        "content_hash": proposal["content_hash"],
        "selection": proposal["content"]["recommendation"],
    }
    response = http.post(f"/proposals/{proposal['id']}/approve", json=body)
    assert response.status_code == 200, response.text
    return response.json(), proposal, body


async def test_b_approval_creates_assigned_plan_and_artifacts(company, http, requirement):
    project, proposal, body = await approved(http, company)
    assert len(http.get("/state").json()["dependencies"]) == 3
    duplicate = http.post(f"/proposals/{proposal['id']}/approve", json=body)
    assert duplicate.json()["id"] == project["id"]
    for _ in range(4):
        assert await tick(company["factory"])
    with company["factory"]() as session:
        tasks = session.scalars(select(Task)).all()
        assert len(tasks) == 4
        assert all(task.status == "completed" for task in tasks)
        assert len(session.scalars(select(Artifact)).all()) == 4
        assert len(session.scalars(select(Approval)).all()) == 1
        assert verify_audit(session, company["org"].id)["valid"]


async def test_stale_approval_and_material_revision_pause_project(company, http, requirement):
    project, proposal, body = await approved(http, company)
    response = http.post(
        f"/requirements/{requirement['id']}/clarify",
        json={"version": 1, "answers": {"region": "India"}, "rates": []},
    )
    assert response.status_code == 200
    assert http.post(f"/proposals/{proposal['id']}/approve", json=body).status_code == 409
    with company["factory"]() as session:
        assert session.get(Project, project["id"]).status == "scope_paused"
        assert session.get(Proposal, proposal["id"]).status == "superseded"


async def test_j_workflow_resume_does_not_repeat_completed_steps(company, requirement):
    for _ in range(3):
        await tick(company["factory"])
    # Each tick closes its Session, equivalent to worker restart at a committed checkpoint.
    with company["factory"]() as session:
        original_ids = {run.id for run in session.scalars(select(ModelRun)).all()}
    for _ in range(4):
        await tick(company["factory"])
    with company["factory"]() as session:
        runs = session.scalars(select(ModelRun)).all()
        assert len(runs) == 7
        assert original_ids.issubset({run.id for run in runs})
        assert len(session.scalars(select(Proposal)).all()) == 1


async def test_bounded_failed_agent_escalates(company, requirement):
    from company_os.models import Agent

    with company["factory"]() as session:
        agent = session.scalar(select(Agent).where(Agent.role == "Business Analyst"))
        agent.enabled = False
        session.commit()
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.scalar(select(Workflow))
        assert workflow.status == "needs_attention"
        assert workflow.attempts == 1
        assert "disabled" in workflow.last_error
