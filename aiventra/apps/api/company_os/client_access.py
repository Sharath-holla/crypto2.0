"""Invitation-only identities and explicitly granted, released client views."""

import json
import secrets

from sqlalchemy import select

from . import models as m
from . import packages, release
from .api_common import serialize
from .config import settings
from .db import now, uid
from .security import audit, password_hasher, token_for


def grant_for(session, user, project_id, respond=False):
    project = session.get(m.Project, project_id)
    grant = session.scalar(
        select(m.ClientAccessGrant).where(
            m.ClientAccessGrant.org_id == user.org_id,
            m.ClientAccessGrant.project_id == project_id,
            m.ClientAccessGrant.user_id == user.id,
            m.ClientAccessGrant.revoked_at.is_(None),
        )
    )
    if (
        user.role != "client"
        or not project
        or project.org_id != user.org_id
        or project.client_id != user.client_id
        or not grant
        or grant.client_id != user.client_id
        or (respond and not grant.can_respond)
    ):
        raise PermissionError("Client project permission is unavailable")
    invitation = session.get(m.ClientInvitation, grant.invitation_id)
    if (
        not invitation
        or invitation.org_id != user.org_id
        or invitation.revoked_at
        or invitation.project_id != project.id
        or invitation.client_id != user.client_id
        or not invitation.redeemed_at
        or invitation.redeemed_by != user.id
        or (respond and not invitation.can_respond)
    ):
        raise PermissionError("Client invitation grant is revoked or invalid")
    return grant


def invitation_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "project_id",
            "client_id",
            "email",
            "created_at",
            "expires_at",
            "redeemed_at",
            "redeemed_by",
            "revoked_at",
            "can_respond",
        )
    }


def requirement_allowed(session, user, requirement):
    if requirement.client_id != user.client_id:
        return False
    if session.scalar(
        select(m.AuditEvent.id).where(
            m.AuditEvent.org_id == user.org_id,
            m.AuditEvent.actor == user.id,
            m.AuditEvent.action == "requirement.submitted",
            m.AuditEvent.subject == requirement.id,
        )
    ):
        return True
    for project in session.scalars(
        select(m.Project)
        .join(m.Proposal, m.Proposal.id == m.Project.proposal_id)
        .where(m.Project.org_id == user.org_id, m.Proposal.requirement_id == requirement.id)
    ):
        try:
            grant_for(session, user, project.id)
            return True
        except PermissionError:
            continue
    return False


def requirement_view(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "org_id",
            "client_id",
            "created_at",
            "title",
            "text",
            "version",
            "status",
            "answers",
            "deadline",
        )
    }


def create_invitation(session, project, user, email, request_id, request_hash, ttl, can_respond):
    previous = session.scalar(
        select(m.ClientInvitation).where(
            m.ClientInvitation.org_id == user.org_id, m.ClientInvitation.request_id == str(request_id)
        )
    )
    if previous:
        if previous.request_hash != request_hash:
            raise PermissionError("Invitation request ID is already used for different scope")
        return {
            "invitation": invitation_view(previous),
            "token": None,
            "message": "Secret invitation token is shown only once; revoke and create another if lost",
        }
    if session.get(m.BusinessRecord, str(request_id)):
        raise PermissionError("Invitation request ID is already used for another delivery command")
    existing = session.scalar(select(m.User).where(m.User.email == email))
    if existing and (
        existing.org_id != user.org_id
        or existing.role != "client"
        or existing.client_id != project.client_id
        or not existing.enabled
    ):
        raise PermissionError("Email cannot be invited into this client scope")
    token = secrets.token_urlsafe(32)
    invitation = m.ClientInvitation(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        client_id=project.client_id,
        owner_id=user.id,
        email=email,
        token_hash=packages.sha(token.encode()),
        request_id=str(request_id),
        request_hash=request_hash,
        expires_at=now() + ttl,
        can_respond=can_respond,
    )
    session.add(invitation)
    session.flush()
    # The raw token never enters a record, notification, log or workflow result.
    release.complete_command(
        session,
        user,
        request_id,
        request_hash,
        project.id,
        "delivery.invitation_created",
        {"id": invitation.id, "expires_at": invitation.expires_at},
    )
    return {
        "invitation": invitation_view(invitation),
        "token": token,
        "message": "Share privately with the intended recipient. No email was sent.",
    }


