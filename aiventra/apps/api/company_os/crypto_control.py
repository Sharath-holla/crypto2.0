"""Crypto managed-project metadata in Aiventra's existing owner-scoped database."""

import hmac
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, uuid5

import httpx
from fastapi import Depends, HTTPException

from . import models as m
from .api_common import serialize
from .config import settings
from .db import now
from .security import audit, digest, owner, scoped
from .staffing import lock_org

RUN_ID = "phase7a-core20-primary-93f987736b1a79d26b773957"


def engine_owner(user: m.User = Depends(owner)):
    configured = settings().crypto_project_org_id
    if not configured:
        raise HTTPException(503, "Crypto engine tenant binding is not configured")
    if user.org_id != configured:
        raise HTTPException(404, "Crypto managed project not found")
    return user


async def adapter(method, endpoint, payload=None, params=None):
    config = settings()
    url = urlsplit(config.crypto_adapter_url)
    if (
        url.scheme != "http"
        or url.hostname not in {"127.0.0.1", "::1"}
        or url.username
        or url.password
        or url.path
        or url.query
        or url.fragment
        or len(config.crypto_adapter_token) < 32
    ):
        raise HTTPException(503, "Private loopback Crypto adapter is not configured")
    try:
        async with httpx.AsyncClient(
            base_url=config.crypto_adapter_url, trust_env=False, follow_redirects=False, timeout=15
        ) as client:
            response = await client.request(
                method,
                endpoint,
                json=payload,
                params=params,
                headers={"Authorization": "Bearer " + config.crypto_adapter_token},
            )
            if response.status_code != 200:
                raise HTTPException(response.status_code, "Crypto operation blocked or evidence unavailable")
            if len(response.content) > 2 * 1024 * 1024:
                raise HTTPException(503, "Crypto response exceeds bounded metadata size")
            return response.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Crypto adapter unavailable; no success inferred") from None


def current_owner(session, user):
    engine_owner(user)
    session.refresh(user)
    org = session.get(m.Organization, user.org_id)
    session.refresh(org)
    if not user.enabled or user.role != "owner" or org.paused:
        raise HTTPException(403, "Current owner/organization authority required")


def registration(session, user):
    identity = str(uuid5(NAMESPACE_URL, "crypto-managed:" + user.org_id + ":" + RUN_ID))
    return session.get(m.BusinessRecord, identity)


def save_registration(session, user, identity):
    if (
        identity.get("run_identity") != RUN_ID
        or identity.get("prospective_holdout_status") != "LOCKED_UNUSED"
    ):
        raise HTTPException(409, "Canonical Crypto identity mismatch")
    lock_org(session, user.org_id)
    current_owner(session, user)
    existing = registration(session, user)
    if existing:
        return serialize(existing)
    record = m.BusinessRecord(
        id=str(uuid5(NAMESPACE_URL, "crypto-managed:" + user.org_id + ":" + RUN_ID)),
        org_id=user.org_id,
        kind="crypto_project",
        title="Crypto 2.0",
        status="protected_external_project",
        data={"identity": identity, "scientific_assets": "IMMUTABLE", "engine": "CANONICAL_CRYPTO"},
    )
    session.add(record)
    audit(
        session,
        user.org_id,
        user.id,
        "crypto.project_registered",
        record.id,
        {"run_identity": RUN_ID, "scientific_execution_authorized": False},
    )
    session.commit()
    return serialize(record)


def job(session, user, job_id):
    row = scoped(session, m.BusinessRecord, job_id, user)
    if row.kind != "crypto_job":
        raise HTTPException(404, "Crypto job not found")
    return row


