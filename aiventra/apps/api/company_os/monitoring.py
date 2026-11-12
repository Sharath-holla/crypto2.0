from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import now
from .models import BusinessRecord, ModelRun, Notification, Workflow
from .security import audit


def inspect(session: Session, org_id: str) -> list[dict]:
    findings = []
    for workflow in session.scalars(
        select(Workflow).where(Workflow.org_id == org_id, Workflow.status.in_(["running", "needs_attention"]))
    ):
        if workflow.status == "needs_attention" or workflow.deadline_at < now():
            findings.append(
                {
                    "subject_id": workflow.id,
                    "severity": "error",
                    "title": workflow.last_error or "Workflow deadline exceeded",
                }
            )
    for run in session.scalars(
        select(ModelRun).where(ModelRun.org_id == org_id, ModelRun.status.in_(["started", "uncertain"]))
    ):
        if run.status == "uncertain" or now() - run.created_at > 180:
            findings.append(
                {
                    "subject_id": run.id,
                    "severity": "warning",
                    "title": "Provider usage needs reconciliation; reservation retained",
                }
            )
    for finding in findings:
        exists = session.scalar(
            select(Notification).where(
                Notification.org_id == org_id,
                Notification.subject_id == finding["subject_id"],
                Notification.title == finding["title"][:200],
            )
        )
        if not exists:
            session.add(Notification(org_id=org_id, **{**finding, "title": finding["title"][:200]}))
            session.add(
                BusinessRecord(org_id=org_id, kind="incident", title=finding["title"][:200], data=finding)
            )
            audit(
                session,
                org_id,
                "independent-watchdog",
                "watchdog.alert",
                finding["subject_id"],
                finding,
                authorization="independent owner reporting",
            )
    session.commit()
    return findings
