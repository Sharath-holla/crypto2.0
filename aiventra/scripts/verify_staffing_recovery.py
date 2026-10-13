"""Digest owner-approved browser staffing fixtures before/after real Docker restarts."""

import hashlib
import json

from company_os import models as m
from company_os.db import SessionLocal
from company_os.security import canonical
from sqlalchemy import select


def snapshot():
    with SessionLocal() as session:
        projects = list(
            session.scalars(
                select(m.Project)
                .where(m.Project.name.like("Workforce browser fixture %"))
                .order_by(m.Project.id)
            )
        )
        assert projects, "Run workforce browser verification first"
        project_ids = [row.id for row in projects]
        plans = list(
            session.scalars(
                select(m.StaffingPlan)
                .where(m.StaffingPlan.project_id.in_(project_ids))
                .order_by(m.StaffingPlan.id)
            )
        )
        assert plans and all(row.status == "paused" for row in plans)
        tasks = list(
            session.scalars(select(m.Task).where(m.Task.project_id.in_(project_ids)).order_by(m.Task.id))
        )
        task_ids = [row.id for row in tasks]
        workflows = list(
            session.scalars(
                select(m.Workflow).where(m.Workflow.task_id.in_(task_ids)).order_by(m.Workflow.id)
            )
        )
        assert all(row.status in {"completed", "paused"} for row in workflows), "Wait for fixture checkpoints"
        tables = {"projects": projects, "staffing_plans": plans, "tasks": tasks, "workflows": workflows}
        filters = [
            (m.StaffingRevision, m.StaffingRevision.plan_id.in_([row.id for row in plans])),
            (m.TaskAssignment, m.TaskAssignment.task_id.in_(task_ids)),
            (m.TaskDependency, m.TaskDependency.task_id.in_(task_ids)),
            (
                m.Approval,
                m.Approval.subject_id.in_([row.id for row in plans] + [row.proposal_id for row in projects]),
            ),
            (m.Proposal, m.Proposal.id.in_([row.proposal_id for row in projects])),
            (m.WorkflowStep, m.WorkflowStep.workflow_id.in_([row.id for row in workflows])),
            (m.ModelRun, m.ModelRun.task_id.in_(task_ids)),
            (m.Message, m.Message.task_id.in_(task_ids)),
        ]
        for model, condition in filters:
            tables[model.__tablename__] = list(
                session.scalars(select(model).where(condition).order_by(*model.__table__.primary_key.columns))
            )
        tables["requirements"] = list(
            session.scalars(
                select(m.Requirement)
                .where(m.Requirement.id.in_([row.requirement_id for row in tables["proposals"]]))
                .order_by(m.Requirement.id)
            )
        )
        data = {
            name: [
                {column.name: getattr(row, column.name) for column in row.__table__.columns} for row in rows
            ]
            for name, rows in tables.items()
        }
        return {
            "counts": {name: len(rows) for name, rows in tables.items()},
            "sha256": hashlib.sha256(canonical(data).encode()).hexdigest(),
        }


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
