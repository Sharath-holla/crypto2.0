import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize, tenant_rows
from ..db import now, session_dependency, uid
from ..finance import settle
from ..monitoring import inspect
from ..organization import activate_crypto, agent_for
from ..schemas import (
    Intake,
    RecordInput,
    Strict,
)
from ..security import (
    audit,
    clean,
    owner,
    scoped,
    verify_audit,
)
from .administration import Control, control
from .consultation import intake

router = APIRouter()


@router.get("/memory/search")
def memory_search(
    project_id: str,
    query: str = "",
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    scoped(session, m.Project, project_id, user)
    from ..memory import retrieve

    return retrieve(session, user.org_id, project_id, query[:200])


@router.post("/records", status_code=201)
def add_record(
    data: RecordInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    if data.project_id:
        scoped(session, m.Project, data.project_id, user)
    if data.client_id:
        scoped(session, m.Client, data.client_id, user)
    record = m.BusinessRecord(id=uid(), org_id=user.org_id, **clean(data.model_dump()))
    session.add(record)
    audit(
        session,
        user.org_id,
        user.id,
        "record.created",
        record.id,
        {"kind": record.kind},
        project_id=data.project_id,
    )
    session.commit()
    return serialize(record)


class StatusInput(Strict):
    version: int
    status: Literal["open", "qualified", "won", "lost", "resolved", "reviewed"]


@router.patch("/records/{record_id}")
def update_record(
    record_id: str,
    data: StatusInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    record = scoped(session, m.BusinessRecord, record_id, user)
    if record.kind.startswith(
        (
            "github_",
            "delivery_",
            "project_setup",
            "provider_catalog",
            "registry_provenance",
            "invocation_receipt",
            "quality_",
            "devops_",
            "crypto_",
        )
    ):
        raise HTTPException(409, "Publication and final-review records use their dedicated workflow controls")
    session.execute(
        update(m.Organization).where(m.Organization.id == user.org_id).values(paused=m.Organization.paused)
    )
    result = session.execute(
        update(m.BusinessRecord)
        .where(m.BusinessRecord.id == record.id, m.BusinessRecord.version == data.version)
        .values(status=data.status, version=m.BusinessRecord.version + 1)
    )
    if not result.rowcount:
        raise HTTPException(409, "Record changed; refresh")
    session.refresh(record)
    from ..semantic_memory import sync_source

    sync_source(session, record)
    audit(session, user.org_id, user.id, "record.updated", record.id, data.model_dump())
    session.commit()
    session.refresh(record)
    return serialize(record)


class ClientInput(Strict):
    name: str = Field(min_length=1, max_length=200)


@router.post("/clients", status_code=201)
def add_client(
    data: ClientInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    client = m.Client(id=uid(), org_id=user.org_id, name=data.name)
    session.add(client)
    audit(session, user.org_id, user.id, "client.created", client.id)
    session.commit()
    return serialize(client)


@router.post("/monitoring/inspect")
def watchdog(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return {"findings": inspect(session, user.org_id)}


@router.post("/notifications/{record_id}/ack")
def acknowledge(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    notification = scoped(session, m.Notification, record_id, user)
    notification.acknowledged = True
    audit(session, user.org_id, user.id, "notification.acknowledged", notification.id)
    session.commit()
    return serialize(notification)


@router.post("/messages/{record_id}/ack")
def acknowledge_message(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    message = scoped(session, m.Message, record_id, user)
    work = session.scalar(
        select(m.AgentWork).where(
            m.AgentWork.org_id == user.org_id,
            m.AgentWork.subject_id == message.id,
            m.AgentWork.kind == "message",
        )
    )
    if work and session.get(m.Workflow, work.workflow_id).status != "completed":
        raise HTTPException(409, "The recipient workflow must complete before acknowledgement")
    message.status, message.acknowledged_at = "acknowledged", now()
    audit(session, user.org_id, user.id, "message.acknowledged", message.id)
    session.commit()
    return serialize(message)


@router.get("/audit/verify")
def audit_integrity(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return verify_audit(session, user.org_id)


class ChatInput(Strict):
    text: str = Field(min_length=1, max_length=30000)
    client_id: str | None = None
    mode: Literal["mock", "live"] = "mock"


@router.post("/chat")
def chat(data: ChatInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    command = data.text.lower().strip()
    action = None
    if command in {
        "pause company",
        "pause all work",
        "resume company",
        "resume all work",
        "pause all production deployments",
    }:
        action = (
            "pause_deployments"
            if "deployments" in command
            else "resume_company"
            if command.startswith("resume")
            else "pause_company"
        )
        org = control(Control(action=action), user, session)
        reply = f"Recorded {action}. Company paused: {org['paused']}; deployments paused: {org['deployments_paused']}."
    elif "project" in command and any(word in command for word in ("show", "list", "active")):
        rows = tenant_rows(session, m.Project, user)
        reply = json.dumps([{"name": row.name, "status": row.status, "id": row.id} for row in rows])
    elif "test report" in command:
        reply = json.dumps([serialize(row) for row in tenant_rows(session, m.Execution, user)])
    elif "spending" in command or "cost" in command:
        runs = tenant_rows(session, m.ModelRun, user)
        reply = f"Recorded computed usage estimate: ${sum(run.cost_micro for run in runs) / 1000000:.6f}. Mock calls have no provider charge. See Finance for held reservations and routing records."
    elif command.startswith("create a new project from this requirement:") or command.startswith("consult:"):
        brief = data.text.split(":", 1)[1].strip()
        client_id = data.client_id or session.scalar(
            select(m.Client.id).where(m.Client.org_id == user.org_id)
        )
        result = intake(
            Intake(client_id=client_id, title=brief[:150], text=brief, mode=data.mode), user, session
        )
        action = "requirement.submitted"
        reply = (
            f"Requirement {result['id']} recorded. Consultation queued; implementation waits for approval."
        )
    else:
        reply = "Supported operations: show every active project; give me the complete test report; show spending; pause company; resume company; pause all production deployments; consult: <requirement>. Use the workforce and provider controls for configuration. No action was executed for this message."
    message = m.Message(
        id=uid(),
        org_id=user.org_id,
        sender=user.id,
        recipient=agent_for(session, user.org_id, "CEO").id,
        type="OWNER_COMMAND",
        correlation_id=uid(),
        content={"input": clean(data.text), "reply": clean(reply), "executed_action": action},
    )
    session.add(message)
    audit(session, user.org_id, user.id, "owner.command", message.id, {"action": action})
    session.commit()
    return {"reply": reply, "action": action, "message_id": message.id}


class Reconcile(Strict):
    cost_micro: int = Field(ge=0, le=10**12)
    note: str = Field(min_length=10, max_length=2000)


@router.post("/runs/{record_id}/reconcile")
def reconcile(
    record_id: str,
    data: Reconcile,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    run = scoped(session, m.ModelRun, record_id, user)
    if run.status not in {"uncertain", "started"}:
        raise HTTPException(409, "Run does not need reconciliation")
    workflow = session.get(m.Workflow, run.workflow_id)
    if workflow.status == "running" and workflow.lease_until > now():
        raise HTTPException(409, "Wait for the worker lease to expire or stop the workflow")
    settle(session, run, data.cost_micro, "owner_reconciled_charge")
    run.status, run.error = "failed", "Owner reconciled: " + clean(data.note)
    audit(session, user.org_id, user.id, "provider.usage_reconciled", run.id, data.model_dump())
    session.commit()
    return serialize(run)


@router.post("/workflows/{record_id}/retry")
def retry(record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    workflow = scoped(session, m.Workflow, record_id, user)
    pending = session.scalar(
        select(m.ModelRun).where(
            m.ModelRun.workflow_id == workflow.id, m.ModelRun.status.in_(["started", "uncertain"])
        )
    )
    if pending or workflow.status != "needs_attention" or workflow.attempts >= workflow.max_attempts:
        raise HTTPException(409, "Reconcile uncertain calls; exhausted workflows require a revised task")
    workflow.status, workflow.lease_until = "queued", 0
    audit(session, user.org_id, user.id, "workflow.retry_authorized", workflow.id)
    session.commit()
    return serialize(workflow)


@router.post("/crypto/activate")
def crypto(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    count = activate_crypto(session, user.org_id)
    audit(session, user.org_id, user.id, "crypto.roles_activated", user.org_id, {"created": count})
    session.commit()
    return {"created": count}
