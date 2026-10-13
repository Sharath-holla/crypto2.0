"""Real SQLite/API integration; no provider entitlement or network is mocked here."""

from uuid import uuid4

import pytest
from company_os import models as m
from company_os.project_setup import LeadAnalysis
from company_os.providers import FreeProviderUnavailable
from company_os.security import token_for
from company_os.workflows import claim, consulting_step
from sqlalchemy import select


def form(company, **changes):
    return {
        "client_id": company["client"].id,
        "title": "Wizard integration fixture",
        "text": "Build an accessible project tracker with persisted requirements and independent QA.",
        **changes,
    }


def create(http, company, **changes):
    response = http.post(
        "/project-drafts", json={"request_id": str(uuid4()), "form": form(company, **changes)}
    )
    assert response.status_code == 201, response.text
    return response.json()


def command(row, **extra):
    return {"request_id": str(uuid4()), "version": row["version"], **extra}


def test_draft_versions_retry_and_connection_recovery(http, company):
    body = {"request_id": str(uuid4()), "form": form(company)}
    first = http.post("/project-drafts", json=body).json()
    assert http.post("/project-drafts", json=body).json()["id"] == first["id"]
    saved = command(first, form=form(company, step=2))
    second = http.patch(f"/project-drafts/{first['id']}", json=saved)
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    assert http.patch(f"/project-drafts/{first['id']}", json=saved).json()["version"] == 2
    assert (
        http.patch(f"/project-drafts/{first['id']}", json=command(first, form=form(company))).status_code
        == 409
    )
    saved["form"]["title"] = "Changed payload"
    assert http.patch(f"/project-drafts/{first['id']}", json=saved).status_code == 409
    company["factory"].kw["bind"].dispose()
    recovered = http.get(f"/project-drafts/{first['id']}").json()
    assert recovered["data"]["form"]["step"] == 2
    assert recovered["lead_status"]["state"] == "UNAVAILABLE_FAVORITE"
    assert "requests" not in recovered["data"]
    assert http.patch(f"/records/{first['id']}", json={"version": 2, "status": "reviewed"}).status_code == 409


@pytest.mark.parametrize(
    "name,content,status",
    [
        ("brief.pdf", b"%PDF", 422),
        ("secret.txt", b"private", 422),
        ("brief.txt", b"a" * 16385, 413),
        ("brief.txt", b"\xff", 422),
        ("brief.txt", b"\x00", 422),
        ("brief.json", b"not json", 422),
    ],
)
def test_upload_rejects_unsupported_files(http, company, name, content, status):
    row = create(http, company)
    result = http.post(
        f"/project-drafts/{row['id']}/attachments", files={"file": (name, content)}, data=command(row)
    )
    assert result.status_code == status, result.text
    assert http.get(f"/project-drafts/{row['id']}").json()["version"] == 1


async def test_upload_intake_waits_without_provider_and_survives_restart(http, company):
    row = create(http, company)
    envelope = command(row)
    files = {"file": ("brief.md", b"# Requirements\nAccessible tracker with saved documents")}
    uploaded = http.post(f"/project-drafts/{row['id']}/attachments", files=files, data=envelope)
    assert uploaded.status_code == 200, uploaded.text
    row = uploaded.json()
    assert row["data"]["attachments"][0]["parsed"]
    assert (
        http.post(f"/project-drafts/{row['id']}/attachments", files=files, data=envelope).json()["version"]
        == 2
    )
    envelope = command(row)
    response = http.post(f"/project-drafts/{row['id']}/submit", json=envelope)
    assert response.status_code == 200, response.text
    row = response.json()
    assert http.post(f"/project-drafts/{row['id']}/submit", json=envelope).json()["id"] == row["id"]
    with company["factory"]() as session:
        assert session.get(m.Requirement, row["data"]["requirement_id"]).mode == "live"
        workflow = claim(session)
        with pytest.raises(FreeProviderUnavailable) as caught:
            await consulting_step(session, workflow, workflow.lease_token)
        assert caught.value.context["selection_reason"]
        assert not session.scalar(select(m.ModelRun))
        assert not session.scalar(select(m.Project))
        assert (
            session.scalar(select(m.BusinessRecord).where(m.BusinessRecord.kind == "knowledge"))
            .data["trust"]
            .startswith("untrusted")
        )
    company["factory"].kw["bind"].dispose()
    assert http.get(f"/project-drafts/{row['id']}").json()["data"]["attachments"]


