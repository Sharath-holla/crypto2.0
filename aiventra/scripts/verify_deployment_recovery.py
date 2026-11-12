"""Read-only simulated deployment evidence digest across actual PostgreSQL service restarts."""

import json

from company_os import deployments
from company_os import models as m
from company_os.db import SessionLocal
from company_os.security import digest
from sqlalchemy import select

with SessionLocal() as session:
    receipts = list(
        session.scalars(
            select(m.BusinessRecord)
            .where(m.BusinessRecord.kind == "devops_receipt")
            .order_by(m.BusinessRecord.id)
        )
    )
    assert receipts, "Run the package-to-simulated-deployment browser journey first"
    for receipt in receipts:
        body = deployments.validate_receipt(session, session.get(m.Project, receipt.project_id), receipt)
        assert body["classification"] == "SIMULATED_NONPRODUCTION" and not body["live_verified"]
    records = list(
        session.scalars(
            select(m.BusinessRecord)
            .where(m.BusinessRecord.kind.like("devops_%"))
            .order_by(m.BusinessRecord.id)
        )
    )
    work = list(
        session.scalars(select(m.AgentWork).where(m.AgentWork.kind == "deployment").order_by(m.AgentWork.id))
    )
    workflows = [session.get(m.Workflow, row.workflow_id) for row in work]
    snapshot = {
        name: [{column.name: getattr(row, column.name) for column in row.__table__.columns} for row in values]
        for name, values in {"records": records, "work": work, "workflows": workflows}.items()
    }
    print(
        json.dumps(
            {
                "receipts": len(receipts),
                "jobs": len(work),
                "classification": "SIMULATED_NONPRODUCTION",
                "sha256": digest(snapshot),
            },
            sort_keys=True,
        )
    )
