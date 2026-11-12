# AIVENTRA OS — NEXT MILESTONE
## Intelligent Task Allocation, Model Selection, Repository Import and Real Engineering Readiness

Continue development of my EXISTING Aiventra OS repository.

Repository: https://github.com/Sharath-holla/Aiventra.git

Last reported application commit: eeb0e6d
Last reported documentation commit: 93a8111

Inspect the actual HEAD before modifying source.

## PRIMARY GOAL

The three-step project wizard and Lead AI model selection now work.

DO NOT rebuild them.

Your next responsibility is to connect the existing project creation system with intelligent task-specific workforce allocation, enhanced document/repository analysis, and the existing Phase 4 engineering workflows.

I want Aiventra to work as follows:

1. I create a project and upload requirements.
2. I choose my preferred Lead AI.
3. I choose automatic worker model selection.
4. The Lead AI analyzes the requirement.
5. It determines the necessary departments and specialists.
6. It divides the project into meaningful engineering tasks.
7. It recommends the best eligible model for every task.
8. I review and approve the plan.
9. The existing orchestration engine dispatches approved tasks.
10. I monitor progress through the simplified interface.

Preserve SQLite, PostgreSQL compatibility, ZERO_COST_ONLY, existing agent permissions and all Phase 4/5 approval gates.

# 1. SOURCE AUDIT

Read:
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- PROJECT_WIZARD.md
- LEAD_AI_ORCHESTRATION.md
- WORKFORCE_PLANNING.md
- MODEL_ROUTING.md
- TEST_REPORT.md

Inspect the existing planner, model registry, workforce allocator, project wizard and coding runner.

Run baseline tests.

Implement missing functionality rather than duplicating existing services.

# 2. INTELLIGENT TASK DECOMPOSITION

Extend the Lead AI planning contract.

For an approved project, produce structured workstreams and tasks.

Each task should include:
- Unique task ID
- Project and requirement version
- Description
- Required skills
- Difficulty level
- Dependencies
- Required tools
- Acceptance criteria
- Suggested agent role
- Recommended model
- Model-selection rationale
- Risk level
- Estimated resource usage
- QA requirements

Validate all results on the backend.

Reject circular dependencies, unauthorized assignments, invalid model identifiers and scope violations.

Persist the plan in SQLite.

Preserve immutable approved versions.

# 3. AUTOMATIC WORKER ALLOCATION

Use the existing workforce planning system.

The Lead AI should propose the smallest suitable team for each project.

Example for a cryptocurrency analytics application:

- Project Manager
- Business Analyst
- Software Architect
- Backend Developer
- Frontend Developer
- Database Engineer
- QA Engineer
- Security Reviewer
- DevOps Engineer

These are example roles, not mandatory allocations.

Select workers according to actual task requirements.

Do not activate all registered agents.

Support concurrent execution of independent tasks within resource limits.

Persist allocations, schedules and rationale.

Require existing approvals before restricted execution.

# 4. TASK-SPECIFIC AI MODEL ASSIGNMENT

This is the main next-stage feature.

For each task, evaluate:
- Complexity
- Required capabilities
- Model availability
- Verified benchmark performance
- Tool support
- Context capacity
- Reliability
- Independent-review requirements
- Resource constraints
- Zero-cost eligibility

The Lead AI recommends a model.

The backend validates the choice.

Do not allow the Lead AI to override provider eligibility, security or budget enforcement.

Support:
- Automatic model selection
- Manual model selection
- Hybrid model selection
- Per-task model overrides
- Model reassignment on failure
- Saved selection explanations

If my preferred GPT-6.1 Sol Lead AI is not eligible under ZERO_COST_ONLY, preserve the preference without invoking it.

Do not silently replace it.

An alternative Lead AI requires explicit user selection.

If no suitable free model is available, place the task in WAITING_FOR_FREE_PROVIDER.

# 5. REQUIREMENTS AND DOCUMENT IMPORT

Improve the existing project wizard.

Support more practical document formats where secure parsers are available:
- TXT
- Markdown
- CSV
- JSON
- PDF
- DOCX

Preserve source text, metadata, file hashes and extraction warnings.

Do not execute document macros or embedded code.

Implement safe size limits and parsing timeouts.

Use project-scoped artifact storage.

Allow users to remove or replace requirement attachments.

For every extracted document, record provenance and retrieval permissions.

Do not send confidential documents to external AI providers unless the provider is approved for that project's data.

# 6. GITHUB REPOSITORY IMPORT

Extend the existing authorized GitHub integration.

Support:
- Repository selection
- Authorized repository URL
- Default branch discovery
- Source tree inspection
- Technology stack detection
- Dependency file inspection
- README analysis
- Existing test discovery
- Architecture summary
- Branch selection
- Repository-to-project association

