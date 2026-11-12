import hashlib
import json
import os
import re
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .db import now, session_dependency, uid
from .models import Agent, AuditEvent, AuthSession, Notification, Organization, Project, Requirement, User

password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def environment_secrets() -> tuple[str, ...]:
    return tuple(
        value
        for key, value in os.environ.items()
        if any(x in key for x in ("KEY", "TOKEN", "SECRET", "PASSWORD")) and len(value) > 7
    )


def redact(text: str, secrets: tuple[str, ...] | None = None) -> str:
    for value in environment_secrets() if secrets is None else secrets:
        text = text.replace(value, "[REDACTED]")
    text = re.sub(
        r"(?i)(api[_-]?key|password|secret|seed[_ ]phrase|private[_ ]key)\s*[:=]\s*[^\n,;]+",
        r"\1=[REDACTED]",
        text,
    )
    text = re.sub(
        r"\b(?:sk-[A-Za-z0-9_-]{16,}|gsk_[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,})\b",
        "[REDACTED]",
        text,
    )
    text = re.sub(
        r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    return text


def clean(value, secrets: tuple[str, ...] | None = None):
    secrets = environment_secrets() if secrets is None else secrets
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, dict):
        return {k: clean(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v, secrets) for v in value]
    return value


def audit(
    session: Session,
    org_id: str,
    actor: str,
    action: str,
    subject: str,
    detail=None,
    project_id=None,
    task_id=None,
    authorization="authenticated owner",
) -> None:
    # Locks the organization row on PostgreSQL; UPDATE obtains the SQLite write lock.
    session.execute(
        update(Organization).where(Organization.id == org_id).values(version=Organization.version + 1)
    )
    head = session.scalar(select(Organization.audit_head).where(Organization.id == org_id))
    payload = {
        "id": uid(),
        "org_id": org_id,
        "actor": actor,
        "action": action,
        "subject": subject,
        "detail": {
            **clean(detail or {}),
            "_history_position": session.scalar(
                select(Organization.version).where(Organization.id == org_id)
            ),
        },
        "created_at": now(),
        "previous_hash": head,
        "project_id": project_id,
        "task_id": task_id,
        "authorization": authorization,
    }
    event_hash = digest(payload)
    session.add(AuditEvent(**payload, event_hash=event_hash))
    session.execute(update(Organization).where(Organization.id == org_id).values(audit_head=event_hash))


def verify_audit(session: Session, org_id: str) -> dict:
    events = session.scalars(select(AuditEvent).where(AuditEvent.org_id == org_id)).all()
    by_previous = {event.previous_hash: event for event in events}
    head = "0" * 64
    count = 0
    while head in by_previous:
        event = by_previous.pop(head)
        payload = {
            column.name: getattr(event, column.name)
            for column in event.__table__.columns
            if column.name != "event_hash"
        }
        if digest(payload) != event.event_hash:
            return {"valid": False, "checked": count, "reason": "hash mismatch"}
        head = event.event_hash
        count += 1
    expected = session.scalar(select(Organization.audit_head).where(Organization.id == org_id))
    return {"valid": count == len(events) and head == expected, "checked": count, "head": head}


def token_for(user: User, session: Session) -> str:
    record = AuthSession(id=uid(), org_id=user.org_id, user_id=user.id, expires_at=now() + 3600)
    session.add(record)
    session.flush()
    return jwt.encode(
        {
            "sub": user.id,
            "jti": record.id,
            "iss": "ai-company-os",
            "aud": "company-web",
            "iat": now(),
            "exp": record.expires_at,
        },
        settings().jwt_secret,
        algorithm="HS256",
    )


def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: Session = Depends(session_dependency),
) -> User:
    if not credentials:
        raise HTTPException(401, "Authentication required")
    try:
        config = settings()
        if config.oidc_issuer:
            key = jwt.PyJWKClient(config.oidc_jwks_url, cache_keys=True).get_signing_key_from_jwt(
                credentials.credentials
            )
            claims = jwt.decode(
                credentials.credentials,
                key.key,
                algorithms=["RS256"],
                issuer=config.oidc_issuer,
                audience=config.oidc_audience,
                options={"require": ["exp", "sub"]},
            )
            user = session.scalar(select(User).where(User.oidc_subject == claims["sub"]))
        else:
            claims = jwt.decode(
                credentials.credentials,
                config.jwt_secret,
                algorithms=["HS256"],
                issuer="ai-company-os",
                audience="company-web",
                options={"require": ["exp", "sub", "jti"]},
            )
            user = session.get(User, claims["sub"])
            record = session.get(AuthSession, claims["jti"])
            if (
                not record
                or record.user_id != claims["sub"]
                or (user and record.org_id != user.org_id)
                or record.revoked_at
                or record.expires_at <= now()
            ):
                raise HTTPException(401, "Session expired or revoked")
            request.state.auth_session_id = record.id
        request.state.auth_expires_at = int(claims["exp"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired authentication") from None
    if not user or not user.enabled:
        raise HTTPException(401, "Identity is disabled or not provisioned")
    return user


def owner(user: User = Depends(current_user), session: Session = Depends(session_dependency)) -> User:
    if user.role != "owner":
        audit(session, user.org_id, user.id, "owner_access.denied", user.id, authorization="RBAC rejection")
        session.commit()
        raise HTTPException(403, "Owner permission required")
    return user


def scoped(session: Session, model, record_id: str, user: User):
    row = session.scalar(select(model).where(model.id == record_id, model.org_id == user.org_id))
    if not row:
        raise HTTPException(404, "Record not found")
    if user.role != "owner":
        if getattr(row, "conversation_id", None):
            raise HTTPException(404, "Record not found")
        if isinstance(row, (Project, Requirement)) and row.client_id != user.client_id:
            raise HTTPException(404, "Record not found")
        if isinstance(row, Project):
            from .client_access import grant_for

            try:
                grant_for(session, user, row.id)
            except PermissionError:
                raise HTTPException(404, "Record not found") from None
        if isinstance(row, Requirement):
            from .client_access import requirement_allowed

            if not requirement_allowed(session, user, row):
                raise HTTPException(404, "Record not found")
        if hasattr(row, "project_id") and row.project_id:
            scoped(session, Project, row.project_id, user)
    return row


def check_agent(session: Session, agent: Agent, tool: str, project: Project | None = None) -> None:
    org = session.get(Organization, agent.org_id)
    reason = None
    if org.paused or not agent.enabled:
        reason = "Company or agent paused"
    elif tool not in agent.tools:
        reason = "Tool permission denied"
    elif project and (project.org_id != agent.org_id or project.status != "active"):
        reason = "Project is outside authorization scope or paused"
    if reason:
        audit(
            session,
            agent.org_id,
            agent.id,
            "policy.denied",
            tool,
            {"reason": reason},
            project_id=project.id if project else None,
            authorization="server agent policy",
        )
        session.add(Notification(org_id=agent.org_id, severity="warning", title=reason, subject_id=agent.id))
        session.commit()
        raise PermissionError(reason)


def validate_endpoint(url: str, allowed: str, local_allowed=False) -> str:
    parts = urlsplit(url)
    hosts = {x.strip() for x in allowed.split(",")}
    if parts.username or parts.password or parts.query or parts.fragment or parts.hostname not in hosts:
        raise ValueError("Endpoint must use an explicitly allowed host and contain no credentials/query")
    if parts.scheme != "https" and not (
        local_allowed and parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1"}
    ):
        raise ValueError("HTTPS required except explicitly local endpoints")
    return url.rstrip("/")
