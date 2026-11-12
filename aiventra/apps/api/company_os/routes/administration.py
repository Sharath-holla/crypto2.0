import os
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize
from ..config import settings
from ..db import session_dependency, uid
from ..schemas import (
    AgentUpdate,
    ModelInput,
    ProviderInput,
    Strict,
)
from ..security import (
    audit,
    owner,
    scoped,
    validate_endpoint,
)
from ..staffing import lock_org

router = APIRouter()


@router.patch("/agents/{record_id}")
def update_agent(
    record_id: str,
    data: AgentUpdate,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    agent = scoped(session, m.Agent, record_id, user)
    for key, value in data.model_dump(exclude_none=True).items():
        if (
            key == "tools"
            and agent.role == "CEO"
            and any(tool in value for tool in ("propose_patch", "run_tests"))
        ):
            raise HTTPException(403, "CEO cannot receive code-authoring or execution tools")
        setattr(agent, key, value)
    audit(session, user.org_id, user.id, "agent.configured", agent.id, data.model_dump(exclude_none=True))
    session.commit()
    return serialize(agent)


@router.post("/agents/{record_id}/clone", status_code=201)
def clone_agent(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    agent = scoped(session, m.Agent, record_id, user)
    values = serialize(agent)
    values.pop("id")
    values.pop("created_at")
    values["name"] += " (additional instance)"
    clone = m.Agent(id=uid(), **values)
    session.add(clone)
    audit(session, user.org_id, user.id, "agent.cloned", clone.id)
    session.commit()
    return serialize(clone)


@router.post("/providers", status_code=201)
def add_provider(
    data: ProviderInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    try:
        validate_endpoint(
            data.base_url, settings().provider_allowed_hosts, local_allowed=data.kind == "ollama"
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    if data.kind == "ollama" and data.credential_env:
        raise HTTPException(422, "Local Ollama must not use a credential reference")
    if data.kind != "ollama" and not data.credential_env.endswith("_API_KEY"):
        raise HTTPException(422, "Use a dedicated *_API_KEY environment reference")
    provider = m.Provider(id=uid(), org_id=user.org_id, **data.model_dump())
    session.add(provider)
    session.flush()
    from ..registry_provenance import classify

    classify(
        session,
        provider,
        "test_fixture" if settings().isolated_test_environment else "owner_registered",
        {"created_by": user.id, "path": "authenticated_provider_registration"},
    )
    audit(session, user.org_id, user.id, "provider.registered", provider.id)
    session.commit()
    return {**serialize(provider), "credential_configured": bool(os.environ.get(provider.credential_env))}


@router.post("/models", status_code=201)
def add_model(
    data: ModelInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    lock_org(session, user.org_id)
    session.expire_all()
    scoped(session, m.Provider, data.provider_id, user)
    model = m.ModelConfig(id=uid(), org_id=user.org_id, **data.model_dump())
    session.add(model)
    audit(session, user.org_id, user.id, "model.registered", model.id)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Model already registered") from None
    return serialize(model)


@router.patch("/models/{record_id}")
def configure_model(
    record_id: str,
    data: ModelInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    model = scoped(session, m.ModelConfig, record_id, user)
    if model.provider_id != data.provider_id or model.identifier != data.identifier:
        raise HTTPException(409, "Model identity is immutable; register a different identifier separately")
    for key, value in data.model_dump().items():
        setattr(model, key, value)
    from ..db import now

    model.price_checked_at = now()
    audit(session, user.org_id, user.id, "model.configured", model.id)
    session.commit()
    return serialize(model)


class Toggle(Strict):
    enabled: bool


@router.patch("/models/{record_id}/enabled")
def toggle_model(
    record_id: str,
    data: Toggle,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    model = scoped(session, m.ModelConfig, record_id, user)
    model.enabled = data.enabled
    audit(session, user.org_id, user.id, "model.toggled", model.id, {"enabled": data.enabled})
    session.commit()
    return serialize(model)


@router.patch("/providers/{record_id}")
def toggle_provider(
    record_id: str,
    data: Toggle,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    provider = scoped(session, m.Provider, record_id, user)
    provider.enabled = data.enabled
    audit(session, user.org_id, user.id, "provider.toggled", provider.id, {"enabled": data.enabled})
    session.commit()
    return serialize(provider)


class Control(Strict):
    action: Literal["pause_company", "resume_company", "pause_deployments", "resume_deployments"]


@router.post("/controls")
def control(data: Control, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    org = session.get(m.Organization, user.org_id)
    if data.action in {"pause_company", "resume_company"}:
        org.paused = data.action == "pause_company"
    else:
        org.deployments_paused = data.action == "pause_deployments"
    audit(session, user.org_id, user.id, "control." + data.action, org.id)
    session.commit()
    return serialize(org)


@router.patch("/projects/{record_id}")
def project_control(
    record_id: str,
    data: Toggle,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    if project.status == "closed":
        raise HTTPException(409, "Closed projects require the dedicated, audited reopen action")
    from ..workflows import project_authority

    if data.enabled:
        try:
            project_authority(session, project)
        except PermissionError as exc:
            raise HTTPException(409, str(exc)) from None
    project.status = "active" if data.enabled else "paused"
    audit(
        session,
        user.org_id,
        user.id,
        "project.toggled",
        project.id,
        {"enabled": data.enabled},
        project_id=project.id,
    )
    session.commit()
    return serialize(project)


class BudgetInput(Strict):
    limit_micro: int = Field(ge=0, le=10**12)
    version: int = Field(ge=1)


@router.patch("/budgets/{record_id}")
def budget_update(
    record_id: str,
    data: BudgetInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    budget = scoped(session, m.Budget, record_id, user)
    if data.limit_micro < budget.spent_micro + budget.reserved_micro:
        raise HTTPException(409, "Limit cannot be below spent plus reserved money")
    changed = session.execute(
        update(m.Budget)
        .where(m.Budget.id == budget.id, m.Budget.version == data.version)
        .values(limit_micro=data.limit_micro, version=m.Budget.version + 1)
    )
    if not changed.rowcount:
        raise HTTPException(409, "Budget changed; refresh")
    audit(session, user.org_id, user.id, "budget.changed", budget.id, data.model_dump())
    session.commit()
    session.refresh(budget)
    return serialize(budget)
