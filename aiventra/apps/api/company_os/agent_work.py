"""Bounded, checkpointed agent messages, independent meetings and inference probes."""

from typing import Literal

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .artifacts import save_artifact
from .db import now, uid
from .gateway import execute
from .memory import retrieve
from .organization import agent_for
from .schemas import DocumentResult, Recommendation, Strict
from .security import audit, check_agent
from .workflows import checkpoint, project_authority


class ConnectivityResult(Strict):
    value: Literal["aiventra_probe_ok"]


class Followup(Strict):
    agent_id: str
    objective: str = Field(min_length=10, max_length=2000)


class MeetingDecision(Strict):
    summary: str = Field(min_length=1, max_length=10000)
    decisions: list[str] = Field(max_length=12)
    unresolved: list[str] = Field(max_length=12)
    followups: list[Followup] = Field(max_length=4)


async def work_step(session: Session, workflow: m.Workflow, token: str):
    work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == workflow.id))
    if not work or work.org_id != workflow.org_id:
        raise PermissionError("Durable agent work scope denied")
    project = session.get(m.Project, work.project_id) if work.project_id else None
    if project:
        project_authority(session, project)
    if work.kind == "planning":
        from .planning import planning_step

        await planning_step(session, workflow, token, work, project)
    elif work.kind == "delivery":
        from .delivery import review_step

        await review_step(session, workflow, token, work, project)
    elif work.kind == "quality":
        from .quality import quality_step

        await quality_step(session, workflow, token, work, project)
    elif work.kind == "deployment":
        from .deployments import deployment_step

        await deployment_step(session, workflow, token, work, project)
    elif work.kind == "tools":
        from .tools import tool_step

        await tool_step(session, workflow, token, work, project)
    elif work.kind == "benchmark":
        from .benchmarks import benchmark_step

        await benchmark_step(session, workflow, token, work)
    elif work.kind == "probe":
        model = session.get(m.ModelConfig, work.input["model_override"])
        provider = session.get(m.Provider, work.subject_id)
        if (
            not model
            or model.org_id != work.org_id
            or model.provider_id != provider.id
            or provider.kind == "mock"
        ):
            raise PermissionError("Inference probe model scope denied")
        agent = session.get(m.Agent, work.participants[0])
        result = await execute(
            session,
            workflow,
            agent,
            "inference_probe",
            ConnectivityResult,
            {"objective": "Return exactly aiventra_probe_ok in the value field."},
            quality=0,
        )
        checkpoint(session, workflow, token, "inference_probe", result.model_dump(), complete=True)
        work.result = {
            "value": result.value,
            "model_id": model.id,
            "evidence": "successful structured inference",
        }
    elif work.kind == "message":
        message = session.get(m.Message, work.subject_id)
        agent = session.get(m.Agent, message.recipient)
        check_agent(session, agent, "write_artifact", project)
        attachments = []
        for record_id in work.input["artifact_ids"]:
            artifact = session.get(m.Artifact, record_id)
            if (
                not artifact
                or artifact.org_id != work.org_id
                or artifact.project_id != project.id
                or artifact.conversation_id
            ):
                raise PermissionError("Message attachment scope denied")
            attachments.append(
                {"id": artifact.id, "sha256": artifact.sha256, "content": artifact.content[:4000]}
            )
        result = await execute(
            session,
            workflow,
            agent,
            "message_response",
            DocumentResult,
            {
                "objective": work.input["body"],
                "message_type": message.type,
                "project": {"id": project.id, "name": project.name},
                "memory": retrieve(session, work.org_id, project.id),
                "attachments": attachments,
            },
            project=project,
        )
        # Fence the result before creating any acknowledgement or follow-up record.
        checkpoint(session, workflow, token, "message_response", result.model_dump(), complete=True)
        artifact = save_artifact(
            session,
            work.org_id,
            result.title,
            result.content,
            "agent_message",
            project_id=project.id,
            agent_id=agent.id,
        )
        response = m.Message(
            id=uid(),
            org_id=work.org_id,
            project_id=project.id,
            sender=agent.id,
            recipient=message.sender,
            type="TaskCompleted",
            correlation_id=message.correlation_id,
            status="delivered",
            content={
                "artifact_id": artifact.id,
                "reply_to": message.id,
                "hop": work.input["hop"],
                "mode": workflow.mode,
            },
            authorization="completed bounded message workflow",
        )
        session.add(response)
        message.status, message.acknowledged_at = "acknowledged", now()
        work.result = {"artifact_id": artifact.id, "response_message_id": response.id}
    elif work.kind == "meeting":
        meeting = session.get(m.Meeting, work.subject_id)
        index, count = workflow.step, len(work.participants)
        if index < count * meeting.rounds:
            round_index, participant = divmod(index, count)
            agent = session.get(m.Agent, work.participants[participant])
            context = {
                "objective": meeting.agenda,
                "role": agent.role,
                "project": {"id": project.id, "name": project.name},
                "memory": work.input["memory_snapshot"],
                "round": round_index + 1,
            }
            if round_index:
                context["prior_round"] = [row for row in meeting.contributions if row["round"] == 1]
                context["objective"] += (
                    " Assess disagreements using the prior round and identify unresolved evidence."
                )
            result = await execute(
                session,
                workflow,
                agent,
                f"meeting_round_{round_index + 1}_{agent.id}",
                Recommendation,
                context,
                project=project,
            )
            checkpoint(session, workflow, token, f"contribution_{index}", result.model_dump())
            meeting.contributions = [
                *meeting.contributions,
                {
                    "agent_id": agent.id,
                    "role": agent.role,
                    "round": round_index + 1,
                    "content": result.model_dump(),
                },
            ]
        else:
            coordinator = agent_for(session, work.org_id, "CEO")
            result = await execute(
                session,
                workflow,
                coordinator,
                "meeting_decision",
                MeetingDecision,
                {
                    "objective": meeting.agenda,
                    "contributions": meeting.contributions,
                    "followup_agents": work.participants,
                    "authority": "Only read-only document objectives may be proposed; no code or external actions.",
                },
                project=project,
            )
            for followup in result.followups:
                if followup.agent_id not in work.participants:
                    raise PermissionError("Meeting follow-up agent outside selected participants")
            checkpoint(session, workflow, token, "meeting_decision", result.model_dump(), complete=True)
            meeting.decision = result.model_dump()
            task_ids = []
            if work.input["create_followups"]:
                for followup in result.followups:
                    agent = session.get(m.Agent, followup.agent_id)
                    check_agent(session, agent, "write_artifact", project)
                    task = m.Task(
                        id=uid(),
                        org_id=work.org_id,
                        project_id=project.id,
                        assigned_agent_id=agent.id,
                        objective=followup.objective,
                        kind="document",
                        budget_micro=100000,
                        acceptance=["Read-only scoped artifact; no external action"],
                        payload={"mode": workflow.mode, "job_id": work.id, "meeting_id": meeting.id},
                    )
                    session.add(task)
                    task_ids.append(task.id)
            work.result = {"meeting_id": meeting.id, "task_ids": task_ids, "decision": result.model_dump()}
    else:
        raise ValueError("Unknown durable agent work kind")
    audit(
        session,
        workflow.org_id,
        "worker",
        "agent_work.checkpoint",
        work.id,
        {"kind": work.kind, "step": workflow.step, "status": workflow.status},
        project_id=work.project_id,
        authorization="bounded owner-authorized agent work",
    )
