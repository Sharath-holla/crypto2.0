# AIVENTRA OS — PHASES 2–5 COMPLETE IMPLEMENTATION
## Transform the Existing AI Company into a Fully Functional Autonomous Software Development Organization

You are acting as a Principal AI Systems Architect, Staff Software Engineer, Multi-Agent Orchestration Engineer, Full-Stack Developer, Database Architect, MLOps Engineer, DevOps Engineer, Security Architect, QA Director and Engineering Program Manager.

Your task is to continue developing my EXISTING Aiventra OS project.

**Repository:** https://github.com/Sharath-holla/Aiventra.git

**Development environment:**
- Windows 11
- VS Code / Codex
- Docker Desktop installed
- GitHub authentication available
- Existing frontend, backend, database, agent registry, workflows and CI/CD

## IMPORTANT PROJECT CONTEXT

The previous development session reported:

- Latest commit: `b9e43cf`
- Previously tested source: `ca51145`
- 66 backend tests passed
- 3 browser tests passed
- PostgreSQL and Docker Compose integration tested
- Existing login/session handling
- Existing approvals and consulting workflows
- Existing model-routing foundation
- Existing 16 departments and 136 configurable agent roles
- Existing budget enforcement
- Existing audit logging
- Existing correlated worker logs

These are historical reports. Inspect the actual current branch and source code before assuming they remain accurate.

**Do not create a new project. Do not rewrite the application from scratch.**

Continue the existing repository.

Preserve working functionality.

The objective is to implement these four major phases:

1. Phase 2 — Real AI Workforce Activation.
2. Phase 3 — Persistent Memory and Dynamic Workforce Allocation.
3. Phase 4 — Autonomous Software Engineering.
4. Phase 5 — Complete Client-to-Delivery Workflow.

All four phases must be implemented as real backend functionality with connected frontend controls, persistent state, automated tests, and verifiable execution.

Do not substitute mock data, simulated messages or static dashboards for actual functionality.

---

# SECTION 1 — INITIAL AUDIT AND DEVELOPMENT RULES

Before writing code:

1. Inspect the entire repository.
2. Read all existing architecture and progress documents.
3. Inspect the current agent runtime.
4. Inspect model provider adapters.
5. Inspect durable workflow implementation.
6. Inspect agent communication.
7. Inspect repository management.
8. Inspect existing coding and testing services.
9. Inspect database models and migrations.
10. Inspect frontend pages and API integration.
11. Inspect Docker configuration.
12. Inspect CI workflows.
13. Inspect security boundaries.
14. Run all existing tests.

Read these files if present:

- README.md
- ARCHITECTURE.md
- ARCHITECTURE_DECISIONS.md
- IMPLEMENTATION_STATUS.md
- AUDIT_REPORT.md
- TEST_REPORT.md
- NEXT_STEPS.md
- KNOWN_LIMITATIONS.md

Run:

- git status
- git remote -v
- git branch
- git log --oneline -5

Do not assume historical commit hashes are current.

Create a gap analysis specifically for Phases 2–5.

Classify every requirement as:
- Implemented and verified
- Partially implemented
- Implemented but unverified
- Mock only
- Missing
- Blocked by external credentials

Preserve existing migrations, data and commits.

Create incremental implementation milestones.

For each feature:
1. Implement backend logic.
2. Connect frontend functionality.
3. Add tests.
4. Run tests.
5. Fix errors.
6. Record results.
7. Commit verified progress.

Do not stop after generating plans or architecture documents.

---

# PHASE 2 — ACTIVATE THE REAL AI WORKFORCE

## 2.1 Objective

The existing AI agents must become operational.

Aiventra currently has many registered roles, but a registered role is not the same as a functioning AI employee.

Implement a reliable agent runtime where agents can receive tasks, call configured models, use authorized tools, produce artifacts, communicate with other agents and report actual execution status.

## 2.2 Agent Architecture

Create or complete these components:

