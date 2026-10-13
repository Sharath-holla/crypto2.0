# AIVENTRA OS — MASTER PRODUCTION IMPLEMENTATION PROMPT
## Upgrade the Existing Prototype into a Real Autonomous Multi-Agent Software Company

You are acting as an elite engineering organization consisting of a Principal Software Architect, AI Systems Architect, Senior Full-Stack Engineer, Multi-Agent Orchestration Engineer, Database Architect, DevOps Engineer, Security Architect, QA Director, UI/UX Director and Engineering Program Manager.

Your task is to AUDIT, REDESIGN, IMPLEMENT, TEST, HARDEN, DEPLOY and PUBLISH my EXISTING Aiventra OS application.

Repository:
https://github.com/Sharath-holla/Aiventra.git

Development environment:
- Windows 11
- VS Code / Codex
- Docker installed
- GitHub repository available

The existing Aiventra project is already created locally, but many features may be mocked, hardcoded, inactive, broken or incomplete.

DO NOT simply recreate the existing fake dashboard.

DO NOT replace working functionality unnecessarily.

DO NOT claim the system is production-ready without testing.

DO NOT stop after generating architecture diagrams or documentation.

The objective is a REAL, functional, secure, persistent, fully integrated autonomous AI company platform.

The application must eventually be capable of accepting an actual software project, conducting professional requirements analysis and solution consulting, obtaining approval, assigning specialized AI workers, writing real code, performing independent testing, preparing deployment and delivering a verified project.

I must be able to observe and control the organization through a professional web interface.

You must build this incrementally, preserving the progress in the repository, with functioning code and tests after every major phase.

---

# SECTION 1 — ABSOLUTE PRODUCT REQUIREMENTS

Aiventra must implement the following end-to-end lifecycle:

CLIENT REQUIREMENT
→ REQUIREMENT ANALYSIS
→ SPECIALIST CONSULTATION
→ SOLUTION RESEARCH
→ ARCHITECTURE AND COST COMPARISON
→ CLIENT APPROVAL
→ PROJECT CREATION
→ AI WORKFORCE ALLOCATION
→ TECHNICAL DESIGN
→ SOFTWARE DEVELOPMENT
→ CODE REVIEW
→ CROSS-MODEL VERIFICATION
→ AUTOMATED TESTING
→ DEBUGGING
→ DEVOPS AND STAGING DEPLOYMENT
→ FINAL ARCHITECTURE / SECURITY / COST REVIEW
→ CLIENT DEMONSTRATION
→ CLIENT ACCEPTANCE
→ PROJECT DELIVERY
→ SUPPORT AND MAINTENANCE.

Every transition must correspond to real persisted workflow state.

Every important artifact must be saved and versioned.

Every critical action must be auditable.

No stage can be marked completed only because an LLM generated a convincing description.

---

# SECTION 2 — AUDIT THE EXISTING PROJECT FIRST

Before implementing changes:

1. Inspect the entire local repository.
2. Identify the actual tech stack.
3. Inspect all frontend pages.
4. Inspect all API endpoints.
5. Inspect all database models.
6. Inspect the current agent runtime.
7. Inspect any agent orchestration framework.
8. Inspect the project management system.
9. Inspect existing memory implementations.
10. Inspect model-provider connections.
11. Inspect Docker configuration.
12. Inspect current authentication.
13. Inspect existing integration code.
14. Inspect test coverage.
15. Inspect Git configuration.
16. Inspect deployment configuration.
17. Identify obsolete and duplicate code.
18. Identify hardcoded demo data and fake execution.

Run existing tests and builds.

Check every displayed feature against actual backend behavior.

Classify each major feature:

- FUNCTIONAL AND TESTED
- FUNCTIONAL BUT UNVERIFIED
- PARTIALLY IMPLEMENTED
- MOCK ONLY
- BROKEN
- MISSING

Generate AUDIT_REPORT.md.

For each missing or broken feature, include:
- Current behavior.
- Expected behavior.
- Root cause where known.
- Affected modules.
- Repair plan.
- Dependencies.
- Verification method.

Preserve existing useful code.

If the current architecture is inadequate, refactor incrementally rather than deleting the whole project.

---

# SECTION 3 — COMPLETE ORGANIZATIONAL HIERARCHY

Build a configurable AI company organization.

Human owner at the top.

Below the owner:
- CEO
- COO
- CTO
- CFO
- CHRO
- CMO
- CISO
- Chief Product Officer
- Chief Sales Officer
- Chief Strategy Officer

Departments:
1. Executive Management
2. Business Analysis
3. Product Management
4. Project Management Office
5. Solution Architecture
6. Software Engineering
7. AI and Machine Learning
8. Data Engineering
9. UI/UX Design
10. Quality Assurance
11. DevOps and Cloud
12. Security
13. Finance and FinOps
14. Human Resources
15. Sales and Business Development
16. Marketing
17. Client Success
18. Legal and Compliance
19. Research and Innovation
20. Independent Monitoring and Audit

Every department can contain:
- Director
- Manager
- Sub-manager
- Team lead
- Senior specialist
- Specialist
- Junior specialist
- Temporary task worker

These are configurable templates, not permanently running AI model instances.

Support expanding the organization to hundreds or thousands of logical employees.

Do not permanently invoke an LLM for every role.

Create runtime workers only when actual tasks require them.

Every agent must have:
- Role and job description.
- Unique identity.
- Department.
- Reporting hierarchy.
- Assigned projects.
- Capabilities.
- Authorized tools.
- Allowed data access.
- Available model policies.
- Current runtime state.
- Task queue.
- Performance history.
- Cost history.
- Work artifacts.
- Memory access.
- Escalation policy.

