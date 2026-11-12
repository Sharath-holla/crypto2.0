"""Source-pinned three-stage QA on existing approvals, jobs, artifacts and leases.

Tests run exclusively in the dedicated broker. Owner-authored test plans are
explicit authority, not fabricated AI tests. Model assessments cannot override
tool failures, missing coverage, stale sources or unresolved defects.
"""

import asyncio
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from . import models as m
from .artifacts import save_artifact
from .db import now, uid
from .gateway import execute
from .organization import agent_for
from .providers import model_identity
from .publication import PublicationError, candidate
from .runner_protocol import SUITES, RunInput, request_digest
from .sandbox import cancel_job, run_snapshot, snapshot, stored_result
from .schemas import Strict
from .security import audit, canonical, check_agent, clean, digest
from .staffing import lock_org
from .workflows import checkpoint, project_authority

ROLES = ("QA Director", "QA Director", "Security Architect")
CHECKS = {
    1: {
        "build",
        "unit",
        "integration",
        "static",
        "format",
        "lint",
        "api",
        "validation",
        "database",
        "errors",
    },
    2: {"functional", "e2e", "negative", "auth", "authorization", "persistence", "regression", "errors"},
    3: {
        "security",
        "dependencies",
        "secrets",
        "authorization",
        "production_build",
        "performance",
        "resources",
        "deployment",
        "migration",
        "recovery",
        "rollback",
        "environment",
        "documentation",
    },
}
AUTOMATIC = {1: {"build", "static", "format", "lint"}, 2: set(), 3: {"secrets", "resources"}}
NON_WAIVABLE = {1: AUTOMATIC[1], 2: set(), 3: {"security", "authorization", "secrets", "resources"}}


class Case(Strict):
    id: str = Field(pattern=r"^aiventra_qa\.round_[123]\.test_[a-z0-9_]+\.[A-Za-z0-9_]+\.test_[A-Za-z0-9_]+$")
    stage: int = Field(ge=1, le=3)
    requirements: list[int] = Field(min_length=1, max_length=20)
    checks: list[str] = Field(min_length=1, max_length=12)


class ExceptionPolicy(Strict):
    stage: int = Field(ge=1, le=3)
    check: str
    reason: str = Field(min_length=30, max_length=1000)


class PlanInput(Strict):
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    files: dict[str, str] = Field(min_length=3, max_length=40)
    cases: list[Case] = Field(min_length=3, max_length=100)
    exceptions: list[ExceptionPolicy] = Field(default_factory=list, max_length=30)
    independence: Literal["role", "require_model", "require_provider"] = "role"
    repair_limit: int = Field(default=3, ge=0, le=3)

    @model_validator(mode="after")
    def coverage(self):
        allowed = set()
        for case in self.cases:
            if not case.id.startswith(f"aiventra_qa.round_{case.stage}."):
                raise ValueError("Test identifier and QA stage differ")
            if not set(case.checks).issubset(CHECKS[case.stage]):
                raise ValueError("Unknown risk-policy check")
            if len(set(case.requirements)) != len(case.requirements) or min(case.requirements) < 0:
                raise ValueError("Requirement indexes must be distinct and nonnegative")
            allowed.add(case.id.rsplit(".", 2)[0].replace(".", "/") + ".py")
        if len({c.id for c in self.cases}) != len(self.cases) or set(self.files) != allowed:
            raise ValueError("Unique test cases and exactly their corresponding files are required")
        RunInput(job_id=uid(), suite="python-qa-1", files=self.files)
        if sum(len(body.encode()) for body in self.files.values()) > 200_000:
            raise ValueError("Independent test plan exceeds the bounded 200 KB evidence limit")
        if len({(e.stage, e.check) for e in self.exceptions}) != len(self.exceptions):
            raise ValueError("Policy exceptions must be distinct")
        for item in self.exceptions:
            if item.check not in CHECKS[item.stage] or item.check in NON_WAIVABLE[item.stage]:
                raise ValueError("Unknown or mandatory tool check cannot be excepted")
        for stage in CHECKS:
            covered = AUTOMATIC[stage] | {check for c in self.cases if c.stage == stage for check in c.checks}
            covered |= {e.check for e in self.exceptions if e.stage == stage}
            if covered != CHECKS[stage]:
                raise ValueError(f"Round {stage} missing checks: {sorted(CHECKS[stage] - covered)}")
        if clean(self.model_dump()) != self.model_dump():
            raise ValueError("Sensitive material is prohibited in a QA plan")
        return self


class Finding(Strict):
    case_id: str = Field(max_length=200)
    severity: Literal["low", "medium", "high", "critical"]
    description: str = Field(min_length=10, max_length=2000)
    reproduction: str = Field(min_length=5, max_length=2000)
    expected: str = Field(min_length=5, max_length=1000)
    actual: str = Field(min_length=5, max_length=1000)


class QualityAssessment(Strict):
    verdict: Literal["PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"]
    summary: str = Field(min_length=20, max_length=2000)
    checked_cases: list[str] = Field(min_length=1, max_length=100)
    findings: list[Finding] = Field(max_length=20)


def rows(session, project, kind):
    return list(
        session.scalars(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.org_id == project.org_id,
                m.BusinessRecord.project_id == project.id,
                m.BusinessRecord.kind == kind,
            )
            .order_by(m.BusinessRecord.created_at, m.BusinessRecord.id)
        )
    )


def model_key(session, model_id, org_id):
    model = session.get(m.ModelConfig, model_id)
    provider = session.get(m.Provider, model.provider_id) if model else None
    if not model or model.org_id != org_id or not provider or provider.org_id != org_id:
        raise PermissionError("QA model identity requires same-tenant provenance")
    return list(model_identity(model, provider))