def test_manual_plan_is_owner_authored_and_requires_exact_approval(http, company):
    row = create(http, company, planning_mode="manual")
    row = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    assert row["workflow"]["status"] == "paused"
    body = command(
        row,
        architecture="SQLite application with isolated engineering and independent QA",
        milestones=["Build tracker", "Validate and review"],
        criteria=["Records survive restart"],
    )
    response = http.post(f"/project-drafts/{row['id']}/manual-plan", json=body)
    assert response.status_code == 200, response.text
    row = response.json()
    assert (
        http.post(f"/project-drafts/{row['id']}/manual-plan", json=body).json()["version"] == row["version"]
    )
    with company["factory"]() as session:
        proposal = session.get(m.Proposal, row["data"]["manual_proposal_id"])
        assert proposal.content["authorship"] == "owner"
        assert not proposal.content["specialist_contributions"]
        assert not session.scalar(select(m.ModelRun))
        assert not session.scalar(select(m.Project))
        approval = {
            "version": proposal.version,
            "content_hash": proposal.content_hash,
            "selection": "Owner-authored plan",
        }
    bad = http.post(f"/proposals/{proposal.id}/approve", json={**approval, "content_hash": "0" * 64})
    assert bad.status_code == 409, bad.text
    result = http.post(f"/proposals/{proposal.id}/approve", json=approval)
    assert result.status_code == 200, result.text
    assert http.get(f"/project-drafts/{row['id']}").json()["approved_project_id"]


def test_scope_and_fake_model_cannot_grant_entitlement(http, company):
    row = create(http, company)
    with company["factory"]() as session:
        mock = session.scalar(select(m.ModelConfig).join(m.Provider).where(m.Provider.kind == "mock"))
        stranger = m.User(org_id=company["org"].id, email="another-owner@test.invalid", role="owner")
        session.add(stranger)
        session.flush()
        other_token = token_for(stranger, session)
        session.commit()
    assert (
        http.post(
            "/project-drafts", json={"request_id": str(uuid4()), "form": form(company, lead_model_id=mock.id)}
        ).status_code
        == 403
    )
    assert (
        http.post(
            "/project-drafts",
            json={"request_id": str(uuid4()), "form": form(company, worker_model_ids=[mock.id])},
        ).status_code
        == 403
    )
    assert (
        http.get(
            f"/project-drafts/{row['id']}", headers={"Authorization": "Bearer " + other_token}
        ).status_code
        == 403
    )
    assert all(model["kind"] != "mock" for model in http.get("/project-creation-options").json()["models"])


def test_lead_schema_rejects_unknown_and_duplicate_specialists():
    from company_os.providers import fixture

    data = fixture("LeadAnalysis", {"text": "Build tracker"}).data
    LeadAnalysis.model_validate(data)
    for roles in [["CEO"], ["Cloud Architect", "Cloud Architect"]]:
        with pytest.raises(ValueError):
            LeadAnalysis.model_validate({**data, "specialist_roles": roles})


async def test_lead_specialist_and_planning_handoffs_explicit_fixture_only(http, company):
    """Production accepts no mock selection. Only this test rewrites its private database."""
    from company_os.workflows import tick

    row = create(http, company)
    row = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    with company["factory"]() as session:
        model = session.scalar(
            select(m.ModelConfig)
            .join(m.Provider)
            .where(m.Provider.kind == "mock")
            .order_by(m.ModelConfig.quality.desc())
        )
        record = session.get(m.BusinessRecord, row["id"])
        record.data = {**record.data, "form": {**record.data["form"], "lead_model_id": model.id}}
        session.get(m.Workflow, row["workflow"]["id"]).mode = "mock"
        session.get(m.Requirement, row["data"]["requirement_id"]).mode = "mock"
        session.commit()
    for _ in range(6):
        assert await tick(company["factory"])
        company["factory"].kw["bind"].dispose()
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, row["workflow"]["id"])
        assert workflow.status == "completed", workflow.last_error
        steps = session.scalars(select(m.WorkflowStep).where(m.WorkflowStep.workflow_id == workflow.id)).all()
        assert {step.name for step in steps} == {
            "lead_intake",
            "Business Analyst",
            "CTO",
            "Project Manager",
            "CFO",
            "proposal",
        }
        assert len(steps) == 6
        runs = session.scalars(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id)).all()
        assert len(runs) == 6 and all(run.model_id == model.id for run in runs)
        assert workflow.mode == "mock"
        proposal = session.scalar(select(m.Proposal))
        approval = {
            "version": proposal.version,
            "content_hash": proposal.content_hash,
            "selection": proposal.content["recommendation"],
        }
    result = http.post(f"/proposals/{proposal.id}/approve", json=approval)
    assert result.status_code == 200, result.text
    project = result.json()
    with company["factory"]() as session:
        for task in session.scalars(select(m.Task).where(m.Task.project_id == project["id"])):
            task.status = "paused"
        session.commit()
    plan = http.get(f"/projects/{project['id']}/staffing").json()
    result = http.post(
        "/agent-planning",
        json={
            "request_id": str(uuid4()),
            "project_id": project["id"],
            "plan_version": plan["version"],
            "plan_hash": plan["content_hash"],
            "objective": "Create the persisted project delivery plan",
            "mode": "mock",
        },
    )
    assert result.status_code == 201, result.text
    for _ in range(3):
        assert await tick(company["factory"])
    updated = http.get(f"/projects/{project['id']}/staffing").json()
    assert updated["version"] == plan["version"] + 1 and updated["status"] == "draft"
    assert updated["content"]["tasks"]


