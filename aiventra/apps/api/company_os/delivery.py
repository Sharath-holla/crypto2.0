"""Persisted final-review preparation; no release, deployment or client acceptance is implied."""

import hashlib
import json

from pydantic import Field
from sqlalchemy import select

from . import models as m
from .artifacts import save_artifact
from .db import now
from .gateway import execute
from .schemas import Strict
from .security import audit, check_agent, digest
from .staffing import lock_org
from .workflows import checkpoint, project_authority

ROLES = ["CTO", "QA Director", "Security Architect", "Project Manager", "CFO"]


class DeliveryReviewResult(Strict):
    approved: bool
    summary: str = Field(min_length=20, max_length=2000)
    checked_criteria: list[int] = Field(min_length=1, max_length=20)
    findings: list[str] = Field(max_length=12)


def readiness(session, project, mode):
    """Read actual source state; never turn a completed flag into certification."""
    blockers, task_evidence, sources, author_models = [], [], [], set()
    content_blocks = {}
    try:
        project_authority(session, project)
    except PermissionError as exc:
        blockers.append(str(exc))
    if project.status != "active" or session.get(m.Organization, project.org_id).paused:
        blockers.append("Project or company is paused")
    proposal = session.get(m.Proposal, project.proposal_id)
    plan = session.scalar(
        select(m.StaffingPlan).where(
            m.StaffingPlan.org_id == project.org_id,
            m.StaffingPlan.project_id == project.id,
        )
    )
    staffing_approval = (
        session.scalar(
            select(m.Approval).where(
                m.Approval.org_id == project.org_id,
                m.Approval.category == "staffing",
                m.Approval.subject_id == plan.id,
                m.Approval.version == plan.version,
            )
        )
        if plan
        else None
    )
    if (
        not plan
        or plan.status != "active"
        or not staffing_approval
        or staffing_approval.expires_at <= now()
        or staffing_approval.subject_hash != digest(plan.content)
        or plan.content_hash != digest(plan.content)
    ):
        blockers.append("Current exact workforce approval and active allocation are required")
    tasks = list(
        session.scalars(
            select(m.Task)
            .where(m.Task.org_id == project.org_id, m.Task.project_id == project.id)
            .order_by(m.Task.id)
        )
    )
    if not tasks or len(tasks) > 40:
        blockers.append("Final review requires 1 to 40 persisted project tasks")
    for task in tasks:
        label = f"Task {task.id}"
        if task.status != "completed":
            blockers.append(f"{label} is {task.status}")
        runs = list(
            session.scalars(
                select(m.ModelRun).where(
                    m.ModelRun.org_id == project.org_id,
                    m.ModelRun.task_id == task.id,
                    m.ModelRun.agent_id == task.assigned_agent_id,
                    m.ModelRun.status == "succeeded",
                )
            )
        )
        if not runs:
            blockers.append(f"{label} has no saved successful author run")
        for run in runs:
            workflow = session.get(m.Workflow, run.workflow_id)
            model = session.get(m.ModelConfig, run.model_id)
            provider = session.get(m.Provider, model.provider_id) if model else None
            if (
                not model
                or model.org_id != project.org_id
                or not provider
                or provider.org_id != project.org_id
            ):
                blockers.append(f"{label} has invalid author model provenance")
            if (
                not workflow
                or workflow.org_id != project.org_id
                or workflow.status != "completed"
                or workflow.task_id != task.id
            ):
                blockers.append(f"{label} has unfinished author execution")
            if mode == "live" and (
                not provider or provider.kind == "mock" or not workflow or workflow.mode != "live"
            ):
                blockers.append(f"{label} contains deterministic fixture evidence")
            if task.kind == "coding":
                author_models.add(run.model_id)
        if task.kind == "document":
            artifact_id = task.evidence.get("artifact_id")
            artifact = session.get(m.Artifact, artifact_id) if artifact_id else None
            if (
                not artifact
                or artifact.org_id != project.org_id
                or artifact.project_id != project.id
                or artifact.task_id != task.id
                or artifact.agent_id != task.assigned_agent_id
                or artifact.sha256 != task.evidence.get("sha256")
                or hashlib.sha256(artifact.content.encode()).hexdigest() != artifact.sha256
            ):
                blockers.append(f"{label} has missing or changed document evidence")
            else:
                checkpoints = list(
                    session.scalars(
                        select(m.WorkflowStep).where(
                            m.WorkflowStep.workflow_id.in_([run.workflow_id for run in runs]),
                            m.WorkflowStep.name == "document",
                        )
                    )
                )
                bound = any(row.result == task.evidence for row in checkpoints)
                if not bound:
                    blockers.append(f"{label} document is not bound to its author checkpoint")
                paragraphs = []
                for paragraph in artifact.content.split("\n\n"):
                    block_hash = hashlib.sha256(paragraph.encode()).hexdigest()
                    content_blocks[block_hash] = paragraph
                    paragraphs.append(block_hash)
                sources.append({"task_id": task.id, "artifact_id": artifact.id, "paragraphs": paragraphs})
        elif task.kind == "coding":
            from .publication import candidate

            try:
                # Mock review is never live certification. A test-only package still
                # requires exact scope, unchanged Git/QA evidence and real Docker.
                _, _, _, _, diff = candidate(session, task, nonproduction=mode == "mock")
                execution = session.get(m.Execution, task.evidence["execution_id"])
                sources.append(
                    {
                        "task_id": task.id,
                        "diff": diff,
                        "qa": {"execution_id": execution.id, "logs": execution.logs},
                        "review": task.evidence["reviews"],
                        "classification": "fixture_nonproduction" if mode == "mock" else "live_reviewed",
                        "review_mode": mode,
                    }
                )
            except (ValueError, PermissionError) as exc:
                reason = (
                    "Fixture review cannot certify engineering execution without verified nonproduction evidence: "
                    if mode == "mock"
                    else ""
                )
                blockers.append(f"{label}: {reason}{exc}")
        else:
            blockers.append(f"{label} has unsupported task kind")
        task_evidence.append(
            {
                "id": task.id,
                "agent_id": task.assigned_agent_id,
                "kind": task.kind,
                "objective": task.objective,
                "acceptance": task.acceptance,
                "version": task.version,
                "scope_hash": digest(task.payload),
                "evidence_hash": digest(task.evidence),
                "run_ids": sorted(r.id for r in runs),
            }
        )
    if plan:
        expected = {row["key"] for row in plan.content["tasks"]}
        actual = {
            task.payload.get("plan_key") for task in tasks if task.payload.get("staffing_plan_id") == plan.id
        }
        if actual != expected or not set(plan.content["foundation_task_ids"]).issubset(
            {task.id for task in tasks}
        ):
            blockers.append("Approved workforce tasks or foundation references are missing")
    budget = session.scalar(
        select(m.Budget).where(m.Budget.org_id == project.org_id, m.Budget.scope == f"project:{project.id}")
    )
    if not budget or budget.spent_micro + budget.reserved_micro > budget.limit_micro:
        blockers.append("Project budget evidence is missing or exceeds its cap")
    criteria = proposal.content.get("acceptance_criteria", [])
    if not criteria or len(criteria) > 20:
        blockers.append("One to twenty approved acceptance criteria are required")
    if len(json.dumps([sources, content_blocks], ensure_ascii=False)) > 18000:
        blockers.append("Evidence exceeds the bounded review context; partition the project before review")
    manifest = {
        "project_id": project.id,
        "client_id": project.client_id,
        "project_version": project.version,
        "proposal_version": proposal.version,
        "proposal_hash": digest(proposal.content),
        "staffing_id": plan.id if plan else None,
        "staffing_version": plan.version if plan else None,
        "staffing_hash": plan.content_hash if plan else None,
        "mode": mode,
        "tasks": task_evidence,
        "sources": sources,
        "content_blocks": content_blocks,
        "acceptance": criteria,
        "author_model_ids": sorted(author_models),
        "budget": {"limit_micro": budget.limit_micro, "spent_micro": budget.spent_micro} if budget else {},
        "deployment_status": "not_verified",
        "delivery_status": "not_released",
    }
    from . import quality

    if quality.required(session, project):
        quality_evidence = quality.readiness(session, project)
        blockers.extend(quality_evidence["blockers"])
        manifest["quality"] = {
            "manifest_hash": quality_evidence["manifest_hash"],
            "candidates": [
                {"task_id": c["task_id"], "plan_hash": c["plan_hash"], "reports": c["reports"]}
                for c in quality_evidence["manifest"]["candidates"]
            ],
        }
    if len(json.dumps(manifest, ensure_ascii=False)) > 24000:
        blockers.append("Project manifest exceeds the bounded review context; partition before review")
    return {
        "ready": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "manifest": manifest,
        "source_hash": digest(manifest),
    }


