"""Read-only saved planning evidence digest for actual service restart comparisons."""

import json

from company_os import models as m
from company_os.db import SessionLocal
from company_os.security import digest
from sqlalchemy import select


def snapshot():
    with SessionLocal() as session:
        work = list(
            session.scalars(
                select(m.AgentWork).where(m.AgentWork.kind == "planning").order_by(m.AgentWork.id)
            )
        )
        work = [row for row in work if session.get(m.Workflow, row.workflow_id).status == "completed"]
        assert work, "Complete the explicit planning browser fixture before checking recovery"
        tables = {"agent_work": work}
        workflow_ids = [row.workflow_id for row in work]
        artifact_ids = [record_id for row in work for record_id in row.result["document_ids"]]
        plan_ids = [row.subject_id for row in work]
        for model, condition in [
            (m.Workflow, m.Workflow.id.in_(workflow_ids)),
            (m.WorkflowStep, m.WorkflowStep.workflow_id.in_(workflow_ids)),
            (m.Artifact, m.Artifact.id.in_(artifact_ids)),
            (m.Message, m.Message.correlation_id.in_([row.id for row in work])),
            (m.ModelRun, m.ModelRun.workflow_id.in_(workflow_ids)),
            (m.StaffingPlan, m.StaffingPlan.id.in_(plan_ids)),
            (m.StaffingRevision, m.StaffingRevision.plan_id.in_(plan_ids)),
        ]:
            tables[model.__tablename__] = list(
                session.scalars(select(model).where(condition).order_by(model.id))
            )
        assert len(tables["artifacts"]) == len(work) * 3
        assert len(tables["messages"]) == len(work) * 2
        assert all(row.status == "acknowledged" for row in tables["messages"])
        data = {
            name: [
                {column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows
            ]
            for name, rows in tables.items()
        }
        return {"counts": {name: len(rows) for name, rows in data.items()}, "sha256": digest(data)}


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
