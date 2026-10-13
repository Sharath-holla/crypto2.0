# MASTER BUILD PROMPT — AI COMPANY OS
## Build a Full-Scale Autonomous, Multi-Model, AI-Operated Software and Business Organization

You are acting as a Principal Software Architect, AI Systems Architect, Senior Full-Stack Engineer, Multi-Agent Systems Engineer, Cloud Architect, Security Engineer, Technical Product Manager, DevOps Engineer, QA Director, and Engineering Program Manager.

Your assignment is to DESIGN, IMPLEMENT, TEST, DOCUMENT, and DELIVER a complete, production-oriented software platform called:

**AI COMPANY OS — Autonomous Multi-Agent Enterprise Operating System**

This must be an actual working software project, not just architectural documentation, a collection of prompts, a basic chatbot, or a visually attractive but nonfunctional demonstration.

The platform must allow one human owner to manage a virtual technology company operated primarily by autonomous AI agents.

Every department and employee role should be represented as a configurable AI agent. Every agent must have responsibilities, reporting relationships, permissions, tools, memory, objectives, policies, a model-routing strategy, and measurable performance.

The company should accept client requirements, analyze business and technical needs, compare alternative approaches, estimate costs, recommend an optimal solution, request human approval, create projects, delegate work, develop software, test it, review it, deploy approved releases, and maintain the solution.

The platform must support real client projects and importing existing repositories, particularly my existing cryptocurrency-related project.

My role as the human owner is to:
- Supervise the company.
- Issue high-level objectives.
- Communicate with the CEO or individual agents.
- Review requirements and proposals.
- Approve spending and critical decisions.
- Override or redirect agents.
- Investigate errors and debug issues.
- Approve production deployments and external actions.
- Review business performance and company costs.

AI agents should perform routine authorized work autonomously.

The central design goal is:

**MAXIMUM USEFUL AUTONOMY + LOWEST PRACTICAL COST + HIGH QUALITY + FULL OBSERVABILITY + HUMAN CONTROL.**

---

# PART 1 — NON-NEGOTIABLE ENGINEERING REQUIREMENTS

1. Create a real, extensible software product, not a proof-of-concept chat simulation.
2. Implement executable agents that can use tools and produce verifiable artifacts.
3. Implement persistent organizational, project, task, conversation, and workflow state.
4. All long-running workflows must survive process restarts.
5. Every action must be associated with an agent identity, project, task, authorization, and audit record.
6. Multiple projects must run concurrently without leaking data between projects or clients.
7. Agent conversations must cause meaningful state changes and decisions, not endless discussions.
8. Use actual provider APIs or supported coding-agent runtimes.
9. Do not invent provider APIs, model IDs, prices, features, or capabilities.
10. Verify integration interfaces against current official documentation.
11. Implement provider adapters rather than hardcoding models.
12. Implement reliable fallback if a provider is unavailable.
13. No external emails, cloud changes, purchases, payments, or production deployments without appropriate authorization.
14. Never put secrets into LLM prompts, logs, browser responses, or generated documents.
15. Use safe execution environments for all generated code.
16. Enforce cost, time, and iteration limits for every workflow.
17. All major features need automated tests.
18. Provide realistic demo data and local mock providers, but clearly separate them from live functionality.
19. No fake “completed” states, fabricated test results, or simulated cost numbers presented as real.
20. Continue implementation in incremental, testable milestones until the requested architecture and functional acceptance criteria are addressed.
21. Prefer maintainable, modular code over unnecessary microservices or dependencies.
22. Treat client inputs, repository content, retrieved documents, and agent-generated messages as untrusted unless validated.
23. Do not expose internal administration services or coding execution systems directly to the public internet.

---

# PART 2 — COMPLETE COMPANY ORGANIZATION

Create a hierarchical organization with configurable AI employees.

The company must have the following departments.

## 2.1 Executive Office

Agents:

- CEO
- COO
- Chief of Staff
- Chief Strategy Officer
- Executive Assistant
- Corporate Planning Agent

CEO responsibilities:
- Understand company objectives.
- Review client opportunities.
- Receive requirements and projects.
- Initiate consultations among relevant departments.
- Compare competing strategies.
- Make decisions within delegated authority.
- Allocate budgets and resources.
- Escalate important decisions to the owner.
- Review project progress.
- Handle cross-department conflicts.
- Present concise executive reports.

CEO must NEVER directly modify production code or bypass required controls.

The CEO should communicate with:
- CTO
- CFO
- COO
- Product Head
- Sales Head
- Project Management Head
- Risk and Security Head

## 2.2 Technology Department

Agents:

- CTO
- VP Engineering
- Enterprise Architect
- Solution Architect
- Software Architect
- Engineering Manager
- Technical Researcher
- Architecture Reviewer

Responsibilities:
- Evaluate project requirements.
- Select technologies.
- Design architecture.
- Compare infrastructure.
- Evaluate build-versus-buy.
- Identify scalability and security concerns.
- Estimate technical effort.
- Review engineering quality.
- Recommend technical solutions.

## 2.3 Product and Business Analysis

Agents:

- Chief Product Officer
- Business Analyst
- Requirements Analyst
- Product Manager
- Domain Researcher
- Technical Feasibility Analyst
- Cost-Benefit Analyst
- Product Strategy Agent

Responsibilities:
- Understand client problems.
- Extract requirements.
- Identify missing information.
- Define business goals.
- Generate user stories.
- Define acceptance criteria.
- Research alternative solutions.
- Estimate business value.
- Prepare proposals.

## 2.4 Project Management Office

Agents:

- PMO Director
- Program Manager
- Project Manager
- Scrum Master
- Delivery Manager
- Resource Allocation Manager
- Project Coordinator
- Risk and Dependency Manager

Responsibilities:
- Convert approved proposals into execution plans.
- Generate milestones.
- Create tasks and dependencies.
- Assign work to teams.
- Monitor progress.
- Detect blockers.
- Schedule AI meetings.
- Maintain project reports.
- Escalate unresolved risks.

## 2.5 Software Engineering

Agents:

- Frontend Team Lead
- Backend Team Lead
- Full-Stack Lead
- Frontend Developer
- Backend Developer
- Full-Stack Developer
- API Engineer
- Database Engineer
- Integration Engineer
- Code Reviewer
- Performance Engineer
- Refactoring Engineer

Allow multiple instances of developer agents.

Each instance must have:
- Assigned tasks.
- A scoped workspace.
- Git branch or isolated worktree.
- Access to approved dependencies.
- Permitted tools.
- Time and cost limits.
- Required test criteria.

## 2.6 AI, ML and Data Engineering

Agents:

