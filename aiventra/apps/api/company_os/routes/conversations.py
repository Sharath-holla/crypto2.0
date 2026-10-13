import asyncio
import hashlib
import json
import re
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize
from ..artifacts import save_artifact
from ..config import settings
from ..db import now, session_dependency, uid
from ..schemas import Strict
from ..security import audit, clean, digest, owner, scoped
from ..staffing import lock_org

router = APIRouter(prefix="/conversations", tags=["conversations"])
ACTIVE = {"queued", "running", "waiting_for_provider", "waiting_for_free_provider"}


class ConversationInput(Strict):
    id: UUID
    client_id: str
    project_id: str | None = None
    mode: Literal["live", "mock"] = "live"
    budget_micro: int = Field(ge=0, le=10**9, default=1_000_000)


class TurnInput(Strict):
    request_id: UUID
    version: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=20000)
    intent: Literal["chat", "consult"] = "chat"
    attachment_ids: list[str] = Field(default_factory=list, max_length=4)


def turn_data(session, turn):
    workflow = session.scalar(select(m.Workflow).where(m.Workflow.conversation_turn_id == turn.id))
    result = serialize(turn)
    result["workflow"] = serialize(workflow) if workflow else None
    result["runs"] = (
        [
            serialize(row)
            for row in session.scalars(
                select(m.ModelRun)
                .where(m.ModelRun.workflow_id == workflow.id)
                .order_by(m.ModelRun.created_at)
            )
        ]
        if workflow
        else []
    )
    result["consultation"] = None
    result["run_traces"] = [
        serialize(row)
        for row in session.scalars(
            select(m.RunTrace).where(
                m.RunTrace.org_id == turn.org_id, m.RunTrace.run_id.in_([run["id"] for run in result["runs"]])
            )
        )
    ]
    if turn.requirement_id:
        requirement = session.get(m.Requirement, turn.requirement_id)
        consultation = session.scalar(
            select(m.Workflow).where(
                m.Workflow.requirement_id == requirement.id, m.Workflow.revision == requirement.version
            )
        )
        result["consultation"] = {
            "requirement": serialize(requirement),
            "workflow": serialize(consultation) if consultation else None,
            "proposals": [
                serialize(row)
                for row in session.scalars(
                    select(m.Proposal).where(m.Proposal.requirement_id == requirement.id)
                )
            ],
        }
    return result


def snapshot(session, conversation, before=None):
    query = select(m.ConversationTurn).where(m.ConversationTurn.conversation_id == conversation.id)
    if before is not None:
        query = query.where(m.ConversationTurn.position < before)
    turns = list(session.scalars(query.order_by(m.ConversationTurn.position.desc()).limit(21)))
    linked = {identity for turn in turns[:20] for identity in turn.attachment_ids}
    recent = (
        select(m.Artifact.id)
        .where(m.Artifact.conversation_id == conversation.id)
        .order_by(m.Artifact.created_at.desc(), m.Artifact.id.desc())
        .limit(20)
    )
    attachments = list(
        session.scalars(
            select(m.Artifact).where(
                m.Artifact.org_id == conversation.org_id,
                m.Artifact.conversation_id == conversation.id,
                (m.Artifact.id.in_(linked)) | (m.Artifact.id.in_(recent)),
            )
        )
    )
    return {
        "conversation": serialize(conversation),
        "turns": [turn_data(session, row) for row in reversed(turns[:20])],
        "next_cursor": str(turns[19].position) if len(turns) > 20 else None,
        "total_turns": session.scalar(
            select(func.count())
            .select_from(m.ConversationTurn)
            .where(m.ConversationTurn.conversation_id == conversation.id)
        ),
        "attachments": [
            {key: value for key, value in serialize(row).items() if key not in {"content", "storage_key"}}
            for row in attachments
        ],
    }


