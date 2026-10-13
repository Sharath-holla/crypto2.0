"""Exact-approved deterministic DevOps orchestration on existing durable workflows."""

import json
import re
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator
from sqlalchemy import select

from . import deployment_adapter as adapter
from . import models as m
from . import packages, quality
from .artifacts import save_artifact
from .db import now, uid
from .organization import agent_for
from .schemas import Strict
from .security import audit, check_agent, clean, digest
from .staffing import lock_org
from .workflows import checkpoint, project_authority


class TargetInput(Strict):
    request_id: UUID
    name: str = Field(min_length=3, max_length=120)
    environment: Literal["staging", "production"]
    adapter: Literal["simulation"] = "simulation"


class PlanInput(Strict):
    request_id: UUID
    package_id: str
    target_id: str
    strategy: Literal["replace_revision"] = "replace_revision"
    configuration_refs: dict[str, str] = Field(default_factory=dict, max_length=20)
    migration: Literal["none", "manual_review_required"] = "none"
    health_timeout_seconds: int = Field(default=30, ge=1, le=120)
    health_observations: int = Field(default=2, ge=1, le=3)
    risk_summary: str = Field(min_length=10, max_length=1500)
    scenario: Literal["healthy", "health_failure", "health_timeout", "partial_failure", "wrong_revision"] = (
        "healthy"
    )
    rollback_receipt_id: str | None = None
    incident_id: str | None = None

    @model_validator(mode="after")
    def reference_only(self):
        if any(
            not re.fullmatch(r"[A-Z][A-Z0-9_]{2,80}", key)
            or not re.fullmatch(r"REF:[A-Z][A-Z0-9_]{2,80}", value)
            for key, value in self.configuration_refs.items()
        ):
            raise ValueError("Configuration contains reference names only; never paste secret values")
        if bool(self.rollback_receipt_id) != bool(self.incident_id):
            raise ValueError("Rollback requires a known prior receipt and a saved incident")
        return self


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


def scope(session, project):
    if not project or project.status != "active" or session.get(m.Organization, project.org_id).paused:
        raise PermissionError("Deployment is blocked while the project or company is paused or closed")
    project_authority(session, project)


def replay(session, request_id, org_id, kind, fingerprint):
    row = session.get(m.BusinessRecord, str(request_id))
    if row:
        if row.org_id != org_id or row.kind != kind or row.data.get("request_hash") != fingerprint:
            raise PermissionError("Request ID is already bound to another operation")
        return row


def create_target(session, project, user, data):
    lock_org(session, user.org_id)
    session.refresh(project)
    scope(session, project)
    fingerprint = digest({"project": project.id, **data.model_dump(mode="json")})
    previous = replay(session, data.request_id, user.org_id, "devops_target", fingerprint)
    if previous:
        return previous
    config = {
        "name": data.name,
        "environment": data.environment,
        "adapter": "simulation",
        "project_id": project.id,
        "client_id": project.client_id,
        "classification": adapter.CLASSIFICATION,
        "public_network": False,
        "cost_micro": 0,
        "resources": {"external_resources": 0},
    }
    if clean(config) != config:
        raise PermissionError("Do not put credentials in target names")
    row = m.BusinessRecord(
        id=str(data.request_id),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="devops_target",
        title=data.name,
        status="enabled",
        data={"config": config, "config_hash": digest(config), "request_hash": fingerprint},
    )
    session.add(row)
    audit(
        session,
        user.org_id,
        user.id,
        "devops.target_created",
        row.id,
        {"environment": data.environment, "classification": adapter.CLASSIFICATION},
        project_id=project.id,
    )
    return row


def target_for(session, project, target_id):
    row = session.get(m.BusinessRecord, target_id)
    if (
        not row
        or row.kind != "devops_target"
        or row.org_id != project.org_id
        or row.project_id != project.id
        or row.client_id != project.client_id
        or row.status != "enabled"
        or row.data["config_hash"] != digest(row.data["config"])
        or row.data["config"]["project_id"] != project.id
        or row.data["config"]["client_id"] != project.client_id
        or row.data["config"]["adapter"] != "simulation"
    ):
        raise PermissionError("Select an enabled, unchanged target in this project")
    return row