- AI Research Lead
- AI Solution Architect
- ML Engineer
- Data Scientist
- Data Engineer
- LLM Engineer
- MLOps Engineer
- Model Evaluation Engineer
- AI Integration Engineer
- Dataset Quality Engineer

Responsibilities:
- Build ML and AI pipelines.
- Evaluate models.
- Perform data processing.
- Implement RAG where useful.
- Manage inference systems.
- Optimize ML infrastructure.
- Create evaluation pipelines.
- Review model performance.

## 2.7 Design Department

Agents:

- Design Director
- UX Researcher
- UX Designer
- UI Designer
- Design System Engineer
- Accessibility Reviewer
- Product Experience Reviewer

Responsibilities:
- Create wireframes.
- Define user journeys.
- Build reusable UI designs.
- Review usability.
- Coordinate with frontend engineers.

## 2.8 Quality Assurance

Agents:

- QA Director
- Test Manager
- Unit Test Engineer
- Integration Test Engineer
- End-to-End Test Engineer
- API Test Engineer
- Performance Test Engineer
- Regression Test Engineer
- Security Test Engineer
- Bug Triage Agent

QA agents must work independently from code-authoring agents.

A developer cannot mark its own task as independently verified.

QA must generate real execution evidence.

## 2.9 DevOps, Cloud and SRE

Agents:

- DevOps Manager
- Cloud Architect
- DevOps Engineer
- Infrastructure Engineer
- CI/CD Engineer
- Site Reliability Engineer
- Monitoring Engineer
- Release Manager
- FinOps Engineer
- Database Reliability Engineer

Responsibilities:
- Prepare cloud infrastructure.
- Build containers.
- Configure CI/CD.
- Set up deployment environments.
- Monitor applications.
- Create rollback plans.
- Optimize infrastructure costs.
- Recommend hosting alternatives.

## 2.10 Finance Department

Agents:

- CFO
- Finance Manager
- Budget Analyst
- Cost Optimization Analyst
- Pricing Analyst
- Procurement Analyst
- Financial Reporting Agent
- Revenue Forecasting Agent

Responsibilities:
- Estimate project costs.
- Track provider spending.
- Monitor budget utilization.
- Evaluate alternatives.
- Recommend cost reductions.
- Prepare financial forecasts.
- Identify inefficient agent usage.

Use deterministic financial calculations and recorded transactions for monetary figures. Never rely on language-model arithmetic alone.

## 2.11 HR and AI Workforce Management

Agents:

- CHRO
- HR Manager
- AI Recruitment Agent
- Workforce Planner
- Agent Performance Evaluator
- Skills Assessment Agent
- Agent Training Coordinator
- Resource Optimization Agent

In this AI company, HR primarily manages the virtual AI workforce.

Responsibilities:
- Evaluate agent performance.
- Identify capability gaps.
- Recommend new agent configurations.
- Maintain agent role profiles.
- Recommend replacing underperforming models.
- Allocate agents between projects.
- Track agent utilization.

HR may recommend a model change, but cannot unilaterally raise budget limits or expand permissions.

## 2.12 Sales and Business Development

Agents:

- Chief Sales Officer
- Business Development Manager
- Market Research Agent
- Client Discovery Agent
- Lead Qualification Agent
- Proposal Writer
- Opportunity Analyst
- Account Manager
- CRM Coordinator
- Partnership Researcher

Responsibilities:
- Research market opportunities.
- Find prospective business clients using permitted public sources.
- Identify business needs.
- Qualify opportunities.
- Draft proposals.
- Prepare meeting agendas.
- Track CRM records.
- Recommend sales strategies.

External outreach requires authorization, compliant contact practices, and appropriate rate limits.

## 2.13 Marketing

Agents:

- Chief Marketing Officer
- Marketing Manager
- Content Strategist
- SEO Analyst
- Social Media Agent
- Campaign Analyst
- Branding Agent
- Market Intelligence Agent

Support campaign planning, content drafts, performance measurement and human-approved publishing.

## 2.14 Client Success and Support

Agents:

- Client Success Manager
- Customer Support Agent
- Technical Support Agent
- Incident Coordinator
- Client Feedback Analyst
- Service Delivery Reviewer

Responsibilities:
- Receive client issues.
- Classify requests.
- Draft responses.
- Create support tickets.
- Escalate technical problems.
- Track SLA targets.
- Report satisfaction trends.

## 2.15 Legal, Security and Compliance

Agents:

- CISO
- Security Architect
- Security Analyst
- Compliance Analyst
- Legal Research Agent
- Privacy Officer
- Risk Manager
- Audit Manager
- Access Control Reviewer

These agents provide research, checks and recommendations. They must not pretend to be licensed legal or financial professionals.

## 2.16 Independent Monitoring Department

Agents:

- Chief Monitoring Agent
- Autonomous Watchdog
- Agent Behavior Auditor
- Budget Monitor
- Workflow Health Monitor
- Security Event Monitor
- Quality Monitor
- Incident Review Agent

These agents report directly to the human owner.

They must be independent of CEO instructions.

The CEO must not be able to disable auditing or alter historical activity logs.

---

# PART 3 — CORE CLIENT REQUIREMENTS WORKFLOW

THIS IS THE MOST IMPORTANT FUNCTION OF THE ENTIRE COMPANY.

A client should be able to enter any software, cloud, data, AI, or migration requirement using the web interface.

The AI company must act like a professional consulting firm.

Example client request:

"I want to move my workloads and data from Google Cloud to Lightning AI. Find the cheapest suitable architecture and help me migrate."

Do not immediately start coding or migrating.

Implement the following real workflow.

## Stage 1 — Client Intake

The Business Analyst:
1. Records the request.
2. Identifies business objectives.
3. Extracts technical requirements.
4. Classifies project type.
5. Identifies constraints.
6. Detects unknown information.
7. Creates a structured requirements record.

The client intake system should support:
- Free-text requirements.
- Document uploads.
- Existing project uploads.
- Repository links.
- Architectural diagrams.
- Budget information.
- Required deadline.
- Performance expectations.
- Preferred technology.
- Confidentiality constraints.
- Deployment restrictions.

## Stage 2 — Requirement Clarification

Agents should ask meaningful questions only when necessary.

For the cloud migration example:
- What workloads currently run on Google Cloud?
- Which Google Cloud services are in use?
- How much data needs to migrate?
- Is GPU acceleration required?
- What are CPU, RAM, GPU and storage requirements?
- What is the current monthly cloud bill?
- What are traffic and networking requirements?
- Are services continuously running or intermittent?
- Is downtime acceptable?
- What region or compliance requirements apply?
- Are there any managed services that must be replaced?

Do not overwhelm the client with irrelevant questions.

Maintain explicit assumptions when information is missing.

