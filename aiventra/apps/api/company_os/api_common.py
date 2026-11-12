from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .security import clean


def serialize(row, secrets=None):
    return clean(
        {
            column.name: getattr(row, column.name)
            for column in row.__table__.columns
            if column.name not in {"password_hash", "audit_head", "ciphertext"}
        },
        secrets,
    )


def tenant_rows(session: Session, model, user: m.User, limit=500):
    statement = select(model).where(model.org_id == user.org_id)
    if model is m.BusinessRecord:
        # Operational receipts have a scoped evidence endpoint; do not crowd
        # approvals, drafts and business records out of the bounded dashboard.
        statement = statement.where(
            model.kind != "invocation_receipt", ~model.kind.like("quality_%"), ~model.kind.like("devops_%")
        )
    return session.scalars(statement.order_by(model.created_at.desc(), model.id.desc()).limit(limit)).all()
