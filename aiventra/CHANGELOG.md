# Change log

## Monetary persistence hardening — October 8, 2026

- Migrated all 12 PostgreSQL monetary fields to BIGINT; SQLite retains its native 64-bit INTEGER tables and audit triggers. Large-balance/reservation and populated-upgrade regression tests added.
- Bound registered model prices to a supported integer range and extended container CI with actual PostgreSQL schema, concurrent cap/login and append-only audit checks.
- All four remote CI jobs passed on `ca51145`: 66 Linux backend tests, 3 browser tests against Compose/PostgreSQL, schema drift and all extended database contracts. Local backend suite also passed 66 tests; no live AI/coding-runner success is claimed.

## CI portability repairs — October 8, 2026

- Added the repository root to pytest's configured import path so the Linux console entry point can import the publication scanner.
- Bound the standalone web image explicitly to `0.0.0.0`, avoiding Docker's inherited hostname breaking loopback health checks. All four CI jobs subsequently passed on `3ade79d`, including Compose/PostgreSQL and 3 browser tests.

## 0.2.0 — October 8, 2026

- Audited actual source/Git/tests against the new Aiventra specification; added missing architecture/audit entry points and preserved working modules.
- Added persistent expiring/revocable local sessions, atomic database login throttling, worker heartbeats, separate health/readiness and correlated structured logs.
- Added durable missing-provider waiting and same-step reactivation without charging or burning failure attempts.
- Bound one/two-review diversity policies to approved coding scope, excluded duplicate service/model identities and saved achieved-diversity evidence without exposing previous verdicts to reviewers.
- Blocked generation after failed/empty baseline tests and guarded interrupted QA replay. Corrected cross-platform Git hook disabling to the OS null device.
- Connected provider readiness and review controls to the UI; refreshed Aiventra branding and retained existing useful views.
- Added data-preserving migration tests, authentication/concurrency/readiness/wait/diversity tests, expanded Git pipeline checks and conservative staged/history publication scanning.
- Added Compose worker/web health, Git in the API/worker image, and secret/container/browser CI jobs. Actual local Docker/PostgreSQL/cluster verification remains unavailable.
- Added durable phase/status/limitations/security/model/memory/workflow/deployment/crypto documentation. Current phase remains Production Foundation; final client delivery and production certification are incomplete.

## 0.1.0 — October 8, 2026

- Established requirements, architecture, schema, permission/routing design, acceptance plan and durable continuation documents.
- Implemented modular API, local identity, owner/client scope, normalized migrations, 16 departments and 136 roles, configurable employees and explicit fixture providers.
- Implemented provider adapters, policy filtering, bounded fallback, deterministic cost arithmetic, durable usage/reservations and owner reconciliation of uncertain requests.
- Added restartable consultation with five specialist contributions including CFO, exact proposal approval, project planning dependencies and saved artifacts.
- Added actual business records, project keyword memory, scoped specialist document assignment, watchdog incidents, pause controls and append-only audit guards.
- Added protected read-only repository discovery, approved Git worktrees, validated patches, independent review and restricted container QA interface. Actual container execution remains unverified.
- Built responsive Next.js dashboard and connected consulting, workforce, project, engineering, finance, provider, record and governance controls to real endpoints.
- Added locked dependencies, Windows lifecycle scripts, CI definition, Compose files, operating/provider/security guides and automated backend/browser coverage.
- Corrected web origin validation, managed process lifecycle, visible dependency data, specialist field associations and logout handling. Dependency scans reported no known vulnerabilities in scanned dependencies.
- Rotated local authentication secrets after an early browser diagnostic captured a previous password; scrubbed local test diagnostics and changed browser tests to authenticate through request cookies without entering credentials into page snapshots.

Unimplemented production integrations and unverified runtimes are listed in IMPLEMENTATION_STATUS.md. No cloud deployment, external message, trading action or live provider success is claimed.