def save_preview(session, user, request_id, request, scope):
    lock_org(session, user.org_id)
    current_owner(session, user)
    registered = registration(session, user)
    if not registered:
        raise HTTPException(409, "Register the existing Crypto project before requesting jobs")
    if scope.get("identity", {}).get("run_identity") != RUN_ID:
        raise HTTPException(409, "Adapter project scope mismatch")
    request_hash = digest(request)
    existing = session.get(m.BusinessRecord, request_id)
    if existing:
        if (
            existing.org_id != user.org_id
            or existing.kind != "crypto_job"
            or existing.data["request_hash"] != request_hash
        ):
            raise HTTPException(409, "Request idempotency conflict")
        return serialize(existing)
    parent_id = request.get("parent_job_id")
    if parent_id:
        parent = job(session, user, parent_id)
        if parent.status not in {"INTERRUPTED", "STOPPED", "FAILED", "BLOCKED"}:
            raise HTTPException(
                409, "Only an explicitly interrupted/stopped/failed job may request fresh resume authority"
            )
        if (
            parent.data["scope"]["request"]["job_type"] != request["job_type"]
            or parent.data["scope"]["request"]["spec_id"] != request["spec_id"]
        ):
            raise HTTPException(409, "Resume cannot change the scientific unit")
    record = m.BusinessRecord(
        id=request_id,
        org_id=user.org_id,
        kind="crypto_job",
        title=request["job_type"],
        status="PENDING_APPROVAL",
        data={
            "request_hash": request_hash,
            "scope": scope,
            "registration_id": registered.id,
            "requested_by": user.id,
            "created_at": now(),
            "automatic_resume": False,
        },
    )
    session.add(record)
    audit(
        session,
        user.org_id,
        user.id,
        "crypto.job_previewed",
        record.id,
        {"scope_hash": scope["scope_hash"], "type": request["job_type"]},
    )
    session.commit()
    return serialize(record)


async def approve_and_submit(session, user, job_id, version, scope_hash):
    # Inspect immutable adapter/source scope before acquiring a database write lock.
    row = job(session, user, job_id)
    scope = row.data["scope"]
    if scope["scope_hash"] != scope_hash:
        raise HTTPException(409, "Exact reviewed scope hash required")
    fresh = await adapter("POST", "/preview", scope["request"])
    if fresh != scope:
        raise HTTPException(
            409, "Source, scope, policy or scientific identity changed; request a new preview"
        )
    if scope.get("execution_blockers"):
        raise HTTPException(409, "Scientific execution is blocked; reviewed target-host gates are required")
    lock_org(session, user.org_id)
    current_owner(session, user)
    session.refresh(row)
    if row.version != version or row.status != "PENDING_APPROVAL":
        raise HTTPException(409, "Job changed or approval was already consumed")
    if scope["request"]["deadline_utc"] <= now():
        raise HTTPException(409, "Fresh deadline required")
    approval = m.Approval(
        org_id=user.org_id,
        category="crypto_start",
        subject_id=row.id,
        subject_hash=scope_hash,
        version=row.version,
        owner_id=user.id,
        selection=scope["request"]["job_type"],
        expires_at=scope["request"]["deadline_utc"],
    )
    session.add(approval)
    session.flush()
    proof = {
        "approval_id": approval.id,
        "owner_id": user.id,
        "org_id": user.org_id,
        "scope_hash": scope_hash,
        "expires_at": approval.expires_at,
    }
    row.data = {**row.data, "approval": proof}
    row.status = "QUEUED"
    row.version += 1
    audit(
        session,
        user.org_id,
        user.id,
        "crypto.job_approved",
        row.id,
        {"approval_id": approval.id, "scope_hash": scope_hash},
    )
    session.commit()  # Persist intent before dispatch; no blind replay after uncertainty.
    try:
        result = await adapter("POST", "/submit", {"job_id": row.id, "scope": scope, "approval": proof})
    except HTTPException:
        # QUEUED + persisted intent remains available for read-only reconciliation.
        raise HTTPException(
            503, "Dispatch outcome uncertain; inspect/reconcile the same job, do not retry approval"
        ) from None
    return {"record": serialize(row), "runtime": result}


