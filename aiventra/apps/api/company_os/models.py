from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base, now, uid

# SQLite INTEGER already stores signed 64-bit values. PostgreSQL requires BIGINT.
MONEY = BigInteger().with_variant(Integer(), "sqlite")


class Record:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[int] = mapped_column(default=now)


class Tenant(Record):
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)


class Organization(Record, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))
    paused: Mapped[bool] = mapped_column(default=False)
    deployments_paused: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    audit_head: Mapped[str] = mapped_column(default="0" * 64)


class Client(Tenant, Base):
    __tablename__ = "clients"
    name: Mapped[str] = mapped_column(String(200))


class User(Tenant, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(default="client")
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    oidc_subject: Mapped[str | None] = mapped_column(String(300), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)


class AuthSession(Tenant, Base):
    __tablename__ = "auth_sessions"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[int] = mapped_column(index=True)
    revoked_at: Mapped[int | None] = mapped_column()


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(default=0)
    resets_at: Mapped[int] = mapped_column(index=True)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    started_at: Mapped[int] = mapped_column(default=now)
    last_seen: Mapped[int] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default="running")


class Department(Tenant, Base):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(200))
    independent: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("org_id", "name"),)


class Agent(Tenant, Base):
    __tablename__ = "agents"
    department_id: Mapped[str] = mapped_column(ForeignKey("departments.id"))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    reports_to: Mapped[str] = mapped_column(default="CEO")
    responsibilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    tools: Mapped[list[str]] = mapped_column(JSON, default=list)
    policies: Mapped[list[str]] = mapped_column(JSON, default=list)
    routing_policy: Mapped[str] = mapped_column(default="economy")
    objectives: Mapped[list[str]] = mapped_column(JSON, default=list)
    memory_scope: Mapped[str] = mapped_column(default="assigned_project")
    max_iterations: Mapped[int] = mapped_column(default=3)
    max_runtime_seconds: Mapped[int] = mapped_column(default=180)
    max_cost_micro: Mapped[int] = mapped_column(MONEY, default=500000)
    enabled: Mapped[bool] = mapped_column(default=True)


class Provider(Tenant, Base):
    __tablename__ = "providers"
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    base_url: Mapped[str] = mapped_column(String(500))
    credential_env: Mapped[str] = mapped_column(String(100), default="")
    enabled: Mapped[bool] = mapped_column(default=True)


class ModelConfig(Tenant, Base):
    __tablename__ = "model_configs"
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"))
    identifier: Mapped[str] = mapped_column(String(200))
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list)
    context_tokens: Mapped[int] = mapped_column(default=32768)
    quality: Mapped[int] = mapped_column(default=50)
    reliability: Mapped[int] = mapped_column(default=100)
    latency_ms: Mapped[int] = mapped_column(default=1000)
    input_price_micro_per_million: Mapped[int] = mapped_column(MONEY, default=0)
    output_price_micro_per_million: Mapped[int] = mapped_column(MONEY, default=0)
    price_source: Mapped[str] = mapped_column(Text, default="")
    price_checked_at: Mapped[int] = mapped_column(default=now)
    sensitivity: Mapped[str] = mapped_column(default="internal")
    enabled: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint("provider_id", "identifier"),)


class LocalModelVerification(Tenant, Base):
    __tablename__ = "local_model_verifications"
    model_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"), unique=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[int] = mapped_column()
    state: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    evidence_digest: Mapped[str] = mapped_column(String(64), default="")


class Requirement(Tenant, Base):
    __tablename__ = "requirements"
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(default="mock")
    sensitivity: Mapped[str] = mapped_column(default="internal")
    budget_micro: Mapped[int] = mapped_column(MONEY, default=5000000)
    deadline: Mapped[str | None] = mapped_column(String(100))
    constraints: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    answers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    rates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default="queued")
    version: Mapped[int] = mapped_column(default=1)


class Proposal(Tenant, Base):
    __tablename__ = "proposals"
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"))
    version: Mapped[int] = mapped_column()
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(default="awaiting_approval")
    __table_args__ = (UniqueConstraint("requirement_id", "version"),)


class Approval(Tenant, Base):
    __tablename__ = "approvals"
    category: Mapped[str] = mapped_column(String(100))
    subject_id: Mapped[str] = mapped_column(String(36))
    subject_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column()
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    selection: Mapped[str] = mapped_column(default="")
    expires_at: Mapped[int] = mapped_column()
    __table_args__ = (UniqueConstraint("org_id", "category", "subject_id", "version"),)


class Project(Tenant, Base):
    __tablename__ = "projects"
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposals.id"), unique=True)
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="active")
    selected_alternative: Mapped[str] = mapped_column(String(200))
    budget_micro: Mapped[int] = mapped_column(MONEY, default=5000000)
    version: Mapped[int] = mapped_column(default=1)


