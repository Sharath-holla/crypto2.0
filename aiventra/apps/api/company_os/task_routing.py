"""Task-level constraints and explainable selection; no provider calls or new authority."""

from typing import Annotated, Literal

from pydantic import Field

from . import models as m
from .registry_provenance import visible
from .schemas import Strict

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class TaskRequirements(Strict):
    workstream: str = Field(default="delivery", min_length=1, max_length=100)
    skills: list[ShortText] = Field(default_factory=list, max_length=12)
    difficulty: Literal["simple", "standard", "complex"] = "standard"
    risk: Literal["low", "medium", "high"] = "medium"
    required_tools: list[ShortText] = Field(default_factory=list, max_length=8)
    context_tokens: int = Field(default=4096, ge=1024, le=131072)
    qa_requirements: list[ShortText] = Field(default_factory=list, max_length=12)
    recommended_model_id: str | None = Field(default=None, max_length=36)
    model_rationale: str = Field(default="", max_length=1000)
    model_override: str | None = Field(default=None, max_length=36)
    # A saved identity preference confers no execution entitlement or capability proof.
    preferred_model_id: str | None = Field(default=None, max_length=36)
    # Recomputed by the server on every draft revision. Never trusted as input.
    model_selection: dict = Field(default_factory=dict)


def setup_form(session, project):
    from .project_setup import for_requirement

    proposal = session.get(m.Proposal, project.proposal_id)
    record = for_requirement(session, proposal.requirement_id, project.org_id)
    return record.data["form"] if record else None


def requirements(row):
    profile = TaskRequirements.model_validate(
        {key: row[key] for key in TaskRequirements.model_fields if key in row}
    )
    capabilities = {"structured"}
    if row["kind"] == "coding":
        capabilities.add("coding")
    if profile.difficulty == "complex":
        capabilities.add("reasoning")
    quality = max(85 if row["kind"] == "coding" else 70, 90 if profile.risk == "high" else 0)
    return profile, capabilities, quality


def benchmark_case(row, agent):
    if row["kind"] == "coding":
        return "coding"
    if agent.role in {"QA Director", "Unit Test Engineer", "Integration Test Engineer"}:
        return "testing"
    if agent.role in {"CTO", "Software Architect", "Database Engineer", "DevOps Engineer"}:
        return "architecture"
    return "review" if agent.role == "Security Architect" else "business"


def choices(session, project, content, row, *, verified=True, preferences=True):
    from . import spending
    from .benchmarks import current_profile
    from .gateway import eligible_models
    from .model_routing import apply_policies
    from .providers import configured

    profile, capabilities, quality = requirements(row)
    agent = session.get(m.Agent, row["agent_id"])
    proposal = session.get(m.Proposal, project.proposal_id)
    requirement = session.get(m.Requirement, proposal.requirement_id)
    form = setup_form(session, project)
    mode = content.get("routing_mode", form["worker_mode"] if form else "automatic")
    selected = (profile.model_override or profile.preferred_model_id) if preferences else None
    if preferences and not selected and form:
        selected = form["overrides"].get("role:" + agent.role) or form["overrides"].get(
            "department:" + agent.department_id
        )
    pool = form["worker_model_ids"] if form else []
    candidates = eligible_models(
        session,
        project.org_id,
        content["mode"],
        capabilities,
        quality,
        requirement.sensitivity,
        profile.context_tokens,
        agent.routing_policy,
        "coding" if row["kind"] == "coding" else "document",
    )
    candidates = apply_policies(session, agent, project.id, candidates, selected)
    candidates = [
        (model, provider)
        for model, provider in candidates
        if configured(provider)
        and (not pool or model.id in pool)
        and (
            spending.status(session, provider, model)["allowed"]
            or (not verified and spending.assess(provider, model).local_candidate)
        )
    ]
    if preferences and mode == "manual" and not selected:
        candidates = []
    case = benchmark_case(row, agent)
    scores = {}
    for model, provider in candidates:
        benchmark = current_profile(session, model, provider)
        score = benchmark.metrics.get("cases", {}).get(case) if benchmark else None
        if score is not None:
            scores[model.id] = score
    candidates = [
        (model, provider) for model, provider in candidates if scores.get(model.id, quality) >= quality
    ]
    candidates.sort(key=lambda pair: (pair[0].id not in scores, -scores.get(pair[0].id, 0)))
    if profile.recommended_model_id and not selected:
        candidates.sort(key=lambda pair: pair[0].id != profile.recommended_model_id)
    return candidates, selected, mode


