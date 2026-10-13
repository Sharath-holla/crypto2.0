"""Persisted owner commands for scoped broker snapshots and separately approved execution."""

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select

from . import models as m
from .config import settings
from .db import now
from .sandbox import connection
from .security import audit, clean, digest
from .staffing import lock_org
from .workflows import project_authority


def validate_execution_result(result, identity):
    if result.get("job_id") != identity or result.get("status") not in {
        "completed",
        "interrupted",
        "running",
    }:
        raise HTTPException(409, "Runner execution identity/status mismatch")


def authorized_project(session, project):
    try:
        project_authority(session, project)
    except PermissionError:
        raise HTTPException(403, "Project execution authority revoked") from None
    return project


async def broker(method, path, data=None, params=None, timeout=200):
    url, headers = connection()
    async with httpx.AsyncClient(
        base_url=url, headers=headers, timeout=timeout, trust_env=False, follow_redirects=False
    ) as client:
        response = await client.request(method, path, json=data, params=params)
        response.raise_for_status()
        return response.json()


def authority(session, row, user):
    session.refresh(user)
    if not user.enabled or user.role != "owner" or user.org_id != row.org_id:
        raise HTTPException(403, "Checkout owner authority revoked")
    project = session.get(m.Project, row.project_id)
    return authorized_project(session, project)


def scope(row):
    return {"org_id": row.org_id, "project_id": row.project_id}


def apply_receipt(row, result):
    manifest = row.data["manifest"]
    if any(result.get(key) != value for key, value in manifest.items()):
        raise ValueError("Runner checkout scope mismatch")
    if result.get("status") not in {"fetching", "ready", "failed", "interrupted", "expired", "cleaned"}:
        raise ValueError("Invalid checkout status")
    row.status = result["status"]
    row.data = {**row.data, "receipt": clean(result)}
    row.data.pop("error", None)


async def create(session, user, repository, request_id):
    project = session.get(m.Project, repository.project_id)
    authorized_project(session, project)
    if not repository.report.get("remote_metadata_only"):
        raise HTTPException(422, "Use the existing local repository workflow")
    # No credential crosses this boundary. The broker independently configures its scoped GitHub reader.
    manifest = {
        "job_id": request_id,
        **scope(repository),
        "repository": repository.report["repository"],
        "branch": repository.report["branch"],
        "commit": repository.baseline_commit,
    }
    fingerprint = digest(manifest)
    lock_org(session, user.org_id)
    existing = session.get(m.BusinessRecord, request_id)
    if existing:
        if (
            existing.org_id != user.org_id
            or existing.kind != "github_checkout"
            or existing.data["request_hash"] != fingerprint
        ):
            raise HTTPException(409, "Checkout request scope conflict")
        return existing
    row = m.BusinessRecord(
        id=request_id,
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="github_checkout",
        title="Restricted GitHub checkout",
        status="fetching",
        data={
            "repository_id": repository.id,
            "manifest": manifest,
            "request_hash": fingerprint,
            "requesting_owner": user.id,
        },
    )
    session.add(row)
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_requested",
        row.id,
        {"commit": repository.baseline_commit},
        project_id=project.id,
    )
    session.commit()
    return await update(session, user, row, "POST", "/checkouts", manifest)


async def update(session, user, row, method, path, body=None, params=None):
    authority(session, row, user)
    session.commit()
    try:
        result = await broker(method, path, body, params)
        lock_org(session, user.org_id)
        session.expire_all()
        authority(session, row, user)
        apply_receipt(row, result)
    except (httpx.HTTPError, ValueError, PermissionError):
        row.status = "interrupted"
        row.data = {
            **row.data,
            "error": "Runner unavailable or response uncertain; reconcile this saved request before retrying",
        }
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_" + row.status,
        row.id,
        {},
        project_id=row.project_id,
    )
    session.commit()
    return row


def execution_hash(row, suite):
    receipt = row.data.get("receipt", {})
    if row.status != "ready" or receipt.get("expires_at", 0) <= now() or not receipt.get("source_digest"):
        raise HTTPException(409, "Checkout is unavailable or expired")
    return digest(
        {
            "manifest": row.data["manifest"],
            "source_digest": receipt["source_digest"],
            "suite": suite,
            "timeout": 120,
        }
    )


