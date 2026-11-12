"""Frozen delivery evidence on the existing durable worker; no inference or external send."""

import hashlib
import json
import os
import re

from sqlalchemy import select

from . import delivery
from . import models as m
from .config import settings
from .db import now, uid
from .security import audit, canonical, clean, digest
from .staffing import lock_org
from .workflows import checkpoint

DOCUMENT_PURPOSES = (
    "architecture_decisions",
    "high_level_design",
    "low_level_design",
    "database",
    "api",
    "deployment_instructions",
)
MAX_FILE = 500_000
MAX_TOTAL = 2_000_000


def notify(session, package, title):
    session.add(m.Notification(org_id=package.org_id, severity="info", title=title, subject_id=package.id))


def review_evidence(session, project, record):
    """Validate persisted role/run/checkpoint provenance, not merely a review status."""
    if (
        not record
        or record.org_id != project.org_id
        or record.project_id != project.id
        or record.client_id != project.client_id
        or record.kind != "delivery_review"
        or record.status not in {"fixture_reviewed", "awaiting_delivery_approval"}
    ):
        raise PermissionError("A completed scoped final review is required")
    mode = record.data.get("mode")
    if mode not in {"live", "mock"}:
        raise PermissionError("Final-review mode is invalid")
    manifest = delivery.current_source(session, project, mode, record.data.get("source_hash"))
    if manifest != record.data.get("manifest"):
        raise PermissionError("Saved final-review manifest changed")
    work = session.get(m.AgentWork, record.data.get("work_id"))
    workflow = session.get(m.Workflow, work.workflow_id) if work else None
    if (
        not work
        or work.org_id != project.org_id
        or work.project_id != project.id
        or work.subject_id != record.id
        or work.kind != "delivery"
        or not workflow
        or workflow.org_id != project.org_id
        or workflow.mode != mode
        or workflow.status != "completed"
        or workflow.step != len(delivery.ROLES)
        or len(work.participants) != len(delivery.ROLES)
        or work.input.get("source_hash") != record.data.get("source_hash")
    ):
        raise PermissionError("Final-review execution is incomplete")
    rows = record.data.get("reviews", [])
    if [row.get("role") for row in rows] != delivery.ROLES:
        raise PermissionError("All five independent final reviews are required")
    for index, row in enumerate(rows):
        artifact = session.get(m.Artifact, row.get("artifact_id"))
        run = session.get(m.ModelRun, row.get("run_id"))
        agent = session.get(m.Agent, row.get("agent_id"))
        step = session.scalar(
            select(m.WorkflowStep).where(
                m.WorkflowStep.workflow_id == workflow.id, m.WorkflowStep.name == f"delivery_review_{index}"
            )
        )
        result = {key: row.get(key) for key in ("approved", "summary", "checked_criteria", "findings")}
        if (
            not agent
            or agent.org_id != project.org_id
            or agent.role != row["role"]
            or agent.id != work.participants[index]
            or not row.get("approved")
            or row.get("findings")
            or row.get("mode") != mode
            or sorted(row.get("checked_criteria", [])) != list(range(len(manifest["acceptance"])))
            or not artifact
            or artifact.org_id != project.org_id
            or artifact.project_id != project.id
            or artifact.agent_id != agent.id
            or artifact.kind != "delivery_review"
            or artifact.sha256 != row.get("sha256")
            or sha(artifact.content.encode()) != artifact.sha256
            or json.loads(artifact.content) != result
            or not run
            or run.org_id != project.org_id
            or run.workflow_id != workflow.id
            or run.project_id != project.id
            or run.agent_id != agent.id
            or run.status != "succeeded"
            or run.step_name != f"delivery_review_{index}"
            or run.response != result
            or not step
            or step.org_id != project.org_id
            or step.result
            != {
                "artifact_id": artifact.id,
                "sha256": artifact.sha256,
                "source_hash": record.data["source_hash"],
            }
        ):
            raise PermissionError("Final-review artifact, model result or checkpoint is invalid")
        model = session.get(m.ModelConfig, run.model_id)
        provider = session.get(m.Provider, model.provider_id) if model else None
        if not model or model.org_id != project.org_id or not provider or provider.org_id != project.org_id:
            raise PermissionError("Final-review model provenance is invalid")
        if mode == "live" and (provider.kind == "mock" or run.cost_basis == "mock_no_charge"):
            raise PermissionError("Fixture inference cannot authorize a live package")
    if mode == "live":
        for task in manifest["tasks"]:
            for run_id in task["run_ids"]:
                if session.get(m.ModelRun, run_id).cost_basis == "mock_no_charge":
                    raise PermissionError("Fixture author inference cannot authorize a live package")
    return manifest


