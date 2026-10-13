"""Owner/tenant/approval contracts with an explicitly synthetic adapter transport."""

import time
from uuid import uuid4

import pytest
from company_os import crypto_control as control
from company_os import models as m
from company_os.config import settings
from company_os.db import uid
from company_os.security import token_for, verify_audit
from fastapi import HTTPException
from sqlalchemy import select


@pytest.fixture
def crypto_http(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "crypto_project_org_id", company["org"].id)
    monkeypatch.setattr(settings(), "crypto_adapter_token", "synthetic-crypto-adapter-test-" + "x" * 32)
    calls = []
    runtime = {}

    async def adapter(method, endpoint, payload=None, params=None):
        calls.append((method, endpoint, payload))
        identity = {
            "run_identity": control.RUN_ID,
            "prospective_holdout_status": "LOCKED_UNUSED",
            "prospective_holdout_used": False,
            "prospective_holdout_evaluation_authorized": False,
            "mode": "DEMO_FIXTURE_STATE",
        }
        if endpoint == "/health":
            return {"status": "PASS", "identity": identity}
        if endpoint == "/snapshot":
            return {"identity": identity, "fixture_transport": True}
        if endpoint == "/preview":
            return {
                "scope_hash": "a" * 64,
                "identity": identity,
                "request": payload,
                "command": ["python", "--closed-test-contract"],
                "execution_blockers": []
                if payload["job_type"] == "CRYPTO_RUNTIME_HEALTH"
                else ["Windows/scientific gate blocked"],
            }
        if endpoint == "/submit":
            runtime[payload["job_id"]] = {
                "job_id": payload["job_id"],
                "state": "QUEUED",
                "scope_hash": payload["scope"]["scope_hash"],
                "completion_verified": False,
            }
            return runtime[payload["job_id"]]
        if endpoint == "/stop":
            return {"job_id": payload["job_id"], "state": "STOP_REQUESTED"}
        if endpoint.startswith("/jobs/"):
            return runtime[endpoint.rsplit("/", 1)[-1]]
        return {"entries": [], "content": "fixture log only"}

    monkeypatch.setattr(control, "adapter", adapter)
    return http, calls, runtime


def payload(kind="CRYPTO_RUNTIME_HEALTH"):
    return {
        "request_id": str(uuid4()),
        "job_type": kind,
        "deadline_utc": int(time.time()) + 300,
        "cost_ceiling": "0",
        "cost_currency": "INR",
    }


def preview(http, kind="CRYPTO_RUNTIME_HEALTH"):
    assert http.post("/crypto/register", json={}).status_code == 200
    result = http.post("/crypto/jobs/preview", json=payload(kind))
    assert result.status_code == 200, result.text
    return result.json()


def test_read_only_project_does_not_register_or_launch(crypto_http, company):
    http, calls, _ = crypto_http
    result = http.get("/crypto/project")
    assert result.status_code == 200 and result.json()["registration"] is None
    assert not any(endpoint == "/submit" for _, endpoint, _ in calls)
    with company["factory"]() as session:
        assert not session.scalar(select(m.BusinessRecord).where(m.BusinessRecord.kind == "crypto_job"))


def test_registration_is_idempotent_and_generic_mutation_protected(crypto_http):
    http, _, _ = crypto_http
    first = http.post("/crypto/register", json={}).json()
    assert http.post("/crypto/register", json={}).json()["id"] == first["id"]
    assert (
        http.patch(
            "/records/" + first["id"], json={"version": first["version"], "status": "open"}
        ).status_code
        == 409
    )


def test_job_preview_persists_without_launch_and_is_idempotent(crypto_http):
    http, calls, _ = crypto_http
    http.post("/crypto/register", json={})
    data = payload()
    first = http.post("/crypto/jobs/preview", json=data).json()
    assert first["status"] == "PENDING_APPROVAL"
    assert http.post("/crypto/jobs/preview", json=data).json()["id"] == first["id"]
    assert http.post("/crypto/jobs/preview", json={**data, "cost_ceiling": "1"}).status_code == 409
    assert not any(endpoint == "/submit" for _, endpoint, _ in calls)


@pytest.mark.parametrize(
    "extra", [{"command": "echo shell"}, {"environment": {}}, {"fold": 2}, {"holdout": True}]
)
def test_shell_environment_fold_and_holdout_overrides_rejected(crypto_http, extra):
    http, _, _ = crypto_http
    assert http.post("/crypto/jobs/preview", json={**payload(), **extra}).status_code == 422


def test_holdout_job_type_not_available(crypto_http):
    http, _, _ = crypto_http
    assert http.post("/crypto/jobs/preview", json=payload("HOLDOUT_EVALUATE")).status_code == 422


def test_approval_is_exact_single_use_and_audited(crypto_http, company):
    http, calls, _ = crypto_http
    row = preview(http)
    path = f"/crypto/jobs/{row['id']}/approve"
    assert http.post(path, json={"version": row["version"], "scope_hash": "b" * 64}).status_code == 409
    data = {"version": row["version"], "scope_hash": "a" * 64}
    assert http.post(path, json=data).status_code == 200
    assert http.post(path, json=data).status_code == 409
    assert sum(endpoint == "/submit" for _, endpoint, _ in calls) == 1
    with company["factory"]() as session:
        assert verify_audit(session, company["org"].id)["valid"]


def test_scientific_gate_cannot_be_overridden_by_owner_approval(crypto_http):
    http, calls, _ = crypto_http
    row = preview(http, "CRYPTO_FOLD_TRAIN")
    assert row["data"]["scope"]["execution_blockers"]
    assert (
        http.post(
            f"/crypto/jobs/{row['id']}/approve", json={"version": row["version"], "scope_hash": "a" * 64}
        ).status_code
        == 409
    )
    assert not any(endpoint == "/submit" for _, endpoint, _ in calls)


