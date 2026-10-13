"""Owner project drafts and project-scoped model choices on existing persistence."""

import hashlib
from datetime import date
from typing import Literal

from pydantic import Field, field_validator
from sqlalchemy import select

from . import models as m
from . import spending
from .api_common import serialize
from .db import now, uid
from .registry_provenance import visible
from .schemas import Analysis, Strict
from .security import audit, digest

FAVORITE = "GPT-6.1 Sol"
KIND = "project_setup"
SPECIALISTS = ("Cloud Architect", "Security Architect", "FinOps Engineer")


def selection(form):
    return {key: form.get(key) for key in ("lead_model_id", "worker_mode", "worker_model_ids", "overrides")}


def record_selection(session, row, user):
    choices = selection(row.data["form"])
    row.data = {
        **row.data,
        "selection_history": [
            *row.data.get("selection_history", []),
            {
                "version": row.version,
                "selected_at": now(),
                "selected_by": user.id,
                "choices": choices,
                "selection_hash": digest(choices),
                "lead_eligibility_at_selection": lead_status(session, row.data["form"]),
            },
        ],
    }


class DraftForm(Strict):
    client_id: str
    title: str = Field(default="", max_length=200)
    text: str = Field(default="", max_length=30000)
    step: int = Field(default=1, ge=1, le=3)
    source_project_id: str | None = None
    repository_id: str | None = None
    technology: str = Field(default="", max_length=1000)
    constraints: str = Field(default="", max_length=4000)
    deadline: date | None = None
    budget_micro: int = Field(default=5000000, ge=0, le=10**12)
    preferred_lead: Literal["GPT-6.1 Sol"] = FAVORITE
    lead_model_id: str | None = None
    worker_mode: Literal["automatic", "manual", "hybrid"] = "automatic"
    worker_model_ids: list[str] = Field(default_factory=list, max_length=32)
    overrides: dict[str, str] = Field(default_factory=dict, max_length=16)
    planning_mode: Literal["ai", "manual"] = "ai"
    review_before_planning: bool = False  # Legacy API drafts retain their existing workflow.


class LeadAnalysis(Analysis):
    specialist_roles: list[Literal["Cloud Architect", "Security Architect", "FinOps Engineer"]] = Field(
        max_length=3
    )

    @field_validator("specialist_roles")
    @classmethod
    def unique_roles(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Specialist roles must be unique")
        return value


def validate_form(session, user, form):
    client = session.get(m.Client, form.client_id)
    if not client or client.org_id != user.org_id:
        raise PermissionError("Client is outside this workspace")
    project = session.get(m.Project, form.source_project_id) if form.source_project_id else None
    if form.source_project_id and (
        not project or project.org_id != user.org_id or project.client_id != client.id
    ):
        raise PermissionError("Reference project must belong to the selected client")
    if form.repository_id:
        repo = session.get(m.Repository, form.repository_id)
        if not repo or repo.org_id != user.org_id or not project or repo.project_id != project.id:
            raise PermissionError("Select an authorized repository from the reference project")
    if form.lead_model_id:
        model = session.get(m.ModelConfig, form.lead_model_id)
        provider = session.get(m.Provider, model.provider_id) if model else None
        if (
            not model
            or model.org_id != user.org_id
            or not provider
            or provider.org_id != user.org_id
            or provider.kind == "mock"
            or not visible(session, provider)
        ):
            raise PermissionError("Lead AI preference must reference a real registered workspace model")
    if len(set(form.worker_model_ids)) != len(form.worker_model_ids):
        raise ValueError("Worker pool must contain unique model IDs")
    for model_id in set(form.worker_model_ids) | set(form.overrides.values()):
        model = session.get(m.ModelConfig, model_id)
        provider = session.get(m.Provider, model.provider_id) if model else None
        if (
            not model
            or model.org_id != user.org_id
            or not provider
            or provider.org_id != user.org_id
            or provider.kind == "mock"
            or not visible(session, provider)
        ):
            raise PermissionError("Worker preference must reference a real registered workspace model")
    for scope, model_id in form.overrides.items():
        if scope.startswith("role:"):
            valid = session.scalar(
                select(m.Agent.id).where(
                    m.Agent.org_id == user.org_id, m.Agent.role == scope[5:], m.Agent.enabled.is_(True)
                )
            )
        elif scope.startswith("department:"):
            department = session.get(m.Department, scope[11:])
            valid = department and department.org_id == user.org_id
        else:
            valid = False
        if not valid:
            raise PermissionError("Override scope must be an enabled role or workspace department")
        if form.worker_model_ids and model_id not in form.worker_model_ids:
            raise PermissionError("Override model is outside the selected worker pool")
    if form.worker_mode == "automatic" and form.overrides:
        raise ValueError("Use hybrid or manual mode for worker overrides")


def owned(session, record_id, user):
    row = session.get(m.BusinessRecord, str(record_id))
    if not row or row.org_id != user.org_id or row.kind != KIND or row.data["owner_id"] != user.id:
        raise PermissionError("Project draft is unavailable")
    return row


def for_requirement(session, requirement_id, org_id):
    return session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == org_id,
            m.BusinessRecord.kind == KIND,
            m.BusinessRecord.data["requirement_id"].as_string() == requirement_id,
        )
    )


