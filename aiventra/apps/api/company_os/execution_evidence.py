"""Trusted invocation receipts; a saved preference or catalog is never a live result."""

from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from . import models as m
from .config import settings
from .credentials import credential_revision
from .db import now
from .security import clean, digest
from .spending import fingerprint

KIND = "invocation_receipt"
WAIT_MESSAGE = "An eligible AI model is required to continue. Configure an approved model and resume."


def identity(run):
    return str(uuid5(NAMESPACE_URL, f"aiventra:invocation:{run.org_id}:{run.id}"))


def test_database(session):
    if settings().isolated_test_environment:
        return True
    url = session.get_bind().engine.url
    return url.get_backend_name() == "sqlite" and (
        not url.database
        or url.database == ":memory:"
        or Path(url.database)
        .resolve()
        .is_relative_to((Path(__file__).resolve().parents[3] / "data/pytest-temp").resolve())
    )


def begin(session, run, workflow, model, provider, decision, requested, pool, context, schema):
    """Called in the same transaction as the durable reservation, before transport."""
    row = m.BusinessRecord(
        id=identity(run),
        org_id=run.org_id,
        project_id=run.project_id,
        kind=KIND,
        title="Model invocation evidence",
        status="started",
        data={
            "run_id": run.id,
            "workflow_id": workflow.id,
            "task_id": run.task_id,
            "agent_id": run.agent_id,
            "step": run.step_name,
            "attempt": run.attempt,
            "requested_model_id": requested,
            "worker_pool": pool,
            "actual_model_id": model.id,
            "selected_model_id": model.id,
            "attempted_model_id": model.id,
            "successful_model_id": None,
            "identifier": model.identifier,
            "provider_id": provider.id,
            "provider": provider.name,
            "provider_kind": provider.kind,
            "fingerprint": fingerprint(provider, model),
            "credential_revision": credential_revision(provider, session),
            "eligibility": decision.public(),
            "selection_reason": run.routing_reason,
            "context_policy": {
                "sensitivity": context["sensitivity"],
                "required_context": context["context_tokens"],
                "authorized_memory": True,
                "untrusted_input": True,
                "schema": schema.__name__,
                "review_policy": context["review_policy"],
                "review_against": context["review_against"],
            },
            "mode": workflow.mode,
            "fixture": provider.kind == "mock"
            or decision.state == "DETERMINISTIC_TEST"
            or test_database(session),
            "verification": "UNVERIFIED",
            "started_at": now(),
        },
    )
    session.add(row)
    return row


def finish(session, run, *, accepted=False, transport=None):
    row = session.get(m.BusinessRecord, identity(run))
    if not row or row.org_id != run.org_id or row.kind != KIND:
        raise PermissionError("Invocation receipt is unavailable")
    data = row.data
    model = session.get(m.ModelConfig, run.model_id)
    provider = session.get(m.Provider, model.provider_id)
    transport = clean(transport or {})
    local_verified = (
        accepted
        and run.status == "succeeded"
        and not data["fixture"]
        and data["mode"] == "live"
        and provider.kind == "ollama"
        and transport.get("identity_verified") is True
        and transport.get("completed") is True
        and transport.get("reported_model") == model.identifier
        and data["eligibility"]["allowed"]
        and data["eligibility"]["state"] == "LOCAL_AVAILABLE"
        and bool(data["eligibility"]["evidence_digest"])
        and data["fingerprint"] == fingerprint(provider, model)
        and data["credential_revision"] == credential_revision(provider, session)
    )
    row.status = run.status
    row.data = {
        **data,
        "verification": "FIXTURE_TESTED"
        if data["fixture"]
        else "LOCAL_LIVE_VERIFIED"
        if local_verified
        else "UNVERIFIED",
        "accepted": accepted,
        "transport": transport,
        "successful_model_id": run.model_id
        if accepted
        and run.status == "succeeded"
        and (
            provider.kind != "ollama"
            or (transport.get("identity_verified") is True and transport.get("completed") is True)
        )
        else None,
        "status": run.status,
        "finished_at": now(),
        "error": clean(run.error),
        "result_sha256": digest(run.response) if run.response else None,
        "duration_ms": run.duration_ms,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "cost_micro": run.cost_micro,
        "cost_basis": run.cost_basis,
    }


def live_results(session, org_id):
    """Only trusted successful receipts establish observed live execution."""
    rows = session.scalars(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == org_id,
            m.BusinessRecord.kind == KIND,
            m.BusinessRecord.data["verification"].as_string() == "LOCAL_LIVE_VERIFIED",
        )
    )
    result = {}
    for row in rows:
        data = row.data
        run = session.get(m.ModelRun, data["run_id"])
        model = session.get(m.ModelConfig, data["actual_model_id"])
        provider = session.get(m.Provider, data["provider_id"])
        if (
            run
            and model
            and provider
            and row.id == identity(run)
            and run.org_id == model.org_id == provider.org_id == org_id
            and run.status == "succeeded"
            and run.model_id == model.id
            and model.provider_id == provider.id
            and provider.kind == "ollama"
            and data.get("mode") == "live"
            and data.get("eligibility", {}).get("state") == "LOCAL_AVAILABLE"
            and data.get("eligibility", {}).get("allowed")
            and data.get("eligibility", {}).get("evidence_digest")
            and data.get("transport", {}).get("identity_verified") is True
            and data.get("transport", {}).get("completed") is True
            and data.get("transport", {}).get("reported_model") == model.identifier
            and data.get("accepted")
            and not data.get("fixture")
            and data["fingerprint"] == fingerprint(provider, model)
            and data["credential_revision"] == credential_revision(provider, session)
            and data["result_sha256"] == digest(run.response)
        ):
            result[model.id] = max(result.get(model.id, 0), data["finished_at"])
    return result


def workflow_view(session, workflow):
    resource_wait = next(
        (
            row.get("reason", "")
            for row in workflow.wait_context.get("eligibility", [])
            if row.get("state") == "LOCAL_RESOURCES_BLOCKED"
        ),
        "",
    )
    runs = session.scalars(
        select(m.ModelRun)
        .where(m.ModelRun.org_id == workflow.org_id, m.ModelRun.workflow_id == workflow.id)
        .order_by(m.ModelRun.created_at.desc(), m.ModelRun.id)
        .limit(100)
    ).all()
    receipts = {
        row.data["run_id"]: row.data
        for row in session.scalars(
            select(m.BusinessRecord).where(
                m.BusinessRecord.org_id == workflow.org_id,
                m.BusinessRecord.kind == KIND,
                m.BusinessRecord.data["workflow_id"].as_string() == workflow.id,
            )
        )
    }
    return {
        "id": workflow.id,
        "kind": workflow.kind,
        "status": workflow.status,
        "step": workflow.step,
        "task_id": workflow.task_id,
        "mode": workflow.mode,
        "waiting": workflow.wait_context,
        "message": resource_wait or WAIT_MESSAGE
        if workflow.status in {"waiting_for_free_provider", "waiting_for_provider"}
        else workflow.last_error,
        "runs": [
            {
                **receipts.get(run.id, {}),
                "run_id": run.id,
                "status": run.status,
                "actual_model_id": run.model_id,
                "agent_id": run.agent_id,
                "step": run.step_name,
                "verification": receipts.get(run.id, {}).get("verification", "UNVERIFIED"),
                "legacy_receipt_missing": run.id not in receipts,
            }
            for run in runs
        ],
    }