def author_keys(session, authors, org_id):
    return sorted({tuple(model_key(session, mid, org_id)) for mid in authors})


def source(session, task):
    project = session.get(m.Project, task.project_id)
    try:
        workspace, _, draft, tree, _ = candidate(
            session, task, nonproduction=task.payload.get("mode") == "mock"
        )
    except PublicationError as exc:
        raise PermissionError(str(exc)) from None
    if task.payload.get("test_suite") != "python-unittest":
        raise PermissionError(
            "Three-stage QA currently requires the approved Python runtime; other profiles are blocked"
        )
    proposal = session.get(m.Proposal, project.proposal_id)
    requirement = session.get(m.Requirement, proposal.requirement_id)
    from .architecture_design import selected_context

    manifest = {
        "task_id": task.id,
        "task_version": task.version,
        "scope_hash": digest(task.payload),
        "project_id": project.id,
        "client_id": project.client_id,
        "project_version": project.version,
        "commit": draft["head_commit"],
        "tree": tree,
        "requirement_id": requirement.id,
        "requirement_version": requirement.version,
        "proposal_hash": digest(proposal.content),
        "criteria": proposal.content.get("acceptance_criteria", []),
        "design": selected_context(proposal, project),
        "snapshot_hash": digest(snapshot(workspace)),
        "tool_profile_hash": digest(
            {
                "profiles": {name: spec for name, spec in SUITES.items() if name.startswith("python-qa-")},
                "harness": Path(__file__).with_name("quality_runner.py").read_text(),
                "checks": {str(stage): sorted(checks) for stage, checks in CHECKS.items()},
                "automatic": {str(stage): sorted(checks) for stage, checks in AUTOMATIC.items()},
                "non_waivable": {str(stage): sorted(checks) for stage, checks in NON_WAIVABLE.items()},
                "policy_version": 1,
            }
        ),
    }
    return workspace, manifest


def authority(session, plan):
    project = session.get(m.Project, plan.project_id) if plan.project_id else None
    if not project or project.org_id != plan.org_id:
        raise PermissionError("QA plan requires an existing same-tenant project")
    project_authority(session, project)
    task = session.get(m.Task, plan.data["source"]["task_id"])
    if not task or task.org_id != project.org_id or task.project_id != project.id:
        raise PermissionError("QA candidate belongs to another project or tenant")
    workspace, current = source(session, task)
    approval = session.get(m.Approval, plan.data.get("approval_id"))
    owner = session.get(m.User, approval.owner_id) if approval else None
    if (
        plan.org_id != project.org_id
        or plan.client_id != project.client_id
        or plan.kind != "quality_plan"
        or plan.status != "approved"
        or digest(current) != plan.data["source_hash"]
        or current != plan.data["source"]
        or digest(plan.data["plan"]) != plan.data["plan_hash"]
        or not approval
        or approval.org_id != plan.org_id
        or approval.category != "quality_plan"
        or approval.subject_id != plan.id
        or approval.version != plan.version
        or approval.subject_hash != digest({"source": current, "plan": plan.data["plan"]})
        or approval.expires_at <= now()
        or not owner
        or not owner.enabled
        or owner.role != "owner"
    ):
        raise PermissionError("QA requires current source and exact unexpired owner test-plan approval")
    return project, task, workspace


def prepare(session, task, user, data):
    lock_org(session, user.org_id)
    session.refresh(task)
    _, manifest = source(session, task)
    if digest(manifest) != data.source_hash:
        raise PermissionError("Candidate changed; refresh QA source before preparing tests")
    criteria = manifest["criteria"]
    if not criteria or len(criteria) > 20:
        raise PermissionError("One to twenty approved requirements are required")
    for stage in (1, 2):
        indexes = {i for c in data.cases if c.stage == stage for i in c.requirements}
        if indexes != set(range(len(criteria))):
            raise PermissionError(f"Round {stage} must trace every approved acceptance criterion")
    if any(i >= len(criteria) for c in data.cases for i in c.requirements):
        raise PermissionError("Unknown approved requirement index")
    defect_id = task.payload.get("quality_defect_id")
    if defect_id:
        original = session.get(m.BusinessRecord, session.get(m.BusinessRecord, defect_id).data["plan_id"])
        for key in ("files", "cases", "exceptions", "independence", "repair_limit"):
            if data.model_dump()[key] != original.data["plan"][key]:
                raise PermissionError(
                    "Repair verification cannot weaken or replace the original approved QA plan"
                )
    record = m.BusinessRecord(
        id=uid(),
        org_id=task.org_id,
        project_id=task.project_id,
        client_id=manifest["client_id"],
        kind="quality_plan",
        title="Owner-authored three-stage QA plan",
        status="awaiting_approval",
        data={
            "source": manifest,
            "source_hash": digest(manifest),
            "plan": data.model_dump(exclude={"source_hash"}),
            "plan_hash": digest(data.model_dump(exclude={"source_hash"})),
            "origin": "owner_authored",
        },
    )
    project = session.get(m.Project, task.project_id)
    record.version = max((p.version for p in rows(session, project, "quality_plan")), default=0) + 1
    session.add(record)
    audit(
        session,
        task.org_id,
        user.id,
        "quality.plan_prepared",
        record.id,
        {"source_hash": digest(manifest)},
        project_id=task.project_id,
    )
    return record


