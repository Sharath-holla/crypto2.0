import asyncio
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifacts import save_artifact
from .config import settings
from .db import now, uid
from .gateway import execute
from .models import (
    Agent,
    Approval,
    BusinessRecord,
    Execution,
    ModelConfig,
    ModelRun,
    Notification,
    Project,
    Provider,
    Repository,
    Task,
    Workflow,
    WorkflowStep,
)
from .organization import agent_for
from .providers import model_identity, provider_identity
from .repositories import apply_files, git, source_context, worktree
from .sandbox import cancel_job, run_tests
from .schemas import PatchResult, ReviewResult
from .security import audit, check_agent, digest
from .workflows import checkpoint, project_authority


def passed_tests(result: dict, suite: str) -> bool:
    pattern = r"^Ran (\d+) tests?\b" if suite == "python-unittest" else r"^# tests (\d+)\b"
    counts = re.findall(pattern, result["logs"], re.MULTILINE)
    return (
        result["exit_code"] == 0
        and result.get("build", {}).get("exit_code", 0) == 0
        and bool(counts)
        and int(counts[-1]) > 0
    )


def round_name(name: str, repair_round: int) -> str:
    return name + (f"_r{repair_round}" if repair_round else "")


def candidate_tree(workspace: Path) -> str:
    git(workspace, "add", "-A")
    return git(workspace, "write-tree")


async def qa_execution(
    session: Session, workflow: Workflow, task: Task, qa: Agent, workspace: Path, token: str
) -> tuple[Execution, dict]:
    if session.scalar(
        select(Execution.id).where(
            Execution.task_id == task.id, Execution.status.in_(["running", "interrupted"])
        )
    ):
        raise PermissionError("Interrupted test execution requires owner reconciliation")
    execution = Execution(
        id=uid(),
        org_id=workflow.org_id,
        task_id=task.id,
        agent_id=qa.id,
        workspace=str(workspace),
        command=[task.payload["test_suite"]],
        environment="dedicated Docker broker",
        commit_hash=task.evidence["baseline_commit"],
    )
    session.add(execution)
    session.commit()
    call = asyncio.create_task(run_tests(workspace, task.payload["test_suite"], job_id=execution.id))
    try:
        while not call.done():
            await asyncio.wait({call}, timeout=1)
            with Session(session.get_bind()) as control_session:
                current = control_session.execute(
                    select(Workflow.status, Workflow.lease_token).where(Workflow.id == workflow.id)
                ).one()
            if current.status != "running" or current.lease_token != token:
                await cancel_job(execution.id)
                break
        result = await call
    except asyncio.CancelledError:
        call.cancel()
        await asyncio.gather(call, return_exceptions=True)
        await cancel_job(execution.id)
        raise
    execution.status = "interrupted" if result.get("status") == "interrupted" else "completed"
    execution.exit_code, execution.ended_at = result["exit_code"], now()
    execution.logs = (
        "Build exit "
        + str(result.get("build", {}).get("exit_code", "contract adapter"))
        + "\n"
        + str(result.get("build", {}).get("logs", ""))
        + "\n"
        + result["logs"]
    )[:500100]
    execution.command, execution.environment = result["command"], result["environment"]
    # Known runner evidence survives a revoked workflow lease; publication still requires checkpoint authority.
    session.commit()
    if result["exit_code"] == 125:
        raise PermissionError("Runner interrupted; owner must inspect execution before retry")
    return execution, result


