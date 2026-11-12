import asyncio
import logging

from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from .artifacts import save_artifact
from .consulting import proposal_content, publish
from .db import SessionLocal, now, uid
from .finance import BudgetExceeded, estimate_rates
from .gateway import execute
from .memory import retrieve
from .models import (
    Agent,
    Approval,
    BusinessRecord,
    Message,
    Notification,
    Organization,
    Project,
    Proposal,
    Requirement,
    Task,
    TaskDependency,
    Workflow,
    WorkflowStep,
)
from .organization import agent_for
from .providers import LocalInferenceBusy, ProviderError, ProviderUnavailable, configured
from .schemas import Analysis, DocumentResult, ProposalContent, Recommendation
from .security import audit, check_agent, digest, redact

logger = logging.getLogger("aiventra")
CONSULTING_STEPS = [
    "intake",
    "CTO",
    "Cloud Architect",
    "Security Architect",
    "FinOps Engineer",
    "CFO",
    "proposal",
]


def claim(session: Session) -> Workflow | None:
    candidates = session.scalars(
        select(Workflow)
        .join(Organization, Organization.id == Workflow.org_id)
        .where(
            Organization.paused.is_(False),
            Workflow.status.in_(["queued", "running"]),
            Workflow.lease_until < now(),
        )
        .order_by(case((Workflow.status == "running", 0), else_=1), Workflow.created_at, Workflow.id)
        .limit(100)
    ).all()
    for workflow in candidates:
        from .staffing import admit

        agents = admit(session, workflow)
        if agents is None:
            session.rollback()
            continue
        token = uid()
        result = session.execute(
            update(Workflow)
            .where(
                Workflow.id == workflow.id,
                Workflow.lease_until < now(),
                Workflow.status.in_(["queued", "running"]),
            )
            .values(status="running", lease_until=now() + 180, lease_token=token, capacity_agents=agents)
        )
        session.commit()
        if result.rowcount:
            session.refresh(workflow)
            return workflow
    return None


def checkpoint(
    session: Session, workflow: Workflow, token: str, name: str, result: dict, complete=False
) -> None:
    org = session.get(Organization, workflow.org_id)
    session.refresh(org)
    if org.paused:
        raise PermissionError("Company paused before result checkpoint")
    current = session.scalar(
        select(Workflow.lease_token).where(Workflow.id == workflow.id, Workflow.status == "running")
    )
    if current != token:
        session.rollback()
        raise PermissionError("Workflow lease revoked; result cannot advance state")
    if not session.scalar(
        select(WorkflowStep).where(WorkflowStep.workflow_id == workflow.id, WorkflowStep.name == name)
    ):
        session.add(WorkflowStep(org_id=workflow.org_id, workflow_id=workflow.id, name=name, result=result))
    workflow.step += 1
    workflow.status = "completed" if complete else "queued"
    workflow.lease_until = 0


