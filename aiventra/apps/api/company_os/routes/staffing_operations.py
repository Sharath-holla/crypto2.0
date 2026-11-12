from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import staffing
from ..api_common import serialize
from ..db import now, session_dependency
from ..schemas import Strict
from ..security import audit, check_agent, clean, digest, owner, scoped
from ..task_routing import TaskRequirements, prepare

router = APIRouter()


class Allocation(Strict):
    agent_id: str
    slots: int = Field(ge=1, le=2)


class PlannedTask(TaskRequirements):
    key: str = Field(pattern=r"^[a-z0-9_-]{1,40}$")
    agent_id: str
    kind: Literal["document", "coding"]
    objective: str = Field(min_length=10, max_length=4000)
    acceptance: list[str] = Field(min_length=1, max_length=15)
    depends_on: list[str] = Field(max_length=32)
    foundation_ids: list[str] = Field(max_length=32)
    budget_micro: int = Field(ge=0, le=10**10)


class PlanContent(Strict):
    routing_mode: Literal["automatic", "manual", "hybrid"] = "automatic"
    planner: str = Field(
        pattern=r"^(policy-rules-v1 \(deterministic planning, no AI call\)|agent-chain:[a-f0-9-]{36})$"
    )
    requirement_version: int = Field(ge=1)
    proposal_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    mode: Literal["live", "mock"]
    concurrency: int = Field(ge=1, le=16)
    allocations: list[Allocation] = Field(min_length=1, max_length=16)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=32)
    foundation_task_ids: list[str] = Field(max_length=32)


class Revision(Strict):
    version: int = Field(ge=1)
    content: PlanContent


