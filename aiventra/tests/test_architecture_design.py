"""Architecture contracts using actual workers, SQLite and labeled test adapters."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from company_os import models as m
from company_os.architecture_design import TechnicalDesign, selected_context, validate
from company_os.db import now
from company_os.providers import fixture
from company_os.security import digest
from company_os.workflows import project_authority, tick
from pydantic import ValidationError
from sqlalchemy import func, select
from test_requirements_refinement import command, critiqued, revise, signoff, submitted


async def proposed(http, company):
    row = await critiqued(http, company)
    row, _ = revise(http, row)
    row, _ = signoff(http, row)
    with company["factory"]() as session:
        session.get(m.Workflow, row["workflow"]["id"]).mode = "mock"
        session.commit()
    for _ in range(4):
        assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, row["workflow"]["id"])
        assert workflow.status == "completed", workflow.last_error
        proposal = session.scalar(
            select(m.Proposal).where(m.Proposal.requirement_id == row["data"]["requirement_id"])
        )
        body = {
            "version": proposal.version,
            "content_hash": proposal.content_hash,
            "selection": proposal.content["recommendation"],
        }
        return row, proposal.id, body


@pytest.mark.parametrize(
    "change", ["duplicate", "recommendation", "single", "benchmark", "prices", "oversize"]
)
def test_design_contract_rejects_incoherent_or_unverified_claims(change):
    result = deepcopy(fixture("TechnicalDesign", {}).data)
    if change == "duplicate":
        result["options"][1]["name"] = result["options"][0]["name"]
    elif change == "recommendation":
        result["recommended_option"] = "Unknown option"
    elif change == "single":
        result["options"] = result["options"][:1]
    elif change == "benchmark":
        result["benchmarks_verified"] = True
    elif change == "prices":
        result["cloud_prices_verified"] = True
    else:
        result["options"][0]["high_level_design"] = "a" * 16001
    with pytest.raises(ValidationError):
        TechnicalDesign.model_validate(result)


async def test_exact_selection_documents_knowledge_and_idempotent_approval(http, company):
    row, proposal_id, body = await proposed(http, company)
    with company["factory"]() as session:
        proposal = session.get(m.Proposal, proposal_id)
        manifest = proposal.content["architecture_manifest"]
        assert manifest["basis"] == "FIXTURE_TESTED"
        assert len(manifest["documents"]) == 2
        messages = list(
            session.scalars(
                select(m.Message).where(
                    m.Message.correlation_id == row["data"]["requirement_id"],
                    m.Message.type == "ARCHITECTURE_PROPOSAL",
                )
            )
        )
        assert (
            next(message for message in messages if "options" in message.content).expected_schema
            == "TechnicalDesign"
        )
        assert not session.scalar(select(m.Approval.id).where(m.Approval.category == "architecture_design"))
        # The owner can choose the non-recommended option.
        body["selection"] = manifest["design"]["options"][1]["name"]
    result = http.post(f"/proposals/{proposal_id}/approve", json=body)
    assert result.status_code == 200, result.text
    assert http.post(f"/proposals/{proposal_id}/approve", json=body).json()["id"] == result.json()["id"]
    with company["factory"]() as session:
        project = session.get(m.Project, result.json()["id"])
        project_authority(session, project)
        context = selected_context(session.get(m.Proposal, proposal_id), project)
        assert context["design"]["name"] == body["selection"]
        approval = session.scalar(select(m.Approval).where(m.Approval.category == "architecture_design"))
        assert approval.selection == body["selection"] and approval.owner_id == company["owner"].id
        assert (
            session.scalar(
                select(func.count())
                .select_from(m.Approval)
                .where(m.Approval.category == "architecture_design")
            )
            == 1
        )
        knowledge = session.scalar(
            select(m.BusinessRecord).where(
                m.BusinessRecord.kind == "knowledge",
                m.BusinessRecord.data["architecture_approval_id"].as_string() == approval.id,
            )
        )
        assert knowledge.project_id == project.id
        assert (
            session.get(m.BusinessRecord, row["id"]).data["architecture_design"]["manifest_hash"]
            == manifest["manifest_hash"]
        )


@pytest.mark.parametrize(
    "change",
    [
        "document",
        "run",
        "checkpoint",
        "scope",
        "manifest",
        "document_option",
        "document_content",
        "missing",
        "malformed",
    ],
)
async def test_provenance_tamper_blocks_project_creation(http, company, change):
    _row, proposal_id, body = await proposed(http, company)
    with company["factory"]() as session:
        proposal = session.get(m.Proposal, proposal_id)
        manifest = deepcopy(proposal.content["architecture_manifest"])
        if change == "document":
            session.get(m.Artifact, manifest["documents"][0]["artifact_id"]).content += "changed"
        elif change == "run":
            session.get(m.ModelRun, manifest["run_id"]).status = "failed"
        elif change == "checkpoint":
            step = session.scalar(
                select(m.WorkflowStep).where(
                    m.WorkflowStep.workflow_id == manifest["workflow_id"], m.WorkflowStep.name == "CTO"
                )
            )
            step.result = {**step.result, "summary": "Changed checkpoint"}
        elif change == "scope":
            manifest["scope_hash"] = "0" * 64
        elif change == "manifest":
            manifest["design"]["options"][0]["architecture"] += " Changed"
        elif change == "malformed":
            manifest["documents"] = None
            manifest["manifest_hash"] = digest(
                {key: value for key, value in manifest.items() if key not in {"created_at", "manifest_hash"}}
            )
        else:
            manifest["documents"][0]["option"] = "Substituted option"
            if change == "document_content":
                manifest["documents"][0] = deepcopy(manifest["documents"][1])
            manifest["manifest_hash"] = digest(
                {k: v for k, v in manifest.items() if k not in {"created_at", "manifest_hash"}}
            )
        proposal.content = {**proposal.content, "architecture_manifest": manifest}
        if change == "missing":
            proposal.content = {
                key: value for key, value in proposal.content.items() if key != "architecture_manifest"
            }
        proposal.content_hash = digest(proposal.content)
        body["content_hash"] = proposal.content_hash
        session.commit()
    result = http.post(f"/proposals/{proposal_id}/approve", json=body)
    assert result.status_code == 409, result.text
    with company["factory"]() as session:
        assert not session.scalar(select(m.Project.id))
        assert not session.scalar(select(m.Approval.id).where(m.Approval.category == "architecture_design"))


@pytest.mark.parametrize("change", ["expired", "selection", "owner_disabled", "approval_hash"])
async def test_authority_rechecked_before_execution(http, company, change):
    _row, proposal_id, body = await proposed(http, company)
    result = http.post(f"/proposals/{proposal_id}/approve", json=body)
    assert result.status_code == 200, result.text
    with company["factory"]() as session:
        project = session.get(m.Project, result.json()["id"])
        approval = session.scalar(select(m.Approval).where(m.Approval.category == "architecture_design"))
        if change == "expired":
            approval.expires_at = now() - 1
        elif change == "selection":
            project.selected_alternative = "Changed selection"
        elif change == "owner_disabled":
            session.get(m.User, approval.owner_id).enabled = False
        else:
            approval.subject_hash = "0" * 64
        session.flush()
        with pytest.raises(PermissionError):
            project_authority(session, project)


def test_manual_architecture_is_explicitly_limited_not_model_evidence(http, company):
    row, _ = revise(http, submitted(http, company, planning_mode="manual"))
    row, _ = signoff(http, row)
    result = http.post(
        f"/project-drafts/{row['id']}/manual-plan",
        json=command(
            row,
            architecture="SQLite task service, scoped API and web interface; implementation still required.",
            milestones=["Implement CRUD", "Verify acceptance"],
            criteria=["Tasks persist"],
        ),
    )
    assert result.status_code == 200, result.text
    with company["factory"]() as session:
        proposal = session.scalar(select(m.Proposal))
        manifest = proposal.content["architecture_manifest"]
        assert manifest["basis"] == "OWNER_AUTHORED_LIMITED_PLAN"
        assert manifest["run_id"] is None and manifest["design"]["limitations"]
        assert not session.scalar(select(m.ModelRun.id))
        validate(session, session.get(m.Requirement, proposal.requirement_id), manifest)
        body = {
            "version": proposal.version,
            "content_hash": proposal.content_hash,
            "selection": "Owner-authored plan",
        }
    assert http.post(f"/proposals/{proposal.id}/approve", json=body).status_code == 200


async def test_concurrent_approve_reject_has_one_winner(http, company):
    _row, proposal_id, body = await proposed(http, company)
    with ThreadPoolExecutor(max_workers=2) as executor:
        approval = executor.submit(http.post, f"/proposals/{proposal_id}/approve", json=body)
        rejection = executor.submit(
            http.post,
            f"/proposals/{proposal_id}/decision",
            json={"version": body["version"], "action": "request_changes", "reason": "Reconsider design"},
        )
        results = [approval.result(), rejection.result()]
    assert sorted(result.status_code for result in results) == [200, 409], [result.text for result in results]
    with company["factory"]() as session:
        proposal = session.get(m.Proposal, proposal_id)
        count = session.scalar(select(func.count()).select_from(m.Project))
        assert (proposal.status == "approved" and count == 1) or (
            proposal.status == "changes_requested" and count == 0
        )


async def test_rejected_design_requires_fresh_scope_preserves_prior_documents(http, company):
    row, proposal_id, body = await proposed(http, company)
    assert (
        http.post(
            f"/proposals/{proposal_id}/decision",
            json={
                "version": body["version"],
                "action": "request_changes",
                "reason": "Owner requests a revised technical scope",
            },
        ).status_code
        == 200
    )
    assert http.post(f"/proposals/{proposal_id}/approve", json=body).status_code == 409
    row = http.get(f"/project-drafts/{row['id']}").json()
    with company["factory"]() as session:
        previous = deepcopy(session.get(m.Proposal, proposal_id).content["architecture_manifest"])
    row, _ = revise(http, row)
    row, _ = signoff(http, row)
    with company["factory"]() as session:
        session.get(m.Workflow, row["workflow"]["id"]).mode = "mock"
        session.commit()
    assert await tick(company["factory"])
    with company["factory"]() as session:
        draft = session.get(m.BusinessRecord, row["id"])
        assert draft.data["architecture_history"] == [previous]
        assert draft.data["architecture_design"]["requirement_version"] == 3
        assert draft.data["architecture_design"]["manifest_hash"] != previous["manifest_hash"]
        assert all(
            session.get(m.Artifact, doc["artifact_id"]).sha256 == doc["sha256"]
            for doc in previous["documents"]
        )
        assert not session.scalar(select(m.Project.id))