def prepare_pull_request(
    session: Session, task: Task, project: Project, agent: Agent, workspace: Path, tree: str
):
    if candidate_tree(workspace) != tree:
        raise PermissionError("Candidate changed after independent review and QA")
    baseline = task.evidence["baseline_commit"]
    head = git(workspace, "rev-parse", "HEAD")
    if head == baseline:
        git(
            workspace,
            "-c",
            "user.name=Aiventra approved task",
            "-c",
            "user.email=aiventra@local.invalid",
            "commit",
            "-m",
            "Aiventra approved task " + task.id,
        )
        head = git(workspace, "rev-parse", "HEAD")
    elif git(workspace, "rev-parse", "HEAD^{tree}") != tree:
        raise PermissionError("Unexpected worktree commit; owner review required")
    diff = git(workspace, "diff", "--no-ext-diff", "--no-textconv", baseline, head)
    mode = task.payload.get("mode", "live")
    body = (
        f"Approved task: {task.id}\n\n{task.objective}\n\nValidation: independent review records and execution {task.evidence['execution_id']}.\nAdapter: {mode}"
        + (" — deterministic test adapter; no live AI certification." if mode == "mock" else ".")
    )
    content = {
        "title": task.objective[:120],
        "body": body,
        "branch": git(workspace, "branch", "--show-current"),
        "base_commit": baseline,
        "head_commit": head,
        "publication": "prepared_not_published",
        "review_run_ids": [row["review_run_id"] for row in task.evidence["reviews"]],
        "execution_id": task.evidence["execution_id"],
        "mode": mode,
    }
    artifact = save_artifact(
        session,
        task.org_id,
        "Prepared pull request and verified diff",
        body + "\n\n```diff\n" + diff + "\n```",
        kind="pull_request_draft",
        project_id=project.id,
        task_id=task.id,
        agent_id=agent.id,
    )
    session.add(
        BusinessRecord(
            org_id=task.org_id,
            project_id=project.id,
            kind="pull_request_draft",
            title=content["title"],
            data={**content, "artifact_id": artifact.id},
        )
    )
    task.evidence = {
        **task.evidence,
        "pull_request": {**content, "artifact_id": artifact.id},
        "candidate_tree": tree,
    }


