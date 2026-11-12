from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import models as m
from ..db import session_dependency
from ..history import project_events
from ..security import owner, scoped

router = APIRouter()


@router.get("/projects/{record_id}/history")
def history(
    record_id: str,
    before: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=20, ge=1, le=50),
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    return project_events(session, scoped(session, m.Project, record_id, user), before, limit)


@router.get("/tasks/{record_id}/history")
def task_history(
    record_id: str,
    before: str | None = Query(default=None, max_length=1024),
    limit: int = Query(default=20, ge=1, le=50),
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    task = scoped(session, m.Task, record_id, user)
    return project_events(session, scoped(session, m.Project, task.project_id, user), before, limit, task)
