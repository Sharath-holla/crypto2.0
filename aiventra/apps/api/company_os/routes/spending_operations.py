"""Owner-only local model inspection and explicit resumption of preserved work."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models as m
from .. import spending
from ..api_common import serialize
from ..db import now, session_dependency
from ..gateway import eligible_models, review_candidates
from ..model_routing import apply_policies
from ..providers import configured
from ..security import audit, owner, scoped

router = APIRouter()


@router.post("/models/{record_id}/verify-local")
async def verify_local(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    model = scoped(session, m.ModelConfig, record_id, user)
    provider = scoped(session, m.Provider, model.provider_id, user)
    if provider.kind != "ollama":
        raise HTTPException(409, "Remote inference is blocked; no zero-billing verifier is implemented")
    try:
        decision = await spending.authorize(provider, model)
    except spending.InferenceBlocked as exc:
        decision = exc.decision
    spending.record_local(session, provider, model, decision)
    audit(session, user.org_id, user.id, "model.local_verified", model.id, decision.public())
    session.commit()
    return spending.status(session, provider, model)


@router.post("/workflows/{record_id}/resume-free")
async def resume_free(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    workflow = scoped(session, m.Workflow, record_id, user)
    if workflow.status != "waiting_for_free_provider" or workflow.deadline_at <= now():
        raise HTTPException(409, "Only unexpired workflows waiting for a free model can resume")
    if session.scalar(
        select(m.ModelRun).where(
            m.ModelRun.workflow_id == workflow.id, m.ModelRun.status.in_(["started", "uncertain"])
        )
    ):
        raise HTTPException(409, "Reconcile uncertain usage before resuming")
    config = workflow.wait_context
    agent = scoped(session, m.Agent, config["agent_id"], user)
    if not agent.enabled:
        raise HTTPException(409, "Assigned employee disabled")
    candidates = eligible_models(
        session,
        user.org_id,
        workflow.mode,
        set(config["capabilities"]),
        config["quality"],
        config["sensitivity"],
        config["context_tokens"],
        config["policy"],
        config.get("task_class"),
    )
    from ..project_setup import routing

    try:
        override, pool, _ = routing(
            session,
            workflow,
            agent,
            config.get("step_name"),
            session.get(m.Project, config["project_id"]) if config.get("project_id") else None,
            config.get("model_override"),
        )
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    if pool is not None:
        candidates = [(model, provider) for model, provider in candidates if model.id in pool]
    candidates = apply_policies(session, agent, config.get("project_id"), candidates, override)
    from ..task_routing import constrain

    candidates = constrain(session, workflow, agent, candidates)
    candidates = review_candidates(
        session, candidates, config.get("review_against", []), config.get("review_policy", "prefer_provider")
    )
    for model, provider in candidates[:3]:
        if not configured(provider):
            continue
        try:
            decision = await spending.authorize(provider, model)
        except spending.InferenceBlocked:
            continue
        if provider.kind == "ollama":
            spending.record_local(session, provider, model, decision)
        changed = session.execute(
            update(m.Workflow)
            .where(m.Workflow.id == workflow.id, m.Workflow.status == "waiting_for_free_provider")
            .values(status="queued", lease_until=0, last_error="")
        )
        if not changed.rowcount:
            raise HTTPException(409, "Workflow changed; refresh before resuming")
        if workflow.task_id:
            session.get(m.Task, workflow.task_id).status = "in_progress"
        if workflow.requirement_id:
            session.get(m.Requirement, workflow.requirement_id).status = "queued"
        audit(
            session,
            user.org_id,
            user.id,
            "workflow.free_resume_authorized",
            workflow.id,
            {"model_id": model.id, "spending_mode": "ZERO_COST_ONLY"},
        )
        session.commit()
        session.refresh(workflow)
        return serialize(workflow)
    raise HTTPException(409, "No eligible verified local model; saved workflow remains waiting")
