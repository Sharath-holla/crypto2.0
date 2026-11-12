# DevOps deployment contracts

## Implemented scope

Increment 6 uses the existing tenant-scoped BusinessRecord, Artifact, Approval,
AgentWork, Workflow and WorkflowStep tables. No schema migration or active
database cutover is needed. SQLite remains active with WAL, busy timeouts and the
organization write lock; the same JSON/model structures support PostgreSQL.

The only adapter is **SIMULATED_NONPRODUCTION**. It performs no network request,
shell command, file upload, host execution, credential acquisition, resource
provisioning or AI inference. A production-environment simulation tests a distinct
approval contract; it does not deploy to production. ZERO_COST_ONLY is unchanged.

## Exact authority and immutable evidence

Owner-only project routes prepare configured simulation targets and canonical
deployment manifests. Manifest hashes bind the project/client/version, current
frozen package and file hashes, available candidate commits, quality readiness,
security review, target/version/configuration digest, environment, fixed operation,
reference-only configuration, migration assessment, bounded health specification,
risk, known rollback reference and reserved exact approval identity/category.

Separate categories are devops_staging, devops_production and their _rollback
variants. Approval records bind owner, version, manifest hash, selection and expiry.
Execution rechecks active project authority, company/deployment pause, target,
source/package/QA, enabled owner and exact approval on every checkpoint. An AI,
project, PR or package approval cannot substitute. Manual-review migrations block
execution; destructive reversal is not implemented.

The existing DevOps Engineer participates using read_context/write_artifact scope.
It receives no credential, budget, infrastructure or unrestricted Docker authority.
Generic BusinessRecord writes cannot modify protected devops records. Generic
workflow pause/resume/cancel delegates to the same deployment authority controls.

## Durable execution and recovery

One approved plan consumes one dispatch identity. Duplicate request UUIDs return
the same work; conflicting or concurrent new dispatches are refused under the
organization lock. The worker commits its job identity before dispatch. Adapter
acknowledgement is persisted separately before the worker checkpoint.

Recovery reads that exact saved job. It never blindly dispatches another operation.
Missing acknowledgement is an uncertain outcome requiring reconciliation. Owner
cancellation fences the worker lease before cancelling a known job. Unknown
cancellation stays pending and may be retried against the same identity. It never
claims the target was stopped without a saved result. Revocation/cancellation is
available while the company is paused. A terminal adapter result is preserved;
cancellation cannot rewrite a completed activation as if it never happened.

States cover deployment_started, artifact_staged, revision_activated,
health_check_running, deployment_completed, deployment_failed and
deployment_cancelled. Workflow needs_attention plus its saved error represents
uncertain/reconciliation-required outcomes. Fixed simulation scenarios exercise
health failure, timeout, partial staging and wrong revision. Simulated health
observations must match the intended revision and artifact before success.

State vocabulary reuses the existing architecture: a prepared draft is saved as
awaiting_approval, then approved and queued; deployment_started is dispatch,
artifact_staged/revision_activated are running, and health_check_running is
verification. Terminal deployment_completed/deployment_failed retain operation
deploy or rollback. An open incident plus an awaiting-approved rollback plan is
rollback pending; its job/receipt records running/success/failure. cancel_requested
with workflow needs_attention is cancellation pending; outcome_uncertain plus the
saved error means human reconciliation is required. No second parallel status
engine or callback endpoint can rewrite these states.

Canonical receipt artifacts bind approval/manifest/work/job/package/target,
adapter digest, events, timestamps, revision and health. Validation checks workflow
checkpoint and adapter provenance, not just the receipt's own hash. Receipts remain
historical evidence after an approval expires; they do not grant fresh authority.

## Incidents and bounded rollback

Failed deployments save an incident, owner notification and DevOps escalation
message. A rollback requires a known healthy receipt for the same project, client,
target and prior package; its exact approval is separate. Fresh health verification
must succeed to resolve the original incident. Failed recovery stays on the same
incident so creating new plans cannot reset the counter. Three attempts exhaust
the budget and escalate to the owner. No automatic public or production rollback
exists.

## UI and release boundary

The existing Delivery stage shows actual saved targets, plans, hashes, approvals,
workflow checkpoints, blockers, health receipts and incident/recovery history. The
owner can prepare, approve, run, pause, reconcile, cancel or revoke simulations and
prepare separately approved rollback. Detailed manifests and receipts are available
without adding top-level navigation. There are no invented percentages or states.

For Phase 7 projects, or projects opting into a deployment plan, client release is
blocked until a future authorized live adapter supplies actual exact production
deployment and health evidence. Current simulation receipts cannot satisfy this
gate. Legacy delivery contracts without a DevOps plan remain compatible. Existing
fixture package, owner release and client acceptance gates remain independent.

## Verification and deferred integration

tests/test_deployments.py exercises real persisted orchestration using explicitly
simulated deployments. The process probe abruptly exits after adapter persistence
and recovers the same job in fresh worker processes. The ordinary browser package
journey uses real HTTP/UI controls on disposable SQLite and PostgreSQL CI storage.
CI compares deployment evidence across actual API/worker/web restart and includes
all table digests in database restart/separate restoration checks. The harmless
Task API journey continues from actual restricted Docker engineering/QA into an
explicit staging simulation; this is not real deployment verification.

A live adapter, scoped target credentials, approved infrastructure/cost policy,
actual deployment/health observation and separately approved operation are future
work. No real target, live DevOps model or public/production deployment is claimed.
TEST_REPORT.md records observed results and failures, rather than inferring them
from the existence of these tests.