def redeem(session, token, email, password):
    if settings().oidc_issuer:
        raise PermissionError("Local invitation password redemption is disabled under configured OIDC")
    invitation = session.scalar(
        select(m.ClientInvitation).where(m.ClientInvitation.token_hash == packages.sha(token.encode()))
    )
    if (
        not invitation
        or invitation.email != email
        or invitation.revoked_at
        or invitation.redeemed_at
        or invitation.expires_at <= now()
    ):
        raise PermissionError("Invitation is invalid, expired, revoked or already used")
    from .staffing import lock_org

    lock_org(session, invitation.org_id)
    session.expire_all()
    if invitation.revoked_at or invitation.redeemed_at or invitation.expires_at <= now():
        raise PermissionError("Invitation is invalid, expired, revoked or already used")
    project = session.get(m.Project, invitation.project_id)
    owner = session.get(m.User, invitation.owner_id)
    if (
        not project
        or project.org_id != invitation.org_id
        or project.client_id != invitation.client_id
        or not owner
        or owner.org_id != invitation.org_id
        or not owner.enabled
        or owner.role != "owner"
    ):
        raise PermissionError("Invitation authority is no longer valid")
    user = session.scalar(select(m.User).where(m.User.email == email))
    if user:
        if (
            user.org_id != invitation.org_id
            or user.client_id != invitation.client_id
            or user.role != "client"
            or not user.enabled
            or not user.password_hash
        ):
            raise PermissionError("Invitation identity cannot redeem this scope")
        from pwdlib.exceptions import UnknownHashError

        try:
            valid = password_hasher.verify(password, user.password_hash)
        except UnknownHashError:
            valid = False
        if not valid:
            raise PermissionError("Existing client account requires its current password")
    else:
        user = m.User(
            id=uid(),
            org_id=invitation.org_id,
            client_id=invitation.client_id,
            email=email,
            role="client",
            password_hash=password_hasher.hash(password),
        )
        session.add(user)
        session.flush()
    grant = session.scalar(
        select(m.ClientAccessGrant).where(
            m.ClientAccessGrant.org_id == user.org_id,
            m.ClientAccessGrant.user_id == user.id,
            m.ClientAccessGrant.project_id == project.id,
        )
    )
    if not grant:
        grant = m.ClientAccessGrant(
            id=uid(),
            org_id=user.org_id,
            client_id=user.client_id,
            user_id=user.id,
            project_id=project.id,
            invitation_id=invitation.id,
        )
        session.add(grant)
    grant.invitation_id, grant.revoked_at, grant.can_respond = invitation.id, None, invitation.can_respond
    invitation.redeemed_at, invitation.redeemed_by = now(), user.id
    session.flush()
    audit(
        session,
        user.org_id,
        user.id,
        "delivery.invitation_redeemed",
        invitation.id,
        {"project_id": project.id, "grant_id": grant.id},
        project_id=project.id,
        authorization="single-use scoped owner invitation",
    )
    access_token = token_for(user, session)
    session.commit()
    return {"access_token": access_token, "token_type": "bearer", "user": serialize(user)}


def released_package(session, user, package_id, respond=False):
    package = session.get(m.DeliveryPackage, package_id)
    if (
        not package
        or package.org_id != user.org_id
        or package.client_id != user.client_id
        or package.classification != "live_reviewed"
        or package.status not in {"released", "superseded"}
        or user.id not in package.manifest.get("recipient_ids", [])
    ):
        raise PermissionError("Released delivery package is unavailable")
    grant_for(session, user, package.project_id, respond)
    packages.integrity(session, package)
    # Multiple released versions retain immutable separate release proofs.
    proofs = session.scalars(
        select(m.BusinessRecord).where(
            m.BusinessRecord.org_id == user.org_id,
            m.BusinessRecord.project_id == package.project_id,
            m.BusinessRecord.kind == "delivery_release",
            m.BusinessRecord.status == "released",
        )
    )
    proof = next(
        (
            row
            for row in proofs
            if row.data.get("package_id") == package.id
            and row.data.get("manifest_hash") == package.manifest_hash
        ),
        None,
    )
    if not proof:
        raise PermissionError("Package has no exact persisted release authorization")
    approval = session.get(m.Approval, proof.data.get("approval_id"))
    if (
        not approval
        or approval.org_id != user.org_id
        or approval.category != "delivery_release"
        or approval.subject_id != package.id
        or approval.version != package.version
        or approval.subject_hash != package.manifest_hash
        or approval.selection != "approve"
        or approval.expires_at <= proof.data["released_at"]
    ):
        raise PermissionError("Saved release approval evidence is invalid")
    return package, proof


def public_view(session, package, proof):
    from .client_responses import response_view

    manifest = package.manifest
    source = next(row for row in manifest["files"] if row["purpose"] == "internal_evidence")
    criteria = json.loads(packages.read_blob(package, source))["acceptance"]
    responses = list(
        session.scalars(
            select(m.DeliveryResponse)
            .where(m.DeliveryResponse.org_id == package.org_id, m.DeliveryResponse.package_id == package.id)
            .order_by(m.DeliveryResponse.created_at, m.DeliveryResponse.id)
        )
    )
    # Explicit disclosure allowlist; never serialize the full internal manifest,
    # source documents, prompts, security findings, run traces or engineering logs.
    return {
        "id": package.id,
        "project_id": package.project_id,
        "project_name": manifest["project_name"],
        "version": package.version,
        "status": package.status,
        "manifest_hash": package.manifest_hash,
        "summary": manifest["summary"],
        "release_notes": manifest["release_notes"],
        "test_summary": manifest["test_summary"],
        "limitations": manifest["limitations"],
        "known_issues": manifest["known_issues"],
        "deployment": manifest["deployment"],
        "released_at": proof.data["released_at"],
        "acceptance_deadline": manifest.get("acceptance_deadline"),
        "acceptance_criteria": criteria,
        "files": [file for file in manifest["files"] if file["client_visible"]],
        "repositories": [
            {
                "repository_id": row["repository_id"],
                "source_commit": row["source_commit"],
                "tree": row["tree"],
                "pull_requests": [
                    {"status": ref["status"], **ref["pull_request"]} for ref in row["pull_requests"]
                ],
            }
            for row in manifest["repositories"]
        ],
        "responses": [response_view(row) for row in responses],
    }
