"""Explicit QA transport/model fixtures. Sample code NEVER executes on the host."""

import asyncio
import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from company_os import gateway, quality
from company_os import models as m
from company_os.db import now
from company_os.providers import Response
from company_os.runner_protocol import SUITES, RunInput, request_digest
from company_os.security import digest
from company_os.workflows import tick
from pydantic import ValidationError
from sqlalchemy import select
from test_publication import publishable  # noqa: F401 — shared isolated Git/provenance fixture


def plan_body(source_hash, requirements=1):
    cases, files = [], {}
    for stage in (1, 2, 3):
        name = f"aiventra_qa/round_{stage}/test_contract.py"
        files[name] = (
            "import unittest\n\n\nclass Contract(unittest.TestCase):\n    def test_contract(self):\n        self.assertTrue(True)\n"
        )
        cases.append(
            {
                "id": f"aiventra_qa.round_{stage}.test_contract.Contract.test_contract",
                "stage": stage,
                "requirements": list(range(requirements)),
                "checks": sorted(quality.CHECKS[stage] - quality.AUTOMATIC[stage]),
            }
        )
    return {
        "source_hash": source_hash,
        "cases": cases,
        "files": files,
        "exceptions": [],
        "independence": "role",
        "repair_limit": 3,
    }


def tool_result(request, status="PASS"):
    stage = int(request.suite[-1])
    receipt = {
        "tests": 1,
        "cases": [
            {"id": f"aiventra_qa.round_{stage}.test_contract.Contract.test_contract", "status": status}
        ],
    }
    return {
        "job_id": str(request.job_id),
        "request_hash": request_digest(request),
        "status": "completed",
        "exit_code": 0 if status != "FAIL" else 1,
        "command": ["python", "-I", "/opt/aiventra/quality_runner.py", "test", str(stage)],
        "environment": "EXPLICIT dedicated Docker transport fixture; NOT actual execution",
        "logs": "AIVENTRA_QA_RESULT=" + json.dumps(receipt),
        "build": {"exit_code": 0, "logs": "EXPLICIT BUILD FIXTURE", "command": SUITES[request.suite][2]},
        "policy": {
            "network": "none",
            "user": "10001:10001",
            "read_only_root": True,
            "memory": 536870912,
            "pids": 128,
            "cpu_nano": 1000000000,
            "mount_destinations": ["/input"],
            "cap_drop": ["ALL"],
            "security": ["no-new-privileges"],
        },
    }


@pytest.fixture
async def qa_candidate(http, company, publishable, monkeypatch):  # noqa: F811
    with company["factory"]() as session:
        task = session.get(m.Task, publishable["task_id"])
        task.payload = {**task.payload, "mode": "mock"}
        approval = session.scalar(
            select(m.Approval).where(
                m.Approval.subject_id == task.id, m.Approval.category == "repository_change"
            )
        )
        approval.subject_hash = digest(task.payload)
        for run in session.scalars(select(m.ModelRun).where(m.ModelRun.task_id == task.id)):
            provider = session.get(m.Provider, session.get(m.ModelConfig, run.model_id).provider_id)
            provider.kind = "mock"
            run.cost_basis = "mock_no_charge"
        session.commit()
    original = gateway.fixture

    def fixture(schema, context):
        if schema == "ReviewResult":
            return Response(
                {
                    "approved": True,
                    "findings": [],
                    "acceptance_assessment": ["Explicit protocol fixture; not real code certification"],
                },
                0,
                0,
            )
        if schema == "QualityAssessment":
            return Response(
                {
                    "verdict": "PASS",
                    "summary": "EXPLICIT DETERMINISTIC QA ASSESSMENT; not live inference.",
                    "checked_cases": [c["id"] for c in context["cases"]],
                    "findings": [],
                },
                0,
                0,
            )
        return original(schema, context)

    monkeypatch.setattr(gateway, "fixture", fixture)
    state = {"requests": [], "status": "PASS", "results": {}}

    async def runner(request):
        state["requests"].append(request)
        value = tool_result(request, state["status"])
        state["results"][str(request.job_id)] = value
        return value

    async def stored(job_id):
        return state["results"][job_id]

    monkeypatch.setattr(quality, "run_snapshot", runner)
    monkeypatch.setattr(quality, "stored_result", stored)
    return {**publishable, "runner": state}


