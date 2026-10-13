"""Scoped keyset history; immutable event positions survive database/service restarts."""

import base64
import hashlib
import hmac
import json

from fastapi import HTTPException
from sqlalchemy import func, or_, select, tuple_

from . import models as m
from .api_common import serialize
from .config import settings
from .security import environment_secrets


def cursor(scope, point):
    payload = base64.urlsafe_b64encode(json.dumps([scope, point], separators=(",", ":")).encode()).decode()
    signature = hmac.new(settings().jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload + "." + signature


def decode(value, scope):
    try:
        payload, signature = value.split(".")
        expected = hmac.new(settings().jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        saved_scope, point = json.loads(base64.urlsafe_b64decode(payload))
        if not hmac.compare_digest(signature, expected) or saved_scope != scope:
            raise ValueError()
        if (
            not isinstance(point, list)
            or len(point) != 3
            or not all(isinstance(item, int) for item in point[:2])
        ):
            raise ValueError()
        if not isinstance(point[2], str) or len(point[2]) > 36:
            raise ValueError()
        return point
    except (ValueError, TypeError, UnicodeError):
        raise HTTPException(422, "Invalid history cursor for this scope") from None


def project_events(session, project, before, limit, task=None):
    scope = f"{project.org_id}:project:{project.id}" + (f":task:{task.id}" if task else "")
    query = select(m.AuditEvent).where(
        m.AuditEvent.org_id == project.org_id, m.AuditEvent.project_id == project.id
    )
    if task:
        query = query.where(or_(m.AuditEvent.task_id == task.id, m.AuditEvent.subject == task.id))
    # Organization.version is incremented under the existing database write lock by audit().
    # Older immutable events retain position zero, ordered by their historical timestamp/ID.
    position = func.coalesce(m.AuditEvent.detail["_history_position"].as_integer(), 0)
    if before:
        sequence, stamp, identity = decode(before, scope)
        query = query.where(
            tuple_(position, m.AuditEvent.created_at, m.AuditEvent.id) < tuple_(sequence, stamp, identity)
        )
    rows = list(
        session.scalars(
            query.order_by(position.desc(), m.AuditEvent.created_at.desc(), m.AuditEvent.id.desc()).limit(
                limit + 1
            )
        )
    )
    page = rows[:limit]
    secrets = environment_secrets()
    return {
        "items": [serialize(row, secrets) for row in page],
        "next_cursor": cursor(
            scope, [page[-1].detail.get("_history_position", 0), page[-1].created_at, page[-1].id]
        )
        if len(rows) > limit
        else None,
    }