class Milestone(Tenant, Base):
    __tablename__ = "milestones"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column()


class Task(Tenant, Base):
    __tablename__ = "tasks"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    milestone_id: Mapped[str | None] = mapped_column(ForeignKey("milestones.id"))
    assigned_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    objective: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(default="document")
    status: Mapped[str] = mapped_column(default="ready")
    acceptance: Mapped[list[str]] = mapped_column(JSON, default=list)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    budget_micro: Mapped[int] = mapped_column(MONEY, default=500000)
    version: Mapped[int] = mapped_column(default=1)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on: Mapped[str] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class Workflow(Tenant, Base):
    __tablename__ = "workflows"
    requirement_id: Mapped[str | None] = mapped_column(ForeignKey("requirements.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    conversation_turn_id: Mapped[str | None] = mapped_column(ForeignKey("conversation_turns.id"))
    kind: Mapped[str] = mapped_column(default="consulting")
    mode: Mapped[str] = mapped_column(default="mock")
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="queued", index=True)
    step: Mapped[int] = mapped_column(default=0)
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int] = mapped_column(default=3)
    deadline_at: Mapped[int] = mapped_column(default=lambda: now() + 1800)
    lease_until: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[str] = mapped_column(default="")
    last_error: Mapped[str] = mapped_column(Text, default="")
    wait_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    capacity_agents: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    __table_args__ = (
        Index("uq_workflows_conversation_turn", "conversation_turn_id", unique=True),
        Index("uq_workflows_task", "task_id", unique=True),
        Index("uq_workflows_requirement_revision", "requirement_id", "revision", unique=True),
    )


class WorkflowStep(Tenant, Base):
    __tablename__ = "workflow_steps"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    name: Mapped[str] = mapped_column(String(100))
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("workflow_id", "name"),)


class Meeting(Tenant, Base):
    __tablename__ = "meetings"
    requirement_id: Mapped[str | None] = mapped_column(ForeignKey("requirements.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    agenda: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column()
    rounds: Mapped[int] = mapped_column(default=1)
    contributions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    decision: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Message(Tenant, Base):
    __tablename__ = "messages"
    sender: Mapped[str] = mapped_column(String(200))
    recipient: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    type: Mapped[str] = mapped_column(String(100))
    correlation_id: Mapped[str] = mapped_column(String(36), index=True)
    priority: Mapped[str] = mapped_column(default="normal")
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    expected_schema: Mapped[str] = mapped_column(default="Acknowledgement")
    authorization: Mapped[str] = mapped_column(default="internal scoped workflow")
    status: Mapped[str] = mapped_column(default="delivered")
    acknowledged_at: Mapped[int | None] = mapped_column()


class Budget(Tenant, Base):
    __tablename__ = "budgets"
    scope: Mapped[str] = mapped_column(String(100), unique=True)
    limit_micro: Mapped[int] = mapped_column(MONEY)
    spent_micro: Mapped[int] = mapped_column(MONEY, default=0)
    reserved_micro: Mapped[int] = mapped_column(MONEY, default=0)
    version: Mapped[int] = mapped_column(default=1)


class ModelRun(Tenant, Base):
    __tablename__ = "model_runs"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    model_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    step_name: Mapped[str] = mapped_column(String(100))
    attempt: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(default="started")
    routing_reason: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cost_micro: Mapped[int] = mapped_column(MONEY, default=0)
    reserved_micro: Mapped[int] = mapped_column(MONEY, default=0)
    budget_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    cost_basis: Mapped[str] = mapped_column(default="computed_estimate")
    duration_ms: Mapped[int] = mapped_column(default=0)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("workflow_id", "step_name", "attempt"),)


class Transaction(Tenant, Base):
    __tablename__ = "spending_transactions"
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), unique=True)
    amount_micro: Mapped[int] = mapped_column(MONEY)
    basis: Mapped[str] = mapped_column()


class Artifact(Tenant, Base):
    __tablename__ = "artifacts"
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"), index=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(default="")


class Repository(Tenant, Base):
    __tablename__ = "repositories"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(Text)
    baseline_commit: Mapped[str] = mapped_column(String(64), default="")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Execution(Tenant, Base):
    __tablename__ = "executions"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    workspace: Mapped[str] = mapped_column(Text)
    command: Mapped[list[str]] = mapped_column(JSON)
    environment: Mapped[str] = mapped_column(String(200))
    commit_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(default="running")
    exit_code: Mapped[int | None] = mapped_column()
    started_at: Mapped[int] = mapped_column(default=now)
    ended_at: Mapped[int | None] = mapped_column()
    logs: Mapped[str] = mapped_column(Text, default="")


