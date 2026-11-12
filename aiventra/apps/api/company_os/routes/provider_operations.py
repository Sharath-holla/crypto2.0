import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, SecretStr
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import model_catalog
from .. import models as m
from ..api_common import serialize
from ..credentials import (
    VaultUnavailable,
    credential_facts,
    credential_revision,
    save_secret,
    stored_credential,
)
from ..db import now, session_dependency
from ..model_routing import task_class_for
from ..provider_catalog import discover
from ..provider_state import probe_for
from ..providers import ProviderError
from ..registry_provenance import visible
from ..schemas import Strict
from ..security import audit, digest, owner, scoped
from ..staffing import lock_org

router = APIRouter()


@router.get("/providers/{record_id}/local-status")
async def local_status(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    from ..local_ai import diagnostics
    from ..security import clean

    provider = scoped(session, m.Provider, record_id, user)
    if not visible(session, provider):
        raise HTTPException(409, "Quarantined provider cannot run local diagnostics")
    try:
        return clean(await diagnostics(provider))
    except PermissionError as exc:
        raise HTTPException(422, str(exc)) from None


class CredentialInput(Strict):
    secret: SecretStr


@router.post("/providers/{record_id}/credentials")
def store_credentials(
    record_id: str,
    data: CredentialInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    lock_org(session, user.org_id)
    session.expire_all()
    provider = scoped(session, m.Provider, record_id, user)
    if not visible(session, provider):
        raise HTTPException(409, "Quarantined test provider; register a genuine provider connection")
    secret = data.secret.get_secret_value()
    if (
        provider.kind in {"mock", "ollama"}
        or not 8 <= len(secret) <= 4096
        or any(c.isspace() for c in secret)
    ):
        raise HTTPException(
            422, "Provide a valid provider API credential; local providers do not require one"
        )
    try:
        save_secret(session, provider, secret)
    except VaultUnavailable as exc:
        raise HTTPException(409, str(exc)) from None
    probe = probe_for(session, provider)
    model_catalog.invalidate(session, provider)
    probe.status, probe.checked_at, probe.error_code = "unverified", None, ""
    probe.models, probe.inference_at, probe.inference_model_id = [], None, None
    audit(session, user.org_id, user.id, "provider.credential_stored", provider.id)
    session.commit()
    return credential_facts(provider, session)


@router.post("/providers/{record_id}/credentials/revoke")
def revoke_credentials(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    lock_org(session, user.org_id)
    session.expire_all()
    provider = scoped(session, m.Provider, record_id, user)
    credential = stored_credential(provider, session)
    if credential:
        session.delete(credential)
    model_catalog.invalidate(session, provider)
    probe = probe_for(session, provider)
    probe.status, probe.models, probe.inference_at = "unverified", [], None
    probe.checked_at, probe.error_code, probe.inference_model_id = None, "", None
    audit(session, user.org_id, user.id, "provider.credential_revoked", provider.id)
    session.commit()
    return credential_facts(provider, session)  # Environment fallback remains explicitly visible.


@router.post("/providers/{record_id}/test")
@router.post("/providers/{record_id}/discover")
async def test_provider(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    lock_org(session, user.org_id)
    session.expire_all()
    provider = scoped(session, m.Provider, record_id, user)
    if not visible(session, provider):
        raise HTTPException(409, "Quarantined test provider cannot discover workspace models")
    if not provider.enabled:
        raise HTTPException(409, "Enable the provider before testing its catalog")
    revision = credential_revision(provider, session)
    configuration = digest([provider.kind, provider.base_url, provider.enabled])
    state = model_catalog.record(session, provider, create=True)
    state.version += 1
    operation = state.version
    state.data = {**state.data, "status": "discovering", "checked_at": now(), "error_code": ""}
    session.commit()  # Never hold the organization writer lock across provider I/O.
    try:
        catalog = await asyncio.wait_for(discover(provider), timeout=20)
        status, error = "catalog_verified", ""
    except ProviderError as exc:
        status, error, catalog = "catalog_failed", str(exc), []
    except TimeoutError:
        status, error, catalog = "catalog_failed", "catalog_timeout", []
    except ValueError:
        status, error, catalog = "catalog_failed", "catalog_endpoint_invalid", []
    # Only fixed error codes leave the credential boundary; never relay provider bodies.
    allowed_errors = {
        "missing_credentials",
        "vault_unavailable",
        "catalog_timeout",
        "catalog_invalid",
        "catalog_too_large",
        "catalog_network_failure",
        "catalog_endpoint_invalid",
        "catalog_pagination_invalid",
        "catalog_page_limit",
        "catalog_unsupported",
    }
    if (
        error
        and error not in allowed_errors
        and not (error.startswith("catalog_http_") and error[13:].isdigit() and len(error) == 16)
    ):
        error = "catalog_failed"
    session.rollback()
    lock_org(session, user.org_id)
    session.expire_all()
    provider = scoped(session, m.Provider, record_id, user)
    state = model_catalog.record(session, provider)
    actor = session.get(m.User, user.id)
    if not actor or not actor.enabled or actor.role != "owner" or actor.org_id != provider.org_id:
        session.rollback()
        raise HTTPException(403, "Owner authority revoked during discovery")
    if (
        state.version != operation
        or credential_revision(provider, session) != revision
        or digest([provider.kind, provider.base_url, provider.enabled]) != configuration
    ):
        session.rollback()
        raise HTTPException(
            409, "Provider configuration changed during discovery; refresh the current configuration"
        )
    if status == "catalog_verified":
        try:
            model_catalog.synchronize(session, provider, state, catalog)
        except ValueError:
            status, error, catalog = "catalog_failed", "catalog_retention_limit", []
    state.data = {**state.data, "status": status, "error_code": error, "checked_at": now()}
    audit(
        session,
        user.org_id,
        user.id,
        "provider.catalog_checked",
        provider.id,
        {"status": status, "error_code": error, "model_count": len(catalog)},
    )
    probe = probe_for(session, provider)
    probe.status, probe.error_code, probe.checked_at = status, error, now()
    if status == "catalog_verified":
        probe.models = catalog  # Failures retain the last successful catalog, visibly stale.
    session.commit()
    return serialize(probe)


@router.get("/model-catalog")
def catalog(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return model_catalog.view(session, user.org_id)


class PolicyInput(Strict):
    preferred_model_id: str | None = None
    allowed_model_ids: list[str] = Field(default_factory=list, max_length=100)
    version: int = Field(default=0, ge=0)


@router.post("/model-policies/{scope_type}/{record_id}")
def set_policy(
    scope_type: str,
    record_id: str,
    data: PolicyInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    types = {"agent": m.Agent, "provider": m.Provider, "project": m.Project}
    if scope_type not in types:
        raise HTTPException(422, "Unsupported model policy scope")
    target = scoped(session, types[scope_type], record_id, user)
    ids = set(data.allowed_model_ids + ([data.preferred_model_id] if data.preferred_model_id else []))
    for model_id in ids:
        model = scoped(session, m.ModelConfig, model_id, user)
        if not visible(session, scoped(session, m.Provider, model.provider_id, user)):
            raise HTTPException(422, "Quarantined models cannot be saved as workspace preferences")
        if scope_type == "provider" and model.provider_id != target.id:
            raise HTTPException(422, "Provider defaults must reference this provider's models")
    scope = f"{scope_type}:{record_id}"
    existing = session.scalar(
        select(m.ModelPolicy).where(m.ModelPolicy.org_id == user.org_id, m.ModelPolicy.scope == scope)
    )
    values = {
        "preferred_model_id": data.preferred_model_id,
        "allowed_model_ids": sorted(set(data.allowed_model_ids)),
    }
    if existing:
        changed = session.execute(
            update(m.ModelPolicy)
            .where(m.ModelPolicy.id == existing.id, m.ModelPolicy.version == data.version)
            .values(**values, version=data.version + 1)
        )
        if not changed.rowcount:
            raise HTTPException(409, "Policy changed; refresh before saving")
    else:
        if data.version:
            raise HTTPException(409, "Policy no longer exists; refresh before saving")
        existing = m.ModelPolicy(org_id=user.org_id, scope=scope, **values)
        session.add(existing)
    try:
        audit(session, user.org_id, user.id, "model.policy_saved", scope, values)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Policy changed; refresh before saving") from None
    session.refresh(existing)
    return serialize(existing)


class EvaluationInput(Strict):
    score: int = Field(ge=0, le=100)
    task_class: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    note: str = Field(default="", max_length=2000)


@router.post("/model-runs/{record_id}/evaluate", status_code=201)
def evaluate(
    record_id: str,
    data: EvaluationInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    run = scoped(session, m.ModelRun, record_id, user)
    if (
        run.status != "succeeded"
        or session.get(m.Provider, session.get(m.ModelConfig, run.model_id).provider_id).kind == "mock"
    ):
        raise HTTPException(409, "Evaluate a successful live inference run")
    if data.task_class != task_class_for(session, session.get(m.Workflow, run.workflow_id)):
        raise HTTPException(422, "Evaluation task class must match the recorded workflow")
    evaluation = m.ModelEvaluation(
        org_id=user.org_id, model_id=run.model_id, run_id=run.id, evaluator_id=user.id, **data.model_dump()
    )
    session.add(evaluation)
    try:
        audit(
            session,
            user.org_id,
            user.id,
            "model.human_evaluation",
            run.id,
            {"score": data.score, "task_class": data.task_class},
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Run already evaluated") from None
    return serialize(evaluation)
