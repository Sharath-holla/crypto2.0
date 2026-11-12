"""Append-only exact-version statements, with separate mutable follow-up cases."""

import json

from sqlalchemy import select

from . import client_access, packages, release
from . import models as m
from .db import now, uid
from .security import clean


def response_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "package_id",
            "project_id",
            "user_id",
            "created_at",
            "package_version",
            "manifest_hash",
            "kind",
            "reason",
            "evidence",
        )
    }


def submit(session, user, package_id, data, request_hash):
    previous = release.command_result(session, user, data.request_id, request_hash)
    if previous:
        # Revoked access cannot use a retry to retrieve statement content.
        row = session.get(m.DeliveryResponse, previous["id"])
        client_access.grant_for(session, user, row.project_id, True)
        return previous
    package, _ = client_access.released_package(session, user, package_id, True)
    if package.version != data.version or package.manifest_hash != data.manifest_hash:
        raise PermissionError("Client statement must bind the exact released version and manifest")
    if data.kind in {"accept", "reject", "request_changes"}:
        if package.status != "released":
            raise PermissionError("Formal decisions require the latest released version")
        deadline = package.manifest.get("acceptance_deadline")
        if deadline and deadline <= now():
            raise PermissionError("The formal response deadline has expired; contact the owner")
        prior = session.scalar(
            select(m.DeliveryResponse.id).where(
                m.DeliveryResponse.org_id == user.org_id,
                m.DeliveryResponse.package_id == package.id,
                m.DeliveryResponse.kind.in_(["accept", "reject", "request_changes"]),
            )
        )
        if prior:
            raise PermissionError(
                "This version already has a formal client decision; revisions require a new package"
            )
    if data.kind == "accept" and session.scalar(
        select(m.BusinessRecord.id).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == package.project_id,
            m.BusinessRecord.kind == "delivery_case",
            m.BusinessRecord.status.not_in(["resolved", "withdrawn"]),
        )
    ):
        raise PermissionError("Resolve outstanding client cases before acceptance")
    reason = clean(data.reason)
    if reason != data.reason:
        raise PermissionError("Client statements must not contain credentials or sensitive material")
    attachments = []
    for item in data.attachments:
        content_hash, size = packages.store_blob(user.org_id, item.content)
        attachments.append({"name": clean(item.name), "sha256": content_hash, "bytes": size})
    response_id, case_id = uid(), uid() if data.kind != "accept" else None
    evidence = {
        "affected_criteria": data.affected_criteria,
        "severity": data.severity,
        "priority": data.priority,
        "reproduction": clean(data.reproduction),
        "feature": clean(data.feature),
        "attachments": attachments,
        "case_id": case_id,
    }
    # Criteria are the approved source, not mutable client-supplied labels.
    source = next(row for row in package.manifest["files"] if row["purpose"] == "internal_evidence")
    criteria = json.loads(packages.read_blob(package, source))["acceptance"]
    if any(index >= len(criteria) for index in data.affected_criteria):
        raise PermissionError("Affected acceptance criterion is outside the released scope")
    result = {
        "id": response_id,
        "package_id": package.id,
        "kind": data.kind,
        "case_id": case_id,
        "version": package.version,
        "manifest_hash": package.manifest_hash,
    }
    release.complete_command(
        session,
        user,
        data.request_id,
        request_hash,
        package.project_id,
        "delivery.client_" + data.kind,
        result,
    )
    session.flush()
    command = session.get(m.BusinessRecord, str(data.request_id))
    row = m.DeliveryResponse(
        id=response_id,
        org_id=user.org_id,
        package_id=package.id,
        project_id=package.project_id,
        client_id=user.client_id,
        user_id=user.id,
        workflow_id=command.data["workflow_id"],
        request_id=str(data.request_id),
        request_hash=request_hash,
        package_version=package.version,
        manifest_hash=package.manifest_hash,
        kind=data.kind,
        reason=reason,
        evidence=evidence,
    )
    session.add(row)
    manager = session.scalar(
        select(m.Agent).where(m.Agent.org_id == user.org_id, m.Agent.role == "Project Manager")
    )
    session.add(
        m.Message(
            org_id=user.org_id,
            project_id=package.project_id,
            sender=user.id,
            recipient=manager.id if manager else "Project Manager",
            type="delivery_client_response",
            correlation_id=str(data.request_id),
            content={
                "response_id": response_id,
                "package_id": package.id,
                "manifest_hash": package.manifest_hash,
                "kind": data.kind,
                "trust": "untrusted client statement; inspect immutable response",
            },
            authorization="exact released package and scoped client response grant",
        )
    )
    if case_id:
        session.add(
            m.BusinessRecord(
                id=case_id,
                org_id=user.org_id,
                client_id=user.client_id,
                project_id=package.project_id,
                kind="delivery_case",
                status="submitted",
                title=f"Client {data.kind.replace('_', ' ')} · v{package.version}",
                data={
                    "kind": data.kind,
                    "response_id": response_id,
                    "package_id": package.id,
                    "package_version": package.version,
                    "manifest_hash": package.manifest_hash,
                    "assigned_role": "Project Manager"
                    if data.kind in {"request_support", "reject"}
                    else "Business Analyst",
                    "submitted_by": user.id,
                    "reason": reason,
                    **evidence,
                },
            )
        )
    project = session.get(m.Project, package.project_id)
    lifecycle = session.scalar(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == project.id,
            m.BusinessRecord.kind == "delivery_lifecycle",
        )
    )
    # A statement about an older version must not overwrite a newer preparation stage.
    if (
        lifecycle
        and lifecycle.data.get("package_id") == package.id
        and lifecycle.status == "awaiting_client_acceptance"
    ):
        if data.kind in {"accept", "reject", "request_changes", "report_defect"}:
            release.transition(
                session,
                project,
                "accepted" if data.kind == "accept" else "changes_requested",
                user.id,
                data.request_id,
                {"response_id": response_id},
            )
    packages.notify(
        session, package, "Client " + data.kind.replace("_", " ") + f" for delivery v{package.version}"
    )
    return result


def case_view(row):
    return {
        "id": row.id,
        "project_id": row.project_id,
        "status": row.status,
        "version": row.version,
        "created_at": row.created_at,
        "kind": row.data["kind"],
        "package_id": row.data["package_id"],
        "package_version": row.data["package_version"],
        "reason": row.data["reason"],
        "assigned_role": row.data["assigned_role"],
        "resolution": row.data.get("public_resolution"),
        **{
            key: row.data.get(key)
            for key in ("severity", "priority", "feature", "reproduction", "affected_criteria", "attachments")
        },
    }


def attachment(session, case, content_hash):
    response = session.get(m.DeliveryResponse, case.data.get("response_id"))
    if (
        not response
        or response.org_id != case.org_id
        or response.project_id != case.project_id
        or response.evidence.get("case_id") != case.id
    ):
        raise PermissionError("Client attachment source binding is invalid")
    reference = next(
        (row for row in response.evidence.get("attachments", []) if row["sha256"] == content_hash), None
    )
    if not reference:
        raise PermissionError("Client attachment is unavailable")
    package = session.get(m.DeliveryPackage, response.package_id)
    return packages.read_blob(package, reference)
