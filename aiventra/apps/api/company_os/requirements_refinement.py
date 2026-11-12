"""Versioned owner scope decisions on the existing draft and consulting workflow.

Model critiques are untrusted proposals. Only a separately authenticated owner can
sign the exact scope. Historical projects retain their original authorization.
"""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from sqlalchemy import select

from . import models as m
from .db import now, uid
from .project_setup import LeadAnalysis, for_requirement
from .schemas import Strict
from .security import audit, clean, digest

Text = Annotated[str, Field(min_length=1, max_length=2000)]
Items = Annotated[list[Text], Field(max_length=30)]


class Scope(Strict):
    text: str = Field(min_length=20, max_length=30000)
    goals: Items
    functional_requirements: Items
    nonfunctional_requirements: Items
    user_roles: Items
    user_journeys: Items
    constraints: Items
    dependencies: Items
    acceptance_criteria: Items
    risks: Items
    out_of_scope: Items
    open_questions: Items

    @field_validator("text")
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 20:
            raise ValueError("Requirements must contain at least 20 non-whitespace characters")
        return value

    @field_validator(
        "goals",
        "functional_requirements",
        "nonfunctional_requirements",
        "user_roles",
        "user_journeys",
        "constraints",
        "dependencies",
        "acceptance_criteria",
        "risks",
        "out_of_scope",
        "open_questions",
    )
    @classmethod
    def nonempty_items(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError("Specification items cannot be blank")
        return value

    @model_validator(mode="after")
    def bounded_document(self):
        if len(self.model_dump_json().encode()) > 100000:
            raise ValueError("Structured requirements must fit within 100 KB")
        return self


class Improvement(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,40}$")
    current_requirement: Text
    gap: Text
    recommendation: Text
    reason: Text
    complexity: Literal["low", "medium", "high"]
    business_impact: Text
    security_performance_impact: Text
    essential: bool


class RequirementCritique(LeadAnalysis):
    project_type: Text
    objectives: list[Text] = Field(max_length=15)
    requirements: Items
    questions: list[Text] = Field(max_length=8)
    assumptions: list[Text] = Field(max_length=15)
    acceptance_criteria: list[Text] = Field(min_length=1, max_length=20)
    improvements: list[Improvement] = Field(max_length=12)
    proposed_specification: Scope

    @field_validator("improvements")
    @classmethod
    def unique(cls, value):
        if len({item.id for item in value}) != len(value):
            raise ValueError("Improvement IDs must be unique")
        return value


class Decision(Strict):
    action: Literal["accept", "reject", "edit"]
    reason: Text
    edited_text: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def explicit_reason(cls, value):
        if not value.strip():
            raise ValueError("A decision needs a nonblank reason")
        return value


def enabled(row):
    return bool(row and row.data.get("form", {}).get("review_before_planning"))


def source(requirement):
    return {
        key: getattr(requirement, key)
        for key in (
            "org_id",
            "client_id",
            "title",
            "text",
            "answers",
            "constraints",
            "sensitivity",
            "budget_micro",
            "deadline",
        )
    }


def snapshot(row, requirement, scope, basis, decisions=None, answers=None):
    content = {
        "requirement_id": requirement.id,
        "version": requirement.version,
        "scope": clean(scope.model_dump()),
        "source": source(requirement),
        "attachments": row.data.get("attachments", []),
        "basis": basis,
        "decisions": clean(decisions or {}),
        "answers": clean(answers or {}),
    }
    return {**content, "scope_hash": digest(content), "created_at": now(), "reviews": []}


def initialize(row, requirement):
    # The original request remains intact in form and in the first snapshot.
    scope = Scope(
        text=requirement.text,
        goals=[requirement.title],
        functional_requirements=[requirement.text[:2000]],
        nonfunctional_requirements=[],
        user_roles=[],
        user_journeys=[],
        constraints=[str(value)[:2000] for value in requirement.constraints.values() if value],
        dependencies=[],
        acceptance_criteria=[],
        risks=[],
        out_of_scope=[],
        open_questions=[],
    )
    row.data = {
        **row.data,
        "refinement": {
            "current": snapshot(row, requirement, scope, "original_request"),
            "history": [],
            "approval_id": None,
        },
    }


def current(row, requirement):
    if not row.data.get("refinement"):
        raise PermissionError("Required scope-review record is missing")
    state = row.data["refinement"]
    entry = state["current"]
    content = {
        key: value for key, value in entry.items() if key not in {"scope_hash", "created_at", "reviews"}
    }
    if (
        row.org_id != requirement.org_id
        or row.client_id != requirement.client_id
        or entry["requirement_id"] != requirement.id
        or entry["version"] != requirement.version
        or digest(content) != entry["scope_hash"]
        or digest(entry["source"]) != digest(source(requirement))
        or entry["scope"]["text"] != requirement.text
        or entry["attachments"] != row.data.get("attachments", [])
    ):
        raise PermissionError("Requirements snapshot integrity changed; approval is invalid")
    return entry


def bound_history(state):
    if len(json.dumps(state, ensure_ascii=False).encode()) > 1000000:
        raise ValueError("Requirements review history reached 1 MB; create a new project draft")
    return state


def verify(session, row, requirement):
    entry = current(row, requirement)

    for attachment in entry["attachments"]:
        artifact = session.get(m.Artifact, attachment["id"])
        if (
            not artifact
            or artifact.org_id != row.org_id
            or artifact.sha256 != attachment["sha256"]
            or hashlib.sha256(artifact.content.encode()).hexdigest() != artifact.sha256
        ):
            raise PermissionError("Requirement document integrity changed")
    for review in entry["reviews"]:
        run = session.get(m.ModelRun, review["run_id"])
        workflow = session.get(m.Workflow, review["workflow_id"])
        step = session.scalar(
            select(m.WorkflowStep).where(
                m.WorkflowStep.workflow_id == review["workflow_id"], m.WorkflowStep.name == review["role"]
            )
        )
        if (
            not run
            or not workflow
            or not step
            or run.org_id != row.org_id
            or workflow.org_id != row.org_id
            or workflow.requirement_id != requirement.id
            or workflow.revision != review["source_version"]
            or run.workflow_id != workflow.id
            or run.step_name != review["role"]
            or run.status != "succeeded"
            or review["report_hash"] != digest(review["critique"])
            or digest(run.response) != review["report_hash"]
            or digest(step.result) != review["report_hash"]
            or review["evidence_category"]
            != ("FIXTURE_TESTED" if workflow.mode == "mock" else "MODEL_EXECUTED")
        ):
            raise PermissionError("Saved critique execution/checkpoint provenance changed")
    return entry


def assert_approved(session, requirement):
    row = for_requirement(session, requirement.id, requirement.org_id)
    if not enabled(row):
        return None  # Legacy authority remains subject to existing exact proposal gates.
    entry = verify(session, row, requirement)
    approval_id = row.data["refinement"].get("approval_id")
    approval = session.get(m.Approval, approval_id) if approval_id else None
    owner = session.get(m.User, approval.owner_id) if approval else None
    if (
        not approval
        or approval.category != "requirement_scope"
        or approval.org_id != requirement.org_id
        or approval.subject_id != requirement.id
        or approval.version != requirement.version
        or approval.subject_hash != entry["scope_hash"]
        or approval.expires_at <= now()
        or not owner
        or not owner.enabled
        or owner.role != "owner"
        or owner.org_id != requirement.org_id
        or owner.id != row.data["owner_id"]
    ):
        raise PermissionError(
            "Exact current requirements need valid owner sign-off before architecture or execution"
        )
    return approval


def review_items(entry):
    improvements, questions = [], []
    for review in entry["reviews"]:
        for item in review["critique"]["improvements"]:
            improvements.append({**item, "id": review["role"] + ":" + item["id"]})
        for index, question in enumerate(review["critique"]["questions"]):
            questions.append({"id": f"{review['role']}:{index}", "question": question})
    return improvements, questions


def save_review(session, row, requirement, workflow, role, result):
    entry = verify(session, row, requirement)
    run = session.scalar(
        select(m.ModelRun)
        .where(
            m.ModelRun.workflow_id == workflow.id,
            m.ModelRun.step_name == role,
            m.ModelRun.status == "succeeded",
        )
        .order_by(m.ModelRun.created_at.desc(), m.ModelRun.id.desc())
    )
    if not run or digest(run.response) != digest(result.model_dump()):
        raise PermissionError("Critique must reference a saved successful model execution")
    reviews = [
        *entry["reviews"],
        {
            "role": role,
            "run_id": run.id,
            "workflow_id": workflow.id,
            "source_version": requirement.version,
            "evidence_category": "FIXTURE_TESTED" if workflow.mode == "mock" else "MODEL_EXECUTED",
            "critique": result.model_dump(),
            "report_hash": digest(result.model_dump()),
            "created_at": now(),
        },
    ]
    row.data = {
        **row.data,
        "refinement": bound_history({**row.data["refinement"], "current": {**entry, "reviews": reviews}}),
    }
    row.version += 1
    audit(
        session,
        row.org_id,
        "consulting-worker",
        "requirements.critique_saved",
        requirement.id,
        {
            "role": role,
            "version": requirement.version,
            "run_id": run.id,
            "evidence_category": reviews[-1]["evidence_category"],
        },
    )


def revise(session, row, requirement, scope, decisions, answers, reconsider, user):
    from .consulting import enqueue_consulting

    entry = verify(session, row, requirement)
    state = row.data["refinement"]
    if len(state["history"]) >= 19:
        raise ValueError("Twenty scope versions reached; create a new project draft")
    if session.scalar(
        select(m.Project.id).join(m.Proposal).where(m.Proposal.requirement_id == requirement.id)
    ):
        raise PermissionError("Approved project changes must use existing versioned change controls")
    improvements, questions = review_items(entry)
    if not reconsider:
        if set(decisions) != {item["id"] for item in improvements}:
            raise ValueError("Accept, reject or edit every proposed improvement explicitly")
        if set(answers) != {item["id"] for item in questions} or any(
            not value.strip() for value in answers.values()
        ):
            raise ValueError("Answer every clarification question explicitly")
        for item in improvements:
            decision = decisions[item["id"]]
            text = decision.edited_text if decision.action == "edit" else item["recommendation"]
            if decision.action == "edit" and not text.strip():
                raise ValueError("An edited improvement needs replacement text")
            if (
                decision.action != "reject"
                and text not in scope.functional_requirements + scope.nonfunctional_requirements
            ):
                raise ValueError(
                    "Accepted or edited improvements must be explicitly included in the structured scope"
                )
    workflow = session.get(m.Workflow, row.data["workflow_id"])
    workflow.status, workflow.lease_token, workflow.lease_until = "cancelled", uid(), 0
    previous = {**entry, "approval_id": state.get("approval_id"), "retired_at": now()}
    requirement.version += 1
    requirement.text, requirement.answers = clean(scope.text), clean(answers)
    requirement.analysis = {} if reconsider else requirement.analysis
    requirement.status = "queued" if reconsider else "requirements_approval_pending"
    next_workflow = enqueue_consulting(session, requirement)
    session.flush()
    if not reconsider:
        next_workflow.status, next_workflow.step = "paused", 2
    revised = snapshot(
        row,
        requirement,
        scope,
        "reconsideration" if reconsider else "owner_authored",
        {key: value.model_dump() for key, value in decisions.items()},
        answers,
    )
    # Reviews remain versioned evidence in history; they do not certify changed scope.
    row.data = {
        **row.data,
        "workflow_id": next_workflow.id,
        "requirement_version": requirement.version,
        "refinement": bound_history(
            {"current": revised, "history": [*state["history"], previous], "approval_id": None}
        ),
    }
    row.version += 1


def approve(session, row, requirement, expected_hash, owner_authored, user):
    if (
        user.role != "owner"
        or not user.enabled
        or user.id != row.data["owner_id"]
        or user.org_id != row.org_id
    ):
        raise PermissionError("Only the enabled owning user can sign this requirements scope")
    entry = verify(session, row, requirement)
    state = row.data["refinement"]
    if expected_hash != entry["scope_hash"]:
        raise ValueError("Scope changed; review its exact current hash")
    if state.get("approval_id"):
        return assert_approved(session, requirement)
    if entry["reviews"] or entry["basis"] != "owner_authored" or not owner_authored:
        raise ValueError("Save your reviewed scope revision and acknowledge owner-authored sign-off first")
    scope = Scope.model_validate(entry["scope"])
    if (
        not scope.goals
        or not scope.functional_requirements
        or not scope.acceptance_criteria
        or scope.open_questions
    ):
        raise ValueError(
            "Sign-off requires goals, functional requirements, acceptance criteria and no open questions"
        )
    workflow = session.get(m.Workflow, row.data["workflow_id"])
    if workflow.status != "paused" or workflow.step != 2 or workflow.deadline_at <= now():
        raise ValueError("Scope is not at an unexpired approval checkpoint; save a fresh revision")
    approval = m.Approval(
        org_id=row.org_id,
        owner_id=user.id,
        category="requirement_scope",
        subject_id=requirement.id,
        subject_hash=expected_hash,
        version=requirement.version,
        selection="Owner-authored scope; model critique is advisory only",
        expires_at=now() + 2592000,
    )
    session.add(approval)
    session.flush()
    row.data = {**row.data, "refinement": {**state, "approval_id": approval.id}}
    row.version += 1
    workflow.status = "paused" if row.data["form"]["planning_mode"] == "manual" else "queued"
    requirement.status = "requirements_approved"
    from .artifacts import save_artifact

    document = save_artifact(
        session,
        row.org_id,
        f"Approved requirements version {requirement.version}",
        json.dumps(
            {
                "requirement_id": requirement.id,
                "scope_hash": expected_hash,
                "approval_id": approval.id,
                "scope": entry["scope"],
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    session.add(
        m.BusinessRecord(
            org_id=row.org_id,
            client_id=row.client_id,
            kind="knowledge",
            title=document.name,
            data={
                "requirement_id": requirement.id,
                "artifact_id": document.id,
                "excerpt": document.content,
                "trust": "Exact owner-approved requirements; model proposals are advisory",
                "source_version": requirement.version,
                "scope_hash": expected_hash,
                "approval_id": approval.id,
            },
        )
    )
    audit(
        session,
        row.org_id,
        user.id,
        "requirements.scope_approved",
        requirement.id,
        {
            "version": requirement.version,
            "scope_hash": expected_hash,
            "approval_id": approval.id,
            "basis": "owner_authored",
        },
        authorization=f"approval:{approval.id}",
    )
    return approval


def view(session, row):
    requirement = session.get(m.Requirement, row.data["requirement_id"])
    entry = verify(session, row, requirement)
    improvements, questions = review_items(entry)
    approval_id = row.data["refinement"].get("approval_id")
    approval = session.get(m.Approval, approval_id) if approval_id else None
    try:
        approved = bool(assert_approved(session, requirement))
        blocker = "" if approved else "Save and approve the exact reviewed requirements before architecture."
    except PermissionError as exc:
        approved, blocker = False, str(exc)
    return {
        **row.data["refinement"],
        "improvements": improvements,
        "questions": questions,
        "approved": approved,
        "approval_expires_at": approval.expires_at if approval else None,
        "blocker": blocker,
        "project_started": bool(
            session.scalar(
                select(m.Project.id)
                .join(m.Proposal)
                .where(m.Project.org_id == row.org_id, m.Proposal.requirement_id == requirement.id)
            )
        ),
    }
