"""Read-only digest for comparing actual conversation state across service restarts.

Run before/after restart against the same database; compare JSON byte-for-byte.
Only record counts and digests are emitted, never conversation content or credentials.
"""

import hashlib
import json

from company_os.config import settings
from company_os.db import SessionLocal
from company_os.models import (
    AgentExecution,
    AgentStateEvent,
    AgentWork,
    Artifact,
    BenchmarkProfile,
    BenchmarkResult,
    Conversation,
    ConversationTurn,
    Meeting,
    Message,
    ModelRun,
    RunTrace,
    ToolInvocation,
    Workflow,
    WorkflowStep,
)
from sqlalchemy import select


def snapshot():
    with SessionLocal() as session:
        conversations = list(session.scalars(select(Conversation).order_by(Conversation.id)))
        assert conversations, "Run conversation integration checks first"
        ids = [row.id for row in conversations]
        turns = list(
            session.scalars(
                select(ConversationTurn)
                .where(ConversationTurn.conversation_id.in_(ids))
                .order_by(ConversationTurn.id)
            )
        )
        turn_ids = [row.id for row in turns]
        workflows = list(
            session.scalars(
                select(Workflow).where(Workflow.conversation_turn_id.in_(turn_ids)).order_by(Workflow.id)
            )
        )
        assert any(row.status == "completed" for row in workflows), "No completed conversation"
        assert any(row.status == "cancelled" for row in workflows), "No persisted cancellation"
        assert all(row.status in {"completed", "cancelled"} for row in workflows), "Wait for active turns"
        attachments = list(
            session.scalars(select(Artifact).where(Artifact.conversation_id.in_(ids)).order_by(Artifact.id))
        )
        assert attachments, "No uploaded document"
        for row in attachments:
            assert hashlib.sha256(row.content.encode()).hexdigest() == row.sha256, "Document integrity failed"
            stored = (settings().artifact_root / row.storage_key).read_text(encoding="utf-8")
            assert hashlib.sha256(stored.encode()).hexdigest() == row.sha256, "Private file integrity failed"
        works = list(session.scalars(select(AgentWork).order_by(AgentWork.id)))
        job_workflow_ids = [row.workflow_id for row in works]
        job_workflows = list(
            session.scalars(select(Workflow).where(Workflow.id.in_(job_workflow_ids)).order_by(Workflow.id))
        )
        assert all(row.status in {"completed", "cancelled"} for row in job_workflows), (
            "Wait for or cancel active agent jobs"
        )
        executions = list(
            session.scalars(
                select(AgentExecution)
                .where(AgentExecution.workflow_id.in_(job_workflow_ids))
                .order_by(AgentExecution.id)
            )
        )
        runs = list(
            session.scalars(
                select(ModelRun).where(ModelRun.workflow_id.in_(job_workflow_ids)).order_by(ModelRun.id)
            )
        )
        projects = [row.project_id for row in works if row.project_id]
        job_artifacts = list(
            session.scalars(select(Artifact).where(Artifact.project_id.in_(projects)).order_by(Artifact.id))
        )
        for artifact in job_artifacts:
            assert hashlib.sha256(artifact.content.encode()).hexdigest() == artifact.sha256
            stored = (settings().artifact_root / artifact.storage_key).read_text(encoding="utf-8")
            assert hashlib.sha256(stored.encode()).hexdigest() == artifact.sha256
        related = [
            (AgentStateEvent, AgentStateEvent.execution_id.in_([r.id for r in executions])),
            (WorkflowStep, WorkflowStep.workflow_id.in_(job_workflow_ids)),
            (RunTrace, RunTrace.run_id.in_([r.id for r in runs])),
            (ToolInvocation, ToolInvocation.workflow_id.in_(job_workflow_ids)),
            (BenchmarkResult, BenchmarkResult.work_id.in_([r.id for r in works])),
            (BenchmarkProfile, BenchmarkProfile.work_id.in_([r.id for r in works])),
            (Message, Message.project_id.in_(projects)),
            (Meeting, Meeting.project_id.in_(projects)),
        ]
        extra_rows = [
            row
            for model, clause in related
            for row in session.scalars(select(model).where(clause).order_by(model.id))
        ]
        rows = [
            *conversations,
            *turns,
            *workflows,
            *attachments,
            *works,
            *job_workflows,
            *executions,
            *runs,
            *job_artifacts,
            *extra_rows,
        ]
        payload = [
            {
                "table": row.__tablename__,
                **{column.name: getattr(row, column.name) for column in row.__table__.columns},
            }
            for row in rows
        ]
        return {
            "conversations": len(conversations),
            "turns": len(turns),
            "documents": len(attachments),
            "agent_jobs": len(works),
            "agent_job_kinds": {
                kind: sum(w.kind == kind for w in works) for kind in sorted({w.kind for w in works})
            },
            "project_artifacts": len(job_artifacts),
            "tool_invocations": sum(isinstance(row, ToolInvocation) for row in extra_rows),
            "benchmark_results": sum(isinstance(row, BenchmarkResult) for row in extra_rows),
            "sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
