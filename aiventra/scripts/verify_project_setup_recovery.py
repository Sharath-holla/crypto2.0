"""Read-only durable draft/attachment snapshot for SQLite and PostgreSQL restart CI."""

import hashlib
import json

from company_os import models as m
from company_os.config import settings
from company_os.db import SessionLocal
from company_os.draft_documents import pdf_source
from company_os.security import digest
from sqlalchemy import select

assert settings().ai_spending_mode == "ZERO_COST_ONLY"
with SessionLocal() as session:
    records = session.scalars(
        select(m.BusinessRecord).where(m.BusinessRecord.kind == "project_setup").order_by(m.BusinessRecord.id)
    ).all()
    assert records, "Complete a project wizard browser journey first"
    snapshots = []
    attachments = []
    for row in records:
        snapshots.append({"id": row.id, "version": row.version, "status": row.status, "data": row.data})
        for item in row.data["attachments"]:
            artifact = session.get(m.Artifact, item["id"])
            assert artifact.org_id == row.org_id
            assert artifact.sha256 == item["sha256"] == hashlib.sha256(artifact.content.encode()).hexdigest()
            attachments.append({"id": artifact.id, "sha256": artifact.sha256})
            if item.get("format") == "pdf":
                source = pdf_source(row.org_id, item["source_sha256"])
                assert source.stat().st_size <= 1048576
                assert hashlib.sha256(source.read_bytes()).hexdigest() == item["source_sha256"]
                attachments[-1]["source_sha256"] = item["source_sha256"]
    print(
        json.dumps(
            {
                "drafts": len(records),
                "draft_digest": digest(snapshots),
                "attachments": len(attachments),
                "attachment_digest": digest(attachments),
                "spending_mode": "ZERO_COST_ONLY",
            },
            sort_keys=True,
        )
    )