- Agent Registry
- Agent Role Definitions
- Agent Instance Manager
- Agent Runtime
- Agent Task Dispatcher
- Agent Tool Registry
- Agent Permission Engine
- Agent Context Builder
- Model Gateway
- Execution Tracker
- Agent Performance Tracker
- Agent Message Service
- Agent Recovery Service

Each agent must have:

- Unique agent ID
- Role
- Department
- Reporting manager
- Skills
- Responsibilities
- Allowed tools
- Model selection policy
- Project assignments
- Current task
- Execution state
- Memory scope
- Permission scope
- Usage metrics
- Cost metrics
- Execution history
- Error history

Use configurable role templates.

Do not create 136 permanently running LLM processes.

Use on-demand runtime workers.

## 2.3 Agent Execution States

Implement accurate states:

- REGISTERED
- AVAILABLE
- IDLE
- ASSIGNED
- RUNNING
- WAITING_FOR_PROVIDER
- WAITING_FOR_INPUT
- WAITING_FOR_APPROVAL
- BLOCKED
- FAILED
- COMPLETED
- DISABLED

State transitions must be persisted and validated.

An agent without a configured provider must not appear to be performing live AI inference.

Show an accurate provider configuration requirement.

## 2.4 Multi-Provider AI Integration

Implement or complete support for:

- OpenAI
- Anthropic Claude
- Google Gemini
- xAI Grok
- Ollama
- Other officially supported OpenAI-compatible APIs

Use official provider SDKs where appropriate.

Do not invent model IDs.

Do not assume a consumer subscription includes API access.

Support provider-specific capabilities without exposing them as generic capabilities when unsupported.

Create adapters with consistent interfaces for:

- Text generation
- Structured output
- Tool calling
- Streaming
- Cancellation
- Usage accounting
- Error classification
- Timeouts
- Retries
- Capability discovery

The system must start without API keys.

When providers are unavailable, the UI must accurately show their connection status.

Never pretend a live provider is connected.

## 2.5 Provider Configuration UI

Create a functional AI Providers page.

Allow the owner to:

- Add a provider
- Configure API credentials
- Test connectivity
- Discover available models when supported
- Select allowed models
- Configure default models
- Assign preferred models to agent roles
- Set project-level restrictions
- Enable or disable providers
- Inspect errors
- View usage and costs

Store credentials securely.

Never return stored secrets to the browser.

Do not commit credentials to GitHub.

## 2.6 Intelligent Model Routing

Create a real model selection service.

The model router must evaluate:

1. Task complexity
2. Required capabilities
3. Model quality
4. Historical benchmark scores
5. Expected cost
6. Expected latency
7. Provider availability
8. Project budget
9. Context requirements
10. Security restrictions

Support:

- Economy
- Balanced
- Quality-first
- Fastest
- Manual override

Use the lowest-cost model that is expected to meet the required quality threshold.

Do not assume a particular model is best purely because of its name.

Maintain task-specific evaluation records.

Example:

Simple email draft → suitable economical model.

Architecture design → stronger reasoning model.

Complex backend engineering → capable coding model.

Security-sensitive review → independent technically capable reviewer.

Routine classification → small low-cost model.

## 2.7 Model Escalation

Implement escalation when a task fails.

Possible steps:

1. Detect failure.
2. Determine whether failure is caused by the model, tool, context or external system.
3. Retry safely within limits.
4. Improve relevant task context.
5. Select a stronger eligible model if justified.
6. Record additional cost.
7. Escalate to human if unresolved.

Implement retry and cost limits.

Prevent recursive delegation loops.

## 2.8 Real Agent Communication

Implement persistent, structured inter-agent messages.

Message types:

- TASK_ASSIGNMENT
- TASK_ACCEPTED
- TASK_COMPLETED
- REVIEW_REQUEST
- REVIEW_FEEDBACK
- CLARIFICATION_REQUEST
- ARCHITECTURE_PROPOSAL
- BUDGET_PROPOSAL
- MEETING_REQUEST
- MEETING_DECISION
- BLOCKER
- ESCALATION
- HUMAN_APPROVAL_REQUEST

