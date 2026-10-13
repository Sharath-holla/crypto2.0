from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import now, uid
from .finance import estimate_rates
from .models import (
    Approval,
    Budget,
    Meeting,
    Message,
    Milestone,
    Project,
    Proposal,
    Requirement,
    Task,
    TaskDependency,
    User,
    Workflow,
)
from .organization import agent_for
from .schemas import Approve, ProposalContent
from .security import audit, digest


def proposal_content(requirement: Requirement, content: ProposalContent, contributions: list[dict]) -> dict:
    data = content.model_dump()
    names = [alternative.name for alternative in content.alternatives]
    if len(names) != len(set(names)) or content.recommendation not in names:
        raise ValueError("Proposal must select one uniquely named alternative")
    data.update(
        {
            "cost_comparison": estimate_rates(requirement.rates, names),
            "mode": requirement.mode,
            "pricing_status": "Incomplete until all applicable cost components are validated",
            "specialist_contributions": contributions,
            "authorization": "No implementation or external changes authorized before approval",
        }
    )
    return data


def publish(session: Session, requirement: Requirement, content: dict) -> Proposal:
    from .architecture_design import bind_proposal
    from .requirements_refinement import assert_approved

    scope_approval = assert_approved(session, requirement)
    if scope_approval:
        from .project_setup import for_requirement

        scope = for_requirement(session, requirement.id, requirement.org_id).data["refinement"]["current"][
            "scope"
        ]
        content = {
            **content,
            "requirements_signoff": {
                "approval_id": scope_approval.id,
                "version": requirement.version,
                "scope_hash": scope_approval.subject_hash,
                "specification": scope,
            },
            "confirmed_requirements": list(
                dict.fromkeys(
                    [
                        *scope["functional_requirements"],
                        *scope["nonfunctional_requirements"],
                        *content["confirmed_requirements"],
                    ]
                )
            ),
            "acceptance_criteria": list(
                dict.fromkeys(
                    [
                        *scope["acceptance_criteria"],
                        *content["acceptance_criteria"],
                    ]
                )
            ),
        }
    content = bind_proposal(session, requirement, content)
    owner_authored = content.get("authorship") == "owner"
    proposal = Proposal(
        id=uid(),
        org_id=requirement.org_id,
        requirement_id=requirement.id,
        version=requirement.version,
        content=content,
        content_hash=digest(content),
    )
    session.add(proposal)
    requirement.status = "awaiting_approval"
    meeting = Meeting(
        org_id=requirement.org_id,
        requirement_id=requirement.id,
        mode=requirement.mode,
        agenda="Owner-authored plan submission; no AI meeting or independent analysis occurred."
        if owner_authored
        else "Compare architectures, cost evidence and risks; one independent contribution per specialist, one synthesis.",
        contributions=content["specialist_contributions"],
        decision={"recommendation": content["recommendation"], "status": "owner decision required"},
    )
    session.add(meeting)
    session.add(
        Message(
            org_id=requirement.org_id,
            sender=content["author_id"]
            if owner_authored
            else agent_for(session, requirement.org_id, "CEO").id,
            recipient="Human owner",
            type="APPROVAL_REQUEST",
            correlation_id=requirement.id,
            content={"proposal_id": proposal.id, "version": proposal.version, "hash": proposal.content_hash},
            authorization="consulting only",
        )
    )
    audit(
        session,
        requirement.org_id,
        content["author_id"] if owner_authored else "consulting-worker",
        "proposal.published",
        proposal.id,
        {"mode": requirement.mode, "version": proposal.version},
        authorization="bounded consultation",
    )
    return proposal