def package_source(session, project, package_id, current=True):
    package = session.get(m.DeliveryPackage, package_id)
    if (
        not package
        or package.org_id != project.org_id
        or package.project_id != project.id
        or package.client_id != project.client_id
        or package.status not in {"package_ready", "awaiting_release_approval"}
    ):
        raise PermissionError("Deployment needs a frozen, ready package in this project")
    packages.integrity(session, package, current=current)
    if package.manifest.get("blockers"):
        raise PermissionError("Resolve package release blockers first")
    if current and session.scalar(
        select(m.DeliveryPackage.id).where(
            m.DeliveryPackage.project_id == project.id, m.DeliveryPackage.version > package.version
        )
    ):
        raise PermissionError("A newer package exists; prepare a current deployment plan")
    refs = [r for r in package.manifest["files"] if r["purpose"] == "quality_readiness"]
    qa = quality.readiness(session, project) if current and quality.required(session, project) else None
    if qa and (
        not qa["ready"]
        or len(refs) != 1
        or packages.read_blob(package, refs[0]).decode() != packages.canonical(qa)
    ):
        raise PermissionError("Current three-stage QA is required before deployment planning")
    frozen_qa = json.loads(packages.read_blob(package, refs[0])) if len(refs) == 1 else None
    if frozen_qa and (
        not frozen_qa["ready"]
        or frozen_qa["manifest_hash"] != digest(frozen_qa["manifest"])
        or frozen_qa["manifest"]["project_id"] != project.id
    ):
        raise PermissionError("Frozen quality evidence is not eligible for this deployment")
    return {
        "package_id": package.id,
        "package_version": package.version,
        "artifact_hash": package.manifest_hash,
        "source_hash": package.source_hash,
        "classification": package.classification,
        "files": [{"id": r["id"], "sha256": r["sha256"]} for r in package.manifest["files"]],
        "quality_hash": frozen_qa["manifest_hash"] if frozen_qa else None,
        "candidates": frozen_qa["manifest"]["candidates"] if frozen_qa else [],
        "security_review": [
            r for r in package.manifest.get("reviews", []) if r.get("role") == "Security Architect"
        ],
    }


def validate_receipt(session, project, receipt):
    if (
        not receipt
        or receipt.org_id != project.org_id
        or receipt.project_id != project.id
        or receipt.client_id != project.client_id
        or receipt.kind != "devops_receipt"
        or digest(receipt.data["body"]) != receipt.data["body_hash"]
    ):
        raise PermissionError("Deployment receipt integrity or scope failed")
    artifact = session.get(m.Artifact, receipt.data["artifact_id"])
    if (
        not artifact
        or artifact.org_id != project.org_id
        or artifact.project_id != project.id
        or artifact.content != packages.canonical(receipt.data["body"])
        or artifact.sha256 != digest_bytes(artifact.content)
    ):
        raise PermissionError("Deployment receipt artifact changed")
    body = receipt.data["body"]
    work = session.get(m.AgentWork, body["work_id"])
    workflow = session.get(m.Workflow, work.workflow_id) if work else None
    job = adapter.read(session, body["job_id"], project.org_id)
    plan = session.get(m.BusinessRecord, body["plan_id"])
    final = (
        session.scalar(
            select(m.WorkflowStep).where(
                m.WorkflowStep.workflow_id == workflow.id, m.WorkflowStep.name == "deployment_final"
            )
        )
        if workflow
        else None
    )
    if (
        not work
        or work.kind != "deployment"
        or work.org_id != project.org_id
        or work.project_id != project.id
        or work.result.get("job_id") != job.id
        or work.input.get("manifest_hash") != body["manifest_hash"]
        or work.result.get("request_hash") != job.data["request_hash"]
        or job.project_id != project.id
        or job.client_id != project.client_id
        or job.data["classification"] != adapter.CLASSIFICATION
        or not workflow
        or workflow.status != ("cancelled" if body["status"] == "deployment_cancelled" else "completed")
        or not plan
        or work.subject_id != plan.id
        or plan.org_id != project.org_id
        or plan.project_id != project.id
        or digest(plan.data["manifest"]) != plan.data["manifest_hash"]
        or body["adapter_hash"] != digest(job.data)
        or body["manifest_hash"] != plan.data["manifest_hash"]
        or body["approval_id"] != plan.data["approval_id"]
        or job.data["request"]["manifest_hash"] != body["manifest_hash"]
        or job.data["request"]["artifact_hash"] != body["artifact_hash"]
        or job.data["request"]["target_id"] != body["target_id"]
        or body["status"] != job.status
        or body["classification"] != adapter.CLASSIFICATION
        or body["live_verified"] is not False
        or body["target_id"] != plan.data["manifest"]["target_id"]
        or body["artifact_hash"] != plan.data["manifest"]["source"]["artifact_hash"]
        or body["health"] != job.data["health"]
        or body["events"] != job.data["events"]
        or body["revision"] != job.data["request"]["revision"]
        or not final
        or final.result != {"receipt_id": receipt.id, "body_hash": receipt.data["body_hash"]}
    ):
        raise PermissionError("Deployment receipt is not bound to its saved workflow and adapter")
    if body["status"] == "deployment_completed" and (
        not body["health"]
        or any(
            not h["healthy"]
            or h["expected_revision"] != body["revision"]
            or h["observed_revision"] != body["revision"]
            or h["artifact_hash"] != body["artifact_hash"]
            for h in body["health"]
        )
    ):
        raise PermissionError("Intended revision and fresh health observations are required")
    return body


