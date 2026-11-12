"""Persisted invocation states, rather than one process per registered role."""

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from . import models as m
from .db import now, uid
from .security import clean

STATES = {
    "REGISTERED",
    "AVAILABLE",
    "IDLE",
    "ASSIGNED",
    "RUNNING",
    "WAITING_FOR_PROVIDER",
    "WAITING_FOR_FREE_PROVIDER",
    "WAITING_FOR_INPUT",
    "WAITING_FOR_APPROVAL",
    "BLOCKED",
    "FAILED",
    "COMPLETED",
    "DISABLED",
}
TRANSITIONS = {
    "REGISTERED": {"AVAILABLE", "IDLE", "ASSIGNED", "BLOCKED", "DISABLED"},
    "AVAILABLE": {"IDLE", "ASSIGNED", "BLOCKED", "DISABLED"},
    "IDLE": {"AVAILABLE", "ASSIGNED", "BLOCKED", "DISABLED"},
    "ASSIGNED": {
        "RUNNING",
        "WAITING_FOR_PROVIDER",
        "WAITING_FOR_FREE_PROVIDER",
        "WAITING_FOR_INPUT",
        "WAITING_FOR_APPROVAL",
        "BLOCKED",
        "FAILED",
        "DISABLED",
    },
    "RUNNING": {"COMPLETED", "FAILED", "BLOCKED", "DISABLED"},
    "WAITING_FOR_PROVIDER": {"ASSIGNED", "BLOCKED", "FAILED", "DISABLED"},
    "WAITING_FOR_FREE_PROVIDER": {"ASSIGNED", "BLOCKED", "FAILED", "DISABLED"},
    "WAITING_FOR_INPUT": {"ASSIGNED", "BLOCKED", "DISABLED"},
    "WAITING_FOR_APPROVAL": {"ASSIGNED", "BLOCKED", "DISABLED"},
    "BLOCKED": {"ASSIGNED", "FAILED", "DISABLED"},
    "FAILED": {"ASSIGNED", "BLOCKED", "DISABLED"},
    "COMPLETED": {"ASSIGNED", "BLOCKED", "IDLE", "DISABLED"},
    "DISABLED": {"ASSIGNED", "IDLE", "AVAILABLE", "BLOCKED"},
}


def transition(
    session: Session,
    workflow: m.Workflow,
    agent: m.Agent,
    state: str,
    step: str = "",
    run_id: str | None = None,
    detail: dict | None = None,
):
    if state not in STATES or agent.org_id != workflow.org_id:
        raise ValueError("Invalid agent execution transition")
    execution = session.scalar(
        select(m.AgentExecution).where(
            m.AgentExecution.workflow_id == workflow.id, m.AgentExecution.agent_id == agent.id
        )
    )
    if not execution:
        execution = m.AgentExecution(
            id=uid(), org_id=workflow.org_id, workflow_id=workflow.id, agent_id=agent.id, state="REGISTERED"
        )
        session.add(execution)
        session.flush()
        session.add(
            m.AgentStateEvent(
                org_id=workflow.org_id,
                execution_id=execution.id,
                previous_state="",
                state="REGISTERED",
                detail={},
                sequence=1,
            )
        )
    if (
        state in {"RUNNING", "WAITING_FOR_PROVIDER", "WAITING_FOR_FREE_PROVIDER"}
        and execution.state != "ASSIGNED"
    ):
        transition(session, workflow, agent, "ASSIGNED", step, detail={"mode": workflow.mode})
    if state != execution.state and state not in TRANSITIONS[execution.state]:
        raise ValueError(f"Invalid agent state transition: {execution.state} to {state}")
    if execution.state != state or execution.step_name != step:
        sequence = (
            session.scalar(
                select(func.max(m.AgentStateEvent.sequence)).where(
                    m.AgentStateEvent.execution_id == execution.id
                )
            )
            or 0
        ) + 1
        session.add(
            m.AgentStateEvent(
                org_id=workflow.org_id,
                execution_id=execution.id,
                previous_state=execution.state,
                state=state,
                detail=clean(detail or {}),
                sequence=sequence,
            )
        )
    execution.state, execution.step_name = state, step
    execution.model_run_id, execution.updated_at = run_id, now()
    execution.detail = clean({"mode": workflow.mode, **(detail or {})})
    return execution


