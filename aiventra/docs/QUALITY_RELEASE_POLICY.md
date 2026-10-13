# Three-stage QA and release policy

Phase 7 Increment 5 extends the existing engineering, durable worker, approval, artifact, package and release services. SQLite remains active; no schema migration or data transfer is required. PostgreSQL-compatible models/migrations remain intact.

## Actual workflow

1. Complete an exactly approved coding task in the restricted runner. Inspect its current candidate through `GET /tasks/{id}/quality-source`.
2. Author a bounded independent Python test overlay and cases, mapping every approved requirement to rounds 1 and 2. Save it through `POST /tasks/{id}/quality-plans`. The existing Testing panel exposes this advanced form and candidate inspection.
3. An enabled owner approves the exact plan version/hash. Its separate seven-day approval binds source commit/tree, snapshot, task/project/client scope, requirement/proposal/design versions, harness/profile hash, cases, risk exceptions, independence and repair cap.
4. Run the approved plan. Each round has a distinct fixed command/profile and separate test directory, persisted runner execution and independent assessment context. Checkpoints and worker leases fence cancellation and recovery. Missing models leave actual tool evidence saved; they do not produce a synthetic live assessment.
5. A failure stops progression, saves a structured defect and notifies the PM and owner. Requesting repair creates an awaiting-approval coding task. It cannot execute until the existing exact repository-change approval succeeds.
6. Repair branches start at the approved parent candidate worktree. The owner's original repository HEAD is never moved. New source requires a fresh approved QA plan with the original test files, cases, exceptions, independence policy and repair cap unchanged. All three rounds must pass, including the original failing case, before explicit verified closure.
7. Save an immutable readiness evaluation. Final review and package assembly bind its exact current hash and include QA evidence. The existing separate owner release approval and client delivery/acceptance gates still apply.

## Different verification stages

| Round | Fixed profile | Required evidence |
| --- | --- | --- |
| Implementation | python-qa-1 | Compile/build, fixed Ruff lint/static/format, approved unit/integration/API/validation/database/error cases |
| Functional | python-qa-2 | Distinct requirement-based journeys, negative/regression/persistence/auth checks, exact acceptance traceability |
| Security and release | python-qa-3 | Security/authorization, secret refusal, inspected container policy, risk-based dependency/performance/resource/recovery/rollback/environment/documentation checks |

Tests execute only inside the dedicated Docker broker's fixed runtime. The trusted harness resides outside the writable snapshot. Agents cannot choose Dockerfiles, image names, arbitrary shell commands, packages, host mounts, credentials or Docker control. Existing nonroot, no-network, read-only-root, capability, CPU/memory/PID/tmpfs and command/output/time limits remain enforced. The trusted image adds pinned Ruff; no AI model weights are installed.

An owner-authored coverage label is an explicit test-plan claim, not automatic proof that a test adequately covers a requirement. Actual case results and independent assessment remain required. The harmless CI fixture uses substantive CRUD/atomic validation/restart tests, an independently discovered unknown-field defect, SQL-injection-as-data, bounded performance, backup/restore and sandbox-secret checks. Its lack of a deployed target, network identity and third-party application dependencies is explicitly excepted as nonproduction scope; it does not certify production security, authenticated user journeys or deployment.

## Deterministic gate

PASS requires nonempty actual case receipts, every approved case present, successful build/test exits, matching fixed commands, inspected isolation policy, exact runner request hash, source identity, model/run/role/artifact/checkpoint provenance and current unexpired approvals. FAIL, skipped/BLOCKED, absent/INCONCLUSIVE output, stale digests, cancelled/incomplete workflows, unresolved or unverified defects, disabled owner, cross-project scope and missing required model/provider independence block readiness. The assessment cannot override failed tools. Security/authorization/secrets/resource checks in round 3 and automatic round-1 checks are non-waivable. Other non-applicable risk checks require a reason inside the exact owner-approved plan; exceptions are retained in reports and traceability.

Readiness always records `production_ready=false`, `deployment=not_verified` and separate owner release approval required. A quality gate pass is not production deployment or completed client delivery. Deterministic model output is labeled FIXTURE_TESTED and cannot claim model independence or authorize live fixture publication/release.

## Persistence and recovery

Protected quality_plan, quality_report, quality_defect and quality_readiness BusinessRecords reuse existing PostgreSQL-compatible JSON columns. They are excluded from the generic dashboard and cannot be created or patched through generic record routes. Dedicated endpoints require owner/tenant/project authority. Artifacts retain canonical bytes and hashes; append-only audit and defect history preserve decisions.

Before broker HTTP, the worker commits the execution/job ID and full request hash. After an uncertain response or actual worker crash, it GETs the same saved job rather than dispatching a new one. Docker stdout/stderr order is not assumed: exactly one complete harness receipt line is required; duplicate or malformed receipts are inconclusive. Unfinished or interrupted broker jobs require reconciliation; fixed-profile runner results persist across broker restart. In-flight cancellation revokes the workflow lease and requests cancellation of the exact job. The original code approval remains required for every repair, attempts are capped at three (or a lower approved limit), and exhaustion saves one owner escalation without executing another task. Verified closed defects are revalidated on each readiness calculation; reopening restores a release blocker.

## Current limits and evidence

The independent three-round profile currently supports the existing Python unittest runtime. Node engineering remains available through its existing runner profile, but unsupported independent QA cannot pass this gate. Plans are owner-authored; eligible connected AI models assess actual evidence. There is no claim of live model execution, generated PR publication, deployment or completed client delivery from deterministic tests. Local Docker is unavailable on the owner's machine; exact-source GitHub runner/Compose/PostgreSQL evidence is recorded separately in TEST_REPORT.md after observation.

## Verified Increment 5 evidence

Source `e69ff70ea6b36ca9e3704358c1ecd91e146ed8d6`, [CI 38303099307](https://github.com/Sharath-holla/Aiventra/actions/runs/38303099307): all six jobs passed; 554 backend and 73 browser checks. Actual Docker detected a defect, enforced exact repair approval, completed the new candidate and three distinct fresh rounds, verified closure and immutable readiness/package integration. Actual broker interruption/cancellation/duplicate prevention and PostgreSQL restart/restore passed. All AI output remains FIXTURE_TESTED. TEST_REPORT.md retains failures, corrected receipt parsing and full limits; END_TO_END_ENGINEERING_EVIDENCE.md records receipts. DevOps Increment 6 has not begun.