def approve(session, user, row, command):
    lock_org(session, user.org_id)
    authority(session, row, user)
    if (
        row.version != command.version
        or row.data.get("receipt", {}).get("source_digest") != command.source_digest
    ):
        raise HTTPException(409, "Exact checkout version/source approval required")
    signature = execution_hash(row, command.suite)
    existing = session.get(m.Approval, str(command.request_id))
    if existing:
        if (
            existing.org_id != user.org_id
            or existing.subject_id != row.id
            or existing.subject_hash != signature
        ):
            raise HTTPException(409, "Approval request scope conflict")
        return existing
    approval = m.Approval(
        id=str(command.request_id),
        org_id=user.org_id,
        owner_id=user.id,
        category="checkout_execution",
        subject_id=row.id,
        version=(
            session.scalar(
                select(func.max(m.Approval.version)).where(
                    m.Approval.org_id == row.org_id,
                    m.Approval.category == "checkout_execution",
                    m.Approval.subject_id == row.id,
                )
            )
            or 0
        )
        + 1,
        subject_hash=signature,
        selection=command.suite,
        expires_at=now() + 600,
    )
    session.add(approval)
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_execution_approved",
        row.id,
        {"suite": command.suite},
        project_id=row.project_id,
    )
    session.commit()
    return approval


async def execute(session, user, row, command):
    if not settings().execution_enabled:
        raise HTTPException(409, "Restricted Docker execution is disabled")
    lock_org(session, user.org_id)
    project = authority(session, row, user)
    approval = session.get(m.Approval, command.approval_id)
    owner = session.get(m.User, approval.owner_id) if approval else None
    if (
        not approval
        or approval.org_id != user.org_id
        or approval.subject_id != row.id
        or approval.category != "checkout_execution"
        or approval.version
        != session.scalar(
            select(func.max(m.Approval.version)).where(
                m.Approval.org_id == row.org_id,
                m.Approval.category == "checkout_execution",
                m.Approval.subject_id == row.id,
            )
        )
        or approval.expires_at <= now()
        or not owner
        or not owner.enabled
        or owner.role != "owner"
        or owner.org_id != row.org_id
        or approval.subject_hash != execution_hash(row, approval.selection)
    ):
        raise HTTPException(403, "Current exact owner execution approval required")
    request_hash = digest({"checkout": row.id, "approval": approval.id, "suite": approval.selection})
    existing = session.get(m.BusinessRecord, str(command.request_id))
    if existing:
        if (
            existing.org_id != user.org_id
            or existing.kind != "github_checkout_execution"
            or existing.data["request_hash"] != request_hash
        ):
            raise HTTPException(409, "Execution request scope conflict")
        return existing
    used = session.scalar(
        select(m.BusinessRecord.id).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.kind == "github_checkout_execution",
            m.BusinessRecord.data["approval_id"].as_string() == approval.id,
        )
    )
    if used:
        raise HTTPException(409, "Approval already consumed; reconcile its saved execution")
    job = m.BusinessRecord(
        id=str(command.request_id),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="github_checkout_execution",
        title="Restricted checkout verification",
        status="running",
        data={
            "request_hash": request_hash,
            "checkout_id": row.id,
            "approval_id": approval.id,
            "suite": approval.selection,
        },
    )
    session.add(job)
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_execution_started",
        job.id,
        {},
        project_id=project.id,
    )
    session.commit()
    try:
        result = await broker(
            "POST",
            f"/checkouts/{row.id}/execute",
            {**scope(row), "job_id": job.id, "suite": approval.selection, "timeout": 120},
            timeout=150,
        )
        lock_org(session, user.org_id)
        session.expire_all()
        authority(session, row, user)
        validate_execution_result(result, job.id)
        job.status = result.get("status", "interrupted")
        job.data = {**job.data, "result": clean(result)}
    except (httpx.HTTPError, ValueError, PermissionError):
        job.status = "interrupted"
        job.data = {**job.data, "error": "Execution response uncertain; reconcile the saved runner job"}
    audit(
        session,
        user.org_id,
        user.id,
        "repository.checkout_execution_" + job.status,
        job.id,
        {},
        project_id=project.id,
    )
    session.commit()
    return job
