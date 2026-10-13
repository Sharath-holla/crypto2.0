"""Controlled fixture preparation across a real service stop before package freeze.

Stop workers before --prepare. Only an existing deterministic package source is
eligible. No inference, release, email, repository execution or deployment occurs.
"""

import argparse
import asyncio
import json
import time

from company_os import models as m
from company_os import packages
from company_os.db import SessionLocal, now, uid
from company_os.routes.package_operations import PackageInput, prepare
from company_os.routes.staffing_operations import Control, workflow_control
from company_os.security import digest
from sqlalchemy import select


async def create():
    with SessionLocal() as session:
        old = session.scalar(
            select(m.DeliveryPackage)
            .where(
                m.DeliveryPackage.classification == "fixture_nonproduction",
                m.DeliveryPackage.status == "package_ready",
            )
            .order_by(m.DeliveryPackage.created_at.desc(), m.DeliveryPackage.version.desc())
        )
        assert old, "Run the deterministic package browser journey first"
        owner = session.get(m.User, old.owner_id)
        assert owner.enabled and owner.role == "owner"
        body = {
            **old.input,
            "request_id": uid(),
            "summary": "Explicit restart recovery fixture between validation and freeze; never release.",
        }
        result = prepare(old.project_id, PackageInput.model_validate(body), owner, session)
        package = session.get(m.DeliveryPackage, result["id"])
        workflow = session.get(m.Workflow, package.workflow_id)
        workflow.status, workflow.lease_token, workflow.lease_until = "running", uid(), now() + 180
        session.commit()
        await packages.package_step(session, workflow, workflow.lease_token)
        session.commit()
        workflow_control(workflow.id, Control(action="pause"), owner, session)
        assert workflow.step == 1 and package.status == "preparing" and not package.finalized_at
        session.add(
            m.BusinessRecord(
                org_id=package.org_id,
                project_id=package.project_id,
                kind="delivery_recovery_fixture",
                title="Controlled partial package recovery",
                data={"package_id": package.id},
                status="fixture",
            )
        )
        session.commit()


def rows(session):
    marker = session.scalar(
        select(m.BusinessRecord)
        .where(m.BusinessRecord.kind == "delivery_recovery_fixture")
        .order_by(m.BusinessRecord.created_at.desc(), m.BusinessRecord.id.desc())
    )
    assert marker, "No preparation recovery fixture exists"
    package = session.get(m.DeliveryPackage, marker.data["package_id"])
    assert package.classification == "fixture_nonproduction"
    workflow = session.get(m.Workflow, package.workflow_id)
    steps = list(
        session.scalars(
            select(m.WorkflowStep)
            .where(m.WorkflowStep.workflow_id == workflow.id)
            .order_by(m.WorkflowStep.id)
        )
    )
    return package, workflow, steps


def snapshot():
    with SessionLocal() as session:
        package, workflow, steps = rows(session)
        assert package.status == "preparing" and not package.finalized_at and not package.manifest_hash
        assert workflow.status == "paused" and workflow.step == 1 and len(steps) == 1
        manifest = packages.assemble(session, package)
        assert digest(manifest["files"]) == steps[0].result["files_hash"]
        data = [
            {column.name: getattr(row, column.name) for column in row.__table__.columns}
            for row in [package, workflow, *steps]
        ]
        return {
            "package_id": package.id,
            "classification": package.classification,
            "checkpoints": 1,
            "files": len(manifest["files"]),
            "sha256": digest(data),
        }


def resume():
    with SessionLocal() as session:
        package, workflow, _ = rows(session)
        owner = session.get(m.User, package.owner_id)
        workflow_control(workflow.id, Control(action="resume"), owner, session)


def verify():
    for _ in range(45):
        with SessionLocal() as session:
            package, workflow, steps = rows(session)
            if workflow.status == "completed":
                assert workflow.step == 2 and len(steps) == 2 and package.status == "package_ready"
                assert packages.integrity(session, package)
                assert not session.scalar(select(m.Approval.id).where(m.Approval.subject_id == package.id))
                return {
                    "package_id": package.id,
                    "checkpoints": 2,
                    "manifest_hash": package.manifest_hash,
                    "released": False,
                }
        time.sleep(1)
    raise AssertionError("Existing worker did not resume the partial package")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.prepare:
        asyncio.run(create())
    if args.resume:
        resume()
    print(json.dumps(verify() if args.verify else snapshot(), sort_keys=True))


if __name__ == "__main__":
    main()