class BusinessRecord(Tenant, Base):
    __tablename__ = "business_records"
    kind: Mapped[str] = mapped_column(String(100), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(default="open")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)


class AuditEvent(Tenant, Base):
    __tablename__ = "audit_events"
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"))
    authorization: Mapped[str] = mapped_column(String(200))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))


class Notification(Tenant, Base):
    __tablename__ = "notifications"
    severity: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200))
    subject_id: Mapped[str] = mapped_column(String(36))
    acknowledged: Mapped[bool] = mapped_column(default=False)


class Conversation(Tenant, Base):
    __tablename__ = "conversations"
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    mode: Mapped[str] = mapped_column(default="live")
    budget_micro: Mapped[int] = mapped_column(MONEY, default=1_000_000)
    version: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[int] = mapped_column(default=now, index=True)


class ConversationTurn(Tenant, Base):
    __tablename__ = "conversation_turns"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    position: Mapped[int] = mapped_column()
    intent: Mapped[str] = mapped_column(default="chat")
    content: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text, default="")
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    requirement_id: Mapped[str | None] = mapped_column(ForeignKey("requirements.id"))
    __table_args__ = (
        UniqueConstraint("conversation_id", "request_id"),
        UniqueConstraint("conversation_id", "position"),
    )


class ProviderCredential(Tenant, Base):
    __tablename__ = "provider_credentials"
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), unique=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)


class ProviderProbe(Tenant, Base):
    __tablename__ = "provider_probes"
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), unique=True)
    status: Mapped[str] = mapped_column(default="unverified")
    checked_at: Mapped[int | None] = mapped_column()
    error_code: Mapped[str] = mapped_column(default="")
    models: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    inference_at: Mapped[int | None] = mapped_column()
    inference_model_id: Mapped[str | None] = mapped_column(ForeignKey("model_configs.id"))


class ModelPolicy(Tenant, Base):
    __tablename__ = "model_policies"
    scope: Mapped[str] = mapped_column(String(100))
    preferred_model_id: Mapped[str | None] = mapped_column(ForeignKey("model_configs.id"))
    allowed_model_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint("org_id", "scope"),)


class ModelEvaluation(Tenant, Base):
    __tablename__ = "model_evaluations"
    model_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), unique=True)
    task_class: Mapped[str] = mapped_column(String(100))
    score: Mapped[int] = mapped_column()
    note: Mapped[str] = mapped_column(Text)
    evaluator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))


class AgentExecution(Tenant, Base):
    __tablename__ = "agent_executions"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), index=True)
    state: Mapped[str] = mapped_column(default="REGISTERED")
    step_name: Mapped[str] = mapped_column(String(100), default="")
    model_run_id: Mapped[str | None] = mapped_column(ForeignKey("model_runs.id"))
    updated_at: Mapped[int] = mapped_column(default=now)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("workflow_id", "agent_id"),)


class AgentStateEvent(Tenant, Base):
    __tablename__ = "agent_state_events"
    execution_id: Mapped[str] = mapped_column(ForeignKey("agent_executions.id"), index=True)
    previous_state: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    sequence: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint("execution_id", "sequence"),)


class AgentWork(Tenant, Base):
    __tablename__ = "agent_work"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), unique=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    kind: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    participants: Mapped[list[str]] = mapped_column(JSON, default=list)
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class RunTrace(Tenant, Base):
    __tablename__ = "run_traces"
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"), unique=True)
    state: Mapped[str] = mapped_column(default="streaming")
    preview: Mapped[str] = mapped_column(Text, default="")
    event_count: Mapped[int] = mapped_column(default=0)
    tool_count: Mapped[int] = mapped_column(default=0)
    usage_known: Mapped[bool] = mapped_column(default=False)


class ToolInvocation(Tenant, Base):
    __tablename__ = "tool_invocations"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("model_runs.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    call_id: Mapped[str] = mapped_column(String(200))
    step_name: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default="rejected")
    __table_args__ = (UniqueConstraint("workflow_id", "step_name", "call_id"),)