Import must initially be read-only.

Do not execute imported repository code outside the restricted runner.

Do not expose GitHub credentials to AI models.

My future cryptocurrency project will have its own independent GitHub repository.

Aiventra must manage that repository as a separate client/project workspace rather than copying the source code into Aiventra itself.

# 7. CONNECT PLANNING TO ENGINEERING

Once a project plan has been approved:

- Create actual tasks.
- Resolve dependencies.
- Assign logical agents.
- Record model assignments.
- Queue eligible work.
- Start authorized tasks through the existing worker.
- Connect coding tasks to the restricted runner.
- Capture actual commits, tests, diffs and review results.
- Route failures into bounded repair workflows.

Do not bypass existing coding and GitHub publication approvals.

Do not label fixture execution as live AI engineering.

# 8. SIMPLIFY THE PROJECT WORKSPACE FURTHER

Preserve the existing five stages:

Requirements → Planning → Development → Testing → Delivery.

Improve the Planning stage to show:

- AI team
- Assigned models
- Reasons for model selection
- Task dependencies
- Estimated resources
- Approval requirements

Create an understandable task view such as:

"Backend API development — assigned to Backend Developer — model awaiting availability."

Allow expanding the task to inspect:
- Technical details
- Model routing decision
- Dependencies
- Logs
- Documents
- Tests
- Errors

Keep complex orchestration details hidden by default.

The interface should remain usable by a nontechnical user.

# 9. PROJECT KNOWLEDGE AND SQLITE

Keep SQLite active.

Persist:
- Imported requirement metadata
- Repository connections
- Project architecture findings
- Task planning versions
- Agent allocation
- Model assignments
- Routing rationale
- Approval records
- Execution history
- Artifact references

Reuse existing semantic memory.

Preserve PostgreSQL and pgvector compatibility.

Test restart recovery and client/project isolation.

Do not migrate the active database.

# 10. ZERO-COST AND AUTHORIZATION

Keep ZERO_COST_ONLY mandatory.

Do not:
- Make paid OpenAI requests.
- Make billable Grok requests.
- Make billable DeepSeek requests.
- Install Ollama without permission.
- Download models without permission.
- Publish real generated PRs without approval.
- Deploy applications without authorization.

Use deterministic test adapters where appropriate and label those results honestly.

Do not claim real AI execution without a configured, eligible model and actual inference evidence.

# 11. TESTING

Extend the existing test suite.

Verify:
- Task-specific model selection
- Invalid model rejection
- Zero-cost restrictions
- Automatic workforce allocation
- Manual override
- Hybrid override
- Task dependency validation
- Plan approval
- Planning persistence
- Upload parsing
- Repository import permissions
- GitHub credential isolation
- Workflow restart recovery
- Task cancellation
- SQLite integrity
- Existing Phase 4 and Phase 5 regressions
- Responsive UI

Run backend tests, browser tests, lint, strict TypeScript, production build, migrations, security audits and secret scans.

Verify Docker runner tests and PostgreSQL compatibility in available CI infrastructure.

Do not suppress failures.

# 12. GITHUB AND DOCUMENTATION

Update:
- IMPLEMENTATION_STATUS.md
- IMPLEMENTATION_LEDGER.md
- NEXT_STEPS.md
- TEST_REPORT.md
- LEAD_AI_ORCHESTRATION.md
- WORKFORCE_ALLOCATION.md
- MODEL_ROUTING.md
- PROJECT_WORKFLOW.md

Implement in verified increments.

Commit and push tested changes to the existing repository.

Do not force push.

Verify GitHub Actions.

# FINAL ACCEPTANCE CRITERIA

I can create a new project through the simplified wizard.

I upload requirements or select an authorized GitHub repository.

I choose a preferred Lead AI.

I select Automatic Worker Models.

A qualified eligible Lead AI produces a structured plan when real inference is available.

The backend validates model assignments.

The workforce planner allocates suitable specialists.

The project workspace shows understandable tasks, assigned agents, models and progress.

I can override individual model assignments.

All important execution remains approval-gated.

All information persists in SQLite.

The project can resume after restart.

Existing Phase 4 coding and Phase 5 delivery capabilities remain functional.

No paid inference occurs under ZERO_COST_ONLY.

Do not claim live AI results when only deterministic fixtures have been used.

START WITH TASK-SPECIFIC WORKFORCE ALLOCATION AND MODEL ROUTING, THEN CONTINUE WITH DOCUMENT AND REPOSITORY IMPORTS.

Implement actual code, run tests, fix errors, update documentation, and push verified increments.
