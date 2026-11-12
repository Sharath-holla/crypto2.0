"""Read-only model readiness and project evidence, separate from execution authority."""

from sqlalchemy import select

from . import models as m
from .config import settings
from .db import now
from .execution_evidence import WAIT_MESSAGE, workflow_view
from .model_catalog import view as catalog_view
from .project_setup import FAVORITE, for_requirement, lead_status


def overview(session, org_id):
    catalog = catalog_view(session, org_id)
    models = catalog["models"]
    eligible = [row for row in models if row["eligibility"]["allowed"]]
    resource_wait = next(
        (
            row["eligibility"]["reason"]
            for row in models
            if row["eligibility"]["state"] == "LOCAL_RESOURCES_BLOCKED"
        ),
        "",
    )
    return {
        "checked_at": now(),
        "spending_mode": settings().ai_spending_mode,
        "database": session.get_bind().dialect.name,
        "providers": catalog["providers"],
        "registered_models": len(models),
        "eligible_models": len(eligible),
        "live_verified_models": len([row for row in models if row["live_inference_at"]]),
        "execution_enabled": settings().execution_enabled,
        "state": "MODEL_AVAILABLE"
        if eligible
        else "WAITING_FOR_LOCAL_RESOURCES"
        if resource_wait
        else "WAITING_FOR_ELIGIBLE_MODEL",
        "message": "An eligible registered model is available; each task still requires authorization."
        if eligible
        else resource_wait or WAIT_MESSAGE,
        "setup_message": "Your providers are not connected. Open Settings to securely connect OpenAI, Grok or DeepSeek."
        if not any(row["configured"] for row in catalog["providers"])
        else "A connected provider and successful discovery do not establish free inference eligibility.",
        "preferred_lead": FAVORITE,
        "check_invokes_inference": False,
    }


def project_view(session, project, draft=None):
    proposal = session.get(m.Proposal, project.proposal_id) if project else None
    draft = draft or for_requirement(session, proposal.requirement_id, project.org_id)
    org_id = project.org_id if project else draft.org_id
    requirement_id = proposal.requirement_id if proposal else draft.data.get("requirement_id")
    task_ids = (
        select(m.Task.id).where(m.Task.org_id == org_id, m.Task.project_id == project.id) if project else None
    )
    filters = []
    if requirement_id:
        filters.append(m.Workflow.requirement_id == requirement_id)
    if task_ids is not None:
        filters.append(m.Workflow.task_id.in_(task_ids))
        filters.append(
            m.Workflow.id.in_(
                select(m.AgentWork.workflow_id).where(
                    m.AgentWork.org_id == org_id, m.AgentWork.project_id == project.id
                )
            )
        )
    from sqlalchemy import or_

    workflows = (
        list(
            session.scalars(
                select(m.Workflow)
                .where(m.Workflow.org_id == org_id, or_(*filters))
                .order_by(m.Workflow.created_at.desc(), m.Workflow.id)
                .limit(50)
            )
        )
        if filters
        else []
    )
    form = draft.data["form"] if draft else None
    return {
        "project_id": project.id if project else None,
        "draft_id": draft.id if draft else None,
        "preferred_lead": FAVORITE,
        "selected_lead_id": form["lead_model_id"] if form else None,
        "lead_status": lead_status(session, form)
        if form
        else {
            "state": "NOT_SELECTED",
            "allowed": False,
            "reason": "No wizard Lead preference is saved for this legacy project",
        },
        "worker_mode": form["worker_mode"] if form else "automatic",
        "worker_model_ids": form["worker_model_ids"] if form else [],
        "overrides": form["overrides"] if form else {},
        "selection_history": draft.data.get("selection_history", []) if draft else [],
        "workflows": [workflow_view(session, workflow) for workflow in workflows],
        "history_limit": 50,
        "model_authorization": "Preferences never authorize inference, repository changes, publication or release",
    }
