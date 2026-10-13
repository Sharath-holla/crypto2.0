"""Disposable SQLite + actual routes/workers. Model output is explicitly deterministic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from company_os import models as m
from company_os.db import now
from company_os.requirements_refinement import RequirementCritique, assert_approved
from company_os.security import token_for
from company_os.workflows import consulting_step, tick
from sqlalchemy import func, select


def command(row, **extra):
    return {"request_id": str(uuid4()), "version": row["version"], **extra}


def submitted(http, company, **extra):
    result = http.post(
        "/project-drafts",
        json={
            "request_id": str(uuid4()),
            "form": {
                "client_id": company["client"].id,
                "title": "Task Management Web Application",
                "text": "Create, view, update, complete and delete tasks with persistent storage and a tested API.",
                "review_before_planning": True,
                **extra,
            },
        },
    )
    assert result.status_code == 201, result.text
    row = result.json()
    result = http.post(f"/project-drafts/{row['id']}/submit", json=command(row))
    assert result.status_code == 200, result.text
    return result.json()


def review(http, row):
    result = http.get(f"/project-drafts/{row['id']}/requirements-review")
    assert result.status_code == 200, result.text
    return result.json()


def revision_body(http, row):
    saved = review(http, row)
    scope = deepcopy(saved["current"]["scope"])
    scope["acceptance_criteria"] = [
        "All task CRUD operations persist across restart",
        "Invalid input changes no saved task",
    ]
    decisions = {}
    for index, item in enumerate(saved["improvements"]):
        action = "accept" if index == 0 else "edit"
        text = "Reject task titles longer than 200 characters."
        decisions[item["id"]] = {
            "action": action,
            "reason": "Owner selects explicit validated scope",
            "edited_text": text if action == "edit" else "",
        }
        scope["functional_requirements"].append(item["recommendation"] if action == "accept" else text)
    return {
        "request_id": str(uuid4()),
        "version": saved["draft_version"],
        "scope": scope,
        "decisions": decisions,
        "answers": {
            item["id"]: "Task owners on a local test deployment, no external costs."
            for item in saved["questions"]
        },
    }


def revise(http, row, **changes):
    body = {**revision_body(http, row), **changes}
    result = http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body)
    assert result.status_code == 200, result.text
    return result.json(), body


def signoff(http, row):
    saved = review(http, row)
    body = command(row, scope_hash=saved["current"]["scope_hash"], owner_authored=True)
    result = http.post(f"/project-drafts/{row['id']}/requirements-approve", json=body)
    assert result.status_code == 200, result.text
    return result.json(), body


def enable_fixture(company, row):
    # No production endpoint can select this mock entry; only the isolated test DB is changed.
    with company["factory"]() as session:
        model = session.scalar(
            select(m.ModelConfig)
            .join(m.Provider)
            .where(m.Provider.kind == "mock")
            .order_by(m.ModelConfig.quality.desc())
        )
        record = session.get(m.BusinessRecord, row["id"])
        record.data = {**record.data, "form": {**record.data["form"], "lead_model_id": model.id}}
        session.get(m.Workflow, record.data["workflow_id"]).mode = "mock"
        session.get(m.Requirement, record.data["requirement_id"]).mode = "mock"
        session.commit()


async def critiqued(http, company):
    row = submitted(http, company)
    enable_fixture(company, row)
    for _ in range(2):
        assert await tick(company["factory"])
        company["factory"].kw["bind"].dispose()
    return http.get(f"/project-drafts/{row['id']}").json()


async def test_unavailable_model_persists_without_analysis_or_authority(http, company):
    row = submitted(http, company)
    assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    row = http.get(f"/project-drafts/{row['id']}").json()
    assert row["workflow"]["status"] == "waiting_for_free_provider"
    saved = review(http, row)
    assert not saved["approved"] and not saved["current"]["reviews"]
    assert saved["current"]["scope"]["text"] == row["data"]["form"]["text"]
    with company["factory"]() as session:
        assert not session.scalar(select(m.ModelRun.id))
        assert not session.scalar(select(m.Approval.id))
        assert not session.scalar(select(m.Project.id))
    assert (
        http.post(
            f"/project-drafts/{row['id']}/requirements-approve",
            json=command(row, scope_hash=saved["current"]["scope_hash"], owner_authored=True),
        ).status_code
        == 422
    )


async def test_lead_ba_pause_decisions_revision_signoff_and_architecture_handoff(http, company):
    row = await critiqued(http, company)
    assert row["workflow"]["step"] == 2 and row["workflow"]["status"] == "paused"
    saved = review(http, row)
    assert [item["role"] for item in saved["current"]["reviews"]] == ["lead_intake", "Business Analyst"]
    assert all(item["evidence_category"] == "FIXTURE_TESTED" for item in saved["current"]["reviews"])
    assert len(saved["improvements"]) == 2 and len(saved["questions"]) == 4
    original = deepcopy(saved["current"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, row["workflow"]["id"])
        workflow.status, workflow.lease_token, workflow.lease_until = (
            "running",
            "forced-test-token",
            now() + 60,
        )
        session.commit()
        with pytest.raises(PermissionError, match="sign-off"):
            await consulting_step(session, workflow, "forced-test-token")
        session.rollback()
        assert session.scalar(select(func.count()).select_from(m.ModelRun)) == 2
        workflow.status = "paused"
        session.commit()
    revised, body = revise(http, row)
    assert revised["data"]["requirement_version"] == 2 and revised["workflow"]["step"] == 2
    history = review(http, revised)["history"]
    assert history[0]["scope"] == original["scope"] and history[0]["scope_hash"] == original["scope_hash"]
    assert history[0]["reviews"] == original["reviews"]
    assert (
        http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body).json()["version"]
        == revised["version"]
    )
    approved, approval_body = signoff(http, revised)
    assert review(http, approved)["approved"]
    assert (
        http.post(f"/project-drafts/{row['id']}/requirements-approve", json=approval_body).json()["version"]
        == approved["version"]
    )
    # The next workflow starts at architecture, with no repeated review or fake independent AI claim.
    with company["factory"]() as session:
        session.get(m.Workflow, approved["workflow"]["id"]).mode = "mock"
        session.commit()
    for _ in range(4):
        assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, approved["workflow"]["id"])
        assert workflow.status == "completed", workflow.last_error
        proposal = session.scalar(select(m.Proposal))
        assert (
            proposal.content["requirements_signoff"]["scope_hash"]
            == review(http, approved)["current"]["scope_hash"]
        )
        assert set(body["scope"]["acceptance_criteria"]).issubset(proposal.content["acceptance_criteria"])
        assert (
            session.scalar(
                select(func.count()).select_from(m.Approval).where(m.Approval.category == "requirement_scope")
            )
            == 1
        )
        assert not session.scalar(select(m.Project.id))
        assert {
            step.name
            for step in session.scalars(
                select(m.WorkflowStep)
                .where(m.WorkflowStep.workflow_id == workflow.id)
                .order_by(m.WorkflowStep.created_at, m.WorkflowStep.id)
            )
        } == {"CTO", "Project Manager", "CFO", "proposal"}
        approval = {
            "version": proposal.version,
            "content_hash": proposal.content_hash,
            "selection": proposal.content["recommendation"],
        }
    result = http.post(f"/proposals/{proposal.id}/approve", json=approval)
    assert result.status_code == 200, result.text
    with company["factory"]() as session:
        knowledge = session.scalar(
            select(m.BusinessRecord).where(
                m.BusinessRecord.kind == "knowledge",
                m.BusinessRecord.data["scope_hash"].as_string()
                == review(http, approved)["current"]["scope_hash"],
            )
        )
        assert knowledge.project_id == result.json()["id"]


@pytest.mark.parametrize(
    "change",
    ["missing_decisions", "missing_answers", "missing_accepted_scope", "blank_edit", "unknown_decision"],
)
async def test_incomplete_decisions_cannot_be_signed_off(http, company, change):
    row = await critiqued(http, company)
    body = revision_body(http, row)
    if change == "missing_decisions":
        body["decisions"] = {}
    if change == "missing_answers":
        body["answers"] = {}
    if change == "missing_accepted_scope":
        body["scope"]["functional_requirements"] = [row["data"]["form"]["text"]]
    if change == "blank_edit":
        body["decisions"][next(reversed(body["decisions"]))]["edited_text"] = " "
    if change == "unknown_decision":
        body["decisions"]["invented"] = {"action": "reject", "reason": "unknown"}
    result = http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body)
    assert result.status_code == 422, result.text
    assert review(http, row)["current"]["version"] == 1


async def test_rejection_and_reconsideration_preserve_prior_review(http, company):
    row = await critiqued(http, company)
    body = revision_body(http, row)
    body["decisions"] = {
        key: {"action": "reject", "reason": "Outside the requested scope"} for key in body["decisions"]
    }
    body["scope"]["functional_requirements"] = [row["data"]["form"]["text"]]
    revised = http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body).json()
    saved = review(http, revised)
    assert len(saved["current"]["scope"]["functional_requirements"]) == 1
    assert all(item["action"] == "reject" for item in saved["current"]["decisions"].values())
    revised, _ = revise(http, revised, reconsider=True)
    assert revised["workflow"]["step"] == 0 and revised["workflow"]["status"] == "queued"
    assert len(review(http, revised)["history"]) == 2
    with company["factory"]() as session:
        session.get(m.Workflow, revised["workflow"]["id"]).mode = "mock"
        session.commit()
    assert await tick(company["factory"])
    assert await tick(company["factory"])
    assert len(review(http, revised)["current"]["reviews"]) == 2


@pytest.mark.parametrize(
    "change", ["expired_approval", "scope_tamper", "source_tamper", "disabled_owner", "wrong_subject"]
)
def test_scope_authority_revalidated_after_signoff(http, company, change):
    row, _ = revise(http, submitted(http, company, planning_mode="manual"))
    row, _ = signoff(http, row)
    with company["factory"]() as session:
        draft = session.get(m.BusinessRecord, row["id"])
        requirement = session.get(m.Requirement, draft.data["requirement_id"])
        approval = session.get(m.Approval, draft.data["refinement"]["approval_id"])
        if change == "expired_approval":
            approval.expires_at = now() - 1
        if change == "disabled_owner":
            session.get(m.User, approval.owner_id).enabled = False
        if change == "wrong_subject":
            approval.subject_id = str(uuid4())
        if change == "source_tamper":
            requirement.text = "Changed requirement after exact approval without a legitimate revision"
        if change == "scope_tamper":
            content = deepcopy(draft.data)
            content["refinement"]["current"]["scope"]["acceptance_criteria"] = ["Fake passing criterion"]
            draft.data = content
        session.commit()
        with pytest.raises(PermissionError):
            assert_approved(session, requirement)


def test_manual_plan_requires_scope_approval_and_retains_original(http, company):
    original = submitted(http, company, planning_mode="manual")
    payload = {
        "architecture": "SQLite task service with a small web frontend and independent QA",
        "milestones": ["Implement CRUD", "Verify acceptance"],
        "criteria": ["Tasks persist"],
    }
    assert (
        http.post(
            f"/project-drafts/{original['id']}/manual-plan", json=command(original, **payload)
        ).status_code
        == 403
    )
    row, _ = revise(http, original)
    wrong = command(row, scope_hash="0" * 64, owner_authored=True)
    assert http.post(f"/project-drafts/{row['id']}/requirements-approve", json=wrong).status_code == 422
    row, _ = signoff(http, row)
    result = http.post(f"/project-drafts/{row['id']}/manual-plan", json=command(row, **payload))
    assert result.status_code == 200, result.text
    assert result.json()["data"]["form"]["text"] == original["data"]["form"]["text"]
    assert review(http, row)["history"][0]["scope"]["text"] == original["data"]["form"]["text"]
    assert (
        http.post(
            f"/requirements/{row['data']['requirement_id']}/clarify",
            json={"version": 2, "answers": {}, "rates": []},
        ).status_code
        == 409
    )
    assert (
        http.patch(
            f"/records/{row['id']}", json={"version": row["version"], "status": "reviewed"}
        ).status_code
        == 409
    )


def test_expired_checkpoint_requires_fresh_revision_and_same_request_conflicts(http, company):
    row, body = revise(http, submitted(http, company, planning_mode="manual"))
    body["scope"]["text"] += " Conflicting reused command."
    assert http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body).status_code == 409
    with company["factory"]() as session:
        session.get(m.Workflow, row["workflow"]["id"]).deadline_at = now() - 1
        session.commit()
    saved = review(http, row)
    result = http.post(
        f"/project-drafts/{row['id']}/requirements-approve",
        json=command(row, scope_hash=saved["current"]["scope_hash"], owner_authored=True),
    )
    assert result.status_code == 422
    row, _ = revise(http, row)
    row, _ = signoff(http, row)
    assert review(http, row)["approved"]


async def test_tampered_critique_checkpoint_rejected(http, company):
    row = await critiqued(http, company)
    with company["factory"]() as session:
        step = session.scalar(
            select(m.WorkflowStep).where(m.WorkflowStep.workflow_id == row["workflow"]["id"])
        )
        step.result = {**step.result, "questions": []}
        session.commit()
    assert http.get(f"/project-drafts/{row['id']}/requirements-review").status_code == 403


def test_owner_client_and_tenant_isolation(http, company):
    row = submitted(http, company)
    with company["factory"]() as session:
        stranger = m.User(org_id=company["org"].id, email="scope-other-owner@fixture.test", role="owner")
        client = m.User(
            org_id=company["org"].id,
            email="scope-client@fixture.test",
            role="client",
            client_id=company["client"].id,
        )
        other = m.Organization(name="Other fixture tenant")
        session.add_all([stranger, client, other])
        session.flush()
        tenant_owner = m.User(org_id=other.id, email="scope-other-tenant@fixture.test", role="owner")
        session.add(tenant_owner)
        session.flush()
        tokens = [token_for(user, session) for user in (stranger, client, tenant_owner)]
        session.commit()
    for token in tokens:
        headers = {"Authorization": "Bearer " + token}
        assert (
            http.get(f"/project-drafts/{row['id']}/requirements-review", headers=headers).status_code == 403
        )
        assert (
            http.post(
                f"/project-drafts/{row['id']}/requirements-revision",
                json=revision_body(http, row),
                headers=headers,
            ).status_code
            == 403
        )


def test_concurrent_scope_revisions_have_one_winner(http, company):
    from company_os.routes.refinement_operations import Revision
    from company_os.routes.refinement_operations import revise as route
    from fastapi import HTTPException

    row = submitted(http, company, planning_mode="manual")
    body = revision_body(http, row)

    def writer(label):
        content = deepcopy(body)
        content["request_id"] = str(uuid4())
        content["scope"]["text"] += label
        with company["factory"]() as session:
            try:
                result = route(
                    row["id"],
                    Revision.model_validate(content),
                    session.get(m.User, company["owner"].id),
                    session,
                )
                return result["version"]
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(writer, [" Writer A", " Writer B"])) == [row["version"] + 1, 409]
    company["factory"].kw["bind"].dispose()
    saved = review(http, row)
    assert len(saved["history"]) == 1 and saved["current"]["version"] == 2


@pytest.mark.parametrize("change", ["duplicate_id", "unknown_complexity", "blank_scope", "extra_authority"])
def test_critique_contract_rejects_invalid_outputs(change):
    from company_os.providers import fixture

    content = fixture(
        "RequirementCritique", {"text": "Build a persisted task management web application"}
    ).data
    if change == "duplicate_id":
        content["improvements"] *= 2
    if change == "unknown_complexity":
        content["improvements"][0]["complexity"] = "automatic approval"
    if change == "blank_scope":
        content["proposed_specification"]["functional_requirements"] = [" "]
    if change == "extra_authority":
        content["owner_approved"] = True
    with pytest.raises(ValueError):
        RequirementCritique.model_validate(content)


@pytest.mark.parametrize("change", ["no_criteria", "open_questions", "no_goals", "no_acknowledgement"])
def test_signoff_rejects_incomplete_specification(http, company, change):
    row = submitted(http, company, planning_mode="manual")
    body = revision_body(http, row)
    if change == "no_criteria":
        body["scope"]["acceptance_criteria"] = []
    if change == "open_questions":
        body["scope"]["open_questions"] = ["Which identity provider is approved?"]
    if change == "no_goals":
        body["scope"]["goals"] = []
    result = http.post(f"/project-drafts/{row['id']}/requirements-revision", json=body)
    assert result.status_code == 200, result.text
    row = result.json()
    saved = review(http, row)
    result = http.post(
        f"/project-drafts/{row['id']}/requirements-approve",
        json=command(
            row, scope_hash=saved["current"]["scope_hash"], owner_authored=change != "no_acknowledgement"
        ),
    )
    assert result.status_code == 422
    assert not review(http, row)["approved"]


def test_new_revision_preserves_old_signoff_and_revokes_architecture_authority(http, company):
    row, _ = revise(http, submitted(http, company, planning_mode="manual"))
    row, _ = signoff(http, row)
    signed = review(http, row)
    revised, _ = revise(http, row)
    saved = review(http, revised)
    assert not saved["approved"] and saved["current"]["version"] == 3
    assert saved["history"][-1]["approval_id"] == signed["approval_id"]
    assert saved["history"][-1]["scope_hash"] == signed["current"]["scope_hash"]
    with company["factory"]() as session:
        approval = session.get(m.Approval, signed["approval_id"])
        assert approval.version == 2 and approval.subject_hash == signed["current"]["scope_hash"]
        with pytest.raises(PermissionError):
            assert_approved(session, session.get(m.Requirement, revised["data"]["requirement_id"]))


def test_missing_refinement_cannot_become_legacy_authority(http, company):
    row = submitted(http, company)
    with company["factory"]() as session:
        draft = session.get(m.BusinessRecord, row["id"])
        draft.data = {key: value for key, value in draft.data.items() if key != "refinement"}
        session.commit()
        with pytest.raises(PermissionError, match="missing"):
            assert_approved(session, session.get(m.Requirement, row["data"]["requirement_id"]))


def test_bounded_scope_history_and_explicit_decision_reason(http, company):
    from company_os.requirements_refinement import Decision, Scope, bound_history

    row = submitted(http, company)
    scope = review(http, row)["current"]["scope"]
    with pytest.raises(ValueError, match="100 KB"):
        Scope.model_validate(
            {
                **scope,
                "functional_requirements": ["a" * 2000] * 30,
                "nonfunctional_requirements": ["b" * 2000] * 30,
            }
        )
    with pytest.raises(ValueError, match="1 MB"):
        bound_history({"oversized": "x" * 1000001})
    with pytest.raises(ValueError, match="nonblank"):
        Decision(action="reject", reason=" ")