## Stage 3 — Internal Consulting Meeting

Automatically convene relevant agents.

For cloud migration:

- CEO
- CTO
- Cloud Architect
- FinOps Engineer
- Security Architect
- Business Analyst
- CFO
- DevOps Lead
- Project Manager

Each agent contributes its specialized analysis.

Architecture discussions must have:
- A defined agenda.
- Relevant project context.
- Structured recommendations.
- Evidence and sources.
- Risks.
- Alternatives.
- Action items.
- Recorded decisions.

Avoid endless agent-to-agent dialogue.

Use bounded discussion rounds with a moderator.

If disagreement remains, record competing proposals and request a decision from the responsible agent or human owner.

## Stage 4 — Independent Solution Research

Research several viable implementation approaches.

For the cloud example, evaluate options such as:
- Remaining on Google Cloud but optimizing existing resources.
- Moving eligible workloads to Lightning AI.
- Using lower-cost general-purpose VM providers.
- Using reserved, spot or serverless resources where appropriate.
- Using a hybrid infrastructure.
- Moving only GPU workloads while retaining databases elsewhere.
- Replacing expensive managed services with suitable lower-cost alternatives.

Compare verified current provider offerings.

Do not assume Lightning AI is always cheaper.

Use provider pricing APIs or verified published rates where possible.

Record:
- Source.
- Retrieval timestamp.
- Region.
- Hardware specifications.
- Pricing units.
- Availability limitations.
- Billing assumptions.
- Data egress.
- Storage.
- Network costs.
- Operational complexity.
- Migration cost.
- Reliability.
- Security.
- Data protection requirements.

Mark unverified or estimated values clearly.

## Stage 5 — Cost and Quality Optimization

The CFO and FinOps Agent should evaluate:

- One-time migration cost.
- Expected recurring cloud expenditure.
- Storage costs.
- Data transfer and egress fees.
- Software licensing.
- Operational effort.
- Migration downtime.
- Reliability.
- Scaling potential.
- Security controls.
- Long-term cost of ownership.

Generate at least three solution proposals when sufficient viable alternatives exist:

1. Lowest estimated cost.
2. Best balance of cost and performance.
3. Highest reliability or performance within the client's constraints.

Do not assume the cheapest option is automatically the best.

Generate comparison tables, trade-offs and clear recommendations.

Allow the client to change assumptions and rerun the analysis.

## Stage 6 — Client Proposal

Present a professional proposal containing:

- Executive summary.
- Business problem.
- Confirmed requirements.
- Open questions and assumptions.
- Current architecture assessment.
- Alternative solutions.
- Comparative estimated costs.
- Technical advantages and disadvantages.
- Recommended architecture.
- Risks and mitigations.
- Estimated delivery milestones.
- Proposed team.
- Expected deliverables.
- Acceptance criteria.
- Required access and approvals.

The client may:

- Approve the recommendation.
- Select an alternative.
- Request modifications.
- Reject the proposal.
- Ask additional questions.

## Stage 7 — Mandatory Approval Gateway

Implementation must not begin until the applicable client or owner approval is recorded.

Approval must be versioned against the actual proposal.

If costs, scope, or architecture change materially, request new approval.

## Stage 8 — Automatic Project Creation

After approval:
1. CEO authorizes internal execution.
2. CTO establishes the technical architecture.
3. PMO creates the project plan.
4. Resource Manager allocates agents.
5. Engineering teams receive tasks.
6. QA builds a test plan.
7. DevOps prepares infrastructure plans.
8. CFO creates project cost controls.
9. Watchdog begins monitoring.

Then the project enters execution.

---

# PART 4 — AI-TO-AI COMMUNICATION SYSTEM

Implement a real organizational communication mechanism.

Do not let agents communicate only through unstructured chat messages.

Create a persistent message bus and structured event system.

Every inter-agent message should contain:

- Message ID.
- Sender agent ID.
- Receiving agent or department.
- Project ID.
- Task ID if applicable.
- Message type.
- Priority.
- Timestamp.
- Correlation ID.
- Relevant artifacts.
- Expected response schema.
- Delivery status.
- Authorization context.

Supported message types:
- TASK_ASSIGNMENT
- TASK_ACCEPTED
- TASK_COMPLETED
- TASK_BLOCKED
- REVIEW_REQUEST
- REVIEW_FEEDBACK
- ARCHITECTURE_PROPOSAL
- COST_PROPOSAL
- APPROVAL_REQUEST
- ESCALATION
- INCIDENT_REPORT
- MEETING_REQUEST
- MEETING_DECISION
- CLIENT_CLARIFICATION
- DEPLOYMENT_REQUEST
- HUMAN_INTERVENTION_REQUIRED

Implement messaging using a durable system with delivery acknowledgments, idempotency and retry behavior.

The system should support real-time viewing through WebSockets or server-sent events.

## AI Meetings

Create an AI meeting engine.

Meeting example:

The CTO requests an architecture review.

Participants:
- CTO
- Enterprise Architect
- Backend Lead
- Database Engineer
- Security Architect
- FinOps Agent

Meeting process:
1. Set agenda.
2. Collect evidence.
3. Collect each agent's independent recommendation.
4. Identify disagreements.
5. Run a bounded discussion round.
6. Generate alternatives.
7. Record a decision or escalate.
8. Create follow-up tasks.
9. Save minutes in project memory.

Agents should not consume unlimited tokens discussing the same topic.

Support asynchronous meetings where independent agents submit analyses in parallel, followed by one synthesis round.

## Agent Communication UI

Provide:
- Company-wide communication feed.
- Department-specific channels.
- Project-specific discussion rooms.
- Meeting records.
- Decision history.
- Agent direct messages.
- Escalation inbox.
- Owner intervention interface.

---

# PART 5 — MULTI-MODEL INTELLIGENT ROUTING ENGINE

THIS IS ANOTHER CRITICAL REQUIREMENT.

The company must support multiple AI model providers.

Possible integrations:
- OpenAI models.
- OpenAI Codex-compatible coding runtimes.
- Anthropic Claude models.
- Claude Agent SDK / supported coding runtimes.
- Google Gemini models.
- xAI Grok models.
- Open-weight local models.
- Ollama-compatible endpoints.
- Other OpenAI-compatible APIs.

Important:

Do not assume consumer subscriptions provide API access.

Implement adapters for supported provider APIs and official agent SDKs.

Do not automate consumer websites using undocumented interfaces or attempt to circumvent provider restrictions.

Model names and identifiers must be loaded from provider configuration or supported discovery endpoints.

No invented hardcoded model identifiers.

## Model Registry

Maintain a database of available models.