def decision(session, project, content, row):
    from . import spending
    from .benchmarks import current_profile

    profile, capabilities, quality = requirements(row)
    candidates, selected, mode = choices(session, project, content, row)
    options = []
    for model, provider in candidates[:8]:
        benchmark = current_profile(session, model, provider)
        options.append(
            {
                "id": model.id,
                "identifier": model.identifier,
                "provider": provider.name,
                "quality_basis": "configured registry; no current benchmark"
                if not benchmark
                else "current fingerprint-bound microbenchmark",
                "benchmark": benchmark.metrics if benchmark else None,
                "reliability": model.reliability,
                "context_tokens": model.context_tokens,
                "capabilities": model.capabilities,
                "configured": True,
                "zero_cost": spending.status(session, provider, model)["state"],
            }
        )
    state = (
        "DETERMINISTIC_TEST"
        if options and content["mode"] == "mock"
        else "READY"
        if options
        else "WAITING_FOR_FREE_PROVIDER"
    )
    return {
        "state": state,
        "mode": mode,
        "model_id": options[0]["id"] if options else None,
        "identifier": options[0]["identifier"] if options else None,
        "reason": (
            "Exact owner model choice passed task and zero-cost filters"
            if options and selected
            else "Eligible task models ranked by scoped routing policy and current evidence; bounded fallback remains permitted"
            if options
            else "Manual task requires an exact assignment"
            if mode == "manual" and not selected
            else "No configured, verified free model meets task capabilities, quality, context and project policies"
        ),
        "capabilities": sorted(capabilities),
        "minimum_quality": quality,
        "minimum_context_tokens": profile.context_tokens,
        "resource_basis": "Context allowance is a constraint, not measured token/RAM usage. Local inference is serialized globally.",
        "independent_qa": row["kind"] == "coding",
        "candidates": options,
        "model_options": [
            {"id": model.id, "identifier": model.identifier, "provider": provider.name}
            for model, provider in choices(session, project, content, row, preferences=False)[0][:32]
        ],
    }


def prepare(session, plan, content):
    """Validate exact model identities/preferences, then save server-produced explanations."""
    from . import spending

    project = session.get(m.Project, plan.project_id)
    form = setup_form(session, project)
    content["routing_mode"] = content.get("routing_mode", form["worker_mode"] if form else "automatic")
    for row in content["tasks"]:
        profile, _, _ = requirements(row)
        if (profile.model_override or profile.preferred_model_id) and content["routing_mode"] == "automatic":
            raise ValueError("Choose hybrid or manual routing for per-task overrides")
        if profile.preferred_model_id:
            model = session.get(m.ModelConfig, profile.preferred_model_id)
            provider = session.get(m.Provider, model.provider_id) if model else None
            if (
                not model
                or model.org_id != plan.org_id
                or not provider
                or provider.org_id != plan.org_id
                or provider.kind == "mock"
                or not visible(session, provider)
            ):
                raise ValueError("Unknown or foreign registered task preference")
            if profile.model_override and profile.model_override != profile.preferred_model_id:
                raise ValueError("Conflicting task model selections")
        agent = session.get(m.Agent, row["agent_id"])
        if not agent or agent.org_id != plan.org_id:
            raise ValueError("Foreign task assignment")
        if not set(profile.required_tools).issubset(agent.tools):
            raise ValueError("Task requires unauthorized agent tools")
        if not profile.skills:
            profile.skills = [agent.role]
        if not profile.required_tools:
            profile.required_tools = ["propose_patch" if row["kind"] == "coding" else "write_artifact"]
        if not profile.qa_requirements:
            profile.qa_requirements = [criterion[:200] for criterion in row["acceptance"][:12]]
        for model_id in (profile.model_override, profile.recommended_model_id):
            if not model_id:
                continue
            model = session.get(m.ModelConfig, model_id)
            provider = session.get(m.Provider, model.provider_id) if model else None
            if not model or model.org_id != plan.org_id or not provider or provider.org_id != plan.org_id:
                raise ValueError("Unknown or foreign task model")
            # A recommendation does not confer eligibility. Explicit choices must pass the same filters.
            proposed = {**row, "model_override": model_id}
            if (
                not spending.status(session, provider, model)["allowed"]
                or not choices(session, project, content, proposed)[0]
            ):
                raise ValueError(
                    "Task model is not currently eligible under ZERO_COST_ONLY and task policies"
                )
        row.update(profile.model_dump())
        row["model_selection"] = decision(session, project, content, row)


def runtime(session, workflow, agent):
    """Only author/document tasks inherit task overrides; reviewers remain independently routed."""
    task = session.get(m.Task, workflow.task_id) if workflow.task_id else None
    if not task or task.assigned_agent_id != agent.id or not task.payload.get("task_requirements"):
        return None
    profile = TaskRequirements.model_validate(task.payload["task_requirements"])
    if not set(profile.required_tools).issubset(agent.tools):
        raise PermissionError("Approved task tool permissions were revoked")
    return task, profile


def constrain(session, workflow, agent, candidates):
    binding = runtime(session, workflow, agent)
    if not binding:
        return candidates
    task, profile = binding
    content = {"mode": workflow.mode, "routing_mode": task.payload["routing_mode"]}
    row = {"agent_id": agent.id, "kind": task.kind, **profile.model_dump()}
    allowed = {
        model.id: index
        for index, (model, _) in enumerate(
            choices(session, session.get(m.Project, task.project_id), content, row, verified=False)[0]
        )
    }
    candidates = [(model, provider) for model, provider in candidates if model.id in allowed]
    candidates.sort(key=lambda pair: allowed[pair[0].id])
    return candidates
