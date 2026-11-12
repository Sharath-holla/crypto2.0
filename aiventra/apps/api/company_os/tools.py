"""Closed server tool registry. No host commands, arbitrary HTTP or model-created permissions."""

import json
from uuid import UUID

from pydantic import Field, ValidationError
from sqlalchemy import select, update

from . import models as m
from .artifacts import save_artifact
from .db import now, uid
from .providers import strict_schema
from .schemas import Strict
from .security import audit, check_agent, clean
from .workflows import project_authority


class Numbers(Strict):
    numbers: list[int] = Field(min_length=1, max_length=20)


class MemoryQuery(Strict):
    query: str = Field(max_length=500)


class ArtifactRead(Strict):
    artifact_id: UUID


class ArtifactWrite(Strict):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=16000)


class Handoff(Strict):
    agent_id: UUID
    objective: str = Field(min_length=10, max_length=2000)


class ToolCall(Strict):
    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict
    signature: str | None = Field(default=None, max_length=8192)


class ToolTurn(Strict):
    answer: str = Field(max_length=20000)
    calls: list[ToolCall] = Field(max_length=4)


REGISTRY = {
    "sum_numbers": (Numbers, "Sum up to twenty integers using the server calculator.", "read_context"),
    "read_project_memory": (
        MemoryQuery,
        "Read scoped project records and artifact references.",
        "read_context",
    ),
    "read_artifact": (ArtifactRead, "Read one artifact belonging to the approved project.", "read_context"),
    "write_artifact": (
        ArtifactWrite,
        "Save a document in the approved project; no code execution.",
        "write_artifact",
    ),
    "handoff_document": (
        Handoff,
        "Assign one bounded document task to an authorized peer; shares this job's cap.",
        "write_artifact",
    ),
}


def definitions(agent, project=None, benchmark=False):
    return [
        {"name": name, "description": description, "parameters": strict_schema(schema.model_json_schema())}
        for name, (schema, description, permission) in REGISTRY.items()
        if permission in agent.tools and (name == "sum_numbers" or (project and not benchmark))
    ]


def guard(session, workflow, agent, project=None):
    company = session.execute(
        update(m.Organization)
        .where(m.Organization.id == workflow.org_id, m.Organization.paused.is_(False))
        .values(paused=False)
    )
    if company.rowcount != 1:
        raise PermissionError("Company paused before tool execution")
    won = session.execute(
        update(m.Workflow)
        .where(
            m.Workflow.id == workflow.id,
            m.Workflow.status == "running",
            m.Workflow.lease_token == workflow.lease_token,
            m.Workflow.lease_until > now(),
        )
        .values(lease_until=workflow.lease_until)
    )
    if won.rowcount != 1:
        raise PermissionError("Workflow lease revoked before tool execution")
    session.refresh(agent)
    if project:
        session.refresh(project)
        project_authority(session, project)
    check_agent(session, agent, "read_context", project)