The executive hierarchy should provide decisions and delegation, while actual task execution must be controlled by a durable backend.

---

# SECTION 4 — COMPLETE CLIENT REQUIREMENT ENGINE

This is the most important feature.

The client should interact with Aiventra through the main chat interface.

Example:

"I want to migrate my application from Google Cloud to Lightning AI. Recommend the best infrastructure and help me migrate."

The company must not immediately start implementation.

## Stage A — Intake

The Business Analyst collects:
- Business objective.
- Functional requirements.
- Nonfunctional requirements.
- Existing infrastructure.
- Constraints.
- Budget.
- Timeline.
- Scalability requirements.
- Security requirements.
- Expected deliverables.
- Existing documentation.
- Available repositories.

Support documents, text files, PDFs, diagrams and repository references.

Store requirements in PostgreSQL.

## Stage B — Clarification

Ask only relevant missing questions.

For cloud migration:
- What services currently run on Google Cloud?
- Is GPU infrastructure required?
- How much data exists?
- What is the current monthly cost?
- What are CPU, RAM, storage and network requirements?
- Is zero downtime necessary?
- What compliance restrictions apply?

Maintain assumptions explicitly.

Do not invent missing requirements.

## Stage C — Internal Company Consultation

Create an internal consulting session involving relevant agents.

For infrastructure migration:
- CEO
- CTO
- Business Analyst
- Cloud Architect
- DevOps Architect
- Security Architect
- CFO
- FinOps Engineer
- Project Manager

Agents should analyze the problem independently where practical.

Persist their proposals.

Hold bounded structured discussions.

Agents must cite evidence, assumptions and uncertainties.

Do not run endless AI meetings.

## Stage D — Alternative Solution Analysis

Research several technically valid solutions.

Example:
- Optimize existing GCP deployment.
- Migrate eligible workloads to Lightning AI.
- Use another lower-cost VM provider.
- Use hybrid infrastructure.
- Use managed services selectively.
- Use serverless or batch infrastructure where suitable.

Compare:
- CPU / RAM / GPU.
- Storage.
- Networking.
- Availability.
- Scalability.
- Security.
- Reliability.
- Operational effort.
- Migration complexity.
- Recurring cost.
- One-time migration cost.
- Downtime risk.
- Vendor lock-in.

Fetch verified pricing when possible.

Record source, date, region, pricing unit and assumptions.

Never fabricate current provider pricing.

## Stage E — Solution Proposal

Generate:

OPTION 1 — LOWEST VIABLE COST

OPTION 2 — BEST VALUE / BALANCED

OPTION 3 — HIGHEST PERFORMANCE OR RELIABILITY

For each option:
- Architecture diagram.
- Technology stack.
- Hosting plan.
- Database recommendation.
- Pros and cons.
- Estimated cost breakdown.
- Security implications.
- Scaling approach.
- Migration considerations.
- Risks.
- Assumptions.

The CEO should synthesize recommendations from specialist agents.

Present an actionable final recommendation.

## Stage F — Client Approval

Client or authorized owner can:
- Approve.
- Reject.
- Request modifications.
- Choose an alternative.
- Adjust budget.
- Change specifications.

Use versioned approval records.

No implementation begins until approval is obtained.

Reapproval is required after material scope or cost changes.

---

# SECTION 5 — AUTOMATIC AI PROJECT WORKFORCE ALLOCATION

After proposal approval, Aiventra must behave like a multinational company assigning employees to a project.

The system must determine:
- Which departments are needed.
- Which specialist roles are needed.
- How many logical agents to allocate.
- Which tasks can run in parallel.
- Which tasks have dependencies.
- Which model capabilities are necessary.
- Project operating budget.
- Concurrency limits.

Example:

For a complex crypto analytics project, the system might recommend:
- 1 Project Manager.
- 2 Business Analysts.
- 2 Architects.
- 3 Frontend Developers.
- 4 Backend Developers.
- 2 Data Engineers.
- 2 AI Engineers.
- 3 QA Engineers.
- 2 DevOps Engineers.
- 1 Security Reviewer.

These numbers are examples.

Real allocations must be based on project analysis.

For small projects, use a small team.

For large projects, support tens or hundreds of logical agent roles.

Distinguish:
- Registered agents.
- Project allocations.
- Available agents.
- Active model invocations.
- Running execution workers.

Avoid starting 50 expensive models simultaneously simply because 50 roles were allocated.

The Workforce Planner must consider:
- Complexity.
- Skills.
- Dependencies.
- Budget.
- Priority.
- Model availability.
- Estimated effort.
- Parallelization opportunity.
- Cost efficiency.

Show the recommended organizational team to the owner.

Allow approval and manual modification.

---

# SECTION 6 — MULTI-MODEL INTELLIGENCE AND ROUTING

Build a provider-independent AI Model Gateway.

Support adapters for:
- OpenAI.
- Anthropic Claude.
- Google Gemini.
- xAI Grok.
- Ollama.
- Supported OpenAI-compatible APIs.
- Official coding-agent runtimes where suitable.

Do not hardcode invented model identifiers.

Support provider model discovery when available.

I will connect provider API keys later.

The application must start without live API credentials.

Provider-dependent agents must accurately display:
WAITING_FOR_PROVIDER or equivalent.

Do not mark them ACTIVE unless they are actually running.

Implement a separate, clearly labeled local demonstration mode for provider-free workflow testing.

## Model Registry