def lead_status(session, form):
    if not form.get("lead_model_id"):
        return {
            "allowed": False,
            "state": "UNAVAILABLE_FAVORITE",
            "reason": "Your preferred Lead AI is saved but cannot currently run under zero-cost mode. "
            "No API identifier or entitlement is assumed. Explicitly select a registered alternate.",
        }
    model = session.get(m.ModelConfig, form["lead_model_id"])
    provider = session.get(m.Provider, model.provider_id) if model else None
    if not model or not provider:
        return {"allowed": False, "state": "PROVIDER_UNAVAILABLE", "reason": "Selected model is unavailable"}
    if not model.enabled or not provider.enabled:
        return {
            "allowed": False,
            "state": "PROVIDER_UNAVAILABLE",
            "reason": "Selected model or provider is disabled",
        }
    if not {"structured", "reasoning"}.issubset(model.capabilities):
        return {
            "allowed": False,
            "state": "UNSUPPORTED_CAPABILITY",
            "reason": "Saved preference; reasoning and structured-output capabilities are not configured",
        }
    return {
        **spending.status(session, provider, model),
        "identifier": model.identifier,
        "provider": provider.name,
    }


def view(session, row):
    result = serialize(row)
    result["data"] = {
        key: value for key, value in result["data"].items() if key not in {"requests", "create_hash"}
    }
    form = row.data["form"]
    requirement_id = row.data.get("requirement_id")
    project = (
        session.scalar(
            select(m.Project)
            .join(m.Proposal)
            .where(m.Project.org_id == row.org_id, m.Proposal.requirement_id == requirement_id)
        )
        if requirement_id
        else None
    )
    workflow = session.get(m.Workflow, row.data.get("workflow_id")) if row.data.get("workflow_id") else None
    return {
        **result,
        "lead_status": lead_status(session, form),
        "approved_project_id": project.id if project else None,
        "workflow": serialize(workflow) if workflow else None,
        "required_approvals": [
            "Exact proposal",
            "Workforce scope",
            "Repository changes",
            "PR publication",
            "Delivery release",
            "Project closure",
        ],
    }


