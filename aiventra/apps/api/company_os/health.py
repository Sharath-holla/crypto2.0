"""Runtime health facts; liveness does not imply worker or provider readiness."""

from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import settings
from .db import now
from .models import WorkerHeartbeat


def workers(session: Session) -> dict:
    latest = session.scalar(
        select(func.max(WorkerHeartbeat.last_seen)).where(WorkerHeartbeat.status == "running")
    )
    return {
        "status": "ready" if latest and now() - latest <= settings().worker_stale_seconds else "unavailable",
        "last_seen": latest,
        "stale_after_seconds": settings().worker_stale_seconds,
    }


def heartbeat(session: Session, worker_id: str, status="running"):
    record = session.get(WorkerHeartbeat, worker_id)
    if record is None:
        record = WorkerHeartbeat(id=worker_id, last_seen=now(), status=status)
        session.add(record)
    else:
        record.last_seen, record.status = now(), status
    session.commit()


def database_state(session: Session) -> dict:
    """Facts from this session's actual database; no connection strings or secrets."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    backend = session.get_bind().dialect.name
    expected = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
    revision, vector, index = None, None, False
    with session.begin_nested():
        session.execute(text("SELECT 1"))
        if backend == "postgresql":
            vector = session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
            index = bool(
                session.scalar(
                    text(
                        "SELECT count(*) FROM pg_indexes WHERE schemaname=current_schema() "
                        "AND tablename='memory_chunks' AND indexname='ix_memory_chunks_vector_hnsw' "
                        "AND indexdef LIKE '%USING hnsw%'"
                    )
                )
            )
    try:
        with session.begin_nested():
            revision = session.scalar(text("SELECT version_num FROM alembic_version"))
    except SQLAlchemyError:
        pass
    return {
        "backend": backend,
        "connected": True,
        "schema_revision": revision,
        "expected_revision": expected,
        "schema_current": revision == expected,
        "pgvector_version": vector,
        "vector_index_available": index,
        "embedding_provider": settings().embedding_provider,
        "embedding_model": settings().embedding_model,
    }
