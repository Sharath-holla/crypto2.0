# AIVENTRA OS — ENTERPRISE MILESTONE 2
## Production PostgreSQL Integration, Local Ollama, Zero-Cost AI Execution and Phase 4 Continuation

You are continuing my EXISTING Aiventra OS application.

Repository:
https://github.com/Sharath-holla/Aiventra.git

Previously reported:
- Application commit: 0e8797d
- Final HEAD: 9826b0e
- 197 backend tests passed
- 13 browser journeys passed
- Five GitHub Actions jobs passed
- Zero-cost policy implemented
- Existing SQLite persistence still active locally
- PostgreSQL/pgvector verified in CI
- No live AI inference verified
- Local Docker/Ollama availability uncertain or unavailable in the previous Codex environment

Do not assume these reports are current. Inspect the actual workspace.

DO NOT REBUILD THE PROJECT.

DO NOT DELETE EXISTING DATA.

DO NOT REQUEST PAID AI API USAGE.

DO NOT EXPOSE EXISTING API KEYS.

# TASK 1 — Complete Audit

Inspect:
- Git status and HEAD
- Existing configuration
- Database connection and migrations
- SQLite data
- PostgreSQL integration
- Semantic memory
- Agent runtime
- Model gateway
- Zero-cost policy
- Docker
- Coding runner
- GitHub integration
- UI
- Test results

Confirm what is working.

Read IMPLEMENTATION_STATUS.md, NEXT_STEPS.md, TEST_REPORT.md, ARCHITECTURE.md and ZERO_COST_AI_POLICY.md if present.

# TASK 2 — Migrate Local Aiventra to PostgreSQL

My computer has PostgreSQL installed.

Determine whether it is accessible from the current execution environment.

Check:
- PostgreSQL service
- Port and network
- Authentication
- Database permissions
- Database existence
- pgvector extension
- Connection URL
- Existing migrations
- Version compatibility

Do not request or print passwords unnecessarily.

Use environment-based credential references.

If host PostgreSQL is inaccessible, diagnose the precise error.

If Docker PostgreSQL is available, use the existing verified Compose configuration as an alternative only when authorized.

## Safe Migration

My existing application currently uses SQLite.

Create a robust SQLite-to-PostgreSQL migration process.

Required:
1. Detect source database.
2. Create a private backup.
3. Inspect schema and existing migrations.
4. Validate destination readiness.
5. Create or migrate PostgreSQL schema.
6. Transfer data in dependency-safe order.
7. Preserve primary keys and relationships.
8. Preserve timestamps and monetary precision.
9. Preserve encrypted vault records and encryption-key requirements.
10. Preserve conversations, projects, memory, workflows, approvals, artifacts and logs.
11. Reconcile row counts.
12. Validate foreign keys.
13. Verify records and critical hashes.
14. Test application queries.
15. Test rollback from a failed migration.
16. Keep SQLite backup unchanged until restoration has been verified.

Do not overwrite existing PostgreSQL data.

If the destination contains records, detect conflicts and require appropriate authorization rather than silently replacing them.

Make the active database configuration explicit.

Do not leave the application accidentally writing to SQLite after switching to PostgreSQL.

## PostgreSQL Verification

Test:
- Authentication
- Transactions
- Connection pooling
- Migrations
- Concurrent task updates
- Agent messaging
- Budget calculations
- Approval integrity
- Semantic vector search
- Worker recovery
- Database restart
- Backup and restore

Record actual local verification separately from CI evidence.

# TASK 3 — Configure Ollama for Real Free AI

Inspect whether Ollama is installed and reachable.

Do not assume it exists.

Do not automatically download large models.

Detect:
- Available RAM
- CPU
- GPU
- Available disk storage
- Existing Ollama installation
- Installed models
- Local endpoint availability

Recommend small, medium and coding-focused local models based on actual supported hardware.

If the environment supports it and the owner has authorized local provisioning, configure a suitable local model.

Use official Ollama interfaces.

Do not make paid cloud inference requests.

## Real Model Integration

Implement:
- Health check
- Model discovery
- Capability registration
- Streaming
- Structured outputs when supported
- Tool calling when supported
- Task cancellation
- Context limits
- Timeout handling
- Usage metrics
- Model failure recovery

If no model is installed, report exactly which model and installation command is recommended.

Do not falsely report successful inference.

## Local Model Benchmarking

Create objective tests for:
- Basic conversation
- Requirement extraction
- Classification
- Task planning
- Code generation
- Simple code repair
- Tool calling
- Structured responses

Use real outputs and validators.

Record scores, inference times, failures and resource usage.

A model should only receive roles that it can perform at an acceptable quality level.

# TASK 4 — Verify Three Existing Cloud Provider Integrations

My existing provider configuration includes:
- OpenAI
- xAI/Grok
- DeepSeek

Preserve the encrypted provider vault.

Do not print API keys.

Keep ZERO_COST_ONLY enabled.

Verify supported endpoints, model discovery and provider capabilities through non-billable methods where available.

Do not make any external inference call unless zero-cost eligibility and enforceable no-charge limits have been verified.

Do not assume ChatGPT Plus includes regular API usage.

For every model, display:
- Provider
- Model ID
- Available capabilities
- Free eligibility
- Verification evidence
- Routing suitability
- Availability
- Reason for any restriction

If eligibility cannot be established, keep inference blocked.

# TASK 5 — Activate Real Agent Orchestration With Local Models