Store:
- Provider.
- Model ID.
- Display name.
- Context capacity.
- Capabilities.
- Tool support.
- Structured output support.
- Input and output pricing.
- Rate limits.
- Latency.
- Reliability.
- Historical benchmark scores.
- Task-specific success scores.
- Security and data classification.
- Current availability.

Support enabling and disabling models.

## Routing Policies

Allow:
- Economy.
- Balanced.
- Quality-first.
- Fastest.
- Manual selection.
- Custom policies.

Route small tasks to small economical models.

Route difficult tasks to stronger models.

Use capable coding models for complex engineering.

Use independently evaluated reviewers for security and quality-sensitive tasks.

Examples:

Simple:
- Email drafts.
- Formatting.
- Task classification.
- Summarization.

Medium:
- Business analysis.
- Documentation.
- Test case generation.
- Project planning.

Complex:
- System architecture.
- Difficult coding.
- Complex debugging.
- Multi-service integration.
- Security-sensitive design.
- Infrastructure migrations.

Choose models based on verified capabilities and benchmark results, not assumptions about brands.

## Model Routing Decision Algorithm

1. Classify task complexity.
2. Determine mandatory capabilities.
3. Check available providers.
4. Exclude incompatible models.
5. Check data security rules.
6. Check project budget.
7. Compare task-specific quality.
8. Compare estimated cost.
9. Compare latency and reliability.
10. Select a suitable model.
11. Record routing reason.
12. Evaluate actual outcome.

If execution fails:
- Retry within safe limits.
- Consider a stronger model.
- Consider an alternate provider.
- Escalate if unresolved.

Never create infinite retry loops.

## Cost Optimization

Optimize for minimum expected total cost while meeting a defined quality threshold.

Include:
- Initial invocation.
- Token usage.
- Tool usage.
- Retries.
- Validation.
- Model escalation.
- Worker infrastructure.

The cheapest invocation is not necessarily the cheapest successful task.

Track actual spending separately from estimates.

---

# SECTION 7 — CROSS-MODEL DEVELOPMENT AND VERIFICATION

I specifically want multiple AI models involved in testing and reviewing important work.

Example:

A coding agent using Claude writes a feature.

Another coding-capable model reviews the diff.

A QA agent independently creates and runs test cases.

A security reviewer checks security-sensitive code.

Use provider diversity where available and justified.

Do not merely ask models whether the code looks correct.

Every completed engineering task must have real validation evidence.

## Required Review Pipeline

1. Developer produces code.
2. Static checks run.
3. Unit tests run.
4. Independent AI code review occurs.
5. Independent QA validates functionality.
6. Security checks run when applicable.
7. Integration tests run.
8. Defects are returned to developers.
9. Fixes are independently verified.
10. Task is accepted.

For critical features, configure two independent model reviews when two eligible models are connected.

Reviewers should not be biased by reading another reviewer's verdict before making an initial independent assessment.

Do not unnecessarily duplicate every trivial task across premium models.

Apply stronger review based on project risk and complexity.

If only one provider is configured, use independent agent contexts and deterministic tests, clearly reporting the reduced model diversity.

---

# SECTION 8 — PERSISTENT MEMORY SYSTEM

THIS IS MANDATORY.

Aiventra must remember projects, conversations, decisions, architecture, task history and errors across restarts.

An AI session ending must not cause the company to forget the project.

Implement multiple memory layers.

## 8.1 Conversation Memory

Persist:
- User messages.
- AI replies.
- Attachments.
- Conversation context.
- Agent messages.
- Conversation summaries.
- References to projects.

## 8.2 Project Memory

Persist:
- Client requirements.
- Approved proposals.
- Selected architecture.
- High-level design.
- Low-level design.
- Technology decisions.
- Milestones.
- Assigned agents.
- Task history.
- Code changes.
- Test results.
- Bugs.
- Resolutions.
- Deployment records.
- Client feedback.

## 8.3 Organizational Memory

Persist:
- Department structures.
- Agent roles.
- Company policies.
- Team assignments.
- Standard procedures.
- Approved technology standards.

## 8.4 Agent Memory

Each agent needs:
- Scoped working context.
- Current assignment.
- Relevant project knowledge.
- Previous decisions.
- Recent failures.
- Tool execution history.

## 8.5 Shared Knowledge

Maintain reusable, permission-controlled knowledge:
- Known solutions.
- Engineering patterns.
- Lessons learned.
- Model performance.
- Architecture templates.
- Testing practices.

## Storage Design

Use:
- PostgreSQL for authoritative structured state.
- pgvector for semantic retrieval.
- Object storage for artifacts.
- Durable workflow checkpoints.
- Git for code history.

Store large files outside normal conversation context.

Do not put entire repositories into every prompt.

Use retrieval and context compaction.

## Memory Safety

Implement:
- Tenant isolation.
- Project access rules.
- Versioning.
- Memory provenance.
- Deletion controls.
- Sensitive data filtering.
- Expiry policies for temporary memory.
- Protection against poisoned retrieved instructions.

## Memory Acceptance Test

Create a test that:

1. Starts a project.
2. Stores requirements.
3. Makes architecture decisions.
4. Assigns tasks.
5. Shuts down the application.
6. Restarts all services.
7. Resumes the same project.
8. Retrieves previous decisions.
9. Continues remaining tasks.
10. Verifies no duplicate execution of completed external actions.

This test must pass.

---

# SECTION 9 — REAL AI-TO-AI COMMUNICATION

Build an inter-agent communication system.

