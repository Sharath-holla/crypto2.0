"""Owner-only DevOps controls, separate from the deterministic domain."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import deployments as d
from .. import models as m
from ..api_common import serialize
from ..db import now, session_dependency
from ..schemas import Strict
from ..security import audit, owner, scoped
from ..staffing import lock_org

router = APIRouter()


class ApprovalInput(Strict):
    version: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_seconds: int = Field(default=86400, ge=60, le=604800)


class RunInput(Strict):
    request_id: UUID
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CommandInput(Strict):
    action: Literal["pause", "resume", "cancel", "reconcile"]


def conflict(exc):
    return HTTPException(409, str(exc))


@router.get("/projects/{record_id}/deployments")
def evidence(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    project = scoped(session, m.Project, record_id, user)
    jobs = []
    for work in session.scalars(
        select(m.AgentWork).where(
            m.AgentWork.org_id == user.org_id,
            m.AgentWork.project_id == project.id,
            m.AgentWork.kind == "deployment",
        )
    ):
        workflow = session.get(m.Workflow, work.workflow_id)
        jobs.append({**serialize(work), "workflow": serialize(workflow)})
    plans = d.rows(session, project, "devops_plan")
    blockers = []
    for plan in plans:
        try:
            d.authority(session, plan)
        except (PermissionError, ValueError, KeyError, TypeError) as exc:
            blockers.append({"plan_id": plan.id, "reason": str(exc)})
    receipts = []
    for row in d.rows(session, project, "devops_receipt"):
        try:
            d.validate_receipt(session, project, row)
            valid = True
        except (PermissionError, ValueError, KeyError, TypeError):
            valid = False
        receipts.append({**serialize(row), "integrity_valid": valid})
    return {
        "classification": "SIMULATED_NONPRODUCTION",
        "live_deployment_available": False,
        "deployments_paused": session.get(m.Organization, user.org_id).deployments_paused,
        "release_blocker": "Actual approved production deployment and health evidence are not available. Simulation cannot release a client package.",
        "targets": [serialize(r) for r in d.rows(session, project, "devops_target")],
        "plans": [serialize(r) for r in plans],
        "jobs": jobs,
        "receipts": receipts,
        "incidents": [serialize(r) for r in d.rows(session, project, "devops_incident")],
        "blockers": blockers,
        "packages": [
            {
                "id": p.id,
                "version": p.version,
                "manifest_hash": p.manifest_hash,
                "status": p.status,
                "classification": p.classification,
            }
            for p in session.scalars(
                select(m.DeliveryPackage).where(
                    m.DeliveryPackage.project_id == project.id, m.DeliveryPackage.org_id == user.org_id
                )
            )
        ],
    }


@router.post("/projects/{record_id}/deployment-targets", status_code=201)
def target(
    record_id: str,
    data: d.TargetInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    try:
        row = d.create_target(session, project, user, data)
        session.commit()
        return serialize(row)
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None


@router.post("/projects/{record_id}/deployment-plans", status_code=201)
def plan(
    record_id: str,
    data: d.PlanInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    try:
        row = d.prepare(session, project, user, data)
        session.commit()
        return serialize(row)
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None


@router.post("/deployment-plans/{record_id}/approve")
def approve(
    record_id: str,
    data: ApprovalInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    row = scoped(session, m.BusinessRecord, record_id, user)
    if row.kind != "devops_plan":
        raise HTTPException(404, "Deployment plan not found")
    try:
        d.approve(session, row, user, data.version, data.manifest_hash, data.expires_seconds)
        session.commit()
        return serialize(row)
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None


@router.post("/deployment-plans/{record_id}/run", status_code=201)
def run(
    record_id: str,
    data: RunInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    row = scoped(session, m.BusinessRecord, record_id, user)
    if row.kind != "devops_plan":
        raise HTTPException(404, "Deployment plan not found")
    try:
        work = d.start(session, row, user, data.request_id, data.manifest_hash)
        session.commit()
        return {**serialize(work), "workflow": serialize(session.get(m.Workflow, work.workflow_id))}
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None


@router.post("/deployment-plans/{record_id}/revoke")
def revoke(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    row = scoped(session, m.BusinessRecord, record_id, user)
    if row.kind != "devops_plan":
        raise HTTPException(404, "Deployment plan not found")
    lock_org(session, user.org_id)
    session.refresh(row)
    approval = session.get(m.Approval, row.data["approval_id"]) if row.data.get("approval_id") else None
    if approval:
        approval.expires_at = now()
    work = session.get(m.AgentWork, row.data.get("dispatch_id")) if row.data.get("dispatch_id") else None
    if work:
        d.command(session, work, user, "cancel")
    row.status = "revoked"
    audit(session, user.org_id, user.id, "devops.approval_revoked", row.id, project_id=row.project_id)
    session.commit()
    return serialize(row)


@router.post("/deployments/{record_id}/commands")
def command(
    record_id: str,
    data: CommandInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    row = scoped(session, m.AgentWork, record_id, user)
    try:
        d.command(session, row, user, data.action)
        session.commit()
        return {**serialize(row), "workflow": serialize(session.get(m.Workflow, row.workflow_id))}
    except (PermissionError, ValueError) as exc:
        raise conflict(exc) from None
