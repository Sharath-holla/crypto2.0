"""Sequential, checkpointed BA → CTO → PM documents and an unapproved workforce revision."""

import json
from typing import Literal

from pydantic import Field
from sqlalchemy import select

from . import models as m
from .artifacts import save_artifact
from .db import now
from .gateway import execute
from .organization import agent_for
from .schemas import DocumentResult, Strict
from .security import audit, check_agent, digest
from .task_routing import TaskRequirements, prepare


class PlannedTask(TaskRequirements):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    role: str = Field(min_length=1, max_length=100)
    kind: Literal["document", "coding"]
    objective: str = Field(min_length=10, max_length=1000)
    acceptance: list[str] = Field(min_length=1, max_length=8)
    depends_on: list[str] = Field(max_length=12)


class ProjectPlanResult(Strict):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=10, max_length=2000)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=12)
    risks: list[str] = Field(max_length=8)


ROLES = ["Business Analyst", "CTO", "Project Manager"]


async def planning_step(session, workflow, token, work, project):
    from .staffing import lock_org, validate
    from .workflows import checkpoint, project_authority

    plan = session.get(m.StaffingPlan, work.subject_id)
    if (
        not plan
        or plan.project_id != project.id
        or plan.status != "draft"
        or plan.version != work.input["plan_version"]
        or plan.content_hash != work.input["plan_hash"]
    ):
        raise PermissionError("Workforce draft changed; restart planning against the current version")
    index = workflow.step
    if index not in range(3):
        raise PermissionError("Invalid planning checkpoint")
    agent = session.get(m.Agent, work.participants[index])
    if agent.role != ROLES[index]:
        raise PermissionError("Planning role binding changed")
    check_agent(session, agent, "write_artifact", project)
    proposal = session.get(m.Proposal, project.proposal_id)
    prior = list(
        session.scalars(
            select(m.WorkflowStep)
            .where(m.WorkflowStep.workflow_id == workflow.id)
            .order_by(m.WorkflowStep.name)
        )
    )
    documents = []
    for step in prior:
        artifact = session.get(m.Artifact, step.result["artifact_id"])
        if not artifact or artifact.org_id != work.org_id or artifact.project_id != project.id:
            raise PermissionError("Planning handoff document outside project")
        documents.append({"id": artifact.id, "sha256": artifact.sha256, "content": artifact.content[:2400]})
    context = {
        "objective": work.input["objective"],
        "approved_requirements": proposal.content["confirmed_requirements"],
        "acceptance": proposal.content["acceptance_criteria"],
        "saved_handoff_documents": documents,
        "instruction": [
            "Analyze approved requirements and acceptance criteria, identifying unresolved questions.",
            "Use the saved BA document to propose architecture, dependencies and technical risks.",
            "Use saved BA and CTO documents to propose a bounded task DAG. Use only supplied agent roles. "
            "This is a draft requiring separate owner staffing approval; no execution or publication is authorized.",
        ][index],
    }
    from .architecture_design import selected_context

    context["owner_selected_architecture"] = selected_context(proposal, project)
    if index == 2:
        context["available_roles"] = sorted(
            set(
                session.scalars(
                    select(m.Agent.role).where(
                        m.Agent.org_id == work.org_id,
                        m.Agent.enabled.is_(True),
                        m.Agent.role.in_(
                            [
                                "Business Analyst",
                                "CTO",
                                "Backend Developer",
                                "Frontend Developer",
                                "QA Director",
                                "Security Architect",
                                "Project Manager",
                                "Software Architect",
                                "Database Engineer",
                                "Integration Engineer",
                                "UI Designer",
                                "DevOps Engineer",
                                "FinOps Engineer",
                                "Unit Test Engineer",
                                "Integration Test Engineer",
                            ]
                        ),
                    )
                )
            )
        )
        from .task_routing import choices

        context["task_model_options"] = {
            row["key"]: [
                {"id": model.id, "identifier": model.identifier, "capabilities": model.capabilities}
                for model, _ in choices(session, project, plan.content, row, preferences=False)[0][:8]
            ]
            for row in plan.content["tasks"]
        }
        context["instruction"] += (
            " Include bounded workstreams, skills, difficulty, risk, tools, context allowance and QA criteria. "
            "Recommend only supplied registered model IDs, or null when no eligible free model exists. "
            "Do not set owner model_override or claim measured resource usage."
        )
    result = await execute(
        session,
        workflow,
        agent,
        f"planning_{index}",
        ProjectPlanResult if index == 2 else DocumentResult,
        context,
        project=project,
    )
    lock_org(session, work.org_id)
    session.refresh(plan)
    session.refresh(project)
    project_authority(session, project)
    check_agent(session, agent, "write_artifact", project)
    if (
        plan.status != "draft"
        or plan.version != work.input["plan_version"]
        or plan.content_hash != work.input["plan_hash"]
    ):
        raise PermissionError("Workforce draft changed while an agent was running")
    if index == 2:
        tasks, allocated = [], set()
        for task in result.tasks:
            if task.role not in context["available_roles"] or task.model_override:
                raise PermissionError("Planner proposed an unauthorized role or owner model override")
            worker = agent_for(session, work.org_id, task.role)
            allocated.add(worker.id)
            tasks.append(
                {
                    "key": task.key,
                    "agent_id": worker.id,
                    "kind": task.kind,
                    "objective": task.objective,
                    "acceptance": task.acceptance,
                    "depends_on": task.depends_on,
                    "foundation_ids": list(plan.content["foundation_task_ids"]),
                    "budget_micro": min(100000, project.budget_micro // len(result.tasks)),
                    **TaskRequirements.model_validate(
                        {key: getattr(task, key) for key in TaskRequirements.model_fields}
                    ).model_dump(),
                }
            )
        if any(task.kind == "coding" for task in result.tasks):
            allocated.update(
                agent_for(session, work.org_id, role).id for role in ("Code Reviewer", "QA Director")
            )
        proposed = {
            **plan.content,
            "planner": f"agent-chain:{work.id}",
            "mode": workflow.mode,
            "concurrency": 1,
            "tasks": tasks,
            "allocations": [{"agent_id": agent_id, "slots": 1} for agent_id in sorted(allocated)],
        }
        validate(session, plan, proposed)
        prepare(session, plan, proposed)
    # Fence saved state before committing handoffs or changing the staffing draft.
    checkpoint(session, workflow, token, f"planning_{index}", {}, complete=index == 2)
    content = json.dumps(result.model_dump(), ensure_ascii=False, indent=2) if index == 2 else result.content
    artifact = save_artifact(
        session,
        work.org_id,
        result.title,
        content,
        "project_planning",
        project_id=project.id,
        agent_id=agent.id,
    )
    session.flush()
    saved = session.scalar(
        select(m.WorkflowStep).where(
            m.WorkflowStep.workflow_id == workflow.id, m.WorkflowStep.name == f"planning_{index}"
        )
    )
    saved.result = {"artifact_id": artifact.id, "sha256": artifact.sha256, "agent_id": agent.id}
    if index:
        for message in session.scalars(
            select(m.Message).where(m.Message.correlation_id == work.id, m.Message.recipient == agent.id)
        ):
            message.status, message.acknowledged_at = "acknowledged", now()
    if index < 2:
        session.add(
            m.Message(
                org_id=work.org_id,
                project_id=project.id,
                sender=agent.id,
                recipient=work.participants[index + 1],
                type="ArtifactShared",
                correlation_id=work.id,
                content={"artifact_id": artifact.id, "sha256": artifact.sha256, "mode": workflow.mode},
                authorization=f"owner-planning:{work.id}",
            )
        )
    else:
        plan.version += 1
        plan.content, plan.content_hash = proposed, digest(proposed)
        session.add(
            m.StaffingRevision(
                org_id=work.org_id,
                plan_id=plan.id,
                version=plan.version,
                content=proposed,
                content_hash=plan.content_hash,
            )
        )
        work.result = {
            "artifact_id": artifact.id,
            "document_ids": [d["id"] for d in documents] + [artifact.id],
            "staffing_plan_id": plan.id,
            "staffing_version": plan.version,
            "staffing_hash": plan.content_hash,
            "approval_required": True,
            "mode": workflow.mode,
        }
        audit(
            session,
            work.org_id,
            agent.id,
            "planning.staffing_draft_saved",
            plan.id,
            {"version": plan.version, "work_id": work.id},
            project_id=project.id,
        )