Properties:
- Provider.
- Model identifier.
- Friendly name.
- API endpoint type.
- Supported capabilities.
- Context window.
- Tool-calling compatibility.
- Structured-output compatibility.
- Coding capability.
- Reasoning capability.
- Multimodal capability.
- Price per input token.
- Price per output token.
- Cache pricing where supported.
- Rate limits.
- Latency measurements.
- Historical evaluation results.
- Reliability statistics.
- Availability status.
- Allowed data sensitivity.
- Maximum project budget.
- Enabled or disabled.

Pricing information must include source and freshness metadata.

## Intelligent Model Selection

The organization must not use the same model for all jobs.

Example intended strategy:

Small, routine tasks:
- Classification.
- Summarization.
- Formatting.
- Task categorization.
- Basic internal messages.

Use a suitable low-cost model.

Medium-complexity tasks:
- Writing requirements.
- Creating test cases.
- Preparing project schedules.
- Ordinary research and documentation.

Use a suitable mid-tier model.

High-complexity tasks:
- System architecture.
- Difficult coding.
- Complex debugging.
- Security-critical review.
- Multi-step reasoning.
- Major migrations.
- Difficult integration.

Use a stronger reasoning or specialized coding model.

However, do not assume a model is good just because its provider advertises it.

Use evaluations and observed performance.

## Dynamic Routing Algorithm

Create a routing engine that considers:

1. Required task capabilities.
2. Task complexity.
3. Model compatibility.
4. Historical success rate on comparable tasks.
5. Expected quality.
6. Estimated monetary cost.
7. Expected latency.
8. Context size.
9. Provider reliability.
10. Project budget.
11. Security and data restrictions.
12. Tool and runtime requirements.

First exclude models that fail mandatory requirements.

Then score suitable models based on quality, cost, latency and reliability.

Choose the lowest-cost eligible model expected to satisfy the minimum quality threshold.

Implement configurable routing policies, including:

- Economy.
- Balanced.
- Quality-first.
- Fastest.
- Manual model assignment.
- Custom weighted policy.

## Model Escalation

Example:

A low-cost agent attempts a routine coding task.

If validation fails:
1. Identify the failure.
2. Attempt bounded repair.
3. Decide whether the problem requires a stronger model.
4. Escalate if justified.
5. Preserve context and artifacts.
6. Record additional cost.

Do not repeatedly retry failed tasks without limits.

## Model Benchmarking

Create an evaluation suite covering:

- Code generation.
- Code repair.
- Architecture reasoning.
- Tool use.
- Requirement extraction.
- Financial analysis.
- Structured output.
- Testing effectiveness.
- Research accuracy.

Use repeatable task datasets and objective checks wherever possible.

Track:
- Success rate.
- Quality score.
- Tokens consumed.
- Actual provider cost.
- Time required.
- Number of retries.
- Errors.
- Human correction rate.

Allow the system to recommend better model allocations over time.

The HR Agent and Model Routing Agent may recommend changes.

Only authorized roles may change provider credentials, spending limits or execution permissions.

## Model Usage Dashboard

Show:
- Current configured models.
- Active models.
- Model assigned to each agent.
- Live model requests.
- Tokens used.
- Cost per model.
- Cost per department.
- Cost per project.
- Success rates.
- Failed requests.
- Fallback events.
- Routing explanations.

Provide manual overrides.

---

# PART 6 — AUTONOMOUS DEVELOPMENT ENVIRONMENT

Agents must genuinely build software.

Provide a secure code-execution subsystem.

Capabilities:
- Read authorized repository files.
- Create isolated Git worktrees or branches.
- Write and modify source code.
- Install allowlisted dependencies.
- Run formatters and linters.
- Execute tests.
- Build applications.
- Run approved development servers.
- Produce patches and commits.
- Open pull requests through supported integrations.
- Read test output.
- Debug failures.
- Generate documentation.

Use sandboxed containers or equivalent isolation.

Apply:
- CPU and memory limits.
- Runtime limits.
- Network restrictions.
- Filesystem restrictions.
- Tool allowlists.
- Secret isolation.
- Per-project credentials.
- Approval policies.
- Artifact collection.
- Cleanup policies.

Never execute generated code directly inside the orchestration server.

## Coding Workflow

Example:

The Project Manager assigns a backend API task.

Backend Developer:
1. Reads task instructions.
2. Reads architecture specifications.
3. Inspects relevant repository files.
4. Chooses an approved implementation strategy.
5. Implements changes.
6. Writes unit tests.
7. Runs checks.
8. Commits changes to a dedicated branch.
9. Submits a review request.

Code Reviewer:
1. Inspects the diff.
2. Checks implementation against requirements.
3. Runs or requests required tests.
4. Flags defects.
5. Approves or requests changes.

QA Agent:
1. Performs independent testing.
2. Confirms actual execution evidence.
3. Checks acceptance criteria.
4. Raises defects.

Project Manager:
1. Updates task status.
2. Records accepted deliverables.
3. Unblocks dependent work.

## Parallel Development

Support multiple engineering agents working concurrently.

Avoid shared writable filesystems when possible.

Use:
- Separate worktrees.
- Task ownership.
- Interface contracts.
- Branch protection.
- Merge queues.
- Conflict detection.
- Integration testing.

Do not let multiple agents blindly overwrite the same files.

---

# PART 7 — PROJECT MANAGEMENT ENGINE

Create a persistent project management system.

Entities:
- Company.
- Client.
- Project.
- Proposal.
- Requirement.
- Milestone.
- Epic.
- Task.
- Subtask.
- Dependency.
- Sprint.
- Agent assignment.
- Approval.
- Decision.
- Risk.
- Artifact.
- Test result.
- Release.
- Incident.

Task statuses:
- Proposed.
- Awaiting approval.
- Ready.
- Assigned.
- In progress.
- Blocked.
- Review.
- Testing.
- Completed.
- Failed.
- Cancelled.

Every task should contain:
- Objective.
- Requirements.
- Acceptance criteria.
- Owner.
- Assigned agent.
- Dependencies.
- Priority.
- Estimated complexity.
- Planned budget.
- Actual cost.
- Execution evidence.
- Linked artifacts.
- Status history.

Implement dependency-aware scheduling.

Do not mark a task as completed solely because an AI agent claims it is finished.

Completion requires the applicable verification criteria.

## Project Manager Responsibilities

The AI Project Manager should:
- Generate execution plans.
- Identify the critical path.
- Assign work.
- Track blockers.
- Detect repeated failures.
- Reallocate work when authorized.
- Generate progress reports.
- Recommend schedule updates.
- Escalate scope changes.

Support Kanban board, timeline view, dependency graph and activity history.

---

# PART 8 — AUTOMATED TESTING AND DEBUGGING

Build a dedicated QA subsystem.