def digest_bytes(value):
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def prepare(session, project, user, data):
    lock_org(session, user.org_id)
    session.refresh(project)
    scope(session, project)
    fingerprint = digest({"project": project.id, **data.model_dump(mode="json")})
    previous = replay(session, data.request_id, user.org_id, "devops_plan", fingerprint)
    if previous:
        return previous
    target = target_for(session, project, data.target_id)
    rollback = None
    if data.rollback_receipt_id:
        prior = session.get(m.BusinessRecord, data.rollback_receipt_id)
        prior_body = validate_receipt(session, project, prior)
        incident = session.get(m.BusinessRecord, data.incident_id)
        if (
            prior.status != "deployment_completed"
            or prior_body["target_id"] != target.id
            or not incident
            or incident.kind != "devops_incident"
            or incident.org_id != project.org_id
            or incident.project_id != project.id
            or incident.client_id != project.client_id
            or incident.status != "open"
            or incident.data["target_id"] != target.id
            or prior_body["package_id"] != data.package_id
            or incident.data.get("attempts", 0) >= 3
        ):
            raise PermissionError(
                "Rollback needs a healthy known artifact, open matching incident and remaining attempts"
            )
        if data.migration != "none":
            raise PermissionError("Destructive database migration reversal is never automatic")
        rollback = {
            "receipt_id": prior.id,
            "receipt_hash": prior.data["body_hash"],
            "revision": prior_body["revision"],
            "incident_id": incident.id,
        }
    source = package_source(session, project, data.package_id, current=not bool(rollback))
    environment = target.data["config"]["environment"]
    category = "devops_" + environment + ("_rollback" if rollback else "")
    manifest = {
        "schema": 1,
        "plan_id": str(data.request_id),
        "project_id": project.id,
        "client_id": project.client_id,
        "project_version": project.version,
        "source": source,
        "target_id": target.id,
        "target_version": target.version,
        "target_hash": target.data["config_hash"],
        "environment": environment,
        "operation": "rollback" if rollback else "deploy",
        "strategy": data.strategy,
        "configuration_refs": data.configuration_refs,
        "migration": data.migration,
        "health": {
            "kind": "revision_and_artifact",
            "timeout_seconds": data.health_timeout_seconds,
            "observations": data.health_observations,
        },
        "risk_summary": data.risk_summary,
        "rollback": rollback,
        "required_approvals": [category],
        "required_approval_id": uid(),
        "scenario": data.scenario,
        "classification": adapter.CLASSIFICATION,
        "external_cost_micro": 0,
        "live_deployment": False,
    }
    if clean(manifest) != manifest:
        raise PermissionError("Potential secret in deployment plan; use configuration reference names")
    artifact = save_artifact(
        session,
        project.org_id,
        "Immutable deployment plan",
        packages.canonical(manifest),
        "deployment_manifest",
        project_id=project.id,
    )
    row = m.BusinessRecord(
        id=str(data.request_id),
        org_id=project.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="devops_plan",
        title=f"{environment.title()} {manifest['operation']} simulation",
        status="awaiting_approval",
        data={
            "manifest": manifest,
            "manifest_hash": digest(manifest),
            "artifact_id": artifact.id,
            "request_hash": fingerprint,
            "approval_id": None,
        },
    )
    session.add(row)
    audit(
        session,
        project.org_id,
        user.id,
        "devops.plan_prepared",
        row.id,
        {"manifest_hash": digest(manifest), "category": category},
        project_id=project.id,
    )
    return row