def approve_proposal(session: Session, proposal: Proposal, request: Approve, user: User) -> Project:
    if user.role != "owner":
        raise PermissionError("Only owner approval is implemented")
    requirement = session.get(Requirement, proposal.requirement_id)
    from .requirements_refinement import assert_approved

    assert_approved(session, requirement)
    if (
        proposal.version != requirement.version
        or request.version != proposal.version
        or request.content_hash != digest(proposal.content)
    ):
        raise ValueError("Stale proposal version or content hash")
    if request.content_hash != proposal.content_hash:
        raise ValueError("Proposal integrity mismatch")
    if request.selection not in [alternative["name"] for alternative in proposal.content["alternatives"]]:
        raise ValueError("Unknown solution alternative")
    existing = session.scalar(select(Project).where(Project.proposal_id == proposal.id))
    if existing:
        if existing.selected_alternative != request.selection:
            raise ValueError("Already approved with a different alternative; revise scope")
        from .architecture_design import assert_project_design

        assert_project_design(session, existing, proposal, requirement)
        return existing
    if proposal.status != "awaiting_approval":
        raise ValueError("Proposal is not awaiting approval")
    from .architecture_design import approve_selection

    approve_selection(session, proposal, requirement, user, request.selection)
    approval = Approval(
        id=uid(),
        org_id=user.org_id,
        owner_id=user.id,
        category="proposal",
        subject_id=proposal.id,
        subject_hash=proposal.content_hash,
        version=proposal.version,
        selection=request.selection,
        expires_at=now() + 2592000,
    )
    session.add(approval)
    session.flush()
    project = Project(
        id=uid(),
        org_id=user.org_id,
        client_id=requirement.client_id,
        proposal_id=proposal.id,
        approval_id=approval.id,
        name=requirement.title,
        selected_alternative=request.selection,
        budget_micro=requirement.budget_micro,
    )
    session.add(project)
    session.flush()
    from .project_setup import attach_project_sources

    attach_project_sources(session, project, requirement)
    session.add(Budget(org_id=user.org_id, scope=f"project:{project.id}", limit_micro=project.budget_micro))
    roles = ["CTO", "Backend Team Lead", "QA Director", "Release Manager"]
    objectives = [
        "Write architecture assessment and unresolved assumptions",
        "Prepare implementation tasks and repository access requirements",
        "Create independent test plan and acceptance checklist",
        "Prepare deployment and rollback plan; request environment approval",
    ]
    previous = None
    for index, objective in enumerate(objectives):
        milestone = Milestone(
            id=uid(),
            org_id=user.org_id,
            project_id=project.id,
            name=proposal.content["milestones"][min(index, len(proposal.content["milestones"]) - 1)],
            position=index,
        )
        session.add(milestone)
        session.flush()
        task = Task(
            id=uid(),
            org_id=user.org_id,
            project_id=project.id,
            milestone_id=milestone.id,
            assigned_agent_id=agent_for(session, user.org_id, roles[index]).id,
            objective=objective,
            acceptance=[
                "Saved artifact with hash",
                "Explicit assumptions and evidence",
                "No unauthorized external operation",
            ],
            payload={"mode": requirement.mode},
            status="ready" if index == 0 else "blocked",
        )
        session.add(task)
        session.flush()
        if previous:
            session.add(TaskDependency(task_id=task.id, depends_on=previous))
        previous = task.id
        session.add(
            Message(
                org_id=user.org_id,
                sender=agent_for(session, user.org_id, "Project Manager").id,
                recipient=task.assigned_agent_id,
                project_id=project.id,
                task_id=task.id,
                type="TASK_ASSIGNMENT",
                correlation_id=project.id,
                content={"objective": objective},
                authorization=f"approval:{approval.id}",
            )
        )
    proposal.status, requirement.status = "approved", "approved"
    from .staffing import suggest

    suggest(session, project)
    audit(
        session,
        user.org_id,
        user.id,
        "proposal.approved",
        proposal.id,
        {"selection": request.selection, "version": request.version},
        project_id=project.id,
        authorization=f"approval:{approval.id}",
    )
    return project


def enqueue_consulting(session: Session, requirement: Requirement) -> Workflow:
    workflow = Workflow(
        org_id=requirement.org_id,
        requirement_id=requirement.id,
        mode=requirement.mode,
        revision=requirement.version,
    )
    session.add(workflow)
    if not session.scalar(select(Budget).where(Budget.scope == f"requirement:{requirement.id}")):
        session.add(
            Budget(
                org_id=requirement.org_id,
                scope=f"requirement:{requirement.id}",
                limit_micro=requirement.budget_micro,
            )
        )
    return workflow
