# Architecture and boundaries

## System

```mermaid
flowchart LR
 Owner --> Web[Next.js / TypeScript]
 Client --> Web
 Web --> API[FastAPI authenticated API]
 API --> DB[(PostgreSQL / SQLite local)]
 Worker[Separate durable worker] --> DB
 Worker --> Policy[Policy + budget + approval]
 Policy --> Gateway[Model gateway]
 Gateway --> Providers[Configured provider APIs / explicit mock]
 Worker --> Sandbox[Restricted Docker execution]
 Worker --> Store[Private artifact storage]
 Watchdog[Independent watchdog] --> DB
 API --> Store
```

The backend is a modular monolith. Provider and container work runs in a separate worker. No container socket is exposed to the API or browser. Development uses SQLite WAL; Compose uses PostgreSQL. No overlapping agent frameworks are installed: typed bounded activities and server tools provide the initial runtime.

## Requirement lifecycle

```mermaid
stateDiagram-v2
 [*] --> queued
 queued --> analysis
 analysis --> consulting
 consulting --> proposal
 proposal --> awaiting_approval
 awaiting_approval --> approved: exact hash and version
 awaiting_approval --> queued: revised requirement
 approved --> project
 project --> paused: material revision or emergency stop
```

## Execution / QA

```mermaid
flowchart LR
 Approval --> Plan --> Task --> Worktree
 Worktree --> Patch[Validated files]
 Patch --> Reviewer[Independent reviewer / actual diff]
 Reviewer --> QA[Independent container tests]
 QA --> Evidence[Exit code, logs, commit and timestamps]
 Evidence --> Complete[Task acceptance]
 QA --> Defect[Failed task / owner escalation]
 Complete -. planned .-> ReleaseApproval[Environment approval: pending]
 ReleaseApproval -. planned .-> Staging[Staging/rollback connector: pending]
```

## Routing

```mermaid
flowchart LR
 Task --> Filter[Capabilities, sensitivity, quality, context, availability]
 Filter --> Rank[Policy: cost / quality / latency / reliability]
 Rank --> Reserve[Atomic worst-case budget reservation]
 Reserve --> Request[Provider request]
 Request --> Validate[Pydantic result validation]
 Validate --> Ledger[Usage, computed estimate and reservation settlement]
 Request --> Fallback[Bounded distinct eligible models]
```

## Agent hierarchy and communication

```mermaid
flowchart TD
 Owner --> CEO
 Owner --> Monitoring[Independent monitoring department]
 CEO --> Heads[CTO / CFO / COO / Product / PMO / Security / Sales]
 Heads --> Departments[16 configured departments]
 Departments --> Employees[Configurable AI employee instances]
 Employees --> Bus[Transactional messages with correlation IDs]
 Bus --> Meetings[Bounded specialist recommendations + synthesis]
 Meetings --> Decisions[Validated decision / owner escalation]
```

Messages are durable records with sender, recipient, scope, correlation, status, schema and authorization context. Workflow steps use unique `(workflow, step)` keys. Completed steps are reused after restart. Claims use conditional updates and fenced lease tokens. A live request that may have reached a provider is not blindly repeated after worker death: it enters reconciliation. This is a tested database state machine, not Temporal. Adopting Temporal for distributed production orchestration remains a tracked architectural gap.

## Security / data

```mermaid
flowchart LR
 JWT[Local JWT / configured OIDC] --> Identity[Server identity + membership]
 Identity --> Scope[Organization and client/project scope]
 Scope --> Tools[Tool allowlist]
 Tools --> Approvals[Versioned owner authority]
 Approvals --> Budget[Hard spending limit]
 Budget --> Effects[Restricted effect]
 Effects --> Audit[Append-only hash chain]
```

```mermaid
erDiagram
 Organization ||--o{ User : owns
 Organization ||--o{ Client : owns
 Client ||--o{ Requirement : submits
 Requirement ||--o{ Proposal : versions
 Proposal ||--o{ Approval : authorizes
 Proposal ||--o| Project : creates
 Project ||--o{ Task : schedules
 Task ||--o{ Artifact : produces
 Project ||--o{ ModelRun : charges
 Organization ||--o{ AuditEvent : records
 Workflow ||--o{ WorkflowStep : checkpoints
```

## Deployment

```mermaid
flowchart LR
 Browser --> Web
 Web --> API
 API --> Postgres
 Worker --> Postgres
 Worker --> DockerHost[Private dedicated runner host]
 Postgres --> Backup[Encrypted backups]
 API --> ObjectStore[Private S3-compatible storage]
```

Production requires HTTPS, an OIDC identity provider, managed secrets, protected artifact storage, isolated dedicated runner hosts, backups and recovery exercises. Single-host development is not a hostile multi-tenant sandbox.


## Durable CEO workspace

```mermaid
flowchart LR
 Chat[Owner chat / private text uploads] --> API[Authenticated conversation API]
 API --> History[(Conversations, ordered turns, private artifacts)]
 API --> Dispatch[Unique durable turn workflow]
 Dispatch --> Worker[Lease-fenced worker]
 Worker --> Advisory[Read-only CEO gateway / scoped memory]
 Worker --> Consult[Existing specialist consultation]
 Consult --> Proposal[Versioned proposal]
 Proposal --> Approval[Exact owner approval]
 Approval --> Project[Persistent project / dependent planning tasks]
 History --> SSE[Revocation-aware saved snapshots]
 SSE --> Chat
```

Conversation/request uniqueness and optimistic versions prevent duplicate dispatch. Conversation and per-turn caps participate in the same atomic reservation transaction as company/project/agent/model/period caps. Cancelled lease tokens cannot publish delayed answers; uncertain provider usage still requires reconciliation. Consultation dispatch and its coordinator acknowledgement are committed together; no advisory text authorizes implementation.

Current SSE carries persisted workflow state, not provider tokens. The browser supports reconnect plus polling recovery. Each iteration opens a short database session and checks identity/session/expiry. Uploaded UTF-8 documents are owner-scoped private artifacts; raw HTML and remote images are suppressed in response rendering. Additive migration `771bb4c719ce` adds conversation tables/links without rebuilding populated SQLite parent tables.