def authority(session, plan, approved=True):
    project = session.get(m.Project, plan.project_id)
    scope(session, project)
    manifest = plan.data["manifest"]
    artifact = session.get(m.Artifact, plan.data["artifact_id"])
    target = target_for(session, project, manifest["target_id"])
    current = package_source(
        session, project, manifest["source"]["package_id"], current=not bool(manifest["rollback"])
    )
    if (
        plan.kind != "devops_plan"
        or plan.org_id != project.org_id
        or plan.client_id != project.client_id
        or manifest["project_id"] != project.id
        or manifest["client_id"] != project.client_id
        or manifest["project_version"] != project.version
        or manifest["plan_id"] != plan.id
        or digest(manifest) != plan.data["manifest_hash"]
        or current != manifest["source"]
        or target.version != manifest["target_version"]
        or target.data["config_hash"] != manifest["target_hash"]
        or target.data["config"]["environment"] != manifest["environment"]
        or not artifact
        or artifact.org_id != project.org_id
        or artifact.project_id != project.id
        or artifact.content != packages.canonical(manifest)
        or artifact.sha256 != digest_bytes(artifact.content)
    ):
        raise PermissionError("Deployment source, target or immutable manifest changed; prepare a new plan")
    if manifest["migration"] != "none":
        raise PermissionError("Database migration needs manual review; no deployment has been authorized")
    rollback = manifest["rollback"]
    if rollback:
        previous = session.get(m.BusinessRecord, rollback["receipt_id"])
        old = validate_receipt(session, project, previous)
        incident = session.get(m.BusinessRecord, rollback["incident_id"])
        if (
            previous.data["body_hash"] != rollback["receipt_hash"]
            or old["revision"] != rollback["revision"]
            or not incident
            or incident.status != "open"
            or incident.project_id != project.id
            or incident.org_id != project.org_id
            or incident.data["target_id"] != target.id
        ):
            raise PermissionError("Known rollback evidence or incident changed")
    if approved:
        approval = session.get(m.Approval, plan.data["approval_id"]) if plan.data.get("approval_id") else None
        owner = session.get(m.User, approval.owner_id) if approval else None
        if (
            not approval
            or approval.org_id != project.org_id
            or approval.id != manifest["required_approval_id"]
            or approval.subject_id != plan.id
            or approval.category != manifest["required_approvals"][0]
            or approval.version != plan.version
            or approval.subject_hash != plan.data["manifest_hash"]
            or approval.expires_at <= now()
            or approval.selection != "approve"
            or not owner
            or not owner.enabled
            or owner.org_id != project.org_id
            or owner.role != "owner"
            or plan.status in {"revoked", "cancelled", "awaiting_approval"}
        ):
            raise PermissionError(
                f"{manifest['environment'].title()} deployment is waiting for your exact current approval"
            )
        if session.get(m.Organization, project.org_id).deployments_paused:
            raise PermissionError("Deployment controls are paused. Resume them before running a simulation")
    return project, target


def approve(session, plan, user, version, manifest_hash, expires_seconds):
    lock_org(session, user.org_id)
    session.refresh(plan)
    project, _ = authority(session, plan, approved=False)
    if (
        plan.status != "awaiting_approval"
        or plan.version != version
        or plan.data["manifest_hash"] != manifest_hash
    ):
        raise PermissionError("Review and approve the exact current deployment plan")
    approval = m.Approval(
        id=plan.data["manifest"]["required_approval_id"],
        org_id=user.org_id,
        subject_id=plan.id,
        owner_id=user.id,
        category=plan.data["manifest"]["required_approvals"][0],
        version=plan.version,
        subject_hash=manifest_hash,
        selection="approve",
        expires_at=now() + expires_seconds,
    )
    session.add(approval)
    plan.status, plan.data = "approved", {**plan.data, "approval_id": approval.id}
    audit(
        session,
        project.org_id,
        user.id,
        "devops.plan_approved",
        plan.id,
        {"approval_id": approval.id, "manifest_hash": manifest_hash},
        project_id=project.id,
    )


