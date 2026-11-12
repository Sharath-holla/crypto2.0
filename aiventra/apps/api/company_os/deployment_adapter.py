"""Credential-free durable simulator. No shell, network, upload or live target exists.

Future adapters must implement submit/read/advance/cancel with these exact identity
and reconciliation contracts. Simulation receipts never authorize a real release.
"""

from sqlalchemy import select

from . import models as m
from .db import now
from .security import digest

CLASSIFICATION = "SIMULATED_NONPRODUCTION"
STATES = ("deployment_started", "artifact_staged", "revision_activated", "health_check_running")


def read(session, job_id, org_id):
    row = session.get(m.BusinessRecord, job_id)
    if not row or row.org_id != org_id or row.kind != "devops_adapter_job":
        raise PermissionError(
            "Deployment outcome is uncertain; reconcile the saved job, never dispatch again"
        )
    if digest(row.data["request"]) != row.data["request_hash"]:
        raise PermissionError("Deployment adapter request integrity failed")
    return row


async def submit(session, job_id, org_id, project_id, client_id, request):
    existing = session.get(m.BusinessRecord, job_id)
    if existing:
        row = read(session, job_id, org_id)
        if row.data["request"] != request:
            raise PermissionError("Deployment job identity already binds different input")
        return row
    row = m.BusinessRecord(
        id=job_id,
        org_id=org_id,
        project_id=project_id,
        client_id=client_id,
        kind="devops_adapter_job",
        title="Explicit deployment simulation",
        status=STATES[0],
        data={
            "request": request,
            "request_hash": digest(request),
            "position": 0,
            "events": [{"state": STATES[0], "at": now()}],
            "health": [],
            "classification": CLASSIFICATION,
            "started_at": now(),
            "ended_at": None,
        },
    )
    session.add(row)
    session.commit()  # A lost acknowledgement can be read by the same job ID.
    return row


def advance(session, job_id, org_id, expected_position):
    row = read(session, job_id, org_id)
    if row.data["position"] != expected_position or row.status in {
        "deployment_completed",
        "deployment_failed",
        "deployment_cancelled",
    }:
        return row  # Idempotent repeated observation/completion.
    request = row.data["request"]
    position = expected_position + 1
    state = STATES[position] if position < len(STATES) else "deployment_completed"
    outcome = request["scenario"]
    error, health = "", row.data["health"]
    if position == 2 and outcome == "partial_failure":
        state, error = "deployment_failed", "SIMULATION: artifact staged but revision activation failed"
    if position == 4:
        healthy = outcome == "healthy"
        health = [
            {
                "at": now(),
                "expected_revision": request["revision"],
                "observed_revision": request["revision"] if outcome != "wrong_revision" else "unintended",
                "artifact_hash": request["artifact_hash"],
                "healthy": healthy,
                "classification": CLASSIFICATION,
            }
            for _ in range(request["health"]["observations"])
        ]
        if not healthy:
            state, error = "deployment_failed", "SIMULATION: health verification " + outcome
    terminal = state in {"deployment_completed", "deployment_failed"}
    row.status, row.version = state, row.version + 1
    row.data = {
        **row.data,
        "position": position,
        "health": health,
        "error": error,
        "events": [*row.data["events"], {"state": state, "at": now()}],
        "ended_at": now() if terminal else None,
    }
    return row


def cancel(session, job_id, org_id):
    row = read(session, job_id, org_id)
    if row.status not in {"deployment_completed", "deployment_failed", "deployment_cancelled"}:
        row.status, row.version = "deployment_cancelled", row.version + 1
        row.data = {
            **row.data,
            "ended_at": now(),
            "events": [*row.data["events"], {"state": row.status, "at": now()}],
        }
    return row


def completed_for_target(session, project_id, target_id):
    return [
        row
        for row in session.scalars(
            select(m.BusinessRecord).where(
                m.BusinessRecord.project_id == project_id, m.BusinessRecord.kind == "devops_receipt"
            )
        )
        if row.data["body"]["target_id"] == target_id and row.status == "deployment_completed"
    ]
