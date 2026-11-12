import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize, tenant_rows
from ..authentication import count_attempt
from ..config import settings
from ..db import SessionLocal, now, session_dependency
from ..health import database_state, workers
from ..schemas import (
    Login,
)
from ..security import (
    audit,
    current_user,
    environment_secrets,
    owner,
    password_hasher,
    token_for,
)

router = APIRouter()
dummy_hash = password_hasher.hash("non-account timing-equalization credential")


@router.get("/health")
def health(session: Session = Depends(session_dependency)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ok", "database": "connected", "version": "0.2.0"}


@router.get("/health/live")
def liveness():
    return {"status": "alive"}


@router.get("/operations/database")
def database_operations(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    try:
        return database_state(session)
    except SQLAlchemyError:
        raise HTTPException(503, "Database inspection unavailable; check server connectivity") from None


@router.get("/health/ready")
def readiness(session: Session = Depends(session_dependency)):
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from fastapi.responses import JSONResponse

    try:
        revision = session.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        worker = workers(session)
        ready = revision == head and worker["status"] == "ready"
    except SQLAlchemyError:
        ready, worker = False, {"status": "unavailable"}
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "worker": worker["status"]},
        status_code=200 if ready else 503,
    )


@router.post("/auth/login")
def login(data: Login, request: Request, session: Session = Depends(session_dependency)):
    if settings().oidc_issuer:
        raise HTTPException(403, "Use configured OIDC bearer authentication")
    account_count = count_attempt(session, "account:" + data.email.lower())
    source_count = count_attempt(session, "source:" + (request.client.host if request.client else "unknown"))
    session.commit()
    if account_count > settings().login_account_limit or source_count > settings().login_source_limit:
        raise HTTPException(429, "Too many login attempts; retry in one minute")
    user = session.scalar(select(m.User).where(m.User.email == data.email, m.User.enabled.is_(True)))
    from pwdlib.exceptions import UnknownHashError

    try:
        valid = password_hasher.verify(
            data.password, user.password_hash if user and user.password_hash else dummy_hash
        )
    except UnknownHashError:
        valid = False
    if not user or not valid:
        raise HTTPException(401, "Invalid credentials")
    token = token_for(user, session)
    audit(session, user.org_id, user.id, "auth.login", user.id, authorization="local password authentication")
    session.commit()
    return {"access_token": token, "token_type": "bearer", "user": serialize(user)}


@router.post("/auth/logout")
def logout(
    request: Request, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    record_id = getattr(request.state, "auth_session_id", None)
    if record_id:
        record = session.get(m.AuthSession, record_id)
        record.revoked_at = now()
    audit(session, user.org_id, user.id, "auth.logout", record_id or user.id)
    session.commit()
    return {"ok": True, "provider_logout_required": bool(settings().oidc_issuer)}


@router.get("/auth/me")
def me(user: m.User = Depends(current_user)):
    return serialize(user)


@router.get("/state")
def state(
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
    history_limit: int = Query(default=30, ge=1, le=300),
):
    # A fresh request snapshot preserves rotation while avoiding thousands of
    # repeated process-environment scans when serializing the company history.
    secrets = environment_secrets()
    names = {
        "departments": m.Department,
        "agents": m.Agent,
        "clients": m.Client,
        "requirements": m.Requirement,
        "proposals": m.Proposal,
        "projects": m.Project,
        "tasks": m.Task,
        "milestones": m.Milestone,
        "workflows": m.Workflow,
        "messages": m.Message,
        "meetings": m.Meeting,
        "providers": m.Provider,
        "models": m.ModelConfig,
        "runs": m.ModelRun,
        "budgets": m.Budget,
        "artifacts": m.Artifact,
        "repositories": m.Repository,
        "executions": m.Execution,
        "records": m.BusinessRecord,
        "audit": m.AuditEvent,
        "notifications": m.Notification,
        "approvals": m.Approval,
        "conversations": m.Conversation,
        "provider_probes": m.ProviderProbe,
        "model_policies": m.ModelPolicy,
        "model_evaluations": m.ModelEvaluation,
        "agent_executions": m.AgentExecution,
        "agent_state_events": m.AgentStateEvent,
        "agent_work": m.AgentWork,
        "run_traces": m.RunTrace,
        "tool_invocations": m.ToolInvocation,
        "benchmark_results": m.BenchmarkResult,
        "benchmark_profiles": m.BenchmarkProfile,
    }
    historical = {
        "messages",
        "audit",
        "runs",
        "agent_state_events",
        "run_traces",
        "tool_invocations",
        "notifications",
    }
    result = {
        name: [
            serialize(row, secrets)
            for row in tenant_rows(session, model, user, history_limit if name in historical else 300)
        ]
        for name, model in names.items()
    }
    task_ids = [row["id"] for row in result["tasks"]]
    from ..registry_provenance import visible

    visible_providers = {
        row.id for row in tenant_rows(session, m.Provider, user, 300) if visible(session, row)
    }
    result["providers"] = [row for row in result["providers"] if row["id"] in visible_providers]
    result["models"] = [row for row in result["models"] if row["provider_id"] in visible_providers]
    result["provider_probes"] = [
        row for row in result["provider_probes"] if row["provider_id"] in visible_providers
    ]
    result["dependencies"] = [
        serialize(row, secrets)
        for row in session.scalars(
            select(m.TaskDependency).where(
                m.TaskDependency.task_id.in_(task_ids), m.TaskDependency.depends_on.in_(task_ids)
            )
        )
    ]
    result["organization"] = serialize(session.get(m.Organization, user.org_id), secrets)
    result["runtime"] = {
        "history_limit": history_limit,
        "ai_spending_mode": settings().ai_spending_mode,
        "mock_enabled": settings().mock_enabled,
        "execution_enabled": settings().execution_enabled,
        "live_credentials_required": True,
        "database": session.get_bind().dialect.name,
        "isolated_test_environment": settings().isolated_test_environment,
        "worker": workers(session),
    }
    from ..agent_runtime import snapshot
    from ..credentials import credential_facts
    from ..providers import configured

    result["agent_runtime"] = snapshot(session, user.org_id)
    from ..spending import status

    result["runtime"]["inference_eligibility"] = [
        status(session, session.get(m.Provider, model.provider_id), model)
        for model in tenant_rows(session, m.ModelConfig, user, 300)
        if model.provider_id in visible_providers
    ]

    result["runtime"]["providers"] = [
        {
            "id": row.id,
            "name": row.name,
            "mode": "mock" if row.kind == "mock" else "live",
            "status": "disabled"
            if not row.enabled
            else "configured_unverified"
            if configured(row)
            else "missing_credentials",
            **credential_facts(row, session),
        }
        for row in tenant_rows(session, m.Provider, user, 300)
        if row.id in visible_providers
    ]
    return result


@router.get("/events")
def events(user: m.User = Depends(owner)):
    async def stream():
        previous = ""
        for _ in range(360):
            with SessionLocal() as session:
                enabled = session.scalar(select(m.User.enabled).where(m.User.id == user.id))
                if not enabled:
                    return
                head = session.scalar(
                    select(m.Organization.audit_head).where(m.Organization.id == user.org_id)
                )
            if head != previous:
                yield f"event: change\ndata: {json.dumps({'revision': head})}\n\n"
                previous = head
            else:
                yield ": heartbeat\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