Agents must be able to:
- Request analysis.
- Assign tasks.
- Ask for clarification.
- Share artifacts.
- Challenge proposals.
- Review work.
- Report errors.
- Escalate blockers.
- Participate in meetings.
- Record decisions.

Use durable messages rather than relying only on ephemeral chat.

Every message should include:
- Sender.
- Recipient.
- Department.
- Project.
- Task.
- Message type.
- Timestamp.
- Correlation ID.
- Priority.
- Content or artifact reference.
- Status.
- Authorization context.

Use bounded message processing.

## AI Meeting Engine

Implement structured meetings.

A typical architecture meeting:

Participants:
- CTO.
- Project Manager.
- Solution Architect.
- Backend Lead.
- Database Architect.
- Security Reviewer.
- CFO.

Meeting:
1. Agenda created.
2. Context shared.
3. Independent assessments submitted.
4. Disagreements identified.
5. Bounded discussion conducted.
6. Decision recorded.
7. Tasks created.
8. Meeting saved.

Allow the human owner to:
- View meetings.
- Inspect transcripts.
- Intervene.
- Ask questions.
- Overrule recommendations.

Do not let discussions run indefinitely.

All important meetings should produce a decision record or explicit unresolved issue.

---

# SECTION 10 — DURABLE AI ORCHESTRATION

Build reliable, persistent, asynchronous workflows.

Preferred technology:
Temporal for long-running business processes.

LangGraph may be used for bounded agent reasoning subworkflows with persistence.

Avoid creating two competing systems for the same responsibilities.

Architecture should clearly separate:

Temporal:
- Long-running project lifecycles.
- Job scheduling.
- Durable execution.
- Approval waits.
- Retry policies.
- Recovery.
- Cross-service coordination.

Agent framework:
- AI reasoning.
- Tool selection.
- Specialist cooperation.
- Structured agent output.
- Local agent context.

PostgreSQL:
- Authoritative business data.

Message bus:
- Inter-agent events and notifications.

## Requirements

- Durable task queues.
- Workflow IDs.
- Retry limits.
- Timeouts.
- Cancellation.
- Pause and resume.
- Checkpointing.
- Idempotency.
- Worker restart recovery.
- Dependency-aware scheduling.
- Compensating operations for partially failed workflows.
- Concurrency limits.
- Dead-letter handling where applicable.

LLM calls and external side effects should run in suitable activities or worker tasks rather than nondeterministically inside replayable workflow logic.

A workflow must not disappear if a worker crashes.

---

# SECTION 11 — ENTERPRISE PROJECT DELIVERY LIFECYCLE

After approval, generate professional SDLC artifacts.

## Requirements Phase

Generate:
- Business Requirements Document.
- Software Requirements Specification.
- Functional requirements.
- Nonfunctional requirements.
- User stories.
- Acceptance criteria.
- Constraints.
- Assumptions.
- Requirement traceability.

## Design Phase

Generate:
- High-Level Design.
- Low-Level Design.
- Architecture diagrams.
- Database schema.
- API contracts.
- Deployment architecture.
- Security model.
- Data flow diagrams.
- Dependency plan.

## Development Phase

- Create project task graph.
- Allocate workers.
- Create repository branches.
- Implement code.
- Add migrations.
- Add tests.
- Perform code review.
- Integrate components.

## Testing Phase

- Unit tests.
- Integration tests.
- API tests.
- UI tests.
- End-to-end tests.
- Regression tests.
- Performance tests.
- Security checks.
- Deployment validation.

## Final Review

The CTO, QA Lead, Security Lead, PM and Finance Agent independently review:
- Requirements coverage.
- Functional correctness.
- Architecture compliance.
- Test evidence.
- Security findings.
- Deployment status.
- Cost against budget.
- Remaining defects.
- Technical debt.

## Client Demo and Acceptance

Generate a client-ready delivery package.

Include:
- Working application.
- Demo or staging URL when actually deployed.
- Architecture documentation.
- Source repository.
- Test report.
- Deployment documentation.
- Cost report.
- Open issues.
- Change log.
- User documentation.

Do not invent a deployment URL.

Allow the client to:
- Review results.
- Request revisions.
- Accept deliverables.
- Open support requests.

---

# SECTION 12 — REAL AUTONOMOUS CODING

Aiventra must write, modify, test and debug actual software.

Implement isolated coding workspaces.

Capabilities:
- Clone approved repositories.
- Inspect project structure.
- Read code.
- Plan modifications.
- Generate code.
- Modify files.
- Run approved terminal commands.
- Install allowlisted dependencies.
- Execute tests.
- Read failure logs.
- Apply corrections.
- Create Git commits.
- Produce pull requests.
- Generate documentation.

Use isolated Docker containers or equivalent restricted execution infrastructure.

Each active worker should have:
- Task ID.
- Workspace ID.
- Repository reference.
- Branch or worktree.
- Execution policy.
- CPU and memory limits.
- Runtime limit.
- Cost budget.
- Network policy.
- Artifact storage.
- Logs.

Do not provide unrestricted host access to AI-generated code.

Never mount Docker's privileged control socket into untrusted worker containers.

Prevent task workers from reading orchestrator secrets or other clients' projects.

## Developer Workflow

1. Receive task.
2. Retrieve relevant project context.
3. Inspect authorized code.
4. Plan the implementation.
5. Write or modify code.
6. Create tests.
7. Execute checks.
8. Repair failures.
9. Commit changes.
10. Submit review request.

## QA Workflow

1. Receive change.
2. Inspect requirements.
3. Independently prepare tests.
4. Execute tests.
5. Record actual results.
6. Report failures.
7. Verify fixes.

