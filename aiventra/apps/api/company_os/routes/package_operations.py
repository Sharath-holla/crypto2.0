from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import packages
from ..api_common import serialize
from ..db import session_dependency, uid
from ..schemas import Strict
from ..security import audit, clean, digest, owner, scoped
from ..staffing import lock_org

router = APIRouter()


class PackageDocument(Strict):
    purpose: Literal[
        "architecture_decisions",
        "high_level_design",
        "low_level_design",
        "database",
        "api",
        "deployment_instructions",
    ]
    artifact_id: str
    client_visible: bool = False


class PackageInput(Strict):
    request_id: UUID
    review_id: str
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=20, max_length=2000)
    release_notes: str = Field(min_length=20, max_length=4000)
    test_summary: str = Field(min_length=20, max_length=2000)
    limitations: list[str] = Field(default_factory=list, max_length=20)
    known_issues: list[str] = Field(default_factory=list, max_length=20)
    documents: list[PackageDocument] = Field(default_factory=list, max_length=6)
    recipient_ids: list[str] = Field(default_factory=list, max_length=20)
    include_source_patches: bool = False
    acceptance_deadline: int | None = None


def checked(operation):
    try:
        return operation()
    except (PermissionError, ValueError, KeyError, OSError) as exc:
        detail = (
            str(exc) if isinstance(exc, PermissionError) else "Package evidence is unavailable or invalid"
        )
        raise HTTPException(409, detail) from None


def view(session, package):
    workflow = session.get(m.Workflow, package.workflow_id)
    valid, error = False, "Package preparation has not completed"
    if package.finalized_at:
        try:
            valid = packages.integrity(session, package)
            error = ""
        except (PermissionError, ValueError, OSError) as exc:
            error = str(exc) if isinstance(exc, PermissionError) else "Package integrity inspection failed"
    return {
        **serialize(package),
        "workflow": serialize(workflow),
        "integrity_valid": valid,
        "integrity_error": error,
    }


@router.get("/projects/{record_id}/delivery-packages")
def package_list(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    project = scoped(session, m.Project, record_id, user)
    return [
        view(session, row)
        for row in session.scalars(
            select(m.DeliveryPackage)
            .where(m.DeliveryPackage.org_id == user.org_id, m.DeliveryPackage.project_id == project.id)
            .order_by(m.DeliveryPackage.version.desc())
        )
    ]


@router.post("/projects/{record_id}/delivery-packages", status_code=201)
def prepare(
    record_id: str,
    data: PackageInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    project = scoped(session, m.Project, record_id, user)
    payload = data.model_dump(mode="json")
    request_hash = digest({"project_id": project.id, **payload})
    previous = session.scalar(
        select(m.DeliveryPackage).where(
            m.DeliveryPackage.org_id == user.org_id, m.DeliveryPackage.request_id == str(data.request_id)
        )
    )
    if previous:
        if previous.request_hash != request_hash:
            raise HTTPException(409, "Package request ID already used for different content")
        return view(session, previous)
    review = scoped(session, m.BusinessRecord, data.review_id, user)
    source = checked(lambda: packages.review_evidence(session, project, review))
    if digest(source) != data.source_hash:
        raise HTTPException(409, "Final-review source changed; refresh before preparing")
    if len({row.purpose for row in data.documents}) != len(data.documents):
        raise HTTPException(422, "Select each document purpose only once")
    if len(set(data.recipient_ids)) != len(data.recipient_ids):
        raise HTTPException(422, "Recipients must be unique")
    for record in data.recipient_ids:
        recipient = scoped(session, m.User, record, user)
        if recipient.role != "client" or not recipient.enabled or recipient.client_id != project.client_id:
            raise HTTPException(422, "Recipient must be an enabled account for this client")
    pending = session.scalar(
        select(m.DeliveryPackage).where(
            m.DeliveryPackage.org_id == user.org_id,
            m.DeliveryPackage.project_id == project.id,
            m.DeliveryPackage.status == "preparing",
        )
    )
    if pending:
        raise HTTPException(409, "Package preparation is already in progress")
    previous = session.scalar(
        select(m.DeliveryPackage)
        .where(
            m.DeliveryPackage.org_id == user.org_id,
            m.DeliveryPackage.project_id == project.id,
            m.DeliveryPackage.finalized_at.is_not(None),
        )
        .order_by(m.DeliveryPackage.version.desc())
    )
    version = (
        session.scalar(
            select(func.max(m.DeliveryPackage.version)).where(
                m.DeliveryPackage.org_id == user.org_id, m.DeliveryPackage.project_id == project.id
            )
        )
        or 0
    ) + 1
    workflow = m.Workflow(id=uid(), org_id=user.org_id, kind="delivery_package", mode=review.data["mode"])
    session.add(workflow)
    session.flush()
    package = m.DeliveryPackage(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        review_id=review.id,
        workflow_id=workflow.id,
        owner_id=user.id,
        version=version,
        request_id=str(data.request_id),
        request_hash=request_hash,
        source_hash=data.source_hash,
        classification="fixture_nonproduction" if review.data["mode"] == "mock" else "live_reviewed",
        input=clean(payload),
        supersedes_id=previous.id if previous else None,
    )
    session.add(package)
    session.flush()
    if package.classification == "live_reviewed":
        from ..release import transition

        checked(
            lambda: transition(
                session,
                project,
                "package_preparation",
                user.id,
                package.request_id,
                {"package_id": package.id},
            )
        )
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.package_requested",
        package.id,
        {"version": version, "source_hash": data.source_hash, "correlation_id": package.request_id},
        project_id=project.id,
    )
    session.commit()
    return view(session, package)


@router.get("/delivery-packages/{record_id}")
def package_detail(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    return view(session, scoped(session, m.DeliveryPackage, record_id, user))


@router.get("/delivery-packages/{record_id}/files/{file_id}")
def download(
    record_id: str,
    file_id: str,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    package = scoped(session, m.DeliveryPackage, record_id, user)
    checked(lambda: packages.integrity(session, package))
    reference = next((row for row in package.manifest["files"] if row["id"] == file_id), None)
    if not reference:
        raise HTTPException(404, "Delivery file not found")
    body = checked(lambda: packages.read_blob(package, reference))
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.file_downloaded",
        package.id,
        {"file_id": file_id, "sha256": reference["sha256"]},
        project_id=package.project_id,
    )
    session.commit()
    return Response(
        body,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="delivery-v{package.version}-{file_id}.txt"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/delivery-packages/{record_id}/cancel")
def cancel(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    lock_org(session, user.org_id)
    package = scoped(session, m.DeliveryPackage, record_id, user)
    if package.status == "cancelled":
        return view(session, package)
    if package.status != "preparing":
        raise HTTPException(409, "Only unfinished package preparation can be cancelled")
    workflow = session.get(m.Workflow, package.workflow_id)
    workflow.status, workflow.lease_token, workflow.lease_until = "cancelled", uid(), 0
    package.status = "cancelled"
    if package.classification == "live_reviewed":
        from ..release import transition

        checked(
            lambda: transition(
                session, session.get(m.Project, package.project_id), "cancelled", user.id, package.request_id
            )
        )
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.package_cancelled",
        package.id,
        {"previous": "preparing", "new": "cancelled"},
        project_id=package.project_id,
    )
    session.commit()
    return view(session, package)
