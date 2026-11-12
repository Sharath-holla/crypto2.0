# AIVENTRA OS — COMPLETE SIMPLIFIED UI, MASTER AI ORCHESTRATION & REAL-WORLD ENGINEERING IMPLEMENTATION

## THE NEXT MAJOR DEVELOPMENT MILESTONE

**Project:** Aiventra OS
**Repository:** https://github.com/Sharath-holla/Aiventra.git
**Application:** Existing Next.js + FastAPI AI company operating system
**Environment:** Windows 11, VS Code, Codex, SQLite, Docker/CI and GitHub
**Objective:** Completely simplify the frontend experience while integrating one central Lead AI that dynamically orchestrates specialized AI workers.

---

# 0. YOUR ROLE AND IMPLEMENTATION MISSION

Act as a coordinated team of:

- Principal AI Systems Architect
- Staff Full-Stack Engineer
- Multi-Agent Orchestration Engineer
- Enterprise UX Designer
- Backend Systems Engineer
- Database Architect
- AI Model Integration Engineer
- Security Architect
- QA Automation Engineer
- DevOps Engineer
- Technical Product Manager

You are responsible for implementing real, maintainable and tested software in my EXISTING Aiventra OS repository.

## My Main Problem

Aiventra currently has many powerful features:

- AI departments
- AI employees
- Model providers
- Model routing
- Workflows
- Projects
- Task management
- Approvals
- Finance
- Memory
- Meetings
- GitHub
- Engineering
- QA
- Delivery
- Reports
- Monitoring

However, the user interface is becoming too complicated.

Even I, the owner of the platform, sometimes find it difficult to understand what to do next.

An ordinary user should not need to understand agent registries, provider adapters, orchestration graphs or technical execution states.

**I want Aiventra to become extremely simple on the frontend while maintaining its advanced AI-company functionality in the backend.**

The new product philosophy is:

**ONE SIMPLE INTERFACE. ONE LEAD AI. AUTOMATIC SPECIALIZED WORKERS. COMPLETE OWNER CONTROL.**

Do not rebuild the existing project.

Do not discard completed functionality.

Implement a professional, production-oriented frontend redesign and orchestration integration using the existing source code.

---

# 1. CURRENT PROJECT BASELINE

Inspect the repository and verify the actual current state.

Previously reported:

Application source:
`2e9ba43`

Documentation:
`f45fcde`

These are historical references, not guaranteed current HEAD values.

The latest reported milestone includes:

- 300 passing backend tests
- 23 passing browser journeys
- Six passing GitHub Actions jobs
- Phase 3 persistent memory
- Dynamic workforce planning
- Phase 4 coding runner and engineering workflows
- GitHub PR publication connector
- Phase 5 immutable delivery packages
- Exact owner release approvals
- Invitation-only client access
- Client acceptance, revision and support workflows
- Project closure/reopen processes
- SQLite active
- PostgreSQL compatibility retained
- ZERO_COST_ONLY enforcement

Live AI inference, actual generated PR publication and complete real-world client delivery have not yet been verified.

These claims must be checked against the repository.

## Read Existing Documentation

Inspect:

- README.md
- AGENTS.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- TEST_REPORT.md
- PROJECT_WORKFLOW.md
- AGENT_ORCHESTRATION.md
- MODEL_CONFIGURATION.md
- MODEL_ROUTING.md
- WORKFORCE_PLANNING.md
- WORKFORCE_ALLOCATION.md
- SEMANTIC_MEMORY.md
- CLIENT_DELIVERY_WORKFLOW.md
- ZERO_COST_AI_POLICY.md
- SECURITY.md
- DEPLOYMENT.md

Preserve all existing functionality.

Run the existing backend, frontend and browser tests before modifications.

Do not delete working modules simply because they are not visible in the new interface.

---

# 2. MAJOR PRODUCT DESIGN CHANGE

The current experience should be redesigned around a single question:

**"What would you like Aiventra to build or improve?"**

Instead of requiring users to navigate through multiple technical pages, the platform should guide them naturally.

The main user journey must be:

1. Describe or upload project requirements.
2. Choose the Lead AI model.
3. Choose Automatic or Manual worker selection.
4. Review the generated project plan.
5. Approve the plan.
6. Watch the AI workforce execute.
7. Review results and approvals.
8. Receive verified deliverables.

The default experience should hide unnecessary implementation details.

Use progressive disclosure.

Advanced controls must remain accessible for technical users.

This is an actual UI and workflow redesign, not simply a CSS color change.

---

# 3. REDESIGN THE APPLICATION NAVIGATION

## 3.1 Main Sidebar

The default navigation should contain only:

- Home
- New Project
- My Projects
- Activity
- Approvals
- Settings

Add an expandable:

**Advanced**

Inside Advanced, retain:

