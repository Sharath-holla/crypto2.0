# Enterprise source audit and prioritized backlog

Starting branch `master`, clean tree, local/remote `3a70a283ab0d3e8e3877aac1fe5094ffd64c91d3`; application source previously `c6dd90e`. Remote: https://github.com/Sharath-holla/Aiventra.git. Baseline rerun: 162 backend tests passed. New specification is preserved in ENTERPRISE_PRODUCTION_SPEC.md; historical phase numbering remains intact.

Source, migration history, workflows, adapters, UI integrations and existing tests were inspected. Classification below applies to the stated scope; VERIFIED_FUNCTIONAL does not mean production certified or live-model verified. Prior Docker/PostgreSQL evidence is identified separately from this workstation.

| Component | Classification | Actual evidence / remaining boundary |
| --- | --- | --- |
| Frontend | VERIFIED_FUNCTIONAL | Connected Next.js owner workspace and browser journeys; full accessibility audit pending |
| Backend | VERIFIED_FUNCTIONAL | FastAPI domain modules, regression suite; external operations incomplete |
| API routes | VERIFIED_FUNCTIONAL | Scoped authenticated operations and request validation |
| Authentication | PARTIAL | Revocable local sessions tested; browser OIDC/invitation lifecycle incomplete |
| Database | PARTIAL | Active SQLite records preserved; Compose PostgreSQL verified in prior CI; local PostgreSQL requires authentication |
| Migrations | VERIFIED_FUNCTIONAL | Additive upgrade tests; new verification table preserves existing rows |
| Agent registry | VERIFIED_FUNCTIONAL | Persistent roles, permissions and policy scopes |
| Agent runtime | VERIFIED_FUNCTIONAL | Durable transitions/usage; live cognition unavailable |
| Model gateway | VERIFIED_FUNCTIONAL | Mandatory guard, bounded routing, usage reconciliation; remote calls intentionally denied |
| Provider vault | VERIFIED_FUNCTIONAL | AES-GCM tenant/provider-bound write-only credentials; managed vault/rotation incomplete |
| Benchmarking | PARTIAL | Versioned deterministic rubrics and controlled protocol tests; no live capability certification |
| Routing | VERIFIED_FUNCTIONAL | Scope intersection, capability/quality/context/budget gates plus zero-cost denial |
| Messaging | VERIFIED_FUNCTIONAL | Durable scoped jobs, idempotency, authorization and cancellation |
| AI meetings | PARTIAL | Bounded structured rounds tested with fixtures; no live provider verification |
| Workforce allocation | VERIFIED_FUNCTIONAL | Versioned plan approval, dependencies, concurrency and persistent scheduling |
| Task orchestration | VERIFIED_FUNCTIONAL | Leases/checkpoints/pause/recovery; free waits now require explicit resume |
| Semantic memory | VERIFIED_FUNCTIONAL | Versioned scoped memory, local embeddings/pgvector and restart tests in prior CI; cached model unavailable locally |
| Coding runner | FUNCTIONAL_NOT_FULLY_TESTED | Real dedicated Docker isolation previously passed CI; hostile-code containment certification pending |
| Git workflows | VERIFIED_FUNCTIONAL | Approved isolated branches, retained changes/diffs and runner recovery |
| Pull-request drafts | PARTIAL | Prepared local drafts; remote branch/PR publication connector missing |
| QA | PARTIAL | Independent review gates and real sample tests/builds; live independent model review unavailable |
| Repair workflows | VERIFIED_FUNCTIONAL | Bounded repair/checkpoints tested; deterministic adapter evidence only for model generation |
| Client lifecycle | PARTIAL | Client requirements/proposal approval/projects; invitations, delivery acceptance and support lifecycle incomplete |
| Finance | PARTIAL | Atomic reservations, caps and append-only settlements; external invoice reconciliation unavailable |
| Monitoring | PARTIAL | Heartbeats, audit, persisted notifications; independent operational watchdog not implemented |
| Docker | FUNCTIONAL_NOT_FULLY_TESTED | Actual Compose/runner CI evidence exists; Docker command unavailable on workstation |
| Kubernetes | PARTIAL | Manifests exist; no cluster deployment/rollout verification |
| CI/CD | PARTIAL | Five existing verification jobs; real zero-cost restart comparison added; no cloud deployment |
| Backup/recovery | PARTIAL | Private SQLite backup and integrity/row-count verification; encrypted automated PostgreSQL offsite restore drill pending |
| UI/UX | PARTIAL | Premium chat and connected controls; zero-cost panel and mobile checks added; delivery/PR screens incomplete |

Highest-risk gap was the absence of a fail-closed spending guard: configured credentials and fresh prices could previously permit paid inference. Enterprise milestone 1 implements the guard and durable waiting vertical slice before expanding provider connectivity.

Next priorities: (1) authorized local PostgreSQL database/pgvector inventory and a reversible data migration plan; (2) local inference service discovery, hardware sizing and approved model provisioning without automatic downloads; (3) prove live local routing/review end to end; (4) exact-approved remote branch/PR publication; (5) client delivery/acceptance. Remote zero-billing eligibility requires a reliable provider-enforced verifier; keep all remote inference blocked until then.

Read-only local hardware inventory: Ryzen 5 5600H, six cores / twelve logical processors, 7.3 GiB reported system RAM; RX 6500M reports approximately 4 GiB adapter memory. This is inventory, not proof of Ollama/GPU compatibility. Docker/Ollama commands and their standard installation binaries were absent. No model or runtime was downloaded. PostgreSQL authentication is still required before inspecting extension/database state.