def approve(session, plan, user, version, plan_hash):
    lock_org(session, user.org_id)
    session.refresh(plan)
    task = session.get(m.Task, plan.data["source"]["task_id"])
    _, manifest = source(session, task)
    if (
        plan.version != version
        or plan.data["plan_hash"] != plan_hash
        or plan.status != "awaiting_approval"
        or manifest != plan.data["source"]
    ):
        raise PermissionError("Approve the exact current QA plan version and candidate")
    if digest(plan.data["plan"]) != plan_hash:
        raise PermissionError("QA plan integrity failed")
    PlanInput(source_hash=digest(manifest), **plan.data["plan"])
    approval = m.Approval(
        id=uid(),
        org_id=user.org_id,
        category="quality_plan",
        subject_id=plan.id,
        subject_hash=digest({"source": manifest, "plan": plan.data["plan"]}),
        version=plan.version,
        owner_id=user.id,
        expires_at=now() + 7 * 86400,
    )
    session.add(approval)
    plan.status, plan.data = "approved", {**plan.data, "approval_id": approval.id}
    audit(
        session,
        user.org_id,
        user.id,
        "quality.plan_approved",
        plan.id,
        {"approval_id": approval.id, "plan_hash": plan_hash},
        project_id=plan.project_id,
    )


def defect(session, project, plan, stage, finding, report_id, actor):
    case = next(
        (c for c in plan.data["plan"]["cases"] if c["id"] == finding.case_id and c["stage"] == stage), None
    )
    if not case:
        raise PermissionError("Defect must identify an approved case in this round")
    key = digest({"plan": plan.id, "stage": stage, "case": case["id"], "report": report_id})
    existing = next((r for r in rows(session, project, "quality_defect") if r.data["key"] == key), None)
    if existing:
        return existing
    record = m.BusinessRecord(
        id=uid(),
        org_id=project.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="quality_defect",
        title=finding.description[:200],
        status="open",
        data={
            **finding.model_dump(),
            "key": key,
            "plan_id": plan.id,
            "report_id": report_id,
            "stage": stage,
            "source_commit": plan.data["source"]["commit"],
            "task_id": plan.data["source"]["task_id"],
            "requirement_id": plan.data["source"]["requirement_id"],
            "requirement_indexes": case["requirements"],
            "priority": "P0"
            if finding.severity == "critical"
            else "P1"
            if finding.severity == "high"
            else "P2",
            "assigned_developer": None,
            "repair_tasks": [],
            "resolution": "",
            "verification": "unverified",
            "history": [{"action": "created", "actor": actor, "at": now()}],
        },
    )
    session.add(record)
    manager = agent_for(session, project.org_id, "Project Manager")
    session.add(
        m.Message(
            org_id=project.org_id,
            project_id=project.id,
            sender=actor,
            recipient=manager.id,
            type="EscalationRaised",
            correlation_id=record.id,
            content={"defect_id": record.id, "plan_id": plan.id, "report_id": report_id},
            authorization=f"quality-plan:{plan.data['approval_id']}",
        )
    )
    session.add(
        m.Notification(org_id=project.org_id, severity="warning", title=record.title, subject_id=record.id)
    )
    audit(
        session,
        project.org_id,
        actor,
        "quality.defect_created",
        record.id,
        {"stage": stage, "severity": finding.severity, "report_id": report_id},
        project_id=project.id,
    )
    return record


def test_result(result, stage, plan):
    """No empty, skipped, absent, forged-scope or failing tool output becomes PASS."""
    cases = [c for c in plan["cases"] if c["stage"] == stage]
    expected = {c["id"] for c in cases}
    try:
        # Docker multiplexes stdout/stderr; unittest's summary may arrive after
        # the harness receipt. Accept one complete receipt line, never an
        # ambiguous duplicate or an arbitrary JSON suffix of combined logs.
        prefix = "AIVENTRA_QA_RESULT="
        lines = [line for line in str(result.get("logs", "")).splitlines() if line.startswith(prefix)]
        if len(lines) != 1:
            raise ValueError("Exactly one QA receipt is required")
        receipt = json.loads(lines[0][len(prefix) :])
        observed = {c["id"] for c in receipt["cases"]}
        if receipt["tests"] < len(expected) or not expected.issubset(observed):
            raise ValueError("Missing approved test cases")
        if any(c["status"] == "FAIL" for c in receipt["cases"]) or result["exit_code"] != 0:
            verdict = "FAIL"
        elif any(c["status"] != "PASS" for c in receipt["cases"]):
            verdict = "BLOCKED"
        else:
            verdict = "PASS"
    except (ValueError, KeyError, TypeError):
        receipt, verdict = {"tests": 0, "cases": []}, "INCONCLUSIVE"
    if result.get("exit_code") in {124, 125}:
        verdict = "BLOCKED"
    elif result.get("build", {}).get("exit_code") != 0:
        verdict = "FAIL"
    policy = result.get("policy", {})
    actual_isolation = (
        policy.get("network") == "none"
        and policy.get("user") == "10001:10001"
        and policy.get("read_only_root") is True
        and policy.get("memory") == 536870912
        and policy.get("pids") == 128
        and policy.get("cpu_nano") == 1000000000
        and "/input" in policy.get("mount_destinations", [])
        and set(policy.get("mount_destinations", [])).issubset({"/input", "/tmp", "/workspace"})
        and policy.get("cap_drop") == ["ALL"]
        and "no-new-privileges" in policy.get("security", [])
    )
    if not actual_isolation or "dedicated Docker" not in result.get("environment", ""):
        verdict = "INCONCLUSIVE"
    profile = SUITES[f"python-qa-{stage}"]
    command = profile[2] if result.get("build", {}).get("exit_code") != 0 else profile[1]
    if result.get("command") != command or result.get("build", {}).get("command") != profile[2]:
        verdict = "INCONCLUSIVE"
    return {"verdict": verdict, **receipt}


