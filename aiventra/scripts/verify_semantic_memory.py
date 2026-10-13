"""Actual PostgreSQL/pgvector + CPU-local semantic model/restart fixture. No paid AI calls."""

import hashlib
import json
import sys

from company_os import models as m
from company_os.db import SessionLocal, uid
from company_os.semantic_memory import index_pending, put, search
from sqlalchemy import select, text

PREFIX = "Semantic recovery verification fixture"


def row_payload(row):
    payload = {"table": row.__tablename__}
    for column in row.__table__.columns:
        value = getattr(row, column.name)
        if column.name == "embedding" and value is not None:
            value = [float(n) for n in value]
        payload[column.name] = value
    return payload


def prepare():
    with SessionLocal() as session:
        assert session.bind.dialect.name == "postgresql", "Run this check against actual PostgreSQL"
        assert session.scalar(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        assert "hnsw" in session.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_memory_chunks_vector_hnsw'")
        )
        org = m.Organization(id=uid(), name=PREFIX)
        session.add(org)
        session.flush()
        put(
            session,
            org.id,
            "manual:billing",
            "Payment recovery",
            "architecture_decision",
            "When a credit card charge fails because the payment processor is unavailable, retry the transaction using an idempotency key to avoid collecting money twice.",
            visibility="organization",
        )
        put(
            session,
            org.id,
            "manual:gardening",
            "Garden maintenance",
            "knowledge",
            "Water roses and prune bushes during the gardening season; add fertilizer to the soil.",
            visibility="organization",
        )
        session.commit()
        assert index_pending(session, org_id=org.id) == 2
        result = search(session, org.id, "Recovering interrupted financial purchases safely")
        assert result["mode"] == "semantic", result["reason"]
        assert result["results"][0]["title"] == "Payment recovery", "Real local paraphrase retrieval failed"
        put(
            session,
            org.id,
            "manual:billing",
            "Payment recovery",
            "architecture_decision",
            "When a credit card charge fails because the payment processor is unavailable, retry the transaction using an idempotency key to avoid collecting money twice. Log the recovery resolution.",
            visibility="organization",
        )
        session.commit()
        assert index_pending(session, org_id=org.id) == 1
    print(
        "PostgreSQL pgvector/HNSW and real local 384-dimensional semantic paraphrase retrieval verified; two source versions persisted"
    )


def snapshot():
    with SessionLocal() as session:
        org = session.scalar(select(m.Organization).where(m.Organization.name == PREFIX))
        assert org, "Prepare the memory recovery fixture first"
        entries = list(
            session.scalars(
                select(m.MemoryEntry).where(m.MemoryEntry.org_id == org.id).order_by(m.MemoryEntry.id)
            )
        )
        versions = list(
            session.scalars(
                select(m.MemoryVersion).where(m.MemoryVersion.org_id == org.id).order_by(m.MemoryVersion.id)
            )
        )
        chunks = list(
            session.scalars(
                select(m.MemoryChunk).where(m.MemoryChunk.org_id == org.id).order_by(m.MemoryChunk.id)
            )
        )
        assert len(entries) == 2 and len(versions) == 3 and len(chunks) == 3
        payload = [row_payload(r) for r in [*entries, *versions, *chunks]]
        result = search(session, org.id, "Recovering interrupted financial purchases safely")
        assert result["mode"] == "semantic" and result["results"][0]["title"] == "Payment recovery"
        return {
            "entries": len(entries),
            "versions": len(versions),
            "vectors": len(chunks),
            "retrieval": result["mode"],
            "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        }


if __name__ == "__main__":
    if "--prepare" in sys.argv:
        prepare()
    else:
        print(json.dumps(snapshot(), sort_keys=True))