The tester must not simply ask a coding model whether the software is correct.

It must perform actual verification.

Support:
- Unit tests.
- Integration tests.
- API tests.
- End-to-end tests.
- Security checks.
- Dependency scanning.
- Type checking.
- Linting.
- Build verification.
- Database migration checks.
- Performance tests.
- Regression testing.

Generate and store test artifacts.

Each result should contain:
- Test command.
- Execution environment.
- Commit hash.
- Start and end timestamps.
- Exit status.
- Logs.
- Coverage where applicable.
- Failed assertions.
- Relevant screenshots or artifacts.

## Autonomous Debugging

When a test fails:
1. QA creates a defect.
2. Relevant engineering agent receives the defect.
3. Engineer diagnoses the issue.
4. Engineer implements a correction.
5. QA reruns the affected tests.
6. The system records the outcome.

After a configurable number of failures, escalate to:
- Senior Engineer.
- Architect.
- Stronger coding model.
- Human owner.

All retries must be bounded by budget and time.

---

# PART 9 — CONTINUING MY EXISTING CRYPTO PROJECT

This company must be capable of taking over ongoing development of my existing cryptocurrency project.

Do not assume its technology stack, intended functionality, exchange integrations, blockchain network, trading strategies, or deployment architecture.

First inspect the actual repository that I provide.

## Existing Project Import

Support:
- GitHub repository import through authorized integration.
- Local repository import.
- ZIP upload.
- Existing project registration.
- Read-only architecture analysis before any changes.

## Repository Discovery

Agents should analyze:
- Directory structure.
- Programming languages.
- Frameworks.
- Dependencies.
- APIs.
- Database architecture.
- Configuration.
- Tests.
- Existing documentation.
- CI/CD.
- Deployment method.
- Security risks.
- Technical debt.

Generate:
- Repository overview.
- Architecture map.
- Dependency report.
- Test baseline.
- Risk assessment.
- Suggested improvements.
- Work breakdown.

## Crypto-Specific Capabilities

If the imported project needs them, support specialists for:

- Blockchain engineering.
- Smart contracts.
- Web3 integrations.
- Exchange API integrations.
- Market data pipelines.
- Wallet infrastructure.
- Cryptographic security.
- Backtesting.
- Risk analysis.
- Transaction monitoring.
- Data analytics.
- Performance optimization.

These roles should be optional agent templates activated when relevant.

Security rules:
- Never expose wallet seed phrases or private keys to LLMs.
- Use external secret management.
- Use sandbox/testnet environments by default.
- Do not execute live trades or transfers without specifically authorized controls.
- Require human approval for financial transactions.
- Validate smart contracts with suitable automated security tests.
- Treat financial projections as estimates, not guaranteed returns.
- Protect against prompt injection inside repository files and market data.

The imported project must remain intact until the owner approves a proposed modification plan.

Before modifying existing projects, create a baseline commit or backup.

Use incremental changes, tests, clear diffs and rollback paths.

---

# PART 10 — AI SALES, CLIENT SEARCH AND BUSINESS DEVELOPMENT

Create an automated business development system.

The company should research potential project opportunities.

Capabilities:
- Industry analysis.
- Company research.
- Public business lead discovery.
- Opportunity qualification.
- Client requirement tracking.
- Proposal generation.
- CRM integration.
- Follow-up scheduling.
- Sales pipeline reporting.

Do not scrape protected private data or bypass websites' restrictions.

Use permitted APIs and reliable public information.

Sales agents may draft personalized outreach for owner review.

Do not send bulk unsolicited marketing messages or impersonate humans.

External messages should clearly identify the sender appropriately.

Record outreach permissions and contact history.

---

# PART 11 — EMAIL AND CALENDAR AUTOMATION

Support integrations such as:
- Gmail.
- Outlook / Microsoft Graph.
- Google Calendar.
- Microsoft Calendar.

Use official OAuth integrations.

Capabilities:
- Receive authorized client communications.
- Classify incoming project inquiries.
- Create project intake records.
- Draft replies.
- Schedule meetings.
- Generate agendas.
- Summarize meeting outcomes.
- Create follow-up tasks.
- Track deadlines.
- Send authorized progress reports.

Implement:
- Draft approval.
- Message previews.
- Recipient validation.
- Attachment checks.
- Audit logging.
- Sending limits.
- Duplicate-send protection.

Initially require owner approval for external email sending.

Internal agent-to-agent messages should use the company's own message infrastructure rather than sending emails unnecessarily.

---

# PART 12 — COMPANY MEMORY AND KNOWLEDGE

Implement several kinds of memory.

## Organizational Memory
Contains:
- Department structure.
- Agent responsibilities.
- Company policies.
- Standard procedures.
- Approved technology choices.

## Project Memory
Contains:
- Requirements.
- Architecture.
- Decisions.
- Code references.
- Task states.
- Meetings.
- Errors.
- Test results.
- Deployment records.

## Agent Working Memory
Contains temporary task-specific context.

## Long-Term Knowledge
Contains:
- Reusable lessons.
- Approved design patterns.
- Repeated problems and solutions.
- Provider evaluation results.
- Historical architecture decisions.

Use PostgreSQL plus pgvector or an equivalent verified approach.

Store authoritative facts in structured database tables rather than only vector embeddings.

Implement permission-aware retrieval.

An agent must not be able to retrieve another client's confidential information unless explicitly authorized.

Use summarization and context compaction to manage token costs.

---

# PART 13 — INDEPENDENT COMPANY WATCHDOG

Build an independent monitoring and control subsystem.

Watch for:
- Stuck workflows.
- Agent loops.
- Repeated failures.
- Unauthorized access attempts.
- Excessive token consumption.
- Unexpected model usage.
- Budget spikes.
- Conflicting decisions.
- Missing approvals.
- Test failures.
- Deployment incidents.
- Broken integrations.
- Unusual agent behavior.
- Data leakage risks.

The watchdog must:
1. Detect suspicious or failed activity.
2. Classify severity.
3. Save supporting evidence.
4. Alert the owner.
5. Pause unsafe operations when required.
6. Suggest recovery actions.
7. Track incident resolution.

Provide global controls:
- Pause company.
- Resume company.
- Stop specific agent.
- Stop project.
- Cancel task.
- Disable provider.
- Revoke tool access.
- Apply emergency budget limit.
- Require manual approvals.

Emergency controls must be implemented at the backend permission and execution layer, not only in the UI.

---

# PART 14 — COST MANAGEMENT AND FINOPS

The platform must prioritize cost optimization without compromising required quality.

Track:
- LLM input tokens.
- LLM output tokens.
- Cache usage.
- Provider charges.
- Agent runtime.
- Cloud compute.
- Storage.
- Data transfer.
- Development sandbox costs.
- Retry costs.
- Project-level costs.
- Department-level costs.

