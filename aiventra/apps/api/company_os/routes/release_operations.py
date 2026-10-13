from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import packages, release
from ..api_common import serialize
from ..db import now, session_dependency
from ..schemas import Strict
from ..security import clean, digest, owner, scoped
from ..staffing import lock_org
from .package_operations import checked, view

router = APIRouter()


class ExactPackage(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    manifest_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReleaseDecision(ExactPackage):
    decision: Literal["approve", "reject", "request_changes"]
    reason: str = Field(min_length=10, max_length=2000)


class ReleaseInput(ExactPackage):
    approval_id: str


class WithdrawInput(ExactPackage):
    reason: str = Field(min_length=10, max_length=2000)


def exact(session, record_id, user, data):
    package = scoped(session, m.DeliveryPackage, record_id, user)
    if package.version != data.version or package.manifest_hash != data.manifest_hash:
        raise HTTPException(409, "Package version or manifest changed; inspect the exact frozen version")
    return package


def prior(session, user, data, record_id, action):
    request_hash = digest({"package_id": record_id, "action": action, **data.model_dump(mode="json")})
    result = checked(lambda: release.command_result(session, user, data.request_id, request_hash))
    return request_hash, result


@router.get("/delivery-packages/{record_id}/release-readiness")
def readiness(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    package = scoped(session, m.DeliveryPackage, record_id, user)
    blockers, approval = [], None
    try:
        release.release_readiness(session, package)
    except (PermissionError, ValueError, KeyError, OSError) as exc:
        blockers.append(str(exc) if isinstance(exc, PermissionError) else "Release evidence is invalid")
    try:
        approval = serialize(release.current_approval(session, package))
    except PermissionError:
        pass
    return {
        "ready": not blockers,
        "blockers": blockers,
        "approval": approval,
        "package": view(session, package),
    }


@router.post("/delivery-packages/{record_id}/release-decision")
def decision(
    record_id: str,
    data: ReleaseDecision,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    package = exact(session, record_id, user, data)
    request_hash, previous = prior(session, user, data, record_id, "decision")
    if previous:
        return previous
    approval = checked(lambda: release.decide(session, package, user, data.decision, clean(data.reason)))
    result = {
        "id": package.id,
        "status": package.status,
        "version": package.version,
        "manifest_hash": package.manifest_hash,
        "approval": serialize(approval) if approval else None,
    }
    checked(
        lambda: release.complete_command(
            session,
            user,
            data.request_id,
            request_hash,
            package.project_id,
            "delivery.release_decision",
            result,
        )
    )
    session.commit()
    return result


@router.post("/delivery-packages/{record_id}/release")
def publish(
    record_id: str,
    data: ReleaseInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    package = exact(session, record_id, user, data)
    request_hash, previous = prior(session, user, data, record_id, "release")
    if previous:
        return previous
    proof = next(
        (
            row
            for row in session.scalars(
                select(m.BusinessRecord).where(
                    m.BusinessRecord.org_id == user.org_id,
                    m.BusinessRecord.project_id == package.project_id,
                    m.BusinessRecord.kind == "delivery_release",
                )
            )
            if row.data.get("package_id") == package.id
        ),
        None,
    )
    if proof:
        if (
            package.status not in {"released", "superseded"}
            or proof.data.get("approval_id") != data.approval_id
            or proof.data.get("manifest_hash") != package.manifest_hash
        ):
            raise HTTPException(409, "Existing release was withdrawn or has different authorization")
        return {
            "id": package.id,
            "status": package.status,
            "release_id": proof.id,
            "manifest_hash": package.manifest_hash,
        }
    proof = checked(lambda: release.publish(session, package, user, data.approval_id))
    result = {
        "id": package.id,
        "status": package.status,
        "release_id": proof.id,
        "manifest_hash": package.manifest_hash,
    }
    checked(
        lambda: release.complete_command(
            session,
            user,
            data.request_id,
            request_hash,
            package.project_id,
            "delivery.package_released",
            result,
        )
    )
    session.commit()
    return result


@router.post("/delivery-packages/{record_id}/withdraw")
def withdraw(
    record_id: str,
    data: WithdrawInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    package = exact(session, record_id, user, data)
    request_hash, previous = prior(session, user, data, record_id, "withdraw")
    if previous:
        return previous
    if package.status not in {"released", "superseded", "awaiting_release_approval", "package_ready"}:
        raise HTTPException(409, "Package cannot be withdrawn from its current state")
    old = package.status
    checked(lambda: release.reconsider(session, package, user, "blocked"))
    package.status = "withdrawn"
    for proof in session.scalars(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == package.project_id,
            m.BusinessRecord.kind == "delivery_release",
        )
    ):
        if proof.data.get("package_id") == package.id:
            proof.status, proof.version = "withdrawn", proof.version + 1
    approval = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == user.org_id,
            m.Approval.category == "delivery_release",
            m.Approval.subject_id == package.id,
            m.Approval.version == package.version,
        )
    )
    if approval:
        approval.expires_at = min(approval.expires_at, now())
    packages.notify(session, package, "Delivery release withdrawn; client access blocked")
    result = {"id": package.id, "status": "withdrawn", "previous": old, "reason": clean(data.reason)}
    checked(
        lambda: release.complete_command(
            session,
            user,
            data.request_id,
            request_hash,
            package.project_id,
            "delivery.package_withdrawn",
            result,
        )
    )
    session.commit()
    return result