Each message must include:

- Sender
- Recipient
- Project ID
- Task ID
- Message type
- Correlation ID
- Timestamp
- Status
- Relevant artifacts
- Authorization context

Messages should be durable, acknowledged and processed safely.

## 2.9 Agent Meetings

Create a real AI meeting workflow.

Example:

The CEO requests a meeting with:

- CTO
- Project Manager
- Solution Architect
- CFO
- Security Lead

Each agent should produce an independent assessment.

The meeting coordinator should:

1. Create agenda.
2. Collect relevant context.
3. Request agent opinions.
4. Compare disagreements.
5. Conduct bounded discussion rounds.
6. Record decisions.
7. Create follow-up tasks.
8. Save meeting minutes.

Do not generate endless dialogue.

Meetings must have token, time and iteration budgets.

Meeting records must survive application restarts.

## 2.10 Phase 2 Acceptance Criteria

Demonstrate:

- Provider configuration works.
- A real configured model executes a bounded task.
- Agent receives an assignment.
- Agent accesses approved tools.
- Agent produces a real artifact.
- Agent sends a message to another agent.
- Another agent responds.
- A meeting produces structured decisions.
- Model router records its selection reason.
- Usage and cost are recorded.
- Failures are handled.
- Agent states update correctly in the UI.

If no real credentials are available, implement and test provider contracts using clearly labeled test adapters, and mark live provider verification as pending.

---

# PHASE 3 — PERSISTENT MEMORY AND DYNAMIC AI WORKFORCE

## 3.1 Objective

Aiventra must remember its projects and organizational history, and it must intelligently allocate AI workers based on client requirements.

## 3.2 Persistent Memory Architecture

Implement five memory layers.

### A. Organizational Memory

Store:

- Company hierarchy
- Departments
- Agent role profiles
- Company policies
- Engineering standards
- Approved workflows
- Technology preferences

### B. Project Memory

Store:

- Client requirements
- Clarifications
- Approved proposals
- Project goals
- Architecture decisions
- HLD
- LLD
- Database decisions
- API contracts
- Task plans
- Assigned workers
- Code changes
- Test outcomes
- Bugs
- Fixes
- Deployment history
- Client feedback

### C. Conversation Memory

Store:

- Owner conversations
- Client conversations
- Agent messages
- Meeting transcripts
- Summaries
- Linked projects
- Referenced artifacts

### D. Agent Working Memory

Store:

- Current task context
- Recent decisions
- Relevant documents
- Execution history
- Failure information
- Tool outputs
- Work progress

### E. Semantic Knowledge Memory

Store reusable information:

- Approved architecture patterns
- Engineering lessons
- Known issues and resolutions
- Provider benchmarks
- Successful implementation strategies
- Project knowledge

## 3.3 Technology

Prefer:

- PostgreSQL for structured authoritative state
- pgvector for semantic retrieval
- Object storage for large artifacts
- Git for source history
- Existing durable workflow state for execution checkpoints

Use provider-independent embedding interfaces.

Support local embedding models if practical.

Do not require paid embedding services for the application to boot.

## 3.4 Memory Retrieval

Build context retrieval that:

1. Identifies the current project.
2. Checks agent permissions.
3. Retrieves relevant requirements.
4. Retrieves current approved decisions.
5. Retrieves relevant task history.
6. Retrieves related artifacts.
7. Uses semantic search where useful.
8. Creates bounded task context.
9. Records provenance.

Do not repeatedly send entire repositories to models.

Do not allow one client's memory to appear in another client's context.

## 3.5 Memory Updates

Implement:

- Versioned records
- Source references
- Timestamps
- Conflict detection
- Superseded decisions
- Memory invalidation
- Retention policies
- Deletion mechanisms
- Access controls

Do not let AI-generated summaries silently overwrite authoritative approved requirements.

## 3.6 Memory Recovery

