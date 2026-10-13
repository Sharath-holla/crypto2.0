# Aiventra OS

Phase 7 continues the existing app with collaborative requirements sign-off and versioned CTO architecture alternatives, exact owner selection, saved design evidence and selected-design planning/coding context. See [REQUIREMENTS_REFINEMENT.md](REQUIREMENTS_REFINEMENT.md), [ARCHITECTURE_DESIGN.md](ARCHITECTURE_DESIGN.md) and [TEST_REPORT.md](TEST_REPORT.md) for implemented behavior and actual evidence. Three-stage QA and restricted DevOps integration remain unfinished; no live AI or production readiness is claimed.

Phase 7 begins with [collaborative requirements refinement](REQUIREMENTS_REFINEMENT.md): Lead/BA critique contracts, explicit recommendation decisions, clarification answers, retained scope versions and exact owner sign-off before architecture for new UI projects. Models may be connected later; owner-authored scope is explicitly labeled. Read the [source gap audit and dependency order](PRODUCTION_SDLC_WORKFLOW.md) and [complete Phase 7 brief](docs/PHASE7_PRODUCTION_SDLC_SPEC.md). Three-stage QA and DevOps deployment acceptance remain subsequent work; no production readiness or live AI completion is implied.

Phase 6 adds backend-derived AI readiness and protected per-invocation evidence to Home, Settings and project workflows. SQLite remains active and ZERO_COST_ONLY mandatory. No genuine model inference is currently verified. See [local hardware/model assessment](LOCAL_MODEL_READINESS.md), [bounded live verification plan](LIVE_AI_VERIFICATION_PLAN.md), [implementation status](IMPLEMENTATION_STATUS.md) and [test evidence](TEST_REPORT.md). Deterministic workflows and actual restricted-runner tests are reported separately; generated PR publication and delivery retain exact approval gates.

A working Next.js + FastAPI application for supervising a configurable AI workforce. Its implemented core takes a client requirement through persisted analysis, specialist consultation, deterministic cost comparison, a versioned proposal, explicit owner approval, assigned project planning tasks and saved artifacts.

**This is a tested local foundation, not a finished production enterprise platform.** Read [implementation status](IMPLEMENTATION_STATUS.md) and [test evidence](TEST_REPORT.md) before enabling live integrations. The full build target is preserved in [the master brief](docs/MASTER_BUILD_PROMPT.md).

