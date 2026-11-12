from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import repository_checkouts as checkouts
from ..api_common import serialize
from ..db import session_dependency
from ..schemas import Strict
from ..security import owner, scoped

router = APIRouter()


@router.get("/repository-checkouts/{identity}/executions")
def executions(identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    parent = record(session, user, identity)
    return [
        {"id": row.id, "status": row.status, "created_at": row.created_at}
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.org_id == user.org_id,
                m.BusinessRecord.project_id == parent.project_id,
                m.BusinessRecord.kind == "github_checkout_execution",
                m.BusinessRecord.data["checkout_id"].as_string() == parent.id,
            )
            .order_by(m.BusinessRecord.created_at.desc(), m.BusinessRecord.id.desc())
            .limit(20)
        )
    ]


@router.get("/repository-checkout-executions/{identity}")
def execution_details(
    identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    return serialize(record(session, user, identity, "github_checkout_execution"))


@router.get("/repositories/{identity}/checkouts")
def listing(identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    repository = scoped(session, m.Repository, identity, user)
    return [
        serialize(row)
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.org_id == user.org_id,
                m.BusinessRecord.project_id == repository.project_id,
                m.BusinessRecord.kind == "github_checkout",
                m.BusinessRecord.data["repository_id"].as_string() == repository.id,
            )
            .order_by(m.BusinessRecord.created_at.desc(), m.BusinessRecord.id.desc())
            .limit(20)
        )
    ]


class Command(Strict):
    request_id: UUID


class Approval(Command):
    version: int = Field(ge=1)
    source_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    suite: Literal["python-unittest", "node-test"]


class Execute(Command):
    approval_id: str


def record(session, user, identity, kind="github_checkout"):
    row = scoped(session, m.BusinessRecord, identity, user)
    if row.kind != kind:
        raise HTTPException(404, "Checkout operation not found")
    return row


@router.post("/repositories/{identity}/checkout")
async def checkout(
    identity: str,
    data: Command,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return serialize(
        await checkouts.create(
            session, user, scoped(session, m.Repository, identity, user), str(data.request_id)
        )
    )


@router.post("/repository-checkouts/{identity}/reconcile")
async def reconcile(
    identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    row = record(session, user, identity)
    return serialize(
        await checkouts.update(session, user, row, "GET", f"/checkouts/{row.id}", params=checkouts.scope(row))
    )


@router.post("/repository-checkouts/{identity}/cleanup")
async def cleanup(
    identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    row = record(session, user, identity)
    return serialize(
        await checkouts.update(
            session, user, row, "POST", f"/checkouts/{row.id}/cleanup", checkouts.scope(row)
        )
    )


@router.post("/repository-checkouts/{identity}/approve-execution")
def approve(
    identity: str,
    data: Approval,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return serialize(checkouts.approve(session, user, record(session, user, identity), data))


@router.post("/repository-checkouts/{identity}/execute")
async def execute(
    identity: str,
    data: Execute,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return serialize(await checkouts.execute(session, user, record(session, user, identity), data))


@router.post("/repository-checkout-executions/{identity}/reconcile")
async def reconcile_execution(
    identity: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    from ..sandbox import stored_result
    from ..security import audit, clean
    from ..staffing import lock_org

    row = record(session, user, identity, "github_checkout_execution")
    parent = record(session, user, row.data["checkout_id"])
    checkouts.authority(session, parent, user)
    session.commit()
    try:
        result = await stored_result(row.id)
    except (httpx.HTTPError, PermissionError, ValueError):
        raise HTTPException(409, "Saved runner result unavailable; operation remains unchanged") from None
    checkouts.validate_execution_result(result, row.id)
    lock_org(session, user.org_id)
    session.expire_all()
    checkouts.authority(session, parent, user)
    row.status, row.data = result["status"], {**row.data, "result": clean(result)}
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_execution_reconciled",
        row.id,
        {},
        project_id=row.project_id,
    )
    session.commit()
    return serialize(row)