def start(session, plan, user, request_id, manifest_hash):
    lock_org(session, user.org_id)
    session.refresh(plan)
    project, _ = authority(session, plan)
    fingerprint = digest({"plan": plan.id, "manifest_hash": manifest_hash})
    existing = session.get(m.AgentWork, str(request_id))
    if existing:
        if (
            existing.org_id != user.org_id
            or existing.kind != "deployment"
            or existing.request_hash != fingerprint
        ):
            raise PermissionError("Deployment request ID is already used")
        return existing
    if plan.data["manifest_hash"] != manifest_hash or plan.data.get("dispatch_id"):
        raise PermissionError("This approved plan already has a deployment job; reconcile it instead")
    agent = agent_for(session, project.org_id, "DevOps Engineer")
    check_agent(session, agent, "write_artifact", project)
    rollback = plan.data["manifest"]["rollback"]
    if rollback:
        incident = session.get(m.BusinessRecord, rollback["incident_id"])
        if incident.data.get("attempts", 0) >= 3:
            raise PermissionError("Rollback limit reached; owner investigation is required")
        incident.data = {**incident.data, "attempts": incident.data.get("attempts", 0) + 1}
    workflow = m.Workflow(id=uid(), org_id=user.org_id, kind="agent_work", mode="mock")
    session.add(workflow)
    session.flush()
    work = m.AgentWork(
        id=str(request_id),
        org_id=user.org_id,
        project_id=project.id,
        workflow_id=workflow.id,
        kind="deployment",
        subject_id=plan.id,
        participants=[agent.id],
        request_hash=fingerprint,
        input={"manifest_hash": manifest_hash, "classification": adapter.CLASSIFICATION},
    )
    session.add(work)
    plan.status, plan.data = "queued", {**plan.data, "dispatch_id": work.id}
    audit(
        session,
        project.org_id,
        user.id,
        "devops.queued",
        work.id,
        {"plan_id": plan.id, "manifest_hash": manifest_hash},
        project_id=project.id,
    )
    return work


def incident(session, project, plan, job):
    existing = next(
        (r for r in rows(session, project, "devops_incident") if r.data["job_id"] == job.id), None
    )
    if existing:
        return existing
    row = m.BusinessRecord(
        id=uid(),
        org_id=project.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="devops_incident",
        title="Simulated deployment needs recovery",
        status="open",
        data={
            "job_id": job.id,
            "plan_id": plan.id,
            "target_id": plan.data["manifest"]["target_id"],
            "error": job.data.get("error", "Health verification failed"),
            "attempts": 0,
            "classification": adapter.CLASSIFICATION,
            "history": [{"action": "opened", "at": now()}],
        },
    )
    session.add(row)
    session.add(m.Notification(org_id=project.org_id, title=row.title, severity="warning", subject_id=row.id))
    agent = agent_for(session, project.org_id, "DevOps Engineer")
    session.add(
        m.Message(
            org_id=project.org_id,
            project_id=project.id,
            sender="deployment-monitor",
            recipient=agent.id,
            type="EscalationRaised",
            correlation_id=row.id,
            content={"incident_id": row.id},
            authorization="saved deployment failure",
        )
    )
    return row


