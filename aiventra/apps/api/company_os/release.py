"""Separate exact owner release authority. No email, GitHub mutation or deployment."""

from sqlalchemy import select

from . import models as m
from . import packages
from .config import settings
from .db import now, uid
from .security import audit, canonical


def command_result(session, user, request_id, request_hash):
    record = session.get(m.BusinessRecord, str(request_id))
    if record:
        if record.org_id != user.org_id or record.data.get("actor_id") != user.id:
            raise PermissionError("Delivery command identity is outside authorization scope")
        if record.kind != "delivery_command" or record.data.get("request_hash") != request_hash:
            raise PermissionError("Delivery request ID is already used for another action")
        return record.data["result"]


def complete_command(session, user, request_id, request_hash, project_id, action, result):
    """Finite database-only actions checkpoint atomically in the existing framework."""
    workflow = m.Workflow(
        id=uid(), org_id=user.org_id, kind="delivery_event", mode="system", status="completed", step=1
    )
    session.add(workflow)
    session.flush()
    session.add(m.WorkflowStep(org_id=user.org_id, workflow_id=workflow.id, name=action, result=result))
    session.add(
        m.BusinessRecord(
            id=str(request_id),
            org_id=user.org_id,
            project_id=project_id,
            kind="delivery_command",
            title=action,
            status="completed",
            data={
                "actor_id": user.id,
                "request_hash": request_hash,
                "result": result,
                "workflow_id": workflow.id,
            },
        )
    )
    audit(
        session,
        user.org_id,
        user.id,
        action,
        result.get("id", project_id),
        {"correlation_id": str(request_id), "result": result},
        project_id=project_id,
        authorization="authenticated scoped delivery command",
    )
    return result


def release_readiness(session, package):
    packages.integrity(session, package, current=True)
    if package.classification != "live_reviewed" or package.manifest["classification"] != "live_reviewed":
        raise PermissionError("Deterministic fixture packages can never be released")
    if package.manifest["blockers"] or package.manifest["status_at_freeze"] != "package_ready":
        raise PermissionError("Package contains unresolved release blockers")
    if package.status not in {"package_ready", "awaiting_release_approval"}:
        raise PermissionError("Package is outside the owner release gate")
    if session.scalar(
        select(m.DeliveryPackage.id).where(
            m.DeliveryPackage.org_id == package.org_id,
            m.DeliveryPackage.project_id == package.project_id,
            m.DeliveryPackage.version > package.version,
        )
    ):
        raise PermissionError("A newer package version exists; stale versions cannot be released")
    cases = session.scalars(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == package.org_id,
            m.BusinessRecord.project_id == package.project_id,
            m.BusinessRecord.kind == "delivery_case",
        )
    )
    if any(
        row.data.get("kind") != "request_support" and row.status not in {"resolved", "withdrawn"}
        for row in cases
    ):
        raise PermissionError("Resolve outstanding client revisions or defects before release")
    if not package.manifest["recipient_ids"]:
        raise PermissionError("An exact intended recipient scope is required")
    project = session.get(m.Project, package.project_id)
    from .deployments import release_gate

    release_gate(session, project, package)
    from . import quality

    if quality.required(session, project):
        evidence = quality.readiness(session, project)
        refs = [row for row in package.manifest.get("files", []) if row.get("purpose") == "quality_readiness"]
        if not evidence["ready"] or len(refs) != 1:
            raise PermissionError("Current three-stage QA and immutable package evidence are required")
        if packages.read_blob(package, refs[0]).decode() != canonical(evidence):
            raise PermissionError("Package QA evidence is stale")
    budget = session.scalar(
        select(m.Budget).where(m.Budget.org_id == package.org_id, m.Budget.scope == f"project:{project.id}")
    )
    if not budget or budget.reserved_micro:
        raise PermissionError("Resolve pending financial reservations before release")
    if session.scalar(
        select(m.ModelRun.id).where(
            m.ModelRun.org_id == package.org_id,
            m.ModelRun.project_id == package.project_id,
            m.ModelRun.status.in_(["started", "uncertain"]),
        )
    ):
        raise PermissionError("Resolve unfinished or uncertain inference before release")
    can_respond = False
    for user_id in package.manifest["recipient_ids"]:
        user = session.get(m.User, user_id)
        grant = session.scalar(
            select(m.ClientAccessGrant).where(
                m.ClientAccessGrant.org_id == package.org_id,
                m.ClientAccessGrant.project_id == package.project_id,
                m.ClientAccessGrant.client_id == package.client_id,
                m.ClientAccessGrant.user_id == user_id,
                m.ClientAccessGrant.revoked_at.is_(None),
            )
        )
        if (
            not user
            or user.org_id != package.org_id
            or user.role != "client"
            or not user.enabled
            or user.client_id != package.client_id
            or not grant
        ):
            raise PermissionError("Intended recipient has no current scoped client grant")
        from .client_access import grant_for

        grant_for(session, user, package.project_id)
        can_respond = can_respond or grant.can_respond
    if not can_respond:
        raise PermissionError("At least one intended recipient must have formal response permission")
    deadline = package.manifest.get("acceptance_deadline")
    if deadline is not None and deadline <= now():
        raise PermissionError("Package acceptance deadline expired before release")
    return project


def current_approval(session, package):
    approval = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == package.org_id,
            m.Approval.category == "delivery_release",
            m.Approval.subject_id == package.id,
            m.Approval.version == package.version,
        )
    )
    owner = session.get(m.User, approval.owner_id) if approval else None
    if (
        not approval
        or approval.subject_hash != package.manifest_hash
        or approval.selection != "approve"
        or approval.expires_at <= now()
        or not owner
        or not owner.enabled
        or owner.org_id != package.org_id
        or owner.role != "owner"
    ):
        raise PermissionError("Current exact owner release approval is required")
    return approval