class Exact(Strict):
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/projects/{record_id}/staffing")
def get_plan(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    project = scoped(session, m.Project, record_id, user)
    plan = session.scalar(select(m.StaffingPlan).where(m.StaffingPlan.project_id == project.id))
    return staffing.evidence(session, plan) if plan else None


@router.post("/projects/{record_id}/staffing", status_code=201)
def propose(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    staffing.lock_org(session, user.org_id)
    project = scoped(session, m.Project, record_id, user)
    from ..workflows import project_authority

    try:
        project_authority(session, project)
        plan = staffing.suggest(session, project)
        session.commit()
        return staffing.evidence(session, plan)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.patch("/staffing/{record_id}")
def revise(
    record_id: str,
    data: Revision,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    staffing.lock_org(session, user.org_id)
    plan = scoped(session, m.StaffingPlan, record_id, user)
    if plan.status != "draft" or plan.version != data.version:
        raise HTTPException(409, "Only the current draft can be edited")
    content = clean(data.content.model_dump())
    if content["planner"] != plan.content["planner"]:
        raise HTTPException(422, "Planner provenance cannot be changed by editing the draft")
    try:
        staffing.validate(session, plan, content)
        prepare(session, plan, content)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from None
    plan.content, plan.content_hash, plan.version = content, digest(content), plan.version + 1
    session.add(
        m.StaffingRevision(
            org_id=plan.org_id,
            plan_id=plan.id,
            version=plan.version,
            content=content,
            content_hash=plan.content_hash,
        )
    )
    audit(
        session,
        user.org_id,
        user.id,
        "staffing.revised",
        plan.id,
        {"version": plan.version},
        project_id=plan.project_id,
    )
    session.commit()
    return staffing.evidence(session, plan)


@router.post("/staffing/{record_id}/approve")
def approve(
    record_id: str, data: Exact, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    staffing.lock_org(session, user.org_id)
    plan = scoped(session, m.StaffingPlan, record_id, user)
    if data.version != plan.version or data.content_hash != plan.content_hash:
        raise HTTPException(409, "Stale staffing scope")
    if plan.status in {"active", "paused"}:
        return staffing.evidence(session, plan)
    if plan.status != "draft":
        raise HTTPException(409, "Plan is not a draft")
    try:
        staffing.approve(session, plan, user)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from None
    session.commit()
    return staffing.evidence(session, plan)


class Control(Strict):
    action: Literal["pause", "resume"]


@router.post("/workflows/{record_id}/control")
def workflow_control(
    record_id: str,
    data: Control,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    staffing.lock_org(session, user.org_id)
    workflow = scoped(session, m.Workflow, record_id, user)
    work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == workflow.id))
    if work and work.kind == "deployment":
        from ..deployments import command

        try:
            command(session, work, user, data.action)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from None
        session.commit()
        return serialize(workflow)
    task = session.get(m.Task, workflow.task_id) if workflow.task_id else None
    plan = staffing.task_plan(session, task)
    if data.action == "resume" and plan and plan.status != "active":
        raise HTTPException(409, "Resume the staffing plan first")
    try:
        staffing.pause_workflow(session, workflow, data.action == "resume")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    audit(session, user.org_id, user.id, "workflow." + data.action, workflow.id, task_id=workflow.task_id)
    session.commit()
    return serialize(workflow)


@router.post("/staffing/{record_id}/control")
def plan_control(
    record_id: str,
    data: Control,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    staffing.lock_org(session, user.org_id)
    plan = scoped(session, m.StaffingPlan, record_id, user)
    resume = data.action == "resume"
    if plan.status != ("paused" if resume else "active"):
        raise HTTPException(409, "Plan cannot make this transition")
    tasks = [
        row
        for row in session.scalars(select(m.Task).where(m.Task.project_id == plan.project_id))
        if row.payload.get("staffing_plan_id") == plan.id
    ]
    paused_tasks = dict(plan.runtime.get("paused_tasks", {}))
    try:
        for task in tasks:
            workflow = session.scalar(select(m.Workflow).where(m.Workflow.task_id == task.id))
            if workflow:
                if (resume and workflow.id in plan.runtime.get("paused_workflows", [])) or (
                    not resume and workflow.status not in {"paused", "cancelled", "completed"}
                ):
                    staffing.pause_workflow(session, workflow, resume)
                    if not resume:
                        paused_tasks[workflow.id] = "workflow"
            elif resume and task.id in paused_tasks and task.status == "paused":
                task.status = paused_tasks[task.id]
            elif not resume and task.status not in {"completed", "cancelled", "failed", "paused"}:
                paused_tasks[task.id], task.status = task.status, "paused"
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    plan.runtime = (
        {}
        if resume
        else {
            "paused_tasks": paused_tasks,
            "paused_workflows": [key for key, value in paused_tasks.items() if value == "workflow"],
        }
    )
    plan.status = "active" if resume else "paused"
    audit(session, user.org_id, user.id, "staffing." + data.action, plan.id, project_id=plan.project_id)
    session.commit()
    return staffing.evidence(session, plan)


class Reassign(Strict):
    version: int = Field(ge=1)
    agent_id: str
    reason: str = Field(min_length=5, max_length=1000)


@router.post("/tasks/{record_id}/assign")
def reassign(
    record_id: str,
    data: Reassign,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    staffing.lock_org(session, user.org_id)
    task = scoped(session, m.Task, record_id, user)
    plan = staffing.task_plan(session, task)
    if not plan or plan.status != "active" or task.version != data.version or task.kind != "document":
        raise HTTPException(409, "Only current approved unexecuted document assignments can change")
    agent = scoped(session, m.Agent, data.agent_id, user)
    if agent.id not in {row["agent_id"] for row in plan.content["allocations"]}:
        raise HTTPException(422, "Agent is outside the approved allocation")
    workflow = session.scalar(select(m.Workflow).where(m.Workflow.task_id == task.id))
    if task.status in {"completed", "cancelled", "failed"} or (
        workflow
        and (
            workflow.status in {"running", "paused"}
            or workflow.step
            or session.scalar(select(m.ModelRun.id).where(m.ModelRun.workflow_id == workflow.id))
        )
    ):
        raise HTTPException(
            409, "Started/paid work cannot be reassigned; create an explicitly approved follow-up"
        )
    previous = session.get(m.Agent, task.assigned_agent_id)
    if agent.department_id != previous.department_id:
        raise HTTPException(422, "Reassignment must preserve the approved department skill")
    try:
        check_agent(session, agent, "write_artifact", session.get(m.Project, task.project_id))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    session.add(
        m.TaskAssignment(
            org_id=user.org_id,
            task_id=task.id,
            previous_agent_id=task.assigned_agent_id,
            agent_id=agent.id,
            owner_id=user.id,
            reason=clean(data.reason),
        )
    )
    task.assigned_agent_id, task.version = agent.id, task.version + 1
    if workflow:
        workflow.wait_context, workflow.status, workflow.lease_until = {}, "queued", 0
        workflow.deadline_at = max(workflow.deadline_at, now() + 1800)
    audit(
        session,
        user.org_id,
        user.id,
        "task.reassigned",
        task.id,
        {"agent_id": agent.id, "reason": clean(data.reason)},
        project_id=task.project_id,
        task_id=task.id,
    )
    session.commit()
    return serialize(task)