def finish(session, workflow, token, work, plan, job, owner_stop=False):
    if work.result.get("receipt_id"):
        return session.get(m.BusinessRecord, work.result["receipt_id"])
    project = session.get(m.Project, work.project_id)
    manifest = plan.data["manifest"]
    receipt_id = uid()
    body = {
        "plan_id": plan.id,
        "manifest_hash": plan.data["manifest_hash"],
        "approval_id": plan.data["approval_id"],
        "work_id": work.id,
        "job_id": job.id,
        "project_id": project.id,
        "target_id": manifest["target_id"],
        "environment": manifest["environment"],
        "operation": manifest["operation"],
        "package_id": manifest["source"]["package_id"],
        "artifact_hash": manifest["source"]["artifact_hash"],
        "revision": job.data["request"]["revision"],
        "adapter_hash": digest(job.data),
        "status": job.status,
        "health": job.data["health"],
        "events": job.data["events"],
        "started_at": job.data["started_at"],
        "ended_at": job.data["ended_at"],
        "classification": adapter.CLASSIFICATION,
        "live_verified": False,
        "public_deployment": False,
    }
    artifact = save_artifact(
        session,
        project.org_id,
        "Immutable simulated deployment receipt",
        packages.canonical(body),
        "deployment_receipt",
        project_id=project.id,
    )
    receipt = m.BusinessRecord(
        id=receipt_id,
        org_id=project.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="devops_receipt",
        title="Simulated deployment outcome",
        status=job.status,
        data={"body": body, "body_hash": digest(body), "artifact_id": artifact.id},
    )
    session.add(receipt)
    if job.status == "deployment_failed":
        if manifest["rollback"]:
            row = session.get(m.BusinessRecord, manifest["rollback"]["incident_id"])
            exhausted = row.data["attempts"] >= 3
            row.status = "escalated" if exhausted else "open"
            row.data = {
                **row.data,
                "history": [
                    *row.data["history"],
                    {
                        "action": "recovery_limit_escalated" if exhausted else "rollback_failed",
                        "job_id": job.id,
                        "receipt_id": receipt_id,
                        "at": now(),
                    },
                ],
            }
            if exhausted:
                session.add(
                    m.Notification(
                        org_id=project.org_id,
                        title="Recovery limit reached; owner investigation required",
                        severity="critical",
                        subject_id=row.id,
                    )
                )
        else:
            incident(session, project, plan, job)
    elif job.status == "deployment_completed" and manifest["rollback"]:
        row = session.get(m.BusinessRecord, manifest["rollback"]["incident_id"])
        row.status, row.data = (
            "resolved",
            {
                **row.data,
                "resolution_receipt": receipt_id,
                "history": [*row.data["history"], {"action": "verified_simulated_rollback", "at": now()}],
            },
        )
    plan.status = job.status
    work.result = {**work.result, "receipt_id": receipt_id}
    result = {"receipt_id": receipt_id, "body_hash": digest(body)}
    if owner_stop:
        # Owner revocation remains available while the company is paused. This
        # records a known outcome; it does not dispatch or activate a revision.
        session.add(
            m.WorkflowStep(
                org_id=work.org_id, workflow_id=workflow.id, name="deployment_final", result=result
            )
        )
        workflow.status = "cancelled" if job.status == "deployment_cancelled" else "completed"
        workflow.lease_until, workflow.step = 0, workflow.step + 1
    else:
        checkpoint(session, workflow, token, "deployment_final", result, complete=True)
    audit(
        session,
        project.org_id,
        "deployment-monitor",
        "devops.completed",
        receipt_id,
        {"status": job.status, "classification": adapter.CLASSIFICATION},
        project_id=project.id,
    )
    return receipt


async def deployment_step(session, workflow, token, work, project):
    lock_org(session, work.org_id)
    session.expire_all()
    require_lease(workflow, token)
    plan = session.get(m.BusinessRecord, work.subject_id)
    if (
        not plan
        or plan.org_id != work.org_id
        or plan.project_id != project.id
        or work.input["manifest_hash"] != plan.data["manifest_hash"]
        or plan.data.get("dispatch_id") != work.id
    ):
        raise PermissionError("Deployment workflow scope or plan changed")
    project, _ = authority(session, plan)
    agent = session.get(m.Agent, work.participants[0])
    if agent.role != "DevOps Engineer":
        raise PermissionError("Only the authorized DevOps role can handle this deployment")
    check_agent(session, agent, "write_artifact", project)
    saved = work.result.get("job_id")
    if workflow.step == 0:
        if saved:
            job = adapter.read(session, saved, work.org_id)  # Never submit an uncertain request twice.
        else:
            manifest = plan.data["manifest"]
            job_id = uid()
            request = {
                "manifest_hash": plan.data["manifest_hash"],
                "target_id": manifest["target_id"],
                "artifact_hash": manifest["source"]["artifact_hash"],
                "scenario": manifest["scenario"],
                "health": manifest["health"],
                "revision": manifest["rollback"]["revision"]
                if manifest["rollback"]
                else digest({"manifest": plan.data["manifest_hash"], "job": job_id}),
            }
            work.result = {"job_id": job_id, "request_hash": digest(request)}
            session.commit()  # Identity is durable BEFORE adapter dispatch.
            lock_org(session, work.org_id)
            session.expire_all()
            require_lease(workflow, token)
            authority(session, plan)
            job = await adapter.submit(session, job_id, work.org_id, project.id, project.client_id, request)
        lock_org(session, work.org_id)
        session.expire_all()
        require_lease(workflow, token)
        authority(session, plan)
        validate_job(job, work, plan, project)
        plan.status = "deployment_started"
        checkpoint(session, workflow, token, "deployment_dispatched", {"job_id": job.id})
    else:
        validate_job(adapter.read(session, saved, work.org_id), work, plan, project)
        job = adapter.advance(session, saved, work.org_id, workflow.step - 1)
        validate_job(job, work, plan, project)
        if job.status in {"deployment_completed", "deployment_failed", "deployment_cancelled"}:
            finish(session, workflow, token, work, plan, job)
        else:
            plan.status = job.status
            checkpoint(
                session,
                workflow,
                token,
                "deployment_" + str(workflow.step),
                {"job_id": job.id, "state": job.status},
            )