def invoke(session, workflow, agent, project, step, run_id, call, allowed):
    guard(session, workflow, agent, project)
    existing = session.scalar(
        select(m.ToolInvocation).where(
            m.ToolInvocation.workflow_id == workflow.id,
            m.ToolInvocation.step_name == step,
            m.ToolInvocation.call_id == call.id,
        )
    )
    if existing:
        return existing.result
    row = m.ToolInvocation(
        id=uid(),
        org_id=workflow.org_id,
        workflow_id=workflow.id,
        agent_id=agent.id,
        project_id=project.id if project else None,
        run_id=run_id,
        step_name=step,
        call_id=call.id,
        name=call.name,
        arguments=clean(call.arguments),
    )
    session.add(row)
    try:
        if call.name not in allowed or call.name not in REGISTRY:
            raise PermissionError("Tool not authorized")
        schema, _, permission = REGISTRY[call.name]
        check_agent(session, agent, permission, project)
        args = schema.model_validate_json(json.dumps(call.arguments), strict=True)
        if call.name == "sum_numbers":
            result = {"sum": sum(args.numbers)}
        elif not project:
            raise PermissionError("Project-scoped tool requires approval")
        elif call.name == "read_project_memory":
            from .semantic_memory import search

            result = search(session, workflow.org_id, args.query, project_id=project.id, agent=agent)
        elif call.name == "read_artifact":
            artifact = session.get(m.Artifact, str(args.artifact_id))
            if (
                not artifact
                or artifact.org_id != workflow.org_id
                or artifact.project_id != project.id
                or artifact.conversation_id
            ):
                raise PermissionError("Artifact scope denied")
            result = {
                "artifact_id": artifact.id,
                "sha256": artifact.sha256,
                "content": artifact.content[:16000],
            }
        elif call.name == "write_artifact":
            artifact = save_artifact(
                session, workflow.org_id, args.name, args.content, project_id=project.id, agent_id=agent.id
            )
            result = {"artifact_id": artifact.id, "sha256": artifact.sha256}
        else:
            # One delegation per job; recipients cannot recursively invoke tools through this task.
            if session.scalar(
                select(m.ToolInvocation.id).where(
                    m.ToolInvocation.workflow_id == workflow.id,
                    m.ToolInvocation.name == "handoff_document",
                    m.ToolInvocation.status == "succeeded",
                )
            ):
                raise PermissionError("Job handoff limit reached")
            recipient = session.get(m.Agent, str(args.agent_id))
            if not recipient or recipient.org_id != workflow.org_id or recipient.id == agent.id:
                raise PermissionError("Peer agent scope denied")
            check_agent(session, recipient, "write_artifact", project)
            work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == workflow.id))
            if recipient.id not in {peer["id"] for peer in work.input["peer_agents"]}:
                raise PermissionError("Peer not selected by owner")
            budget = session.scalar(select(m.Budget).where(m.Budget.scope == f"job:{work.id}"))
            task = m.Task(
                id=uid(),
                org_id=workflow.org_id,
                project_id=project.id,
                assigned_agent_id=recipient.id,
                objective=args.objective,
                kind="document",
                budget_micro=budget.limit_micro,
                acceptance=["Persist scoped document with artifact hash"],
                payload={"mode": workflow.mode, "job_id": work.id, "handoff_from": agent.id},
            )
            session.add(task)
            session.add(
                m.Budget(org_id=workflow.org_id, scope=f"task:{task.id}", limit_micro=budget.limit_micro)
            )
            result = {"task_id": task.id, "status": "queued", "recipient_id": recipient.id}
        row.status, row.result = "succeeded", clean(result)
    except (PermissionError, ValidationError):
        row.status, row.result = "rejected", {"error": "Tool authorization or argument validation failed"}
    audit(
        session,
        workflow.org_id,
        agent.id,
        "tool." + row.status,
        row.id,
        {"name": row.name, "call_id": call.id},
        project_id=row.project_id,
    )
    return row.result


async def tool_step(session, workflow, token, work, project):
    from .gateway import execute
    from .workflows import checkpoint

    agent = session.get(m.Agent, work.participants[0])
    if workflow.step >= 3:
        raise PermissionError("Three-round native tool limit reached")
    tool_defs = definitions(agent, project)
    tool_defs = [t for t in tool_defs if t["name"] != "handoff_document" or work.input["peer_agents"]]
    history = [
        row.result
        for row in session.scalars(
            select(m.WorkflowStep)
            .where(m.WorkflowStep.workflow_id == workflow.id)
            .order_by(m.WorkflowStep.created_at, m.WorkflowStep.name)
        )
    ]
    step = f"tools_{workflow.step}"
    turn = await execute(
        session,
        workflow,
        agent,
        step,
        ToolTurn,
        {
            "objective": work.input["objective"],
            "project_id": project.id,
            "peer_agents": work.input["peer_agents"],
            "maximum_rounds": 3,
        },
        project=project,
        capabilities={"tools"},
        native_tools=tool_defs,
        native_history=history,
    )
    guard(session, workflow, agent, project)
    if len({c.id for c in turn.calls}) != len(turn.calls):
        raise PermissionError("Duplicate native call IDs")
    run_id = session.scalar(
        select(m.ModelRun.id).where(
            m.ModelRun.workflow_id == workflow.id,
            m.ModelRun.step_name == step,
            m.ModelRun.status == "succeeded",
        )
    )
    results = {
        call.id: invoke(session, workflow, agent, project, step, run_id, call, {t["name"] for t in tool_defs})
        for call in turn.calls
    }
    result = {**turn.model_dump(), "results": results}
    if not turn.calls:
        if not turn.answer.strip():
            raise PermissionError("Empty native final answer")
        check_agent(session, agent, "write_artifact", project)
        artifact = save_artifact(
            session,
            workflow.org_id,
            "Agent tool execution result",
            turn.answer,
            project_id=project.id,
            agent_id=agent.id,
        )
        work.result = {"artifact_id": artifact.id, "sha256": artifact.sha256, "rounds": workflow.step + 1}
    checkpoint(session, workflow, token, step, result, complete=not turn.calls)
