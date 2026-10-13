"""Durable DevOps contracts. All deployment operations here are explicit simulations."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os import deployment_adapter as adapter
from company_os import deployments
from company_os import models as m
from company_os.db import now
from company_os.security import token_for
from company_os.workflows import tick
from sqlalchemy import select, text
from test_packages import prepare_package


@pytest.fixture
async def deployable(http, company, requirement):
    project, _, _, _, package = await prepare_package(http, company, requirement)
    for _ in range(2):
        assert await tick(company["factory"])
    assert http.post("/controls", json={"action": "resume_deployments"}).status_code == 200
    target = http.post(
        f"/projects/{project['id']}/deployment-targets",
        json={
            "request_id": str(uuid4()),
            "name": "Disposable staging",
            "environment": "staging",
        },
    )
    assert target.status_code == 201, target.text
    return {"project": project, "package": package, "target": target.json()}


def prepare(http, fixture, **kwargs):
    body = {
        "request_id": str(uuid4()),
        "package_id": fixture["package"]["id"],
        "target_id": fixture["target"]["id"],
        "risk_summary": "Explicit isolated simulation; no public resources.",
        **kwargs,
    }
    result = http.post(f"/projects/{fixture['project']['id']}/deployment-plans", json=body)
    assert result.status_code == 201, result.text
    return result.json()


def approve(http, plan):
    result = http.post(
        f"/deployment-plans/{plan['id']}/approve",
        json={
            "version": plan["version"],
            "manifest_hash": plan["data"]["manifest_hash"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def start(http, plan, request_id=None):
    return http.post(
        f"/deployment-plans/{plan['id']}/run",
        json={
            "request_id": request_id or str(uuid4()),
            "manifest_hash": plan["data"]["manifest_hash"],
        },
    )


def evidence(http, fixture):
    response = http.get(f"/projects/{fixture['project']['id']}/deployments")
    assert response.status_code == 200, response.text
    return response.json()


async def complete(http, company, fixture, **kwargs):
    plan = approve(http, prepare(http, fixture, **kwargs))
    response = start(http, plan)
    assert response.status_code == 201, response.text
    for _ in range(5):
        await tick(company["factory"])
    saved = evidence(http, fixture)
    job = next(row for row in saved["jobs"] if row["id"] == response.json()["id"])
    assert job["workflow"]["status"] == "completed", job
    receipt = next(row for row in saved["receipts"] if row["id"] == job["result"]["receipt_id"])
    assert receipt["integrity_valid"]
    return plan, job, receipt


async def test_exact_approval_states_health_and_duplicate_dispatch(http, company, deployable):
    plan = prepare(http, deployable)
    assert start(http, plan).status_code == 409
    assert (
        http.post(
            f"/deployment-plans/{plan['id']}/approve",
            json={
                "version": 2,
                "manifest_hash": plan["data"]["manifest_hash"],
            },
        ).status_code
        == 409
    )
    plan = approve(http, plan)
    request_id = str(uuid4())
    response = start(http, plan, request_id)
    assert response.status_code == 201, response.text
    job = response.json()
    assert start(http, plan, request_id).json()["id"] == job["id"]
    assert start(http, plan).status_code == 409
    states = []
    for _ in range(5):
        assert await tick(company["factory"])
        states.append(evidence(http, deployable)["plans"][0]["status"])
    assert states == [
        "deployment_started",
        "artifact_staged",
        "revision_activated",
        "health_check_running",
        "deployment_completed",
    ]
    saved = evidence(http, deployable)
    receipt = saved["receipts"][0]
    assert receipt["integrity_valid"] and not saved["live_deployment_available"]
    assert receipt["data"]["body"]["classification"] == adapter.CLASSIFICATION
    assert len(receipt["data"]["body"]["health"]) == 2
    assert not receipt["data"]["body"]["live_verified"]
    assert not await tick(company["factory"])
    with company["factory"]() as session:
        row = session.get(m.BusinessRecord, receipt["id"])
        deployments.validate_receipt(session, session.get(m.Project, deployable["project"]["id"]), row)
        with pytest.raises(PermissionError, match="actual approved"):
            deployments.release_gate(session, session.get(m.Project, deployable["project"]["id"]), None)
        assert not list(
            session.scalars(select(m.ModelRun).where(m.ModelRun.workflow_id == job["workflow"]["id"]))
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "expired",
        "disabled_owner",
        "category",
        "hash",
        "target",
        "source",
        "artifact",
        "manifest",
        "agent",
        "global_pause",
        "target_org",
        "target_client",
        "project_cancelled",
    ],
)
async def test_stale_or_unauthorized_execution_is_blocked(http, company, deployable, mutation):
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    with company["factory"]() as session:
        row = session.get(m.BusinessRecord, plan["id"])
        approval = session.get(m.Approval, row.data["approval_id"])
        if mutation == "expired":
            approval.expires_at = now() - 1
        elif mutation == "disabled_owner":
            session.get(m.User, approval.owner_id).enabled = False
        elif mutation == "category":
            approval.category = "devops_production"
        elif mutation == "hash":
            approval.subject_hash = "a" * 64
        elif mutation == "target":
            session.get(m.BusinessRecord, deployable["target"]["id"]).version += 1
        elif mutation == "source":
            session.get(m.DeliveryPackage, deployable["package"]["id"]).source_hash = "b" * 64
        elif mutation == "artifact":
            session.get(m.Artifact, row.data["artifact_id"]).content += "changed"
        elif mutation == "manifest":
            row.data = {**row.data, "manifest": {**row.data["manifest"], "environment": "production"}}
        elif mutation == "agent":
            work = session.get(m.AgentWork, job["id"])
            session.get(m.Agent, work.participants[0]).tools = []
        elif mutation == "global_pause":
            session.get(m.Organization, company["org"].id).deployments_paused = True
        elif mutation == "target_org":
            other = m.Organization(name="Foreign test organization")
            session.add(other)
            session.flush()
            session.get(m.BusinessRecord, deployable["target"]["id"]).org_id = other.id
        elif mutation == "target_client":
            other = m.Client(org_id=company["org"].id, name="Different fixture client")
            session.add(other)
            session.flush()
            session.get(m.BusinessRecord, deployable["target"]["id"]).client_id = other.id
        else:
            session.get(m.Project, deployable["project"]["id"]).status = "cancelled"
        session.commit()
    assert await tick(company["factory"])
    with company["factory"]() as session:
        assert session.get(m.Workflow, job["workflow"]["id"]).status == "needs_attention"
        assert not list(
            session.scalars(select(m.BusinessRecord).where(m.BusinessRecord.kind == "devops_adapter_job"))
        )


@pytest.mark.parametrize(
    "scenario", ["health_failure", "health_timeout", "partial_failure", "wrong_revision"]
)
async def test_failure_incident_and_separately_approved_rollback(http, company, deployable, scenario):
    _, _, healthy = await complete(http, company, deployable)
    _, _, failed = await complete(http, company, deployable, scenario=scenario)
    assert failed["status"] == "deployment_failed"
    incident = evidence(http, deployable)["incidents"][0]
    recovery = prepare(http, deployable, rollback_receipt_id=healthy["id"], incident_id=incident["id"])
    assert recovery["data"]["manifest"]["required_approvals"] == ["devops_staging_rollback"]
    assert start(http, recovery).status_code == 409
    approve(http, recovery)
    assert start(http, recovery).status_code == 201
    for _ in range(5):
        await tick(company["factory"])
    saved = evidence(http, deployable)
    assert next(row for row in saved["incidents"] if row["id"] == incident["id"])["status"] == "resolved"
    receipt = next(row for row in saved["receipts"] if row["data"]["body"]["plan_id"] == recovery["id"])
    assert (
        receipt["integrity_valid"]
        and receipt["data"]["body"]["revision"] == healthy["data"]["body"]["revision"]
    )


async def test_pause_revoke_and_cancel_while_company_paused(http, company, deployable):
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    assert await tick(company["factory"])
    control = f"/workflows/{job['workflow']['id']}/control"
    assert http.post(control, json={"action": "pause"}).status_code == 200
    assert not await tick(company["factory"])
    assert http.post(control, json={"action": "resume"}).status_code == 200
    assert http.post("/controls", json={"action": "pause_company"}).status_code == 200
    assert http.post(f"/deployment-plans/{plan['id']}/revoke").status_code == 200
    assert http.post(f"/agent-work/{job['id']}/cancel").status_code == 200
    saved = evidence(http, deployable)
    assert saved["receipts"][0]["integrity_valid"]
    assert saved["receipts"][0]["status"] == "deployment_cancelled"
    assert len(saved["receipts"]) == 1 and saved["jobs"][0]["workflow"]["status"] == "cancelled"
    assert http.post(control, json={"action": "resume"}).status_code == 200  # terminal is idempotent


async def test_lost_ack_restart_and_duplicate_completion(http, company, deployable, monkeypatch):
    real_submit = adapter.submit
    calls = 0

    async def interrupted(*args):
        nonlocal calls
        calls += 1
        await real_submit(*args)
        raise OSError("Disposable acknowledgement lost after durable adapter save")

    monkeypatch.setattr(adapter, "submit", interrupted)
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, job["workflow"]["id"])
        assert workflow.step == 0 and workflow.status == "queued"
        workflow.lease_until = 0
        session.commit()
    for _ in range(5):
        await tick(company["factory"])
    saved = evidence(http, deployable)
    assert calls == 1 and len(saved["receipts"]) == 1
    receipt = saved["receipts"][0]
    assert receipt["integrity_valid"]
    with company["factory"]() as session:
        body = receipt["data"]["body"]
        before = adapter.read(session, body["job_id"], company["org"].id).data.copy()
        assert adapter.advance(session, body["job_id"], company["org"].id, 3).data == before
        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert session.execute(text("PRAGMA busy_timeout")).scalar() >= 5000
        assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert not session.execute(text("PRAGMA foreign_key_check")).all()


async def test_unknown_dispatch_never_resubmits(http, company, deployable, monkeypatch):
    async def lost_before_receipt(*args):
        raise OSError("Uncertain dispatch before adapter receipt")

    monkeypatch.setattr(adapter, "submit", lost_before_receipt)
    job = start(http, approve(http, prepare(http, deployable))).json()
    await tick(company["factory"])
    with company["factory"]() as session:
        session.get(m.Workflow, job["workflow"]["id"]).lease_until = 0
        session.commit()
    await tick(company["factory"])
    saved = evidence(http, deployable)
    assert saved["jobs"][0]["workflow"]["status"] == "needs_attention"
    assert "uncertain" in saved["jobs"][0]["workflow"]["last_error"]
    assert http.post(f"/deployments/{job['id']}/commands", json={"action": "reconcile"}).status_code == 409
    assert not saved["receipts"]


async def test_concurrent_dispatch_and_environment_separation(http, company, deployable):
    plan = approve(http, prepare(http, deployable))
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: start(http, plan), range(2)))
    assert sorted(row.status_code for row in responses) == [201, 409]
    production = http.post(
        f"/projects/{deployable['project']['id']}/deployment-targets",
        json={
            "request_id": str(uuid4()),
            "name": "Production simulation only",
            "environment": "production",
        },
    ).json()
    prod_plan = prepare(http, deployable, target_id=production["id"])
    assert prod_plan["data"]["manifest"]["required_approvals"] == ["devops_production"]
    assert start(http, prod_plan).status_code == 409
    approve(http, prod_plan)
    assert start(http, prod_plan).status_code == 201


async def test_scope_protected_records_and_reference_only_inputs(http, company, deployable):
    path = f"/projects/{deployable['project']['id']}/deployment-plans"
    basic = {
        "request_id": str(uuid4()),
        "package_id": deployable["package"]["id"],
        "target_id": deployable["target"]["id"],
        "risk_summary": "Explicit deterministic deployment simulation",
    }
    for change in (
        {"command": "sh arbitrary"},
        {"configuration_refs": {"DATABASE_URL": "postgres://secret"}},
        {"health_url": "http://host.internal"},
        {"strategy": "shell"},
        {"workspace": "../../host"},
        {"callback": {"status": "REAL_DEPLOYMENT"}},
    ):
        assert http.post(path, json={**basic, **change}).status_code == 422
    confidential = "fixture-password-value-" + str(uuid4())
    response = http.post(path, json={**basic, "risk_summary": "password=" + confidential})
    assert response.status_code == 409 and confidential not in response.text
    assert (
        http.post(
            f"/projects/{deployable['project']['id']}/deployment-targets",
            json={
                "request_id": str(uuid4()),
                "name": "Unapproved real target",
                "environment": "production",
                "adapter": "ssh",
                "url": "http://127.0.0.1/internal",
            },
        ).status_code
        == 422
    )
    plan = prepare(http, deployable, configuration_refs={"DATABASE_URL": "REF:APP_DATABASE_URL"})
    assert http.patch(f"/records/{plan['id']}", json={"version": 1, "status": "reviewed"}).status_code == 409
    with company["factory"]() as session:
        outsider = m.User(
            org_id=company["org"].id,
            client_id=company["client"].id,
            email="client-deploy@fixture.test",
            role="client",
            password_hash="unused",
        )
        session.add(outsider)
        session.flush()
        token = token_for(outsider, session)
        session.commit()
    assert (
        http.get(
            f"/projects/{deployable['project']['id']}/deployments",
            headers={"Authorization": "Bearer " + token},
        ).status_code
        == 403
    )
    with company["factory"]() as session:
        foreign_org = m.Organization(name="Foreign deployment test tenant")
        session.add(foreign_org)
        session.flush()
        foreign_owner = m.User(
            org_id=foreign_org.id, email="foreign-devops@fixture.test", role="owner", password_hash="unused"
        )
        session.add(foreign_owner)
        session.flush()
        foreign_token = token_for(foreign_owner, session)
        session.commit()
    headers = {"Authorization": "Bearer " + foreign_token}
    assert (
        http.get(f"/projects/{deployable['project']['id']}/deployments", headers=headers).status_code == 404
    )
    assert (
        http.post(
            f"/deployment-plans/{plan['id']}/approve",
            json={"version": 1, "manifest_hash": plan["data"]["manifest_hash"]},
            headers=headers,
        ).status_code
        == 404
    )


async def test_receipt_tampering_is_detected(http, company, deployable):
    _, _, receipt = await complete(http, company, deployable)
    with company["factory"]() as session:
        row = session.get(m.BusinessRecord, receipt["id"])
        row.data = {**row.data, "body": {**row.data["body"], "live_verified": True}}
        session.commit()
    assert not evidence(http, deployable)["receipts"][0]["integrity_valid"]


async def test_failed_rollbacks_stop_after_three_attempts(http, company, deployable):
    _, _, prior = await complete(http, company, deployable)
    await complete(http, company, deployable, scenario="health_failure")
    incident = evidence(http, deployable)["incidents"][0]
    for attempt in range(3):
        _, _, receipt = await complete(
            http,
            company,
            deployable,
            scenario="health_failure",
            rollback_receipt_id=prior["id"],
            incident_id=incident["id"],
        )
        assert receipt["status"] == "deployment_failed"
        saved = evidence(http, deployable)
        assert len(saved["incidents"]) == 1
        assert saved["incidents"][0]["data"]["attempts"] == attempt + 1
    assert saved["incidents"][0]["status"] == "escalated"
    response = http.post(
        f"/projects/{deployable['project']['id']}/deployment-plans",
        json={
            "request_id": str(uuid4()),
            "package_id": deployable["package"]["id"],
            "target_id": deployable["target"]["id"],
            "risk_summary": "Fourth rollback must remain blocked",
            "rollback_receipt_id": prior["id"],
            "incident_id": incident["id"],
        },
    )
    assert response.status_code == 409


async def test_cancel_unknown_job_preserves_pending_state(http, company, deployable, monkeypatch):
    async def unknown(*args):
        raise OSError("No acknowledgement")

    monkeypatch.setattr(adapter, "submit", unknown)
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    await tick(company["factory"])
    assert http.post(f"/deployment-plans/{plan['id']}/revoke").status_code == 200
    saved = evidence(http, deployable)
    assert saved["jobs"][0]["workflow"]["status"] == "needs_attention"
    assert saved["jobs"][0]["result"]["cancel_requested"]
    assert not saved["receipts"]
    assert http.post(f"/deployments/{job['id']}/commands", json={"action": "resume"}).status_code == 409


@pytest.mark.parametrize(
    "operation,stopped_step",
    [("before_dispatch", 0), ("deploy", 0), ("deploy", 1), ("deploy", 3), ("rollback", 0), ("rollback", 3)],
)
async def test_worker_process_crash_recovers_same_adapter_job(
    http, company, deployable, operation, stopped_step
):
    import os
    import subprocess
    import sys
    from pathlib import Path

    extra = {}
    previous_jobs = 0
    if operation == "rollback":
        _, _, prior = await complete(http, company, deployable)
        await complete(http, company, deployable, scenario="health_failure")
        incident = evidence(http, deployable)["incidents"][0]
        extra = {"rollback_receipt_id": prior["id"], "incident_id": incident["id"]}
        previous_jobs = 2
    plan = approve(http, prepare(http, deployable, **extra))
    job = start(http, plan).json()
    for _ in range(stopped_step):
        await tick(company["factory"])
    root = Path.cwd()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "Path",
            "SYSTEMROOT",
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "LOCALAPPDATA",
        }
    }
    environment["PYTHONPATH"] = os.pathsep.join([str(root / "apps/api"), str(root / "tests")])
    environment["AI_SPENDING_MODE"] = "ZERO_COST_ONLY"
    command = [
        sys.executable,
        str(root / "tests/deployment_process_probe.py"),
        str(company["factory"].kw["bind"].url),
        str(company["root"]),
    ]
    crashed = subprocess.run(
        [*command, "crash_before" if operation == "before_dispatch" else "crash"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert crashed.returncode == 17, crashed.stdout + crashed.stderr
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, job["workflow"]["id"])
        assert workflow.status == "running" and workflow.step == stopped_step
        workflow.lease_until = now() - 1
        session.commit()
    if operation == "before_dispatch":
        recovered = subprocess.run(
            [*command, "tick"], env=environment, capture_output=True, text=True, timeout=60
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
        saved = evidence(http, deployable)
        assert saved["jobs"][0]["workflow"]["status"] == "needs_attention"
        assert "uncertain" in saved["jobs"][0]["workflow"]["last_error"]
        assert not saved["receipts"]
        return
    for _ in range(5 - stopped_step):
        recovered = subprocess.run(
            [*command, "tick"], env=environment, capture_output=True, text=True, timeout=60
        )
        assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    company["factory"].kw["bind"].dispose()
    saved = evidence(http, deployable)
    assert len(saved["receipts"]) == previous_jobs + 1
    assert all(row["integrity_valid"] for row in saved["receipts"])
    with company["factory"]() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(m.BusinessRecord).where(m.BusinessRecord.kind == "devops_adapter_job")
                    )
                )
            )
            == previous_jobs + 1
        )


async def test_revocation_during_adapter_ack_cannot_activate(http, company, deployable, monkeypatch):
    original = adapter.submit
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()

    async def revoke_before_ack(*args):
        row = await original(*args)
        assert http.post(f"/deployment-plans/{plan['id']}/revoke").status_code == 200
        return row

    monkeypatch.setattr(adapter, "submit", revoke_before_ack)
    await tick(company["factory"])
    saved = evidence(http, deployable)
    assert saved["jobs"][0]["workflow"]["status"] == "cancelled"
    receipt = saved["receipts"][0]
    assert receipt["integrity_valid"] and receipt["status"] == "deployment_cancelled"
    assert all(event["state"] != "revision_activated" for event in receipt["data"]["body"]["events"])
    assert (
        http.post(f"/workflows/{job['workflow']['id']}/control", json={"action": "resume"}).status_code == 200
    )
    assert not await tick(company["factory"])


async def test_expiry_after_dispatch_blocks_resume_and_activation(http, company, deployable):
    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    await tick(company["factory"])
    with company["factory"]() as session:
        session.get(m.Approval, plan["data"]["approval_id"]).expires_at = now() - 1
        session.commit()
    await tick(company["factory"])
    assert (
        http.post(f"/workflows/{job['workflow']['id']}/control", json={"action": "resume"}).status_code == 409
    )
    saved = evidence(http, deployable)
    assert saved["jobs"][0]["workflow"]["status"] == "needs_attention"
    assert not saved["receipts"]
    assert http.post(f"/deployments/{job['id']}/commands", json={"action": "cancel"}).status_code == 200
    assert evidence(http, deployable)["receipts"][0]["status"] == "deployment_cancelled"


async def test_migrations_and_missing_qa_cannot_be_approved(http, company, deployable):
    plan = prepare(http, deployable, migration="manual_review_required")
    result = http.post(
        f"/deployment-plans/{plan['id']}/approve",
        json={"version": plan["version"], "manifest_hash": plan["data"]["manifest_hash"]},
    )
    assert result.status_code == 409 and "manual review" in result.text
    with company["factory"]() as session:
        # An unfinished quality plan makes QA mandatory; no direct document
        # package or AI statement can replace the missing three tool receipts.
        session.add(
            m.BusinessRecord(
                org_id=company["org"].id,
                project_id=deployable["project"]["id"],
                client_id=company["client"].id,
                kind="quality_plan",
                title="Unfinished isolated QA",
                data={},
            )
        )
        session.commit()
    response = http.post(
        f"/projects/{deployable['project']['id']}/deployment-plans",
        json={
            "request_id": str(uuid4()),
            "package_id": deployable["package"]["id"],
            "target_id": deployable["target"]["id"],
            "risk_summary": "Missing QA must block planning",
        },
    )
    assert response.status_code == 409


async def test_stale_worker_cannot_dispatch_after_owner_pause(http, company, deployable):
    from company_os.workflows import claim

    plan = approve(http, prepare(http, deployable))
    job = start(http, plan).json()
    with company["factory"]() as session:
        workflow = claim(session)
        token = workflow.lease_token
    assert http.post(f"/deployments/{job['id']}/commands", json={"action": "pause"}).status_code == 200
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, job["workflow"]["id"])
        work = session.get(m.AgentWork, job["id"])
        with pytest.raises(PermissionError, match="lease"):
            await deployments.deployment_step(
                session, workflow, token, work, session.get(m.Project, deployable["project"]["id"])
            )
        session.rollback()
        assert not work.result.get("job_id")
        assert not list(
            session.scalars(select(m.BusinessRecord).where(m.BusinessRecord.kind == "devops_adapter_job"))
        )