def current_source(session, project, mode, expected_hash):
    evidence = readiness(session, project, mode)
    if not evidence["ready"] or evidence["source_hash"] != expected_hash:
        raise PermissionError(
            "Final-review source changed or is incomplete; prepare against current evidence"
        )
    return evidence["manifest"]


async def review_step(session, workflow, token, work, project):
    record = session.get(m.BusinessRecord, work.subject_id)
    if (
        not record
        or record.org_id != work.org_id
        or record.project_id != project.id
        or record.kind != "delivery_review"
        or record.status != "reviewing"
    ):
        raise PermissionError("Final-review scope denied")
    manifest = current_source(session, project, workflow.mode, work.input["source_hash"])
    index = workflow.step
    if index not in range(len(ROLES)):
        raise PermissionError("Invalid final-review checkpoint")
    agent = session.get(m.Agent, work.participants[index])
    if agent.role != ROLES[index] or agent.id in {
        task["agent_id"] for task in manifest["tasks"] if task["kind"] == "coding"
    }:
        raise PermissionError("Final reviewer must be independent of coding authors")
    check_agent(session, agent, "write_artifact", project)
    result = await execute(
        session,
        workflow,
        agent,
        f"delivery_review_{index}",
        DeliveryReviewResult,
        {
            "objective": "Review approved requirements against saved project evidence; identify missing evidence and do not certify deployment or client acceptance.",
            "role": agent.role,
            "acceptance": manifest["acceptance"],
            "source_manifest": manifest,
            "previous_reviews": [
                {"role": row["role"], "approved": row["approved"], "findings": row["findings"]}
                for row in record.data.get("reviews", [])
            ],
            "instruction": "Document sources reference content_blocks by paragraph hash in order; join paragraphs with two newlines to recover the full saved document. Nothing is omitted. checked_criteria must list each zero-based acceptance criterion exactly once. Findings block final approval. Fixture output never certifies delivery.",
        },
        quality=85,
        project=project,
        review_against=manifest["author_model_ids"] if workflow.mode == "live" else [],
        review_policy="require_model",
    )
    if sorted(result.checked_criteria) != list(range(len(manifest["acceptance"]))):
        raise PermissionError("Final reviewer must assess every approved criterion exactly once")
    lock_org(session, work.org_id)
    # The gateway commits its run with expire_on_commit=False. Discard cached
    # source/agent state so another connection's edits during inference are fenced.
    session.expire_all()
    current_source(session, project, workflow.mode, work.input["source_hash"])
    check_agent(session, agent, "write_artifact", project)
    if record.status != "reviewing":
        raise PermissionError("Final-review state changed")
    approved = result.approved and not result.findings
    terminal = not approved or index == len(ROLES) - 1
    checkpoint(session, workflow, token, f"delivery_review_{index}", {}, complete=terminal)
    artifact = save_artifact(
        session,
        work.org_id,
        f"{agent.role} final review",
        json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
        "delivery_review",
        project_id=project.id,
        agent_id=agent.id,
    )
    run = session.scalar(
        select(m.ModelRun).where(
            m.ModelRun.workflow_id == workflow.id,
            m.ModelRun.step_name == f"delivery_review_{index}",
            m.ModelRun.status == "succeeded",
        )
    )
    review = {
        "role": agent.role,
        "agent_id": agent.id,
        "artifact_id": artifact.id,
        "sha256": artifact.sha256,
        "run_id": run.id,
        "mode": workflow.mode,
        **result.model_dump(),
    }
    record.data = {**record.data, "reviews": [*record.data.get("reviews", []), review]}
    record.version += 1
    saved = session.scalar(
        select(m.WorkflowStep).where(
            m.WorkflowStep.workflow_id == workflow.id, m.WorkflowStep.name == f"delivery_review_{index}"
        )
    )
    saved.result = {
        "artifact_id": artifact.id,
        "sha256": artifact.sha256,
        "source_hash": work.input["source_hash"],
    }
    if index:
        for message in session.scalars(
            select(m.Message).where(
                m.Message.org_id == work.org_id,
                m.Message.correlation_id == work.id,
                m.Message.recipient == agent.id,
            )
        ):
            message.status, message.acknowledged_at = "acknowledged", now()
    if terminal:
        record.status = (
            "changes_required"
            if not approved
            else "fixture_reviewed"
            if workflow.mode == "mock"
            else "awaiting_delivery_approval"
        )
        session.add(
            m.Notification(
                org_id=work.org_id,
                severity="info" if approved else "warning",
                title="Final review passed"
                if approved and workflow.mode == "live"
                else "Deterministic final-review fixture completed"
                if approved
                else "Final review requires changes",
                subject_id=record.id,
            )
        )
    else:
        session.add(
            m.Message(
                org_id=work.org_id,
                project_id=project.id,
                sender=agent.id,
                recipient=work.participants[index + 1],
                type="ReviewRequested",
                correlation_id=work.id,
                content={
                    "artifact_id": artifact.id,
                    "sha256": artifact.sha256,
                    "source_hash": work.input["source_hash"],
                    "mode": workflow.mode,
                },
                authorization=f"owner-final-review:{work.id}",
            )
        )
    work.result = {
        "review_id": record.id,
        "source_hash": work.input["source_hash"],
        "status": record.status,
        "review_count": len(record.data["reviews"]),
        "delivery_released": False,
        "client_accepted": False,
    }
    audit(
        session,
        work.org_id,
        agent.id,
        "delivery.review_checkpoint",
        record.id,
        {"role": agent.role, "approved": approved, "mode": workflow.mode},
        project_id=project.id,
        authorization=f"owner-final-review:{work.id}",
    )
