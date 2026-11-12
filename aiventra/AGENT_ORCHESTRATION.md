# Agent orchestration

Wizard consulting adds strict LeadAnalysis, mandatory BA/CTO/PM/CFO and bounded optional Cloud/Security/FinOps contributions before exact Lead synthesis. Existing persisted checkpoints/messages, admission, memory and finance remain authoritative; legacy consultation is preserved. Manual plans record owner authorship, not AI activity. Existing BA → CTO → PM staffing planning applies Lead selection at its final stage and still requires exact staffing approval. See LEAD_AI_ORCHESTRATION.md for fixture/live limits.

## Current orchestration status

Persistent scoped messages/meetings, agent delegation, workforce scheduling, leases/checkpoints, bounded tools and pause/recovery are implemented and regression-tested. The current milestone adds WAITING_FOR_FREE_PROVIDER with saved employee/context/revision, notification/audit and explicit guarded owner resume. No simulated response is presented as live inference. Source and evidence are in ARCHITECTURE.md, WORKFORCE_PLANNING.md, ZERO_COST_AI_POLICY.md and TEST_REPORT.md; older missing-feature descriptions below are historical.


Current scope: Milestone A of [Phases 2–5](docs/PHASES_2_5_SPEC.md). Registered roles execute through one on-demand durable worker, not 136 permanent model processes.

`workflows` retain claims, deadlines, attempt bounds and checkpoint results. `agent_work` binds an owner-idempotent request to a probe, message or meeting and a shared budget. `agent_executions` records each workflow/employee invocation; `agent_state_events` records validated transitions with unique per-execution sequence numbers. A completed invocation is not proof that a project is complete or its output is semantically correct.

RUNNING begins only when a model run and reservation have committed. Provider waits have no paid run. Success/failure/uncertainty, ordered state history, actual usage and costs persist. Runtime summaries prioritize current valid live leases and show expired/revoked work as blocked. Registered employees with no current work are idle; disabled employees are labeled disabled.

Messages validate sender/recipient/project/artifact scope and approved project authority. The recipient writes an artifact before an acknowledgement/response is published. Responses remain records until an owner explicitly requests another task; a correlation chain is bounded to two replies. A repeated request ID with a different payload is rejected.

Meetings use 2–8 participants and 1–2 rounds plus CEO synthesis. Round-one evidence is captured once; participants do not see earlier verdicts. Round two may compare round one. Optional bounded document follow-ups share the meeting spend cap and cannot grant code or deployment tools.

Worker restart reclaims expired leases and replays successful checkpoints. Started/uncertain provider calls require owner reconciliation instead of blind repayment. Cancellation changes the lease token; late answers cannot advance checkpoints or publish artifacts. Usage can still be recorded after cancellation. Native function dispatch now uses a closed, schema-validated and lease-fenced registry, with one owner-selected document handoff sharing the job cap. Distributed load certification, richer role templates/dead letters and production recovery drills remain pending.
