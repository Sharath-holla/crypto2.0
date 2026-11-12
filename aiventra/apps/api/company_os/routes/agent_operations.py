from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..agent_runtime import snapshot, transition
from ..api_common import serialize
from ..config import settings
from ..db import session_dependency, uid
from ..memory import retrieve
from ..organization import agent_for
from ..schemas import Strict
from ..security import audit, check_agent, clean, digest, owner, scoped
from ..workflows import project_authority

router = APIRouter()


class WorkInput(Strict):
    request_id: UUID
    mode: Literal["live", "mock"] = "live"
    budget_micro: int = Field(default=500000, ge=1000, le=50000000)
    model_override: str | None = None


class MessageInput(WorkInput):
    project_id: str
    sender_id: str
    recipient_id: str
    type: Literal[
        "TaskAssigned", "QuestionAsked", "ReviewRequested", "EscalationRaised", "ArtifactShared"
    ] = "TaskAssigned"
    body: str = Field(min_length=10, max_length=12000)
    artifact_ids: list[str] = Field(default_factory=list, max_length=5)
    reply_to: str | None = None


class MeetingInput(WorkInput):
    project_id: str
    participant_ids: list[str] = Field(min_length=2, max_length=8)
    agenda: str = Field(min_length=10, max_length=12000)
    rounds: int = Field(default=1, ge=1, le=2)
    create_followups: bool = False


class ProbeInput(Strict):
    request_id: UUID
    model_id: str
    budget_micro: int = Field(default=100000, ge=1000, le=1000000)


class ToolsInput(WorkInput):
    project_id: str
    agent_id: str
    peer_ids: list[str] = Field(default_factory=list, max_length=8)
    objective: str = Field(min_length=10, max_length=12000)


class BenchmarkInput(ProbeInput):
    budget_micro: int = Field(default=1000000, ge=1000, le=5000000)


class PlanningInput(WorkInput):
    project_id: str
    plan_version: int = Field(ge=1)
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    objective: str = Field(min_length=10, max_length=2000)


def approved_project(session: Session, project_id: str, user: m.User):
    project = scoped(session, m.Project, project_id, user)
    try:
        project_authority(session, project)
        if project.status != "active":
            raise PermissionError("Project must be active")
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    return project


def authorized_agent(session: Session, record_id: str, user: m.User, project=None, tool="read_context"):
    agent = scoped(session, m.Agent, record_id, user)
    try:
        check_agent(session, agent, tool, project)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    return agent


def existing_work(session: Session, request_id: UUID, user: m.User, request_hash: str):
    existing = session.get(m.AgentWork, str(request_id))
    if existing:
        if existing.org_id != user.org_id:
            raise HTTPException(404, "Agent work not found")
        if existing.request_hash != request_hash:
            raise HTTPException(409, "Request ID already used for different agent work")
        return {
            "work": serialize(existing),
            "workflow": serialize(session.get(m.Workflow, existing.workflow_id)),
        }