async def tool_receipt(session, workflow, token, work, plan, task, workspace, stage, agent):
    executions = work.result.get("executions", {})
    saved = executions.get(str(stage))
    if saved and saved.get("result"):
        if digest(saved["result"]) != saved["result_hash"]:
            raise PermissionError("Saved QA tool receipt changed")
        return saved
    files = snapshot(workspace)
    if any(name == "aiventra_qa" or name.startswith("aiventra_qa/") for name in files):
        raise PermissionError("Candidate collides with reserved independent QA overlay")
    files.update(plan.data["plan"]["files"])
    for folder in ("aiventra_qa", "aiventra_qa/round_1", "aiventra_qa/round_2", "aiventra_qa/round_3"):
        files[folder + "/__init__.py"] = ""
    execution_id = saved["execution_id"] if saved else uid()
    request = RunInput(job_id=execution_id, suite=f"python-qa-{stage}", files=files)
    request_hash = request_digest(request)
    if saved:
        if saved["request_hash"] != request_hash:
            raise PermissionError("Interrupted QA request changed")
        # Never POST an uncertain request again. Reconcile its durable broker result.
        result = await stored_result(execution_id)
        if result.get("status") == "running":
            raise PermissionError("QA runner still active; owner recovery must retain the same job ID")
    else:
        execution = m.Execution(
            id=execution_id,
            org_id=task.org_id,
            task_id=task.id,
            agent_id=agent.id,
            workspace=str(workspace),
            command=[request.suite],
            environment="dedicated Docker; pending",
            commit_hash=plan.data["source"]["commit"],
        )
        session.add(execution)
        saved = {"execution_id": execution_id, "request_hash": request_hash}
        work.result = {**work.result, "executions": {**executions, str(stage): saved}}
        session.commit()  # Durable identity BEFORE HTTP; no SQLite writer spans execution.
        operation = asyncio.create_task(run_snapshot(request))
        try:
            while not operation.done():
                await asyncio.wait({operation}, timeout=1)
                session.expire_all()
                session.refresh(workflow)
                if workflow.status != "running" or workflow.lease_token != token:
                    await cancel_job(execution_id)
                    operation.cancel()
                    raise PermissionError("QA cancelled or lease revoked; reconcile exact runner job")
            result = await operation
        finally:
            if not operation.done():
                operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
    if result.get("job_id") != execution_id or result.get("request_hash") != request_hash:
        raise PermissionError("QA broker receipt identity does not match its approved snapshot")
    lock_org(session, task.org_id)
    session.expire_all()
    execution = session.get(m.Execution, execution_id)
    execution.status = result.get("status", "interrupted")
    execution.exit_code, execution.ended_at = result.get("exit_code"), now()
    execution.command = result.get("command", [])
    execution.environment = result.get("environment", "unknown")[:200]
    execution.logs = clean(str(result.get("build", {}).get("logs", "")) + "\n" + str(result.get("logs", "")))[
        :500100
    ]
    saved = {**saved, "result": clean(result), "result_hash": digest(clean(result))}
    work.result = {**work.result, "executions": {**work.result.get("executions", {}), str(stage): saved}}
    session.commit()  # Retain tool evidence even when model inference waits or the lease is lost.
    authority(session, plan)
    return saved


