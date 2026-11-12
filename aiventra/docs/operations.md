# Deployment, Windows operations, recovery and troubleshooting

## Development installation

Windows 11: install Git, Node.js 22+, uv/Python 3.12. Run `scripts/bootstrap.ps1` then `scripts/start.ps1` from PowerShell. If execution policy blocks the script, follow your organization's policy; individual manual commands in README also work. Paths containing spaces/apostrophes are supported by the scripts' literal working directories.

API, web and worker logs are under `data/`. Database is `data/company.db`; artifacts are private under `artifacts/`. Configuration is private `.env`. Bootstrap never overwrites existing secrets or deletes project data.

## Compose deployment

Docker Desktop installation and WSL2/virtualization prerequisites follow [Docker's official Windows instructions](https://docs.docker.com/desktop/setup/install/windows-install/). Generate `.env` and a strong DB_PASSWORD, then `docker compose up --build -d`. Initialization applies migrations and seeds departments/owner. Database health gates startup. API/web publish only loopback ports. Dedicated code execution is disabled.

Stop with `docker compose stop`; resume with `docker compose start`. Do not remove volumes when retaining company data. Review image versions/digests and build scans before deployment. Compose and PostgreSQL have not been run on this build host.

## Production prerequisites

Production is not certified. Configure HTTPS with COOKIE_SECURE=true, OIDC, least-privilege database roles, encrypted private storage, a managed secret store, private dedicated runner hosts, egress restrictions, log retention and immutable audit anchoring. Verify PostgreSQL concurrency, authentication, restore, load, all live adapters and sandbox behavior. Temporal orchestration and staging deployment/rollback are outstanding milestones. Kubernetes deployment manifests are not included because production behavior is not yet validated.

## Backup / restore

For local SQLite, pause the company, stop the worker/API, then copy the database, artifact directory and encrypted `.env` to restricted backup storage. Use SQLite's backup API for online backups rather than copying a live WAL database. Example after stopping processes:

```powershell
New-Item -ItemType Directory -Path backups -Force
Copy-Item -LiteralPath data/company.db -Destination backups/company.db
Copy-Item -LiteralPath artifacts -Destination backups/artifacts -Recurse
```

For PostgreSQL, use `pg_dump` for the company database and separately snapshot private object storage. Keep secrets backed up separately and encrypted. Restore to a fresh, paused installation; verify migrations, audit chain, scoped records and artifact hashes before resuming. Recover uncertain paid requests from provider billing rather than replaying them. Perform a real restore drill before production use.

## Workflow recovery

Completed model runs and checkpoints persist. Expired leases can be reclaimed. A provider call durably marked started/uncertain is blocked for owner reconciliation, retaining reserved budget. Use `/runs/{id}/reconcile` with verified cost/evidence, then `/workflows/{id}/retry` if within attempt limits. A schema/quality failure's usage is recorded before fallback. A process restart does not certify an unknown external outcome.

Interrupted container executions require manual review. The system does not blindly mark them passed or replay them. The coding workflow currently has no automatic execution-reconciliation endpoint; inspect container state and create a revised approved task after preserving evidence.

## Troubleshooting

- Sign-in fails: inspect private `.env` credentials. Seeding does not change an existing owner's password. For an intentional local reset, stop managed processes, run `.venv/Scripts/python.exe scripts/rotate-local-secrets.py`, then restart; both password and signing key change without printing them. This does not provide production OIDC provisioning.
- API unavailable: check `data/api-error.log`, JWT_SECRET length and migration state.
- Work does not advance: ensure the worker is running; inspect company/agent/project pauses, tool permissions, approvals, budgets and workflow errors.
- Live model unavailable: check server credential environment, configured ID/capabilities/context, quality threshold, data sensitivity and price freshness.
- Unexpected cost: inspect reservation versus recorded usage and basis. Budget scopes overlap; never sum their counters together as spending.
- Docker failure: execution is disabled by default, requires pre-pulled images and an accessible dedicated Docker runtime. Missing runner never creates a fake success.
- Locked test temp directory: tests use `data/pytest-temp` instead of shared system temp.
- Port occupied: identify the owning process before terminating it; never kill unrelated user processes.
- Unverified source: some pricing pages need JavaScript, reject redirects or do not contain usable rates. Keep costs unknown and supply verified evidence.