def prepare(http, fixture, **changes):
    source = http.get(f"/tasks/{fixture['task_id']}/quality-source")
    assert source.status_code == 200, source.text
    body = plan_body(source.json()["source_hash"], len(source.json()["source"]["criteria"]))
    body.update(changes)
    response = http.post(f"/tasks/{fixture['task_id']}/quality-plans", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def approve(http, plan):
    response = http.post(
        f"/quality-plans/{plan['id']}/approve",
        json={"version": plan["version"], "content_hash": plan["data"]["plan_hash"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def run(http, plan, **changes):
    response = http.post(
        f"/quality-plans/{plan['id']}/run",
        json={"request_id": str(uuid4()), "mode": "mock", "plan_hash": plan["data"]["plan_hash"], **changes},
    )
    return response


async def complete(company):
    for _ in range(3):
        assert await tick(company["factory"])
        company["factory"].kw["bind"].dispose()


async def test_exact_three_rounds_persist_traceability_and_immutable_report(http, company, qa_candidate):
    plan = approve(http, prepare(http, qa_candidate))
    request_id = str(uuid4())
    response = run(http, plan, request_id=request_id)
    assert response.status_code == 201, response.text
    assert run(http, plan, request_id=request_id).json()["work"]["id"] == request_id
    assert run(http, plan).status_code == 409
    await complete(company)
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert evidence["readiness"]["ready"], evidence["readiness"]["blockers"]
    assert len(evidence["reports"]) == 3
    assert all(r["data"]["body"]["classification"] == "FIXTURE_TESTED" for r in evidence["reports"])
    assert not any(r["data"]["body"]["model_independent"] for r in evidence["reports"])
    assert len(qa_candidate["runner"]["requests"]) == 3
    trace = evidence["readiness"]["manifest"]["traceability"]
    assert trace and trace[0]["commit"] == plan["data"]["source"]["commit"]
    frozen = http.post(f"/projects/{qa_candidate['project']['id']}/quality-readiness")
    assert frozen.status_code == 201
    assert frozen.json()["data"]["evaluation_hash"] == digest(frozen.json()["data"]["evaluation"])
    assert not frozen.json()["data"]["evaluation"]["manifest"]["production_ready"]
    assert (
        http.patch(f"/records/{plan['id']}", json={"version": plan["version"], "status": "open"}).status_code
        == 409
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "source",
        "plan",
        "expiry",
        "owner",
        "role",
        "artifact",
        "checkpoint",
        "execution",
        "execution_logs",
        "receipt",
        "model",
        "model_identity",
        "independence",
    ],
)
async def test_release_gate_rejects_tampering(http, company, qa_candidate, mutation):
    plan = approve(http, prepare(http, qa_candidate))
    assert run(http, plan).status_code == 201
    await complete(company)
    with company["factory"]() as session:
        saved = session.get(m.BusinessRecord, plan["id"])
        report = quality.rows(
            session, session.get(m.Project, qa_candidate["project"]["id"]), "quality_report"
        )[0]
        body = report.data["body"]
        if mutation in {"source", "plan"}:
            data = copy.deepcopy(saved.data)
            data["source" if mutation == "source" else "plan"]["tampered"] = True
            saved.data = data
        elif mutation == "expiry":
            session.get(m.Approval, saved.data["approval_id"]).expires_at = now() - 1
        elif mutation == "owner":
            session.get(m.User, company["owner"].id).enabled = False
        elif mutation == "role":
            session.get(m.Agent, body["agent_id"]).role = "Backend Developer"
        elif mutation == "artifact":
            session.get(m.Artifact, report.data["artifact_id"]).content += "changed"
        elif mutation == "checkpoint":
            session.scalar(
                select(m.WorkflowStep).where(
                    m.WorkflowStep.workflow_id == body["workflow_id"],
                    m.WorkflowStep.name == f"quality_round_{body['stage']}",
                )
            ).result = {}
        elif mutation == "execution":
            session.get(m.Execution, body["execution_id"]).exit_code = 1
        elif mutation == "execution_logs":
            session.get(m.Execution, body["execution_id"]).logs += "tampered"
        elif mutation == "receipt":
            work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == body["workflow_id"]))
            data = copy.deepcopy(work.result)
            data["executions"][str(body["stage"])]["result"]["policy"]["network"] = "host"
            work.result = data
        elif mutation == "model":
            session.get(m.ModelRun, body["run_id"]).status = "failed"
        elif mutation == "model_identity":
            session.get(m.ModelConfig, body["model_id"]).identifier = "changed-after-qa"
        else:
            data = copy.deepcopy(saved.data)
            data["plan"]["independence"] = "require_model"
            saved.data = data
        session.commit()
        result = quality.readiness(session, session.get(m.Project, qa_candidate["project"]["id"]))
        assert not result["ready"], mutation


@pytest.mark.parametrize("status", ["FAIL", "BLOCKED"])
async def test_tools_override_positive_ai_and_persist_defects(http, company, qa_candidate, status):
    plan = approve(http, prepare(http, qa_candidate))
    qa_candidate["runner"]["status"] = status
    assert run(http, plan).status_code == 201
    assert await tick(company["factory"])
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert evidence["reports"][0]["data"]["body"]["verdict"] == status
    assert not evidence["readiness"]["ready"]
    if status == "FAIL":
        defect = evidence["defects"][0]
        assert defect["data"]["requirement_id"] == plan["data"]["source"]["requirement_id"]
        assert defect["data"]["source_commit"] == plan["data"]["source"]["commit"]
        request = {"request_id": str(uuid4()), "objective": "Repair the exact independently reported defect"}
        repair = http.post(f"/quality-defects/{defect['id']}/repair", json=request)
        assert repair.status_code == 201, repair.text
        assert repair.json()["status"] == "awaiting_approval"
        assert repair.json()["payload"]["baseline_commit"] == plan["data"]["source"]["commit"]
        assert (
            http.post(f"/quality-defects/{defect['id']}/repair", json=request).json()["id"]
            == repair.json()["id"]
        )
        assert (
            http.post(
                f"/quality-defects/{defect['id']}/commands",
                json={
                    "version": defect["version"],
                    "action": "verify_close",
                    "resolution": "Developer says the defect is fixed",
                },
            ).status_code
            == 409
        )


async def test_interrupted_http_reconciles_same_job_without_duplicate_execution(
    http, company, qa_candidate, monkeypatch
):
    plan = approve(http, prepare(http, qa_candidate))
    original = quality.run_snapshot

    async def interrupted(request):
        await original(request)
        raise httpx.ReadError("Controlled lost runner response")

    monkeypatch.setattr(quality, "run_snapshot", interrupted)
    response = run(http, plan)
    assert response.status_code == 201
    assert await tick(company["factory"])
    monkeypatch.setattr(quality, "run_snapshot", original)
    assert await tick(company["factory"])
    assert len(qa_candidate["runner"]["requests"]) == 1
    await tick(company["factory"])
    await tick(company["factory"])
    assert len(qa_candidate["runner"]["requests"]) == 3
    assert http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()["readiness"]["ready"]


async def test_defect_repair_requires_owner_scope_and_fresh_unchanged_three_rounds(
    http, company, qa_candidate, monkeypatch
):
    plan = approve(http, prepare(http, qa_candidate, repair_limit=1))
    qa_candidate["runner"]["status"] = "FAIL"
    assert run(http, plan).status_code == 201
    assert await tick(company["factory"])
    project_id = qa_candidate["project"]["id"]
    defect = http.get(f"/projects/{project_id}/quality").json()["defects"][0]
    request = {
        "request_id": str(uuid4()),
        "objective": "Repair the independently reported contract fixture defect",
    }
    response = http.post(f"/quality-defects/{defect['id']}/repair", json=request)
    assert response.status_code == 201
    repair = response.json()
    assert repair["status"] == "awaiting_approval" and not await tick(company["factory"])
    from company_os.repositories import git

    with company["factory"]() as session:
        saved = session.get(m.Task, repair["id"])
        project = session.get(m.Project, project_id)
        owner_root = Path(session.get(m.Repository, saved.payload["repository_id"]).path)
        owner_head = git(owner_root, "rev-parse", "HEAD")
        parent_root = quality.repair_baseline(session, saved, project)
        assert git(parent_root, "rev-parse", "HEAD") == repair["payload"]["baseline_commit"]
        saved.payload = {**saved.payload, "baseline_commit": "0" * 40}
        with pytest.raises(PermissionError, match="baseline"):
            quality.repair_baseline(session, saved, project)
        session.rollback()

    async def engineering_fixture(workspace, suite, timeout=120, job_id=None):
        return {
            "job_id": job_id,
            "status": "completed",
            "exit_code": 0,
            "logs": "EXPLICIT TOOL FIXTURE; no generated code executed\nRan 1 test\nOK",
            "build": {"exit_code": 0},
            "environment": "Explicit dedicated Docker protocol fixture",
            "command": ["fixture-only"],
        }

    monkeypatch.setattr("company_os.engineering.run_tests", engineering_fixture)
    scope = digest(repair["payload"])
    assert http.post(f"/tasks/{repair['id']}/approve", json={"content_hash": "a" * 64}).status_code == 409
    assert http.post(f"/tasks/{repair['id']}/approve", json={"content_hash": scope}).status_code == 200
    for _ in range(5):
        await tick(company["factory"])
    with company["factory"]() as session:
        task = session.get(m.Task, repair["id"])
        assert task.status == "completed", task.evidence
        assert git(owner_root, "rev-parse", "HEAD") == owner_head
    repaired_fixture = {**qa_candidate, "task_id": repair["id"]}
    source = http.get(f"/tasks/{repair['id']}/quality-source").json()
    weakened = plan_body(source["source_hash"], len(source["source"]["criteria"]))
    weakened["repair_limit"] = 0
    assert http.post(f"/tasks/{repair['id']}/quality-plans", json=weakened).status_code == 409
    fresh = approve(http, prepare(http, repaired_fixture, repair_limit=1))
    qa_candidate["runner"]["status"] = "PASS"
    assert run(http, fresh).status_code == 201
    await complete(company)
    current = http.get(f"/projects/{project_id}/quality").json()["defects"][0]
    closed = http.post(
        f"/quality-defects/{defect['id']}/commands",
        json={
            "version": current["version"],
            "action": "verify_close",
            "resolution": "Three fresh independent fixture assessments verified the changed source",
        },
    )
    assert closed.status_code == 200, closed.text
    assert http.get(f"/projects/{project_id}/quality").json()["readiness"]["ready"]
    assert (
        http.post(
            f"/quality-defects/{defect['id']}/commands",
            json={
                "version": closed.json()["version"],
                "action": "reopen",
                "resolution": "Owner identified a new regression requiring investigation",
            },
        ).status_code
        == 200
    )
    assert not http.get(f"/projects/{project_id}/quality").json()["readiness"]["ready"]
    for _ in range(2):
        denied = http.post(
            f"/quality-defects/{defect['id']}/repair",
            json={"request_id": str(uuid4()), "objective": "Attempt another repair beyond the approved cap"},
        )
        assert denied.status_code == 409 and "limit" in denied.text
    escalated = http.get(f"/projects/{project_id}/quality").json()["defects"][0]
    assert escalated["status"] == "needs_owner"
    assert escalated["data"]["repair_tasks"] == [repair["id"]]
    assert sum(h["action"] == "repair_limit_escalated" for h in escalated["data"]["history"]) == 1


async def test_quality_scope_rejects_missing_project_and_other_tenant(http, company, qa_candidate):
    plan = prepare(http, qa_candidate)
    with company["factory"]() as session:
        record = session.get(m.BusinessRecord, plan["id"])
        session.add(m.Organization(id="foreign-tenant", name="Isolated foreign tenant fixture"))
        session.flush()
        record.org_id = "foreign-tenant"
        session.commit()
    assert (
        http.post(
            f"/quality-plans/{plan['id']}/approve",
            json={"version": plan["version"], "content_hash": plan["data"]["plan_hash"]},
        ).status_code
        == 404
    )
    with company["factory"]() as session:
        record = session.get(m.BusinessRecord, plan["id"])
        record.org_id = company["org"].id
        record.project_id = None  # Missing project authority must not become executable.
        session.commit()
    assert run(http, plan).status_code == 409
    from test_agent_planning import draft_project

    requirement = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Separate QA isolation project",
            "text": "Create a separate harmless project to verify that QA candidate authority cannot cross project boundaries.",
            "mode": "mock",
        },
    ).json()
    other, _ = await draft_project(http, company, requirement)
    assert other["id"] != qa_candidate["project"]["id"]
    with company["factory"]() as session:
        assert session.get(m.Task, qa_candidate["task_id"]).status == "completed"
        session.get(m.BusinessRecord, plan["id"]).project_id = other["id"]
        session.commit()
    denied = run(http, plan)
    assert denied.status_code == 409 and "another project" in denied.text


