from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from .. import models as m
from ..api_common import serialize
from ..db import now, session_dependency, uid
from ..organization import agent_for
from ..repositories import discover, safe_repository
from ..repository_imports import discover as discover_github
from ..repository_imports import repository_name
from ..schemas import (
    CodingTaskInput,
    Strict,
)
from ..security import (
    audit,
    clean,
    current_user,
    digest,
    owner,
    scoped,
)

router = APIRouter()


@router.post("/executions/{record_id}/reconcile")
async def reconcile_execution(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    from ..sandbox import stored_result

    execution = scoped(session, m.Execution, record_id, user)
    if execution.status != "running":
        raise HTTPException(409, "Execution is already recorded")
    try:
        result = await stored_result(execution.id)
    except Exception:
        raise HTTPException(
            409, "Runner result unavailable; retain interrupted execution for investigation"
        ) from None
    if result.get("status") not in {"completed", "interrupted"}:
        raise HTTPException(409, "Runner job is still active")
    execution.status = "interrupted" if result["status"] == "interrupted" else "completed"
    execution.exit_code, execution.ended_at = result["exit_code"], now()
    execution.command, execution.environment = result["command"], result["environment"]
    execution.logs = clean(str(result.get("build", {}).get("logs", "")) + "\n" + str(result["logs"]))[:500100]
    audit(
        session,
        user.org_id,
        user.id,
        "runner.execution_reconciled",
        execution.id,
        {"exit_code": execution.exit_code},
        task_id=execution.task_id,
    )
    session.commit()
    return serialize(execution)


class SpecialistTaskInput(Strict):
    agent_id: str
    objective: str = Field(min_length=10, max_length=10000)
    acceptance: list[str] = Field(min_length=1, max_length=20)
    mode: str = Field(pattern="^(mock|live)$", default="live")
    budget_micro: int = Field(ge=0, le=10**10, default=500000)


@router.post("/projects/{record_id}/tasks", status_code=201)
def specialist_task(
    record_id: str,
    data: SpecialistTaskInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    agent = scoped(session, m.Agent, data.agent_id, user)
    from ..security import check_agent
    from ..workflows import project_authority

    try:
        project_authority(session, project)
        check_agent(session, agent, "write_artifact", project)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    task = m.Task(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        assigned_agent_id=agent.id,
        objective=clean(data.objective),
        acceptance=clean(data.acceptance),
        kind="document",
        payload={"mode": data.mode},
        budget_micro=data.budget_micro,
    )
    session.add(task)
    session.add(m.Budget(org_id=user.org_id, scope=f"task:{task.id}", limit_micro=data.budget_micro))
    audit(
        session,
        user.org_id,
        user.id,
        "specialist.task_assigned",
        task.id,
        {"agent": agent.id},
        project_id=project.id,
        task_id=task.id,
    )
    session.commit()
    return serialize(task)


@router.post("/tasks/{record_id}/cancel")
def cancel_task(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    task = scoped(session, m.Task, record_id, user)
    task.status = "cancelled"
    session.execute(
        update(m.Workflow).where(m.Workflow.task_id == task.id).values(status="cancelled", lease_token=uid())
    )
    audit(
        session, user.org_id, user.id, "task.cancelled", task.id, project_id=task.project_id, task_id=task.id
    )
    session.commit()
    return serialize(task)


class RepositoryInput(Strict):
    project_id: str
    name: str = Field(min_length=1, max_length=200)
    relative_path: str = Field(min_length=1, max_length=500)


class GitHubImport(Strict):
    request_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    repository: str = Field(min_length=3, max_length=240)
    branch: str | None = Field(default=None, max_length=100)


@router.post("/projects/{record_id}/github-import", status_code=201)
async def import_github(
    record_id: str,
    data: GitHubImport,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    import json

    from ..artifacts import save_artifact
    from ..staffing import lock_org
    from ..workflows import project_authority

    project = scoped(session, m.Project, record_id, user)
    try:
        project_authority(session, project)
        repository = repository_name(data.repository)
        fingerprint = digest({"project_id": project.id, "repository": repository, "branch": data.branch})
        existing = session.get(m.BusinessRecord, data.request_id)
        if existing:
            if existing.org_id != user.org_id or existing.kind != "github_repository_import":
                raise HTTPException(404, "Import not found")
            if existing.data["request_hash"] != fingerprint:
                raise HTTPException(409, "Import request already used for different scope")
            return serialize(session.get(m.Repository, existing.data["repository_id"]))
        session.commit()  # No database write lock spans GitHub HTTP.
        report = await discover_github(repository, data.branch)
        lock_org(session, user.org_id)
        session.expire_all()
        project = scoped(session, m.Project, record_id, user)
        project_authority(session, project)
        session.refresh(user)
        if not user.enabled or user.role != "owner":
            raise PermissionError("Import owner authority revoked")
        from ..publication import GitHub

        GitHub(repository)  # Recheck connector allowlist/credential availability after HTTP.
        # A concurrent retry may have committed while HTTP was in flight.
        existing = session.get(m.BusinessRecord, data.request_id)
        if existing:
            if (
                existing.org_id != user.org_id
                or existing.kind != "github_repository_import"
                or existing.data["request_hash"] != fingerprint
            ):
                raise HTTPException(409, "Concurrent import scope conflict")
            return serialize(session.get(m.Repository, existing.data["repository_id"]))
        artifact = save_artifact(
            session,
            user.org_id,
            "GitHub read-only architecture findings",
            json.dumps(clean(report), ensure_ascii=False),
            "repository_analysis",
            project_id=project.id,
        )
        row = m.Repository(
            id=uid(),
            org_id=user.org_id,
            project_id=project.id,
            name=repository + " · " + report["branch"],
            path="github://" + repository,
            baseline_commit=report["baseline_commit"],
            report={**clean(report), "artifact_id": artifact.id},
        )
        session.add(row)
        session.flush()
        session.add(
            m.BusinessRecord(
                id=data.request_id,
                org_id=user.org_id,
                project_id=project.id,
                client_id=project.client_id,
                kind="github_repository_import",
                title="Read-only GitHub import",
                status="recorded",
                data={"request_hash": fingerprint, "repository_id": row.id, "artifact_id": artifact.id},
            )
        )
        audit(
            session,
            user.org_id,
            user.id,
            "repository.github_discovered",
            row.id,
            {"commit": row.baseline_commit, "read_only": True},
            project_id=project.id,
        )
        session.commit()
        return serialize(row)
    except (ValueError, PermissionError) as exc:
        session.rollback()
        raise HTTPException(422, str(exc)) from None


@router.post("/repositories", status_code=201)
def import_repository(
    data: RepositoryInput, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    scoped(session, m.Project, data.project_id, user)
    try:
        path = safe_repository(data.relative_path)
        report = discover(path)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(422, str(exc)) from None
    repository = m.Repository(
        id=uid(),
        org_id=user.org_id,
        project_id=data.project_id,
        name=data.name,
        path=str(path),
        report=report,
        baseline_commit=report["baseline_commit"],
    )
    session.add(repository)
    audit(
        session,
        user.org_id,
        user.id,
        "repository.discovered",
        repository.id,
        {"read_only": True},
        project_id=data.project_id,
    )
    session.commit()
    return serialize(repository)


@router.post("/projects/{record_id}/coding", status_code=201)
def coding_task(
    record_id: str,
    data: CodingTaskInput,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    project = scoped(session, m.Project, record_id, user)
    repository = scoped(session, m.Repository, data.repository_id, user)
    if repository.project_id != project.id:
        raise HTTPException(422, "Repository belongs to a different project")
    if repository.report.get("remote_metadata_only"):
        raise HTTPException(
            409, "Read-only GitHub analysis requires a separate managed checkout before coding"
        )
    task = m.Task(
        id=uid(),
        org_id=user.org_id,
        project_id=project.id,
        assigned_agent_id=agent_for(session, user.org_id, "Backend Developer").id,
        objective=data.objective,
        acceptance=data.acceptance,
        kind="coding",
        status="awaiting_approval",
        payload={
            "repository_id": repository.id,
            "baseline_commit": repository.baseline_commit,
            "objective": data.objective,
            "test_suite": data.test_suite,
            "mode": data.mode,
            "review_policy": data.review_policy,
            "review_count": data.review_count,
            "repair_limit": data.repair_limit,
        },
        budget_micro=data.budget_micro,
    )
    session.add(task)
    session.add(m.Budget(org_id=user.org_id, scope=f"task:{task.id}", limit_micro=data.budget_micro))
    audit(session, user.org_id, user.id, "coding.requested", task.id, project_id=project.id, task_id=task.id)
    session.commit()
    return {**serialize(task), "approval_hash": digest(task.payload)}


class HashApproval(Strict):
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class CodingScope(Strict):
    repository_id: str
    test_suite: str = Field(pattern="^(python-unittest|node-test)$")
    review_policy: str = Field(
        pattern="^(prefer_provider|require_provider|require_model)$", default="prefer_provider"
    )
    review_count: int = Field(ge=1, le=2, default=1)
    repair_limit: int = Field(ge=0, le=2, default=1)


@router.get("/tasks/{record_id}/coding-scope")
def coding_scope(
    record_id: str, user: m.User = Depends(owner), session: Session = Depends(session_dependency)
):
    task = scoped(session, m.Task, record_id, user)
    if task.kind != "coding":
        raise HTTPException(422, "Coding task required")
    return {**serialize(task), "approval_hash": digest(task.payload)}


@router.post("/tasks/{record_id}/coding-scope")
def bind_coding_scope(
    record_id: str,
    data: CodingScope,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    from ..staffing import lock_org, task_plan

    lock_org(session, user.org_id)
    task = scoped(session, m.Task, record_id, user)
    plan = task_plan(session, task)
    if task.kind != "coding" or task.status != "awaiting_repository" or not plan or plan.status != "active":
        raise HTTPException(409, "Active allocated coding task awaiting repository required")
    repository = scoped(session, m.Repository, data.repository_id, user)
    if repository.project_id != task.project_id:
        raise HTTPException(422, "Repository belongs to another project")
    if repository.report.get("remote_metadata_only"):
        raise HTTPException(
            409, "Read-only GitHub analysis requires a separate managed checkout before coding"
        )
    task.payload = {
        **task.payload,
        **data.model_dump(),
        "baseline_commit": repository.baseline_commit,
        "objective": task.objective,
    }
    task.status, task.version = "awaiting_approval", task.version + 1
    audit(
        session,
        user.org_id,
        user.id,
        "coding.scope_bound",
        task.id,
        project_id=task.project_id,
        task_id=task.id,
    )
    session.commit()
    return {**serialize(task), "approval_hash": digest(task.payload)}


@router.post("/tasks/{record_id}/approve")
def approve_coding(
    record_id: str,
    data: HashApproval,
    user: m.User = Depends(owner),
    session: Session = Depends(session_dependency),
):
    from ..staffing import lock_org, task_plan

    lock_org(session, user.org_id)
    task = scoped(session, m.Task, record_id, user)
    plan = task_plan(session, task)
    if plan and plan.status != "active":
        raise HTTPException(409, "Staffing plan must be active")
    if (
        task.kind != "coding"
        or task.status != "awaiting_approval"
        or data.content_hash != digest(task.payload)
    ):
        raise HTTPException(409, "Invalid or stale coding scope")
    approval = m.Approval(
        id=uid(),
        org_id=user.org_id,
        category="repository_change",
        subject_id=task.id,
        subject_hash=data.content_hash,
        version=task.version,
        owner_id=user.id,
        expires_at=now() + 604800,
    )
    session.add(approval)
    task.status = "in_progress"
    session.add(m.Workflow(org_id=user.org_id, task_id=task.id, kind="coding", mode=task.payload["mode"]))
    audit(
        session,
        user.org_id,
        user.id,
        "coding.approved",
        task.id,
        project_id=task.project_id,
        task_id=task.id,
        authorization=f"approval:{approval.id}",
    )
    session.commit()
    return serialize(task)


@router.get("/artifacts/{record_id}")
def artifact_detail(
    record_id: str, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    if user.role != "owner":
        raise HTTPException(404, "Artifact not found")
    artifact = scoped(session, m.Artifact, record_id, user)
    return serialize(artifact)


@router.post("/projects/{record_id}/deploy")
def deploy(
    record_id: str, user: m.User = Depends(current_user), session: Session = Depends(session_dependency)
):
    project = scoped(session, m.Project, record_id, user)
    audit(
        session,
        user.org_id,
        user.id,
        "deployment.denied",
        project.id,
        {"reason": "No verified deployment connector and environment approval"},
        project_id=project.id,
        authorization="policy rejection",
    )
    session.add(
        m.Notification(
            org_id=user.org_id,
            severity="warning",
            title="Deployment blocked: connector and environment approval required",
            subject_id=project.id,
        )
    )
    session.commit()
    raise HTTPException(
        403,
        "Deployment requires a configured connector, verified QA evidence and environment-specific owner approval",
    )