Use merge gates to prevent unverified code from automatically entering protected branches.

---

# SECTION 13 — CONTINUE MY EXISTING CRYPTO PROJECT

This must support my existing cryptocurrency project.

Do not assume the crypto project's technology stack or business logic.

I will import its repository later.

Implement:
- Repository connection.
- Repository import.
- Existing architecture discovery.
- Dependency analysis.
- Test baseline.
- Task extraction.
- AI workforce allocation.
- Incremental development.
- QA review.
- Deployment preparation.

The AI team should understand existing code before making changes.

Never rewrite the entire crypto project unnecessarily.

Preserve working functionality.

Add crypto specialist agents only when required:
- Blockchain Engineer.
- Exchange Integration Engineer.
- Data Engineer.
- Quantitative Researcher.
- Wallet Security Reviewer.
- Smart Contract Reviewer.
- Risk Analyst.

Never disclose wallet keys or seed phrases to LLMs.

Do not perform live trading, asset transfers or financial commitments without appropriate explicit authorization.

Use sandbox or testnet environments for initial integration testing.

---

# SECTION 14 — FINANCE AND COST OPTIMIZATION

Build a complete AI FinOps subsystem.

Track:
- Tokens per request.
- Model invocation cost.
- Cost per agent.
- Cost per department.
- Cost per project.
- Retry cost.
- Cloud infrastructure cost.
- Code execution cost.
- Storage cost.
- Estimated future cost.

Create budget controls:
- Per-task budget.
- Per-agent budget.
- Per-project budget.
- Daily company limit.
- Monthly company limit.

Provide:
- Budget alerts.
- Actual and estimated cost separation.
- Cost forecasts.
- Model efficiency reports.
- Cost-saving recommendations.

An agent must not spend unlimited money because it has been assigned a large project.

Prevent uncontrolled recursive delegation or excessive AI meeting loops.

---

# SECTION 15 — SALES, CLIENT SEARCH, HR AND BUSINESS OPERATIONS

Implement operational departments with real, permissioned workflows.

## Sales

- Research permitted public business opportunities.
- Generate lead profiles.
- Qualify opportunities.
- Maintain CRM records.
- Draft proposals.
- Track sales pipelines.
- Request permission before external outreach.

## HR

- Maintain agent registry.
- Measure agent task performance.
- Compare model suitability.
- Recommend role changes.
- Recommend additional agent configurations.
- Track utilization.
- Identify bottlenecks.

## Finance

- Monitor expenditure.
- Prepare budget reports.
- Analyze project profitability.
- Recommend cost reductions.
- Track financial commitments.

## Client Success

- Manage support requests.
- Track client feedback.
- Prepare project status updates.
- Escalate unresolved issues.

## Marketing

- Draft content.
- Research market positioning.
- Prepare campaigns.
- Analyze approved campaign results.

External communication and publication require appropriate authorization.

---

# SECTION 16 — EMAIL, CALENDAR AND MCP TOOL INTEGRATIONS

Implement an extensible integration layer.

Support connectors for:
- Gmail.
- Outlook.
- Google Calendar.
- GitHub.
- Cloud providers.
- Issue trackers.
- MCP-compatible tool servers where appropriate.

Use official APIs, OAuth and supported SDKs.

The AI organization should be able to:
- Read authorized project-related email.
- Identify client requirements.
- Draft replies.
- Create project tickets.
- Schedule meetings.
- Generate meeting summaries.
- Send authorized progress reports.

Do not send external emails without approval during the initial implementation.

Implement strict tool permissions, input validation, rate limits, audit logging and human approval for sensitive actions.

---

# SECTION 17 — INDEPENDENT MONITORING AND WATCHDOG

Create an independent company monitoring service.

It must observe:
- Agent states.
- Current tasks.
- Workflow failures.
- API errors.
- LLM provider errors.
- Token consumption.
- Spending anomalies.
- Stuck tasks.
- Infinite delegation loops.
- Failed tests.
- Deployment failures.
- Unauthorized action attempts.
- Security alerts.

Implement real monitoring based on events, logs and metrics.

A language model may summarize incidents, but deterministic monitoring must remain authoritative.

Provide:
- Live dashboard.
- Agent activity timeline.
- Error logs.
- Incident reports.
- Approval queue.
- Pause and resume controls.
- Per-agent cancellation.
- Per-project cancellation.
- Global emergency stop.

The CEO must not be able to disable independent monitoring or edit immutable audit history.

---

# SECTION 18 — USER INTERFACE REQUIREMENTS

Completely improve the existing UI and UX.

Default theme:
Premium dark mode.

Design inspiration:
- ChatGPT's conversational simplicity.
- Modern developer tools.
- Professional project management software.
- Enterprise monitoring dashboards.

Do not copy proprietary branding.

## Main Pages

1. Home / AI CEO Chat.
2. Project Workspace.
3. Client Requirements.
4. Solution Comparison.
5. Architecture Review.
6. Approval Center.
7. Organization Chart.
8. Agent Directory.
9. Agent Communication.
10. Agent Meetings.
11. Project Kanban.
12. Task Dependencies.
13. Engineering Workspace.
14. Code Review.
15. Testing.
16. DevOps and Deployments.
17. Model Providers.
18. Model Router.
19. Persistent Memory.
20. Finance.
21. Sales and CRM.
22. HR.
23. Monitoring.
24. Audit Logs.
25. Settings.

## Functionality

Every button should:
- Execute its claimed operation.
- Return clear feedback.
- Handle errors.
- Respect authorization.
- Persist relevant changes.