async def consulting_step(session: Session, workflow: Workflow, token: str) -> None:
    requirement = session.get(Requirement, workflow.requirement_id)
    if requirement.version != workflow.revision:
        workflow.status = "cancelled"
        return
    context = {
        "text": requirement.text,
        "constraints": requirement.constraints,
        "answers": requirement.answers,
        "deadline": requirement.deadline,
        "analysis": requirement.analysis,
    }
    evidence = session.scalars(
        select(BusinessRecord).where(
            BusinessRecord.org_id == workflow.org_id, BusinessRecord.kind == "knowledge"
        )
    ).all()
    context["source_evidence"] = [
        {**row.data, "excerpt": str(row.data.get("excerpt", ""))[:2000]}
        for row in evidence
        if row.data.get("requirement_id") == requirement.id
    ][:6]
    from .project_setup import LeadAnalysis, consulting_steps, for_requirement

    setup = for_requirement(session, requirement.id, workflow.org_id)
    if setup:
        form = setup.data["form"]
        context["owner_model_preferences"] = {
            key: form[key] for key in ("worker_mode", "worker_model_ids", "overrides")
        }
        context["specialist_policy"] = (
            "Choose only necessary optional specialist roles from Cloud Architect, Security Architect, FinOps Engineer. Business Analyst, CTO, Project Manager and CFO are mandatory. No model IDs, commands or approvals may be invented."
        )
        if form["source_project_id"]:
            reference = session.get(Project, form["source_project_id"])
            if (
                not reference
                or reference.org_id != workflow.org_id
                or reference.client_id != requirement.client_id
            ):
                raise PermissionError("Reference project authorization changed")
            context["reference_project"] = {
                "id": reference.id,
                "name": reference.name,
                "selected_alternative": reference.selected_alternative,
                "authorization": "Read-only reference; no code execution or inherited approval",
            }
    name = (consulting_steps(session, requirement) or CONSULTING_STEPS)[workflow.step]
    from .requirements_refinement import RequirementCritique, assert_approved, enabled, save_review

    refinement_review = enabled(setup) and name in {"lead_intake", "Business Analyst"}
    if enabled(setup) and not refinement_review:
        assert_approved(session, requirement)
        context["approved_scope_specification"] = setup.data["refinement"]["current"]["scope"]
    if name in {"intake", "lead_intake"} or refinement_review:
        agent = agent_for(session, workflow.org_id, "CEO" if name == "lead_intake" else "Business Analyst")
        if refinement_review:
            context["review_policy"] = (
                "Critique the untrusted owner request, constraints and documents. Identify ambiguity, "
                "contradictions, missing business/nonfunctional/security requirements and feasibility risks. "
                "Propose bounded improvements and a structured specification separately from confirmed scope. "
                "Never treat suggestions, assumptions or missing requirements as approved. Ask clarification "
                "questions. This is advisory requirements review only, with no commands or execution authority."
            )
        result = await execute(
            session,
            workflow,
            agent,
            name,
            RequirementCritique if refinement_review else LeadAnalysis if name == "lead_intake" else Analysis,
            context,
            sensitivity=requirement.sensitivity,
            capabilities={"structured", "reasoning"} if name == "lead_intake" else {"structured"},
        )
        if refinement_review:
            from .staffing import lock_org

            lock_org(session, workflow.org_id)
            session.refresh(workflow)
            session.refresh(requirement)
            session.refresh(setup)
            if workflow.revision != requirement.version:
                raise PermissionError("Requirements changed during critique")
        requirement.analysis = result.model_dump()
        requirement.status = "consulting"
        checkpoint(session, workflow, token, name, result.model_dump())
        if refinement_review:
            save_review(session, setup, requirement, workflow, name, result)
            if name == "Business Analyst":
                workflow.status = "paused"
                requirement.status = "requirements_revision_pending"
    elif name != "proposal":
        from .architecture_design import TechnicalDesign

        technical_design = name == "CTO" and enabled(setup)
        if name == "CFO":
            # Independent published evidence retrieval is read-only and cannot mutate infrastructure.
            from .research import fetch_source

            if workflow.mode == "live" and not context["source_evidence"]:
                urls = []
                text_lower = requirement.text.lower()
                if "google cloud" in text_lower:
                    urls.append("https://cloud.google.com/products/compute/pricing")
                if "lightning" in text_lower:
                    urls.append("https://lightning.ai/pricing")
                for url in urls:
                    try:
                        source = await fetch_source(url)
                    except Exception as exc:
                        source = {
                            "source_url": url,
                            "retrieved_at": now(),
                            "pricing_verified": False,
                            "error": type(exc).__name__,
                            "excerpt": "Source could not be retrieved; rates remain unknown",
                        }
                    session.add(
                        BusinessRecord(
                            org_id=workflow.org_id,
                            client_id=requirement.client_id,
                            kind="knowledge",
                            title="Independent published pricing research",
                            data={"requirement_id": requirement.id, **source},
                        )
                    )
                    context["source_evidence"].append({**source, "excerpt": source["excerpt"][:4000]})
            context["financial_comparison"] = estimate_rates(
                requirement.rates, ["Optimize current platform", "Hybrid migration", "Full migration"]
            )
            context["financial_policy"] = (
                "Interpret deterministic partial estimates. No invented rates or LLM arithmetic. Require complete cost evidence before claiming cheapest option."
            )
        agent = agent_for(session, workflow.org_id, name)
        context["role"] = name
        if technical_design:
            context["design_policy"] = (
                "Design only the exact approved scope. Propose at least two genuinely reasonable alternatives "
                "when they exist; otherwise explain the single option. Include HLD, LLD, API and database "
                "specifications, authentication, data flow, deployment topology, observability, verification, "
                "ADRs and explicit trade-offs. Prices and benchmarks remain unverified. No execution is authorized."
            )
        result = await execute(
            session,
            workflow,
            agent,
            name,
            TechnicalDesign if technical_design else Recommendation,
            context,
            quality=85,
            sensitivity=requirement.sensitivity,
            capabilities={"structured", "reasoning"},
        )
        if technical_design:
            from .staffing import lock_org

            lock_org(session, workflow.org_id)
            session.refresh(workflow)
            session.refresh(requirement)
            if workflow.revision != requirement.version:
                raise PermissionError("Requirements changed during architecture design")
            assert_approved(session, requirement)
        checkpoint(
            session, workflow, token, name, {"agent_id": agent.id, "role": name, **result.model_dump()}
        )
        if technical_design:
            from .architecture_design import record

            record(session, requirement, workflow, result)
        session.add(
            Message(
                org_id=workflow.org_id,
                sender=agent.id,
                recipient="CEO",
                type="ARCHITECTURE_PROPOSAL",
                correlation_id=requirement.id,
                content=result.model_dump(),
                expected_schema="TechnicalDesign" if technical_design else "Recommendation",
                authorization=f"consulting:{workflow.id}",
                acknowledged_at=now(),
            )
        )
    else:
        if enabled(setup):
            from .architecture_design import validate

            session.refresh(setup)
            design = setup.data.get("architecture_design")
            if not design:
                raise PermissionError("CTO design is required before Lead synthesis")
            context["approved_architecture_design"] = validate(session, requirement, design)
        contributions = [
            row.result
            for row in session.scalars(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_id == workflow.id,
                    WorkflowStep.name.not_in(["intake", "lead_intake"]),
                )
            ).all()
        ]
        context["contributions"] = contributions
        result = await execute(
            session,
            workflow,
            agent_for(session, workflow.org_id, "CEO"),
            name,
            ProposalContent,
            context,
            quality=85,
            sensitivity=requirement.sensitivity,
            capabilities={"structured", "reasoning"},
        )
        content = proposal_content(requirement, result, contributions)
        publish(session, requirement, content)
        checkpoint(session, workflow, token, name, content, complete=True)