class BenchmarkResult(Tenant, Base):
    __tablename__ = "benchmark_results"
    work_id: Mapped[str] = mapped_column(ForeignKey("agent_work.id"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"), index=True)
    case_name: Mapped[str] = mapped_column(String(100))
    score: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column()
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("work_id", "case_name"),)


class BenchmarkProfile(Tenant, Base):
    __tablename__ = "benchmark_profiles"
    model_id: Mapped[str] = mapped_column(ForeignKey("model_configs.id"), unique=True)
    work_id: Mapped[str] = mapped_column(ForeignKey("agent_work.id"))
    suite_version: Mapped[str] = mapped_column(String(100))
    fingerprint: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[int] = mapped_column(default=now)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class MemoryEntry(Tenant, Base):
    __tablename__ = "memory_entries"
    source_key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(60))
    title: Mapped[str] = mapped_column(String(200))
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("agents.id"))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey("conversations.id"))
    client_id: Mapped[str | None] = mapped_column(ForeignKey("clients.id"))
    visibility: Mapped[str] = mapped_column(default="owner")
    version: Mapped[int] = mapped_column(default=1)
    content_hash: Mapped[str] = mapped_column(String(64))
    deleted: Mapped[bool] = mapped_column(default=False)
    index_status: Mapped[str] = mapped_column(default="pending", index=True)
    embedding_fingerprint: Mapped[str] = mapped_column(default="")
    index_error: Mapped[str] = mapped_column(default="")
    updated_at: Mapped[int] = mapped_column(default=now)
    __table_args__ = (UniqueConstraint("org_id", "source_key"),)


class MemoryVersion(Tenant, Base):
    __tablename__ = "memory_versions"
    entry_id: Mapped[str] = mapped_column(ForeignKey("memory_entries.id"), index=True)
    entry: Mapped[MemoryEntry] = relationship()
    version: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("entry_id", "version"),)


class MemoryChunk(Tenant, Base):
    __tablename__ = "memory_chunks"
    entry_id: Mapped[str] = mapped_column(ForeignKey("memory_entries.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("memory_versions.id"), index=True)
    version_record: Mapped[MemoryVersion] = relationship()
    position: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any | None] = mapped_column(Vector(384).with_variant(JSON(), "sqlite"))
    fingerprint: Mapped[str] = mapped_column(default="")
    __table_args__ = (
        UniqueConstraint("version_id", "position"),
        Index(
            "ix_memory_chunks_vector_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class MemoryGrant(Base):
    __tablename__ = "memory_grants"
    entry_id: Mapped[str] = mapped_column(ForeignKey("memory_entries.id"), primary_key=True)
    entry: Mapped[MemoryEntry] = relationship()
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"), primary_key=True)


class MemoryCursor(Tenant, Base):
    __tablename__ = "memory_cursors"
    source: Mapped[str] = mapped_column(String(100))
    last_id: Mapped[str] = mapped_column(default="")
    __table_args__ = (UniqueConstraint("org_id", "source"),)


class StaffingPlan(Tenant, Base):
    __tablename__ = "staffing_plans"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default="draft")
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    runtime: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class StaffingRevision(Tenant, Base):
    __tablename__ = "staffing_revisions"
    plan_id: Mapped[str] = mapped_column(ForeignKey("staffing_plans.id"))
    version: Mapped[int] = mapped_column()
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    __table_args__ = (UniqueConstraint("plan_id", "version"),)


class TaskAssignment(Tenant, Base):
    __tablename__ = "task_assignments"
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    previous_agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)


class DeliveryPackage(Tenant, Base):
    """One frozen version. Release state changes never rewrite the manifest."""

    __tablename__ = "delivery_packages"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("business_records.id"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), unique=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column()
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    source_hash: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="preparing")
    input: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    manifest_hash: Mapped[str] = mapped_column(String(64), default="")
    finalized_at: Mapped[int | None] = mapped_column()
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("delivery_packages.id"))
    __table_args__ = (
        UniqueConstraint("org_id", "project_id", "version"),
        UniqueConstraint("org_id", "request_id"),
    )


class ClientInvitation(Tenant, Base):
    __tablename__ = "client_invitations"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    email: Mapped[str] = mapped_column(String(254))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[int] = mapped_column()
    redeemed_at: Mapped[int | None] = mapped_column()
    redeemed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[int | None] = mapped_column()
    can_respond: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (UniqueConstraint("org_id", "request_id"),)


class ClientAccessGrant(Tenant, Base):
    __tablename__ = "client_access_grants"
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    invitation_id: Mapped[str] = mapped_column(ForeignKey("client_invitations.id"))
    can_respond: Mapped[bool] = mapped_column(default=True)
    revoked_at: Mapped[int | None] = mapped_column()
    __table_args__ = (UniqueConstraint("org_id", "user_id", "project_id"),)


class DeliveryResponse(Tenant, Base):
    """Append-only exact-package client statement, separate from mutable case progress."""

    __tablename__ = "delivery_responses"
    package_id: Mapped[str] = mapped_column(ForeignKey("delivery_packages.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), unique=True)
    request_id: Mapped[str] = mapped_column(String(36))
    request_hash: Mapped[str] = mapped_column(String(64))
    package_version: Mapped[int] = mapped_column()
    manifest_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("org_id", "request_id"),
        Index(
            "uq_delivery_package_acceptance",
            "org_id",
            "package_id",
            unique=True,
            sqlite_where=text("kind = 'accept'"),
            postgresql_where=text("kind = 'accept'"),
        ),
    )