Do not leave decorative controls that appear functional.

If a feature requires unavailable external credentials, show an informative connection state.

## Agent Activity

Show real states such as:
- Idle.
- Assigned.
- Running.
- Waiting for model.
- Waiting for approval.
- Testing.
- Blocked.
- Failed.
- Completed.

Do not fabricate active agents.

## Real-Time Updates

Use WebSockets or server-sent events where suitable.

Display:
- Live project events.
- Agent status changes.
- Task transitions.
- Test results.
- Spending updates.
- Approval requests.
- Deployment state.

---

# SECTION 19 — AUTHENTICATION

Do not create public signup or registration.

This is initially an owner-controlled platform.

Implement secure initial owner provisioning.

Support an authenticated owner dashboard.

If a client-facing portal is implemented, use invitation-based access or another secure scoped access mechanism.

Do not expose the full owner dashboard to clients.

Require authentication and permissions for expensive or destructive operations.

Do not hardcode passwords.

---

# SECTION 20 — RECOMMENDED PRODUCTION ARCHITECTURE

Prefer adapting the existing stack when possible.

If architectural changes are justified, use:

Frontend:
- Next.js.
- React.
- TypeScript.
- Tailwind CSS.

Backend:
- Python.
- FastAPI.
- Pydantic.

Database:
- PostgreSQL.
- pgvector.

Workflow Engine:
- Temporal.

Agent Orchestration:
- LangGraph or another well-supported agent runtime, with clear separation from Temporal.

Model Routing:
- LiteLLM or a provider-independent custom gateway.

Messaging:
- Durable application events and queues.

Cache:
- Redis when justified.

Object Storage:
- S3-compatible storage.

Sandboxed Code Execution:
- Restricted Docker-based workers, with production isolation reviewed carefully.

Observability:
- OpenTelemetry.
- Prometheus.
- Grafana.
- Structured logs.

Infrastructure:
- Docker Compose for local development.
- Kubernetes deployment manifests or Helm charts for production environments.
- GitHub Actions for CI/CD.

Authentication:
- Secure owner login and scoped client access.

Do not adopt every technology blindly.

Inspect the existing architecture and justify migrations.

Avoid unnecessary microservices.

Prefer a modular backend with separately scalable workers until independent services are operationally necessary.

---

# SECTION 21 — DEVOPS, DOCKER AND KUBERNETES

This functionality is required NOW.

## Docker

Create or repair:
- Dockerfiles.
- Docker Compose configuration.
- Health checks.
- Service dependencies.
- Internal networks.
- Environment configuration.
- Persistent volumes.
- Database migrations.
- Startup scripts.

The following should work from a clean development environment:

`docker compose up --build -d`

Provide documented initialization steps for any required secrets or configuration.

Test container startup.

Test database persistence after restart.

Test backend and frontend connectivity.

Test worker connectivity.

Ensure the local stack does not depend on manually running undocumented processes.

## Kubernetes

Provide production deployment support:
- Deployments.
- Services.
- Ingress configuration.
- ConfigMaps.
- Secret references.
- Health probes.
- Resource requests and limits.
- Persistent storage configuration.
- Worker scaling rules.
- Network policies.
- Deployment rollback documentation.

Use an external secrets solution or securely provisioned Kubernetes Secrets.

Do not commit live credentials.

Do not claim a Kubernetes deployment has been verified unless an actual cluster test was performed.

## GitHub Actions

Create CI workflows for:
- Backend unit tests.
- Frontend tests.
- Type checking.
- Linting.
- Production builds.
- Dependency auditing.
- Secret scanning.
- Container image builds.
- Integration tests where available.

Protect releases with appropriate approvals.

Do not automatically deploy unverified code to production.

---

# SECTION 22 — SECURITY HARDENING

Implement:
- Secure authentication.
- Role-based and project-scoped authorization.
- Input validation.
- File-upload validation.
- Prompt injection defenses.
- Tool permissions.
- API rate limiting.
- Secret management.
- Audit logging.
- Data isolation.
- Safe error handling.
- Dependency scanning.
- Container isolation.
- Budget enforcement.

Treat project documents, repository files and external websites as untrusted sources.

They must not be able to override agent permissions or company policy.

Avoid giving coding agents direct unrestricted access to:
- Host operating system.
- Docker daemon.
- Production credentials.
- Other client projects.
- Organization-wide secrets.

Sensitive actions require server-side approval enforcement.

---

# SECTION 23 — DATABASE AND PERSISTENCE

Design and maintain real database tables for:

- Users.
- Clients.
- Organizations.
- Departments.
- Agent definitions.
- Agent instances.
- Agent capabilities.
- Agent permissions.
- Model providers.
- Model configurations.
- Model benchmarks.
- Conversations.
- Messages.
- Requirements.
- Proposals.
- Solution alternatives.
- Architecture decisions.
- Approvals.
- Projects.
- Milestones.
- Tasks.
- Dependencies.
- Assignments.
- Agent meetings.
- Workflow executions.
- Execution events.
- Code workspaces.
- Repository connections.
- Artifacts.
- Test results.
- Bugs.
- Releases.
- Deployments.
- Budgets.
- Expenses.
- Incidents.
- Notifications.
- Memory records.
- Audit logs.

Use proper schema migrations.

Ensure:
- Foreign keys.
- Unique constraints.
- Transaction integrity.
- Concurrency safety.
- Project isolation.
- Recovery behavior.

Use actual database queries instead of hardcoded dashboard values.

---

# SECTION 24 — COMPLETE ERROR HANDLING AND DEBUGGING