Test:

1. Create a project.
2. Save requirements.
3. Conduct agent consultation.
4. Save decisions.
5. Assign tasks.
6. Stop Docker.
7. Restart Docker.
8. Load the project.
9. Retrieve previous decisions.
10. Resume unfinished work.

Verify completed tasks are not duplicated.

## 3.7 Dynamic Workforce Allocation

Implement a workforce planner that analyzes each approved project.

Inputs:

- Project requirements
- Complexity
- Deadline
- Budget
- Technologies
- Risk
- Required deliverables
- Task dependencies
- Available agent skills
- Available models
- Worker concurrency limits

Output:

- Required departments
- Required agent roles
- Number of logical workers
- Responsibilities
- Assigned tasks
- Suggested models
- Execution schedule
- Cost estimate
- Resource allocation rationale

## 3.8 Example Allocation

A small website might need:

- 1 Project Manager
- 1 Designer
- 1 Full-Stack Developer
- 1 QA Agent

A complex cryptocurrency analytics platform might need:

- Project Manager
- Business Analyst
- Solution Architect
- Backend Lead
- Backend Developers
- Frontend Lead
- Frontend Developers
- Data Engineers
- AI/ML Engineers
- Security Reviewer
- QA Engineers
- DevOps Engineers

These are examples, not fixed team sizes.

The actual allocation must be justified by project scope.

## 3.9 Scale to Large Organizations

Support hundreds or thousands of registered logical agent roles.

Do not translate 100 assigned roles into 100 simultaneous paid model calls.

Implement:

- Queued execution
- Concurrency limits
- Skills matching
- Priority scheduling
- Agent reuse
- Budget-aware scheduling
- Model-aware allocation
- Resource utilization tracking

Agents should be activated when work is available.

## 3.10 Workforce UI

Provide:

- Project team organization chart
- Allocated roles
- Assigned tasks
- Model assignments
- Estimated costs
- Active workers
- Idle workers
- Blocked workers
- Utilization metrics

Allow the owner to approve or modify the allocation.

## 3.11 Phase 3 Acceptance Criteria

Demonstrate:

- Project memory survives restart.
- Semantic retrieval returns relevant authorized records.
- Old decisions can be superseded without loss of history.
- Client/project isolation works.
- A new project produces a sensible workforce proposal.
- Allocation can be approved.
- Agent assignments persist.
- Concurrent work respects limits.
- Budget limits affect scheduling.
- The UI displays actual allocated agents.

---

# PHASE 4 — REAL AUTONOMOUS SOFTWARE ENGINEERING

## 4.1 Objective

Aiventra must be able to execute real software development tasks.

It must not merely generate code snippets in chat.

Create a secure, restricted coding execution system.

## 4.2 Coding Runner Architecture

Implement isolated coding runners using appropriate sandboxed environments.

Requirements:

- Task-specific workspace
- Repository checkout
- Isolated Git branch or worktree
- CPU and RAM limits
- Timeout limits
- Filesystem boundaries
- Network restrictions
- Secret isolation
- Execution logging
- Artifact collection
- Cleanup
- Recovery

Never run untrusted generated code directly in the orchestration server.

Do not mount unrestricted Docker daemon control into untrusted runners.

## 4.3 Repository Management

Support:

- Import existing repository
- Inspect repository structure
- Read approved files
- Create task branches
- Modify files
- Generate patches
- Run tests
- Commit code
- Create pull requests through authorized integrations
- Review differences
- Merge approved changes

Do not automatically overwrite protected branches.

Do not delete existing project data.

## 4.4 Engineering Organization

Create functional workflows for:

- CTO
- Architect
- Engineering Manager
- Team Lead
- Frontend Developer
- Backend Developer
- Full-Stack Developer
- Database Engineer
- QA Engineer
- Code Reviewer
- Security Reviewer
- DevOps Engineer

These roles may use shared underlying model providers but must maintain separate task context and permissions.

## 4.5 Coding Workflow