- Organization
- Departments
- Agent Registry
- Workforce Management
- Model Benchmarks
- Model Routing
- Memory Explorer
- Tools
- Meetings
- Finance
- Security
- Audit Logs
- Developer Logs
- Infrastructure Monitoring

These sections must continue using existing working routes and APIs.

Do not delete them.

## 3.2 Sidebar Behavior

Implement:

- Expand/collapse.
- Compact icon mode.
- Clear active navigation.
- Responsive mobile drawer.
- Keyboard accessibility.
- Remembered display preferences.
- Search or quick navigation where useful.

Do not overwhelm the sidebar with 20 primary destinations.

## 3.3 Home Page

Make the home page conversational.

It should show:

- Aiventra branding.
- A clear greeting.
- Central requirements input.
- New Project action.
- Continue Existing Project action.
- Recent project history.
- Pending approvals.
- Current work requiring attention.

Avoid unnecessary financial charts and dense dashboards on the home screen.

The primary action must be immediately understandable.

---

# 4. BUILD A THREE-STEP PROJECT CREATION EXPERIENCE

This is one of the most important requirements.

**Model selection must happen during project requirements submission.**

Do not require the user to navigate separately to Settings to choose the project models.

Implement the workflow using the existing project creation, requirements and approval services.

## STEP 1 — DESCRIBE YOUR PROJECT

Show:

**What would you like Aiventra to build?**

Provide a large, attractive input area.

Support:

- Plain-English description
- Requirement text
- Drag-and-drop files
- Existing project selection
- GitHub repository selection
- Technology preferences
- Optional budget
- Optional deadline
- Optional constraints

Example requirement:

"Analyze my existing cryptocurrency analytics platform, find architectural weaknesses, identify improvements, and implement approved changes."

The user should be able to write the entire requirement directly.

### Upload Handling

Allow supported documents.

Validate:
- File type.
- File size.
- Content.
- Filename.
- Storage permissions.

Reuse existing secure upload processing.

Show uploaded filenames, processing status and parsing errors.

Persist requirement drafts.

If rich PDF, DOCX or image extraction is not currently available, implement supported safe parsers as appropriate or explain unsupported formats. Do not claim successful extraction when it has not happened.

### GitHub Repository Selection

Allow:
- Existing configured repositories.
- Authorized repository URL/import.
- Branch selection.
- Read-only initial inspection.

Do not clone arbitrary repositories with elevated credentials.

Never execute code from imported repositories outside the authorized runner.

### Draft Persistence

If the browser closes, the requirement draft must remain recoverable.

Use existing SQLite persistence.

---

# 5. STEP 2 — CHOOSE THE AI MODELS

This is my main requested change.

The model selection screen must appear directly after requirements submission.

It should have only two main sections.

## A. LEAD AI — MASTER ORCHESTRATOR

Display:

**Choose the AI that will lead your project.**

This is the central planning and coordination model.

My preferred Lead AI is:

**GPT-6.1 Sol**

Store it as the preferred model.

Do not assume its API identifier, availability, entitlement or capabilities without verifying the currently supported official provider catalog.

If a matching registered model is available, use its exact discovered identifier.

If it is unavailable or blocked by billing policy, preserve the user preference but clearly show that it cannot currently execute.

Do not invent an available provider connection.

### Lead AI Selector

Show available or configured models from:

- OpenAI
- xAI/Grok
- DeepSeek
- Ollama
- Other existing connected providers

Do not hardcode fake model entries.

A specifically requested preference may be represented as an unavailable favorite, clearly distinguished from discovered executable models.

Each model should show:

- Display name.
- Provider.
- Current availability.
- Capability summary.
- Verified free/paid status.
- Context limitations when known.
- Tool calling support.
- Reason when blocked.

### Default Selection

Save:

Preferred Lead AI: GPT-6.1 Sol.

The preference is not authorization to make paid inference requests.

Keep ZERO_COST_ONLY enabled.

If GPT-6.1 Sol requires billable API access, do not invoke it.

Show:

"Your preferred Lead AI is saved but cannot currently run under zero-cost mode."

Allow me to explicitly choose a different eligible model for the current project.

Do not silently change my preferred Lead AI.

## B. WORKER MODEL SELECTION

Below the Lead AI selector, show:

**Who should perform the project tasks?**

Default choice:

**Automatic — Let the Lead AI choose the best models.**

Alternative:

**Manual — I'll choose the models myself.**

### Automatic Mode

The Lead AI proposes the best specialist workers and eligible model assignments.

For example:

- Business analysis
- Architecture
- Coding
- Documentation
- QA
- Security
- Data engineering
- DevOps

Only allocate roles needed by the project.

Do not automatically activate all 136 registered agent roles.

### Manual Mode

Let the owner configure model preferences by:

- Role.
- Department.
- Workstream.
- Individual task.

Show only real registered models.

Validate capability and spending eligibility.