Fix existing errors across the entire application.

Run:
- Backend test suites.
- Frontend test suites.
- Type checking.
- Linting.
- Production builds.
- Docker builds.
- Database migration tests.
- Agent workflow tests.
- Integration tests.
- Security checks.

Add missing tests.

Diagnose actual root causes.

Do not merely add try/except blocks that hide exceptions.

Frontend errors should display meaningful status and possible next actions.

Backend errors should produce structured logs.

Background workflows should record failures and support safe recovery.

Implement correlation IDs across UI, API, agent execution and workflow logs.

---

# SECTION 25 — CROSS-MODEL QUALITY GATES

For important tasks, support:

DEVELOPER MODEL
→ AUTOMATED TESTS
→ INDEPENDENT REVIEWER MODEL
→ QA MODEL
→ SECURITY REVIEW
→ PROJECT MANAGER ACCEPTANCE.

Examples:
- Claude creates a backend feature.
- An available OpenAI model reviews implementation.
- Another QA agent designs test cases.
- Automated tests execute.
- A security agent reviews important vulnerabilities.

The actual model choices must depend on available provider credentials, benchmarks and configured budgets.

Different models are useful but do not replace real execution tests.

For high-risk changes, require independent verification.

Allow the owner to configure:
- Number of reviewers.
- Review model diversity.
- Quality threshold.
- Retry limit.
- Escalation rules.
- Maximum review cost.

Do not allow code authors to independently certify their own implementation without additional verification.

---

# SECTION 26 — END-TO-END ACCEPTANCE TESTS

Create functional tests for the entire user journey.

## Test A — Requirement to Proposal

Submit:
"I want to migrate from GCP to a cheaper infrastructure."

Verify:
- Requirement saved.
- Questions generated.
- Consulting tasks created.
- Relevant agent roles selected.
- Alternative solutions analyzed.
- Proposal produced.
- Costs classified as verified or estimated.
- Approval required before execution.

## Test B — Approval to Workforce

Approve a proposal.

Verify:
- Approval persisted.
- Project created.
- Task graph generated.
- Workforce recommended.
- Allocation recorded.
- Execution begins only within approved scope.

## Test C — Workforce to Code

Assign a coding task.

Verify:
- Agent starts.
- Repository workspace created.
- Code actually changes.
- Tests execute.
- Diff generated.
- Review occurs.
- QA evidence recorded.

## Test D — Cross-Model QA

When two eligible providers are configured:
- Primary model codes.
- Independent provider reviews.
- QA executes actual tests.
- Failures trigger repair.
- Results are visible in the dashboard.

Without credentials, run controlled adapter tests without claiming live multi-provider verification.

## Test E — Persistence

- Create project.
- Run tasks.
- Save decisions.
- Stop Docker.
- Restart Docker.
- Load project.
- Confirm memory.
- Resume unfinished work.

## Test F — Budget Safety

- Configure a low project budget.
- Trigger AI tasks.
- Verify spending controls prevent exceeding the authorized hard limit.

## Test G — Approval Safety

- Attempt a protected deployment without approval.
- Verify it is blocked and logged.

## Test H — Docker

- Build containers.
- Start services.
- Run health checks.
- Verify database.
- Verify workers.
- Verify frontend.

## Test I — GitHub Workflow

- Make an isolated code change.
- Run tests.
- Commit.
- Push to an authorized branch.
- Verify CI workflow.
- Prevent unsafe force pushes.

## Test J — Final Client Delivery

- Complete a project.
- Run required reviews.
- Produce delivery artifacts.
- Generate final report.
- Show client acceptance controls.
- Record feedback.

Tests must verify meaningful functionality, not just HTTP 200 responses.

---

# SECTION 27 — BUILD IN VERIFIED IMPLEMENTATION PHASES

Implement in this order.

### PHASE 0 — Existing Project Audit

- Inspect code.
- Run services.
- Classify fake features.
- Identify errors.
- Build repair backlog.

### PHASE 1 — Production Foundation

- Fix backend and frontend.
- Fix database.
- Fix Docker.
- Secure owner authentication.
- Improve base project architecture.
- Add real logging and health checks.

### PHASE 2 — Core AI Execution

- Functional agent runtime.
- Real tool execution.
- Provider adapters.
- Agent registry.
- Agent task assignment.
- Actual agent statuses.

### PHASE 3 — Multi-Model Routing and Persistent Memory

- Provider registry.
- Intelligent model selection.
- Budget controls.
- Model benchmarks.
- Conversation memory.
- Project memory.
- Organizational memory.
- Agent memory.
- Recovery tests.

### PHASE 4 — Enterprise AI Orchestration

- Durable workflows.
- Inter-agent communication.
- AI meetings.
- Delegation.
- Approval gates.
- Restart recovery.
- Watchdog.

### PHASE 5 — Client Consulting Lifecycle

- Requirements.
- Business analysis.
- Technical research.
- Cost comparison.
- Architecture proposals.
- Client approval.

### PHASE 6 — AI Workforce Allocation

- Dynamic department selection.
- Project team planning.
- Agent scheduling.
- Work allocation.
- Dependency graphs.
- Budget-aware concurrency.

### PHASE 7 — Autonomous Engineering

- Repository integration.
- Coding sandboxes.
- Actual code generation.
- Code reviews.
- Cross-model QA.
- Automated testing.
- Debugging.

### PHASE 8 — Enterprise UI/UX Redesign

- Complete dark design system.
- ChatGPT-inspired main workspace.
- Project dashboard.
- Agent workspaces.
- Live task visualization.
- Model settings.
- Finance dashboard.
- Monitoring and approval screens.