Example:

Client approves a new feature.

The Project Manager creates tasks.

The Architect defines interfaces.

The Team Lead assigns development tasks.

Developer:

1. Retrieves requirements and architecture.
2. Inspects repository.
3. Plans implementation.
4. Modifies code.
5. Writes unit tests.
6. Runs build and lint checks.
7. Fixes local failures.
8. Commits the changes.
9. Submits code for review.

Code Reviewer:

1. Inspects actual diff.
2. Evaluates requirements coverage.
3. Reviews architecture compliance.
4. Identifies defects.
5. Requests changes or approves.

QA:

1. Creates independent test cases.
2. Runs tests.
3. Records actual outputs.
4. Reports defects.
5. Verifies fixes.

## 4.6 Cross-Model Review

Support different eligible models reviewing important work.

Example:

- Developer model A writes code.
- Reviewer model B independently reviews the change.
- QA agent evaluates functionality.
- Deterministic test tools execute the tests.

Where two different providers are configured, allow provider-diverse review.

Preserve the existing reviewer diversity enforcement.

Do not count the same model as independent merely because two different agent roles invoke it.

Model agreement is not proof of correctness.

Real tests and security checks remain mandatory.

## 4.7 Debugging Loop

On failed tests:

1. Record failure.
2. Create defect.
3. Assign developer.
4. Inspect logs.
5. Identify root cause.
6. Produce fix.
7. Rerun relevant tests.
8. Independently verify correction.
9. Record outcome.

Bound retries.

Escalate repeated failures to stronger models or the owner.

## 4.8 Concurrent Development

Support multiple coding agents.

Implement:

- Separate worktrees
- Task ownership
- Interface contracts
- Merge conflict handling
- Branch protection
- Merge queue
- Integration testing

Prevent agents from overwriting each other's code.

## 4.9 Baseline Protection

Preserve the existing failed-baseline gates.

Do not treat preexisting test failures as introduced by a new patch.

Record:
- Baseline failures
- New failures
- Fixed failures
- Unchanged failures

Block changes that introduce unacceptable regressions.

## 4.10 GitHub Integration

Use authorized GitHub credentials.

Support:
- Repository registration
- Pull requests
- Status checks
- Commit history
- Review status
- CI results

Do not force push.

Do not expose tokens.

## 4.11 DevOps Integration

Integrate:

- Docker
- Docker Compose
- GitHub Actions
- Deployment preparation
- Environment configuration
- Build artifacts
- Health checks
- Staging deployment
- Rollback plans

Prepare Kubernetes manifests where appropriate.

Do not claim live cluster verification without actual deployment testing.

## 4.12 Phase 4 Acceptance Criteria

Demonstrate:

- A real sample repository can be imported.
- A coding task is created.
- An isolated runner starts.
- A developer agent modifies real code.
- Changes appear in an actual Git diff.
- Tests execute.
- Review occurs.
- QA records evidence.
- Defects trigger repair.
- An approved change can be committed and prepared for merge.
- The UI displays true execution history.

When no real model credentials exist, test runner isolation and lifecycle using deterministic fixtures, and mark autonomous live coding verification as pending.

---

# PHASE 5 — COMPLETE CLIENT-TO-DELIVERY LIFECYCLE

## 5.1 Objective

Connect Phases 2–4 into one functional business workflow.

A client must be able to submit a requirement and receive a verified software deliverable after approval.

## 5.2 Requirement Intake

Support:

- Natural-language requirement submission
- File uploads
- Repository references
- Project documents
- Budget
- Deadline
- Preferred technologies
- Security requirements

Create persistent requirement records.

## 5.3 Business and Technical Analysis

Business Analyst:

- Extracts objectives
- Determines functional requirements
- Determines nonfunctional requirements
- Identifies missing information
- Creates structured specification

CTO and Architects:

- Evaluate feasibility
- Compare architectures
- Determine technologies
- Identify risks
- Recommend implementation approach

Finance:

- Estimate implementation and operating costs
- Compare alternatives
- Recommend cost optimization

Security:

- Identify compliance, privacy and technical risks

## 5.4 Internal Consultation

Run structured collaboration between relevant agents.

For a cloud migration:

- CEO
- CTO
- Cloud Architect
- Security Architect
- CFO
- FinOps Engineer
- Project Manager

They should compare actual viable infrastructure options.

Example:

"I want to move workloads from Google Cloud to Lightning AI."

The system should consider alternatives rather than blindly recommending Lightning AI.

Compare:

- Existing GCP optimization
- Lightning AI
- General-purpose virtual machines
- Managed compute
- Hybrid infrastructure
- Relevant serverless alternatives

Use real documented pricing where available.

Mark uncertain estimates clearly.

## 5.5 Proposal Generation

Create a professional proposal with:

- Executive summary
- Requirements
- Assumptions
- Solution alternatives
- Cost comparison
- Architecture diagrams
- Technical stack
- Security implications
- Risks
- Recommended solution
- Milestones
- Proposed AI team
- Acceptance criteria

Provide at least three meaningful alternatives when viable.

## 5.6 Human Approval

The client or owner may:

- Approve
- Reject
- Request modification
- Select alternative
- Change budget
- Change requirements

Preserve versioned proposals and approval history.

Do not proceed with implementation without relevant approval.

## 5.7 Project Creation

After approval:

1. CEO authorizes implementation.
2. CTO finalizes architecture.
3. Project Manager generates milestones.
4. Workforce Planner recommends agents.
5. Owner approves allocation where required.
6. Tasks are assigned.
7. Engineering begins.

## 5.8 Technical Design

Generate:

- Business Requirements Document
- Software Requirements Specification
- High-Level Design
- Low-Level Design
- API specifications
- Database schema
- Architecture diagrams
- Deployment architecture
- Test strategy

Store these artifacts in persistent project memory.

## 5.9 Implementation

Engineering agents:

- Create branches
- Implement code
- Write tests
- Perform reviews
- Fix defects
- Produce build artifacts

Project Manager monitors dependencies and progress.

## 5.10 Final Testing

Before delivery, execute:

- Unit tests
- Integration tests
- API tests
- UI tests
- Regression tests
- Security checks
- Deployment readiness checks

Use independent reviewers.

## 5.11 Final Company Review

The CTO, QA Lead, Security Lead, Project Manager and Finance Agent review:

- Requirements coverage
- Technical correctness
- Architecture consistency
- Test evidence
- Security issues
- Budget usage
- Remaining defects
- Deployment readiness

Record the final decision.

## 5.12 Client Demonstration

Provide a client-facing result page.

Display:

- Project summary
- Completed features
- Deliverables
- Architecture
- Test reports
- Code repository
- Deployment status
- Known issues
- Cost report
- User documentation

If a working staging deployment exists, provide its verified URL.

Do not fabricate deployment links.

## 5.13 Client Acceptance

Allow client or authorized owner to:

- Accept delivery
- Request changes
- Report defects
- Request support
- Reject incomplete deliverables

Record acceptance status.

## 5.14 Complete Delivery Acceptance Test

Demonstrate the entire process using a safe example application.

Example request:

"Build a task-management web application with login, task creation, task assignment and an admin dashboard."

Required flow:

1. Requirement submission
2. Business analysis
3. Architecture recommendation
4. Cost estimate
5. Proposal
6. Approval
7. Workforce allocation
8. Project planning
9. Coding
10. Testing
11. Independent review
12. Staging deployment if an authorized environment is available
13. Final review
14. Delivery package
15. Client acceptance

Verify every transition through actual persisted records and artifacts.

Do not consider a series of mocked API responses a successful end-to-end test.

---

# CROSS-PHASE REQUIREMENT — PREMIUM UI/UX

The existing Aiventra UI needs substantial improvement.

While implementing Phases 2–5, redesign the interface into a polished dark-themed AI company operating system.