def project_authority(session: Session, project: Project) -> Approval:
    approval = session.get(Approval, project.approval_id)
    proposal = session.get(Proposal, project.proposal_id)
    requirement = session.get(Requirement, proposal.requirement_id)
    from .requirements_refinement import assert_approved

    assert_approved(session, requirement)
    from .architecture_design import assert_project_design

    assert_project_design(session, project, proposal, requirement)
    if (
        approval.expires_at <= now()
        or approval.subject_hash != digest(proposal.content)
        or approval.version != proposal.version
        or proposal.version != requirement.version
    ):
        raise PermissionError("Project authorization expired or scope changed")
    return approval


async def document_step(session: Session, workflow: Workflow, token: str) -> None:
    task = session.get(Task, workflow.task_id)
    project = session.get(Project, task.project_id)
    project_authority(session, project)
    agent = session.get(Agent, task.assigned_agent_id)
    check_agent(session, agent, "write_artifact", project)
    proposal = session.get(Proposal, project.proposal_id)
    from .architecture_design import selected_context

    result = await execute(
        session,
        workflow,
        agent,
        "document",
        DocumentResult,
        {
            "objective": task.objective,
            "acceptance": task.acceptance,
            "project": proposal.content,
            "owner_selected_architecture": selected_context(proposal, project),
            "project_memory": [
                {**row, "excerpt": str(row.get("excerpt", ""))[:1000]}
                for row in retrieve(session, project.org_id, project.id)[:2]
            ],
        },
        project=project,
    )
    # Provider completion does not override a pause issued while a request was in flight.
    session.refresh(project)
    session.refresh(agent)
    check_agent(session, agent, "write_artifact", project)
    artifact = save_artifact(
        session,
        workflow.org_id,
        result.title,
        result.content,
        project_id=project.id,
        task_id=task.id,
        agent_id=agent.id,
    )
    task.evidence = {
        "artifact_id": artifact.id,
        "sha256": artifact.sha256,
        "verification": "schema and artifact integrity; document requires owner assessment",
        "mode": workflow.mode,
        "checks": result.acceptance_checks,
    }
    task.status = "completed"
    session.execute(
        update(Message)
        .where(
            Message.org_id == workflow.org_id,
            Message.task_id == task.id,
            Message.recipient == agent.id,
            Message.type == "delivery_case_assignment",
            Message.status == "delivered",
        )
        .values(status="acknowledged", acknowledged_at=now())
    )
    checkpoint(session, workflow, token, "document", task.evidence, complete=True)
    audit(
        session,
        workflow.org_id,
        agent.id,
        "task.artifact_saved",
        task.id,
        task.evidence,
        project_id=project.id,
        task_id=task.id,
        authorization=f"approval:{project.approval_id}",
    )


