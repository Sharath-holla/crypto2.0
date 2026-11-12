"""Policy-based workforce planning. Plans are proposals, never fabricated AI output."""

from collections import Counter
from copy import deepcopy

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import models as m
from .config import settings
from .db import now, uid
from .finance import token_cost
from .organization import agent_for
from .security import audit, check_agent, digest


def lock_org(session: Session, org_id: str) -> None:
    session.execute(
        update(m.Organization).where(m.Organization.id == org_id).values(name=m.Organization.name)
    )


def suggest(session: Session, project: m.Project) -> m.StaffingPlan:
    existing = session.scalar(select(m.StaffingPlan).where(m.StaffingPlan.project_id == project.id))
    if existing:
        return existing
    proposal = session.get(m.Proposal, project.proposal_id)
    requirement = session.get(m.Requirement, proposal.requirement_id)
    text = (requirement.title + " " + requirement.text).lower()
    foundation = list(
        session.scalars(
            select(m.Task).where(m.Task.project_id == project.id).order_by(m.Task.created_at, m.Task.id)
        )
    )
    architecture = next(
        (task.id for task in foundation if session.get(m.Agent, task.assigned_agent_id).role == "CTO"), None
    )
    definitions = [
        (
            "requirements",
            "Business Analyst",
            "document",
            "Write traceable requirements and acceptance criteria",
            [],
        ),
        ("cost", "FinOps Engineer", "document", "Assess execution costs and record unknown rates", []),
    ]
    ui = any(word in text for word in ("website", "frontend", "dashboard", "interface", " web", " ui", "app"))
    software = ui or any(
        word in text for word in ("api", "software", "backend", "code", "platform", "service")
    )
    if ui:
        definitions += [
            (
                "design",
                "UI Designer",
                "document",
                "Specify accessible interface and interaction contracts",
                ["requirements"],
            ),
            (
                "frontend",
                "Frontend Developer",
                "coding",
                "Implement the approved frontend acceptance criteria",
                ["design"],
            ),
        ]
    if software:
        definitions.append(
            (
                "backend",
                "Backend Developer",
                "coding",
                "Implement approved backend behavior with unit tests",
                ["requirements"],
            )
        )
    if any(word in text for word in ("database", "postgres", "storage", "data", "migration")):
        definitions.append(
            (
                "data",
                "Database Engineer",
                "document",
                "Specify database migrations, integrity and recovery checks",
                ["requirements"],
            )
        )
    if any(word in text for word in ("integration", "payment", "oauth", "external api")):
        definitions.append(
            (
                "integration",
                "Integration Engineer",
                "coding",
                "Implement approved integration contracts with isolated tests",
                ["requirements"],
            )
        )
    coding_keys = [row[0] for row in definitions if row[2] == "coding"]
    definitions.append(
        (
            "security",
            "Security Architect",
            "document",
            "Review delivered evidence and unresolved security risks",
            coding_keys or ["requirements"],
        )
    )
    tasks = []
    for key, role, kind, objective, dependencies in definitions:
        agent = agent_for(session, project.org_id, role)
        tasks.append(
            {
                "key": key,
                "agent_id": agent.id,
                "kind": kind,
                "objective": objective,
                "acceptance": [
                    "Saved source evidence and explicit unresolved assumptions",
                    "Meet approved requirements; no unauthorized external action",
                ],
                "depends_on": dependencies,
                "foundation_ids": [architecture] if architecture else [],
                "budget_micro": min(500000, project.budget_micro // max(1, len(definitions))),
            }
        )
    ids = {row["agent_id"] for row in tasks}
    if coding_keys:
        ids |= {agent_for(session, project.org_id, role).id for role in ("Code Reviewer", "QA Director")}
    content = {
        "planner": "policy-rules-v1 (deterministic planning, no AI call)",
        "requirement_version": requirement.version,
        "proposal_hash": proposal.content_hash,
        "mode": "live",
        "concurrency": min(2, settings().scheduler_concurrency),
        "allocations": [{"agent_id": agent_id, "slots": 1} for agent_id in sorted(ids)],
        "tasks": tasks,
        "foundation_task_ids": [task.id for task in foundation],
    }
    plan = m.StaffingPlan(
        id=uid(), org_id=project.org_id, project_id=project.id, content=content, content_hash=digest(content)
    )
    session.add(plan)
    session.flush()
    from .task_routing import prepare, setup_form

    content = deepcopy(content)
    form = setup_form(session, project)
    content["routing_mode"] = form["worker_mode"] if form else "automatic"
    prepare(session, plan, content)
    plan.content, plan.content_hash = content, digest(content)
    session.add(
        m.StaffingRevision(
            org_id=plan.org_id, plan_id=plan.id, version=1, content=content, content_hash=plan.content_hash
        )
    )
    return plan


def validate(session: Session, plan: m.StaffingPlan, content: dict) -> None:
    from .workflows import project_authority

    project = session.get(m.Project, plan.project_id)
    project_authority(session, project)
    proposal = session.get(m.Proposal, project.proposal_id)
    if (
        content["requirement_version"] != proposal.version
        or content["proposal_hash"] != proposal.content_hash
    ):
        raise ValueError("Requirement or proposal changed; revise project authority first")
    if content["mode"] == "mock" and not settings().mock_enabled:
        raise ValueError("Deterministic test adapter disabled")
    if content["concurrency"] > settings().scheduler_concurrency:
        raise ValueError("Plan exceeds configured scheduler concurrency")
    allocations = {row["agent_id"]: row["slots"] for row in content["allocations"]}
    if len(allocations) != len(content["allocations"]) or sum(allocations.values()) > 16:
        raise ValueError("Duplicate allocations or more than 16 logical slots")
    foundation = set(content["foundation_task_ids"])
    if foundation != set(plan.content["foundation_task_ids"]):
        raise ValueError("Existing foundation task references cannot be replaced")
    for task_id in foundation:
        task = session.get(m.Task, task_id)
        if not task or task.project_id != project.id or task.org_id != plan.org_id:
            raise ValueError("Foreign foundation task")
    for agent_id in allocations:
        agent = session.get(m.Agent, agent_id)
        if not agent or agent.org_id != plan.org_id:
            raise ValueError("Foreign allocation")
        check_agent(session, agent, "read_context", project)
    keys = {row["key"] for row in content["tasks"]}
    if len(keys) != len(content["tasks"]):
        raise ValueError("Duplicate task keys")
    for row in content["tasks"]:
        if row["agent_id"] not in allocations or not set(row["foundation_ids"]).issubset(foundation):
            raise ValueError("Task must use approved allocation and foundation")
        check_agent(
            session,
            session.get(m.Agent, row["agent_id"]),
            "propose_patch" if row["kind"] == "coding" else "write_artifact",
            project,
        )
        if not set(row["depends_on"]).issubset(keys):
            raise ValueError("Unknown dependency")
    pending = {row["key"]: set(row["depends_on"]) for row in content["tasks"]}
    while pending:
        ready = {key for key, dependencies in pending.items() if not dependencies}
        if not ready:
            raise ValueError("Dependency cycle")
        pending = {key: dependencies - ready for key, dependencies in pending.items() if key not in ready}
    if any(row["kind"] == "coding" for row in content["tasks"]):
        for role, tool in (("Code Reviewer", "review_diff"), ("QA Director", "run_tests")):
            agent = agent_for(session, plan.org_id, role)
            if agent.id not in allocations:
                raise ValueError("Coding requires independent reviewer and QA allocations")
            check_agent(session, agent, tool, project)
    cap = session.scalar(
        select(m.Budget).where(m.Budget.org_id == plan.org_id, m.Budget.scope == f"project:{project.id}")
    )
    if (
        not cap
        or sum(row["budget_micro"] for row in content["tasks"])
        > cap.limit_micro - cap.spent_micro - cap.reserved_micro
    ):
        raise ValueError("Task caps exceed remaining project budget")


def approve(session: Session, plan: m.StaffingPlan, user: m.User) -> None:
    from .task_routing import TaskRequirements

    validate(session, plan, plan.content)
    approval = m.Approval(
        id=uid(),
        org_id=plan.org_id,
        category="staffing",
        subject_id=plan.id,
        subject_hash=plan.content_hash,
        version=plan.version,
        owner_id=user.id,
        expires_at=now() + 2592000,
    )
    session.add(approval)
    task_ids = {row["key"]: uid() for row in plan.content["tasks"]}
    for row in plan.content["tasks"]:
        task = m.Task(
            id=task_ids[row["key"]],
            org_id=plan.org_id,
            project_id=plan.project_id,
            assigned_agent_id=row["agent_id"],
            kind=row["kind"],
            objective=row["objective"],
            acceptance=row["acceptance"],
            status="awaiting_repository" if row["kind"] == "coding" else "blocked",
            payload={
                "mode": plan.content["mode"],
                "staffing_plan_id": plan.id,
                "plan_key": row["key"],
                "routing_mode": plan.content.get("routing_mode", "automatic"),
                "task_requirements": {key: row[key] for key in TaskRequirements.model_fields if key in row},
                "project_version": session.get(m.Project, plan.project_id).version,
                "requirement_version": plan.content["requirement_version"],
            },
            budget_micro=row["budget_micro"],
        )
        session.add(task)
        session.flush()
        session.add(m.Budget(org_id=plan.org_id, scope=f"task:{task.id}", limit_micro=task.budget_micro))
        session.add(
            m.Message(
                org_id=plan.org_id,
                sender=user.id,
                recipient=task.assigned_agent_id,
                type="TASK_ASSIGNMENT",
                project_id=plan.project_id,
                task_id=task.id,
                correlation_id=plan.id,
                content={"objective": task.objective, "plan_version": plan.version},
                authorization=f"approval:{approval.id}",
            )
        )
    for row in plan.content["tasks"]:
        for dependency in [*[task_ids[key] for key in row["depends_on"]], *row["foundation_ids"]]:
            session.add(m.TaskDependency(task_id=task_ids[row["key"]], depends_on=dependency))
    session.add(
        m.Budget(
            org_id=plan.org_id,
            scope=f"staffing:{plan.id}",
            limit_micro=sum(row["budget_micro"] for row in plan.content["tasks"]),
        )
    )
    plan.status = "active"
    audit(
        session,
        plan.org_id,
        user.id,
        "staffing.approved",
        plan.id,
        {"version": plan.version, "tasks": task_ids},
        project_id=plan.project_id,
        authorization=f"approval:{approval.id}",
    )


def task_plan(session: Session, task: m.Task | None) -> m.StaffingPlan | None:
    return (
        session.get(m.StaffingPlan, task.payload["staffing_plan_id"])
        if task and task.payload.get("staffing_plan_id")
        else None
    )


def task_ready(session: Session, task: m.Task) -> bool:
    plan = task_plan(session, task)
    if plan:
        if plan.org_id != task.org_id or plan.project_id != task.project_id or plan.status != "active":
            return False
        approval = session.scalar(
            select(m.Approval).where(
                m.Approval.org_id == task.org_id,
                m.Approval.category == "staffing",
                m.Approval.subject_id == plan.id,
                m.Approval.version == plan.version,
            )
        )
        owner = session.get(m.User, approval.owner_id) if approval else None
        if (
            not approval
            or approval.expires_at <= now()
            or approval.subject_hash != digest(plan.content)
            or plan.content_hash != approval.subject_hash
            or not owner
            or not owner.enabled
            or owner.org_id != task.org_id
            or owner.role != "owner"
        ):
            return False
        if "task_requirements" in task.payload:
            from .task_routing import TaskRequirements

            source = next(
                (row for row in plan.content["tasks"] if row["key"] == task.payload["plan_key"]), None
            )
            if not source or task.payload["task_requirements"] != {
                key: source[key] for key in TaskRequirements.model_fields if key in source
            }:
                return False
            if task.payload["routing_mode"] != plan.content.get("routing_mode", "automatic"):
                return False
    return not session.scalar(
        select(m.Task.id)
        .join(m.TaskDependency, m.TaskDependency.depends_on == m.Task.id)
        .where(m.TaskDependency.task_id == task.id, m.Task.status != "completed")
    )


def participants(session: Session, workflow: m.Workflow) -> list[str]:
    if workflow.kind == "delivery_package":
        return []  # Deterministic artifact bookkeeping does not occupy an AI employee.
    if workflow.task_id:
        task = session.get(m.Task, workflow.task_id)
        ids = [task.assigned_agent_id]
        if workflow.kind == "coding":
            ids += list(
                session.scalars(
                    select(m.Agent.id).where(
                        m.Agent.org_id == workflow.org_id, m.Agent.role.in_(["Code Reviewer", "QA Director"])
                    )
                )
            )
        return sorted(set(ids))
    work = session.scalar(select(m.AgentWork).where(m.AgentWork.workflow_id == workflow.id))
    if work:
        return sorted(set(work.participants))
    # Consulting and CEO jobs are admitted conservatively against every participant.
    roles = (
        ["CEO"]
        if workflow.kind == "conversation"
        else [
            "CEO",
            "Business Analyst",
            "CTO",
            "Cloud Architect",
            "Security Architect",
            "FinOps Engineer",
            "CFO",
        ]
    )
    if workflow.kind == "consulting" and workflow.requirement_id:
        from .project_setup import consulting_steps

        steps = consulting_steps(session, session.get(m.Requirement, workflow.requirement_id))
        if steps:
            roles = ["CEO" if step in {"lead_intake", "proposal"} else step for step in steps]
    return list(
        session.scalars(select(m.Agent.id).where(m.Agent.org_id == workflow.org_id, m.Agent.role.in_(roles)))
    )


def admit(session: Session, workflow: m.Workflow) -> list[str] | None:
    lock_org(session, workflow.org_id)
    session.refresh(workflow)
    if workflow.status not in {"queued", "running"} or workflow.lease_until >= now():
        return None
    org = session.get(m.Organization, workflow.org_id)
    session.refresh(org)
    if org.paused:
        return None
    task = session.get(m.Task, workflow.task_id) if workflow.task_id else None
    if task and (
        task.status in {"paused", "cancelled", "completed", "failed"}
        or session.get(m.Project, task.project_id).status != "active"
        or not task_ready(session, task)
    ):
        return None
    active = list(
        session.scalars(
            select(m.Workflow).where(
                m.Workflow.org_id == workflow.org_id,
                m.Workflow.status == "running",
                m.Workflow.lease_until >= now(),
                m.Workflow.id != workflow.id,
            )
        )
    )
    if len(active) >= settings().scheduler_concurrency:
        return None
    ids = participants(session, workflow)
    plan = task_plan(session, task)
    slots = {row["agent_id"]: row["slots"] for row in plan.content["allocations"]} if plan else {}
    if plan:
        same_plan = [
            row
            for row in active
            if task_plan(session, session.get(m.Task, row.task_id) if row.task_id else None) == plan
        ]
        if len(same_plan) >= plan.content["concurrency"]:
            return None
    busy = Counter(
        agent_id for row in active for agent_id in (row.capacity_agents or participants(session, row))
    )
    if any(busy[agent_id] >= slots.get(agent_id, 1) for agent_id in ids):
        return None
    return ids


def pause_workflow(session: Session, workflow: m.Workflow, resume: bool) -> None:
    task = session.get(m.Task, workflow.task_id) if workflow.task_id else None
    if resume:
        if workflow.status != "paused":
            raise ValueError("Workflow is not paused")
        if session.scalar(
            select(m.ModelRun.id).where(
                m.ModelRun.workflow_id == workflow.id, m.ModelRun.status.in_(["started", "uncertain"])
            )
        ):
            raise ValueError("Resolve interrupted or uncertain provider usage before resuming")
        if session.scalar(
            select(m.Execution.id).where(
                m.Execution.task_id == workflow.task_id, m.Execution.status == "running"
            )
        ):
            raise ValueError("Reconcile interrupted runner execution before resuming")
        previous = workflow.wait_context.get("_paused", {})
        workflow.status = previous.get("status", "queued")
        workflow.wait_context = {
            key: value for key, value in workflow.wait_context.items() if key != "_paused"
        }
        workflow.deadline_at = max(workflow.deadline_at, now() + 1800)
        if task and task.status == "paused":
            task.status = previous.get("task_status", "in_progress")
    else:
        if workflow.status in {"completed", "cancelled", "paused"}:
            return
        workflow.wait_context = {
            **workflow.wait_context,
            "_paused": {
                "status": "queued" if workflow.status == "running" else workflow.status,
                "task_status": task.status if task else None,
            },
        }
        workflow.status = "paused"
        if task:
            task.status = "paused"
    workflow.lease_token, workflow.lease_until = uid(), 0


def evidence(session: Session, plan: m.StaffingPlan) -> dict:
    from .api_common import serialize
    from .task_routing import decision

    tasks = [
        task
        for task in session.scalars(select(m.Task).where(m.Task.project_id == plan.project_id))
        if task.payload.get("staffing_plan_id") == plan.id
    ]
    workflows = (
        list(session.scalars(select(m.Workflow).where(m.Workflow.task_id.in_([task.id for task in tasks]))))
        if tasks
        else []
    )
    quotes = []
    for row in plan.content["tasks"]:
        selection = decision(session, session.get(m.Project, plan.project_id), plan.content, row)
        candidates = selection["candidates"]
        quotes.append(
            {
                "key": row["key"],
                "selection": selection,
                "capabilities": selection["capabilities"],
                "token_allowance": {"input": selection["minimum_context_tokens"], "output": 2048},
                "estimate_micro": token_cost(
                    session.get(m.ModelConfig, candidates[0]["id"]), selection["minimum_context_tokens"], 2048
                )
                * (9 if row["kind"] == "coding" else 1)
                if candidates
                else None,
                "basis": "upper token allowance; coding includes up to three author/review rounds; actual gateway selection rechecked",
                "models": candidates,
            }
        )
    budget = session.scalar(
        select(m.Budget).where(m.Budget.org_id == plan.org_id, m.Budget.scope == f"staffing:{plan.id}")
    )
    return {
        **serialize(plan),
        "quotes": quotes,
        "estimated_micro": sum(row["estimate_micro"] for row in quotes)
        if all(row["estimate_micro"] is not None for row in quotes)
        else None,
        "tasks": [serialize(task) for task in tasks],
        "workflows": [serialize(row) for row in workflows],
        "budget": serialize(budget) if budget else None,
        "active_claims": sum(row.status == "running" and row.lease_until >= now() for row in workflows),
        "history": [
            serialize(row)
            for row in session.scalars(
                select(m.TaskAssignment)
                .where(m.TaskAssignment.task_id.in_([task.id for task in tasks]))
                .order_by(m.TaskAssignment.created_at)
            )
        ],
    }
