from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import client_access, client_responses, packages, release
from .. import models as m
from ..api_common import serialize
from ..authentication import count_attempt
from ..config import settings
from ..db import now, session_dependency
from ..schemas import Strict
from ..security import audit, clean, current_user, digest, owner, scoped
from ..staffing import lock_org
from .package_operations import checked

router = APIRouter()


class InvitationInput(Strict):
    request_id: UUID
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
    can_respond: bool = True
    ttl_seconds: int | None = Field(default=None, ge=60, le=604800)

    @field_validator("email")
    @classmethod
    def normalized(cls, value):
        return value.strip().lower()


class Redemption(Strict):
    token: str = Field(pattern=r"^[A-Za-z0-9_-]{43,100}$")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=1024)


class RevokeInput(Strict):
    request_id: UUID
    reason: str = Field(min_length=10, max_length=2000)


class ClientAttachment(Strict):
    name: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=20000)


class ClientResponseInput(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: Literal["accept", "request_changes", "reject", "report_defect", "request_support"]
    reason: str = Field(min_length=20, max_length=4000)
    affected_criteria: list[int] = Field(default_factory=list, max_length=20)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    priority: Literal["low", "normal", "high"] = "normal"
    reproduction: str = Field(default="", max_length=4000)
    feature: str = Field(default="", max_length=1000)
    attachments: list[ClientAttachment] = Field(default_factory=list, max_length=3)

    @field_validator("affected_criteria")
    @classmethod
    def valid_indices(cls, value):
        if any(index < 0 for index in value) or len(set(value)) != len(value):
            raise ValueError("Criterion indices must be unique and nonnegative")
        return value


@router.get("/projects/{record_id}/client-access")
def access(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    project = scoped(session, m.Project, record_id, user)
    invitations = session.scalars(
        select(m.ClientInvitation)
        .where(m.ClientInvitation.org_id == user.org_id, m.ClientInvitation.project_id == project.id)
        .order_by(m.ClientInvitation.created_at.desc())
    )
    grants = session.scalars(
        select(m.ClientAccessGrant).where(
            m.ClientAccessGrant.org_id == user.org_id, m.ClientAccessGrant.project_id == project.id
        )
    )
    return {
        "invitations": [client_access.invitation_view(row) for row in invitations],
        "grants": [
            {
                **serialize(row),
                "email": session.get(m.User, row.user_id).email,
                "enabled": session.get(m.User, row.user_id).enabled,
            }
            for row in grants
        ],
    }


@router.post("/projects/{record_id}/client-invitations", status_code=201)
def invite(
    record_id: str,
    data: InvitationInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    project = scoped(session, m.Project, record_id, user)
    request_hash = digest({"project_id": project.id, **data.model_dump(mode="json")})
    result = checked(
        lambda: client_access.create_invitation(
            session,
            project,
            user,
            data.email,
            data.request_id,
            request_hash,
            data.ttl_seconds or settings().client_invitation_ttl_seconds,
            data.can_respond,
        )
    )
    session.commit()
    return result


@router.post("/client-invitations/{record_id}/revoke")
def revoke(
    record_id: str,
    data: RevokeInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    invitation = scoped(session, m.ClientInvitation, record_id, user)
    request_hash = digest({"invitation_id": invitation.id, **data.model_dump(mode="json")})
    previous = checked(lambda: release.command_result(session, user, data.request_id, request_hash))
    if previous:
        return previous
    invitation.revoked_at = invitation.revoked_at or now()
    grant = session.scalar(
        select(m.ClientAccessGrant).where(
            m.ClientAccessGrant.org_id == user.org_id, m.ClientAccessGrant.invitation_id == invitation.id
        )
    )
    if grant:
        grant.revoked_at = invitation.revoked_at
    result = {"id": invitation.id, "revoked_at": invitation.revoked_at, "reason": clean(data.reason)}
    checked(
        lambda: release.complete_command(
            session,
            user,
            data.request_id,
            request_hash,
            invitation.project_id,
            "delivery.invitation_revoked",
            result,
        )
    )
    session.commit()
    return result


@router.post("/auth/redeem-invitation")
def redeem(data: Redemption, request: Request, session: Session = Depends(session_dependency)):
    source = count_attempt(
        session, "invitation-source:" + (request.client.host if request.client else "unknown")
    )
    account = count_attempt(session, "invitation-account:" + data.email.lower())
    session.commit()
    if source > settings().login_source_limit or account > settings().login_account_limit:
        raise HTTPException(429, "Too many invitation attempts; retry in one minute")
    try:
        return client_access.redeem(session, data.token, data.email.strip().lower(), data.password)
    except (PermissionError, IntegrityError):
        session.rollback()
        raise HTTPException(
            403, "Invitation or account credentials are invalid, expired, revoked or already used"
        ) from None


def released(session, user, record_id, respond=False):
    try:
        return client_access.released_package(session, user, record_id, respond)
    except (PermissionError, ValueError, KeyError, OSError):
        raise HTTPException(404, "Released delivery package is unavailable") from None


@router.get("/client/projects")
def projects(user: m.User = Depends(current_user), session: Session = Depends(session_dependency)):
    result = []
    for grant in session.scalars(
        select(m.ClientAccessGrant).where(
            m.ClientAccessGrant.org_id == user.org_id,
            m.ClientAccessGrant.user_id == user.id,
            m.ClientAccessGrant.revoked_at.is_(None),
        )
    ):
        try:
            client_access.grant_for(session, user, grant.project_id)
        except PermissionError:
            continue
        project = session.get(m.Project, grant.project_id)
        result.append({"id": project.id, "name": project.name, "can_respond": grant.can_respond})
    return result


@router.get("/client/deliveries")
def deliveries(user: m.User = Depends(current_user), session: Session = Depends(session_dependency)):
    result = []
    for package in session.scalars(
        select(m.DeliveryPackage)
        .where(
            m.DeliveryPackage.org_id == user.org_id,
            m.DeliveryPackage.client_id == user.client_id,
            m.DeliveryPackage.status.in_(["released", "superseded"]),
        )
        .order_by(m.DeliveryPackage.version.desc())
    ):
        try:
            package, proof = client_access.released_package(session, user, package.id)
        except (PermissionError, ValueError, KeyError, OSError):
            continue
        result.append(client_access.public_view(session, package, proof))
    return result


@router.get("/client/deliveries/{record_id}")
def detail(
    record_id: str, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    package, proof = released(session, user, record_id)
    return client_access.public_view(session, package, proof)


@router.get("/client/deliveries/{record_id}/files/{file_id}")
def download(
    record_id: str,
    file_id: str,
    user: m.User = Depends(current_user),
    session: Session = Depends(session_dependency),
):
    package, _ = released(session, user, record_id)
    reference = next(
        (row for row in package.manifest["files"] if row["id"] == file_id and row["client_visible"]), None
    )
    if not reference:
        raise HTTPException(404, "Released delivery file is unavailable")
    body = checked(lambda: packages.read_blob(package, reference))
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.client_file_downloaded",
        package.id,
        {"file_id": file_id, "sha256": reference["sha256"]},
        project_id=package.project_id,
        authorization="released file and current scoped client grant",
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


@router.get("/client/history")
def history(user: m.User = Depends(current_user), session: Session = Depends(session_dependency)):
    result = []
    for row in session.scalars(
        select(m.DeliveryResponse)
        .where(m.DeliveryResponse.org_id == user.org_id, m.DeliveryResponse.client_id == user.client_id)
        .order_by(m.DeliveryResponse.created_at.desc())
    ):
        try:
            client_access.grant_for(session, user, row.project_id)
        except PermissionError:
            continue
        result.append(client_responses.response_view(row))
    return result


@router.post("/client/deliveries/{record_id}/responses", status_code=201)
def respond(
    record_id: str,
    data: ClientResponseInput,
    user: m.User = Depends(current_user),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    request_hash = digest({"package_id": record_id, **data.model_dump(mode="json")})
    result = checked(lambda: client_responses.submit(session, user, record_id, data, request_hash))
    session.commit()
    return result


@router.get("/client/cases")
def cases(user: m.User = Depends(current_user), session: Session = Depends(session_dependency)):
    result = []
    for row in session.scalars(
        select(m.BusinessRecord)
        .where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.client_id == user.client_id,
            m.BusinessRecord.kind == "delivery_case",
        )
        .order_by(m.BusinessRecord.created_at.desc())
    ):
        try:
            client_access.grant_for(session, user, row.project_id)
        except PermissionError:
            continue
        result.append(client_responses.case_view(row))
    return result


@router.get("/client/cases/{record_id}/attachments/{content_hash}")
def attachment(
    record_id: str,
    content_hash: str,
    user: m.User = Depends(current_user),
    session: Session = Depends(session_dependency),
):
    case = scoped(session, m.BusinessRecord, record_id, user)
    if user.role != "client" or case.kind != "delivery_case" or case.client_id != user.client_id:
        raise HTTPException(404, "Client case is unavailable")
    body = checked(lambda: client_responses.attachment(session, case, content_hash))
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.client_attachment_downloaded",
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
