"""Owner-scoped read-only readiness and invocation evidence."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models as m
from .. import readiness
from ..db import session_dependency
from ..project_setup import owned
from ..security import clean, owner, scoped

router = APIRouter()


@router.get("/ai-readiness")
def overview(user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return clean(readiness.overview(session, user.org_id))


@router.get("/projects/{project_id}/execution-evidence")
def project(project_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    return clean(readiness.project_view(session, scoped(session, m.Project, project_id, user)))


@router.get("/project-drafts/{draft_id}/execution-evidence")
def draft(draft_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)):
    from fastapi import HTTPException

    try:
        record = owned(session, draft_id, user)
    except PermissionError:
        raise HTTPException(404, "Project draft is unavailable") from None
    return clean(readiness.project_view(session, None, record))
