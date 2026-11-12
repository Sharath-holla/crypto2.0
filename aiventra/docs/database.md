# Database design

SQLAlchemy defines normalized entities in `apps/api/company_os/models.py`. Alembic owns schema creation and changes. `alembic upgrade head` applies versioned migrations; `alembic check` detects metadata drift. Do not use `create_all` for production upgrades.

| Area | Tables |
|---|---|
| Identity / organization | organizations, users, clients, departments, agents |
| Models | providers, model_configs, model_runs |
| Consulting | requirements, proposals, approvals, meetings |
| Delivery | projects, milestones, tasks, task_dependencies, repositories, executions, artifacts |
| Durable state | workflows, workflow_steps, messages |
| Finance | budgets, spending_transactions |
| Enterprise / oversight | business_records, notifications, audit_events |

Every business row has an organization foreign key. Requirements and projects carry client scope. Project/task relationships are server validated before records are created or exposed. Foreign keys and unique constraints protect identities, proposal versions, model IDs, workflow steps and transactions. Unique workflow indexes prevent duplicate task dispatch and duplicate requirement revisions.

Requirements, budgets and business records have optimistic update checks. Jobs use conditional lease claims and fenced checkpoints. Approval creation obtains an organization write lock to serialize competing choices. Money uses integers in microdollars; estimates multiply with Decimal and round conservatively.

Daily and monthly budget scopes currently use UTC billing periods. Organization limits are lifetime caps unless the owner changes them. Reservations participate in all applicable caps. Spending is counted once in the transaction ledger; per-scope budget counters are overlapping views, never amounts to add together.

Business records are a validated envelope for CRM, support, incidents, knowledge and drafts. They do not yet replace fully normalized external contact/email/calendar schemas. Model evaluations, skills, independent tool-grant rows, sprints, epics, deployments and billing imports remain schema expansion work. pgvector semantic retrieval is pending.

SQLite WAL provides local persistence and foreign keys. PostgreSQL is the intended deployment database; SQLAlchemy's dialect and Compose configuration target it, but PostgreSQL runtime verification is pending. A separate read/write application database role and restricted migration role are required before production.

Audit events are hash-linked per organization. A database trigger rejects update/delete. Database owners can still disable triggers or replace history and the stored head; external immutable anchoring is required for stronger integrity.