The owner should not need to select a model for every unused role.

### Hybrid Mode

Also support a practical hybrid:

- Lead AI automatically selects workers.
- Owner overrides specific assignments.

This allows fine control without complicating the default experience.

---

# 6. STEP 3 — REVIEW AND CREATE THE PROJECT

Show one simple summary.

Fields:

- Project name.
- Short requirement summary.
- Uploaded files.
- Linked GitHub repository.
- Preferred Lead AI.
- Effective Lead AI availability.
- Worker selection mode.
- Available worker pool.
- Spending policy.
- Required approvals.

Primary action:

**Create Project & Prepare Plan**

Avoid promising immediate AI execution if no eligible Lead AI is available.

When no eligible model exists, save the project and offer:

- Wait for model availability.
- Choose another eligible model.
- Continue with a manually authored plan.
- Return to project later.

A manually authored plan must be distinguished from AI-generated analysis.

When an eligible Lead AI is available, use the existing orchestration engine to generate a structured planning proposal.

---

# 7. CENTRAL LEAD AI ARCHITECTURE

Implement a Lead AI orchestration layer.

Do not create a second independent workflow engine.

Reuse:
- Existing model gateway.
- Agent runtime.
- Durable workflow system.
- Workforce planner.
- Memory retrieval.
- Agent messaging.
- Approval engine.
- Budget policy.
- QA and engineering services.

## 7.1 Lead AI Responsibilities

The Lead AI should:

1. Understand the user's requirement.
2. Read authorized project context.
3. Retrieve relevant long-term memory.
4. Identify missing requirements.
5. Determine project complexity.
6. Recommend a technical architecture.
7. Propose necessary workstreams.
8. Identify required agent roles.
9. Recommend suitable worker models.
10. Generate a task breakdown.
11. Determine task dependencies.
12. Estimate resource requirements.
13. Identify important risks.
14. Prepare a project plan.
15. Ask for approval.
16. Coordinate approved work.
17. Monitor results.
18. Recommend reassignment when necessary.
19. Escalate blockers.
20. Summarize progress and deliverables.

The Lead AI should be the main coordination interface, not an unrestricted administrator.

## 7.2 Lead AI vs Backend Authority

The Lead AI makes decisions and recommendations about:

- Task decomposition.
- Role selection.
- Model suitability.
- Workstream planning.
- Dependency suggestions.
- Technical alternatives.
- Recovery recommendations.

Deterministic backend systems enforce:

- Permissions.
- Database transactions.
- Budget limits.
- ZERO_COST_ONLY.
- Tool access.
- Approval status.
- Task states.
- Worker ownership.
- Retry bounds.
- Concurrency limits.
- Cancellation.
- Release authorization.

The Lead AI must not be allowed to bypass these enforcement systems.

---

# 8. VERSIONED PROJECT PLAN CONTRACT

Create or extend a strict schema-validated orchestration plan.

Recommended fields:

- plan_id
- organization_id
- project_id
- requirement_version
- lead_provider_id
- lead_model_id
- lead_selection_status
- plan_version
- architecture_summary
- workstreams
- milestones
- tasks
- dependencies
- required_roles
- worker_model_proposals
- model_selection_rationale
- acceptance_criteria
- risks
- resource_estimates
- approval_requirements
- created_at

Each task should contain:

- Task ID.
- Description.
- Workstream.
- Required skills.
- Complexity.
- Required model capabilities.
- Assigned logical agent.
- Proposed model.
- Allowed tools.
- Dependencies.
- Acceptance criteria.
- Estimated resources.
- Review requirements.

Use existing schema and migration conventions.

Reject:
- Invalid model identifiers.
- Cross-project references.
- Unauthorized tools.
- Circular dependencies.
- Incompatible assignments.
- Unapproved scope.
- Budget violations.
- Unsupported provider capabilities.

The plan must be versioned.

When requirements change, create a new version.

Do not silently overwrite previously approved plans.

---

# 9. INTELLIGENT MODEL ROUTING AND WORK ALLOCATION

The Lead AI should choose models based on the task, not only brand or size.

## 9.1 Task Difficulty

Classify tasks as:

**Simple**
- Formatting.
- Summaries.
- Classification.
- Basic documentation.

**Standard**
- Requirements analysis.
- Test planning.
- Routine coding.
- Database queries.

**Advanced**
- Complex coding.
- Architecture.
- Debugging.
- Multi-service integration.
- Security analysis.

**Critical**
- Production migrations.
- Sensitive security changes.
- Financial or cryptocurrency operations.
- High-risk deployment changes.

## 9.2 Model Assignment

Examples:

Simple documentation → capable lightweight model.

Moderate coding → eligible coding model.

Advanced architecture → stronger eligible reasoning model.

Complex debugging → capable coding/reasoning model.

QA → independent qualified reviewer.

These are examples only.

