"""Versioned CTO design evidence and exact owner selection on existing proposals."""

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from . import models as m
from .artifacts import save_artifact
from .db import now
from .project_setup import for_requirement
from .requirements_refinement import Items, Text, assert_approved
from .schemas import Recommendation, Strict
from .security import audit, digest


class DesignOption(Strict):
    name: str = Field(min_length=1, max_length=120)
    architecture: str = Field(min_length=20, max_length=8000)
    high_level_design: str = Field(min_length=20, max_length=16000)
    low_level_design: str = Field(min_length=20, max_length=16000)
    api_specification: str = Field(min_length=20, max_length=16000)
    database_schema: str = Field(min_length=20, max_length=16000)
    authentication: Text
    data_flow: Text
    deployment_topology: Text
    observability: Text
    verification_plan: Text
    complexity: Text
    reliability: Text
    maintainability: Text
    performance: Text
    resource_requirements: Text
    cost_notes: Text
    security_impact: Text
    advantages: Items
    disadvantages: Items
    architecture_decisions: Items
    unresolved_assumptions: Items


class TechnicalDesign(Recommendation):
    options: list[DesignOption] = Field(min_length=1, max_length=5)
    recommended_option: str = Field(min_length=1, max_length=120)
    single_option_reason: str = Field(default="", max_length=2000)
    benchmarks_verified: Literal[False] = False
    cloud_prices_verified: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self):
        names = [option.name for option in self.options]
        if len(names) != len(set(names)) or self.recommended_option not in names:
            raise ValueError("Design needs unique options and a recommendation from those options")
        if len(names) == 1 and not self.single_option_reason.strip():
            raise ValueError(
                "A single architecture needs an explicit explanation of the lack of alternatives"
            )
        if len(self.model_dump_json().encode()) > 100000:
            raise ValueError("Technical design must fit within 100 KB")
        return self


def approved_scope(session, requirement):
    approval = assert_approved(session, requirement)
    if not approval:
        return None, None
    return for_requirement(session, requirement.id, requirement.org_id), approval


def record(session, requirement, workflow, result):
    row, approval = approved_scope(session, requirement)
    run = session.scalar(
        select(m.ModelRun)
        .where(
            m.ModelRun.workflow_id == workflow.id,
            m.ModelRun.step_name == "CTO",
            m.ModelRun.status == "succeeded",
        )
        .order_by(m.ModelRun.created_at.desc(), m.ModelRun.id.desc())
    )
    if not run or digest(TechnicalDesign.model_validate(run.response).model_dump()) != digest(
        result.model_dump()
    ):
        raise PermissionError("Architecture requires a saved successful CTO execution")
    documents = []
    for option in result.options:
        artifact = save_artifact(
            session,
            row.org_id,
            f"Design v{requirement.version}: {option.name}",
            json.dumps(option.model_dump(), ensure_ascii=False, indent=2),
            kind="architecture_design",
        )
        documents.append({"option": option.name, "artifact_id": artifact.id, "sha256": artifact.sha256})
    core = {
        "requirement_id": requirement.id,
        "requirement_version": requirement.version,
        "scope_hash": approval.subject_hash,
        "run_id": run.id,
        "workflow_id": workflow.id,
        "basis": "FIXTURE_TESTED" if run.cost_basis == "mock_no_charge" else "MODEL_EXECUTED",
        "design": result.model_dump(),
        "documents": documents,
    }
    previous = row.data.get("architecture_design")
    history = [*row.data.get("architecture_history", []), *([previous] if previous else [])]
    if len(history) >= 20:
        raise ValueError("Architecture history limit reached; use a new project draft")
    row.data = {
        **row.data,
        "architecture_design": {**core, "manifest_hash": digest(core), "created_at": now()},
        "architecture_history": history,
    }
    row.version += 1
    audit(
        session,
        row.org_id,
        "consulting-worker",
        "architecture.design_saved",
        requirement.id,
        {
            "version": requirement.version,
            "manifest_hash": digest(core),
            "run_id": run.id,
            "basis": core["basis"],
        },
    )
    return row.data["architecture_design"]