def transition(session, project, stage, actor, correlation, detail=None):
    lifecycle = session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == project.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "delivery_lifecycle",
        )
    )
    previous = lifecycle.status if lifecycle else "final_review"
    allowed = {
        "final_review": {"package_preparation", "blocked"},
        "package_preparation": {"awaiting_owner_release", "blocked", "cancelled"},
        "awaiting_owner_release": {
            "package_preparation",
            "awaiting_client_acceptance",
            "changes_requested",
            "blocked",
            "cancelled",
            "final_review",
        },
        "awaiting_client_acceptance": {
            "accepted",
            "changes_requested",
            "blocked",
            "package_preparation",
            "final_review",
        },
        "accepted": {"closed", "changes_requested", "package_preparation", "blocked", "final_review"},
        "changes_requested": {
            "implementation",
            "package_preparation",
            "blocked",
            "cancelled",
            "final_review",
        },
        "implementation": {"final_review", "package_preparation", "blocked", "cancelled"},
        "blocked": {"package_preparation", "changes_requested", "cancelled", "final_review"},
        "cancelled": {"changes_requested", "package_preparation", "final_review"},
        "closed": {"changes_requested"},
    }
    if stage != previous and stage not in allowed.get(previous, set()):
        raise PermissionError(f"Delivery stage cannot move from {previous} to {stage}")
    if not lifecycle:
        lifecycle = m.BusinessRecord(
            id=uid(),
            org_id=project.org_id,
            project_id=project.id,
            client_id=project.client_id,
            kind="delivery_lifecycle",
            title="Project delivery lifecycle",
        )
        session.add(lifecycle)
        session.flush()
    lifecycle.status, lifecycle.version = stage, lifecycle.version + 1
    lifecycle.data = {**lifecycle.data, "correlation_id": str(correlation), **(detail or {})}
    audit(
        session,
        project.org_id,
        actor,
        "delivery.stage_changed",
        project.id,
        {"previous": previous, "new": stage, "correlation_id": str(correlation)},
        project_id=project.id,
    )
    return lifecycle


def reconsider(session, package, user, stage):
    """An older package decision must not overwrite a newer delivery lifecycle."""
    lifecycle = session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == package.org_id,
            m.BusinessRecord.project_id == package.project_id,
            m.BusinessRecord.kind == "delivery_lifecycle",
        )
    )
    if lifecycle and lifecycle.data.get("package_id") == package.id:
        if lifecycle.status == "closed":
            raise PermissionError("Reopen the closed project before withdrawing its delivery")
        transition(session, session.get(m.Project, package.project_id), stage, user.id, package.id)


def decide(session, package, user, decision, reason):
    if decision == "approve":
        release_readiness(session, package)
    else:
        packages.integrity(session, package)
        if package.status not in {"package_ready", "package_blocked", "awaiting_release_approval"}:
            raise PermissionError("Package is outside the owner decision gate")
    existing = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == package.org_id,
            m.Approval.category == "delivery_release",
            m.Approval.subject_id == package.id,
            m.Approval.version == package.version,
        )
    )
    if decision == "approve":
        if existing:
            current_approval(session, package)
            return existing
        approval = m.Approval(
            id=uid(),
            org_id=package.org_id,
            category="delivery_release",
            subject_id=package.id,
            subject_hash=package.manifest_hash,
            version=package.version,
            owner_id=user.id,
            selection="approve",
            expires_at=now() + settings().delivery_release_ttl_seconds,
        )
        session.add(approval)
        session.flush()
        package.status = "awaiting_release_approval"
        packages.notify(session, package, "Owner approved exact delivery release")
        audit(
            session,
            user.org_id,
            user.id,
            "delivery.release_approved",
            package.id,
            {"approval_id": approval.id, "manifest_hash": package.manifest_hash, "reason": reason},
            project_id=package.project_id,
            authorization=f"owner-release:{approval.id}",
        )
        return approval
    if existing:
        existing.expires_at = min(existing.expires_at, now())
    package.status = "withdrawn" if decision == "reject" else "changes_requested"
    reconsider(session, package, user, "changes_requested")
    packages.notify(
        session,
        package,
        "Owner requested delivery changes"
        if decision == "request_changes"
        else "Owner rejected delivery release",
    )
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.release_" + decision,
        package.id,
        {"reason": reason, "manifest_hash": package.manifest_hash},
        project_id=package.project_id,
    )


def publish(session, package, user, approval_id):
    project = release_readiness(session, package)
    approval = current_approval(session, package)
    if approval.id != approval_id:
        raise PermissionError("Release action must identify the exact owner approval")
    proof = m.BusinessRecord(
        id=uid(),
        org_id=package.org_id,
        project_id=package.project_id,
        client_id=package.client_id,
        kind="delivery_release",
        title=f"Released package v{package.version}",
        status="released",
        data={
            "package_id": package.id,
            "manifest_hash": package.manifest_hash,
            "version": package.version,
            "approval_id": approval.id,
            "released_at": now(),
            "released_by": user.id,
            "recipient_ids": package.manifest["recipient_ids"],
        },
    )
    session.add(proof)
    for previous in session.scalars(
        select(m.DeliveryPackage).where(
            m.DeliveryPackage.org_id == package.org_id,
            m.DeliveryPackage.project_id == project.id,
            m.DeliveryPackage.status == "released",
        )
    ):
        previous.status = "superseded"
    package.status = "released"
    transition(
        session,
        project,
        "awaiting_client_acceptance",
        user.id,
        proof.id,
        {"package_id": package.id, "manifest_hash": package.manifest_hash},
    )
    packages.notify(session, package, "Client package available; awaiting acceptance")
    session.flush()
    return proof