Do not hardcode specific models into these roles.

## 9.3 Eligibility Filter

Before accepting the Lead AI's proposed worker model, validate:

- Registered provider.
- Registered model.
- Availability.
- Verified cost eligibility.
- Required capabilities.
- Context capacity.
- Task risk.
- Project permissions.
- Model benchmark evidence.
- Resource constraints.
- Independent-review requirements.

ZERO_COST_ONLY is a hard filter.

Do not score a paid model highly and then allow the model to override the spending rule.

## 9.4 Routing Explainability

Show a simple explanation:

"Selected because this model supports coding tools and passed the required evaluation."

Or:

"Cannot use this model because paid API requests are disabled."

Store decisions and evidence in SQLite.

## 9.5 Failure Recovery

If the worker fails:

1. Record the error.
2. Determine whether it is a model, tool or task failure.
3. Retry within bounds if safe.
4. Ask the Lead AI to propose a repair or reassignment when necessary.
5. Validate the new proposed model.
6. Require approval where needed.
7. Resume from a durable checkpoint.

Do not create infinite planning loops or repeated expensive model calls.

---

# 10. STRUCTURED AI AGENT COMMUNICATION

Preserve the existing durable communication infrastructure.

The Lead AI should send structured work instructions to specialized agents.

Example:

Client Requirement
→ Lead AI
→ Business Analyst
→ CTO
→ Project Manager
→ Developers
→ QA
→ Final Review

Use existing persistent message records.

Messages should contain:

- Sender.
- Recipient.
- Project.
- Task.
- Message type.
- Context references.
- Artifact references.
- Correlation ID.
- Execution status.
- Timestamps.

## Agent Meetings

The Lead AI may request a bounded meeting.

Example:

CTO + Cloud Architect + Security Architect + Finance.

Meeting participants provide actual expert contributions when eligible models are available.

The Lead AI summarizes decisions.

Save:
- Meeting agenda.
- Agent contributions.
- Alternatives.
- Agreements.
- Disagreements.
- Decisions.
- Follow-up tasks.

When real inference is unavailable, use clearly labeled fixtures in tests only.

Do not display test conversations as live production meetings.

---

# 11. NEW PROJECT WORKSPACE DESIGN

After creating a project, the user should see one understandable workspace.

Avoid forcing users to jump across unrelated screens.

## Header

Show:

- Project name.
- Project status.
- Lead AI model.
- Current stage.
- Next required action.

## Main Progress View

Show five primary stages:

1. Requirements
2. Planning
3. Development
4. Testing
5. Delivery

These must map to real persisted workflows.

## Requirements

Display:
- Original requirements.
- Uploaded documents.
- Clarifications.
- Current approved version.

## Planning

Display:
- Architecture.
- Alternative solutions.
- Lead AI recommendations.
- Proposed workforce.
- Model assignments.
- Milestones.
- Approval controls.

## Development

Display:
- Assigned agents.
- Current coding tasks.
- Source repository.
- Branches.
- Commits.
- Diffs.
- Build and test results.

## Testing

Display:
- QA status.
- Test results.
- Bugs.
- Repair attempts.
- Independent code review.
- Remaining blockers.

## Delivery

Display:
- Final review.
- Delivery package.
- Owner release approval.
- Client access.
- Client acceptance.
- Change requests.
- Project closure.

Keep advanced technical information inside expandable details.

Do not remove any implemented Phase 4 or Phase 5 features.

---

# 12. HUMAN-READABLE AI ACTIVITY TIMELINE

Build a simple activity feed.

The user should understand what Aiventra is doing without reading execution logs.

For example:

"Lead AI is analyzing your requirements."

"CTO reviewed three architecture options."

"Project Manager created eight development tasks."

"Backend Developer started implementation."

"QA detected a failing test."

"Developer submitted a repair."

"Code review requires your approval."

"Project is ready for final review."

These statements must correspond to real recorded events.

Do not display them as fabricated animations or time-based simulations.

## Expandable Details

Allow users to inspect:

- Agent ID.
- Model ID.
- Model selection explanation.
- Tool invocations.
- Task details.
- Test logs.
- Git changes.
- Artifact references.
- Error traces.

Keep the default timeline readable.

Support filtering by:
- All activity.
- AI decisions.
- Development.
- Testing.
- Approvals.
- Errors.

---

# 13. KEEP SQLITE AS THE ACTIVE DATABASE

This is a firm decision.

Keep SQLite active for local development.

Do not migrate to PostgreSQL in this milestone.

Preserve:
- Existing SQLite records.
- WAL configuration.
- Schema migrations.
- Transaction safety.
- Recovery tests.
- PostgreSQL compatibility.
- pgvector migration infrastructure.

Store the new project experience's authoritative records:

