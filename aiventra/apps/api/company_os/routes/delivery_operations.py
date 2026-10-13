from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import delivery
from .. import models as m
from ..api_common import serialize
from ..db import session_dependency, uid
from ..organization import agent_for
from ..security import audit, digest, owner, scoped
from ..staffing import lock_org
from .agent_operations import WorkInput, approved_project, authorized_agent, enqueue, existing_work

router = APIRouter()


class FinalReviewInput(WorkInput):
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/projects/{record_id}/delivery-readiness")
def readiness(
    record_id: str,
    mode: Literal["live", "mock"] = "live",
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    return delivery.readiness(session, project, mode)


@router.post("/projects/{record_id}/final-review", status_code=201)
def start(
    record_id: str,
    data: FinalReviewInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    request_hash = digest({"project_id": record_id, **data.model_dump(mode="json")})
    previous = existing_work(session, data.request_id, user, request_hash)
    if previous:
        return previous
    lock_org(session, user.org_id)
    previous = existing_work(session, data.request_id, user, request_hash)
    if previous:
        return previous
    project = approved_project(session, record_id, user)
    try:
        manifest = delivery.current_source(session, project, data.mode, data.source_hash)
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    pending = session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "delivery_review",
            m.BusinessRecord.status == "reviewing",
        )
    )
    if pending:
        raise HTTPException(409, "A final review already exists; monitor or recover its saved workflow")
    try:
        agents = [agent_for(session, user.org_id, role) for role in delivery.ROLES]
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from None
    for agent in agents:
        authorized_agent(session, agent.id, user, project, "write_artifact")
        if agent.id in {task["agent_id"] for task in manifest["tasks"] if task["kind"] == "coding"}:
            raise HTTPException(409, "Final review cannot be assigned to a coding author")
    record = m.BusinessRecord(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="delivery_review",
        title=f"Final review: {project.name}"[:200],
        status="reviewing",
        data={
            "manifest": manifest,
            "source_hash": data.source_hash,
            "reviews": [],
            "mode": data.mode,
            "work_id": str(data.request_id),
        },
    )
    session.add(record)
    if data.mode == "live":
        from ..release import transition

        try:
            transition(session, project, "final_review", user.id, data.request_id)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from None
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.review_requested",
        record.id,
        {"source_hash": data.source_hash, "mode": data.mode},
        project_id=project.id,
    )
    result = enqueue(
        session,
        user,
        data,
        "delivery",
        record.id,
        [agent.id for agent in agents],
        {"source_hash": data.source_hash, "model_override": data.model_override},
        project=project,
        request_hash=request_hash,
    )
    result["review"] = serialize(session.get(m.BusinessRecord, result["work"]["subject_id"]))
    return result
