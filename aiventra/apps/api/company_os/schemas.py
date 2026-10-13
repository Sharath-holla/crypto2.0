from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Strict):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class Rate(Strict):
    alternative: str = Field(max_length=200)
    label: str = Field(max_length=200)
    unit_price_micro: int = Field(ge=0, le=10**15)
    quantity: str = Field(pattern=r"^\d{1,9}(\.\d{1,6})?$")
    unit: str = Field(max_length=100)
    region: str = Field(max_length=100)
    source_url: str = Field(pattern=r"^https://", max_length=2000)
    retrieved_at: int = Field(gt=0)
    one_time: bool = False
    verified: bool = False


class Intake(Strict):
    client_id: str
    title: str = Field(min_length=3, max_length=200)
    text: str = Field(min_length=20, max_length=30000)
    mode: Literal["mock", "live"] = "mock"
    sensitivity: Literal["public", "internal", "confidential"] = "internal"
    budget_micro: int = Field(ge=0, le=10**12, default=5000000)
    deadline: str | None = Field(default=None, max_length=100)
    constraints: dict[str, str] = Field(default_factory=dict, max_length=30)
    rates: list[Rate] = Field(default_factory=list, max_length=100)


class Clarification(Strict):
    version: int = Field(ge=1)
    answers: dict[str, str] = Field(max_length=30)
    rates: list[Rate] = Field(default_factory=list, max_length=100)


class Analysis(Strict):
    project_type: str
    objectives: list[str] = Field(max_length=15)
    requirements: list[str] = Field(max_length=30)
    questions: list[str] = Field(max_length=8)
    assumptions: list[str] = Field(max_length=15)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=20)


class Recommendation(Strict):
    summary: str
    evidence: list[str] = Field(max_length=10)
    risks: list[str] = Field(max_length=15)
    alternatives: list[str] = Field(max_length=5)
    actions: list[str] = Field(max_length=15)


class Alternative(Strict):
    name: str
    architecture: str
    advantages: list[str]
    disadvantages: list[str]
    reliability: str


class ProposalContent(Strict):
    executive_summary: str
    business_problem: str
    confirmed_requirements: list[str]
    assumptions: list[str]
    open_questions: list[str]
    current_architecture: str
    alternatives: list[Alternative] = Field(min_length=1, max_length=5)
    recommendation: str
    risks_and_mitigations: list[str]
    milestones: list[str] = Field(min_length=1, max_length=8)
    proposed_team: list[str]
    deliverables: list[str]
    acceptance_criteria: list[str] = Field(min_length=1)
    required_approvals: list[str]


class Approve(Strict):
    version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    selection: str = Field(min_length=1, max_length=200)


class ProviderInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["openai", "anthropic", "gemini", "ollama", "compatible", "xai"]
    base_url: str = Field(max_length=500)
    credential_env: str = Field(default="", pattern=r"^(?:[A-Z][A-Z0-9_]{0,99})?$")


class ModelInput(Strict):
    provider_id: str
    identifier: str = Field(min_length=1, max_length=200)
    capabilities: list[Literal["structured", "reasoning", "coding", "tools", "streaming"]] = Field(
        min_length=1
    )
    context_tokens: int = Field(ge=1024, le=10**7)
    quality: int = Field(ge=0, le=100)
    reliability: int = Field(ge=0, le=100, default=100)
    latency_ms: int = Field(ge=1, default=1000)
    input_price_micro_per_million: int = Field(ge=0, le=10**15)
    output_price_micro_per_million: int = Field(ge=0, le=10**15)
    price_source: str = Field(min_length=1, max_length=2000)
    sensitivity: Literal["public", "internal", "confidential"] = "internal"


class AgentUpdate(Strict):
    enabled: bool | None = None
    tools: (
        list[Literal["read_context", "write_artifact", "propose_patch", "run_tests", "review_diff"]] | None
    ) = None
    routing_policy: Literal["economy", "balanced", "quality", "fastest", "manual"] | None = None
    max_iterations: int | None = Field(default=None, ge=1, le=5)
    max_cost_micro: int | None = Field(default=None, ge=0, le=10**10)
    max_runtime_seconds: int | None = Field(default=None, ge=10, le=180)
    responsibilities: list[str] | None = Field(default=None, max_length=20)
    objectives: list[str] | None = Field(default=None, max_length=20)


class RecordInput(Strict):
    kind: Literal[
        "opportunity", "support", "knowledge", "email_draft", "calendar_draft", "incident", "campaign"
    ]
    title: str = Field(min_length=1, max_length=200)
    project_id: str | None = None
    client_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DocumentResult(Strict):
    title: str
    content: str = Field(min_length=20, max_length=30000)
    acceptance_checks: list[str] = Field(min_length=1, max_length=20)


class PatchFile(Strict):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=100000)


class PatchResult(Strict):
    summary: str
    files: list[PatchFile] = Field(min_length=1, max_length=20)
    tests: Literal["python-unittest", "node-test"]


class CodingTaskInput(Strict):
    repository_id: str
    objective: str = Field(min_length=10, max_length=10000)
    acceptance: list[str] = Field(min_length=1, max_length=15)
    mode: Literal["mock", "live"] = "live"
    test_suite: Literal["python-unittest", "node-test"]
    budget_micro: int = Field(ge=0, le=10**10, default=5000000)
    review_policy: Literal["prefer_provider", "require_provider", "require_model"] = "prefer_provider"
    review_count: int = Field(ge=1, le=2, default=1)
    repair_limit: int = Field(ge=0, le=2, default=1)


class ReviewResult(Strict):
    approved: bool
    findings: list[str]
    acceptance_assessment: list[str]