async def coding_step(session: Session, workflow: Workflow, token: str) -> None:
    task = session.get(Task, workflow.task_id)
    project = session.get(Project, task.project_id)
    project_authority(session, project)
    approval = session.scalar(
        select(Approval).where(
            Approval.org_id == workflow.org_id,
            Approval.category == "repository_change",
            Approval.subject_id == task.id,
        )
    )
    if not approval or approval.expires_at <= now() or approval.subject_hash != digest(task.payload):
        raise PermissionError("Approved repository-change scope required")
    repository = session.get(Repository, task.payload["repository_id"])
    agent = session.get(Agent, task.assigned_agent_id)
    workspace = settings().repository_root.resolve() / ".worktrees" / project.id / task.id
    baseline_root = Path(repository.path)
    if task.payload.get("quality_defect_id"):
        from .quality import repair_baseline

        baseline_root = repair_baseline(session, task, project)
    context = source_context(workspace if workspace.exists() else baseline_root, task.objective)
    context["acceptance"] = task.acceptance
    if task.payload.get("quality_defect_id"):
        context["independent_qa_defect"] = task.payload["quality_feedback"]
    from .architecture_design import selected_context
    from .models import Proposal

    context["owner_selected_architecture"] = selected_context(
        session.get(Proposal, project.proposal_id), project
    )
    if task.payload.get("publication_id"):
        context["remote_review_feedback"] = {
            "publication_id": task.payload["publication_id"],
            "feedback_hash": task.payload["feedback_hash"],
            "untrusted_feedback": task.payload["feedback"],
        }
    repair_round = task.evidence.get("repair_round", 0)
    patch_name = round_name("patch", repair_round)
    review_names = [round_name(name, repair_round) for name in ("review", "review_2")]
    if repair_round:
        context["repair_evidence"] = task.evidence.get("repair_feedback", {})
    if workflow.step == 0:
        check_agent(session, agent, "propose_patch", project)
        baseline = worktree(baseline_root, workspace, task.id, task.payload.get("baseline_commit"))
        task.evidence = {"baseline_commit": baseline, "workspace": str(workspace)}
        qa = agent_for(session, workflow.org_id, "QA Director")
        check_agent(session, qa, "run_tests", project)
        execution, result = await qa_execution(session, workflow, task, qa, workspace, token)
        passed = passed_tests(result, task.payload["test_suite"])
        checkpoint(
            session,
            workflow,
            token,
            "baseline",
            {"execution_id": execution.id, **result},
            complete=not passed,
        )
        if not passed:
            task.status = "failed"
            task.evidence = {
                **task.evidence,
                "baseline_execution_id": execution.id,
                "baseline_passed": False,
                "reason": "Baseline failed or discovered no tests; code generation blocked",
            }
            session.add(
                Notification(
                    org_id=workflow.org_id,
                    severity="error",
                    title=task.evidence["reason"],
                    subject_id=task.id,
                )
            )
            audit(
                session,
                workflow.org_id,
                qa.id,
                "coding.baseline_failed",
                task.id,
                task.evidence,
                project_id=project.id,
                task_id=task.id,
                authorization=f"approval:{approval.id}",
            )
            return
    elif workflow.step == 1:
        result = await execute(
            session,
            workflow,
            agent,
            patch_name,
            PatchResult,
            context,
            quality=85,
            capabilities={"structured", "coding"},
            project=project,
        )
        session.refresh(project)
        check_agent(session, agent, "propose_patch", project)
        if result.tests != task.payload["test_suite"]:
            raise PermissionError("Model cannot change approved test command")
        apply_files(workspace, [file.model_dump() for file in result.files])
        tree = candidate_tree(workspace)
        diff = git(workspace, "diff", "--cached", "--no-ext-diff", "--no-textconv")
        if not diff:
            raise PermissionError("Patch made no repository changes")
        artifact = save_artifact(
            session,
            workflow.org_id,
            "Proposed code changes",
            diff,
            kind="code_diff",
            project_id=project.id,
            task_id=task.id,
            agent_id=agent.id,
        )
        checkpoint(
            session,
            workflow,
            token,
            patch_name,
            {
                "files": [file.model_dump() for file in result.files],
                "artifact_id": artifact.id,
                "candidate_tree": tree,
            },
        )
        task.status = "review"
    elif workflow.step < 2 + task.payload.get("review_count", 1):
        patch = session.scalar(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id, WorkflowStep.name == patch_name
            )
        )
        reviewer = agent_for(session, workflow.org_id, "Code Reviewer")
        if reviewer.id == agent.id:
            raise PermissionError("Code author cannot review own change")
        check_agent(session, reviewer, "review_diff", project)
        context["proposed_files"] = patch.result["files"]
        if candidate_tree(workspace) != patch.result["candidate_tree"]:
            raise PermissionError("Candidate changed before independent review")
        context["actual_diff"] = git(workspace, "diff", "--cached", "--no-ext-diff", "--no-textconv")[:8000]
        authored = session.scalar(
            select(ModelRun).where(
                ModelRun.workflow_id == workflow.id,
                ModelRun.step_name == patch_name,
                ModelRun.status == "succeeded",
            )
        )
        if not authored:
            raise PermissionError("Persisted successful author run required before independent review")
        previous_reviews = list(
            session.scalars(
                select(ModelRun).where(
                    ModelRun.workflow_id == workflow.id,
                    ModelRun.step_name.in_(review_names),
                    ModelRun.status == "succeeded",
                )
            )
        )
        review_name = review_names[0] if workflow.step == 2 else review_names[1]
        # Initial reviewers receive the same diff/criteria; other verdicts are never supplied.
        result = await execute(
            session,
            workflow,
            reviewer,
            review_name,
            ReviewResult,
            context,
            quality=85,
            capabilities={"structured", "coding"},
            project=project,
            review_against=[authored.model_id, *[run.model_id for run in previous_reviews]],
            review_policy=task.payload.get("review_policy", "prefer_provider"),
        )
        reviewed = session.scalar(
            select(ModelRun).where(
                ModelRun.workflow_id == workflow.id,
                ModelRun.step_name == review_name,
                ModelRun.status == "succeeded",
            )
        )
        author_model, reviewer_model = (
            session.get(ModelConfig, authored.model_id),
            session.get(ModelConfig, reviewed.model_id),
        )
        author_provider = session.get(Provider, author_model.provider_id)
        reviewer_provider = session.get(Provider, reviewer_model.provider_id)
        diversity = (
            "different_provider"
            if provider_identity(author_provider) != provider_identity(reviewer_provider)
            else "different_model"
            if model_identity(author_model, author_provider)
            != model_identity(reviewer_model, reviewer_provider)
            else "same_model_independent_context"
        )
        evidence = {
            **result.model_dump(),
            "author_run_id": authored.id,
            "review_run_id": reviewed.id,
            "author_model_id": authored.model_id,
            "review_model_id": reviewed.model_id,
            "diversity": diversity,
            "review_policy": task.payload.get("review_policy", "prefer_provider"),
        }
        checkpoint(session, workflow, token, review_name, evidence)
        task.evidence = {**task.evidence, "reviews": [*task.evidence.get("reviews", []), evidence]}
        task.status = "testing" if workflow.step >= 2 + task.payload.get("review_count", 1) else "review"
    else:
        qa = agent_for(session, workflow.org_id, "QA Director")
        if qa.id == agent.id:
            raise PermissionError("Code author cannot independently verify own change")
        check_agent(session, qa, "run_tests", project)
        patch = session.scalar(
            select(WorkflowStep).where(
                WorkflowStep.workflow_id == workflow.id, WorkflowStep.name == patch_name
            )
        )
        if candidate_tree(workspace) != patch.result["candidate_tree"]:
            raise PermissionError("Candidate changed before independent QA")
        execution, result = await qa_execution(session, workflow, task, qa, workspace, token)
        reviews = list(
            session.scalars(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_id == workflow.id, WorkflowStep.name.in_(review_names)
                )
            )
        )
        reviewer_approved = len(reviews) == task.payload.get("review_count", 1) and all(
            review.result["approved"] for review in reviews
        )
        approved = reviewer_approved and passed_tests(result, task.payload["test_suite"])
        task.status = "completed" if approved else "failed"
        task.evidence = {
            **task.evidence,
            "execution_id": execution.id,
            "reviewer_approved": reviewer_approved,
            "qa_agent_id": qa.id,
            "mode": workflow.mode,
            "exit_code": result["exit_code"],
            "patch_sha256": digest(
                session.scalar(
                    select(WorkflowStep).where(
                        WorkflowStep.workflow_id == workflow.id, WorkflowStep.name == patch_name
                    )
                ).result
            ),
        }
        task.evidence = {
            **task.evidence,
            "build_exit_code": result.get("build", {}).get("exit_code"),
            "runner_job_id": result.get("job_id"),
            "repair_round": repair_round,
        }
        repair = not passed_tests(result, task.payload["test_suite"]) and repair_round < task.payload.get(
            "repair_limit", 0
        )
        if approved:
            # Checkpoint verifies the current lease before any prepared result is published.
            checkpoint(session, workflow, token, round_name("qa", repair_round), task.evidence, complete=True)
            project_authority(session, project)
            prepare_pull_request(session, task, project, agent, workspace, patch.result["candidate_tree"])
        elif repair:
            checkpoint(session, workflow, token, round_name("qa", repair_round), task.evidence)
            failed_round = {
                "round": repair_round,
                "execution_id": execution.id,
                "reviews": task.evidence.get("reviews", []),
                "patch_step": patch_name,
            }
            task.evidence = {
                **task.evidence,
                "repair_round": repair_round + 1,
                "repairs": [*task.evidence.get("repairs", []), failed_round],
                "reviews": [],
                "repair_feedback": {
                    "exit_code": result["exit_code"],
                    "test_logs": result["logs"][-2500:],
                    "build_logs": str(result.get("build", {}).get("logs", ""))[-1500:],
                },
            }
            task.status, workflow.step = "in_progress", 1
        else:
            session.add(
                BusinessRecord(
                    org_id=workflow.org_id,
                    project_id=project.id,
                    kind="incident",
                    title="Coding task needs repair or owner review",
                    data=task.evidence,
                )
            )
            checkpoint(session, workflow, token, round_name("qa", repair_round), task.evidence, complete=True)
    audit(
        session,
        workflow.org_id,
        agent.id,
        "coding.step",
        task.id,
        {"step": workflow.step, "status": task.status},
        project_id=project.id,
        task_id=task.id,
        authorization=f"approval:{approval.id}",
    )