@router.get("")
def list_conversations(
    search: str = Query(default="", max_length=100),
    before: str | None = Query(default=None, max_length=1024),
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    query = select(m.Conversation).where(m.Conversation.org_id == user.org_id)
    if search:
        query = query.where(
            m.Conversation.title.ilike(
                "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%",
                escape="\\",
            )
        )
    from ..history import cursor, decode

    scope = f"{user.org_id}:conversations:{search}"
    if before:
        _, stamp, identity = decode(before, scope)
        query = query.where(
            (m.Conversation.updated_at < stamp)
            | ((m.Conversation.updated_at == stamp) & (m.Conversation.id < identity))
        )
    rows = list(
        session.scalars(query.order_by(m.Conversation.updated_at.desc(), m.Conversation.id.desc()).limit(51))
    )
    return {
        "items": [serialize(row) for row in rows[:50]],
        "next_cursor": cursor(scope, [0, rows[49].updated_at, rows[49].id]) if len(rows) > 50 else None,
    }


@router.post("", status_code=201)
def create_conversation(
    data: ConversationInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    scoped(session, m.Client, data.client_id, user)
    if data.project_id:
        project = scoped(session, m.Project, data.project_id, user)
        if project.client_id != data.client_id:
            raise HTTPException(422, "Project must belong to the selected client")
    if data.mode == "mock" and not settings().mock_enabled:
        raise HTTPException(403, "Fixture mode disabled")
    existing = session.get(m.Conversation, str(data.id))
    if existing:
        if existing.org_id != user.org_id or any(
            getattr(existing, key) != getattr(data, key)
            for key in ("client_id", "project_id", "mode", "budget_micro")
        ):
            raise HTTPException(409, "Conversation creation key conflicts with existing scope")
        return serialize(existing)
    conversation = m.Conversation(org_id=user.org_id, owner_id=user.id, **data.model_dump(mode="json"))
    session.add(conversation)
    session.add(m.Budget(org_id=user.org_id, scope=f"conversation:{data.id}", limit_micro=data.budget_micro))
    audit(
        session,
        user.org_id,
        user.id,
        "conversation.created",
        str(data.id),
        {"mode": data.mode},
        project_id=data.project_id,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Conversation creation conflicted; retry the same key") from None
    return serialize(conversation)


@router.get("/{record_id}")
def detail(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return snapshot(session, scoped(session, m.Conversation, record_id, user))


@router.get("/{record_id}/history")
def older_history(
    record_id: str,
    before: int = Query(ge=1),
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return snapshot(session, scoped(session, m.Conversation, record_id, user), before)


@router.post("/{record_id}/turns", status_code=201)
def send_turn(
    record_id: str,
    data: TurnInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    # Dispatch and audit both lock the organization before any child row.
    lock_org(session, user.org_id)
    session.expire_all()
    conversation = scoped(session, m.Conversation, record_id, user)
    content = clean(data.text.strip())
    if not content or (data.intent == "consult" and len(content) < 20):
        raise HTTPException(422, "Write a question, or a consultation brief of at least 20 characters")
    fingerprint = digest({"text": content, "intent": data.intent, "attachments": data.attachment_ids})

    def previous():
        row = session.scalar(
            select(m.ConversationTurn).where(
                m.ConversationTurn.conversation_id == record_id,
                m.ConversationTurn.request_id == str(data.request_id),
            )
        )
        if row and row.request_hash != fingerprint:
            raise HTTPException(409, "Request key reused for a different message")
        return row

    duplicate = previous()
    if duplicate:
        return turn_data(session, duplicate)
    changed = session.execute(
        update(m.Conversation)
        .where(m.Conversation.id == record_id, m.Conversation.version == data.version)
        .values(version=m.Conversation.version + 1, updated_at=now())
    )
    if changed.rowcount != 1:
        duplicate = previous()
        if duplicate:
            return turn_data(session, duplicate)
        raise HTTPException(409, "Conversation changed; refresh before sending")
    pending = session.scalar(
        select(m.Workflow.id)
        .join(m.ConversationTurn, m.ConversationTurn.id == m.Workflow.conversation_turn_id)
        .where(m.ConversationTurn.conversation_id == record_id, m.Workflow.status.in_(ACTIVE))
    )
    if pending:
        raise HTTPException(409, "Wait for or cancel the current response first")
    for artifact_id in data.attachment_ids:
        artifact = scoped(session, m.Artifact, artifact_id, user)
        if artifact.conversation_id != record_id:
            raise HTTPException(404, "Attachment not in this conversation")
    turn = m.ConversationTurn(
        id=uid(),
        org_id=user.org_id,
        conversation_id=record_id,
        request_id=str(data.request_id),
        request_hash=fingerprint,
        position=conversation.version,
        intent=data.intent,
        content=content,
        attachment_ids=data.attachment_ids,
    )
    session.add(turn)
    session.flush()
    session.add(
        m.Workflow(
            id=uid(),
            org_id=user.org_id,
            conversation_turn_id=turn.id,
            kind="conversation",
            mode=conversation.mode,
        )
    )
    if conversation.title == "New conversation":
        conversation.title = content[:100]
    audit(
        session,
        user.org_id,
        user.id,
        "conversation.turn_queued",
        turn.id,
        {"intent": data.intent, "mode": conversation.mode},
        project_id=conversation.project_id,
    )
    session.commit()
    return turn_data(session, turn)


@router.post("/{record_id}/turns/{turn_id}/cancel")
def cancel_turn(
    record_id: str,
    turn_id: str,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    # Match worker admission's organization -> workflow lock order.
    lock_org(session, user.org_id)
    session.expire_all()
    conversation = scoped(session, m.Conversation, record_id, user)
    turn = scoped(session, m.ConversationTurn, turn_id, user)
    if turn.conversation_id != record_id:
        raise HTTPException(404, "Turn not in conversation")
    workflow = session.scalar(select(m.Workflow).where(m.Workflow.conversation_turn_id == turn.id))
    won = session.execute(
        update(m.Workflow)
        .where(m.Workflow.id == workflow.id, m.Workflow.status.in_(ACTIVE))
        .values(status="cancelled", lease_until=0, lease_token=uid())
    )
    if won.rowcount:
        conversation.version += 1
        conversation.updated_at = now()
        audit(
            session,
            user.org_id,
            user.id,
            "conversation.cancelled",
            turn.id,
            {"note": "In-flight provider usage may still be charged; cancelled output is not published"},
        )
    session.commit()
    return turn_data(session, turn)


@router.post("/{record_id}/attachments", status_code=201)
async def upload(
    record_id: str,
    file: UploadFile,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    conversation = scoped(session, m.Conversation, record_id, user)
    name = file.filename or ""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,150}\.(txt|md|csv|json)", name, re.I) or re.search(
        r"(\.env|secret|password|wallet|private.?key|seed.?phrase)", name, re.I
    ):
        raise HTTPException(422, "Attach a safe UTF-8 .txt, .md, .csv or .json document")
    raw = await file.read(16385)
    if len(raw) > 16384:
        raise HTTPException(413, "Document exceeds 16 KB")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(422, "Document must be UTF-8 text") from None
    if not content.strip() or "\x00" in content:
        raise HTTPException(422, "Document is empty or binary")
    count = session.scalar(
        select(func.count()).select_from(m.Artifact).where(m.Artifact.conversation_id == record_id)
    )
    if count >= 20:
        raise HTTPException(409, "Conversation attachment limit reached")
    artifact = save_artifact(
        session,
        user.org_id,
        name,
        content,
        kind="conversation_attachment",
        project_id=conversation.project_id,
        conversation_id=record_id,
    )
    audit(
        session,
        user.org_id,
        user.id,
        "conversation.attachment_uploaded",
        artifact.id,
        {"name": name, "sha256": artifact.sha256},
    )
    session.commit()
    return {key: value for key, value in serialize(artifact).items() if key not in {"content", "storage_key"}}


@router.get("/{record_id}/events")
def events(
    record_id: str,
    request: Request,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    scoped(session, m.Conversation, record_id, user)
    bind = session.get_bind()
    auth_id = getattr(request.state, "auth_session_id", None)
    expires = request.state.auth_expires_at

    async def stream():
        previous = ""
        for _ in range(60):
            if await request.is_disconnected():
                return
            with Session(bind) as connection:
                identity = connection.get(m.User, user.id)
                auth = connection.get(m.AuthSession, auth_id) if auth_id else None
                if (
                    not identity
                    or not identity.enabled
                    or identity.role != "owner"
                    or identity.org_id != user.org_id
                    or now() >= expires
                    or (auth_id and (not auth or auth.revoked_at or auth.expires_at <= now()))
                ):
                    return
                value = snapshot(connection, scoped(connection, m.Conversation, record_id, user))
            payload = json.dumps(value)
            revision = hashlib.sha256(payload.encode()).hexdigest()
            if revision != previous:
                yield f"event: snapshot\nid: {revision}\ndata: {payload}\n\n"
                previous = revision
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