async def stop_job(session, user, job_id, version, scope_hash):
    lock_org(session, user.org_id)
    current_owner(session, user)
    row = job(session, user, job_id)
    session.refresh(row)
    if row.version != version or row.data["scope"]["scope_hash"] != scope_hash:
        raise HTTPException(409, "Exact current job/stop scope required")
    if row.status not in {"QUEUED", "PREPARING", "TRAINING", "EVALUATING"}:
        raise HTTPException(409, "Only an active approved job may be stopped")
    approval = m.Approval(
        org_id=user.org_id,
        category="crypto_stop",
        subject_id=row.id,
        subject_hash=scope_hash,
        version=row.version,
        owner_id=user.id,
        selection="STOP",
        expires_at=now() + 300,
    )
    session.add(approval)
    session.flush()
    proof = {
        "approval_id": approval.id,
        "job_id": row.id,
        "scope_hash": scope_hash,
        "expires_at": approval.expires_at,
        "owner_id": user.id,
        "org_id": user.org_id,
    }
    row.data = {**row.data, "stop_approval": proof}
    row.status = "STOP_REQUESTED"
    row.version += 1
    audit(session, user.org_id, user.id, "crypto.job_stop_approved", row.id, {"approval_id": approval.id})
    session.commit()
    return await adapter("POST", "/stop", {"job_id": row.id, "approval": proof})


def internal_authorized(authorization):
    key = settings().crypto_adapter_token
    if len(key) < 32 or not hmac.compare_digest(authorization or "", "Bearer " + key):
        raise HTTPException(401, "Private worker authentication required")


def worker_authority(session, job_id):
    row = session.get(m.BusinessRecord, job_id)
    if not row or row.kind != "crypto_job":
        raise HTTPException(404, "Job not found")
    proof = row.data.get("approval", {})
    approval = session.get(m.Approval, proof.get("approval_id", ""))
    owner = session.get(m.User, proof.get("owner_id", ""))
    org = session.get(m.Organization, row.org_id)
    allowed = bool(
        approval
        and owner
        and owner.enabled
        and owner.role == "owner"
        and owner.org_id == row.org_id
        and row.org_id == settings().crypto_project_org_id
        and org
        and not org.paused
        and row.status in {"QUEUED", "PREPARING", "TRAINING", "EVALUATING"}
        and approval.org_id == row.org_id
        and approval.owner_id == owner.id
        and approval.subject_id == row.id
        and approval.subject_hash == row.data["scope"]["scope_hash"]
        and approval.category == "crypto_start"
        and approval.expires_at > now()
    )
    return {"authorized": allowed, "scope_hash": row.data["scope"]["scope_hash"]}


async def reconcile(session, row):
    runtime = await adapter("GET", f"/jobs/{row.id}")
    if runtime.get("job_id") != row.id or runtime.get("scope_hash") != row.data["scope"]["scope_hash"]:
        raise HTTPException(409, "Runtime receipt job/scope mismatch")
    states = {
        "QUEUED",
        "PREPARING",
        "PREPARATION_COMPLETE",
        "TRAINING",
        "EVALUATING",
        "COMPLETED",
        "FAILED",
        "INTERRUPTED",
        "STOPPED",
        "BLOCKED",
    }
    if runtime.get("state") not in states or (
        runtime["state"] in {"COMPLETED", "PREPARATION_COMPLETE"}
        and runtime.get("completion_verified") is not True
    ):
        raise HTTPException(409, "Runtime completion evidence is not proven")
    lock_org(session, row.org_id)
    session.refresh(row)
    if row.status == "PENDING_APPROVAL" or runtime["scope_hash"] != row.data["scope"]["scope_hash"]:
        raise HTTPException(409, "No approved current scope to reconcile")
    terminal = {"COMPLETED", "PREPARATION_COMPLETE", "FAILED", "INTERRUPTED", "STOPPED", "BLOCKED"}
    if row.status in terminal and runtime["state"] != row.status:
        raise HTTPException(409, "Terminal job state cannot regress")
    if row.status == "STOP_REQUESTED" and runtime["state"] not in terminal:
        return {"record": serialize(row), "runtime": runtime}
    row.status = runtime["state"]
    row.version += 1
    row.data = {**row.data, "runtime_receipt": runtime}
    audit(
        session,
        row.org_id,
        "crypto-runtime",
        "crypto.job_reconciled",
        row.id,
        {"state": row.status, "scope_hash": runtime["scope_hash"]},
    )
    session.commit()
    return {"record": serialize(row), "runtime": runtime}