def _validate(session, requirement, manifest):
    _row, approval = approved_scope(session, requirement)
    if not approval:
        raise PermissionError("Architecture evidence requires an approved versioned scope")
    core = {key: value for key, value in manifest.items() if key not in {"manifest_hash", "created_at"}}
    if (
        manifest["requirement_id"] != requirement.id
        or manifest["requirement_version"] != requirement.version
        or manifest["scope_hash"] != approval.subject_hash
        or digest(core) != manifest["manifest_hash"]
    ):
        raise PermissionError("Architecture design belongs to changed requirements or has changed content")
    for document in manifest["documents"]:
        artifact = session.get(m.Artifact, document["artifact_id"])
        if (
            not artifact
            or artifact.org_id != requirement.org_id
            or artifact.sha256 != document["sha256"]
            or hashlib.sha256(artifact.content.encode()).hexdigest() != document["sha256"]
        ):
            raise PermissionError("Architecture artifact integrity changed")
    if manifest["basis"] == "OWNER_AUTHORED_LIMITED_PLAN":
        if (
            manifest.get("run_id")
            or manifest.get("workflow_id")
            or len(manifest["documents"]) != 1
            or manifest["documents"][0]["option"] != "Owner-authored plan"
        ):
            raise PermissionError("Owner-authored design cannot claim model evidence")
        return manifest
    options = TechnicalDesign.model_validate(manifest["design"]).options
    if [document["option"] for document in manifest["documents"]] != [
        option.name for option in options
    ] or any(
        digest(json.loads(session.get(m.Artifact, document["artifact_id"]).content))
        != digest(option.model_dump())
        for document, option in zip(manifest["documents"], options, strict=True)
    ):
        raise PermissionError("Architecture documents do not match the saved options")
    run = session.get(m.ModelRun, manifest["run_id"])
    workflow = session.get(m.Workflow, manifest["workflow_id"])
    step = session.scalar(
        select(m.WorkflowStep).where(
            m.WorkflowStep.workflow_id == manifest["workflow_id"], m.WorkflowStep.name == "CTO"
        )
    )
    if (
        not run
        or not workflow
        or not step
        or run.org_id != requirement.org_id
        or workflow.org_id != requirement.org_id
        or workflow.requirement_id != requirement.id
        or workflow.revision != requirement.version
        or run.workflow_id != workflow.id
        or run.step_name != "CTO"
        or run.status != "succeeded"
        or step.result.get("agent_id") != run.agent_id
        or manifest["basis"] != ("FIXTURE_TESTED" if run.cost_basis == "mock_no_charge" else "MODEL_EXECUTED")
        or digest(TechnicalDesign.model_validate(run.response).model_dump()) != digest(manifest["design"])
        or digest({key: value for key, value in step.result.items() if key not in {"agent_id", "role"}})
        != digest(manifest["design"])
    ):
        raise PermissionError("Architecture execution/checkpoint provenance changed")
    return manifest


def validate(session, requirement, manifest):
    try:
        return _validate(session, requirement, manifest)
    except (KeyError, TypeError, ValueError):
        raise PermissionError(
            "Architecture evidence is malformed or changed; review a fresh design"
        ) from None


def bind_proposal(session, requirement, content):
    row, approval = approved_scope(session, requirement)
    if not row:
        return content
    if content.get("authorship") == "owner":
        artifact = save_artifact(
            session,
            row.org_id,
            f"Owner architecture plan v{requirement.version}",
            content["current_architecture"],
            kind="architecture_design",
        )
        core = {
            "requirement_id": requirement.id,
            "requirement_version": requirement.version,
            "scope_hash": approval.subject_hash,
            "basis": "OWNER_AUTHORED_LIMITED_PLAN",
            "run_id": None,
            "workflow_id": None,
            "design": {
                "limitations": [
                    "Owner-authored architecture only; no CTO analysis, complete HLD/LLD or independent validation is implied."
                ]
            },
            "documents": [
                {"option": "Owner-authored plan", "artifact_id": artifact.id, "sha256": artifact.sha256}
            ],
        }
        manifest = {**core, "manifest_hash": digest(core), "created_at": now()}
    else:
        manifest = row.data.get("architecture_design")
        if not manifest:
            raise PermissionError("A saved CTO technical design is required before proposal publication")
        validate(session, requirement, manifest)
        options = manifest["design"]["options"]
        if content["recommendation"] not in {option["name"] for option in options}:
            raise ValueError("Lead recommendation must select a saved CTO architecture option")
        content = {
            **content,
            "alternatives": [
                {
                    key: option[key]
                    for key in ("name", "architecture", "advantages", "disadvantages", "reliability")
                }
                for option in options
            ],
        }
        from .finance import estimate_rates

        content["cost_comparison"] = estimate_rates(requirement.rates, [option["name"] for option in options])
    return {**content, "architecture_manifest": manifest}