Build essential UI flows in earlier phases as needed; Phase 8 is the comprehensive design pass.

### PHASE 9 — Business Departments

- Sales.
- CRM.
- HR.
- Finance.
- Client success.
- Email and calendar.
- Business opportunity research.

### PHASE 10 — DevOps and Production Hardening

- Docker validation.
- Kubernetes manifests.
- CI/CD.
- Security hardening.
- Observability.
- Backups.
- Disaster recovery.
- Load tests.
- Documentation.

### PHASE 11 — Crypto Project Readiness

- Repository import.
- Codebase analysis.
- Baseline testing.
- New task creation.
- Assigned AI engineering teams.
- Cross-model review.
- Tested artifact delivery.

### PHASE 12 — Final Verification and GitHub Publication

- Run all applicable tests.
- Fix discovered failures.
- Validate local Docker execution.
- Review security.
- Review source code.
- Review documentation.
- Prepare release notes.
- Commit verified work.
- Push to the existing repository.

Do not falsely mark future phases completed.

---

# SECTION 28 — GITHUB PUBLICATION

Existing target:

https://github.com/Sharath-holla/Aiventra.git

Use the existing local project.

Inspect:
- Git status.
- Current branch.
- Remote configuration.
- Commit history.
- Untracked files.
- Secret exposure risk.

Create or update `.gitignore`.

Exclude:
- `.env`
- API keys.
- Credentials.
- Tokens.
- Local database files.
- Build caches.
- Virtual environments.
- Node modules.
- Temporary execution workspaces.
- Logs containing secrets.
- Sensitive client documents.

Keep `.env.example` with placeholders.

Scan repository content and Git history for exposed secrets before publishing.

Never force push.

If permission or authentication is unavailable, prepare the commits and provide the exact commands required rather than claiming the push succeeded.

After a successful push, verify the target branch and commit.

---

# SECTION 29 — REQUIRED DOCUMENTATION

Generate or update:

- README.md
- ARCHITECTURE.md
- AUDIT_REPORT.md
- IMPLEMENTATION_STATUS.md
- NEXT_STEPS.md
- TEST_REPORT.md
- KNOWN_LIMITATIONS.md
- SECURITY.md
- DEPLOYMENT.md
- MODEL_CONFIGURATION.md
- AGENT_ORCHESTRATION.md
- MEMORY_ARCHITECTURE.md
- PROJECT_WORKFLOW.md
- CRYPTO_PROJECT_INTEGRATION.md

Include:
- Installation instructions.
- Windows 11 setup.
- Docker startup.
- Database migrations.
- Agent configuration.
- Provider API configuration.
- Secrets management.
- Worker execution.
- Testing.
- Monitoring.
- GitHub CI/CD.
- Kubernetes deployment.
- Troubleshooting.

Do not describe unimplemented capabilities as completed.

---

# SECTION 30 — CODEX EXECUTION INSTRUCTIONS

Begin by inspecting the existing local Aiventra project.

Do not ask me to repeat requirements already included here.

Use reasonable architecture decisions and document them.

Prioritize actual functionality over placeholder UI.

Do not create fake dashboard data to hide missing integrations.

If no external AI providers are configured:
- Keep the core platform operational.
- Allow configuration and management.
- Allow safe workflow testing using explicit mocks.
- Show accurate waiting states for live AI operations.
- Do not pretend models are executing.

Use proper database-backed state.

Use real Git operations.

Use real sandboxed command execution.

Use real tests.

Use actual workflow persistence.

Implement the full project iteratively.

At the end of each phase:
1. Run tests.
2. Fix failures.
3. Record completion evidence.
4. Update progress documents.
5. Preserve repository state.
6. Proceed to the next phase where feasible.

If work exceeds the execution session, leave the repository in a recoverable, documented condition so the next Codex session can continue without rebuilding earlier work.

The application must be maintainable and extensible.

Avoid giant monolithic files and duplicated logic.

Do not introduce unnecessary services.

Always respect human approval boundaries.

---

# FINAL DEFINITION OF SUCCESS

I open Aiventra OS.

I see a premium dark interface with a ChatGPT-style conversation workspace.

I type:

"I have a cryptocurrency application. Analyze it, recommend architectural improvements and implement an approved feature."

Aiventra identifies the project.

The AI CEO assigns initial analysis.

The CTO and architecture agents inspect the actual repository.

The CFO estimates development and operating costs.

The system explains technical alternatives.

I approve the proposal.

The Project Manager creates an execution plan.

The AI Resource Manager recommends an appropriate engineering team.

The model router selects available models based on capability, cost and quality.

AI developers execute real code changes in isolated workspaces.

Independent reviewers inspect the code.

QA agents execute actual tests.

Failed tests trigger bounded debugging.

DevOps prepares staging deployment.

The CTO and QA Lead conduct a final review.

The system creates a delivery report.

I can inspect every task, agent, model decision, cost, conversation, artifact and test result.

If I restart Docker, the company remembers everything and resumes properly.

If a provider fails, the system retries or escalates safely.

If a project reaches its budget, the system pauses spending.

If a sensitive operation requires approval, it waits for me.

When the project is verified, Aiventra presents the final deliverables for my review.

THAT is the intended Aiventra OS.

Build the actual engineering platform required to achieve this behavior.

Do not substitute simulations for functional execution.

**START WITH THE EXISTING PROJECT AUDIT, THEN IMPLEMENT, TEST, HARDEN AND PUBLISH THE SYSTEM PHASE BY PHASE.**