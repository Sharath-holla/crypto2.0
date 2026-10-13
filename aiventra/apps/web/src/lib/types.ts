export type Json =
  string | number | boolean | null | Json[] | { [key: string]: Json };
export interface Entity {
  id: string;
  org_id: string;
  created_at: number;
}
export interface User extends Entity {
  email: string;
  role: "owner" | "client";
  client_id: string | null;
}
export interface Agent extends Entity {
  name: string;
  role: string;
  department_id: string;
  reports_to: string;
  responsibilities: string[];
  tools: string[];
  policies: string[];
  objectives: string[];
  routing_policy: string;
  enabled: boolean;
  max_cost_micro: number;
  max_iterations: number;
}
export interface Department extends Entity {
  name: string;
  independent: boolean;
}
export interface Requirement extends Entity {
  client_id: string;
  title: string;
  text: string;
  mode: string;
  sensitivity: string;
  status: string;
  version: number;
  budget_micro: number;
  answers: Record<string, string>;
  rates: Json[];
  analysis: {
    questions?: string[];
    objectives?: string[];
    requirements?: string[];
    assumptions?: string[];
    acceptance_criteria?: string[];
  };
}
export interface Alternative {
  name: string;
  architecture: string;
  advantages: string[];
  disadvantages: string[];
  reliability: string;
}
export interface Proposal extends Entity {
  requirement_id: string;
  version: number;
  status: string;
  content_hash: string;
  content: {
    mode: string;
    executive_summary: string;
    business_problem: string;
    alternatives: Alternative[];
    recommendation: string;
    architecture_manifest?: {
      manifest_hash: string;
      scope_hash: string;
      basis: string;
      requirement_version: number;
      design: {
        options?: (Alternative & Record<string, string | string[]>)[];
        limitations?: string[];
        single_option_reason?: string;
      };
      documents: { option: string; artifact_id: string; sha256: string }[];
    };
    assumptions: string[];
    open_questions: string[];
    milestones: string[];
    proposed_team: string[];
    deliverables: string[];
    acceptance_criteria: string[];
    risks_and_mitigations: string[];
    cost_comparison: {
      alternative: string;
      recurring_micro: number | null;
      one_time_micro: number | null;
      twelve_month_micro: number | null;
      basis: string;
      complete: boolean;
      lines: Json[];
      warnings: string[];
    }[];
  };
}
export interface Project extends Entity {
  version: number;
  name: string;
  status: string;
  client_id: string;
  proposal_id: string;
  selected_alternative: string;
  budget_micro: number;
}
export interface Task extends Entity {
  version: number;
  project_id: string;
  assigned_agent_id: string;
  objective: string;
  kind: string;
  status: string;
  acceptance: string[];
  payload: Record<string, Json>;
  evidence: Record<string, Json>;
}
export interface Workflow extends Entity {
  mode: string;
  kind: string;
  requirement_id: string | null;
  task_id: string | null;
  status: string;
  step: number;
  attempts: number;
  max_attempts: number;
  lease_until: number;
  last_error: string;
}
export interface Model extends Entity {
  enabled: boolean;
  identifier: string;
  provider_id: string;
  quality: number;
  reliability: number;
  capabilities: string[];
  context_tokens: number;
  input_price_micro_per_million: number;
  output_price_micro_per_million: number;
  price_source: string;
  sensitivity: string;
}
export interface Provider extends Entity {
  name: string;
  kind: string;
  base_url: string;
  credential_env: string;
  enabled: boolean;
}
export interface Run extends Entity {
  agent_id: string;
  model_id: string;
  workflow_id: string;
  task_id: string | null;
  project_id: string | null;
  step_name: string;
  status: string;
  routing_reason: string;
  input_tokens: number;
  output_tokens: number;
  cost_micro: number;
  reserved_micro: number;
  cost_basis: string;
  duration_ms: number;
  error: string;
}
export interface Budget extends Entity {
  scope: string;
  limit_micro: number;
  spent_micro: number;
  reserved_micro: number;
  version: number;
}
export interface Artifact extends Entity {
  name: string;
  kind: string;
  content: string;
  sha256: string;
  agent_id: string;
  task_id: string | null;
  project_id: string | null;
}
export interface Audit extends Entity {
  actor: string;
  action: string;
  subject: string;
  authorization: string;
  event_hash: string;
  detail: Json;
}
export interface Message extends Entity {
  sender: string;
  recipient: string;
  type: string;
  content: Record<string, Json>;
  status: string;
  correlation_id: string;
}
export interface Meeting extends Entity {
  agenda: string;
  mode: string;
  rounds: number;
  contributions: Json[];
  decision: Json;
}
export interface BusinessRecord extends Entity {
  project_id: string | null;
  client_id: string | null;
  kind: string;
  title: string;
  status: string;
  data: Record<string, Json>;
  version: number;
}
export interface Repository extends Entity {
  name: string;
  project_id: string;
  path: string;
  baseline_commit: string;
  report: Record<string, Json>;
}
export interface Execution extends Entity {
  task_id: string;
  agent_id: string;
  command: string[];
  environment: string;
  status: string;
  exit_code: number | null;
  logs: string;
  commit_hash: string;
  started_at: number;
  ended_at: number | null;
}
export interface Notification extends Entity {
  title: string;
  severity: string;
  acknowledged: boolean;
  subject_id: string;
}
export interface State {
  run_traces: RunTrace[];
  tool_invocations: (Entity & {
    workflow_id: string;
    name: string;
    status: string;
    result: Record<string, unknown>;
  })[];
  benchmark_results: (Entity & {
    work_id: string;
    model_id: string;
    case_name: string;
    status: string;
    score: number;
    metrics: { cost_micro: number; duration_ms: number };
  })[];
  benchmark_profiles: (Entity & {
    model_id: string;
    suite_version: string;
    metrics: { quality: number; [key: string]: unknown };
  })[];
  provider_probes: (Entity & {
    provider_id: string;
    status: string;
    checked_at: number | null;
    error_code: string;
    models: { identifier: string; generation_methods: string[] }[];
    inference_at: number | null;
    inference_model_id: string | null;
  })[];
  model_policies: (Entity & {
    scope: string;
    preferred_model_id: string | null;
    allowed_model_ids: string[];
    version: number;
  })[];
  model_evaluations: (Entity & {
    model_id: string;
    run_id: string;
    score: number;
    task_class: string;
    note: string;
  })[];
  agent_executions: (Entity & {
    agent_id: string;
    workflow_id: string;
    state: string;
    step_name: string;
    updated_at: number;
    detail: Json;
  })[];
  agent_state_events: (Entity & {
    sequence: number;
    execution_id: string;
    previous_state: string;
    state: string;
    detail: Json;
  })[];
  agent_runtime: {
    agent_id: string;
    state: string;
    workflow_id: string | null;
    mode: string | null;
    step_name: string;
    updated_at: number;
    stale_lease: boolean;
    successful_runs: number;
    failed_runs: number;
    cost_micro: number;
  }[];
  agent_work: (Entity & {
    workflow_id: string;
    project_id: string | null;
    kind: string;
    subject_id: string;
    participants: string[];
    input: Record<string, Json>;
    result: Record<string, Json>;
  })[];
  conversations: Conversation[];
  organization: {
    id: string;
    version: number;
    name: string;
    paused: boolean;
    deployments_paused: boolean;
  };
  runtime: {
    ai_spending_mode: "ZERO_COST_ONLY";
    inference_eligibility: {
      model_id: string;
      provider_id: string;
      allowed: boolean;
      state: string;
      reason: string;
      local_candidate: boolean;
      evidence_digest: string;
    }[];
    mock_enabled: boolean;
    execution_enabled: boolean;
    database: string;
    worker: {
      status: string;
      last_seen: number | null;
      stale_after_seconds: number;
    };
    providers: {
      id: string;
      name: string;
      mode: string;
      status: string;
      credential_source: string;
      credential_configured: boolean;
      credential_error: string;
      vault_available: boolean;
    }[];
  };
  departments: Department[];
  agents: Agent[];
  clients: (Entity & { name: string })[];
  requirements: Requirement[];
  proposals: Proposal[];
  projects: Project[];
  tasks: Task[];
  dependencies: { task_id: string; depends_on: string }[];
  milestones: (Entity & {
    project_id: string;
    name: string;
    position: number;
  })[];
  workflows: Workflow[];
  messages: Message[];
  meetings: Meeting[];
  providers: Provider[];
  models: Model[];
  runs: Run[];
  budgets: Budget[];
  artifacts: Artifact[];
  repositories: Repository[];
  executions: Execution[];
  records: BusinessRecord[];
  audit: Audit[];
  notifications: Notification[];
  approvals: (Entity & {
    category: string;
    subject_id: string;
    version: number;
    expires_at: number;
  })[];
}

export interface Conversation extends Entity {
  owner_id: string;
  client_id: string;
  project_id: string | null;
  title: string;
  mode: "live" | "mock";
  budget_micro: number;
  version: number;
  updated_at: number;
}
export interface ConversationTurn extends Entity {
  run_traces: RunTrace[];
  conversation_id: string;
  position: number;
  intent: "chat" | "consult";
  content: string;
  response: string;
  attachment_ids: string[];
  workflow: Workflow | null;
  runs: Run[];
  consultation: {
    requirement: Requirement;
    workflow: Workflow | null;
    proposals: Proposal[];
  } | null;
}

export interface RunTrace extends Entity {
  run_id: string;
  state: string;
  preview: string;
  event_count: number;
  tool_count: number;
  usage_known: boolean;
}
export interface ConversationSnapshot {
  next_cursor: string | null;
  conversation: Conversation;
  turns: ConversationTurn[];
  total_turns: number;
  attachments: Omit<Artifact, "content">[];
}
