# Aiventra × Crypto integration discovery — 2026-10-13

## Verified source and branch boundary

- Actual host: Windows, `C:\Users\HP\Documents\ChatGPT\crypto2.0`, not the historical Lightning path.
- SOURCE_BRANCH: `phase7a-pre-lightning-hardening-20261003`.
- SOURCE_HEAD / INTEGRATION_START_HEAD: `24dd8148af8cc1db4827dd40d2754d5ec1846ee6`.
- INTEGRATION_BRANCH: `integration/aiventra-crypto-os`, newly created from that HEAD.
- Crypto origin: `https://github.com/Sharath-holla/crypto2.0.git`, unchanged.
- External source: `https://github.com/Sharath-holla/Aiventra.git`, default branch `master`,
  commit `1d8b479d48a4f208529d71f0cd355853a9288776` (October 13).
- A shallow, no-checkout clone and inspection-only tracked archive live outside Crypto in a
  unique OS temporary directory. No upstream branch, commit, push, or remote changes.
- Initial upstream scanner: 386 tracked blobs, zero findings. No tracked .git entries,
  symlinks, submodules, private configuration or license/notice file found. No public license
  is asserted; this integration is made under the owner's explicit request, with source
  attribution preserved. Do not infer redistribution rights beyond that authorization.

## Crypto scientific engine

Python/uv; immutable Bronze/Silver/Gold; PyArrow, NumPy, LightGBM, Pydantic, joblib.
Canonical Phase 7A config is `configs/phase7/research_core20_primary_v1.toml`, identity
`93f987736b1a79d26b773957`; run `phase7a-core20-primary-93f987736b1a79d26b773957`.
16 folds, 48 primary A6 specs, 109 model features/130 Gold fields. Regression, not
classification. Existing canonical config/spec/fold/cache/checkpoint/report/lease APIs remain
authoritative; no numerical implementation belongs in the control plane.
Project remains on hold: no acquisition, preparation, fit, GPU, holdout access, cloud work or
phase advancement is authorized by application startup. August stays LOCKED_UNUSED;
July stays unused. Existing runtime paths can be overridden without editing scientific TOML.

## Aiventra architecture

- Frontend: Next.js 16.4.0, React 19.3.0, strict TypeScript, existing design tokens,
  Lucide icons, authenticated `/api` proxy with HttpOnly session cookie. No second UI framework.
- Backend: Python >=3.12, FastAPI, modular routers/domain services, SQLAlchemy 2,
  Pydantic settings, Uvicorn. Existing owner/tenant authorization and append-only audit.
- Storage: owner-selected SQLite with WAL/bounded locking. PostgreSQL/pgvector models,
  Alembic migrations and optional Compose compatibility preserved; no database cutover.
- Auth: local password/session authentication, owner checks, tenant scoping, optional OIDC.
  Generate private local configuration using the existing setup, never print/commit secrets.
- Agents: persisted role/task/workflow/model/approval/evidence records; mandatory ZERO_COST_ONLY.
  No provider keys, model downloads or live inference needed or authorized for this integration.
- Runtime: separate durable workflow worker, heartbeat/lease/recovery, restricted generated-code
  runner. Crypto's trusted fixed command worker must remain distinct from generated-code tools;
  no arbitrary shell, agents' host execution, general filesystem or cloud authority.
- Existing metadata stores: Project, BusinessRecord, Approval, Workflow/WorkflowStep, Artifact,
  AuditEvent. Extend these for integration metadata; do not put scientific rows in SQLite.
- Docker: optional PostgreSQL/runner compatibility, not the selected Windows development stack.
  Existing deployment adapter is explicitly simulated, not a live deployment connector.

## Dependencies, ports, tests and build

Keep Crypto `.venv`/`uv.lock` untouched. Imported Aiventra gets its own `.venv`, `uv.lock`,
frontend `node_modules` and `package-lock.json`. Python dependency overlap does not justify
combining environments. The exact pinned Next/React/Prettier versions were verified on npm.
Development bindings must be loopback and configurable; proposed dedicated ports 8010 API,
3010 web, 8011 Crypto adapter avoid assuming upstream 8000/3000 are free. Never kill an
unrelated port owner. No public exposure or auth weakening.

Actual upstream commands: `uv sync --extra dev --locked`; Ruff check/format over apps/api,
tests, scripts and migrations; `python -m pytest -q`; Alembic check; pip-audit;
frontend `npm ci`, `npm run typecheck`, `npm run format:check`, `npm run build`,
`npm audit --omit=dev`, Playwright default/phase5/PostgreSQL configurations. Existing CI also
has real Docker and PostgreSQL recovery jobs; those upstream results are historical, not
verification of this integration. Current reported upstream baseline is 590 backend tests.
Fresh Crypto baseline was launched before source import; result pending observation.
New adapter tests use only temporary synthetic metadata, never real Gold/Silver or training.
Browser tests must use their existing isolated fixture services, not the owner's database.

## Import and adapter design

Import all 386 tracked source files under `aiventra/` using the commit-pinned Git archive.
Do not copy `.git`, generated state, environment secrets, node_modules, virtual environments,
owner databases, or generated datasets. No Aiventra Git remote is needed.

Add `integration/crypto_aiventra/` for configuration, read-only adapter, typed job definitions,
independent worker supervision and protected metadata boundaries. Aiventra's owner-only router
talks to the adapter; its UI never imports Crypto Python internals. Reuse the existing SQLite
organization/project/approval/audit stores rather than introducing another application database.
Read-only pages distinguish actual validated completion, present-but-unverified metadata,
missing evidence and dated historical state. No fabricated metrics or progress percentages.

Execution requests must preview exact command, scientific identity, fold/spec, resources,
deadline/cost contract and approval hash. Only fixed typed commands may execute, under both
owner approval and the canonical engine's guards/lease. Holdout/next-fold/delete/general-shell
operations are not available. Missing safe canonical entrypoints remain BLOCKED rather than
being approximated by an expensive different job. Starting the application starts no science.

## Expected changes and risks

Imported source under aiventra; focused Aiventra router/domain/UI additions; integration adapter,
configuration/worker/launcher/tests; integration docs and optional dedicated CI. Preserve existing
`src/crypto_ai`, scientific configs/artifacts, legacy files and source branch bytes/ref.

Key risks: local Windows is not Lightning; current real restored data/lineage is not available
at the brief's historical paths. Do not display VALIDATED/PASS from quoted counts alone.
Cross-process PID reuse and crashes require identity-safe recovery, not automatic replay.
Owner approvals must bind exact current source and immutable scope; disabled owners, tenant
mismatch, expiration, changed resources/source or holdout requests fail closed. Imported
upstream Git-root assumptions and separate runtime dependencies require regression testing.
No destructive migration, science change, cloud provisioning or expensive job is needed now.

Discovery precedes source import and implementation. Continue on the isolated integration branch.

## Post-implementation verification note

The original discovery observations above are retained as written before import.
Final gates passed: Crypto 790 passed / 5 Linux-only skips; Aiventra backend 610 passed;
ordinary browser 32 passed; delivery browser 9 passed; Crypto browser 3 passed.
See `TESTING.md` for initial setup/Windows fixture failures and successful final rechecks.
Authenticated real-mode startup passed with zero jobs and missing local scientific
evidence honestly unavailable. Crypto origin's scientific branch remains at the older
`0597a4d71b5ee1883502ea892f0c78e3961d2169`; this work preserves the local scientific
source at `24dd8148af8cc1db4827dd40d2754d5ec1846ee6` without pushing that scientific ref.