Make the main interaction conversational, similar in usability to ChatGPT.

Main features:

- AI CEO chat
- Persistent conversations
- File uploads
- Project selection
- Agent activity
- Project progress
- Workforce visualization
- Model routing details
- Task management
- QA reports
- Memory search
- Approval center
- Finance monitoring
- Execution logs
- Final client delivery

Create an attractive dark-first design with:

- Clean typography
- Consistent spacing
- Responsive layouts
- Accessible colors
- Excellent loading states
- Clear error messages
- Smooth but restrained animations
- Well-organized navigation
- Readable cards and tables
- Useful dashboards

No fake progress indicators.

No dead buttons.

No static status labels pretending to show live execution.

Use real backend state.

Provide browser tests for all major UI workflows.

---

# CROSS-PHASE REQUIREMENT — SECURITY

Preserve and improve:

- Owner authentication
- Secure sessions
- Login rate limits
- API authorization
- Project isolation
- Audit logging
- Secret management
- Approval enforcement
- Budget enforcement
- Code execution isolation

Do not add public registration.

Support invitation-based client access only where required by the client delivery workflow.

Critical operations requiring authorization include:

- Production deployment
- External communications
- Budget increases
- Sensitive data access
- Destructive repository actions
- Financial transactions
- Live cryptocurrency transfers

Never send private keys, wallet seed phrases or production secrets into model prompts.

---

# CROSS-PHASE REQUIREMENT — FINOPS

Track real spending associated with:

- Models
- Agents
- Tasks
- Projects
- Reviews
- Retries
- Tool execution
- Infrastructure

Separate estimates from actual charges.

Enforce spending caps.

Support economy, balanced and quality-first policies.

Make model selection explainable.

---

# CROSS-PHASE REQUIREMENT — OBSERVABILITY

Implement real-time operational monitoring.

Track:

- Agent state
- Current task
- Workflow status
- Model used
- Routing reason
- Token usage
- Cost
- Failures
- Retry attempts
- Tool execution
- Test results
- Deployment state

Use correlated logs and trace IDs.

Provide working pause, resume, cancel and emergency-stop controls.

The independent watchdog must not be overridable by the CEO agent.

---

# CROSS-PHASE REQUIREMENT — DOCKER AND DEVOPS

Ensure local development works through Docker Compose.

Verify:

- Frontend
- Backend
- PostgreSQL
- Worker services
- Agent orchestration
- Memory services
- Execution infrastructure
- Health checks
- Database migrations

Document startup commands.

Implement GitHub Actions for:

- Backend tests
- Frontend tests
- Typecheck
- Lint
- Build
- Migrations
- Container builds
- Security scans
- Integration tests

Maintain Kubernetes deployment configuration where relevant.

Do not claim live deployment verification unless tested.

---

# CROSS-PHASE REQUIREMENT — CRYPTO PROJECT READINESS

My existing cryptocurrency project will be imported into Aiventra later.

Prepare support for:

- Git repository import
- Architecture analysis
- Dependency analysis
- Baseline tests
- Improvement proposals
- Agent team allocation
- Autonomous coding tasks
- Code review
- Cross-model QA
- Deployment preparation

Do not assume its existing technology stack.

Preserve existing functionality.

Use isolated environments.

Do not perform live trades or financial transfers without explicit authorization.

---

# REQUIRED AUTOMATED TESTING

Run and extend existing tests.

Required suites:

1. Agent runtime tests
2. Provider adapter tests
3. Model routing tests
4. Agent communication tests
5. Meeting workflow tests
6. Memory persistence tests
7. Semantic retrieval tests
8. Workforce allocation tests
9. Budget enforcement tests
10. Coding runner isolation tests
11. Git workflow tests
12. Cross-model review tests
13. QA automation tests
14. Approval tests
15. Client lifecycle tests
16. Frontend browser tests
17. Docker restart tests
18. PostgreSQL concurrency tests
19. Security tests
20. End-to-end delivery tests

