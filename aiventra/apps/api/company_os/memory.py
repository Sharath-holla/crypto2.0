from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Artifact, BusinessRecord, Project
from .security import clean


def retrieve(session: Session, org_id: str, project_id: str, query: str = "", limit: int = 5) -> list[dict]:
    project = session.get(Project, project_id)
    if not project or project.org_id != org_id:
        raise PermissionError("Memory project scope denied")
    candidates = []
    for record in session.scalars(
        select(BusinessRecord).where(
            BusinessRecord.org_id == org_id,
            BusinessRecord.project_id == project_id,
            BusinessRecord.kind == "knowledge",
        )
    ).all():
        content = str(record.data)
        if query.lower() in (record.title + " " + content).lower():
            candidates.append(
                {
                    "id": record.id,
                    "kind": "knowledge",
                    "title": record.title,
                    "excerpt": content[:4000],
                    "trust": "untrusted stored knowledge",
                }
            )
    for artifact in session.scalars(
        select(Artifact)
        .where(
            Artifact.org_id == org_id,
            Artifact.project_id == project_id,
            Artifact.conversation_id.is_(None),
            Artifact.kind != "retired_requirement_attachment",
        )
        .order_by(Artifact.created_at.desc())
        .limit(20)
    ).all():
        if query.lower() in (artifact.name + " " + artifact.content).lower():
            candidates.append(
                {
                    "id": artifact.id,
                    "kind": artifact.kind,
                    "title": artifact.name,
                    "excerpt": artifact.content[:4000],
                    "sha256": artifact.sha256,
                    "trust": "artifact evidence; verify claims independently",
                }
            )
    return clean(candidates[:limit])