def schedule(session: Session) -> None:
    tasks = session.scalars(
        select(Task)
        .join(Project, Project.id == Task.project_id)
        .join(Organization, Organization.id == Task.org_id)
        .where(
            Project.status == "active",
            Organization.paused.is_(False),
            Task.kind == "document",
            Task.status.in_(["ready", "blocked"]),
        )
    ).all()
    for task in tasks:
        from .staffing import task_ready

        if not task_ready(session, task):
            continue
        dependencies = session.scalars(
            select(Task)
            .join(TaskDependency, Task.id == TaskDependency.depends_on)
            .where(TaskDependency.task_id == task.id)
        ).all()
        if any(dependency.status != "completed" for dependency in dependencies):
            continue
        if session.scalar(select(Workflow).where(Workflow.task_id == task.id)):
            continue
        won = session.execute(
            update(Task)
            .where(Task.id == task.id, Task.status.in_(["ready", "blocked"]))
            .values(status="in_progress")
        )
        if won.rowcount != 1:
            continue
        session.add(
            Workflow(
                org_id=task.org_id, task_id=task.id, kind="document", mode=task.payload.get("mode", "live")
            )
        )
    session.commit()


def wake_waiting(session: Session):
    from .gateway import eligible_models, review_candidates

    for workflow in session.scalars(
        select(Workflow).where(Workflow.status.in_(["waiting_for_provider", "waiting_for_free_provider"]))
    ):
        config = workflow.wait_context
        if workflow.deadline_at <= now():
            workflow.status, workflow.last_error = (
                "needs_attention",
                "Provider wait exceeded workflow deadline",
            )
            session.add(
                Notification(
                    org_id=workflow.org_id,
                    severity="warning",
                    title=workflow.last_error,
                    subject_id=workflow.id,
                )
            )
            audit(session, workflow.org_id, "worker", "workflow.provider_wait_expired", workflow.id)
            continue
        if workflow.status == "waiting_for_free_provider":
            continue  # Credentials/configuration changes cannot authorize automatic free-policy resumption.
        if not config:
            continue
        candidates = eligible_models(
            session,
            workflow.org_id,
            workflow.mode,
            set(config["capabilities"]),
            config["quality"],
            config["sensitivity"],
            config["context_tokens"],
            config["policy"],
            config.get("task_class"),
        )
        from .model_routing import apply_policies

        agent = session.get(Agent, config["agent_id"])
        if not agent or not agent.enabled:
            continue
        candidates = apply_policies(
            session, agent, config.get("project_id"), candidates, config.get("model_override")
        )
        candidates = review_candidates(
            session,
            candidates,
            config.get("review_against", []),
            config.get("review_policy", "prefer_provider"),
        )
        if any(configured(provider) for _, provider in candidates):
            changed = session.execute(
                update(Workflow)
                .where(Workflow.id == workflow.id, Workflow.status == "waiting_for_provider")
                .values(status="queued", last_error="")
            )
            if changed.rowcount:
                if workflow.task_id:
                    session.get(Task, workflow.task_id).status = "in_progress"
                audit(
                    session,
                    workflow.org_id,
                    "worker",
                    "workflow.provider_ready",
                    workflow.id,
                    authorization="configuration became eligible",
                )
    session.commit()