async def quality_step(session, workflow, token, work, project):
    plan = session.get(m.BusinessRecord, work.subject_id)
    if (
        not plan
        or plan.org_id != work.org_id
        or plan.project_id != work.project_id
        or work.input.get("plan_hash") != plan.data["plan_hash"]
    ):
        raise PermissionError("QA work scope changed")
    project, task, workspace = authority(session, plan)
    stage = workflow.step + 1
    if stage not in CHECKS:
        raise PermissionError("Invalid QA checkpoint")
    agent = session.get(m.Agent, work.participants[stage - 1])
    if agent.org_id != task.org_id or agent.role != ROLES[stage - 1] or agent.id == task.assigned_agent_id:
        raise PermissionError("QA role must be independent of the developer")
    check_agent(session, agent, "run_tests" if stage < 3 else "write_artifact", project)
    saved = await tool_receipt(session, workflow, token, work, plan, task, workspace, stage, agent)
    tools = test_result(saved["result"], stage, plan.data["plan"])
    cases = [c for c in plan.data["plan"]["cases"] if c["stage"] == stage]
    authors = list(
        session.scalars(
            select(m.ModelRun.model_id).where(
                m.ModelRun.task_id == task.id,
                m.ModelRun.agent_id == task.assigned_agent_id,
                m.ModelRun.status == "succeeded",
            )
        )
    )
    name = f"quality_round_{stage}"
    assessment = await execute(
        session,
        workflow,
        agent,
        name,
        QualityAssessment,
        {
            "objective": "Independently assess exact approved QA cases and actual tool evidence. Never override failures or claim deployment. Fixture output must be labeled.",
            "source": plan.data["source"],
            "cases": cases,
            "tools": tools,
            "test_sources": {
                path: body for path, body in plan.data["plan"]["files"].items() if f"/round_{stage}/" in path
            },
            "logs": saved["result"].get("logs", "")[-12000:],
            "build": saved["result"].get("build", {}),
            "exceptions": plan.data["plan"]["exceptions"],
        },
        quality=80,
        project=project,
        review_against=authors if workflow.mode == "live" else [],
        review_policy=plan.data["plan"]["independence"]
        if plan.data["plan"]["independence"] != "role"
        else "prefer_provider",
    )
    if sorted(assessment.checked_cases) != sorted(c["id"] for c in cases):
        raise PermissionError("QA assessment must cover every exact test case once")
    lock_org(session, work.org_id)
    session.expire_all()
    authority(session, plan)
    check_agent(session, agent, "write_artifact", project)
    run = session.scalar(
        select(m.ModelRun).where(
            m.ModelRun.workflow_id == workflow.id,
            m.ModelRun.step_name == name,
            m.ModelRun.status == "succeeded",
        )
    )
    verdict = tools["verdict"] if tools["verdict"] != "PASS" else assessment.verdict
    if assessment.findings:
        verdict = "FAIL"
    terminal = verdict != "PASS" or stage == 3
    checkpoint(session, workflow, token, name, {}, complete=terminal)
    report_id = uid()
    identity = model_key(session, run.model_id, project.org_id)
    identities = [list(key) for key in author_keys(session, authors, project.org_id)]
    body = {
        "plan_id": plan.id,
        "source_hash": plan.data["source_hash"],
        "plan_hash": plan.data["plan_hash"],
        "stage": stage,
        "verdict": verdict,
        "tools": tools,
        "assessment": assessment.model_dump(),
        "execution_id": saved["execution_id"],
        "receipt_hash": saved["result_hash"],
        "run_id": run.id,
        "agent_id": agent.id,
        "role": agent.role,
        "model_id": run.model_id,
        "model_identity": identity,
        "author_identities": identities,
        "model_independent": identity not in identities and workflow.mode == "live",
        "mode": workflow.mode,
        "verified_at": now(),
        "workflow_id": workflow.id,
        "classification": "FIXTURE_TESTED"
        if workflow.mode == "mock"
        else "LOCAL_OR_CONFIGURED_AI_ASSESSMENT",
        "position": max(
            (r.data["body"].get("position", 0) for r in rows(session, project, "quality_report")), default=0
        )
        + 1,
    }
    artifact = save_artifact(
        session,
        work.org_id,
        f"QA round {stage} immutable evidence",
        canonical(body),
        "quality_report",
        project_id=project.id,
        agent_id=agent.id,
    )
    report = m.BusinessRecord(
        id=report_id,
        org_id=work.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="quality_report",
        title=f"Round {stage} — {verdict}",
        status=verdict,
        data={
            "body": body,
            "body_hash": digest(body),
            "artifact_id": artifact.id,
            "artifact_hash": artifact.sha256,
        },
    )
    session.add(report)
    saved_step = session.scalar(
        select(m.WorkflowStep).where(m.WorkflowStep.workflow_id == workflow.id, m.WorkflowStep.name == name)
    )
    saved_step.result = {"report_id": report.id, "body_hash": digest(body), "artifact_id": artifact.id}
    findings = list(assessment.findings)
    failed = {c["id"] for c in tools["cases"] if c["status"] == "FAIL"}
    if verdict == "FAIL" and not failed and not findings:
        failed = {cases[0]["id"]}
    for case_id in failed - {f.case_id for f in findings}:
        findings.append(
            Finding(
                case_id=case_id,
                severity="high",
                description="Approved QA tool check failed",
                reproduction=f"Run approved plan {plan.id} round {stage} in the restricted runner",
                expected="All approved checks pass",
                actual="See immutable command output and exit codes",
            )
        )
    for finding in findings:
        defect(session, project, plan, stage, finding, report.id, agent.id)
    work.result = {**work.result, "reports": [*work.result.get("reports", []), report.id], "status": verdict}
    audit(
        session,
        work.org_id,
        agent.id,
        "quality.round_verified",
        report.id,
        {"verdict": verdict, "stage": stage, "body_hash": digest(body)},
        project_id=project.id,
    )