Provide:
- Daily budgets.
- Monthly budgets.
- Per-project budgets.
- Per-agent limits.
- Per-model spending limits.
- Spending alerts.
- Budget forecasts.
- Cost comparison charts.

Use actual billing data wherever available.

Where actual billing is unavailable, display clearly labeled estimates.

Avoid double-counting provider and infrastructure costs.

Implement reservation or preflight cost checks for expensive jobs.

A project should automatically pause or request approval when a hard budget threshold is reached.

## Cost Optimization Strategies

- Small models for routine tasks.
- Premium models for difficult tasks.
- Batch compatible operations when useful.
- Cache repeated results.
- Reuse validated project knowledge.
- Avoid sending entire repositories as prompts.
- Prefer targeted retrieval.
- Limit meeting rounds.
- Avoid unnecessary duplicate agent work.
- Use incremental analysis.
- Escalate model capability only when justified.
- Cancel obsolete tasks.
- Limit retries.
- Reuse existing solutions before rebuilding.

Create a Cost Optimization Agent that regularly reviews actual model allocation and recommends cheaper options when quality is maintained.

---

# PART 15 — SECURITY AND APPROVAL ENGINE

Implement permissions independent of AI prompts.

Use:
- Authentication.
- Role-based permissions.
- Project-scoped permissions.
- Tool-specific permissions.
- Secret management.
- Credential rotation.
- Audit logs.
- Policy enforcement.
- Sandboxed execution.

Approval categories:
- Client proposal approval.
- Architecture approval.
- Budget increase.
- Sensitive data access.
- Repository destructive changes.
- Cloud resource creation.
- External communication.
- Contract commitments.
- Payment initiation.
- Financial trading.
- Production deployment.
- Security policy changes.

Ensure an agent cannot approve its own restricted action by creating another agent or forging a message.

Use signed or server-validated authorization records with expiry, scope and version identifiers.

Reject stale approvals when the underlying proposal materially changes.

---

# PART 16 — FRONTEND APPLICATION

Build a modern, responsive enterprise dashboard.

Preferred technologies:
- Next.js.
- React.
- TypeScript.
- Tailwind CSS.
- Accessible component library.
- Real-time updates.

The UI should look like a polished professional business platform.

Do not make it unnecessarily flashy.

Prioritize functionality, information hierarchy and usability.

## Required Pages

1. Company Overview Dashboard.
2. Organizational Hierarchy.
3. AI Employee Directory.
4. Agent Detail Page.
5. Executive CEO Chat.
6. Client Requirement Submission.
7. Requirements Analysis.
8. Solution Comparison.
9. Proposal Review and Approval.
10. Project Portfolio.
11. Project Detail.
12. Kanban Board.
13. Project Timeline.
14. Task Dependency Graph.
15. AI Meeting Rooms.
16. Internal Company Messages.
17. Department Workspaces.
18. Live Agent Activity.
19. Code Execution Logs.
20. QA and Test Reports.
21. Deployment Management.
22. Finance Dashboard.
23. Model Registry.
24. Model Routing Settings.
25. Provider Configuration.
26. HR and Agent Performance.
27. Sales and CRM.
28. Client Management.
29. Email and Calendar.
30. Knowledge Base.
31. Security and Permissions.
32. Audit Logs.
33. Monitoring and Alerts.
34. Human Approval Queue.
35. System Settings.

## Dashboard Requirements

Company dashboard should display:
- Total registered agents.
- Active agents.
- Active projects.
- Pending client proposals.
- Running tasks.
- Failed tasks.
- Project progress.
- Daily AI spending.
- Monthly spending.
- Pending approvals.
- Security alerts.
- Deployment health.

Provide drill-down access to real underlying records.

## Owner Chat

Allow me to communicate with the CEO using natural language.

Example commands:
- "Show every active project."
- "Why is the crypto project delayed?"
- "Reduce unnecessary AI spending."
- "Ask the CTO to review architecture."
- "Give me the complete test report."
- "Pause all production deployments."
- "Compare alternatives to our current cloud provider."
- "Assign a stronger coding model to this task."
- "Create a new project from this requirement."

These commands must map to authenticated backend operations where appropriate.

A chat response alone must not falsely claim the action happened.

---

# PART 17 — BACKEND TECHNOLOGY

Preferred stack:

Frontend:
- Next.js + TypeScript.

Backend:
- Python + FastAPI.

Primary database:
- PostgreSQL.

Vector retrieval:
- pgvector.

Workflow orchestration:
- Temporal Python SDK, or another proven durable workflow engine.

Inter-agent messaging:
- Durable event and messaging architecture.

Model gateway:
- LiteLLM where supported, plus adapters for provider-specific capabilities.

Agent framework:
- OpenAI Agents SDK, LangGraph, or a suitably justified combination.

Authentication:
- OIDC/OAuth-compatible solution.

Storage:
- S3-compatible object storage.

Execution:
- Isolated containers or equivalent sandboxes.

Monitoring:
- OpenTelemetry-compatible tracing and metrics.

Deployment:
- Docker Compose for local development.
- Kubernetes-ready deployment configuration for future scale.

Avoid using multiple overlapping agent frameworks without a technical justification.

Do not build a complex microservice ecosystem when a well-structured modular backend with separate worker processes is sufficient.

---

# PART 18 — REQUIRED SYSTEM ARCHITECTURE

Use clean architecture principles and well-defined module boundaries.

Create these major modules:

- API Gateway.
- Identity and Access Management.
- Organization Service.
- Agent Registry.
- Agent Runtime.
- Model Gateway.
- Model Benchmarking.
- Requirement Intake.
- Consulting and Proposal Engine.
- Approval Engine.
- Workflow Orchestrator.
- Task Scheduler.
- Messaging and Meetings.
- Project Management.
- Repository Management.
- Sandboxed Coding Service.
- Test Execution Service.
- Deployment Service.
- Memory and Knowledge Service.
- Finance and Billing.
- Sales and CRM.
- Email and Calendar Integrations.
- Security Policy Engine.
- Monitoring and Watchdog.
- Artifact Storage.
- Notification Service.
- Audit Service.

Provide diagrams for:
- System architecture.
- Agent hierarchy.
- Client requirement lifecycle.
- Project execution lifecycle.
- Coding and QA workflow.
- Model routing.
- Agent communication.
- Approval and security boundaries.
- Data architecture.
- Deployment architecture.

Use Mermaid diagrams within the repository documentation.

---

# PART 19 — DATABASE DESIGN

Design normalized database entities for:

