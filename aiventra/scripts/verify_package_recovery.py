"""Read-only digest of frozen fixture packages and actual private files across restart."""

import json

from company_os import models as m
from company_os import packages
from company_os.db import SessionLocal
from company_os.security import digest
from sqlalchemy import select


def snapshot():
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(m.DeliveryPackage)
                .where(
                    m.DeliveryPackage.classification == "fixture_nonproduction",
                    m.DeliveryPackage.finalized_at.is_not(None),
                )
                .order_by(m.DeliveryPackage.id)
            )
        )
        assert rows, "Run the actual package browser fixture first"
        assert all(row.status in {"package_ready", "package_blocked"} for row in rows)
        for row in rows:
            assert packages.integrity(session, row)
        workflows = [session.get(m.Workflow, row.workflow_id) for row in rows]
        assert all(row.status == "completed" and row.step == 2 for row in workflows)
        steps = list(
            session.scalars(
                select(m.WorkflowStep)
                .where(m.WorkflowStep.workflow_id.in_([row.id for row in workflows]))
                .order_by(m.WorkflowStep.id)
            )
        )
        assert len(steps) == len(rows) * 2
        data = {
            name: [
                {column.name: getattr(row, column.name) for column in row.__table__.columns} for row in values
            ]
            for name, values in {"packages": rows, "workflows": workflows, "steps": steps}.items()
        }
        files = [
            {
                "package_id": row.id,
                "file_id": file["id"],
                "sha256": packages.sha(packages.read_blob(row, file)),
            }
            for row in rows
            for file in row.manifest["files"]
        ]
        return {
            "packages": len(rows),
            "checkpoints": len(steps),
            "files": len(files),
            "sha256": digest({"records": data, "files": files}),
        }


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