def validate_report(session, project, plan, report):
    body = report.data["body"]
    artifact = session.get(m.Artifact, report.data["artifact_id"])
    run = session.get(m.ModelRun, body["run_id"])
    work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == body["workflow_id"]))
    workflow = session.get(m.Workflow, body["workflow_id"])
    step = session.scalar(
        select(m.WorkflowStep).where(
            m.WorkflowStep.workflow_id == body["workflow_id"],
            m.WorkflowStep.name == f"quality_round_{body['stage']}",
        )
    )
    execution = session.get(m.Execution, body["execution_id"])
    saved = work.result.get("executions", {}).get(str(body["stage"]), {}) if work else {}
    agent = session.get(m.Agent, body["agent_id"])
    if (
        report.org_id != project.org_id
        or report.client_id != project.client_id
        or report.project_id != project.id
        or body["plan_id"] != plan.id
        or body["plan_hash"] != plan.data["plan_hash"]
        or body["source_hash"] != plan.data["source_hash"]
        or digest(body) != report.data["body_hash"]
        or report.status != body["verdict"]
        or not artifact
        or artifact.org_id != project.org_id
        or artifact.project_id != project.id
        or artifact.sha256 != report.data["artifact_hash"]
        or artifact.sha256 != digest_bytes(artifact.content)
        or artifact.content != canonical(body)
        or artifact.agent_id != body["agent_id"]
        or not agent
        or agent.org_id != project.org_id
        or agent.role != ROLES[body["stage"] - 1]
        or agent.id == session.get(m.Task, plan.data["source"]["task_id"]).assigned_agent_id
        or not run
        or run.org_id != project.org_id
        or run.project_id != project.id
        or run.status != "succeeded"
        or run.workflow_id != body["workflow_id"]
        or run.agent_id != body["agent_id"]
        or run.model_id != body["model_id"]
        or run.response != body["assessment"]
        or run.step_name != f"quality_round_{body['stage']}"
        or not work
        or work.org_id != project.org_id
        or work.project_id != project.id
        or work.subject_id != plan.id
        or work.kind != "quality"
        or not workflow
        or workflow.org_id != project.org_id
        or workflow.status != "completed"
        or workflow.step != 3
        or workflow.mode != body["mode"]
        or not step
        or step.result != {"report_id": report.id, "body_hash": digest(body), "artifact_id": artifact.id}
        or not execution
        or execution.org_id != project.org_id
        or execution.task_id != plan.data["source"]["task_id"]
        or execution.agent_id != body["agent_id"]
        or execution.commit_hash != plan.data["source"]["commit"]
        or execution.status != "completed"
        or execution.exit_code != 0
        or saved.get("execution_id") != execution.id
        or saved.get("result_hash") != body["receipt_hash"]
        or digest(saved.get("result")) != body["receipt_hash"]
        or execution.command != saved.get("result", {}).get("command")
        or execution.environment != saved.get("result", {}).get("environment", "")[:200]
        or execution.logs
        != clean(
            str(saved.get("result", {}).get("build", {}).get("logs", ""))
            + "\n"
            + str(saved.get("result", {}).get("logs", ""))
        )[:500100]
        or test_result(saved["result"], body["stage"], plan.data["plan"])["verdict"] != "PASS"
        or body["verdict"] != "PASS"
        or body["assessment"]["verdict"] != "PASS"
        or body["assessment"]["findings"]
    ):
        raise PermissionError("QA report, tools, source, role, model or checkpoint provenance is invalid")
    model = session.get(m.ModelConfig, run.model_id)
    provider = session.get(m.Provider, model.provider_id) if model else None
    if not model or model.org_id != project.org_id or not provider or provider.org_id != project.org_id:
        raise PermissionError("QA model provenance is invalid")
    authors = list(
        session.scalars(
            select(m.ModelRun.model_id).where(
                m.ModelRun.task_id == execution.task_id,
                m.ModelRun.agent_id == session.get(m.Task, execution.task_id).assigned_agent_id,
                m.ModelRun.status == "succeeded",
            )
        )
    )
    policy = plan.data["plan"]["independence"]
    identity = model_key(session, run.model_id, project.org_id)
    identities = [list(key) for key in author_keys(session, authors, project.org_id)]
    if body.get("model_identity") != identity or body.get("author_identities") != identities:
        raise PermissionError("QA model or author identity changed after assessment")
    if body["mode"] == "live" and (provider.kind == "mock" or run.cost_basis == "mock_no_charge"):
        raise PermissionError("Fixture QA cannot authorize live release")
    if policy != "role" and (body["mode"] != "live" or identity in identities):
        raise PermissionError("Required model independence has not been verified")
    if policy == "require_provider" and identity[0] in {key[0] for key in identities}:
        raise PermissionError("Required provider independence has not been verified")
    return body


def digest_bytes(content):
    import hashlib

    return hashlib.sha256(content.encode()).hexdigest()


def readiness(session, project):
    blockers, pinned, trace = [], [], []
    plans = rows(session, project, "quality_plan")
    reports = rows(session, project, "quality_report")
    tasks = list(
        session.scalars(
            select(m.Task).where(
                m.Task.org_id == project.org_id, m.Task.project_id == project.id, m.Task.kind == "coding"
            )
        )
    )
    if not tasks:
        blockers.append("No engineering candidate has been independently verified")
    try:
        project_authority(session, project)
        if project.status != "active" or session.get(m.Organization, project.org_id).paused:
            raise PermissionError("Project or company is paused")
    except PermissionError as exc:
        blockers.append(str(exc))
    for task in tasks:
        if superseded(session, project, task.id):
            continue
        applicable = sorted(
            [p for p in plans if p.data["source"]["task_id"] == task.id and p.status == "approved"],
            key=lambda p: p.version,
        )
        plan = applicable[-1] if applicable else None
        if not plan:
            blockers.append(f"Task {task.id}: exact owner QA plan approval is missing")
            proposal = session.get(m.Proposal, project.proposal_id)
            for index, text in enumerate(proposal.content.get("acceptance_criteria", [])):
                trace.append(
                    {
                        "task_id": task.id,
                        "requirement_index": index,
                        "text": text,
                        "status": "MISSING_VERIFICATION",
                        "cases": [],
                        "reports": [],
                    }
                )
            continue
        try:
            authority(session, plan)
            stage_rows = []
            for stage in CHECKS:
                matches = [
                    r
                    for r in reports
                    if r.data["body"]["plan_id"] == plan.id and r.data["body"]["stage"] == stage
                ]
                if not matches:
                    raise PermissionError(f"Round {stage} evidence is missing")
                # A fresh failed run invalidates earlier passing evidence.
                report = max(matches, key=lambda r: r.data["body"].get("position", 0))
                body = validate_report(session, project, plan, report)
                stage_rows.append(
                    {
                        "stage": stage,
                        "report_id": report.id,
                        "hash": report.data["body_hash"],
                        "artifact_hash": report.data["artifact_hash"],
                        "classification": body["classification"],
                    }
                )
            pinned.append(
                {
                    "task_id": task.id,
                    "plan_id": plan.id,
                    "source": plan.data["source"],
                    "plan_hash": plan.data["plan_hash"],
                    "reports": stage_rows,
                    "exceptions": plan.data["plan"]["exceptions"],
                }
            )
            for index, text in enumerate(plan.data["source"]["criteria"]):
                trace.append(
                    {
                        "requirement_id": plan.data["source"]["requirement_id"],
                        "index": index,
                        "text": text,
                        "design": plan.data["source"]["design"],
                        "task_id": task.id,
                        "commit": plan.data["source"]["commit"],
                        "cases": [c["id"] for c in plan.data["plan"]["cases"] if index in c["requirements"]],
                        "reports": stage_rows,
                        "status": "TESTED",
                        "release_artifact": "awaiting_package",
                    }
                )
        except (PermissionError, KeyError, ValueError, TypeError) as exc:
            blockers.append(f"Task {task.id}: {str(exc) or 'Invalid QA evidence'}")
            for index, text in enumerate(plan.data["source"].get("criteria", [])):
                applicable_reports = [r for r in reports if r.data["body"].get("plan_id") == plan.id]
                statuses = {r.status for r in applicable_reports}
                trace.append(
                    {
                        "task_id": task.id,
                        "requirement_id": plan.data["source"]["requirement_id"],
                        "index": index,
                        "text": text,
                        "commit": plan.data["source"]["commit"],
                        "design": plan.data["source"]["design"],
                        "cases": [c["id"] for c in plan.data["plan"]["cases"] if index in c["requirements"]],
                        "reports": [{"id": r.id, "verdict": r.status} for r in applicable_reports],
                        "exceptions": plan.data["plan"]["exceptions"],
                        "status": "FAILED"
                        if "FAIL" in statuses
                        else "BLOCKED"
                        if "BLOCKED" in statuses
                        else "MISSING_VERIFICATION",
                    }
                )
    for record in rows(session, project, "quality_defect"):
        if record.status != "closed" or record.data.get("verification") != "verified":
            blockers.append(f"{record.data['severity']} defect {record.id} is {record.status}")
        else:
            try:
                if repair_verification(session, project, record) != record.data.get("verified_evidence"):
                    raise PermissionError("Verified defect evidence changed")
            except (PermissionError, KeyError, ValueError, TypeError) as exc:
                blockers.append(f"Defect {record.id}: {exc}")
    manifest = {
        "policy_version": 1,
        "project_id": project.id,
        "candidates": pinned,
        "traceability": trace,
        "owner_release_approval": "still_required",
        "deployment": "not_verified",
        "production_ready": False,
    }
    return {
        "ready": not blockers,
        "blockers": blockers,
        "manifest": manifest,
        "manifest_hash": digest(manifest),
    }