- Users.
- Organizations.
- Clients.
- Departments.
- Agent definitions.
- Agent instances.
- Agent skills.
- Agent tool permissions.
- Model providers.
- Model configurations.
- Model prices.
- Model evaluations.
- Model execution records.
- Requirements.
- Proposals.
- Solution alternatives.
- Cost estimates.
- Approvals.
- Projects.
- Milestones.
- Tasks.
- Task dependencies.
- Agent assignments.
- Workflow executions.
- Workflow events.
- Messages.
- Meetings.
- Meeting decisions.
- Repository registrations.
- Code execution sessions.
- Build results.
- Test results.
- Artifacts.
- Deployments.
- Incidents.
- Budgets.
- Spending transactions.
- Clients and contacts.
- CRM opportunities.
- Email integration records.
- Audit events.
- Notifications.

Use migration tooling.

Enforce foreign keys, uniqueness constraints and client/project isolation.

Maintain optimistic locking or other concurrency controls where needed.

Avoid storing arbitrary unvalidated model output directly in authoritative business records.

---

# PART 20 — REQUIRED PROJECT STRUCTURE

Create a maintainable monorepo resembling:

ai-company-os/
- apps/
  - web/
  - api/
  - worker/
- packages/
  - shared-schemas/
  - client-sdk/
- services/
  - orchestration/
  - agent-runtime/
  - model-gateway/
  - requirements/
  - consulting/
  - approvals/
  - messaging/
  - meetings/
  - project-management/
  - code-execution/
  - testing/
  - repository-management/
  - deployment/
  - finance/
  - memory/
  - crm/
  - monitoring/
  - security/
- agents/
  - executive/
  - technology/
  - product/
  - project-management/
  - engineering/
  - ai-ml/
  - design/
  - qa/
  - devops/
  - finance/
  - hr/
  - sales/
  - marketing/
  - client-success/
  - compliance/
  - monitoring/
- integrations/
  - model-providers/
  - coding-runtimes/
  - repositories/
  - cloud-providers/
  - email/
  - calendar/
- infrastructure/
  - docker/
  - temporal/
  - database/
  - monitoring/
  - kubernetes/
- configs/
  - agents/
  - models/
  - policies/
  - workflows/
- tests/
  - unit/
  - integration/
  - end-to-end/
  - security/
  - workflows/
  - agent-evaluations/
- docs/
  - architecture/
  - api/
  - deployment/
  - user-guide/
  - agent-design/
  - security/
  - decisions/
- scripts/
- examples/
- .env.example
- compose.yaml
- README.md

This is a reference structure, not a requirement to create empty placeholder directories.

Adjust it for maintainability while preserving clear responsibilities.

---

# PART 21 — IMPLEMENTATION PHASES

Build the system in incremental milestones.

Do not spend the entire development effort generating specifications while leaving the implementation incomplete.

## Phase 1 — Engineering Foundation

Implement:
- Monorepo.
- Development environment.
- Database.
- Authentication.
- Basic frontend shell.
- Backend API.
- Docker setup.
- CI checks.
- Health monitoring.
- Environment configuration.

Acceptance:
The application starts locally and authenticated users can access the dashboard.

## Phase 2 — Organization and Agents

Implement:
- Department registry.
- Agent role templates.
- Agent instances.
- Agent tool permissions.
- Agent runtime.
- Basic CEO interaction.
- Model provider connections.

Acceptance:
A configured AI agent can execute an authorized tool-using task and save actual results.

## Phase 3 — Model Routing and Finance

Implement:
- Multi-provider adapters.
- Model registry.
- Task complexity classification.
- Quality-aware routing.
- Budget limits.
- Provider fallbacks.
- Usage monitoring.

Acceptance:
Different tasks are routed to suitable configured models with explainable routing decisions and recorded costs.

## Phase 4 — Client Consulting

Implement:
- Requirement submission.
- Requirement parsing.
- Clarification.
- Internal consulting.
- Solution research.
- Cost comparison.
- Proposal generation.
- Approval workflow.

Acceptance:
The client can submit a migration problem and receive a realistic comparison before any implementation starts.

## Phase 5 — Project Management

Implement:
- Project generation.
- Epics.
- Tasks.
- Dependencies.
- Assignments.
- Progress monitoring.
- AI meetings.

Acceptance:
An approved proposal creates an executable project plan with assigned tasks.

## Phase 6 — Engineering and QA

Implement:
- Repository workspaces.
- Sandboxed code execution.
- Specialized coding agents.
- Code review.
- Real test execution.
- Defect tracking.
- Repair workflows.

Acceptance:
An agent can implement a small real project feature and QA can independently verify it.

## Phase 7 — Deployment and Operations

Implement:
- Staging deployment.
- CI/CD integrations.
- Environment management.
- Deployment approvals.
- Rollback workflows.
- Runtime monitoring.

Acceptance:
A tested application can be deployed to an authorized staging environment and its status verified.

## Phase 8 — Enterprise Departments

Implement:
- HR workflows.
- Sales and CRM.
- Finance reporting.
- Email and calendar.
- Client support.
- Security auditing.

Acceptance:
Department workflows run on actual stored business records with correct permission controls.

## Phase 9 — Existing Crypto Project Integration

Implement:
- Repository import.
- Architecture discovery.
- Baseline tests.
- Development task planning.
- Code modification workflows.
- Regression testing.
- Approval-controlled changes.

Acceptance:
The system can import my crypto project, analyze it and complete an approved, isolated development task without losing existing functionality.

## Phase 10 — Hardening

Implement:
- Load tests.
- Security tests.
- Provider failure tests.
- Workflow restart tests.
- Budget-limit tests.
- Multi-project concurrency tests.
- Audit verification.
- Recovery tests.
- Deployment documentation.

Acceptance:
Core workflows are reproducible, secure within the documented threat model, and resilient to expected failures.

---

# PART 22 — END-TO-END ACCEPTANCE TESTS

Create automated tests for these scenarios.

## Scenario A — New Client Consulting

A client requests migration from Google Cloud to Lightning AI.

Expected:
- Requirements recorded.
- Relevant questions generated.
- Technical agents consulted.
- Alternative architectures evaluated.
- Cost sources recorded.
- CFO analysis completed.
- Proposal generated.
- Implementation blocked pending approval.

## Scenario B — Client Approval

The client approves a proposal.

Expected:
- Approval recorded.
- Project created.
- Milestones generated.
- Tasks assigned.
- Agents execute authorized work.
- Progress appears on dashboard.

## Scenario C — Coding Task

The owner requests a new feature.

Expected:
- Engineering task created.
- Coding agent uses isolated workspace.
- Code changes produced.
- Tests executed.
- Reviewer analyzes actual diff.
- QA validates changes.
- Results recorded.

## Scenario D — Model Cost Optimization