async def test_cancel_and_pause_preserve_checkpoints_and_do_not_fabricate_results(
    http, company, qa_candidate
):
    plan = approve(http, prepare(http, qa_candidate))
    work = run(http, plan).json()
    workflow_id = work["workflow"]["id"]
    assert http.post(f"/workflows/{workflow_id}/control", json={"action": "pause"}).status_code == 200
    assert not await tick(company["factory"])
    assert http.post(f"/workflows/{workflow_id}/control", json={"action": "resume"}).status_code == 200
    assert await tick(company["factory"])
    assert http.post(f"/agent-work/{work['work']['id']}/cancel").status_code == 200
    assert not await tick(company["factory"])
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert len(evidence["reports"]) == 1 and not evidence["readiness"]["ready"]
    assert len(qa_candidate["runner"]["requests"]) == 1


async def test_required_model_independence_cannot_be_claimed_by_fixture_assessment(
    http, company, qa_candidate
):
    plan = approve(http, prepare(http, qa_candidate, independence="require_model"))
    assert run(http, plan).status_code == 201
    await complete(company)
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert not evidence["readiness"]["ready"]
    assert any("independence" in blocker for blocker in evidence["readiness"]["blockers"])


async def test_inflight_cancel_revokes_lease_and_cancels_exact_runner_identity(
    http, company, qa_candidate, monkeypatch
):
    started = asyncio.Event()
    dispatched, cancelled = [], []

    async def pending(request):
        dispatched.append(str(request.job_id))
        started.set()
        await asyncio.Event().wait()

    async def cancel(job_id):
        cancelled.append(job_id)
        return {"status": "cancellation_requested"}

    monkeypatch.setattr(quality, "run_snapshot", pending)
    monkeypatch.setattr(quality, "cancel_job", cancel)
    plan = approve(http, prepare(http, qa_candidate))
    work = run(http, plan).json()
    operation = asyncio.create_task(tick(company["factory"]))
    try:
        await asyncio.wait_for(started.wait(), timeout=60)
        assert http.post(f"/agent-work/{work['work']['id']}/cancel").status_code == 200
        await asyncio.wait_for(operation, timeout=10)
    finally:
        if not operation.done():
            operation.cancel()
        await asyncio.gather(operation, return_exceptions=True)
    assert dispatched == cancelled and len(dispatched) == 1
    with company["factory"]() as session:
        assert session.get(m.Workflow, work["workflow"]["id"]).status == "cancelled"
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert not evidence["reports"] and not evidence["readiness"]["ready"]


