from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize
from ..db import now, session_dependency, uid
from ..embeddings import fingerprint
from ..schemas import Strict
from ..security import audit, owner, scoped
from ..semantic_memory import access_clause, backfill, index_pending, put, search

router = APIRouter(prefix="/semantic-memory")


class MemoryInput(Strict):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=64000)
    kind: str = Field(
        pattern="^(knowledge|architecture_decision|resolution|working_memory)$", default="knowledge"
    )
    project_id: str | None = None
    agent_id: str | None = None
    visibility: str = Field(pattern="^(owner|organization|project|agent|selected)$", default="project")
    grant_ids: list[str] = Field(default_factory=list, max_length=30)


class MemoryUpdate(MemoryInput):
    version: int = Field(ge=1)


def validate_scope(session, user, data):
    if data.project_id:
        scoped(session, m.Project, data.project_id, user)
    if data.agent_id:
        scoped(session, m.Agent, data.agent_id, user)
    for record_id in data.grant_ids:
        scoped(session, m.Agent, record_id, user)
    if data.visibility == "organization" and data.project_id:
        raise HTTPException(422, "Organization memory cannot contain a project scope")
    if data.visibility == "project" and not data.project_id:
        raise HTTPException(422, "Project memory requires a project")
    if data.visibility == "agent" and not data.agent_id:
        raise HTTPException(422, "Private agent memory requires an agent")
    if data.visibility == "selected" and not data.grant_ids:
        raise HTTPException(422, "Select at least one authorized agent")


@router.get("")
def browse(
    project_id: str | None = None,
    query: str = Query(default="", max_length=500),
    agent_id: str | None = None,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    if project_id:
        scoped(session, m.Project, project_id, user)
    if user.role != "owner" and not project_id:
        raise HTTPException(403, "Client memory requires an authorized project")
    agent = scoped(session, m.Agent, agent_id, user) if agent_id and user.role == "owner" else None
    if agent_id and user.role != "owner":
        raise HTTPException(403, "Agent memory inspection requires owner permission")
    result = search(
        session,
        user.org_id,
        query,
        project_id=project_id,
        agent=agent,
        client_id=user.client_id if user.role != "owner" else None,
    )
    result["entries"] = [
        serialize(e)
        for e in session.scalars(
            select(m.MemoryEntry)
            .where(
                access_clause(
                    user.org_id, project_id, agent, client_id=user.client_id if user.role != "owner" else None
                )
            )
            .order_by(m.MemoryEntry.updated_at.desc())
            .limit(100)
        )
    ]
    result["storage"] = (
        "pgvector" if session.bind.dialect.name == "postgresql" else "SQLite exact cosine (development)"
    )
    return result


@router.post("", status_code=201)
def create(data: MemoryInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    validate_scope(session, user, data)
    entry = put(
        session,
        user.org_id,
        "manual:" + uid(),
        data.title,
        data.kind,
        data.content,
        project_id=data.project_id,
        agent_id=data.agent_id,
        visibility=data.visibility,
        grant_ids=data.grant_ids,
        client_id=session.get(m.Project, data.project_id).client_id if data.project_id else None,
        provenance={"actor": user.id, "source_type": "owner_entry"},
    )
    audit(session, user.org_id, user.id, "memory.created", entry.id, project_id=data.project_id)
    session.commit()
    return serialize(entry)


@router.patch("/{record_id}")
def revise(
    record_id: str,
    data: MemoryUpdate,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    entry = scoped(session, m.MemoryEntry, record_id, user)
    if not entry.source_key.startswith("manual:") or entry.deleted:
        raise HTTPException(409, "Source-backed entries must be edited at their source")
    validate_scope(session, user, data)
    session.execute(
        update(m.Organization).where(m.Organization.id == user.org_id).values(paused=m.Organization.paused)
    )
    won = session.execute(
        update(m.MemoryEntry)
        .where(m.MemoryEntry.id == entry.id, m.MemoryEntry.version == data.version)
        .values(updated_at=now())
    )
    if won.rowcount != 1:
        raise HTTPException(409, "Memory version changed; reload before editing")
    entry = put(
        session,
        user.org_id,
        entry.source_key,
        data.title,
        data.kind,
        data.content,
        project_id=data.project_id,
        agent_id=data.agent_id,
        visibility=data.visibility,
        grant_ids=data.grant_ids,
        client_id=session.get(m.Project, data.project_id).client_id if data.project_id else None,
        provenance={"actor": user.id, "source_type": "owner_entry"},
    )
    audit(session, user.org_id, user.id, "memory.revised", entry.id, {"version": entry.version})
    session.commit()
    return serialize(entry)


@router.get("/{record_id}/versions")
def versions(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    entry = scoped(session, m.MemoryEntry, record_id, user)
    return [
        serialize(v)
        for v in session.scalars(
            select(m.MemoryVersion)
            .where(m.MemoryVersion.entry_id == entry.id)
            .order_by(m.MemoryVersion.version.desc())
        )
    ]


class VersionInput(Strict):
    version: int = Field(ge=1)


@router.post("/{record_id}/delete")
def tombstone(
    record_id: str,
    data: VersionInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    entry = scoped(session, m.MemoryEntry, record_id, user)
    session.execute(
        update(m.Organization).where(m.Organization.id == user.org_id).values(paused=m.Organization.paused)
    )
    won = session.execute(
        update(m.MemoryEntry)
        .where(
            m.MemoryEntry.id == entry.id,
            m.MemoryEntry.version == data.version,
            m.MemoryEntry.deleted.is_(False),
        )
        .values(deleted=True, index_status="deleted", version=data.version + 1)
    )
    if won.rowcount != 1:
        raise HTTPException(409, "Memory version changed or already deleted")
    # Purge content/vectors; retain only source tombstone/hash and audit for synchronization safety.
    session.execute(delete(m.MemoryChunk).where(m.MemoryChunk.entry_id == entry.id))
    session.execute(delete(m.MemoryVersion).where(m.MemoryVersion.entry_id == entry.id))
    session.execute(delete(m.MemoryGrant).where(m.MemoryGrant.entry_id == entry.id))
    audit(session, user.org_id, user.id, "memory.content_purged", entry.id)
    session.commit()
    return {"id": entry.id, "deleted": True}


@router.post("/index")
def index(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    backfill(session, user.org_id)
    # Indexing on this endpoint is tenant-scoped; worker indexing is separately bounded.
    indexed = index_pending(session, org_id=user.org_id)
    audit(session, user.org_id, user.id, "memory.index_requested", user.org_id, {"indexed": indexed})
    session.commit()
    return {
        "indexed": indexed,
        "embedding_fingerprint": fingerprint(),
        "note": "Uncached local models wait; keyword retrieval continues",
    }