def workflow_state(session: Session, workflow: m.Workflow, state: str, detail: dict):
    for row in session.scalars(select(m.AgentExecution).where(m.AgentExecution.workflow_id == workflow.id)):
        if row.state != "COMPLETED":
            transition(
                session,
                workflow,
                session.get(m.Agent, row.agent_id),
                state,
                row.step_name,
                row.model_run_id,
                detail,
            )


def snapshot(session: Session, org_id: str) -> list[dict]:
    agents = session.scalars(select(m.Agent).where(m.Agent.org_id == org_id)).all()
    executions = session.scalars(
        select(m.AgentExecution)
        .where(m.AgentExecution.org_id == org_id)
        .order_by(m.AgentExecution.updated_at.desc(), m.AgentExecution.id)
    ).all()
    workflows = {
        row.id: row for row in session.scalars(select(m.Workflow).where(m.Workflow.org_id == org_id))
    }
    latest = {}

    def priority(row):
        workflow = workflows.get(row.workflow_id)
        rank = 3
        if (
            workflow
            and workflow.status == "running"
            and workflow.lease_until >= now()
            and row.state == "RUNNING"
        ):
            rank = 0
        elif workflow and workflow.status in {"waiting_for_provider", "waiting_for_free_provider"}:
            rank = 1
        elif workflow and workflow.status == "queued" and row.state == "ASSIGNED":
            rank = 2
        return rank, -row.updated_at, row.id

    for row in sorted(executions, key=priority):
        latest.setdefault(row.agent_id, row)
    tasks = session.scalars(
        select(m.Task).where(
            m.Task.org_id == org_id,
            m.Task.status.in_(
                ["queued", "in_progress", "waiting_for_provider", "waiting_for_free_provider", "blocked"]
            ),
        )
    ).all()
    assigned = {task.assigned_agent_id for task in tasks}
    totals = {
        row.agent_id: row
        for row in session.execute(
            select(
                m.ModelRun.agent_id,
                func.sum(m.ModelRun.cost_micro).label("cost"),
                func.sum(case((m.ModelRun.status == "succeeded", 1), else_=0)).label("successful"),
                func.sum(
                    case((m.ModelRun.status.in_(["failed", "quality_failed", "uncertain"]), 1), else_=0)
                ).label("failed"),
            )
            .where(m.ModelRun.org_id == org_id)
            .group_by(m.ModelRun.agent_id)
        )
    }
    result = []
    for agent in agents:
        execution = latest.get(agent.id)
        workflow = workflows.get(execution.workflow_id) if execution else None
        state = execution.state if execution else "ASSIGNED" if agent.id in assigned else "IDLE"
        stale = False
        if not agent.enabled:
            state = "DISABLED"
        elif workflow and workflow.status == "cancelled":
            state = "BLOCKED"
        elif workflow and workflow.status in {"waiting_for_provider", "waiting_for_free_provider"}:
            state = workflow.status.upper()
        elif state == "RUNNING" and (
            not workflow or workflow.status != "running" or workflow.lease_until < now()
        ):
            state, stale = "BLOCKED", True
        total = totals.get(agent.id)
        result.append(
            {
                "agent_id": agent.id,
                "state": state,
                "stale_lease": stale,
                "workflow_id": workflow.id if workflow else None,
                "mode": workflow.mode if workflow else None,
                "step_name": execution.step_name if execution else "",
                "updated_at": execution.updated_at if execution else agent.created_at,
                "successful_runs": total.successful if total else 0,
                "failed_runs": total.failed if total else 0,
                "cost_micro": total.cost if total else 0,
            }
        )
    return result
