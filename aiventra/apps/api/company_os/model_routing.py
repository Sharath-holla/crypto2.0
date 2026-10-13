from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m


def task_class_for(session: Session, workflow: m.Workflow) -> str:
    return (
        session.scalar(select(m.AgentWork.kind).where(m.AgentWork.workflow_id == workflow.id))
        or workflow.kind
    )


def work_override(session: Session, workflow: m.Workflow) -> str | None:
    work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == workflow.id))
    if work:
        return work.input.get("model_override")
    task = session.get(m.Task, workflow.task_id) if workflow.task_id else None
    return task.payload.get("model_override") if task else None


def apply_policies(
    session: Session, agent: m.Agent, project_id: str | None, candidates: list, override: str | None = None
) -> list:
    policies = {
        row.scope: row
        for row in session.scalars(select(m.ModelPolicy).where(m.ModelPolicy.org_id == agent.org_id))
    }
    relevant = [policies.get(f"agent:{agent.id}"), policies.get(f"project:{project_id}")]
    rows = []
    for model, provider in candidates:
        restrictions = relevant + [policies.get(f"provider:{provider.id}")]
        if override and model.id != override:
            continue
        if any(
            policy and policy.allowed_model_ids and model.id not in policy.allowed_model_ids
            for policy in restrictions
        ):
            continue
        rows.append((model, provider))
    preferred = {policy.preferred_model_id for policy in relevant if policy and policy.preferred_model_id}
    return sorted(
        rows,
        key=lambda row: (
            row[0].id not in preferred,
            not (
                policies.get(f"provider:{row[1].id}")
                and policies[f"provider:{row[1].id}"].preferred_model_id == row[0].id
            ),
        ),
    )