def routing(session, workflow, agent, step, project, override):
    """Preferences constrain candidates, never confer spending/tool/approval authority."""
    from .task_routing import runtime

    binding = runtime(session, workflow, agent)
    task_choice = (binding[1].model_override or binding[1].preferred_model_id) if binding else None
    task_mode = binding[0].payload["routing_mode"] if binding else None
    if task_choice and override and task_choice != override:
        raise PermissionError("Invocation override conflicts with the approved task model")
    override = task_choice or override
    row = None
    if workflow.requirement_id:
        row = for_requirement(session, workflow.requirement_id, workflow.org_id)
    elif project:
        proposal = session.get(m.Proposal, project.proposal_id)
        row = for_requirement(session, proposal.requirement_id, workflow.org_id)
    if not row:
        if task_mode == "manual" and not override:
            return None, [], "Manual task selection has no exact model assignment"
        return override, None, None
    owner = session.get(m.User, row.data["owner_id"])
    requirement = session.get(m.Requirement, row.data["requirement_id"])
    if not owner or not owner.enabled or owner.role != "owner" or owner.org_id != workflow.org_id:
        raise PermissionError("Project model-selection owner authority revoked")
    if requirement.version != row.data["requirement_version"]:
        raise PermissionError("Requirements changed; prepare a new reviewed model-selection revision")
    form = row.data["form"]
    is_lead = step in {"lead_intake", "proposal", "planning_2"}
    selected = (
        form["lead_model_id"]
        if is_lead
        else (
            task_choice
            or form["overrides"].get("role:" + agent.role)
            or form["overrides"].get("department:" + agent.department_id)
        )
    )
    if is_lead and not selected:
        return None, [], "Preferred Lead AI unavailable; explicitly select an eligible alternate"
    if not is_lead and (task_mode or form["worker_mode"]) == "manual" and not selected and not override:
        return None, [], "Manual worker selection has no model assigned to this role or department"
    if selected and override and override != selected:
        raise PermissionError("Invocation override conflicts with the project's exact model selection")
    return selected or override, (None if is_lead else form["worker_model_ids"] or None), None


def submit(session, row, user):
    from .routes.consultation import stage_intake
    from .schemas import Intake

    form = DraftForm.model_validate(row.data["form"])
    validate_form(session, user, form)
    if len(form.title.strip()) < 3 or len(form.text.strip()) < 20:
        raise ValueError("Provide a project name and at least 20 characters of requirements")
    if form.deadline and form.deadline < date.today():
        raise ValueError("Deadline is in the past")
    if form.worker_mode == "manual" and not form.overrides:
        raise ValueError("Assign at least one role or department in manual mode")
    result = stage_intake(
        Intake(
            client_id=form.client_id,
            title=form.title,
            text=form.text,
            mode="live",
            budget_micro=form.budget_micro,
            deadline=str(form.deadline) if form.deadline else None,
            constraints={"technology": form.technology, "owner_constraints": form.constraints},
        ),
        user,
        session,
    )
    workflow = session.get(m.Workflow, result["workflow_id"])
    row.status, row.version = "submitted", row.version + 1
    row.data = {
        **row.data,
        "requirement_id": result["id"],
        "requirement_version": 1,
        "workflow_id": workflow.id,
        "submitted_at": now(),
        "selection_hash": digest(row.data["form"]),
    }
    if form.review_before_planning:
        from .requirements_refinement import initialize

        initialize(row, session.get(m.Requirement, result["id"]))
    for attachment in row.data["attachments"]:
        artifact = session.get(m.Artifact, attachment["id"])
        if (
            not artifact
            or artifact.org_id != row.org_id
            or artifact.sha256 != attachment["sha256"]
            or hashlib.sha256(artifact.content.encode()).hexdigest() != artifact.sha256
        ):
            raise PermissionError("Draft attachment integrity changed")
        session.add(
            m.BusinessRecord(
                org_id=row.org_id,
                client_id=row.client_id,
                kind="knowledge",
                title=artifact.name,
                data={
                    "requirement_id": result["id"],
                    "artifact_id": artifact.id,
                    "excerpt": artifact.content,
                    "trust": "untrusted uploaded requirements",
                    "provenance": attachment,
                },
            )
        )
    if form.planning_mode == "manual":
        workflow.status = "paused"
        session.get(m.Requirement, result["id"]).status = "awaiting_manual_plan"
    audit(
        session,
        row.org_id,
        user.id,
        "project_setup.submitted",
        row.id,
        {
            "requirement_id": result["id"],
            "selection_hash": row.data["selection_hash"],
            "mode": form.planning_mode,
        },
    )