def test_sqlite_concurrent_edit_has_one_winner(company):
    from concurrent.futures import ThreadPoolExecutor

    from company_os.project_setup import DraftForm
    from company_os.routes.project_setup_operations import Create, Save
    from company_os.routes.project_setup_operations import create as create_route
    from company_os.routes.project_setup_operations import save as save_route
    from fastapi import HTTPException

    with company["factory"]() as session:
        user = session.get(m.User, company["owner"].id)
        row = create_route(Create(request_id=uuid4(), form=DraftForm(**form(company))), user, session)

    def writer(title):
        with company["factory"]() as session:
            user = session.get(m.User, company["owner"].id)
            try:
                return save_route(
                    row["id"],
                    Save(request_id=uuid4(), version=1, form=DraftForm(**form(company, title=title))),
                    user,
                    session,
                )["version"]
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, ["Concurrent A", "Concurrent B"])) == [2, 409]


async def test_paid_lead_waits_and_alternate_requires_explicit_selection(http, company):
    from company_os.workflows import tick

    with company["factory"]() as session:
        provider = m.Provider(
            org_id=company["org"].id,
            name="Blocked remote fixture metadata",
            kind="compatible",
            base_url="https://example.invalid",
            credential_env="UNUSED_TEST_CREDENTIAL",
        )
        session.add(provider)
        session.flush()
        first = m.ModelConfig(
            org_id=provider.org_id,
            provider_id=provider.id,
            identifier="blocked-first",
            capabilities=["structured", "reasoning"],
            quality=95,
            input_price_micro_per_million=1000000,
        )
        alternate = m.ModelConfig(
            org_id=provider.org_id,
            provider_id=provider.id,
            identifier="blocked-alternate",
            capabilities=["structured", "reasoning"],
            quality=95,
        )
        session.add_all([first, alternate])
        session.commit()
    row = create(http, company, lead_model_id=first.id)
    row = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    assert await tick(company["factory"])
    row = http.get(f"/project-drafts/{row['id']}").json()
    assert row["workflow"]["status"] == "waiting_for_free_provider"
    changed_form = {**row["data"]["form"], "lead_model_id": alternate.id}
    bad = http.post(
        f"/project-drafts/{row['id']}/models",
        json=command(row, form={**changed_form, "text": "Unapproved rewritten requirements"}),
    )
    assert bad.status_code == 409
    result = http.post(f"/project-drafts/{row['id']}/models", json=command(row, form=changed_form))
    assert result.status_code == 200, result.text
    assert result.json()["data"]["form"]["lead_model_id"] == alternate.id
    assert http.post(f"/workflows/{row['workflow']['id']}/resume-free", json={}).status_code == 409
    with company["factory"]() as session:
        assert not session.scalar(select(m.ModelRun))
        assert not session.scalar(select(m.Project))


def test_role_pool_override_and_revoked_owner_are_enforced(http, company):
    from company_os.organization import agent_for
    from company_os.project_setup import routing

    row = create(http, company)
    row = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    with company["factory"]() as session:
        models = session.scalars(select(m.ModelConfig).order_by(m.ModelConfig.quality.desc())).all()
        record = session.get(m.BusinessRecord, row["id"])
        record.data = {
            **record.data,
            "form": {
                **record.data["form"],
                "lead_model_id": models[0].id,
                "worker_mode": "manual",
                "worker_model_ids": [models[1].id],
                "overrides": {"role:Business Analyst": models[1].id},
            },
        }
        session.flush()
        workflow = session.get(m.Workflow, row["workflow"]["id"])
        analyst = agent_for(session, workflow.org_id, "Business Analyst")
        assert routing(session, workflow, analyst, "Business Analyst", None, None) == (
            models[1].id,
            [models[1].id],
            None,
        )
        assert routing(session, workflow, analyst, "lead_intake", None, None) == (models[0].id, None, None)
        assert (
            routing(session, workflow, agent_for(session, workflow.org_id, "CTO"), "CTO", None, None)[1] == []
        )
        with pytest.raises(PermissionError, match="conflicts"):
            routing(session, workflow, analyst, "Business Analyst", None, models[0].id)
        session.get(m.User, company["owner"].id).enabled = False
        with pytest.raises(PermissionError, match="revoked"):
            routing(session, workflow, analyst, "lead_intake", None, None)


def test_upload_only_brief_and_integrity_rollback(http, company):
    row = create(http, company, text="")
    response = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data=command(row),
        files={"file": ("brief.md", b"Build a tracker with durable documents and independent tests.")},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["data"]["form"]["text"].startswith("Build a tracker")
    with company["factory"]() as session:
        session.get(m.Artifact, row["data"]["attachments"][0]["id"]).content = "Tampered content"
        session.commit()
    assert http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).status_code == 403
    with company["factory"]() as session:
        assert not session.scalar(select(m.Requirement))
        assert not session.scalar(select(m.Workflow))
        assert session.get(m.BusinessRecord, row["id"]).status == "draft"
