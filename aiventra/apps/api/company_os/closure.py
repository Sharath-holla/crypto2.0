"""Exact owner closure after client acceptance, retained deliverables and settled finance."""

from sqlalchemy import select

from . import models as m
from . import packages, release
from .db import now, uid
from .security import digest, verify_audit


def readiness(session, project):
    if project.status != "active":
        raise PermissionError("Closure requires an active project")
    package = session.scalar(
        select(m.DeliveryPackage)
        .where(m.DeliveryPackage.org_id == project.org_id, m.DeliveryPackage.project_id == project.id)
        .order_by(m.DeliveryPackage.version.desc())
    )
    if not package or package.status != "released" or package.classification != "live_reviewed":
        raise PermissionError("The latest package must be live-reviewed and released")
    packages.integrity(session, package, current=True)
    if package.manifest["blockers"]:
        raise PermissionError("Required deliverables and documentation are incomplete")
    acceptance = session.scalar(
        select(m.DeliveryResponse).where(
            m.DeliveryResponse.org_id == project.org_id,
            m.DeliveryResponse.package_id == package.id,
            m.DeliveryResponse.kind == "accept",
        )
    )
    if (
        not acceptance
        or acceptance.manifest_hash != package.manifest_hash
        or acceptance.package_version != package.version
    ):
        raise PermissionError("Exact formal client acceptance is required")
    proof = next(
        (
            row
            for row in session.scalars(
                select(m.BusinessRecord).where(
                    m.BusinessRecord.org_id == project.org_id,
                    m.BusinessRecord.project_id == project.id,
                    m.BusinessRecord.kind == "delivery_release",
                    m.BusinessRecord.status == "released",
                )
            )
            if row.data.get("package_id") == package.id
            and row.data.get("manifest_hash") == package.manifest_hash
        ),
        None,
    )
    if not proof:
        raise PermissionError("Persisted exact release authorization is missing")
    if session.scalar(
        select(m.BusinessRecord.id).where(
            m.BusinessRecord.org_id == project.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "delivery_case",
            m.BusinessRecord.status.not_in(["resolved", "withdrawn"]),
        )
    ):
        raise PermissionError("Resolve outstanding client cases before closure")
    tasks = list(
        session.scalars(
            select(m.Task)
            .where(m.Task.org_id == project.org_id, m.Task.project_id == project.id)
            .order_by(m.Task.id)
        )
    )
    if any(task.status != "completed" for task in tasks):
        raise PermissionError("All project tasks must be complete")
    runs = list(
        session.scalars(
            select(m.ModelRun)
            .where(m.ModelRun.org_id == project.org_id, m.ModelRun.project_id == project.id)
            .order_by(m.ModelRun.id)
        )
    )
    transactions = []
    for run in runs:
        transaction = session.scalar(
            select(m.Transaction).where(
                m.Transaction.org_id == project.org_id, m.Transaction.run_id == run.id
            )
        )
        if (
            run.status in {"started", "uncertain"}
            or not transaction
            or transaction.amount_micro != run.cost_micro
        ):
            raise PermissionError("All project inference must have settled financial evidence")
        transactions.append(
            {
                "id": transaction.id,
                "run_id": run.id,
                "amount_micro": transaction.amount_micro,
                "basis": transaction.basis,
            }
        )
    budgets = list(
        session.scalars(
            select(m.Budget)
            .where(
                m.Budget.org_id == project.org_id,
                m.Budget.scope.in_([f"project:{project.id}", *[f"task:{task.id}" for task in tasks]]),
            )
            .order_by(m.Budget.id)
        )
    )
    if any(row.reserved_micro or row.spent_micro > row.limit_micro for row in budgets):
        raise PermissionError("Final budgets have unresolved reservations or overspend")
    if not verify_audit(session, project.org_id)["valid"]:
        raise PermissionError("Audit chain verification failed")
    manifest = {
        "project_id": project.id,
        "project_version": project.version,
        "package_id": package.id,
        "package_version": package.version,
        "manifest_hash": package.manifest_hash,
        "acceptance_id": acceptance.id,
        "accepted_at": acceptance.created_at,
        "accepted_by": acceptance.user_id,
        "release_id": proof.id,
        "release_approval_id": proof.data["approval_id"],
        "files": [{"sha256": file["sha256"], "bytes": file["bytes"]} for file in package.manifest["files"]],
        "budgets": [
            {
                "id": row.id,
                "version": row.version,
                "scope": row.scope,
                "limit_micro": row.limit_micro,
                "spent_micro": row.spent_micro,
            }
            for row in budgets
        ],
        "transactions": transactions,
        "task_ids": [task.id for task in tasks],
        "retention": "Retain immutable package files, statements, release evidence and audit; no automatic deletion",
        "audit_chain_verified": True,
        "final_audit_event": "delivery.project_closed",
    }
    return manifest


def approve(session, project, user, manifest, expected):
    if digest(manifest) != expected:
        raise PermissionError("Closure evidence changed; inspect the current exact manifest")
    previous = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == project.org_id,
            m.Approval.category == "delivery_closure",
            m.Approval.subject_id == project.id,
            m.Approval.version == project.version,
        )
    )
    if previous:
        if previous.subject_hash != expected or previous.expires_at <= now():
            raise PermissionError("Closure approval is stale or expired; reopen a reviewed project revision")
        return previous
    approval = m.Approval(
        id=uid(),
        org_id=project.org_id,
        category="delivery_closure",
        subject_id=project.id,
        version=project.version,
        subject_hash=expected,
        owner_id=user.id,
        selection="approve",
        expires_at=now() + 3600,
    )
    session.add(approval)
    session.flush()
    return approval


def close(session, project, user, expected, approval_id, request_id):
    manifest = readiness(session, project)
    approval = session.get(m.Approval, approval_id)
    approver = session.get(m.User, approval.owner_id) if approval else None
    if (
        digest(manifest) != expected
        or not approval
        or approval.org_id != user.org_id
        or approval.category != "delivery_closure"
        or approval.subject_id != project.id
        or approval.version != project.version
        or approval.subject_hash != expected
        or approval.selection != "approve"
        or approval.expires_at <= now()
        or not approver
        or approver.org_id != user.org_id
        or not approver.enabled
        or approver.role != "owner"
    ):
        raise PermissionError("Exact current owner closure approval is required")
    release.transition(session, project, "closed", user.id, request_id, {"closure_hash": expected})
    project.status = "closed"
    proof = m.BusinessRecord(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        kind="delivery_closure",
        title="Owner-approved project closure",
        status="closed",
        data={
            "manifest": manifest,
            "closure_hash": expected,
            "approval_id": approval.id,
            "closed_at": now(),
            "closed_by": user.id,
        },
    )
    session.add(proof)
    return {"id": project.id, "status": "closed", "closure_id": proof.id, "closure_hash": expected}
