from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import closure, release
from .. import models as m
from ..api_common import serialize
from ..db import session_dependency
from ..schemas import Strict
from ..security import clean, digest, owner, scoped
from ..staffing import lock_org
from .package_operations import checked

router = APIRouter()


@router.get("/projects/{record_id}/delivery-state")
def delivery_state(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    project = scoped(session, m.Project, record_id, user)
    lifecycle = session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "delivery_lifecycle",
        )
    )
    plan = session.scalar(
        select(m.StaffingPlan).where(
            m.StaffingPlan.project_id == project.id, m.StaffingPlan.org_id == user.org_id
        )
    )
    tasks = list(
        session.scalars(select(m.Task).where(m.Task.org_id == user.org_id, m.Task.project_id == project.id))
    )
    stage = lifecycle.status if lifecycle else "planning"
    if not lifecycle and plan and plan.status == "active":
        stage = "workforce_allocated"
        if any(task.status not in {"ready", "awaiting_approval", "paused"} for task in tasks):
            stage = "implementation"
        if tasks and all(task.status == "completed" for task in tasks):
            stage = "final_review"
    if project.status == "paused":
        stage = "blocked"
    events = session.scalars(
        select(m.AuditEvent)
        .where(
            m.AuditEvent.org_id == user.org_id,
            m.AuditEvent.project_id == project.id,
            m.AuditEvent.action == "delivery.stage_changed",
        )
        .order_by(m.AuditEvent.created_at, m.AuditEvent.id)
    )
    return {
        "stage": stage,
        "recorded_transition": bool(lifecycle),
        "project_status": project.status,
        "timeline": [
            {"id": row.id, "created_at": row.created_at, "actor": row.actor, **row.detail} for row in events
        ],
    }


class ExactClosure(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    closure_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Close(ExactClosure):
    approval_id: str


class Reopen(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    reason: str = Field(min_length=20, max_length=2000)


@router.get("/projects/{record_id}/closure-readiness")
def readiness(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    project = scoped(session, m.Project, record_id, user)
    try:
        manifest = closure.readiness(session, project)
        return {
            "ready": True,
            "blockers": [],
            "manifest": manifest,
            "closure_hash": digest(manifest),
            "version": project.version,
        }
    except (PermissionError, KeyError, ValueError, OSError) as exc:
        return {
            "ready": False,
            "blockers": [str(exc) if isinstance(exc, PermissionError) else "Closure evidence is invalid"],
            "version": project.version,
        }


def command(session, user, record_id, data, action, execute):
    lock_org(session, user.org_id)
    session.expire_all()
    project = scoped(session, m.Project, record_id, user)
    request_hash = digest({"project_id": project.id, "action": action, **data.model_dump(mode="json")})
    previous = checked(lambda: release.command_result(session, user, data.request_id, request_hash))
    if previous:
        return previous
    if project.version != data.version:
        raise HTTPException(409, "Project revision changed; inspect current closure evidence")
    result = checked(lambda: execute(project))
    release.complete_command(session, user, data.request_id, request_hash, project.id, action, result)
    session.add(
        m.Notification(
            org_id=user.org_id, severity="info", title=action.replace(".", " "), subject_id=project.id
        )
    )
    session.commit()
    return result


@router.post("/projects/{record_id}/approve-closure")
def approve(
    record_id: str,
    data: ExactClosure,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.closure_approved",
        lambda project: {
            "id": project.id,
            "status": "closure_approved",
            "approval": serialize(
                closure.approve(
                    session, project, user, closure.readiness(session, project), data.closure_hash
                )
            ),
        },
    )


@router.post("/projects/{record_id}/close")
def close(
    record_id: str, data: Close, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.project_closed",
        lambda project: closure.close(
            session, project, user, data.closure_hash, data.approval_id, data.request_id
        ),
    )


@router.post("/projects/{record_id}/reopen")
def reopen(
    record_id: str,
    data: Reopen,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    def execute(project):
        if project.status != "closed":
            raise PermissionError("Only a closed project can be reopened")
        release.transition(
            session,
            project,
            "changes_requested",
            user.id,
            data.request_id,
            {"reopen_reason": clean(data.reason)},
        )
        project.status, project.version = "active", project.version + 1
        return {"id": project.id, "status": project.status, "version": project.version}

    return command(session, user, record_id, data, "delivery.project_reopened", execute)