- Requirement drafts.
- Uploaded document metadata.
- Lead AI preference.
- Allowed worker models.
- Effective model assignments.
- Planning jobs.
- Plan versions.
- Agent allocation.
- Task dependencies.
- Conversations.
- Activity events.
- Routing decisions.
- Approvals.
- Artifact references.

Use existing tables when possible.

Avoid duplicating project state.

Store large document contents and artifacts through existing protected artifact storage where appropriate.

Test:
- Restart recovery.
- SQLite write contention.
- Draft autosave.
- Concurrent task updates.
- Version consistency.
- Migration rollback.

Existing data must remain intact.

---

# 14. PRESERVE PHASE 4 AUTONOMOUS ENGINEERING

Do not break completed engineering infrastructure.

Continue using:

- Isolated coding runner.
- Repository worktrees.
- Task-specific branches.
- Patch validation.
- Unit tests.
- Build checks.
- Independent review.
- QA.
- Repair loops.
- Git commits.
- PR drafts.
- Authenticated PR publication connector.
- Owner approvals.

The new simplified UI should surface these workflows naturally.

For example:

User:
"Improve the backend performance."

Lead AI:
- Analyzes scope.
- Creates an approved plan.
- Assigns Backend Developer.
- Selects eligible coding model.
- Requests restricted coding execution.
- Reviews test results.
- Assigns QA.
- Presents code diff for owner review.

Never directly execute untrusted model-generated code on the application host.

Do not expose unrestricted Docker control.

Do not automatically publish or merge GitHub changes.

---

# 15. PRESERVE PHASE 5 CLIENT DELIVERY

The newly implemented Phase 5 functionality must remain intact.

Preserve:

- Five-role final review.
- Immutable packages.
- Manifest hashing.
- Exact owner release approval.
- Release withdrawal.
- Invitation-only clients.
- Protected downloads.
- Client acceptance.
- Rejection.
- Change requests.
- Defect reporting.
- Support requests.
- Approved follow-up tasks.
- Closure and reopen approvals.

Connect these to the new project workspace's Delivery stage.

Do not create duplicate package or approval systems.

Use existing persisted records.

Do not claim fixture-tested delivery is an actual client release.

---

# 16. CRYPTO PROJECT SUPPORT — KEEP PROJECTS SEPARATE

My long-term plan is:

Aiventra OS will remain its own GitHub repository.

My cryptocurrency application will remain a separate project/repository.

After finishing Aiventra, I will connect the cryptocurrency repository as a managed project.

Design the new project wizard so that this future integration is natural.

Example:

Project name: Crypto Analytics Platform.

Repository: Existing authorized cryptocurrency repository.

Lead AI: GPT-6.1 Sol preference.

Worker mode: Automatic.

Requirement:
"Analyze the current codebase, identify technical improvements, estimate potential benefits and prepare an engineering plan."

Aiventra should:
- Inspect authorized repository metadata.
- Understand the architecture.
- Retrieve relevant project history.
- Recommend changes.
- Create task branches after approval.
- Coordinate eligible worker models.
- Track tests and review.
- Save work in its project memory.
- Prepare PRs.
- Show development progress.

Do not copy Aiventra source into the crypto repository.

Do not move cryptocurrency code into Aiventra's core.

Use project-level repository references and isolated workspaces.

Never perform live cryptocurrency transfers, trades or wallet operations without explicit authorization.

---

# 17. FUTURE MULTI-PROJECT SCALABILITY

Although the immediate goal is the simple UI, preserve scalability.

Support:

- Multiple clients.
- Multiple projects.
- Different Lead AI preferences per project.
- Different worker pools.
- Different repository connections.
- Different project budgets.
- Different memory scopes.
- Different approval histories.

A single project must not accidentally retrieve another client's private knowledge.

Avoid global mutable model state that silently changes the active model for all projects.

Use organization and project scopes.

Store preferences as persistent records.

---

# 18. MODEL AVAILABILITY AND BILLING SAFETY

Keep:

`AI_SPENDING_MODE=ZERO_COST_ONLY`

My currently configured providers may include:
- OpenAI.
- Grok/xAI.
- DeepSeek.

Local Ollama support is planned or partially implemented.

Do not assume any particular model has free API access.

Do not install Ollama or download models without explicit authorization.

Do not make paid API requests.

Do not perform chargeable model benchmarks.

Do not automatically buy credits.

Do not downgrade billing protections.

## Preferred Lead AI

Save GPT-6.1 Sol as a preference.

Verify the exact model identifier through available official discovery or supported documentation before using it.

If unavailable:
- Show its saved preference.
- Show execution restriction.
- Save the project.
- Provide an explicit selection path for another eligible Lead AI.
- Preserve queued work.

Do not silently claim GPT-6.1 Sol generated an architecture plan.

## No Model Available

Allow:
- Requirement creation.
- File upload.
- Project draft.
- Manual planning.
- Viewing previous records.
- Owner approvals that do not require new AI inference.
- Existing deterministic tests.