Every test result must be reported accurately.

Do not disable tests to hide failures.

---

# IMPLEMENTATION EXECUTION STRATEGY

Implement in this exact sequence:

## Milestone A — Phase 2 Foundation
- Complete provider adapters.
- Complete real agent runtime.
- Complete model routing.
- Complete agent messaging.
- Test live bounded execution where credentials are available.

## Milestone B — Phase 3 Memory
- Complete memory architecture.
- Semantic retrieval.
- Project isolation.
- Restart persistence.
- Recovery tests.

## Milestone C — Phase 3 Workforce
- Requirements-based team planning.
- Resource scheduling.
- Budget-aware assignment.
- Workforce dashboard.

## Milestone D — Phase 4 Coding
- Isolated runners.
- Repository workspaces.
- Code execution.
- Git integration.
- Reviews and QA.
- Debugging.

## Milestone E — Phase 5 Client Workflow
- Requirement intake.
- Consultation.
- Architecture comparison.
- Proposal.
- Approval.
- Workforce.
- Engineering.
- Testing.
- Final review.
- Delivery.

## Milestone F — UI/UX and Integration
- Complete premium dark UI redesign.
- Connect every screen to real backend services.
- Run browser and end-to-end tests.

Implement essential UI controls during earlier milestones rather than postponing all frontend work.

## Milestone G — Production Verification
- Docker testing.
- Security checks.
- CI/CD.
- Observability.
- Recovery tests.
- Documentation.

## Milestone H — GitHub Publication
- Verify all changes.
- Run tests.
- Run secret scanning.
- Update documentation.
- Commit tested work.
- Push to the existing GitHub repository.
- Verify GitHub Actions.

---

# DOCUMENTATION

Update:

- README.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- TEST_REPORT.md
- NEXT_STEPS.md
- KNOWN_LIMITATIONS.md
- AGENT_ORCHESTRATION.md
- MODEL_ROUTING.md
- MEMORY_ARCHITECTURE.md
- WORKFORCE_ALLOCATION.md
- CODING_RUNTIME.md
- CLIENT_DELIVERY_WORKFLOW.md
- SECURITY.md
- DEPLOYMENT.md

Preserve relevant earlier documentation.

Avoid contradictory status reports.

Clearly distinguish:

- Implemented
- Tested
- Live verified
- Mock tested
- Requires credentials
- Not implemented

---

# FINAL SUCCESS CRITERIA

When I open Aiventra OS, I should see a professional dark-themed AI company dashboard.

I should be able to talk to the AI CEO.

I submit:

"Build a complete web application for managing projects and tasks."

The company analyzes the requirement.

The CTO and specialist agents discuss architecture.

Finance compares implementation and operating costs.

Aiventra recommends the best technical solution.

I approve the proposal.

The Workforce Planner recommends an appropriate AI team.

The Project Manager allocates tasks.

The model router selects suitable configured models.

Coding agents create actual software in isolated environments.

Other models independently review important code.

QA agents execute real tests.

Failed tests trigger debugging.

DevOps prepares an authorized staging deployment.

The CTO and QA Lead conduct a final review.

Aiventra generates the complete client delivery package.

All project knowledge persists across restarts.

I can monitor agents, models, work, costs, errors, conversations, decisions and deliverables through the UI.

No fake workers.

No fake test results.

No fake deployment statuses.

No fake progress metrics.

No arbitrary AI conversations without task outcomes.

Every critical operation must have actual code, execution evidence and stored records.

The platform must be capable of continuing development of my cryptocurrency project once connected.

**IMPLEMENT PHASES 2, 3, 4 AND 5 COMPLETELY IN THE EXISTING AIVENTRA REPOSITORY, IN VERIFIED INCREMENTS. RUN TESTS, FIX ERRORS, UPDATE DOCUMENTATION AND PUSH VERIFIED PROGRESS TO GITHUB.**

START BY AUDITING THE CURRENT SOURCE AND IMPLEMENTING MILESTONE A.