def validate_job(job, work, plan, project):
    if (
        job.id != work.result.get("job_id")
        or job.org_id != project.org_id
        or job.project_id != project.id
        or job.client_id != project.client_id
        or job.data["request_hash"] != work.result["request_hash"]
        or job.data["request"]["manifest_hash"] != plan.data["manifest_hash"]
        or job.data["request"]["target_id"] != plan.data["manifest"]["target_id"]
        or job.data["request"]["artifact_hash"] != plan.data["manifest"]["source"]["artifact_hash"]
        or job.data["classification"] != adapter.CLASSIFICATION
    ):
        raise PermissionError("Deployment adapter evidence does not match the saved project and operation")


def require_lease(workflow, token):
    if workflow.status != "running" or workflow.lease_token != token or workflow.lease_until <= now():
        raise PermissionError("Deployment worker lease revoked or expired; no operation may advance")


def command(session, work, user, action):
    lock_org(session, user.org_id)
    session.refresh(work)
    if work.kind != "deployment":
        raise PermissionError("This is not a deployment job")
    project = session.get(m.Project, work.project_id)
    if not project or project.org_id != user.org_id:
        raise PermissionError("Deployment project is unavailable")
    workflow = session.get(m.Workflow, work.workflow_id)
    plan = session.get(m.BusinessRecord, work.subject_id)
    if workflow.status in {"completed", "cancelled"}:
        return work
    if action in {"resume", "reconcile"}:
        if work.result.get("cancel_requested"):
            raise PermissionError("Cancellation is pending; retry Cancel to reconcile the saved job")
        authority(session, plan)
        if work.result.get("job_id"):
            adapter.read(session, work.result["job_id"], user.org_id)
        if workflow.status not in {"paused", "needs_attention", "failed"}:
            raise PermissionError("Only paused or uncertain deployment jobs can be resumed")
        workflow.status, workflow.last_error, workflow.lease_token, workflow.lease_until = (
            "queued",
            "",
            uid(),
            0,
        )
        workflow.attempts, workflow.deadline_at = 0, now() + 1800
    elif action == "pause":
        workflow.status, workflow.lease_token, workflow.lease_until = "paused", uid(), 0
    else:
        if action != "cancel":
            raise PermissionError("Unsupported deployment command")
        # Revoke lease before touching the adapter. A stale worker cannot checkpoint.
        workflow.status, workflow.lease_token, workflow.lease_until = "running", uid(), 0
        job_id = work.result.get("job_id")
        if job_id:
            try:
                validate_job(adapter.read(session, job_id, user.org_id), work, plan, project)
                job = adapter.cancel(session, job_id, user.org_id)
            except PermissionError:
                # No acknowledgement is not proof of cancellation. Fence the
                # worker and preserve the same job identity for later reads.
                workflow.status = "needs_attention"
                workflow.last_error = (
                    "Deployment outcome uncertain; cancellation pending. Retry Cancel to reconcile saved job."
                )
                work.result = {**work.result, "cancel_requested": True}
                plan.status = "outcome_uncertain"
                audit(
                    session,
                    user.org_id,
                    user.id,
                    "devops.cancellation_uncertain",
                    work.id,
                    project_id=project.id,
                )
                return work
            finish(session, workflow, workflow.lease_token, work, plan, job, owner_stop=True)
        else:
            workflow.status, plan.status = "cancelled", "cancelled"
    audit(session, user.org_id, user.id, "devops." + action, work.id, project_id=project.id)
    return work


def release_gate(session, project, package):
    """A simulator, staging approval, PR approval or AI response cannot certify deployment."""
    if quality.required(session, project) or rows(session, project, "devops_plan"):
        raise PermissionError(
            "Production release requires actual approved deployment and health evidence; simulation cannot authorize release"
        )