Connect the local model runtime to the existing agent organization.

Test one genuine workflow:

Client requirement
→ Business Analyst
→ CTO
→ Project Manager
→ Saved artifacts.

Requirements:
- Agents must receive actual task context.
- Each active step must produce real model output.
- Agent messages must be stored.
- Artifacts must be saved.
- Memory must be retrieved appropriately.
- Routing decisions must be recorded.
- Workflow state must survive restarts.
- Agent status must reflect actual execution.

Do not confuse deterministic fixture output with live inference.

If the local model cannot complete a complex task reliably, record the limitation and keep that task waiting.

# TASK 6 — Complete Phase 4 GitHub Pull Request Integration

Preserve existing:
- Restricted runner
- Git worktrees
- Coding tasks
- Candidate diffs
- Tests
- Repair rounds
- Independent review logic
- Draft PR records
- Cancellation and recovery

Implement the missing authenticated GitHub publication workflow.

Support:
- GitHub App or least-privilege credentials
- Repository permission checks
- Target branch validation
- Draft PR preview
- Exact commit and diff confirmation
- Owner approval
- Git push
- Real GitHub draft PR creation
- PR URL and ID persistence
- Idempotent retries
- CI status retrieval
- Review comments
- Repair task creation
- PR updates
- Audit history

Do not automatically merge into master.

Do not force push.

Do not publish PRs without approval.

Use a disposable test repository for verification when authorized.

# TASK 7 — Connect Coding Agents to the Restricted Runner

Create one end-to-end coding workflow.

Example:
"Add validation and tests to a small Python API."

Workflow:
1. Project Manager creates an approved task.
2. Coding Agent receives context.
3. Model generates a proposed patch.
4. Patch is validated.
5. Runner checks out repository.
6. Code is modified in an isolated worktree.
7. Unit tests execute.
8. Failures are recorded.
9. Repair is attempted within limits.
10. Independent reviewer checks the change.
11. QA executes tests.
12. Git commit is created.
13. PR draft is prepared.
14. Owner approves publication.

Use a harmless sample repository.

If no capable local model is installed, verify the deterministic execution infrastructure and mark real autonomous coding as pending.

# TASK 8 — Continue Phase 5 Client Delivery

Extend the existing requirements and approvals workflow.

Connect:
- Requirement intake
- Technical consultation
- Architecture options
- Cost comparison
- Approval
- Dynamic workforce
- Engineering tasks
- Coding execution
- QA
- Final engineering review
- Delivery artifacts
- Client acceptance

All records must persist in PostgreSQL after migration.

Do not fabricate solutions, code execution or delivery results.

# TASK 9 — Improve the UI

The UI is still not sufficiently polished.

Improve the premium dark ChatGPT-style application.

Prioritize:
- Main AI CEO chat
- Real-time streaming
- Clear model/provider states
- Project management workspace
- PostgreSQL and memory status
- Agent communications
- Workforce allocation
- Coding execution
- Git diffs and PR approvals
- QA results
- Zero-cost policy
- Client delivery

Use actual backend data.

Improve visual hierarchy, navigation, typography, spacing, responsiveness, accessibility, loading states and actionable errors.

No fake progress or inactive decorative controls.

# TASK 10 — Production Operations

Verify:
- Docker Compose
- PostgreSQL
- pgvector
- Runner isolation
- CI/CD
- GitHub Actions
- Secrets handling
- Monitoring
- Authentication
- Worker recovery
- Backup/restore
- Database migration rollback

Preserve Kubernetes deployment configuration.

Validate manifests where tools are available.

Do not claim live cluster verification without a real cluster test.

# TASK 11 — Full Verification

Run applicable:
- Backend tests
- Browser tests
- Type checking
- Lint
- Formatting
- Production builds
- Migration tests
- PostgreSQL integration
- Semantic memory
- Zero-cost policy tests
- Runner isolation
- GitHub PR tests
- Security checks
- Secret scan
- Workflow restart tests

Fix regressions.

Do not disable existing tests.

# TASK 12 — Commit and Push

Update:
- IMPLEMENTATION_STATUS.md
- TEST_REPORT.md
- NEXT_STEPS.md
- ARCHITECTURE.md
- DATABASE_MIGRATION.md
- MODEL_CONFIGURATION.md
- ZERO_COST_AI_POLICY.md
- DEPLOYMENT.md

Clearly state what passed locally, in CI, with real local models and with fixtures.

Commit verified changes.

Push to the existing authorized GitHub repository.

Do not force push.

Verify GitHub Actions.

# CRITICAL SUCCESS CRITERIA

Aiventra must be able to start using its configured PostgreSQL database and preserve existing data.

The semantic memory must survive restarts.

The company must be able to execute a real local AI task if a capable local model is available.

All paid cloud inference must remain blocked.

The AI company must be able to coordinate agent handoffs, create tasks, and use the existing restricted coding runner.

GitHub PR publication must require owner approval.

The UI must present actual execution and clear error states.

Do not claim production readiness until security, operational recovery, live execution and end-to-end delivery have been verified.

DO NOT STOP AFTER PLANNING.

IMPLEMENT REAL CODE IN VERIFIED INCREMENTS, TEST IT, DOCUMENT THE RESULTS AND PUSH TESTED PROGRESS TO GITHUB.

START WITH POSTGRESQL CONNECTIVITY AND SAFE SQLITE-TO-POSTGRESQL MIGRATION.