def selection_hash(manifest, selection):
    return digest(
        {
            "manifest_hash": manifest["manifest_hash"],
            "scope_hash": manifest["scope_hash"],
            "selection": selection,
        }
    )


def selected_context(proposal, project):
    """Use the owner-selected design, never silently reselect the Lead recommendation."""
    manifest = proposal.content.get("architecture_manifest")
    if not manifest:
        return None
    design = next(
        (
            option
            for option in manifest["design"].get("options", [])
            if option["name"] == project.selected_alternative
        ),
        manifest["design"],
    )
    return {
        "selection": project.selected_alternative,
        "manifest_hash": manifest["manifest_hash"],
        "scope_hash": manifest["scope_hash"],
        "basis": manifest["basis"],
        "design": design,
    }


def approve_selection(session, proposal, requirement, user, selection):
    manifest = proposal.content.get("architecture_manifest")
    if not manifest:
        if assert_approved(session, requirement):
            raise PermissionError("Reviewed requirements require saved architecture evidence")
        return None  # Previously approved proposals keep their original contract.
    validate(session, requirement, manifest)
    approval = m.Approval(
        org_id=user.org_id,
        owner_id=user.id,
        category="architecture_design",
        subject_id=proposal.id,
        subject_hash=selection_hash(manifest, selection),
        version=proposal.version,
        selection=selection,
        expires_at=now() + 2592000,
    )
    session.add(approval)
    session.flush()
    selected = next(document for document in manifest["documents"] if document["option"] == selection)
    artifact = session.get(m.Artifact, selected["artifact_id"])
    session.add(
        m.BusinessRecord(
            org_id=user.org_id,
            client_id=requirement.client_id,
            kind="knowledge",
            title=artifact.name,
            data={
                "requirement_id": requirement.id,
                "artifact_id": artifact.id,
                "excerpt": artifact.content,
                "trust": "Owner-approved exact architecture selection",
                "architecture_approval_id": approval.id,
                "manifest_hash": manifest["manifest_hash"],
            },
        )
    )
    audit(
        session,
        user.org_id,
        user.id,
        "architecture.selected",
        proposal.id,
        {"selection": selection, "manifest_hash": manifest["manifest_hash"], "approval_id": approval.id},
        authorization=f"approval:{approval.id}",
    )
    return approval


def assert_project_design(session, project, proposal, requirement):
    manifest = proposal.content.get("architecture_manifest")
    if not manifest:
        if assert_approved(session, requirement):
            raise PermissionError("Reviewed project architecture evidence is missing")
        return None
    validate(session, requirement, manifest)
    approval = session.scalar(
        select(m.Approval).where(
            m.Approval.org_id == project.org_id,
            m.Approval.category == "architecture_design",
            m.Approval.subject_id == proposal.id,
            m.Approval.version == proposal.version,
        )
    )
    user = session.get(m.User, approval.owner_id) if approval else None
    if (
        not approval
        or approval.subject_hash != selection_hash(manifest, project.selected_alternative)
        or approval.selection != project.selected_alternative
        or approval.expires_at <= now()
        or not user
        or not user.enabled
        or user.org_id != project.org_id
        or user.role != "owner"
    ):
        raise PermissionError("Current exact architecture selection needs valid owner approval")
    return approval
