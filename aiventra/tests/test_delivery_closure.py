"""No live client delivery: exact closure contracts in isolated fixture databases."""

from uuid import uuid4

import pytest
from company_os import models as m
from company_os.db import now
from company_os.security import digest
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_client_delivery import approve, exact, publish, release_fixture

from tests.test_migration_upgrade import migrate


async def accepted(http, company, requirement):
    project, package, _, client = await release_fixture(http, company, requirement)
    publish(http, package, approve(http, package))
    owner = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    result = http.post(
        f"/client/deliveries/{package['id']}/responses",
        json=exact(
            package, kind="accept", reason="Exact isolated fixture package accepted for contract testing."
        ),
    )
    assert result.status_code == 201, result.text
    http.headers["Authorization"] = owner
    return project, package, client, result.json()


async def test_exact_closure_reopen_retains_acceptance(http, company, requirement):
    project, package, client, response = await accepted(http, company, requirement)
    path = f"/projects/{project['id']}"
    evidence = http.get(path + "/closure-readiness").json()
    assert evidence["ready"], evidence
    body = {
        "request_id": str(uuid4()),
        "version": project["version"],
        "closure_hash": evidence["closure_hash"],
    }
    assert http.post(path + "/close", json={**body, "approval_id": "missing"}).status_code == 409
    approved = http.post(path + "/approve-closure", json=body)
    assert approved.status_code == 200, approved.text
    approval = approved.json()["approval"]
    closed_body = {**body, "request_id": str(uuid4()), "approval_id": approval["id"]}
    closed = http.post(path + "/close", json=closed_body)
    assert closed.status_code == 200, closed.text
    assert http.post(path + "/close", json=closed_body).json() == closed.json()
    assert http.patch(path, json={"enabled": True}).status_code == 409
    assert (
        http.post(
            f"/delivery-packages/{package['id']}/withdraw",
            json=exact(package, reason="Must explicitly reopen before changing a closed delivery."),
        ).status_code
        == 409
    )
    reopened = http.post(
        path + "/reopen",
        json={
            "request_id": str(uuid4()),
            "version": project["version"],
            "reason": "Owner reopened the fixture for a new scoped follow-up.",
        },
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["version"] == project["version"] + 1
    with company["factory"]() as session:
        assert session.get(m.DeliveryResponse, response["id"]).manifest_hash == package["manifest_hash"]
        closure = session.get(m.BusinessRecord, closed.json()["closure_id"])
        assert closure.data["closure_hash"] == digest(closure.data["manifest"])
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    assert http.get("/client/history").json()[0]["id"] == response["id"]
    assert http.get(f"/client/deliveries/{package['id']}").status_code == 200


@pytest.mark.parametrize("fault", ["approval_expiry", "financial", "source", "unresolved_case"])
async def test_closure_revalidates_current_evidence(http, company, requirement, fault):
    project, package, _, _ = await accepted(http, company, requirement)
    path = f"/projects/{project['id']}"
    evidence = http.get(path + "/closure-readiness").json()
    assert evidence["ready"], evidence
    body = {
        "request_id": str(uuid4()),
        "version": project["version"],
        "closure_hash": evidence["closure_hash"],
    }
    approval = http.post(path + "/approve-closure", json=body).json()["approval"]
    with company["factory"]() as session:
        if fault == "approval_expiry":
            session.get(m.Approval, approval["id"]).expires_at = now() - 1
        elif fault == "financial":
            session.scalar(
                select(m.Budget).where(m.Budget.scope == f"project:{project['id']}")
            ).reserved_micro = 1
        elif fault == "source":
            session.get(m.Project, project["id"]).version += 1
        else:
            session.add(
                m.BusinessRecord(
                    org_id=company["org"].id,
                    project_id=project["id"],
                    client_id=company["client"].id,
                    kind="delivery_case",
                    title="Controlled outstanding defect",
                    status="submitted",
                    data={"kind": "report_defect"},
                )
            )
        session.commit()
    assert (
        http.post(
            path + "/close", json={**body, "request_id": str(uuid4()), "approval_id": approval["id"]}
        ).status_code
        == 409
    )
    with company["factory"]() as session:
        assert session.get(m.Project, project["id"]).status == "active"


async def test_migrated_client_statements_are_append_only(http, company, requirement):
    engine = company["factory"].kw["bind"]
    with engine.begin() as connection:
        for table in (m.DeliveryResponse, m.ClientAccessGrant, m.ClientInvitation, m.DeliveryPackage):
            table.__table__.drop(connection)
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('a31d07edc482')"))
    migrate(company["root"] / "test.db", "head")
    _, _, _, response = await accepted(http, company, requirement)
    with company["factory"]() as session:
        with pytest.raises(IntegrityError, match="append only"):
            session.execute(
                update(m.DeliveryResponse)
                .where(m.DeliveryResponse.id == response["id"])
                .values(reason="rewritten")
            )
            session.commit()
        session.rollback()
        with pytest.raises(IntegrityError, match="append only"):
            session.execute(text("DELETE FROM delivery_responses WHERE id=:id"), {"id": response["id"]})
            session.commit()
        session.rollback()
        assert session.get(m.DeliveryResponse, response["id"]).kind == "accept"