Block:
- New AI-generated consulting.
- New AI-generated coding.
- New AI-generated reviews.
- Any model-dependent task lacking an eligible model.

Use clear waiting states.

---

# 19. SECURITY AND APPROVAL AUTHORITY

The Lead AI must not become a security superuser.

Retain:

- Owner authentication.
- Invite-only client access.
- Project-scoped permissions.
- Encrypted provider vault.
- Budget enforcement.
- Tool authorization.
- Model eligibility guards.
- Independent watchdog.
- Audit logging.
- Worker cancellation.
- Release approvals.
- PR approvals.
- Client acceptance.

The Lead AI cannot:
- Disable ZERO_COST_ONLY.
- Reveal API keys.
- Grant itself tool permissions.
- Approve its own production deployment.
- Publish unapproved code.
- Override final-review failures.
- Access unrelated clients.
- Perform unauthorized financial operations.

Treat uploaded requirements and repository contents as untrusted input.

Prevent prompt injection from changing execution permissions.

---

# 20. PREMIUM DARK UI DESIGN REQUIREMENTS

The interface must feel like a modern high-quality software product.

## Design Direction

- Minimal.
- Dark-first.
- Spacious.
- Professional.
- Clear.
- Calm.
- Modern.
- Accessible.
- Responsive.

Use consistent typography, spacing, component sizing and color semantics.

Prefer a restrained visual palette.

Do not overcrowd the screen.

Avoid excessive gradient backgrounds, oversized cards and decorative dashboards.

## Component System

Create reusable components for:

- Sidebar.
- Project header.
- Conversation input.
- File upload.
- Model picker.
- Model availability indicator.
- Role assignment picker.
- Project stepper.
- Approval dialog.
- Activity timeline.
- Worker status.
- Error state.
- Artifact preview.
- Task detail drawer.
- Code diff viewer.
- Delivery panel.

Reuse the existing frontend stack.

Avoid unnecessary new UI dependencies.

## Responsiveness

Test desktop, tablet and mobile widths.

Sidebar must collapse properly.

Project wizard must work on narrow screens.

Model names and eligibility messages must remain readable.

Avoid horizontal overflow.

## Accessibility

Implement:
- Keyboard navigation.
- Visible focus indicators.
- Correct input labels.
- Accessible dialogs.
- Screen-reader status announcements.
- Sufficient contrast.
- Reduced-motion support.
- Accessible loading and error states.

## Browser Verification

Use actual browser tests.

Inspect relevant screenshots.

Fix:
- Misaligned elements.
- Overlapping panels.
- Hidden buttons.
- Confusing labels.
- Broken responsive layouts.
- Excessive scrolling.
- Dead navigation.

Do not declare the redesign complete merely because the build passes.

---

# 21. BACKEND API AND INTEGRATION CONTRACTS

Reuse existing APIs wherever possible.

Only add new API contracts when required.

Suggested logical operations:

- Get project-creation options.
- Save requirement draft.
- Attach requirement files.
- Retrieve eligible Lead AI models.
- Retrieve eligible worker models.
- Save project model preferences.
- Create planning request.
- Read planning status.
- Read planning artifacts.
- Propose workforce allocation.
- Validate model assignments.
- Approve a plan.
- Start approved execution.
- Read project timeline.
- Pause/resume/cancel execution.

Do not blindly create these as duplicate endpoints if existing APIs already support them.

Use typed request/response schemas.

Validate authorization on every operation.

Use version identifiers, idempotency keys and concurrency controls for important mutations.

A frontend-selected model ID is not proof of permission to execute it.

The backend must independently validate every invocation.

---

# 22. COMPLETE TESTING SPECIFICATION

Keep all existing tests passing.

Add new test coverage in these categories.

## A. Project Wizard Tests

1. New project page opens.
2. Requirement text saves.
3. Upload metadata saves.
4. Reopening restores the draft.
5. Existing repository can be selected when authorized.
6. Unsupported files show clear errors.
7. Wizard step validation works.
8. Refresh does not lose progress.

## B. Lead AI Tests

1. Lead AI preference persists.
2. GPT-6.1 Sol can be saved as a preferred unavailable model.
3. Unknown model execution is rejected.
4. Paid model invocation is blocked.
5. Eligible alternate model requires explicit selection when replacing an unavailable preferred Lead AI.
6. Lead AI plan output is schema validated.
7. Malformed planning output is rejected.
8. Plan versions are immutable after approval.

## C. Worker Selection Tests

1. Automatic worker selection proposes appropriate roles.
2. Capability filters are enforced.
3. Model cost restrictions are enforced.
4. Manual overrides are validated.
5. Missing eligible worker leaves the task waiting.
6. Reviewer independence is enforced.
7. Invalid task dependencies are rejected.
8. Circular task graphs are rejected.

