# Owner and client walkthrough

## Consult a new requirement

1. Create a client in Sales & Clients, or use Owner projects.
2. In Client Requirements, enter a title, brief, restrictions, deadline and AI consultation budget.
3. Choose **Local fixture** to exercise state transitions without AI API calls, or **Live providers** after registering credentials/models.
4. The worker saves Business Analyst extraction and independent specialist recommendations, then CFO interpretation and CEO synthesis. Live cloud briefs attempt read-only retrieval of the named providers' published pricing sources. Dynamic/unavailable pages remain unverified.
5. Answer clarification questions and provide rate inputs with region, quantity, unit, source and retrieval time. Saving a revision invalidates old approvals and reruns analysis.
6. Review alternatives, assumptions, cost completeness, risks, team and acceptance criteria. Choose an option and approve its exact hash/version, request changes or reject it.
7. Approval creates a project with architecture, implementation planning, independent test-plan and release-plan tasks. Later tasks wait for predecessor artifacts.
8. Review the board, ordered milestones, artifacts, model ledger, messages and audit history. Planning completion does not mean software has been implemented or deployed.
9. Use **Assign specialist** inside an active project to queue document work for an enabled employee with artifact permission. Supply an objective, acceptance criteria, provider mode and task cap. Repository changes use the separate coding approval workflow.

Uploaded txt/md/json documents are stored as untrusted evidence. Upload or research retrieval after a run needs a new revision to enter its context. Diagram/PDF parsing, generic repository ZIP uploads and rich client document ingestion remain pending.

## Rate inputs

Open Clarify & Revise → Source-backed cost inputs. Example **format only** (replace all values with actual evidence; this is not a published rate):

```json
[{"alternative":"Hybrid migration","label":"Owner supplied compute rate","unit_price_micro":0,"quantity":"1","unit":"monthly instance","region":"supply-region","source_url":"https://cloud.google.com/products/compute/pricing","retrieved_at":1,"one_time":false,"verified":false}]
```

Each alternative matches its exact proposal name. Zero means a rate explicitly supplied as zero; no lines means unknown. All comparisons remain partial until compute, storage, egress, licenses, labor, migration and downtime are validated. No cheapest-provider conclusion is certified automatically.

## Workforce and controls

Inspect every employee, department, manager, responsibility, tool list and run history. Change routing policy, pause an employee or create another instance. Server APIs support responsibilities/objectives and iteration/time/cost settings. Only owner permissions can change these configurations.

Company pause stops new dispatch and result checkpoints. It does not erase history or retract an already dispatched provider request. Project pause, provider disable, task cancel and tool revocation preserve artifacts and remain server controls. Live requests with uncertain billing hold funds until reconciliation.

## Executive commands

Supported commands execute authenticated operations: `Show every active project`, `Give me the complete test report`, `Show spending`, `Pause company`, `Resume company`, `Pause all production deployments`, and `consult: <requirement>`. The command interface records its reply and actual action. Unsupported natural-language instructions do not claim to execute.

## Business records

CRM opportunities, campaigns, support requests, knowledge, incidents, email drafts and calendar drafts are persistent records with owner-reviewed status. OAuth mail/calendar connections and external sending/publishing are pending. Draft saving never sends messages.

Client identities can use scoped requirement submission and retrieval. Owner provisioning through the user-management CLI/API and a full proposal-review client portal require further implementation; the current approval endpoint is owner-only.