def repair_baseline(session, task, project):
    """Use the exact approved parent worktree without moving the owner's repository HEAD."""
    record = session.get(m.BusinessRecord, task.payload.get("quality_defect_id"))
    parent = session.get(m.Task, task.payload.get("supersedes_task_id"))
    if (
        not record
        or record.kind != "quality_defect"
        or record.org_id != project.org_id
        or record.project_id != project.id
        or task.id not in record.data.get("repair_tasks", [])
        or not parent
        or parent.org_id != task.org_id
        or parent.project_id != project.id
        or parent.payload.get("repository_id") != task.payload.get("repository_id")
        or parent.payload.get("mode") != task.payload.get("mode")
    ):
        raise PermissionError("Repair requires an authorized same-project candidate lineage")
    lineage = [record.data["task_id"], *record.data["repair_tasks"]]
    if lineage.index(task.id) == 0 or lineage[lineage.index(task.id) - 1] != parent.id:
        raise PermissionError("Repair parent differs from the recorded candidate lineage")
    workspace, manifest = source(session, parent)
    if task.payload.get("baseline_commit") != manifest["commit"]:
        raise PermissionError("Repair baseline differs from the exact approved parent candidate")
    return workspace


def repair_verification(session, project, record):
    if not record.data["repair_tasks"]:
        raise PermissionError("A new approved repair candidate and fresh independent QA are required")
    task = session.get(m.Task, record.data["repair_tasks"][-1])
    if (
        not task
        or task.org_id != project.org_id
        or task.project_id != project.id
        or task.payload.get("quality_defect_id") != record.id
    ):
        raise PermissionError("Repair lineage is invalid")
    plans = [
        p
        for p in rows(session, project, "quality_plan")
        if p.status == "approved" and p.data["source"]["task_id"] == task.id
    ]
    if not plans:
        raise PermissionError("Repair candidate needs an exact approved QA plan")
    plan = max(plans, key=lambda p: p.version)
    authority(session, plan)
    original = session.get(m.BusinessRecord, record.data["plan_id"])
    previous = session.get(m.Task, record.data["task_id"])
    if (
        original.org_id != project.org_id
        or original.project_id != project.id
        or original.data["source"]["task_id"] != previous.id
    ):
        raise PermissionError("Original defect and source scope differ")
    for task_id in record.data["repair_tasks"]:
        child = session.get(m.Task, task_id)
        if (
            not child
            or child.org_id != project.org_id
            or child.project_id != project.id
            or child.payload.get("quality_defect_id") != record.id
            or child.payload.get("supersedes_task_id") != previous.id
            or child.payload.get("baseline_commit")
            != previous.evidence.get("pull_request", {}).get("head_commit")
        ):
            raise PermissionError("Every repair must preserve its exact approved candidate lineage")
        previous = child
    if plan.data["source"]["commit"] == record.data["source_commit"] or any(
        plan.data["plan"][key] != original.data["plan"][key]
        for key in ("files", "cases", "exceptions", "independence", "repair_limit")
    ):
        raise PermissionError("Repair needs a changed source and unchanged verification policy")
    verified = []
    reports = rows(session, project, "quality_report")
    for stage in CHECKS:
        matches = [
            r for r in reports if r.data["body"]["plan_id"] == plan.id and r.data["body"]["stage"] == stage
        ]
        if not matches:
            raise PermissionError("All three fresh repair rounds are required")
        report = max(matches, key=lambda r: r.data["body"].get("position", 0))
        body = validate_report(session, project, plan, report)
        if stage == record.data["stage"] and not any(
            c["id"] == record.data["case_id"] and c["status"] == "PASS" for c in body["tools"]["cases"]
        ):
            raise PermissionError("The original failing test must independently pass")
        verified.append({"id": report.id, "hash": report.data["body_hash"]})
    return {
        "task_id": task.id,
        "commit": plan.data["source"]["commit"],
        "plan_id": plan.id,
        "reports": verified,
    }


