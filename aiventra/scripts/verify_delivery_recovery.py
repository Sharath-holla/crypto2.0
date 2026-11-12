"""Digest actual browser-created fixture reviews across service/database restart."""

import json

from company_os import models as m
from company_os.db import SessionLocal
from company_os.security import digest
from sqlalchemy import select


def snapshot():
    with SessionLocal() as session:
        records = list(
            session.scalars(
                select(m.BusinessRecord)
                .where(
                    m.BusinessRecord.kind == "delivery_review",
                    m.BusinessRecord.status == "fixture_reviewed",
                )
                .order_by(m.BusinessRecord.id)
            )
        )
        assert records, "Complete the explicit final-review browser fixture first"
        work_ids = [row.data["work_id"] for row in records]
        work = list(
            session.scalars(select(m.AgentWork).where(m.AgentWork.id.in_(work_ids)).order_by(m.AgentWork.id))
        )
        assert len(work) == len(records)
        assert all(
            row.result["delivery_released"] is False and row.result["client_accepted"] is False
            for row in work
        )
        workflow_ids = [row.workflow_id for row in work]
        artifact_ids = [review["artifact_id"] for row in records for review in row.data["reviews"]]
        tables = {"business_records": records, "agent_work": work}
        for model, condition in [
            (m.Workflow, m.Workflow.id.in_(workflow_ids)),
            (m.WorkflowStep, m.WorkflowStep.workflow_id.in_(workflow_ids)),
            (m.ModelRun, m.ModelRun.workflow_id.in_(workflow_ids)),
            (m.Artifact, m.Artifact.id.in_(artifact_ids)),
            (m.Message, m.Message.correlation_id.in_(work_ids)),
        ]:
            tables[model.__tablename__] = list(
                session.scalars(select(model).where(condition).order_by(model.id))
            )
        assert len(tables["workflow_steps"]) == len(records) * 5
        assert len(tables["artifacts"]) == len(records) * 5
        assert len(tables["messages"]) == len(records) * 4
        assert all(row.status == "acknowledged" for row in tables["messages"])
        assert all(row.status == "completed" and row.mode == "mock" for row in tables["workflows"])
        data = {
            name: [
                {column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows
            ]
            for name, rows in tables.items()
        }
        return {"counts": {name: len(rows) for name, rows in data.items()}, "sha256": digest(data)}


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
