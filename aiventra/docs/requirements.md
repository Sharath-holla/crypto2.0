# Requirements and acceptance plan

The original master brief is preserved in `docs/MASTER_BUILD_PROMPT.md` and remains the full implementation target.

## Mandatory invariants

- All business data is persistent and tenant-scoped. Clients see their own consulting records; owner-only operations are enforced by the API.
- Agent output is validated before it enters authoritative state. Repository and client text are untrusted data.
- Implementation follows approval of an exact proposal version, content hash, selected alternative and expiry.
- Provider failures have bounded fallback. Paid calls reserve budget before network activity; interrupted calls with uncertain billing stop for reconciliation.
- Model names and prices come from explicit configuration. Mock runs, manually entered estimates and real executions have separate labels.
- Independent QA evidence is required for coding completion. Generated code runs only in restricted containers, never in the API process.
- Logs and prompts are redacted, credentials remain server-side. Secret detection is defense in depth, not a substitute for a vault.
- Emergency pause, project pause, tool permissions and spending checks live in backend policy code.

## Milestones

1. Foundation: monorepo, auth, schema migrations, health, Compose, frontend, CI.
2. Workforce: all 16 departments and role templates, configurable instances, scoped tools and activity.
3. Routing: provider adapters, quality/capability/security filters, deterministic finance, reservations and bounded fallback.
4. Consulting: intake, clarification, specialist contributions, source evidence, deterministic comparison, proposals and approval.
5. Projects: milestones, dependency tasks, artifacts, messages and owner controls.
6. Engineering: repository discovery, isolated workspaces, validated patches, review and container QA.
7. Operations: deployment approval boundary, staging integration and rollback evidence.
8. Enterprise: real CRM, support, knowledge, drafts, monitoring and HR records; OAuth external integrations.
9. Crypto: repository discovery without assuming a stack; approved isolated changes and testnet-only defaults.
10. Hardening: recovery, concurrency, policy, budgets, provider failure, UI, load and dependency checks.

## Test plan

Automate scenarios A–J from the brief wherever implemented. Cover tenant isolation, stale approval rejection, duplicate approval idempotency, deterministic financial arithmetic, concurrent spending reservations, workflow recovery, bounded failure, independent QA, traversal/symlink rejection, secret redaction, and emergency stop. Network adapters use contract fixtures; live verification requires credentials. Docker execution and PostgreSQL must be explicitly marked unverified if those runtimes are unavailable. Never substitute mocked evidence for real execution evidence.
