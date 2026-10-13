"""Fenced CI-only partial simulation across actual API/worker restart; never live deployment."""

import argparse
import asyncio
import json
import os
import re
import time

from company_os import deployment_adapter as adapter
from company_os import deployments as d
from company_os import models as m
from company_os.config import settings
from company_os.db import SessionLocal, engine, now, uid
from company_os.security import digest
from sqlalchemy import select


def guard():
    config = settings()
    assert os.getenv("CI") == "true" and config.isolated_postgres_ci and config.isolated_test_environment
    assert config.app_env == "test" and re.fullmatch(r"browser_ci_\d+_\d+", engine.url.database or "")
    assert config.ai_spending_mode == "ZERO_COST_ONLY"


async def prepare():
    with SessionLocal() as session:
        previous = session.scalar(
            select(m.BusinessRecord)
            .where(
                m.BusinessRecord.kind == "devops_receipt", m.BusinessRecord.status == "deployment_completed"
            )
            .order_by(m.BusinessRecord.created_at.desc())
        )
        assert previous, "Run the explicitly simulated browser journey first"
        project = session.get(m.Project, previous.project_id)
        body = d.validate_receipt(session, project, previous)
        package = session.get(m.DeliveryPackage, body["package_id"])
        assert package.classification == "fixture_nonproduction"
        owner = session.get(m.User, package.owner_id)
        assert owner.email == "browser-owner@fixture.test" and owner.enabled and owner.role == "owner"
        plan = d.prepare(
            session,
            project,
            owner,
            d.PlanInput(
                request_id=uid(),
                package_id=package.id,
                target_id=body["target_id"],
                risk_summary="Explicit CI restart simulation. No real target or client release.",
            ),
        )
        session.flush()
        d.approve(session, plan, owner, plan.version, plan.data["manifest_hash"], 3600)
        session.flush()
        work = d.start(session, plan, owner, uid(), plan.data["manifest_hash"])
        session.commit()
        workflow = session.get(m.Workflow, work.workflow_id)
        for _ in range(2):
            workflow.status, workflow.lease_token, workflow.lease_until = "running", uid(), now() + 180
            session.commit()
            await d.deployment_step(session, workflow, workflow.lease_token, work, project)
            session.commit()
        d.command(session, work, owner, "pause")
        session.add(
            m.BusinessRecord(
                org_id=project.org_id,
                project_id=project.id,
                client_id=project.client_id,
                kind="devops_recovery_fixture",
                title="Explicit partial simulator restart fixture",
                data={"work_id": work.id, "owner_id": owner.id},
            )
        )
        session.commit()


def rows(session):
    marker = session.scalar(
        select(m.BusinessRecord)
        .where(m.BusinessRecord.kind == "devops_recovery_fixture")
        .order_by(m.BusinessRecord.created_at.desc())
    )
    assert marker
    work = session.get(m.AgentWork, marker.data["work_id"])
    workflow = session.get(m.Workflow, work.workflow_id)
    job = adapter.read(session, work.result["job_id"], work.org_id)
    return marker, work, workflow, job


def snapshot():
    with SessionLocal() as session:
        marker, work, workflow, job = rows(session)
        assert workflow.status == "paused" and workflow.step == 2 and job.status == "artifact_staged"
        values = [marker, work, workflow, job]
        saved = [
            {column.name: getattr(row, column.name) for column in row.__table__.columns} for row in values
        ]
        return {
            "work_id": work.id,
            "job_id": job.id,
            "classification": adapter.CLASSIFICATION,
            "sha256": digest(saved),
        }


def resume():
    with SessionLocal() as session:
        marker, work, _, _ = rows(session)
        d.command(session, work, session.get(m.User, marker.data["owner_id"]), "resume")
        session.commit()


def verify():
    for _ in range(45):
        with SessionLocal() as session:
            _, work, workflow, job = rows(session)
            if workflow.status == "completed":
                receipt = session.get(m.BusinessRecord, work.result["receipt_id"])
                body = d.validate_receipt(session, session.get(m.Project, work.project_id), receipt)
                assert (
                    workflow.step == 5
                    and body["job_id"] == job.id
                    and body["status"] == "deployment_completed"
                )
                assert not body["live_verified"]
                receipts = session.scalars(
                    select(m.BusinessRecord).where(
                        m.BusinessRecord.kind == "devops_receipt",
                        m.BusinessRecord.project_id == work.project_id,
                    )
                )
                assert len([row for row in receipts if row.data["body"]["work_id"] == work.id]) == 1
                return {
                    "work_id": work.id,
                    "job_id": job.id,
                    "receipt_id": receipt.id,
                    "checkpoints": workflow.step,
                    "classification": adapter.CLASSIFICATION,
                    "live_verified": False,
                }
            assert workflow.status not in {"needs_attention", "failed", "cancelled"}, workflow.last_error
        time.sleep(1)
    raise AssertionError("The actual worker did not resume the saved simulator job")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    guard()
    if args.prepare:
        asyncio.run(prepare())
    if args.resume:
        resume()
    print(json.dumps(verify() if args.verify else snapshot(), sort_keys=True))