## D. Orchestration Tests

1. Lead AI planning requests persist.
2. Agent handoffs persist.
3. Workflows resume after restart.
4. Cancellation prevents unauthorized continuation.
5. Revoked approvals stop related execution.
6. Retries are bounded.
7. Duplicate dispatch is prevented.
8. Tool authorization is enforced.
9. Stale plans cannot execute.
10. Task reassignment preserves audit history.

## E. UI Tests

1. Sidebar is understandable.
2. Home page shows primary project action.
3. Wizard works on desktop.
4. Wizard works on tablet.
5. Wizard works on mobile.
6. Model status is clear.
7. Project stages correspond to backend state.
8. Activity feed uses actual persisted events.
9. Approval controls work.
10. Existing Delivery interface remains functional.
11. Navigation remains accessible.
12. No critical route is broken.

## F. Security Tests

1. AI cannot override spending restrictions.
2. Client cannot select unauthorized models.
3. Client cannot access another client's project.
4. Uploaded instructions cannot grant tool permissions.
5. Agent cannot approve its own privileged actions.
6. Unapproved PR publication is blocked.
7. Secrets are never included in model-selection responses.

## G. Regression Tests

Preserve:
- Existing Phase 3 semantic memory.
- Workforce allocation.
- SQLite restart recovery.
- Phase 4 runner isolation.
- GitHub PR preparation.
- Owner approval.
- Phase 5 final review.
- Immutable delivery packages.
- Client acceptance.
- Project closure.
- ZERO_COST_ONLY enforcement.

## H. Live vs Fixture Verification

Clearly distinguish:

- Deterministic fixture tests.
- Backend integration tests.
- Actual SQLite recovery tests.
- Live local-model execution.
- Live external model execution.
- Actual GitHub PR publication.
- Actual client acceptance.

Do not report fixture outputs as live AI execution.

---

# 23. IMPLEMENTATION MILESTONES

Implement in the following order.

## Milestone 1 — Source Audit and UX Design

- Inspect project creation.
- Inspect existing navigation.
- Identify reusable components.
- Map old screens to new screens.
- Define the minimal navigation.
- Create an implementation plan.
- Run baseline tests.

Then immediately begin code changes.

## Milestone 2 — Simplified Home and Navigation

- New sidebar.
- Clean home screen.
- Conversational primary action.
- Recent projects.
- Pending approvals.
- Collapsible Advanced menu.

Connect to real backend state.

## Milestone 3 — Requirements Upload Wizard

- Project description.
- File upload.
- Existing repository selection.
- Requirement drafts.
- Validation.
- Autosave.
- Restart recovery.

## Milestone 4 — Model Selection During Upload

- Lead AI selector.
- Worker selection mode.
- Automatic/manual/hybrid configuration.
- Model availability.
- Cost eligibility.
- Saved preferences.
- Backend validation.

This milestone is a priority.

## Milestone 5 — Lead AI Planning Integration

- Planning schema.
- Requirement context retrieval.
- Role recommendation.
- Task planning.
- Worker model proposal.
- Router validation.
- Persistence.
- Versioned approval.

Use existing orchestration.

## Milestone 6 — Simplified Project Execution Dashboard

- Five-stage progress view.
- Human-readable statuses.
- Current tasks.
- Agent activity.
- Model assignments.
- Approvals.
- Errors and blockers.
- Technical details drawer.

## Milestone 7 — Phase 4 and Phase 5 UI Connections

- Coding evidence.
- Git diffs.
- QA.
- PR review.
- Final review.
- Delivery packages.
- Owner release.
- Client acceptance.

Preserve security and approval gates.

## Milestone 8 — Responsive and Accessibility Quality

- Desktop.
- Tablet.
- Mobile.
- Keyboard.
- Screen-reader behavior.
- Visual consistency.
- Usability refinement.

## Milestone 9 — Complete Verification

- Backend tests.
- Browser tests.
- Strict TypeScript.
- Lint.
- Formatting.
- Production build.
- SQLite migrations.
- Restart recovery.
- Security tests.
- Secret scanning.
- GitHub Actions.

Fix failures.

## Milestone 10 — GitHub Publication

- Inspect final diff.
- Verify tests.
- Update documentation.
- Commit verified changes.
- Push to existing repository.
- Verify CI.

Do not force push.

---

# 24. DOCUMENTATION REQUIREMENTS

Update:

- README.md
- ARCHITECTURE.md
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- TEST_REPORT.md
- MODEL_ROUTING.md
- AGENT_ORCHESTRATION.md
- PROJECT_WORKFLOW.md
- WORKFORCE_PLANNING.md
- SECURITY.md

Add if necessary:

- SIMPLE_UI_DESIGN.md
- LEAD_AI_ORCHESTRATION.md
- PROJECT_WIZARD.md
- MODEL_SELECTION_POLICY.md