A routine task is submitted.

Expected:
- Router identifies complexity.
- Lower-cost suitable model is chosen.
- Selection reason saved.
- Usage cost recorded.
- A quality failure can trigger bounded escalation.

## Scenario E — Provider Failure

A configured model provider becomes unavailable.

Expected:
- Timeout or failure recognized.
- Safe retry/fallback performed.
- No duplicate destructive actions.
- Execution history preserved.
- Cost and error logged.

## Scenario F — Agent Failure

An agent repeatedly produces broken code.

Expected:
- Retry limit enforced.
- Task escalated.
- Stronger model considered.
- Human notified if unresolved.

## Scenario G — Security Enforcement

An agent attempts unauthorized production deployment.

Expected:
- Backend rejects action.
- Audit record created.
- Owner receives alert.
- No deployment occurs.

## Scenario H — Budget Enforcement

A project reaches its hard spending limit.

Expected:
- Additional paid requests blocked.
- Project paused where necessary.
- Human approval requested for increased spending.
- Previously committed artifacts preserved.

## Scenario I — Crypto Project Import

An existing repository is registered.

Expected:
- Repository analyzed without unauthorized modifications.
- Architecture summary produced.
- Existing tests run when safe.
- Suggested development plan generated.
- Changes blocked pending relevant approval.

## Scenario J — Workflow Recovery

Stop and restart the worker process during an active project.

Expected:
- Persisted state survives restart.
- Workflow resumes appropriately.
- Completed tasks are not blindly repeated.
- External operations are not duplicated.

---

# PART 23 — DOCUMENTATION

Provide:

1. Complete README.
2. Quick-start instructions.
3. Windows 11 development instructions.
4. Docker installation and startup instructions.
5. Architecture documentation.
6. Database schema documentation.
7. Agent role reference.
8. Model provider configuration guide.
9. API credentials setup guide.
10. Security guide.
11. Cost-control guide.
12. Client project walkthrough.
13. Existing repository import guide.
14. Crypto project integration guide.
15. Testing guide.
16. Deployment guide.
17. Backup and restore procedures.
18. Troubleshooting guide.
19. Known limitations.
20. Future roadmap.

Create a real `.env.example` without secrets.

Include commands to:
- Install dependencies.
- Start infrastructure.
- Run database migrations.
- Start API.
- Start frontend.
- Start workers.
- Run tests.
- Seed initial departments and roles.
- Register model providers.
- Stop and restart the system.

---

# PART 24 — DEVELOPMENT QUALITY REQUIREMENTS

Use strict typing where practical.

Use:
- Python type hints.
- Pydantic validation.
- TypeScript strict mode.
- Automated formatting.
- Linting.
- Unit tests.
- Integration tests.
- Dependency security scanning.
- Structured logging.
- OpenAPI documentation.

Handle failures gracefully.

Avoid:
- Hardcoded API keys.
- Fake provider integrations.
- Mock execution paths mislabeled as live.
- Placeholder implementations of required core features.
- Frontend buttons without functioning handlers.
- Agents that only return generic advice.
- Artificial progress percentages.
- Fake meetings.
- Fake test success.
- Unbounded loops.
- Unlimited token consumption.
- Overly broad execution privileges.

Provide clear distinctions between:
- Implemented.
- Tested.
- Configured but requiring credentials.
- Not yet implemented.

---

# PART 25 — HOW YOU MUST WORK IN CODEX

First inspect the existing workspace.

If files already exist, understand them before replacing anything.

If this is a new repository, create the structure.

Start by producing:
1. Requirements specification.
2. Architecture design.
3. Database design.
4. Agent communication design.
5. Security and permission model.
6. Model routing design.
7. Implementation milestones.
8. Test plan.

Then immediately begin implementation.

Do not stop after the planning documents.

Implement in dependency order.

After each milestone:
- Run relevant tests.
- Fix failures.
- Update the implementation status.
- Record changes.
- Document limitations.
- Continue to the next milestone.

Avoid enormous single-file implementations.

Build reusable services and modules.

Where a live integration needs credentials:
- Implement the supported adapter.
- Provide configuration instructions.
- Write mock-based tests.
- Clearly mark live verification pending.
- Do not fabricate successful integration results.

For each major feature, ensure its UI calls a real backend, and its backend performs meaningful operations.

If project scope exceeds a single execution session, maintain durable project progress files such as:

- IMPLEMENTATION_STATUS.md
- NEXT_STEPS.md
- ARCHITECTURE_DECISIONS.md
- TEST_REPORT.md

These should clearly identify completed and incomplete work.

Do not claim the entire company system is production-ready if it has not been tested and hardened.

Do not delete user project data.

Do not request live credentials inside source files.

---

# PART 26 — FINAL PRODUCT EXPERIENCE

When I start the application, I want to see a real AI company dashboard.

I should be able to configure my AI providers.

I should be able to view every department and AI employee.

I should be able to send a client requirement to the CEO.

The AI company should automatically analyze the requirement.

The CTO should evaluate technical architectures.

The CFO should compare costs.

Relevant specialists should hold bounded internal consultations.

The company should present the best recommended solution with alternatives.

I should be able to approve or modify that proposal.

After approval, the organization should create a project.

The Project Manager should assign work.

Developers should use real code execution tools.

Testers should verify their work independently.

DevOps should prepare authorized deployments.

The monitoring agents should report everything important.

I should be able to see:
- Which agent is working.
- Which task it is handling.
- Which model it selected.
- Why that model was chosen.
- What the agent changed.
- What tests ran.
- What problems occurred.
- What the project has cost.
- What requires my attention.

I should be able to interrupt any agent, inspect execution history, fix errors, assign new instructions, and continue from the previous state.

The application must eventually support multiple clients and projects at the same time.

My existing crypto project must be able to become one such managed project.

---

# FINAL INSTRUCTION

Build AI COMPANY OS as a serious, modular, secure, scalable, cost-aware, multi-provider autonomous enterprise platform.

Prioritize:
1. Correct functional architecture.
2. Reliable client consultation and approvals.
3. Actual multi-agent execution.
4. Smart model selection and budget management.
5. Real software development and testing.
6. Clear supervision and auditability.
7. Existing project integration.
8. Professional frontend.
9. Documentation.
10. Extensibility.

Do not reduce this to a chatbot, generic dashboard or superficial multi-agent demo.

Use the entire specification as the implementation target.

Begin by inspecting the workspace and establishing the architecture, then implement and test the complete foundation and end-to-end workflow in practical milestones.

When technical trade-offs are necessary, choose the option that provides the best combination of reliability, maintainability, security, engineering quality and reasonable operating cost.

**START BUILDING THE ACTUAL PROJECT.**