def test_expired_scope_does_not_execute(crypto_http, company):
    http, calls, _ = crypto_http
    row = preview(http)
    with company["factory"]() as session:
        record = session.get(m.BusinessRecord, row["id"])
        data = dict(record.data)
        data["scope"] = {**data["scope"], "request": {**data["scope"]["request"], "deadline_utc": 1}}
        record.data = data
        session.commit()
    assert (
        http.post(
            f"/crypto/jobs/{row['id']}/approve", json={"version": row["version"], "scope_hash": "a" * 64}
        ).status_code
        == 409
    )
    assert not any(endpoint == "/submit" for _, endpoint, _ in calls)


def test_source_or_command_change_requires_new_approval(crypto_http, monkeypatch):
    http, _, _ = crypto_http
    row = preview(http)
    old = control.adapter

    async def changed(method, endpoint, payload=None, params=None):
        result = await old(method, endpoint, payload, params)
        if endpoint == "/preview":
            result["command"] = ["different-command"]
        return result

    monkeypatch.setattr(control, "adapter", changed)
    assert (
        http.post(
            f"/crypto/jobs/{row['id']}/approve", json={"version": row["version"], "scope_hash": "a" * 64}
        ).status_code
        == 409
    )


def test_stop_and_resume_require_separate_exact_scope(crypto_http):
    http, _, runtime = crypto_http
    row = preview(http)
    assert (
        http.post(
            f"/crypto/jobs/{row['id']}/approve", json={"version": 1, "scope_hash": "a" * 64}
        ).status_code
        == 200
    )
    assert (
        http.post(f"/crypto/jobs/{row['id']}/stop", json={"version": 2, "scope_hash": "a" * 64}).status_code
        == 200
    )
    runtime[row["id"]].update(state="STOPPED")
    assert http.post(f"/crypto/jobs/{row['id']}/reconcile", json={}).status_code == 200
    resumed = http.post("/crypto/jobs/preview", json={**payload(), "parent_job_id": row["id"]})
    assert resumed.status_code == 200 and resumed.json()["status"] == "PENDING_APPROVAL"


def test_missing_completion_evidence_is_not_complete(crypto_http):
    http, _, runtime = crypto_http
    row = preview(http)
    http.post(f"/crypto/jobs/{row['id']}/approve", json={"version": 1, "scope_hash": "a" * 64})
    runtime[row["id"]].update(state="COMPLETED", completion_verified=False)
    assert http.post(f"/crypto/jobs/{row['id']}/reconcile", json={}).status_code == 409


def test_worker_authority_rechecks_enabled_owner(crypto_http, company):
    http, _, _ = crypto_http
    row = preview(http)
    http.post(f"/crypto/jobs/{row['id']}/approve", json={"version": 1, "scope_hash": "a" * 64})
    with company["factory"]() as session:
        assert control.worker_authority(session, row["id"])["authorized"]
        user = session.get(m.User, company["owner"].id)
        user.enabled = False
        session.commit()
        assert not control.worker_authority(session, row["id"])["authorized"]


def test_other_tenant_owner_cannot_read_crypto(crypto_http, company):
    http, _, _ = crypto_http
    with company["factory"]() as session:
        org = m.Organization(id=uid(), name="Other tenant fixture")
        session.add(org)
        session.flush()
        user = m.User(
            id=uid(), org_id=org.id, email="other-crypto-owner@fixture.test", role="owner", enabled=True
        )
        session.add(user)
        session.flush()
        token = token_for(user, session)
        session.commit()
    assert http.get("/crypto/project", headers={"Authorization": "Bearer " + token}).status_code == 404


def test_private_worker_api_does_not_accept_owner_jwt(crypto_http):
    http, _, _ = crypto_http
    assert http.get(f"/crypto/internal/jobs/{uuid4()}/authority").status_code == 401


@pytest.mark.asyncio
async def test_adapter_transport_refuses_nonloopback_endpoint(monkeypatch):
    monkeypatch.setattr(settings(), "crypto_adapter_url", "https://example.com")
    with pytest.raises(HTTPException) as error:
        await control.adapter("GET", "/snapshot")
    assert error.value.status_code == 503


def test_pending_job_cannot_be_stopped_or_reconciled(crypto_http):
    http, _, runtime = crypto_http
    row = preview(http)
    assert (
        http.post(f"/crypto/jobs/{row['id']}/stop", json={"version": 1, "scope_hash": "a" * 64}).status_code
        == 409
    )
    runtime[row["id"]] = {"job_id": row["id"], "scope_hash": "a" * 64, "state": "QUEUED"}
    assert http.post(f"/crypto/jobs/{row['id']}/reconcile", json={}).status_code == 409


def test_stop_intent_and_terminal_receipts_cannot_regress(crypto_http):
    http, _, runtime = crypto_http
    row = preview(http)
    http.post(f"/crypto/jobs/{row['id']}/approve", json={"version": 1, "scope_hash": "a" * 64})
    http.post(f"/crypto/jobs/{row['id']}/stop", json={"version": 2, "scope_hash": "a" * 64})
    runtime[row["id"]].update(state="QUEUED")
    result = http.post(f"/crypto/jobs/{row['id']}/reconcile", json={})
    assert result.status_code == 200 and result.json()["record"]["status"] == "STOP_REQUESTED"
    runtime[row["id"]].update(state="STOPPED")
    assert http.post(f"/crypto/jobs/{row['id']}/reconcile", json={}).status_code == 200
    runtime[row["id"]].update(state="COMPLETED", completion_verified=True)
    assert http.post(f"/crypto/jobs/{row['id']}/reconcile", json={}).status_code == 409
