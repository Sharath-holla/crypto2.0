"""Local sessions and atomic, restart-persistent authentication limits."""

import hashlib

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .config import settings
from .db import now
from .models import LoginThrottle


def count_attempt(session: Session, key: str) -> int:
    moment = now()
    insert = sqlite_insert if session.bind.dialect.name == "sqlite" else pg_insert
    statement = insert(LoginThrottle).values(
        key_hash=hashlib.sha256(key.encode()).hexdigest(),
        attempts=1,
        resets_at=moment + settings().login_window_seconds,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[LoginThrottle.key_hash],
        set_={
            "attempts": case((LoginThrottle.resets_at <= moment, 1), else_=LoginThrottle.attempts + 1),
            "resets_at": case(
                (LoginThrottle.resets_at <= moment, moment + settings().login_window_seconds),
                else_=LoginThrottle.resets_at,
            ),
        },
    ).returning(LoginThrottle.attempts)
    return session.scalar(statement)
