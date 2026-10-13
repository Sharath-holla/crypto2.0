# Phases 2–5 source audit

Starting branch: master, clean `ae10711`; tested application source `4de41f5`. October 8, 2026. Audit inspected runtime, provider/gateway contracts, state models/migrations, agent registry/permissions, memory, consulting, Git/runner boundaries, frontend/proxy, Compose and CI. Baseline rerun: **81 backend tests passed in 63.74 seconds**, **seven browser tests passed in 2.1 minutes**, TypeScript/format passed.

Classification refers to the source before this increment. Live model verification needs real credentials; Docker/Ollama are absent locally despite the attachment's environment assertion. Ephemeral Compose/PostgreSQL CI is verified; the separate code runner has no actual test evidence yet.

| Requirement | Classification | Source evidence / gap |
|---|---|---|
| 2.1–2.2 registry, roles, on-demand dispatch, permissions/context/artifacts | Partially implemented | 136 real configurable roles, bounded document/consulting/coding jobs and model ledger; general runtime state/performance not yet persisted |
| 2.3 validated agent execution states | Missing | Workflow/task states exist; employee enablement is not execution state |
| 2.4 providers | Partially implemented; live blocked by external credentials | OpenAI/Anthropic/Gemini/Ollama/compatible structured HTTP adapters tested with controlled transports. xAI explicit kind, discovery, stream/tool contracts/cancellation incomplete |
| 2.5 provider UI/credentials/connectivity/discovery | Partially implemented | Registry, enable/disable, environment references and usage work; encrypted browser credential input, connectivity/model catalog tests/defaults absent |
| 2.6 routing | Partially implemented | Capability/quality/context/sensitivity/freshness filters, economy/balanced/quality/fastest, exact hard caps and actual selection reason. Overrides/project restrictions/measured evaluation scoring missing |
| 2.7 escalation | Partially implemented | Bounded distinct-model fallback, schema failures and uncertain-call reconciliation work; richer context improvement and tool failure classification incomplete |
| 2.8 durable message processing | Partially implemented | Stored correlated scoped messages and owner acknowledgment exist; recipient workflow/actual model reply/dedup/dead-letter handling missing |
| 2.9 meetings | Partially implemented | Seven-step requirement consultation persists specialist opinions; general agendas, bounded rounds/follow-up dispatch missing |
| 2.10 live acceptance | Blocked by external credentials | Fixture/control-adapter contracts can be exercised; no live account access inferred |
| 3.1–3.2 memory layers | Partially implemented | Structured authoritative project/org/workflow/message/conversation/artifact state persists; working summaries/semantic lifecycle incomplete |
| 3.3 semantic storage/embeddings | Missing | Compose uses pgvector image but no embedding/index pipeline; keyword retrieval only |
| 3.4 scoped bounded retrieval | Partially implemented | Project/client-scoped keyword records/artifacts; semantic retrieval/versioned provenance absent |
| 3.5 memory lifecycle | Partially implemented | Requirement/proposal/record versions retained; explicit memory revision/supersession/invalidation/retention/deletion absent |
| 3.6 restart recovery | Implemented and verified for existing workflows/conversations | Fenced checkpoint/uncertain-call recovery and actual PostgreSQL conversation/document restart comparison; new memory/allocation restart proof pending |
| 3.7–3.10 dynamic workforce/scheduling/UI | Missing | Four fixed planning tasks and manual specialist assignment work; no versioned scope-based team proposal/approval/concurrency allocation |
| 3.11 acceptance | Partially implemented | Existing isolation/persistence tests pass; semantic/team/scheduling evidence required |
| 4.1–4.2 restricted runner | Implemented but unverified in actual containers | Network-disabled read-only nonroot CPU/RAM/PID/timeout/output limits in source; mocked QA in coding tests; cancellation/orphan recovery incomplete |
| 4.3 Git import/workspaces/patches | Partially implemented | Real read-only discovery, isolated worktree and validated file batches/diffs; commits/PRs/merge queue missing |
| 4.4–4.7 coding/review/QA/repair | Partially implemented | Actual source changes and diverse reviewer policies; no live coding, actual container tests or automatic repair/security/PM gates. Fixture reviews correctly refuse certification |
| 4.8 concurrent development/merge | Partially implemented | Task-specific worktrees isolate changes; ownership/interface/merge queue/integration tests incomplete |
| 4.9 baseline protection | Implemented and verified with runner contracts | Failed/empty baseline blocks generation, interrupted execution stops replay; actual baseline/container evidence pending |
| 4.10–4.11 GitHub/DevOps | Partially implemented | Authorized publication and passing app CI/Compose; product PR/merge/staging/rollback connectors missing |
| 4.12 real acceptance | Blocked by external credentials for live author/review; runner verification missing | Deterministic real container lifecycle tests are permitted evidence, not live autonomous coding |
| 5.1–5.7 intake/analysis/consultation/proposal/approval/projects | Partially implemented | Real persisted intake/text evidence/seven specialist calls/version/hash owner approval/projects; live pricing quality and dynamic workforce incomplete |
| 5.8–5.10 designs/implementation/final tests | Partially implemented | Document tasks/artifacts and coding interface exist; comprehensive designs, build/security/integration acceptance missing |
| 5.11–5.14 final review/delivery/client acceptance | Missing | No verified release package, client review portal/acceptance/support or genuine software delivery acceptance |
| Premium UI | Partially implemented | Tested dark/light responsive saved CEO chat plus connected operational screens; runtime/team/memory/delivery controls absent |
| Security/FinOps/observability | Partially implemented | Sessions/RBAC/audit/caps/fenced leases/watchdog/correlation; credential vault, invitations, distributed load/restore and production monitoring pending |

Implement A before B/C/D/E. Add essential UI/tests with each backend milestone. Update current status and evidence as code is verified; do not reinterpret this historical gap table as final completion.

## Milestone A follow-up

Vault/catalog/inference-probe controls, scoped model policies/evaluations, persisted invocation states and durable owner-directed messages/meetings are now implemented. Final verification is recorded in TEST_REPORT.md. This does not change the historical audit above into a completion claim: native streaming/tools and broader Phase 2 recovery/benchmarks remain partial; semantic memory, dynamic allocation, complete coding and delivery are still missing.