def sha(content):
    return hashlib.sha256(content).hexdigest()


def blob_path(org_id, content_hash):
    if not re.fullmatch(r"[a-f0-9]{64}", content_hash) or not re.fullmatch(r"[a-zA-Z0-9-]{1,36}", org_id):
        raise PermissionError("Invalid immutable artifact reference")
    root = settings().artifact_root.resolve()
    path = root / "delivery" / org_id / content_hash[:2] / (content_hash + ".txt")
    if not path.resolve().is_relative_to(root) or any(
        part.is_symlink() or part.is_junction() for part in [path, *path.parents]
    ):
        raise PermissionError("Immutable artifact storage is outside the private root")
    return path


def store_blob(org_id, content):
    body = content.encode("utf-8")
    if len(body) > MAX_FILE or clean(content) != content or "\0" in content:
        raise PermissionError("Delivery artifact is oversized, binary or contains sensitive material")
    content_hash = sha(body)
    path = blob_path(org_id, content_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Publish a fully fsynced file by an atomic, no-replace hard link. A crash
    # leaves either an unreferenced private temp file or the complete hash blob.
    temporary = path.parent / (uid() + ".tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(body)
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
    finally:
        temporary.unlink(missing_ok=True)
    with path.open("rb") as source:
        retained = source.read(MAX_FILE + 1)
    if retained != body:
        raise PermissionError("Immutable artifact is missing, replaced or has an interrupted write")
    return content_hash, len(body)


def read_blob(package, reference):
    path = blob_path(package.org_id, reference["sha256"])
    try:
        with path.open("rb") as source:
            body = source.read(MAX_FILE + 1)
    except OSError:
        raise PermissionError("Immutable delivery file is missing") from None
    if len(body) != reference["bytes"] or sha(body) != reference["sha256"]:
        raise PermissionError("Immutable delivery file failed hash verification")
    return body


def assemble(session, package):
    project = session.get(m.Project, package.project_id)
    review = session.get(m.BusinessRecord, package.review_id)
    source = review_evidence(session, project, review)
    if digest(source) != package.source_hash:
        raise PermissionError("Package source changed after preparation was requested")
    proposal = session.get(m.Proposal, project.proposal_id)
    requirement = session.get(m.Requirement, proposal.requirement_id)
    files, blockers = [], []

    def add(name, purpose, content, visible=False, artifact_id=None):
        content_hash, size = store_blob(package.org_id, content)
        files.append(
            {
                "id": str(len(files)),
                "name": name[:200],
                "purpose": purpose,
                "sha256": content_hash,
                "bytes": size,
                "client_visible": visible,
                "artifact_id": artifact_id,
            }
        )

    add(
        "Approved requirements.json",
        "requirements",
        canonical(
            {
                "title": requirement.title,
                "version": requirement.version,
                "text": requirement.text,
                "answers": requirement.answers,
                "acceptance": source["acceptance"],
            }
        ),
        True,
    )
    add("Approved proposal.json", "proposal", canonical(proposal.content))
    add("Verified project evidence.json", "internal_evidence", canonical(source))
    add("Five-role final review.json", "internal_reviews", canonical(review.data["reviews"]))
    if "quality" in source:
        from . import quality

        evaluation = quality.readiness(session, project)
        if not evaluation["ready"] or evaluation["manifest_hash"] != source["quality"]["manifest_hash"]:
            raise PermissionError("Exact three-stage QA evidence changed before package assembly")
        add("Three-stage QA readiness.json", "quality_readiness", canonical(evaluation), True)
        for candidate in evaluation["manifest"]["candidates"]:
            plan = session.get(m.BusinessRecord, candidate["plan_id"])
            add(f"Approved QA plan {plan.id}.json", "quality_plan", canonical(plan.data))
            for ref in candidate["reports"]:
                report = session.get(m.BusinessRecord, ref["report_id"])
                artifact = session.get(m.Artifact, report.data["artifact_id"])
                add(
                    f"Round {ref['stage']} evidence {report.id}.json",
                    "quality_report",
                    artifact.content,
                    False,
                    artifact.id,
                )
    selected = package.input.get("documents", [])
    actual_sources = {row.get("artifact_id") for row in source["sources"] if row.get("artifact_id")}
    for document in selected:
        artifact = session.get(m.Artifact, document["artifact_id"])
        if (
            not artifact
            or artifact.org_id != package.org_id
            or artifact.project_id != project.id
            or artifact.conversation_id
            or artifact.id not in actual_sources
            or sha(artifact.content.encode()) != artifact.sha256
        ):
            raise PermissionError("Selected document is not bound to the reviewed project source")
        add(artifact.name, document["purpose"], artifact.content, document["client_visible"], artifact.id)
    purposes = {row["purpose"] for row in selected}
    for purpose in DOCUMENT_PURPOSES:
        if purpose not in purposes:
            blockers.append(f"Missing reviewed document: {purpose}")
    coding = [task for task in source["tasks"] if task["kind"] == "coding"]
    repositories, build_artifacts = [], []
    for row in coding:
        task = session.get(m.Task, row["id"])
        draft = task.evidence["pull_request"]
        execution = session.get(m.Execution, task.evidence["execution_id"])
        publications = list(
            session.scalars(
                select(m.BusinessRecord).where(
                    m.BusinessRecord.org_id == package.org_id,
                    m.BusinessRecord.project_id == project.id,
                    m.BusinessRecord.kind == "github_publication",
                )
            )
        )
        refs = [
            {
                "record_id": item.id,
                "status": item.status,
                "pull_request": {
                    "number": item.data.get("number"),
                    "url": item.data.get("url"),
                    "remote_commit": item.data.get("manifest", {}).get("head_commit"),
                },
                "manifest_hash": item.data.get("manifest_hash"),
            }
            for item in publications
            if item.data.get("manifest", {}).get("task_id") == task.id
        ]
        repositories.append(
            {
                "task_id": task.id,
                "repository_id": task.payload["repository_id"],
                "source_commit": draft["head_commit"],
                "tree": task.evidence["candidate_tree"],
                "qa_execution_id": execution.id,
                "test_exit_code": execution.exit_code,
                "build_exit_code": task.evidence["build_exit_code"],
                "pull_requests": refs,
            }
        )
        verified = next(item for item in source["sources"] if item["task_id"] == task.id)
        add(
            f"Verified source change {task.id}.diff",
            "source_patch",
            verified["diff"],
            package.input.get("include_source_patches", False),
        )
        receipt = {
            "task_id": task.id,
            "source_commit": draft["head_commit"],
            "tree": task.evidence["candidate_tree"],
            "execution_id": execution.id,
            "environment": execution.environment,
            "test_suite": task.payload["test_suite"],
            "test_exit_code": execution.exit_code,
            "build_exit_code": task.evidence["build_exit_code"],
            "artifact_type": "verified_source_patch",
            "deployable_binary_exported": False,
        }
        add(f"Build and QA receipt {task.id}.json", "build_receipt", canonical(receipt), True)
        build_artifacts.append({**receipt, "sha256": files[-2]["sha256"]})
        if not package.input.get("include_source_patches"):
            blockers.append(f"Task {task.id}: verified source patch is not selected for client disclosure")
    milestones = [
        {"id": row.id, "name": row.name, "position": row.position}
        for row in session.scalars(select(m.Milestone).where(m.Milestone.project_id == project.id))
    ]
    if sum(row["bytes"] for row in files) > MAX_TOTAL:
        raise PermissionError("Package exceeds the bounded delivery storage limit")
    status = "package_blocked" if blockers else "package_ready"
    return {
        "package_id": package.id,
        "org_id": package.org_id,
        "client_id": project.client_id,
        "project_id": project.id,
        "project_name": project.name,
        "version": package.version,
        "requirement_id": requirement.id,
        "requirement_version": requirement.version,
        "proposal_id": proposal.id,
        "proposal_version": proposal.version,
        "proposal_hash": proposal.content_hash,
        "source_hash": package.source_hash,
        "review_id": review.id,
        "reviews": [
            {
                "role": row["role"],
                "artifact_id": row["artifact_id"],
                "sha256": row["sha256"],
                "run_id": row["run_id"],
                "approved": row["approved"],
            }
            for row in review.data["reviews"]
        ],
        "workforce": {key: source[key] for key in ("staffing_id", "staffing_version", "staffing_hash")},
        "tasks": source["tasks"],
        "milestones": milestones,
        "repositories": repositories,
        "files": files,
        "build_artifacts": build_artifacts,
        "budget": source["budget"],
        "blockers": blockers,
        "summary": package.input["summary"],
        "release_notes": package.input["release_notes"],
        "test_summary": package.input["test_summary"],
        "limitations": package.input["limitations"],
        "known_issues": package.input["known_issues"],
        "recipient_ids": package.input["recipient_ids"],
        "acceptance_deadline": package.input.get("acceptance_deadline"),
        "deployment": {"status": "not_verified", "url": None},
        "release_actions": ["Make explicitly selected files available in authenticated client portal"],
        "classification": package.classification,
        "status_at_freeze": status,
        "created_at": package.created_at,
        "created_by": package.owner_id,
        "supersedes_id": package.supersedes_id,
    }


def integrity(session, package, current=False):
    if not package.finalized_at or digest(package.manifest) != package.manifest_hash:
        raise PermissionError("Package manifest is not frozen or failed hash verification")
    expected = {
        "package_id": package.id,
        "org_id": package.org_id,
        "client_id": package.client_id,
        "project_id": package.project_id,
        "version": package.version,
        "review_id": package.review_id,
        "source_hash": package.source_hash,
        "classification": package.classification,
        "created_at": package.created_at,
        "created_by": package.owner_id,
        "supersedes_id": package.supersedes_id,
    }
    if any(package.manifest.get(key) != value for key, value in expected.items()):
        raise PermissionError("Frozen manifest identity does not match its package scope")
    sources = [row for row in package.manifest["files"] if row["purpose"] == "internal_evidence"]
    if len(sources) != 1 or sources[0]["sha256"] != package.source_hash:
        raise PermissionError("Frozen source file is not bound to the reviewed source hash")
    if len({row["id"] for row in package.manifest["files"]}) != len(package.manifest["files"]):
        raise PermissionError("Frozen file identifiers must be unique")
    for reference in package.manifest["files"]:
        read_blob(package, reference)
    if current:
        project = session.get(m.Project, package.project_id)
        source = review_evidence(
            session,
            project,
            session.get(m.BusinessRecord, package.review_id),
        )
        if digest(source) != package.source_hash:
            raise PermissionError("Package source is stale")
        proposal = session.get(m.Proposal, project.proposal_id)
        requirement = session.get(m.Requirement, proposal.requirement_id)
        required = canonical(
            {
                "title": requirement.title,
                "version": requirement.version,
                "text": requirement.text,
                "answers": requirement.answers,
                "acceptance": source["acceptance"],
            }
        )
        reference = next(row for row in package.manifest["files"] if row["purpose"] == "requirements")
        if sha(required.encode()) != reference["sha256"] or project.name != package.manifest["project_name"]:
            raise PermissionError("Approved requirement or project identity changed after freeze")
    return True


async def package_step(session, workflow, token):
    lock_org(session, workflow.org_id)
    session.expire_all()
    package = session.scalar(select(m.DeliveryPackage).where(m.DeliveryPackage.workflow_id == workflow.id))
    if not package or package.org_id != workflow.org_id or package.status != "preparing":
        raise PermissionError("Package preparation was revoked or is outside workflow scope")
    manifest = assemble(session, package)
    if workflow.step == 0:
        checkpoint(
            session,
            workflow,
            token,
            "validate_delivery_artifacts",
            {
                "source_hash": package.source_hash,
                "files_hash": digest(manifest["files"]),
                "blockers": manifest["blockers"],
            },
        )
    elif workflow.step == 1:
        validation = session.scalar(
            select(m.WorkflowStep).where(
                m.WorkflowStep.workflow_id == workflow.id,
                m.WorkflowStep.name == "validate_delivery_artifacts",
            )
        )
        if not validation or validation.result["files_hash"] != digest(manifest["files"]):
            raise PermissionError("Delivery artifact validation changed before freeze")
        checkpoint(
            session,
            workflow,
            token,
            "freeze_delivery_package",
            {"package_id": package.id, "manifest_hash": digest(manifest)},
            complete=True,
        )
        package.manifest, package.manifest_hash = manifest, digest(manifest)
        package.finalized_at, package.status = now(), manifest["status_at_freeze"]
        if package.classification == "live_reviewed":
            from .release import transition

            transition(
                session,
                session.get(m.Project, package.project_id),
                "blocked" if manifest["blockers"] else "awaiting_owner_release",
                "worker",
                package.request_id,
                {"package_id": package.id, "manifest_hash": package.manifest_hash},
            )
        notify(
            session, package, "Delivery package blocked" if manifest["blockers"] else "Delivery package ready"
        )
    else:
        raise PermissionError("Invalid package preparation checkpoint")
    audit(
        session,
        package.org_id,
        "worker",
        "delivery.package_checkpoint",
        package.id,
        {"step": workflow.step, "status": package.status, "correlation_id": package.request_id},
        project_id=package.project_id,
        authorization=f"owner-package:{package.owner_id}",
    )
