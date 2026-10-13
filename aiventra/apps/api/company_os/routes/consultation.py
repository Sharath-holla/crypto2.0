from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize
from ..config import settings
from ..consulting import approve_proposal, enqueue_consulting
from ..db import session_dependency, uid
from ..research import fetch_source
from ..schemas import (
    Approve,
    Clarification,
    Intake,
    Strict,
)
from ..security import (
    audit,
    clean,
    current_user,
    owner,
    scoped,
)

router = APIRouter()


@router.get("/requirements")
def requirements(user: m.User = Depends(current_user), session: Session = Depends(session_dependency)):
    query = select(m.Requirement).where(m.Requirement.org_id == user.org_id)
    if user.role != "owner":
        query = query.where(m.Requirement.client_id == user.client_id)
    from ..client_access import requirement_allowed, requirement_view

    return [
        serialize(row) if user.role == "owner" else requirement_view(row)
        for row in session.scalars(query).all()
        if user.role == "owner" or requirement_allowed(session, user, row)
    ]


@router.post("/requirements", status_code=201)
def intake(
    data: Intake, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    result = stage_intake(data, user, session)
    session.commit()
    return result


def stage_intake(data: Intake, user: m.User, session: Session):
    """Stage an intake and its workflow in the caller's atomic transaction."""
    client = scoped(session, m.Client, data.client_id, user)
    if user.role != "owner" and client.id != user.client_id:
        raise HTTPException(404, "Client not found")
    if data.mode == "mock" and not settings().mock_enabled:
        raise HTTPException(403, "Mock mode disabled")
    requirement = m.Requirement(id=uid(), org_id=user.org_id, **clean(data.model_dump()))
    # An owner-supplied assertion is not a verified price feed.
    requirement.rates = [{**rate, "verified": False} for rate in requirement.rates]
    session.add(requirement)
    session.flush()
    workflow = enqueue_consulting(session, requirement)
    audit(session, user.org_id, user.id, "requirement.submitted", requirement.id, {"mode": data.mode})
    return {**serialize(requirement), "workflow_id": workflow.id}


@router.get("/requirements/{record_id}")
def requirement_detail(
    record_id: str, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    requirement = scoped(session, m.Requirement, record_id, user)
    if user.role != "owner":
        from ..client_access import requirement_view

        return {**requirement_view(requirement), "proposals": []}
    proposals = session.scalars(select(m.Proposal).where(m.Proposal.requirement_id == requirement.id)).all()
    return {**serialize(requirement), "proposals": [serialize(row) for row in proposals]}


@router.post("/requirements/{record_id}/clarify")
def clarify(
    record_id: str,
    data: Clarification,
    user: m.User = Depends(current_user),
    session: Session = Depends(session_dependency),
):
    requirement = scoped(session, m.Requirement, record_id, user)
    from ..project_setup import for_requirement
    from ..requirements_refinement import enabled

    if enabled(for_requirement(session, requirement.id, requirement.org_id)):
        raise HTTPException(409, "Use the versioned project requirements review controls")
    if user.role != "owner" and session.scalar(
        select(m.Project.id).join(m.Proposal).where(m.Proposal.requirement_id == requirement.id)
    ):
        raise HTTPException(409, "Approved project changes require a versioned delivery change request")
    result = session.execute(
        update(m.Requirement)
        .where(m.Requirement.id == requirement.id, m.Requirement.version == data.version)
        .values(
            version=m.Requirement.version + 1,
            answers=clean(data.answers),
            rates=[{**rate.model_dump(), "verified": False} for rate in data.rates],
            status="queued",
        )
    )
    if not result.rowcount:
        raise HTTPException(409, "Requirement changed; refresh before editing")
    session.refresh(requirement)
    session.execute(
        update(m.Workflow)
        .where(
            m.Workflow.requirement_id == requirement.id,
            m.Workflow.status.in_(
                [
                    "queued",
                    "running",
                    "waiting_for_provider",
                    "waiting_for_free_provider",
                    "paused",
                    "needs_attention",
                ]
            ),
        )
        .values(status="cancelled", lease_token=uid())
    )
    old_proposals = session.scalars(
        select(m.Proposal).where(m.Proposal.requirement_id == requirement.id)
    ).all()
    for proposal in old_proposals:
        proposal.status = "superseded"
        project = session.scalar(select(m.Project).where(m.Project.proposal_id == proposal.id))
        if project:
            project.status = "scope_paused"
    enqueue_consulting(session, requirement)
    audit(
        session, user.org_id, user.id, "requirement.revised", requirement.id, {"version": requirement.version}
    )
    session.commit()
    return serialize(requirement)


class URLInput(Strict):
    url: str = Field(max_length=2000)


@router.post("/requirements/{record_id}/research")
async def research(
    record_id: str,
    data: URLInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    requirement = scoped(session, m.Requirement, record_id, user)
    try:
        evidence = await fetch_source(data.url)
    except Exception as exc:
        raise HTTPException(422, str(exc)[:200]) from None
    record = m.BusinessRecord(
        org_id=user.org_id,
        client_id=requirement.client_id,
        kind="knowledge",
        title="Verified retrieval of published source",
        data={"requirement_id": requirement.id, **evidence},
    )
    session.add(record)
    audit(session, user.org_id, user.id, "research.source_saved", requirement.id, {"url": data.url})
    session.commit()
    return serialize(record)


@router.post("/requirements/{record_id}/upload")
async def upload(
    record_id: str,
    file: UploadFile,
    user: m.User = Depends(current_user),
    session: Session = Depends(session_dependency),
):
    requirement = scoped(session, m.Requirement, record_id, user)
    body = await file.read(100001)
    if (
        len(body) > 100000
        or not file.filename
        or not file.filename.lower().endswith((".txt", ".md", ".json"))
    ):
        raise HTTPException(422, "Upload a UTF-8 txt, md or json document up to 100KB")
    try:
        content = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(422, "UTF-8 document required") from None
    record = m.BusinessRecord(
        org_id=user.org_id,
        client_id=requirement.client_id,
        kind="knowledge",
        title=file.filename[:200],
        data={
            "requirement_id": requirement.id,
            "excerpt": clean(content),
            "trust": "untrusted uploaded document",
        },
    )
    session.add(record)
    audit(session, user.org_id, user.id, "requirement.document_uploaded", requirement.id)
    session.commit()
    return serialize(record)


@router.post("/proposals/{record_id}/approve")
def approve(
    record_id: str,
    data: Approve,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    try:
        # Serialize approval against concurrent clicks and competing selections.
        session.execute(
            update(m.Organization)
            .where(m.Organization.id == user.org_id)
            .values(version=m.Organization.version + 1)
        )
        session.expire_all()
        proposal = scoped(session, m.Proposal, record_id, user)
        project = approve_proposal(session, proposal, data, user)
        session.commit()
        return serialize(project)
    except (ValueError, PermissionError, IntegrityError) as exc:
        session.rollback()
        raise HTTPException(409, str(exc)[:300]) from None


class DecisionInput(Strict):
    version: int
    action: Literal["reject", "request_changes"]
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/proposals/{record_id}/decision")
def proposal_decision(
    record_id: str,
    data: DecisionInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    from ..staffing import lock_org

    lock_org(session, user.org_id)
    session.expire_all()
    proposal = scoped(session, m.Proposal, record_id, user)
    requirement = session.get(m.Requirement, proposal.requirement_id)
    if (
        proposal.version != data.version
        or proposal.version != requirement.version
        or proposal.status != "awaiting_approval"
    ):
        raise HTTPException(409, "Proposal is stale or already decided")
    proposal.status = "rejected" if data.action == "reject" else "changes_requested"
    requirement.status = proposal.status
    audit(
        session,
        user.org_id,
        user.id,
        "proposal." + data.action,
        proposal.id,
        {"reason": data.reason, "version": proposal.version, "content_hash": proposal.content_hash},
    )
    session.commit()
    return serialize(proposal)
