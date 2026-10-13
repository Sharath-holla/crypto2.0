# Decisions

- Next.js and FastAPI follow the requested stack. SQLAlchemy + Alembic target PostgreSQL, with SQLite for credential-free local development.
- Separate worker process; transactional checkpointing and conditional job leases. Temporal and distributed worker certification remain pending, explicitly tracked.
- Native HTTP provider adapters avoid model-specific hardcoding and framework overlap. Prices are owner-entered with source/freshness; recorded token usage produces **computed estimates**, not claims of invoice charges.
- Local fixtures are an explicit execution mode and cannot be used as live fallback. No model identifiers or prices are preconfigured for live providers.
- Repository import is read-only under a configured root. Worktrees and restricted Docker commands protect the original project. Cloud mutations and external outreach remain gated and disabled until a supported authorized connector exists.
- Normalized relational records hold authoritative state. Permission-scoped text retrieval is initial memory; pgvector semantic retrieval remains pending.
