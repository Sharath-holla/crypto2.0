"""Owner-scoped QA commands. Generic business-record updates confer no authority."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import quality
from ..api_common import serialize
from ..db import now, session_dependency
from ..organization import agent_for
from ..schemas import Strict
from ..security import audit, check_agent, clean, digest, owner, scoped
from ..staffing import lock_org
from .agent_operations import WorkInput, approved_project, enqueue, existing_work

router = APIRouter()


class Exact(Strict):
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RunInput(WorkInput):
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RepairInput(Strict):
    request_id: UUID
    objective: str = Field(min_length=10, max_length=2000)


class DefectCommand(Strict):
    version: int = Field(ge=1)
    action: Literal["assign", "reopen", "verify_close"]
    developer_id: str | None = None
    resolution: str = Field(default="", max_length=2000)


def record(session, record_id, user, kind):
    row = scoped(session, m.BusinessRecord, record_id, user)
    if row.kind != kind:
        raise HTTPException(404, "QA record not found")
    return row


def conflict(exc):
    return HTTPException(409, str(exc))


@router.get("/tasks/{record_id}/quality-source")
def source(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    try:
        _, manifest = quality.source(session, scoped(session, m.Task, record_id, user))
        return {
            "source": manifest,
            "source_hash": digest(manifest),
            "checks": quality.CHECKS,
            "automatic_checks": quality.AUTOMATIC,
            "profile": "python-qa-v1",
        }
    except PermissionError as exc:
        raise conflict(exc) from None


@router.get("/projects/{record_id}/quality")
def evidence(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    project = scoped(session, m.Project, record_id, user)
    jobs = []
    for work in session.scalars(
        select(m.AgentWork).where(
            m.AgentWork.org_id == user.org_id,
            m.AgentWork.project_id == project.id,
            m.AgentWork.kind == "quality",
        )
    ):
        workflow = session.get(m.Workflow, work.workflow_id)
        executions = [
            session.get(m.Execution, saved["execution_id"])
            for saved in work.result.get("executions", {}).values()
        ]
        jobs.append(
            {
                "id": work.id,
                "plan_id": work.subject_id,
                "workflow_id": workflow.id,
                "status": workflow.status,
                "step": workflow.step,
                "last_error": workflow.last_error,
                "executions": [
                    {"id": execution.id, "status": execution.status, "exit_code": execution.exit_code}
                    for execution in executions
                    if execution
                ],
            }
        )
    return {
        "readiness": quality.readiness(session, project),
        "plans": [serialize(r) for r in quality.rows(session, project, "quality_plan")],
        "reports": [serialize(r) for r in quality.rows(session, project, "quality_report")],
        "defects": [serialize(r) for r in quality.rows(session, project, "quality_defect")],
        "jobs": jobs,
    }


@router.post("/tasks/{record_id}/quality-plans", status_code=201)
def prepare(
    record_id: str,
    data: quality.PlanInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    try:
        plan = quality.prepare(session, scoped(session, m.Task, record_id, user), user, data)
        session.commit()
        return serialize(plan)
    except PermissionError as exc:
        raise conflict(exc) from None


@router.post("/quality-plans/{record_id}/approve")
def approve(
    record_id: str, data: Exact, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    try:
        plan = record(session, record_id, user, "quality_plan")
        quality.approve(session, plan, user, data.version, data.content_hash)
        session.commit()
        return serialize(plan)
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None


@router.post("/quality-plans/{record_id}/run", status_code=201)
def run(
    record_id: str,
    data: RunInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    fingerprint = digest({"plan_id": record_id, **data.model_dump(mode="json")})
    previous = existing_work(session, data.request_id, user, fingerprint)
    if previous:
        return previous
    lock_org(session, user.org_id)
    plan = record(session, record_id, user, "quality_plan")
    try:
        project, task, _ = quality.authority(session, plan)
        if data.plan_hash != plan.data["plan_hash"] or data.mode != task.payload.get("mode"):
            raise PermissionError("Exact QA plan and candidate execution mode are required")
        for work in session.scalars(
            select(m.AgentWork).where(
                m.AgentWork.org_id == user.org_id,
                m.AgentWork.kind == "quality",
                m.AgentWork.subject_id == plan.id,
            )
        ):
            workflow = session.get(m.Workflow, work.workflow_id)
            if workflow.status not in {"completed", "failed", "cancelled"}:
                raise PermissionError("A QA run for this plan is already active; use its recovery controls")
            for saved in work.result.get("executions", {}).values():
                execution = session.get(m.Execution, saved["execution_id"])
                if execution and execution.status == "running":
                    raise PermissionError("Reconcile interrupted QA execution before starting another run")
        participants = [agent_for(session, user.org_id, role) for role in quality.ROLES]
        for agent in participants:
            if agent.id == task.assigned_agent_id:
                raise PermissionError("Developer cannot independently verify own candidate")
            check_agent(session, agent, "write_artifact", project)
        return enqueue(
            session,
            user,
            data,
            "quality",
            plan.id,
            [a.id for a in participants],
            {
                "plan_hash": plan.data["plan_hash"],
                "source_hash": plan.data["source_hash"],
                "model_override": data.model_override,
            },
            project=project,
            request_hash=fingerprint,
        )
    except PermissionError as exc:
        raise conflict(exc) from None


@router.post("/quality-defects/{record_id}/repair", status_code=201)
def repair(
    record_id: str,
    data: RepairInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    try:
        task = quality.repair(
            session,
            record(session, record_id, user, "quality_defect"),
            user,
            str(data.request_id),
            data.objective,
        )
        session.commit()
        return serialize(task)
    except quality.RepairEscalation as exc:
        session.commit()
        raise conflict(exc) from None
    except PermissionError as exc:
        raise conflict(exc) from None


@router.post("/quality-defects/{record_id}/commands")
def defect_command(
    record_id: str,
    data: DefectCommand,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    row = record(session, record_id, user, "quality_defect")
    session.refresh(row)
    project = approved_project(session, row.project_id, user)
    if row.version != data.version:
        raise HTTPException(409, "Defect changed; review its current version")
    changes = {}
    try:
        if data.action == "assign":
            agent = scoped(session, m.Agent, data.developer_id or "", user)
            check_agent(session, agent, "propose_patch", project)
            changes = {"assigned_developer": agent.id}
        elif data.action == "reopen":
            if len(data.resolution.strip()) < 10:
                raise PermissionError("Explain why the defect is reopened")
            row.status, changes = (
                "reopened",
                {"verification": "unverified", "resolution": clean(data.resolution)},
            )
        else:
            if len(data.resolution.strip()) < 10:
                raise PermissionError("A resolution and fresh independent verification are required")
            verified = quality.repair_verification(session, project, row)
            row.status, changes = (
                "closed",
                {
                    "verification": "verified",
                    "resolution": clean(data.resolution),
                    "verified_evidence": verified,
                },
            )
        row.data = {
            **row.data,
            **changes,
            "history": [
                *row.data["history"],
                {"action": data.action, "actor": user.id, "at": now(), "changes": changes},
            ],
        }
        row.version += 1
        audit(
            session,
            user.org_id,
            user.id,
            "quality.defect_" + data.action,
            row.id,
            changes,
            project_id=project.id,
        )
        session.commit()
        return serialize(row)
    except PermissionError as exc:
        raise conflict(exc) from None


@router.post("/projects/{record_id}/quality-readiness", status_code=201)
def freeze(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    lock_org(session, user.org_id)
    project = approved_project(session, record_id, user)
    row = quality.freeze_readiness(session, project, user)
    session.commit()
    return serialize(row)
