# Architecture

Aiventra OS is the control plane; `src/crypto_ai` is the sole scientific engine.
The imported application is not a new model pipeline or trading application.

```text
Owner browser → Next.js /api proxy → Aiventra FastAPI + existing SQLite
                                      ↓ private loopback bearer
                                  Crypto2Adapter (Crypto Python environment)
                                      ↓ exact approved typed request
                                  detached supervisor → canonical command
                                      ↓ signed durable receipt
                                  Aiventra approval/audit/job metadata
```

## Isolation and ownership

`aiventra/` preserves the commit-pinned upstream application, its PostgreSQL migration
and Docker options, agent workforce, model/provider configuration, budgets, approvals,
audit chain, execution sandbox and business features. Active local storage is SQLite.
The two Python environments and frontend lockfiles remain separate. No upstream
Aiventra database, credentials, model downloads or generated data were imported.

`integration/crypto_aiventra/adapter.py` imports canonical configuration, fold planning,
specification enumeration and source identity. It does not reimplement feature/target
generation, purging, calibration, early stopping, metrics or economics. Ordinary reads
inspect bounded metadata, not Gold/Silver tables or serialized models. Reported metrics
are explicitly unverified until canonical artifact checks establish completion.

Aiventra's existing `BusinessRecord` stores tenant-scoped `crypto_project` and
`crypto_job` records. An external managed project is deliberately not a generated-code
`Project` requiring a fabricated proposal. The My Projects page links to the protected
engine. Generic business-record PATCH cannot mutate these integration records.
Existing `Approval` and append-only `AuditEvent` are reused; no second application
database, alternate approval engine or public shell API is introduced.

## Request and worker lifecycle

1. Registering the existing engine records metadata only; viewing it does not register it.
2. A strict typed preview creates `PENDING_APPROVAL`, with exact command, Git/source
   identity, configuration, canonical first fold/spec, resource floors, cost declaration,
   deadline, exact input/output path mapping, reviewed-gate digest and scope checksum.
   It executes nothing.
3. The current enabled owner of the configured engine organization explicitly approves
   that exact version/hash. A fresh preview must still match. Blockers cannot be waived.
4. Aiventra commits its approved `QUEUED` intent before private dispatch. An uncertain
   dispatch is inspected, not automatically retried or approved twice.
5. The adapter publishes an immutable HMAC-bound request and starts an independent
   supervisor. Journals under `local_artifacts/aiventra-control/jobs/<uuid>` persist PID,
   process creation times, heartbeat, command, log/artifact paths, exit and receipt.
6. The supervisor checks current owner authority, source/branch, runtime/deadline and
   control requests while executing a fixed canonical command. It survives closing a
   browser/page/terminal. It does not bypass unavailable backend authority.
7. Exit zero alone is insufficient. Completion requires operation-specific evidence,
   signed receipts and, for future training, independently supplied expected model
   identities plus canonical model/report/receipt/checkpoint validation.
8. Stops require separate exact owner approval. Only identity-matching owned processes
   are signaled. Interrupted, corrupt and partial evidence is preserved; resumption is
   a fresh approved job linked to a reconciled terminal parent, never automatic replay.

The configured `CRYPTO_PROJECT_ORG_ID` binds one tenant to this engine. Other tenant
owners receive 404; non-owners cannot use the control endpoints. Agent role/tool access
does not confer Crypto start/stop authority. Private worker routes require the private
adapter token, not a browser JWT. The token never appears in frontend responses.

## Existing workforce role mapping

No duplicate workforce or agent authority is created. Existing Aiventra roles map as follows:

| Existing role family | Crypto responsibility | Authority limit |
| --- | --- | --- |
| Human owner | Exact approvals, spending/deadline contracts, phase decisions | No holdout action exists here; August remains locked |
| CEO/orchestrator | Interpret evidence, decompose approved work, monitor and delegate proposals | Cannot approve or launch its own science |
| Developer/ML engineering | Maintain adapters and separately approved engine enhancements | Frozen science cannot be changed by this integration |
| QA | Tests, approved cache/artifact integrity checks, regression evidence | Missing evidence is not PASS; heavy checks need owner approval |
| Security | Secret/dependency/permission review and unsafe-command checks | Cannot weaken typed operations or owner scopes |
| DevOps/SRE | Environment health, process identity, persistence and recovery evidence | No cloud provisioning/deployment or automatic replay |

Agent principals do not receive direct owner-only Crypto API permissions. An authorized
owner may supply scoped evidence to the existing workforce; this does not seed mock
agent executions, grant trading access or bypass an approval.

## Deliberate limits

No live trading, execution account access, cloud provisioning, Phase 8, next-fold autoqueue,
holdout endpoints, arbitrary commands, deletion, synthesized data or scientific rewriting.
Windows heavy jobs remain blocked. `CRYPTO_MODEL_VALIDATE` is visible but blocked until
an independently reviewed canonical recovery invocation is supplied; it does not infer
an expected identity from an orphan. Cost ceilings are recorded declarations, not a
cloud billing meter or enforcement guarantee. Real Linux and data verification is a
separate owner-authorized gate, not established by laptop unit/browser tests.
