from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import client_responses, delivery_cases, release
from .. import models as m
from ..api_common import serialize
from ..config import settings
from ..db import session_dependency
from ..schemas import Strict
from ..security import audit, clean, digest, owner, scoped
from ..staffing import lock_org
from .package_operations import checked

router = APIRouter()


@router.get("/delivery-cases/{record_id}/attachments/{content_hash}")
def attachment(
    record_id: str,
    content_hash: str,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    case = scoped(session, m.BusinessRecord, record_id, user)
    if case.kind != "delivery_case":
        raise HTTPException(404, "Client case is unavailable")
    body = checked(lambda: client_responses.attachment(session, case, content_hash))
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.owner_attachment_downloaded",
        case.id,
        {"sha256": content_hash},
        project_id=case.project_id,
    )
    session.commit()
    return Response(
        body,
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": 'attachment; filename="client-evidence.txt"',
        },
    )


class CaseExact(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    case_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class Analyze(CaseExact):
    mode: Literal["mock", "live"] = "live"
    budget_micro: int = Field(ge=0, le=10**10, default=500000)


class Impact(Strict):
    summary: str = Field(min_length=20, max_length=2000)
    components: list[str] = Field(min_length=1, max_length=20)
    acceptance: list[str] = Field(min_length=1, max_length=20)
    budget_micro: int = Field(ge=0, le=10**10)


class Scope(CaseExact):
    analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    impact: Impact


class Assign(CaseExact):
    task_ids: list[str] = Field(min_length=1, max_length=10)


class Resolve(CaseExact):
    public_resolution: str = Field(min_length=20, max_length=4000)


class Revise(CaseExact):
    reason: str = Field(min_length=20, max_length=2000)


class FollowUpTask(Strict):
    kind: Literal["document", "coding"]
    component: str = Field(min_length=1, max_length=200)
    role: Literal["Business Analyst", "Project Manager", "CTO", "Security Architect", "QA Director"] = (
        "Project Manager"
    )
    budget_micro: int = Field(ge=0, le=10**10)
    repository_id: str | None = None
    test_suite: Literal["python-unittest", "node-test"] = "python-unittest"


class CreateWork(CaseExact):
    tasks: list[FollowUpTask] = Field(min_length=1, max_length=10)


@router.get("/projects/{record_id}/delivery-cases")
def cases(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    scoped(session, m.Project, record_id, user)
    return [
        {**serialize(row), "case_hash": delivery_cases.case_hash(row)}
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.org_id == user.org_id,
                m.BusinessRecord.project_id == record_id,
                m.BusinessRecord.kind == "delivery_case",
            )
            .order_by(m.BusinessRecord.created_at.desc())
        )
    ]


def command(session, user, record_id, data, action, execute):
    lock_org(session, user.org_id)
    session.expire_all()
    case = scoped(session, m.BusinessRecord, record_id, user)
    if case.kind != "delivery_case":
        raise HTTPException(404, "Delivery case not found")
    request_hash = digest({"case_id": case.id, "action": action, **data.model_dump(mode="json")})
    previous = checked(lambda: release.command_result(session, user, data.request_id, request_hash))
    if previous:
        return previous
    if case.version != data.version or delivery_cases.case_hash(case) != data.case_hash:
        raise HTTPException(409, "Case changed; inspect its current version and impact before acting")
    result = checked(lambda: execute(case))
    release.complete_command(session, user, data.request_id, request_hash, case.project_id, action, result)
    session.add(
        m.Notification(
            org_id=user.org_id, severity="info", title=f"Delivery case {result['status']}", subject_id=case.id
        )
    )
    session.commit()
    return result


@router.post("/delivery-cases/{record_id}/analyze")
def analyze(
    record_id: str,
    data: Analyze,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    if data.mode == "mock" and not settings().mock_enabled:
        raise HTTPException(403, "Deterministic test adapter is disabled")
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_analysis",
        lambda case: delivery_cases.analyze(session, case, user, data.mode, data.budget_micro),
    )


@router.post("/delivery-cases/{record_id}/approve-scope")
def approve_scope(
    record_id: str, data: Scope, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_scope_approved",
        lambda case: delivery_cases.approve_scope(
            session, case, user, clean(data.impact.model_dump()), data.analysis_sha256
        ),
    )


@router.post("/delivery-cases/{record_id}/assign")
def assign(
    record_id: str,
    data: Assign,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    if len(set(data.task_ids)) != len(data.task_ids):
        raise HTTPException(422, "Follow-up task IDs must be unique")
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_work_assigned",
        lambda case: delivery_cases.assign(session, case, data.task_ids),
    )


@router.post("/delivery-cases/{record_id}/resolve")
def resolve(
    record_id: str,
    data: Resolve,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_resolved",
        lambda case: delivery_cases.resolve(session, case, clean(data.public_resolution)),
    )


@router.post("/delivery-cases/{record_id}/create-work")
def create_work(
    record_id: str,
    data: CreateWork,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_work_created",
        lambda case: delivery_cases.create_work(session, case, user, data.tasks),
    )


@router.post("/delivery-cases/{record_id}/revise")
def revise(
    record_id: str,
    data: Revise,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return command(
        session,
        user,
        record_id,
        data,
        "delivery.case_scope_revised",
        lambda case: delivery_cases.revise(session, case, clean(data.reason)),
    )
