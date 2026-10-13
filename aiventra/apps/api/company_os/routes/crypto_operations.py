"""Owner-only Crypto control plane. No shell strings, data mutation or holdout endpoint."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import crypto_control as control
from .. import models as m
from ..api_common import serialize
from ..crypto_control import engine_owner as owner
from ..db import session_dependency
from ..schemas import Strict

router = APIRouter(prefix="/crypto", tags=["Crypto 2.0 protected scientific engine"])


class Preview(Strict):
    request_id: UUID
    job_type: Literal[
        "CRYPTO_RUNTIME_HEALTH",
        "CRYPTO_LINEAGE_VALIDATE",
        "CRYPTO_CACHE_PREPARE",
        "CRYPTO_CACHE_VALIDATE",
        "CRYPTO_FOLD_TRAIN",
        "CRYPTO_SPEC_TRAIN",
        "CRYPTO_MODEL_VALIDATE",
        "CRYPTO_REPORT_GENERATE",
        "CRYPTO_RECOVERY_INSPECT",
    ]
    spec_id: str = Field(default="architecture-G0-A6-60m-raw", max_length=160)
    maximum_runtime_seconds: int = Field(default=60, ge=5, le=86400)
    deadline_utc: int = Field(gt=0)
    cost_ceiling: str = Field(min_length=1, max_length=80)
    cost_currency: str = Field(default="UNKNOWN", pattern=r"^[A-Z]{3,12}$")
    cpu_threads: int = Field(default=1, ge=1, le=128)
    minimum_free_ram_gib: float = Field(default=1, gt=0, allow_inf_nan=False)
    minimum_free_disk_gib: float = Field(default=1, gt=0, allow_inf_nan=False)
    parent_job_id: str | None = Field(default=None, pattern=r"^[a-f0-9-]{36}$")


class Approval(Strict):
    version: int = Field(ge=1)
    scope_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("/project")
async def project(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    registered = control.registration(session, user)
    return {
        "registration": serialize(registered) if registered else None,
        "snapshot": await control.adapter("GET", "/snapshot"),
    }


@router.post("/register")
async def register(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    identity = (await control.adapter("GET", "/health"))["identity"]
    return control.save_registration(session, user, identity)


@router.get("/models")
async def models(fold_id: str | None = None, user: m.User = Depends(owner)):
    return await control.adapter("GET", "/models", params={"fold_id": fold_id} if fold_id else {})


@router.get("/artifacts")
async def artifacts(category: str = "reports", path: str = ".", user: m.User = Depends(owner)):
    return await control.adapter("GET", "/artifacts", params={"category": category, "path": path})


@router.get("/document")
async def document(category: str, path: str, tail: bool = False, user: m.User = Depends(owner)):
    return await control.adapter(
        "GET", "/document", params={"category": category, "path": path, "tail": str(tail).lower()}
    )


@router.post("/jobs/preview")
async def preview(
    data: Preview, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    payload = data.model_dump(mode="json", exclude={"request_id"})
    scope = await control.adapter("POST", "/preview", payload)
    return control.save_preview(session, user, str(data.request_id), payload, scope)


@router.post("/jobs/{job_id}/approve")
async def approve(
    job_id: UUID,
    data: Approval,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return await control.approve_and_submit(session, user, str(job_id), data.version, data.scope_hash)


@router.post("/jobs/{job_id}/stop")
async def stop(
    job_id: UUID,
    data: Approval,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return await control.stop_job(session, user, str(job_id), data.version, data.scope_hash)


@router.get("/jobs")
async def jobs(
    limit: int = Query(default=20, ge=1, le=50),
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    rows = session.scalars(
        select(m.BusinessRecord)
        .where(m.BusinessRecord.org_id == user.org_id, m.BusinessRecord.kind == "crypto_job")
        .order_by(m.BusinessRecord.created_at.desc(), m.BusinessRecord.id.desc())
        .limit(limit)
    ).all()
    results = []
    for row in rows:
        runtime = None
        if row.status != "PENDING_APPROVAL":
            try:
                runtime = await control.adapter("GET", f"/jobs/{row.id}")
            except HTTPException:
                runtime = {"state": "AWAITING_EVIDENCE", "completion_verified": False}
        results.append({"record": serialize(row), "runtime": runtime})
    return results


@router.get("/jobs/{job_id}")
async def job(job_id: UUID, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    row = control.job(session, user, str(job_id))
    return {"record": serialize(row), "runtime": await control.adapter("GET", f"/jobs/{row.id}")}


@router.get("/internal/jobs/{job_id}/authority")
def authority(
    job_id: UUID,
    authorization: str | None = Header(default=None),
    session: Session = Depends(session_dependency),
):
    control.internal_authorized(authorization)
    return control.worker_authority(session, str(job_id))


@router.get("/jobs/{job_id}/logs")
async def job_logs(
    job_id: UUID, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    row = control.job(session, user, str(job_id))
    result = await control.adapter("GET", f"/job-logs/{row.id}")
    if result.get("scope_hash") != row.data["scope"]["scope_hash"]:
        raise HTTPException(409, "Job log scope mismatch")
    return result


@router.post("/jobs/{job_id}/reconcile")
async def reconcile(
    job_id: UUID, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    return await control.reconcile(session, control.job(session, user, str(job_id)))


@router.post("/internal/jobs/{job_id}/receipt")
async def receipt(
    job_id: UUID,
    authorization: str | None = Header(default=None),
    session: Session = Depends(session_dependency),
):
    control.internal_authorized(authorization)
    row = session.get(m.BusinessRecord, str(job_id))
    if not row or row.kind != "crypto_job" or row.org_id != control.settings().crypto_project_org_id:
        raise HTTPException(404, "Job not found")
    return await control.reconcile(session, row)