def consulting_steps(session, requirement):
    row = for_requirement(session, requirement.id, requirement.org_id)
    if not row:
        return None
    roles = requirement.analysis.get("specialist_roles", [])
    if len(roles) != len(set(roles)) or any(role not in SPECIALISTS for role in roles):
        raise PermissionError("Lead AI proposed an invalid specialist allocation")
    return ["lead_intake", "Business Analyst", "CTO", *roles, "Project Manager", "CFO", "proposal"]


def attach_project_sources(session, project, requirement):
    """Exact proposal approval grants the approved requirement's documents to its project."""
    from .semantic_memory import sync_source

    records = list(
        session.scalars(
            select(m.BusinessRecord).where(
                m.BusinessRecord.org_id == project.org_id,
                m.BusinessRecord.client_id == project.client_id,
                m.BusinessRecord.kind == "knowledge",
                m.BusinessRecord.data["requirement_id"].as_string() == requirement.id,
            )
        )
    )
    for record in records:
        if record.project_id and record.project_id != project.id:
            raise PermissionError("Requirement knowledge already belongs to another project")
        record.project_id = project.id
        sync_source(session, record)
        artifact = (
            session.get(m.Artifact, record.data.get("artifact_id"))
            if record.data.get("artifact_id")
            else None
        )
        if artifact:
            if artifact.org_id != project.org_id or (
                artifact.project_id and artifact.project_id != project.id
            ):
                raise PermissionError("Requirement artifact is outside the approved project")
            artifact.project_id = project.id
            sync_source(session, artifact)


def manual_plan(session, row, user, architecture, milestones, criteria):
    from .consulting import proposal_content, publish
    from .schemas import Alternative, ProposalContent

    requirement = session.get(m.Requirement, row.data["requirement_id"])
    from .requirements_refinement import assert_approved, enabled

    assert_approved(session, requirement)
    workflow = session.get(m.Workflow, row.data["workflow_id"])
    if (
        workflow.status not in {"paused", "waiting_for_free_provider", "queued"}
        or requirement.version != row.data["requirement_version"]
        or (workflow.step != 2 if enabled(row) else workflow.step != 0)
        or session.scalar(select(m.ModelRun.id).where(m.ModelRun.workflow_id == workflow.id))
        or session.scalar(select(m.Proposal.id).where(m.Proposal.requirement_id == requirement.id))
    ):
        raise PermissionError("Existing analysis or changed requirements require a new plan revision")
    content = ProposalContent(
        executive_summary="Owner-authored plan; no AI-generated analysis",
        business_problem=requirement.text,
        confirmed_requirements=[requirement.text],
        assumptions=[],
        open_questions=[],
        current_architecture=architecture,
        alternatives=[
            Alternative(
                name="Owner-authored plan",
                architecture=architecture,
                advantages=["Explicit owner scope"],
                disadvantages=["Not independently analyzed by AI"],
                reliability="Unverified",
            )
        ],
        recommendation="Owner-authored plan",
        risks_and_mitigations=["Engineering and independent QA still required"],
        milestones=milestones,
        proposed_team=[],
        deliverables=milestones,
        acceptance_criteria=criteria,
        required_approvals=["Separate exact owner proposal approval", "Workforce and repository approvals"],
    )
    data = {**proposal_content(requirement, content, []), "authorship": "owner", "author_id": user.id}
    proposal = publish(session, requirement, data)
    workflow.status, workflow.lease_token = "cancelled", uid()
    row.version += 1
    row.data = {**row.data, "manual_proposal_id": proposal.id}
    audit(session, row.org_id, user.id, "project_setup.manual_plan", row.id, {"proposal_id": proposal.id})
    return proposal