def superseded(session, project, task_id):
    for record in rows(session, project, "quality_defect"):
        if record.status != "closed" or record.data.get("verification") != "verified":
            continue
        try:
            verified = repair_verification(session, project, record)
            if verified != record.data.get("verified_evidence"):
                continue
            lineage = [record.data["task_id"], *record.data["repair_tasks"][:-1]]
            if task_id in lineage:
                return verified
        except (PermissionError, KeyError, ValueError, TypeError):
            continue
    return None


def required(session, project):
    from .project_setup import for_requirement

    proposal = session.get(m.Proposal, project.proposal_id)
    setup = for_requirement(session, proposal.requirement_id, project.org_id)
    return bool(
        rows(session, project, "quality_plan")
        or (setup and setup.data.get("form", {}).get("review_before_planning"))
    )


def freeze_readiness(session, project, user):
    result = readiness(session, project)
    artifact = save_artifact(
        session,
        project.org_id,
        "Immutable QA readiness evaluation",
        canonical(result),
        "quality_readiness",
        project_id=project.id,
    )
    record = m.BusinessRecord(
        id=uid(),
        org_id=project.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="quality_readiness",
        title="Quality readiness — " + ("passed" if result["ready"] else "blocked"),
        status="ready" if result["ready"] else "blocked",
        data={
            "evaluation": result,
            "evaluation_hash": digest(result),
            "artifact_id": artifact.id,
            "artifact_hash": artifact.sha256,
        },
    )
    session.add(record)
    audit(
        session,
        project.org_id,
        user.id,
        "quality.readiness_frozen",
        record.id,
        {"ready": result["ready"], "hash": digest(result)},
        project_id=project.id,
    )
    return record


class RepairEscalation(PermissionError):
    """A durable owner notification, never permission for another execution."""


def repair(session, record, user, request_id, objective):
    lock_org(session, user.org_id)
    session.refresh(record)
    project = session.get(m.Project, record.project_id)
    project_authority(session, project)
    fingerprint = digest({"defect": record.id, "objective": objective})
    existing = session.get(m.Task, request_id)
    if existing:
        if existing.org_id != user.org_id or existing.payload.get("quality_request_hash") != fingerprint:
            raise PermissionError("Repair request ID already used for another scope")
        return existing
    plan = session.get(m.BusinessRecord, record.data["plan_id"])
    attempts = record.data["repair_tasks"]
    if record.status == "closed":
        raise PermissionError("Closed defects require explicit reopening")
    if len(attempts) >= plan.data["plan"]["repair_limit"]:
        if record.status != "needs_owner":
            record.status = "needs_owner"
            record.version += 1
            record.data = {
                **record.data,
                "history": [
                    *record.data["history"],
                    {"action": "repair_limit_escalated", "actor": user.id, "at": now()},
                ],
            }
            session.add(
                m.Notification(
                    org_id=user.org_id,
                    severity="error",
                    title="QA repair limit reached; owner investigation required",
                    subject_id=record.id,
                )
            )
            audit(
                session,
                user.org_id,
                user.id,
                "quality.repair_limit_escalated",
                record.id,
                {"attempts": len(attempts), "limit": plan.data["plan"]["repair_limit"]},
                project_id=project.id,
            )
        raise RepairEscalation("Bounded repair limit reached; owner escalation saved, execution denied")
    if record.status not in {"open", "reopened", "repairing"}:
        raise PermissionError("Defect is not eligible for repair")
    source_task = session.get(m.Task, attempts[-1] if attempts else record.data["task_id"])
    _, manifest = source(session, source_task)
    payload = {
        key: value
        for key, value in source_task.payload.items()
        if key in {"repository_id", "test_suite", "mode", "review_policy", "review_count", "repair_limit"}
    }
    payload.update(
        {
            "baseline_commit": manifest["commit"],
            "objective": objective,
            "quality_defect_id": record.id,
            "quality_feedback": {
                key: record.data[key]
                for key in (
                    "description",
                    "reproduction",
                    "expected",
                    "actual",
                    "case_id",
                    "source_commit",
                    "report_id",
                )
            },
            "quality_request_hash": fingerprint,
            "quality_repair_round": len(attempts) + 1,
            "supersedes_task_id": source_task.id,
        }
    )
    task = m.Task(
        id=request_id,
        org_id=user.org_id,
        project_id=project.id,
        assigned_agent_id=record.data.get("assigned_developer") or source_task.assigned_agent_id,
        kind="coding",
        status="awaiting_approval",
        objective=clean(objective),
        acceptance=list(source_task.acceptance),
        budget_micro=source_task.budget_micro,
        payload=payload,
    )
    session.add(task)
    session.add(m.Budget(org_id=user.org_id, scope=f"task:{task.id}", limit_micro=task.budget_micro))
    record.status = "repairing"
    record.version += 1
    record.data = {
        **record.data,
        "repair_tasks": [*attempts, task.id],
        "verification": "unverified",
        "history": [
            *record.data["history"],
            {"action": "repair_requested", "actor": user.id, "task_id": task.id, "at": now()},
        ],
    }
    audit(
        session,
        user.org_id,
        user.id,
        "quality.repair_scope_requested",
        record.id,
        {"task_id": task.id, "attempt": len(attempts) + 1},
        project_id=project.id,
    )
    return task