Latest continuation: [Simple UI + Lead AI orchestration](docs/SIMPLE_UI_LEAD_AI_SPEC.md). Home leads into a [three-step persistent wizard](PROJECT_WIZARD.md), explicit [Lead/worker choices](LEAD_AI_ORCHESTRATION.md) and existing approval-controlled engineering/delivery services. Advanced retains all tools. SQLite and ZERO_COST_ONLY stay active; blocked models wait without paid fallback. Earlier briefs and the [production roadmap](docs/PRODUCTION_UPGRADE_SPEC.md) remain preserved. Read current status/test evidence for fixture versus live boundaries. Repository: [Sharath-holla/Aiventra](https://github.com/Sharath-holla/Aiventra).

## Start on Windows 11

Install Node.js 22 or newer, Git and [uv](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is recommended. From this repository:

```powershell
./scripts/bootstrap.ps1
./scripts/start.ps1
```

Open **http://localhost:3000**. Sign in using `OWNER_EMAIL` and `OWNER_PASSWORD` in your private `.env`. Bootstrap generates random secrets and preserves existing configuration. Never share or commit that file.

To load the clearly labeled consulting example:

```powershell
.venv/Scripts/python.exe -m company_os.cli demo
```

The example uses local fixtures and creates a proposal **awaiting approval**. It does not make paid requests, invent cloud prices, modify repositories or deploy anything.

Stop and restart without deleting data:

```powershell
./scripts/stop.ps1
./scripts/start.ps1
```

The scripts write process IDs and logs under `data/`. Do not run start twice. If a port remains occupied, identify its process before stopping it.

## Manual development

```powershell
uv sync --extra dev --locked
.venv/Scripts/python.exe scripts/configure.py
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m company_os.cli seed
.venv/Scripts/python.exe -m uvicorn company_os.api:app --host 127.0.0.1 --port 8000
# Separate terminal at repository root:
.venv/Scripts/python.exe -m company_os.workflows
# Separate terminal:
cd apps/web
npm ci
npm run dev
```

Linux/macOS: use `.venv/bin/python` and run the API, worker and frontend in separate terminals. `python scripts/configure.py` creates the same local configuration.

API documentation: http://localhost:8000/docs. Public health: http://localhost:8000/health. All business operations require authentication. The web proxy keeps the session token in an HttpOnly cookie.
Liveness is `/health/live`; readiness is `/health/ready` and requires the expected migration plus a fresh worker heartbeat. Existing pre-0.2 tokens need a new sign-in. Public signup is intentionally unavailable; the owner is provisioned during setup.

## Executive chat

The default workspace saves real conversations and connects questions to the separate worker. **Live AI** is the default and waits for an eligible configured provider. Choose **Local fixture** explicitly for an offline example; fixture output never claims live inference. Inspect actual workflow/model/cost evidence below each turn.

Attach small UTF-8 `.txt`, `.md`, `.csv` or `.json` files (16 KB each, four per turn). Preview their saved content/hash, search recent conversations and reopen their URLs after reload/restart. SSE streams saved workflow state and provisional native output for models explicitly configured with streaming. Rich PDF/image ingestion remains pending. Stop cancels publication of the response; in-flight paid usage may still be charged.

Choose **Start consultation** to invoke the existing specialist flow. Its review button opens the exact requirement; versioned approval opens the exact persistent project with dependent planning tasks. The separate **Company commands** view retains the earlier bounded operations interface. Theme/sidebar preferences persist locally.

## Provider and agent operations

In Models & providers, store a write-only encrypted key or use a dedicated environment reference, test the real account catalog and configure documented model capabilities/prices. A catalog identifier is not inference proof. Registered models can run an explicit owner-capped inference test; unavailable models wait durably. Bootstrap creates the independent private PROVIDER_SECRET_KEY needed for vault storage.

Employee/provider/project preferences and allowed-model lists preserve mandatory routing/security/budget filters. Inspect saved runs and optionally record an owner quality evaluation with evidence. Workforce cards show persisted invocation state/history, not activity inferred from enabled roles.

Meetings & messages can queue a scoped artifact task or a bounded 2–8 participant meeting for an approved active project. First-round contributions are independent; optional document follow-ups share the original cap. Fixture output is labeled. Cancellation blocks late publication while in-flight usage can remain charged.

## What works

- 16 departments and 136 initial employees; optional crypto specialists; instance cloning, tool permissions and routing controls.
- Local password authentication, server-side role and tenant checks, configured OIDC bearer verification.
- Persistent expiring local sessions, server logout revocation, atomic database login limits, worker heartbeat and correlated structured logs.
- Persisted requirements, clarification, uploads of UTF-8 text documents, source retrieval, bounded specialist contributions, CFO interpretation and proposal alternatives.
- Deterministic source-backed **partial estimates**; absent rates remain unknown.
- Exact proposal hash/version approval, project creation, dependent planning tasks and saved artifacts.
- Owner-assigned specialist document work and permission-scoped versioned semantic memory with PostgreSQL/pgvector, CPU-local embeddings and an explicit keyword fallback. See [SEMANTIC_MEMORY.md](SEMANTIC_MEMORY.md).
- Durable separate worker, atomic job claims, checkpoints, failure bounds, owner notifications and uncertain-paid-call reconciliation.
- Configurable adapters for OpenAI Responses, Anthropic Messages, Gemini, xAI, Ollama and compatible chat-completion endpoints. No live model IDs or prices are invented or preloaded.
- Capability, quality, sensitivity, context, freshness and availability routing filters; bounded fallback; atomic company/project/task/conversation/turn/agent/model/day/month spending reservations.
- Read-only local repository discovery, approved isolated Git worktrees, structured file patches, independent reviewer boundary and restricted container QA implementation.
- Failed/empty baseline blocking, one/two review passes, owner-approved model/provider diversity policy and persisted achieved-diversity evidence.
- Company/project/agent/provider controls, independent watchdog, durable dispatched messages/bounded meetings, ordered agent state history and audit chain with database mutation guards.
- Persistent CRM, client, support, knowledge, incident and email/calendar/campaign **draft** records.
- Responsive dashboard, directory/hierarchy, executive commands, consultation/approval, project board/timeline, engineering evidence, finance, providers, records and audit interfaces.

## Explicit limits

Live provider calls require API credentials and valid configured models/prices; the owner has deferred provider connection. Local semantic embeddings and provider-free development do not require paid credentials. Docker is unavailable on the local build host; CI separately checks actual Compose/PostgreSQL services, vector retrieval and restarts. Generated-code runner evidence is recorded separately in TEST_REPORT.md. Cloud deployment requires a supported connector and environment-specific approval. No mail/calendar OAuth, external sending, GitHub PR creation, comprehensive model quality certification or Temporal production orchestration is claimed.

The local workflow engine is a tested transactional database state machine. SQLite is for a trusted owner's local development. Hostile multi-tenant production execution requires hardened dedicated runners and PostgreSQL verification. The existing crypto repository has not been supplied; its integration remains pending.

## Verify

```powershell
.venv/Scripts/ruff.exe check apps/api tests scripts infrastructure/database/migrations
.venv/Scripts/ruff.exe format --check apps/api tests scripts infrastructure/database/migrations scripts infrastructure/database/migrations
.venv/Scripts/ruff.exe format --check apps/api tests scripts infrastructure/database/migrations
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m pip_audit
cd apps/web
npm run typecheck
npm run format:check
npm run build
npm audit --omit=dev
# API, worker and frontend must be running:
npx playwright install chromium
npm run test:e2e
```

Backend tests use isolated databases under `data/pytest-temp`. Browser tests create **fixture-labeled** local consulting records and projects. They establish fixture-backed UI/backend integration and saved-state recovery; live inference and the separate dedicated coding runner remain unverified.
Before committing/publishing, stage the intended files and run `.venv/Scripts/python.exe scripts/secret_scan.py --history`. It scans staged blobs and publishable branch/remote history without printing values. Keep ignored private configuration/data outside Git.

## Docker Compose

Install [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/) with its supported virtualization backend. Generate `.env` first; `DB_PASSWORD` is required. Then:

```powershell
docker compose up --build -d
docker compose logs -f api worker
docker compose stop
docker compose start
```

Compose uses PostgreSQL with a pgvector-capable image, an initialization job, API, worker and web. Only web/API loopback ports are published; the database stays on the internal network. Code execution is disabled in this stack: the API has no Docker socket, and a dedicated runner must be configured separately. The pgvector extension is not used for retrieval yet. Startup, readiness, monetary/concurrency/audit contracts, schema drift and browser integration passed in GitHub CI on `ca51145`; Docker remains unavailable on this Windows host. See TEST_REPORT.md for current commit-specific evidence.

## Repository map

```text
apps/api/company_os/   domain models, policy, routing, finance, workflows, engineering, API routers
apps/web/             Next.js frontend, typed schemas, authenticated backend proxy, browser tests
infrastructure/       Alembic migrations, Dockerfiles, Compose support
tests/                workflow, routing, financial, security, repository and recovery tests
scripts/              safe configuration and Windows lifecycle commands
docs/                 architecture, operations, provider setup, user guide and full requirements
```

See [architecture](docs/architecture.md), [database design](docs/database.md), [provider setup](docs/providers.md), [security](docs/security.md), [operating guide](docs/user-guide.md), [crypto import](docs/repositories.md), [deployment/recovery](docs/operations.md), [testing](docs/testing.md) and [API reference](docs/api.md).

Native streaming, closed server tools/peer documents and the Benchmarks tab: see [NATIVE_EXECUTION.md](NATIVE_EXECUTION.md). Latest request: docs/LIVE_EXECUTION_SPEC.md. Phases 3–5 remain incomplete.