def enqueue(
    session: Session,
    user: m.User,
    data,
    kind,
    subject,
    participants,
    work_input,
    project=None,
    request_hash=None,
):
    mode = getattr(data, "mode", "live")
    if mode == "mock" and not settings().mock_enabled:
        raise HTTPException(403, "Local fixture execution disabled")
    override = work_input.get("model_override")
    if override:
        scoped(session, m.ModelConfig, override, user)
    workflow = m.Workflow(id=uid(), org_id=user.org_id, kind="agent_work", mode=mode)
    work = m.AgentWork(
        id=str(data.request_id),
        org_id=user.org_id,
        workflow_id=workflow.id,
        project_id=project.id if project else None,
        kind=kind,
        subject_id=subject,
        request_hash=request_hash or digest(data.model_dump(mode="json")),
        participants=participants,
        input=clean(work_input),
    )
    request_hash = work.request_hash
    try:
        session.add(workflow)
        session.flush()
        session.add(work)
        session.add(m.Budget(org_id=user.org_id, scope=f"job:{work.id}", limit_micro=data.budget_micro))
        for agent_id in participants:
            transition(session, workflow, session.get(m.Agent, agent_id), "ASSIGNED", kind)
        audit(
            session,
            user.org_id,
            user.id,
            "agent_work.queued",
            work.id,
            {"kind": kind, "mode": mode, "participants": participants, "budget_micro": data.budget_micro},
            project_id=work.project_id,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        result = existing_work(session, data.request_id, user, request_hash)
        if result:
            return result
        raise HTTPException(409, "Agent work changed; refresh and retry") from None
    return {"work": serialize(work), "workflow": serialize(workflow)}


@router.get("/agents/runtime")
def runtime(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return snapshot(session, user.org_id)


@router.post("/agent-planning", status_code=201)
def start_planning(
    data: PlanningInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    previous = existing_work(session, data.request_id, user, digest(data.model_dump(mode="json")))
    if previous:
        return previous
    project = approved_project(session, data.project_id, user)
    from ..planning import ROLES
    from ..staffing import lock_org

    lock_org(session, user.org_id)
    plan = session.scalar(select(m.StaffingPlan).where(m.StaffingPlan.project_id == project.id))
    if (
        not plan
        or plan.status != "draft"
        or plan.version != data.plan_version
        or plan.content_hash != data.plan_hash
    ):
        raise HTTPException(409, "Select the current unapproved workforce draft")
    agents = [agent_for(session, user.org_id, role) for role in ROLES]
    for agent in agents:
        authorized_agent(session, agent.id, user, project, "write_artifact")
    return enqueue(
        session,
        user,
        data,
        "planning",
        plan.id,
        [a.id for a in agents],
        {
            "objective": data.objective,
            "plan_version": plan.version,
            "plan_hash": plan.content_hash,
            "model_override": data.model_override,
        },
        project=project,
    )


@router.post("/agent-tool-jobs", status_code=201)
def start_tools(
    data: ToolsInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    previous = existing_work(session, data.request_id, user, digest(data.model_dump(mode="json")))
    if previous:
        return previous
    if data.mode != "live":
        raise HTTPException(422, "Native tools require live mode; deterministic adapter tests are separate")
    project = approved_project(session, data.project_id, user)
    agent = authorized_agent(session, data.agent_id, user, project, "write_artifact")
    if len(set(data.peer_ids)) != len(data.peer_ids) or agent.id in data.peer_ids:
        raise HTTPException(422, "Choose distinct peer agents")
    peers = [
        authorized_agent(session, record_id, user, project, "write_artifact") for record_id in data.peer_ids
    ]
    return enqueue(
        session,
        user,
        data,
        "tools",
        agent.id,
        [agent.id],
        {
            "objective": data.objective,
            "peer_agents": [{"id": a.id, "name": a.name} for a in peers],
            "model_override": data.model_override,
        },
        project=project,
    )


@router.post("/model-benchmarks", status_code=201)
def start_benchmark(
    data: BenchmarkInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    from ..benchmarks import SUITE, fingerprint

    previous = existing_work(session, data.request_id, user, digest(data.model_dump(mode="json")))
    if previous:
        return previous
    model = scoped(session, m.ModelConfig, data.model_id, user)
    provider = scoped(session, m.Provider, model.provider_id, user)
    if provider.kind == "mock":
        raise HTTPException(422, "Benchmarks require a real-provider registry entry")
    agent = agent_for(session, user.org_id, "CEO")
    authorized_agent(session, agent.id, user)
    return enqueue(
        session,
        user,
        data,
        "benchmark",
        model.id,
        [agent.id],
        {
            "model_override": model.id,
            "suite_version": SUITE,
            "fingerprint": fingerprint(session, model, provider),
        },
    )


@router.get("/model-recommendations")
def recommendations(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    from ..benchmarks import current_profile
    from ..gateway import eligible_models
    from ..providers import configured

    result = {}
    for policy in ("economy", "balanced", "quality"):
        candidates = [
            (model, provider)
            for model, provider in eligible_models(
                session, user.org_id, "live", {"structured"}, 70, "internal", 8192, policy
            )
            if configured(provider) and current_profile(session, model, provider)
        ]
        if candidates:
            model, provider = candidates[0]
            profile = current_profile(session, model, provider)
            result[policy] = {
                "model_id": model.id,
                "metrics": profile.metrics,
                "reason": f"{policy}: current measured profile, structured/internal, quality >=70, context >=8192, fresh registered prices; job-specific scope/caps are rechecked",
            }
        else:
            result[policy] = {
                "model_id": None,
                "reason": "No measured, configured model meets the current default advice constraints",
            }
    result["manual"] = {
        "model_id": None,
        "reason": "Use an exact job override or the employee's selected model preference; no automatic fallback",
    }
    return result


@router.post("/agent-work/{record_id}/cancel")
def cancel_work(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    work = scoped(session, m.AgentWork, record_id, user)
    if work.kind == "deployment":
        from ..deployments import command

        try:
            command(session, work, user, "cancel")
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from None
        session.commit()
        return serialize(work)
    session.execute(
        update(m.Organization).where(m.Organization.id == user.org_id).values(paused=m.Organization.paused)
    )
    session.execute(
        update(m.Workflow).where(m.Workflow.id == work.workflow_id).values(lease_until=m.Workflow.lease_until)
    )
    workflow = session.get(m.Workflow, work.workflow_id)
    children = [
        task
        for task in session.scalars(
            select(m.Task).where(m.Task.org_id == user.org_id, m.Task.project_id == work.project_id)
        )
        if task.payload.get("job_id") == work.id and task.status not in {"completed", "cancelled", "failed"}
    ]
    if workflow.status == "cancelled" or (workflow.status == "completed" and not children):
        raise HTTPException(409, "Agent work already finished")
    session.execute(
        update(m.Workflow)
        .where(m.Workflow.id == workflow.id)
        .values(status="cancelled", lease_until=0, lease_token=uid())
    )
    from ..agent_runtime import workflow_state

    workflow_state(
        session, workflow, "BLOCKED", {"reason": "owner cancelled; in-flight usage may still be charged"}
    )
    if work.kind == "delivery":
        review = session.get(m.BusinessRecord, work.subject_id)
        if review and review.org_id == work.org_id and review.kind == "delivery_review":
            review.status = "cancelled"
            review.version += 1
            work.result = {
                **work.result,
                "status": "cancelled",
                "delivery_released": False,
                "client_accepted": False,
            }
    for task in children:
        task.status = "cancelled"
        child = session.scalar(select(m.Workflow).where(m.Workflow.task_id == task.id))
        if child:
            child.status, child.lease_until, child.lease_token = "cancelled", 0, uid()
            workflow_state(session, child, "BLOCKED", {"reason": "owner cancelled parent job"})
    audit(session, user.org_id, user.id, "agent_work.cancelled", work.id, project_id=work.project_id)
    session.commit()
    return serialize(workflow)


@router.post("/agent-messages", status_code=201)
def send_message(
    data: MessageInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    previous = existing_work(session, data.request_id, user, digest(data.model_dump(mode="json")))
    if previous:
        return previous
    project = approved_project(session, data.project_id, user)
    authorized_agent(session, data.sender_id, user, project)
    authorized_agent(session, data.recipient_id, user, project, "write_artifact")
    if data.sender_id == data.recipient_id:
        raise HTTPException(422, "Choose distinct sender and recipient agents")
    for record_id in data.artifact_ids:
        artifact = scoped(session, m.Artifact, record_id, user)
        if artifact.project_id != project.id or artifact.conversation_id:
            raise HTTPException(403, "Message attachment must belong to this project")
    hop, correlation = 0, uid()
    if data.reply_to:
        parent = scoped(session, m.Message, data.reply_to, user)
        if (
            parent.project_id != project.id
            or data.sender_id != parent.recipient
            or data.recipient_id != parent.sender
        ):
            raise HTTPException(403, "Reply participants and project must match the parent message")
        hop, correlation = int(parent.content.get("hop", 0)) + 1, parent.correlation_id
        if hop > 2:
            raise HTTPException(409, "Conversation hop limit reached; start a new owner-directed task")
    message = m.Message(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        sender=data.sender_id,
        recipient=data.recipient_id,
        type=data.type,
        correlation_id=correlation,
        status="queued",
        expected_schema="DocumentResult",
        authorization="explicit owner-directed read-only artifact task",
        content=clean(
            {
                "body": data.body,
                "artifact_ids": data.artifact_ids,
                "hop": hop,
                "reply_to": data.reply_to,
                "mode": data.mode,
            }
        ),
    )
    session.add(message)
    return enqueue(
        session,
        user,
        data,
        "message",
        message.id,
        [data.recipient_id],
        {
            "body": data.body,
            "artifact_ids": data.artifact_ids,
            "hop": hop,
            "model_override": data.model_override,
        },
        project,
    )


@router.post("/agent-meetings", status_code=201)
def start_meeting(
    data: MeetingInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    previous = existing_work(session, data.request_id, user, digest(data.model_dump(mode="json")))
    if previous:
        return previous
    project = approved_project(session, data.project_id, user)
    if len(set(data.participant_ids)) != len(data.participant_ids):
        raise HTTPException(422, "Meeting participants must be distinct")
    for agent_id in data.participant_ids:
        authorized_agent(
            session, agent_id, user, project, "write_artifact" if data.create_followups else "read_context"
        )
    coordinator = agent_for(session, user.org_id, "CEO")
    authorized_agent(session, coordinator.id, user, project)
    meeting = m.Meeting(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        agenda=clean(data.agenda),
        mode=data.mode,
        rounds=data.rounds,
    )
    session.add(meeting)
    return enqueue(
        session,
        user,
        data,
        "meeting",
        meeting.id,
        data.participant_ids,
        {
            "create_followups": data.create_followups,
            "model_override": data.model_override,
            "memory_snapshot": retrieve(session, user.org_id, project.id),
        },
        project,
    )


@router.post("/providers/{record_id}/inference-probe", status_code=201)
def inference_probe(
    record_id: str,
    data: ProbeInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    request_hash = digest({**data.model_dump(mode="json"), "provider_id": record_id})
    previous = existing_work(session, data.request_id, user, request_hash)
    if previous:
        return previous
    provider = scoped(session, m.Provider, record_id, user)
    model = scoped(session, m.ModelConfig, data.model_id, user)
    if provider.kind == "mock" or model.provider_id != provider.id:
        raise HTTPException(422, "Choose a live model belonging to this provider")
    agent = agent_for(session, user.org_id, "CEO")
    authorized_agent(session, agent.id, user)
    # Include provider identity in idempotency even when two providers reuse model names.
    return enqueue(
        session,
        user,
        data,
        "probe",
        provider.id,
        [agent.id],
        {"model_override": model.id},
        request_hash=request_hash,
    )
