"""Owner-only, organization-serialized scope revisions and exact sign-off."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.orm import Session

from .. import models as m
from .. import requirements_refinement as refinement
from ..db import session_dependency
from ..project_setup import for_requirement, owned
from ..security import owner
from .project_setup_operations import Command, change, transaction

router = APIRouter()


class Revision(Command):
    scope: refinement.Scope
    decisions: dict[str, refinement.Decision] = Field(default_factory=dict, max_length=24)
    answers: dict[str, Annotated[str, Field(min_length=1, max_length=2000)]] = Field(
        default_factory=dict, max_length=16
    )
    reconsider: bool = False


class SignOff(Command):
    scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    owner_authored: bool = False


def checked(session, row):
    if row.status != "submitted" or not refinement.enabled(row):
        raise HTTPException(409, "This draft does not use collaborative requirements review")
    return session.get(m.Requirement, row.data["requirement_id"])


@router.get("/requirements/{requirement_id}/requirements-review")
def for_scope(
    requirement_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    def operation():
        requirement = session.get(m.Requirement, requirement_id)
        if not requirement or requirement.org_id != user.org_id:
            raise HTTPException(404, "Requirement unavailable")
        row = for_requirement(session, requirement.id, user.org_id)
        if not refinement.enabled(row):
            return None
        owned(session, row.id, user)
        return {"draft_id": row.id, "draft_version": row.version, **refinement.view(session, row)}

    return transaction(session, operation)


@router.get("/project-drafts/{record_id}/requirements-review")
def detail(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    def operation():
        row = owned(session, record_id, user)
        checked(session, row)
        return {"draft_id": row.id, "draft_version": row.version, **refinement.view(session, row)}

    return transaction(session, operation)


@router.post("/project-drafts/{record_id}/requirements-revision")
def revise(
    record_id: str,
    data: Revision,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    def operation(row):
        requirement = checked(session, row)
        refinement.revise(
            session, row, requirement, data.scope, data.decisions, data.answers, data.reconsider, user
        )

    return transaction(
        session, lambda: change(session, user, record_id, data, "requirements_revised", operation)
    )


@router.post("/project-drafts/{record_id}/requirements-approve")
def approve(
    record_id: str,
    data: SignOff,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    def operation(row):
        refinement.approve(session, row, checked(session, row), data.scope_hash, data.owner_authored, user)

    return transaction(
        session, lambda: change(session, user, record_id, data, "requirements_signed_off", operation)
    )