Document:
- New user flow.
- Lead AI responsibilities.
- Worker selection.
- Zero-cost behavior.
- Model unavailability.
- Approval rules.
- Migration changes.
- API changes.
- Testing evidence.

Avoid outdated documentation that refers to removed navigation structures.

Do not exaggerate completeness.

---

# 25. FINAL ACCEPTANCE SCENARIO

Use this scenario to validate the redesigned platform.

I open Aiventra at:

http://localhost:3000

I see a clean, modern, dark interface.

The home page asks:

**What would you like Aiventra to build?**

I click New Project.

I enter:

"Analyze my cryptocurrency application. Identify architectural weaknesses, suggest technical improvements, propose a development roadmap, and implement changes after my approval."

I upload requirements or link the authorized repository.

I click Next.

I see:

**Lead AI**

Preferred: GPT-6.1 Sol.

I see its actual availability and cost eligibility.

I choose:

**Worker Models: Automatic**

I click Next.

Aiventra shows my project configuration.

If the preferred Lead AI is unavailable under ZERO_COST_ONLY, the project is saved and a clear waiting message appears.

If I explicitly choose a suitable eligible Lead AI, it generates a structured project plan.

The plan proposes:
- Architecture alternatives.
- Required engineering roles.
- Task breakdown.
- Model allocations.
- Dependencies.
- Risks.
- Acceptance criteria.

The backend validates the plan.

I approve it.

The existing workforce and orchestration systems assign tasks.

I open the project workspace.

I see five clear stages:

Requirements → Planning → Development → Testing → Delivery.

As tasks run, the activity timeline updates using actual recorded events.

I can see which agent is responsible for each task.

I can view which model was selected and why.

I can inspect code changes, tests, reviews and generated documents.

I can pause or cancel execution.

I approve required GitHub operations.

I inspect verified delivery packages.

I approve release when appropriate.

The client can accept or request revisions using existing Phase 5 controls.

All records remain persistent in SQLite.

PostgreSQL compatibility remains intact.

No paid model is invoked without an explicit future change to the spending policy.

The entire default experience is simple enough for a nontechnical user.

---

# 26. REQUIRED FINAL CODEX REPORT

At the end, provide:

## Source Control
- Starting Git commit.
- Final Git commit.
- Branch.
- Push status.
- CI status.

## UI Changes
- Navigation changes.
- Wizard features.
- Model selection.
- Project workspace.
- Activity timeline.
- Responsive improvements.

## Backend Changes
- Lead AI planning.
- Model routing.
- Worker assignment.
- API integration.
- SQLite persistence.
- Approval integration.

## Tests
- Backend count.
- Browser count.
- Build status.
- Security checks.
- Database tests.
- Recovery tests.
- CI status.

## AI Verification
- Fixture-tested features.
- Live-tested features.
- Blocked providers.
- Available models.
- Unavailable features.
- Spending policy status.

## Remaining Work
- Unverified local inference.
- Unverified external inference.
- Unverified live coding.
- Unverified PR publication.
- Unverified production client delivery.
- Any other actual limitations.

Only list an item as incomplete if it genuinely remains incomplete after implementation.

---

# FINAL NON-NEGOTIABLE INSTRUCTIONS

Do not build a separate application.

Do not rewrite Aiventra from scratch.

Do not delete completed agent systems.

Do not delete Phase 4 functionality.

Do not delete Phase 5 delivery systems.

Do not migrate active SQLite records to PostgreSQL.

Do not expose API credentials.

Do not install Ollama without authorization.

Do not download models without authorization.

Do not make paid cloud inference requests.

Do not bypass approval controls.

Do not publish a generated GitHub PR without approval.

Do not fake AI activity.

Do not fabricate progress metrics.

Do not stop after making mockups.

Do not mark tests successful without running them.

**IMPLEMENT THE UI REDESIGN IN ACTUAL SOURCE CODE.**

**CONNECT MODEL SELECTION DIRECTLY TO PROJECT REQUIREMENT UPLOAD.**

**IMPLEMENT ONE LEAD AI THAT PLANS AND PROPOSES SPECIALIZED WORKER ASSIGNMENTS.**

**USE THE EXISTING MODEL GATEWAY, MEMORY, WORKFORCE PLANNER AND DURABLE ORCHESTRATION SYSTEM.**

**KEEP ZERO_COST_ONLY AND ALL SECURITY/APPROVAL CONTROLS ACTIVE.**

**MAINTAIN A SIMPLE FRONTEND AND A POWERFUL BACKEND.**

Implement complete functional increments, run relevant tests, fix regressions, update documentation, commit verified changes, push to the existing GitHub repository and verify CI.

**START WITH THE CURRENT SOURCE AUDIT, SIMPLIFIED NAVIGATION AND THREE-STEP REQUIREMENT/MODEL-SELECTION WIZARD.**
