from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import publication
from ..api_common import serialize
from ..config import settings
from ..db import now, session_dependency
from ..schemas import Strict
from ..security import audit, digest, owner, scoped
from ..staffing import lock_org

router = APIRouter()


@router.get("/operations/github")
def configuration(user: m.User = Depends(owner)):
    import os

    repositories = [
        name.strip() for name in settings().github_publication_repositories.split(",") if name.strip()
    ]
    return {
        "credential_configured": bool(os.environ.get(settings().github_publication_token_env)),
        "repositories": repositories,
        "draft_only": True,
        "repair_request_limit": 2,
    }


class PreviewInput(Strict):
    repository: str = Field(min_length=3, max_length=200)
    base_ref: str = Field(default="main", min_length=1, max_length=100)


class Exact(Strict):
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RepairInput(Strict):
    request_id: UUID
    feedback_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    objective: str = Field(min_length=10, max_length=2000)


def publication_record(session, record_id, user):
    record = scoped(session, m.BusinessRecord, record_id, user)
    if record.kind != "github_publication":
        raise HTTPException(404, "Publication not found")
    return record


@router.post("/tasks/{record_id}/publication-preview", status_code=201)
async def prepare(
    record_id: str,
    data: PreviewInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    task = scoped(session, m.Task, record_id, user)
    try:
        return serialize(await publication.preview(session, task, data.repository, data.base_ref, user))
    except (publication.PublicationError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/publications/{record_id}/approve")
def approve(
    record_id: str, data: Exact, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    lock_org(session, user.org_id)
    record = publication_record(session, record_id, user)
    if (
        record.version != data.version
        or record.data["manifest_hash"] != data.content_hash
        or digest(record.data["manifest"]) != data.content_hash
    ):
        raise HTTPException(409, "Stale publication manifest")
    existing = session.scalar(
        select(m.Approval).where(
            m.Approval.category == "github_publication",
            m.Approval.subject_id == record.id,
            m.Approval.version == record.version,
        )
    )
    if existing:
        if existing.expires_at <= now():
            raise HTTPException(409, "Approval expired; prepare and review a new manifest")
        return serialize(record)
    if record.status != "prepared":
        raise HTTPException(409, "Only an unpublished prepared manifest may be approved")
    try:
        publication.target(session, record)
    except (publication.PublicationError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None
    session.add(
        m.Approval(
            org_id=user.org_id,
            category="github_publication",
            subject_id=record.id,
            version=record.version,
            subject_hash=data.content_hash,
            owner_id=user.id,
            expires_at=now() + 3600,
        )
    )
    record.status = "approved"
    audit(
        session,
        user.org_id,
        user.id,
        "publication.owner_approved",
        record.id,
        {"manifest_hash": data.content_hash},
        project_id=record.project_id,
    )
    session.commit()
    return serialize(record)


@router.post("/publications/{record_id}/publish")
async def publish(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    record = publication_record(session, record_id, user)
    try:
        return serialize(await publication.publish(session, record, user))
    except (publication.PublicationError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/publications/{record_id}/feedback")
async def feedback(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    record = publication_record(session, record_id, user)
    try:
        return serialize(await publication.feedback(session, record, user))
    except (publication.PublicationError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/publications/{record_id}/repairs", status_code=201)
def repair(
    record_id: str,
    data: RepairInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    record = publication_record(session, record_id, user)
    try:
        task = publication.repair(
            session, record, user, str(data.request_id), data.feedback_hash, data.objective
        )
        return {**serialize(task), "approval_hash": digest(task.payload)}
    except (publication.PublicationError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from None