async def tick(factory=SessionLocal) -> bool:
    with factory() as session:
        wake_waiting(session)
        schedule(session)
        workflow = claim(session)
        if not workflow:
            return False
        token = workflow.lease_token

        async def renew_lease():
            while True:
                await asyncio.sleep(20)
                with factory() as lease_session:
                    lease_session.execute(
                        update(Workflow)
                        .where(
                            Workflow.id == workflow.id,
                            Workflow.status == "running",
                            Workflow.lease_token == token,
                        )
                        .values(lease_until=now() + 180)
                    )
                    lease_session.commit()

        renewal = asyncio.create_task(renew_lease())
        from .observability import correlation_id

        marker = correlation_id.set(workflow.id)
        try:
            if workflow.deadline_at < now() or workflow.attempts >= workflow.max_attempts:
                raise TimeoutError("Workflow time or iteration limit reached")
            if workflow.kind == "consulting":
                await consulting_step(session, workflow, token)
            elif workflow.kind == "conversation":
                from .conversations import conversation_step

                await conversation_step(session, workflow, token)
            elif workflow.kind == "document":
                await document_step(session, workflow, token)
            elif workflow.kind == "coding":
                from .engineering import coding_step

                await coding_step(session, workflow, token)
            elif workflow.kind == "agent_work":
                from .agent_work import work_step

                await work_step(session, workflow, token)
            elif workflow.kind == "delivery_package":
                from .packages import package_step

                await package_step(session, workflow, token)
            else:
                raise ValueError("Unknown workflow kind")
            session.commit()
        except LocalInferenceBusy as exc:
            session.rollback()
            workflow = session.get(Workflow, workflow.id)
            if workflow.lease_token == token:
                workflow.status, workflow.lease_until = "queued", now() + 2
                workflow.last_error = str(exc)
                session.commit()
        except ProviderUnavailable as exc:
            session.rollback()
            workflow = session.get(Workflow, workflow.id)
            if workflow.lease_token != token:
                return True
            from .providers import FreeProviderUnavailable

            waiting_status = (
                "waiting_for_free_provider"
                if isinstance(exc, FreeProviderUnavailable)
                else "waiting_for_provider"
            )
            workflow.status, workflow.lease_until = waiting_status, 0
            workflow.wait_context, workflow.last_error = exc.context, str(exc)
            from .agent_runtime import transition

            waiting_agent = session.get(Agent, exc.context["agent_id"])
            transition(
                session,
                workflow,
                waiting_agent,
                waiting_status.upper(),
                exc.context.get("step_name", ""),
                detail={"reason": str(exc), "spending_mode": exc.context.get("spending_mode")},
            )
            if workflow.requirement_id:
                session.get(Requirement, workflow.requirement_id).status = waiting_status
            if workflow.task_id:
                session.get(Task, workflow.task_id).status = waiting_status
            audit(
                session,
                workflow.org_id,
                "worker",
                "workflow." + waiting_status,
                workflow.id,
                {"routing": exc.context},
                task_id=workflow.task_id,
                authorization="no eligible configured provider",
            )
            session.add(
                Notification(
                    org_id=workflow.org_id, severity="warning", title=str(exc), subject_id=workflow.id
                )
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            workflow = session.get(Workflow, workflow.id)
            if workflow.lease_token != token:
                return True
            workflow.attempts += 1
            workflow.lease_until = 0
            uncertain = isinstance(exc, ProviderError) and exc.uncertain
            workflow.status = (
                "needs_attention"
                if uncertain
                or isinstance(exc, (BudgetExceeded, PermissionError))
                or workflow.attempts >= workflow.max_attempts
                else "queued"
            )
            workflow.last_error = redact(str(exc))[:1000]
            from .agent_runtime import workflow_state

            workflow_state(
                session,
                workflow,
                "BLOCKED" if workflow.status == "needs_attention" else "FAILED",
                {"error": workflow.last_error},
            )
            if workflow.status == "needs_attention":
                session.add(
                    Notification(
                        org_id=workflow.org_id,
                        severity="error",
                        title=workflow.last_error[:200],
                        subject_id=workflow.id,
                    )
                )
                if workflow.task_id:
                    session.get(Task, workflow.task_id).status = "blocked"
                if isinstance(exc, BudgetExceeded) and workflow.task_id:
                    task = session.get(Task, workflow.task_id)
                    session.get(Project, task.project_id).status = "budget_paused"
                if isinstance(exc, BudgetExceeded) and workflow.requirement_id:
                    session.get(Requirement, workflow.requirement_id).status = "budget_paused"
            audit(
                session,
                workflow.org_id,
                "worker",
                "workflow.failure",
                workflow.id,
                {"error": workflow.last_error, "attempt": workflow.attempts},
                authorization="durable worker",
            )
            session.commit()
            logger.warning(
                "workflow.failure", extra={"workflow_id": workflow.id, "error_type": type(exc).__name__}
            )
        finally:
            renewal.cancel()
            await asyncio.gather(renewal, return_exceptions=True)
            correlation_id.reset(marker)
        return True


async def run() -> None:
    from .health import heartbeat
    from .observability import configure_logging

    configure_logging()
    worker_id = uid()

    async def pulse():
        while True:
            with SessionLocal() as session:
                heartbeat(session, worker_id)
            await asyncio.sleep(5)

    pulse_task = asyncio.create_task(pulse())

    async def work_loop():
        while True:
            active = await tick()
            await asyncio.sleep(0.2 if active else 1)

    from .config import settings

    work_tasks = [asyncio.create_task(work_loop()) for _ in range(settings().scheduler_concurrency)]
    last_inspection = 0
    try:
        while True:
            if now() - last_inspection >= 30:
                from .monitoring import inspect

                with SessionLocal() as session:
                    for org in session.scalars(select(Organization)).all():
                        inspect(session, org.id)
                        from .semantic_memory import backfill

                        backfill(session, org.id)
                from .semantic_memory import index_pending

                def index_memory():
                    with SessionLocal() as index_session:
                        index_pending(index_session)

                await asyncio.to_thread(index_memory)
                last_inspection = now()
            await asyncio.sleep(1)
    finally:
        pulse_task.cancel()
        for work_task in work_tasks:
            work_task.cancel()
        await asyncio.gather(pulse_task, *work_tasks, return_exceptions=True)
        with SessionLocal() as session:
            heartbeat(session, worker_id, "stopped")


if __name__ == "__main__":
    asyncio.run(run())