async def test_actual_worker_process_restart_recovers_exact_job_and_sqlite_records(
    http, company, qa_candidate
):
    plan = approve(http, prepare(http, qa_candidate))
    work = run(http, plan).json()
    root = Path.cwd()
    fixture_root = company["root"].resolve()
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
        str(root / "tests/quality_process_probe.py"),
        str(company["factory"].kw["bind"].url),
        str(fixture_root),
    ]
    crashed = subprocess.run([*command, "crash"], env=environment, capture_output=True, text=True, timeout=60)
    assert crashed.returncode == 17, crashed.stdout + crashed.stderr
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, work["workflow"]["id"])
        assert workflow.status == "running" and workflow.step == 0
        workflow.lease_until = now() - 1  # Only this disposable fixture; no production lease change.
        session.commit()
    for _ in range(3):
        completed = subprocess.run(
            [*command, "tick"], env=environment, capture_output=True, text=True, timeout=60
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    company["factory"].kw["bind"].dispose()
    evidence = http.get(f"/projects/{qa_candidate['project']['id']}/quality").json()
    assert evidence["readiness"]["ready"], evidence["readiness"]["blockers"]
    assert len(evidence["reports"]) == len(list(fixture_root.glob("*.fixture-result.json"))) == 3
    with company["factory"]() as session:
        from sqlalchemy import text

        assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
        assert not session.execute(text("PRAGMA foreign_key_check")).all()


@pytest.mark.parametrize(
    "mutation",
    [
        "path",
        "missing_check",
        "duplicate",
        "wrong_stage",
        "empty_requirements",
        "mandatory_exception",
        "security_exception",
    ],
)
def test_plan_rejects_unsafe_missing_and_ambiguous_checks(mutation):
    data = plan_body("a" * 64)
    if mutation == "path":
        data["files"]["../escape.py"] = "bad"
    elif mutation == "missing_check":
        data["cases"][0]["checks"] = ["unit"]
    elif mutation == "duplicate":
        data["cases"].append(data["cases"][0])
    elif mutation == "wrong_stage":
        data["cases"][0]["stage"] = 2
    elif mutation == "empty_requirements":
        data["cases"][0]["requirements"] = []
    elif mutation == "mandatory_exception":
        data["exceptions"] = [
            {"stage": 3, "check": "secrets", "reason": "Skipping an essential automatic tool check is unsafe"}
        ]
    else:
        data["exceptions"] = [
            {
                "stage": 3,
                "check": "security",
                "reason": "Owner exceptions cannot waive essential security tests",
            }
        ]
    with pytest.raises(ValidationError):
        quality.PlanInput.model_validate(data)


@pytest.mark.parametrize(
    "change",
    ["empty", "skipped", "missing", "identity", "policy", "build", "timeout", "duplicate", "malformed"],
)
def test_tool_failure_and_missing_receipts_never_pass(change):
    request = RunInput(job_id=uuid4(), suite="python-qa-1", files={"fixture.txt": "Fixture only"})
    result = tool_result(request)
    if change == "empty":
        result["logs"] = 'AIVENTRA_QA_RESULT={"tests":0,"cases":[]}'
    elif change == "skipped":
        result = tool_result(request, "BLOCKED")
    elif change == "missing":
        result["logs"] = "No test receipt"
    elif change == "identity":
        result["logs"] = result["logs"].replace("test_contract.Contract", "test_other.Contract")
    elif change == "policy":
        result["policy"]["network"] = "host"
    elif change == "build":
        result["build"]["exit_code"] = 1
        result["command"] = SUITES[request.suite][2]
    elif change == "duplicate":
        result["logs"] += "\n" + result["logs"]
    elif change == "malformed":
        result["logs"] += " extra JSON data"
    else:
        result["exit_code"] = 124
    verdict = quality.test_result(result, 1, plan_body("a" * 64))["verdict"]
    assert verdict != "PASS"
    if change == "build":
        assert verdict == "FAIL"


@pytest.mark.parametrize("summary", ["\n\nOK\n", "\nRan 1 test in 0.020s\n\nOK\n"])
def test_qa_receipt_survives_docker_stdout_stderr_reordering(summary):
    request = RunInput(job_id=uuid4(), suite="python-qa-1", files={"fixture.txt": "Fixture only"})
    result = tool_result(request)
    result["logs"] = "unittest output\n" + result["logs"] + summary
    assert quality.test_result(result, 1, plan_body("a" * 64))["verdict"] == "PASS"
