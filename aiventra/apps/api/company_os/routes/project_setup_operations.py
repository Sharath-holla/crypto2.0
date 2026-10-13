"""Versioned owner drafts; choices confer no inference or execution authority."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import project_setup as setup
from ..db import session_dependency
from ..document_imports import MAX_UPLOAD, parse_document
from ..draft_documents import attach, pdf_source, retire
from ..schemas import Strict
from ..security import audit, clean, digest, owner
from ..staffing import lock_org

router = APIRouter()


class Create(Strict):
    request_id: UUID
    form: setup.DraftForm


class Command(Strict):
    request_id: UUID
    version: int = Field(ge=1)


class Save(Command):
    form: setup.DraftForm


class Manual(Command):
    architecture: str = Field(min_length=20, max_length=8000)
    milestones: list[str] = Field(min_length=1, max_length=8)
    criteria: list[str] = Field(min_length=1, max_length=20)


def transaction(session, operation):
    try:
        result = operation()
        session.commit()
        return result
    except PermissionError as exc:
        session.rollback()
        raise HTTPException(403, str(exc)) from None
    except ValueError as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from None


def change(session, user, record_id, data, action, operation):
    lock_org(session, user.org_id)
    session.expire_all()
    row = setup.owned(session, record_id, user)
    fingerprint = digest({"action": action, **data.model_dump(mode="json")})
    requests = row.data.get("requests", {})
    key = str(data.request_id)
    if key in requests:
        if requests[key] != fingerprint:
            raise HTTPException(409, "Request ID already used for different content")
        return setup.view(session, row)
    if row.version != data.version:
        raise HTTPException(409, "Draft changed; reload before saving. Your edits have not overwritten it.")
    if len(requests) >= 1000:
        raise HTTPException(409, "Draft edit limit reached; create a new draft")
    previous_selection = setup.selection(row.data["form"])
    operation(row)
    if setup.selection(row.data["form"]) != previous_selection:
        setup.record_selection(session, row, user)
    row.data = {**row.data, "requests": {**requests, key: fingerprint}}
    audit(session, user.org_id, user.id, "project_setup." + action, row.id, {"version": row.version})
    session.flush()
    return setup.view(session, row)


@router.get("/project-creation-options")
def options(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    from ..model_catalog import view

    catalog = view(session, user.org_id)
    return {
        "favorite": setup.FAVORITE,
        "spending_mode": "ZERO_COST_ONLY",
        **catalog,
        "roles": sorted(
            set(
                session.scalars(
                    select(m.Agent.role).where(m.Agent.org_id == user.org_id, m.Agent.enabled.is_(True))
                )
            )
        ),
        "departments": [
            {"id": row.id, "name": row.name}
            for row in session.scalars(select(m.Department).where(m.Department.org_id == user.org_id))
        ],
    }


@router.get("/project-drafts")
def drafts(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return [
        setup.view(session, row)
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.org_id == user.org_id,
                m.BusinessRecord.kind == setup.KIND,
                m.BusinessRecord.data["owner_id"].as_string() == user.id,
            )
            .order_by(m.BusinessRecord.created_at.desc())
            .limit(50)
        )
    ]


@router.post("/project-drafts", status_code=201)
def create(data: Create, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    def operation():
        lock_org(session, user.org_id)
        existing = session.get(m.BusinessRecord, str(data.request_id))
        fingerprint = digest(data.form.model_dump(mode="json"))
        if existing:
            row = setup.owned(session, existing.id, user)
            if row.data["create_hash"] != fingerprint:
                raise HTTPException(409, "Draft ID already used for different content")
            return setup.view(session, row)
        setup.validate_form(session, user, data.form)
        row = m.BusinessRecord(
            id=str(data.request_id),
            org_id=user.org_id,
            client_id=data.form.client_id,
            kind=setup.KIND,
            title=data.form.title or "Untitled project",
            status="draft",
            version=1,
            data={
                "owner_id": user.id,
                "form": clean(data.form.model_dump(mode="json")),
                "attachments": [],
                "create_hash": fingerprint,
                "requests": {},
            },
        )
        session.add(row)
        session.flush()
        setup.record_selection(session, row, user)
        audit(session, user.org_id, user.id, "project_setup.created", row.id, {})
        return setup.view(session, row)

    return transaction(session, operation)


@router.get("/project-drafts/{record_id}")
def detail(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return transaction(session, lambda: setup.view(session, setup.owned(session, record_id, user)))


@router.patch("/project-drafts/{record_id}")
def save(
    record_id: str, data: Save, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    def operation(row):
        if row.status != "draft":
            raise HTTPException(409, "Submitted requirements are immutable; create a new draft revision")
        setup.validate_form(session, user, data.form)
        row.data = {**row.data, "form": clean(data.form.model_dump(mode="json"))}
        row.title, row.client_id = data.form.title or "Untitled project", data.form.client_id
        row.version += 1

    return transaction(session, lambda: change(session, user, record_id, data, "saved", operation))


@router.post("/project-drafts/{record_id}/attachments")
async def upload(
    record_id: str,
    file: UploadFile,
    version: Annotated[int, Form(ge=1)],
    request_id: Annotated[UUID, Form()],
    replace_id: Annotated[str | None, Form()] = None,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    raw = await file.read(MAX_UPLOAD + 1)
    name = file.filename or ""
    content, metadata = await parse_document(name, raw, file.content_type)
    data = Command(version=version, request_id=request_id)

    # Bind upload retries to the actual document, not just its command envelope.
    class Upload(Command):
        document_hash: str
        name: str
        replace_id: str | None

    upload_data = Upload(
        **data.model_dump(), document_hash=metadata["source_sha256"], name=name, replace_id=replace_id
    )

    def operation(row):
        attach(session, user, row, name, raw, content, metadata, replace_id)

    return transaction(session, lambda: change(session, user, record_id, upload_data, "uploaded", operation))


@router.post("/project-drafts/{record_id}/attachments/{attachment_id}/remove")
def remove_attachment(
    record_id: str,
    attachment_id: str,
    data: Command,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    class Removal(Command):
        attachment_id: str

    def operation(row):
        if row.status != "draft":
            raise HTTPException(409, "Attachments cannot change after submission")
        items = row.data["attachments"]
        if not any(item["id"] == attachment_id for item in items):
            raise HTTPException(404, "Attachment is outside this draft")
        previous = session.get(m.Artifact, attachment_id)
        form = row.data["form"]
        if previous and form["text"] == previous.content[:30000]:
            form = {**form, "text": ""}
        retire(session, previous)
        # Preserve private source artifacts and audit history; unlink only the active draft reference.
        row.data = {
            **row.data,
            "form": form,
            "attachments": [item for item in items if item["id"] != attachment_id],
        }
        row.version += 1

    command = Removal(**data.model_dump(), attachment_id=attachment_id)
    return transaction(
        session, lambda: change(session, user, record_id, command, "attachment_removed", operation)
    )


@router.post("/project-drafts/{record_id}/attachments/{attachment_id}/reprocess")
async def reprocess_attachment(
    record_id: str,
    attachment_id: str,
    data: Command,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    class Reprocess(Command):
        attachment_id: str

    command = Reprocess(**data.model_dump(), attachment_id=attachment_id)
    row = setup.owned(session, record_id, user)
    if str(data.request_id) in row.data.get("requests", {}):
        return transaction(
            session, lambda: change(session, user, record_id, command, "reprocessed", lambda _: None)
        )
    item = next((item for item in row.data["attachments"] if item["id"] == attachment_id), None)
    if not item or item.get("format") != "pdf":
        raise HTTPException(404, "Active PDF attachment not found")
    if row.status != "draft":
        raise HTTPException(409, "Submitted source is immutable; create a new approved requirement revision")
    import hashlib

    path = pdf_source(user.org_id, item["source_sha256"])
    if not path.is_file() or path.stat().st_size > MAX_UPLOAD:
        raise HTTPException(409, "Original PDF unavailable; upload a replacement")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != item["source_sha256"]:
        raise HTTPException(409, "PDF source integrity changed")
    content, metadata = await parse_document(item["name"], raw, "application/pdf")
    return transaction(
        session,
        lambda: change(
            session,
            user,
            record_id,
            command,
            "reprocessed",
            lambda current: attach(
                session, user, current, item["name"], raw, content, metadata, attachment_id
            ),
        ),
    )


@router.post("/project-drafts/{record_id}/submit")
def submit(
    record_id: str,
    data: Command,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    def operation(row):
        if row.status != "draft":
            raise HTTPException(409, "Draft already submitted")
        setup.submit(session, row, user)

    return transaction(session, lambda: change(session, user, record_id, data, "submitted", operation))


@router.post("/project-drafts/{record_id}/manual-plan")
def manual(
    record_id: str,
    data: Manual,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    def operation(row):
        if row.status != "submitted" or any(
            not item.strip() or len(item) > 1000 for item in [*data.milestones, *data.criteria]
        ):
            raise ValueError(
                "Submit requirements first and provide nonempty bounded milestones and acceptance criteria"
            )
        setup.manual_plan(session, row, user, data.architecture, data.milestones, data.criteria)

    return transaction(
        session, lambda: change(session, user, record_id, data, "manual_plan_saved", operation)
    )


@router.post("/project-drafts/{record_id}/models")
def models(
    record_id: str, data: Save, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    def operation(row):
        if row.status != "submitted":
            raise HTTPException(409, "Save draft choices before submission")
        workflow = session.get(m.Workflow, row.data["workflow_id"])
        if workflow.status not in {"paused", "waiting_for_free_provider"} or session.scalar(
            select(m.ModelRun.id).where(m.ModelRun.workflow_id == workflow.id)
        ):
            raise HTTPException(
                409, "Model choices can change only before inference while work is paused or waiting"
            )
        choices = {"lead_model_id", "worker_mode", "worker_model_ids", "overrides"}
        form = data.form.model_dump(mode="json")
        if {key: value for key, value in form.items() if key not in choices} != {
            key: value
            for key, value in setup.DraftForm.model_validate(row.data["form"]).model_dump(mode="json").items()
            if key not in choices
        }:
            raise HTTPException(409, "Submitted requirements cannot be edited through model selection")
        setup.validate_form(session, user, data.form)
        row.data = {**row.data, "form": clean(form), "selection_hash": digest(form)}
        workflow.wait_context = {**workflow.wait_context, "model_override": None}
        row.version += 1

    return transaction(session, lambda: change(session, user, record_id, data, "models_selected", operation))
