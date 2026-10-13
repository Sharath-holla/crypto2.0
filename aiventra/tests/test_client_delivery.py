"""Release/access contracts in disposable SQLite. No live AI or real client release.

Positive contracts explicitly rewrite fixture provenance into a live-shaped saved
record. There is no application bypass, network inference or active database use.
"""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os import delivery
from company_os import models as m
from company_os.db import now
from company_os.security import digest
from company_os.workflows import tick
from sqlalchemy import select
from test_packages import package_input, reviewed_project


def exact(package, **extra):
    return {
        "request_id": str(uuid4()),
        "version": package["version"],
        "manifest_hash": package["manifest_hash"],
        **extra,
    }


def invite_client(http, project, email="invited-client@test", can_respond=True):
    body = {"request_id": str(uuid4()), "email": email, "can_respond": can_respond}
    response = http.post(f"/projects/{project['id']}/client-invitations", json=body)
    assert response.status_code == 201, response.text
    invitation = response.json()
    retry = http.post(f"/projects/{project['id']}/client-invitations", json=body)
    assert retry.json()["token"] is None
    assert "token_hash" not in str(retry.json())
    redemption = http.post(
        "/auth/redeem-invitation",
        json={"token": invitation["token"], "email": email, "password": "private-fixture-client-password"},
    )
    assert redemption.status_code == 200, redemption.text
    assert (
        http.post(
            "/auth/redeem-invitation",
            json={
                "token": invitation["token"],
                "email": email,
                "password": "private-fixture-client-password",
            },
        ).status_code
        == 403
    )
    return invitation, redemption.json()


async def release_fixture(http, company, requirement, live_shape=True):
    project, evidence, review = await reviewed_project(http, company, requirement)
    if live_shape:
        # Controlled persisted provider contracts ONLY, not live execution evidence.
        with company["factory"]() as session:
            for provider in session.scalars(select(m.Provider)):
                provider.kind = "ollama"
            for workflow in session.scalars(select(m.Workflow)):
                workflow.mode = "live"
            for run in session.scalars(select(m.ModelRun)):
                run.cost_basis = "local_no_provider_charge"
            session.flush()
            evidence = delivery.readiness(session, session.get(m.Project, project["id"]), "live")
            assert evidence["ready"], evidence["blockers"]
            record = session.get(m.BusinessRecord, review["id"])
            record.status = "awaiting_delivery_approval"
            record.data = {
                **record.data,
                "mode": "live",
                "manifest": evidence["manifest"],
                "source_hash": evidence["source_hash"],
                "reviews": [{**row, "mode": "live"} for row in record.data["reviews"]],
            }
            work = session.get(m.AgentWork, record.data["work_id"])
            work.input = {**work.input, "source_hash": evidence["source_hash"]}
            for step in session.scalars(
                select(m.WorkflowStep).where(m.WorkflowStep.workflow_id == work.workflow_id)
            ):
                step.result = {**step.result, "source_hash": evidence["source_hash"]}
            session.commit()
    invitation, client = invite_client(http, project)
    body = package_input(evidence, review)
    body["recipient_ids"] = [client["user"]["id"]]
    body["documents"][0]["client_visible"] = True
    response = http.post(f"/projects/{project['id']}/delivery-packages", json=body)
    assert response.status_code == 201, response.text
    package = response.json()
    for _ in range(2):
        assert await tick(company["factory"])
    saved = http.get(f"/delivery-packages/{package['id']}").json()
    assert saved["status"] == "package_ready", saved
    return project, saved, invitation, client


def approve(http, package):
    body = exact(package, decision="approve", reason="Owner reviewed this exact fixture contract.")
    path = f"/delivery-packages/{package['id']}/release-decision"
    response = http.post(path, json=body)
    assert response.status_code == 200, response.text
    assert http.post(path, json=body).json() == response.json()
    return response.json()["approval"]


def publish(http, package, approval):
    path = f"/delivery-packages/{package['id']}/release"
    body = exact(package, approval_id=approval["id"])
    result = http.post(path, json=body)
    assert result.status_code == 200, result.text
    assert http.post(path, json=body).json() == result.json()
    return result.json()


async def test_exact_release_and_filtered_client_files(http, company, requirement):
    project, package, invitation, client = await release_fixture(http, company, requirement)
    path = f"/delivery-packages/{package['id']}/release"
    assert http.post(path, json=exact(package, approval_id="missing")).status_code == 409
    approval = approve(http, package)
    assert (
        http.post(path, json={**exact(package, approval_id=approval["id"]), "version": 999}).status_code
        == 409
    )
    proof = publish(http, package, approval)
    assert http.patch(f"/records/{proof['release_id']}", json={"status": "withdrawn"}).status_code in {
        403,
        404,
        422,
    }
    owner_token = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    assert http.get(f"/delivery-packages/{package['id']}").status_code == 403
    assert http.get("/semantic-memory").status_code == 403
    view = http.get(f"/client/deliveries/{package['id']}")
    assert view.status_code == 200, view.text
    data = view.json()
    assert "reviews" not in data and "budget" not in data and "manifest" not in data
    assert len(data["files"]) == 2  # Approved requirement plus explicitly disclosed architecture.
    assert all(row["client_visible"] for row in data["files"])
    for file in package["manifest"]["files"]:
        result = http.get(f"/client/deliveries/{package['id']}/files/{file['id']}")
        assert result.status_code == (200 if file["client_visible"] else 404)
        if result.status_code == 200:
            assert "no-store" in result.headers["cache-control"]
    artifact_id = package["manifest"]["files"][-1].get("artifact_id", "missing")
    assert http.get(f"/artifacts/{artifact_id}").status_code == 404
    assert http.post(path, json=exact(package, approval_id=approval["id"])).status_code == 403
    http.headers["Authorization"] = owner_token
    withdraw = exact(package, reason="Owner withdrew this isolated fixture release.")
    result = http.post(f"/delivery-packages/{package['id']}/withdraw", json=withdraw)
    assert result.status_code == 200, result.text
    assert http.get(f"/projects/{project['id']}/delivery-state").json()["stage"] == "blocked"
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    assert http.get(f"/client/deliveries/{package['id']}").status_code == 404
    assert http.get("/client/deliveries").json() == []


@pytest.mark.parametrize(
    "fault",
    [
        "expired",
        "source",
        "revoked",
        "financial",
        "disabled_owner",
        "manifest",
        "file",
        "requirement",
        "stale",
    ],
)
async def test_release_revalidates_all_authority(http, company, requirement, fault):
    project, package, invitation, client = await release_fixture(http, company, requirement)
    approval = approve(http, package)
    if fault == "stale":
        newer = http.post(
            f"/projects/{project['id']}/delivery-packages",
            json={**package["input"], "request_id": str(uuid4())},
        )
        assert newer.status_code == 201, newer.text
    with company["factory"]() as session:
        if fault == "expired":
            session.get(m.Approval, approval["id"]).expires_at = now() - 1
        elif fault == "source":
            session.get(m.Project, project["id"]).version += 1
        elif fault == "revoked":
            session.get(m.ClientInvitation, invitation["invitation"]["id"]).revoked_at = now()
        elif fault == "financial":
            budget = session.scalar(select(m.Budget).where(m.Budget.scope == f"project:{project['id']}"))
            budget.reserved_micro = 1
        elif fault == "disabled_owner":
            session.get(m.User, company["owner"].id).enabled = False
        elif fault == "manifest":
            row = session.get(m.DeliveryPackage, package["id"])
            row.manifest = {**row.manifest, "version": 500}
            row.manifest_hash = digest(row.manifest)
        elif fault == "requirement":
            session.get(m.Requirement, requirement["id"]).text += " Changed without a revision"
        elif fault == "file":
            from company_os import packages

            packages.blob_path(package["org_id"], package["manifest"]["files"][0]["sha256"]).write_bytes(
                b"changed"
            )
        session.commit()
    result = http.post(
        f"/delivery-packages/{package['id']}/release", json=exact(package, approval_id=approval["id"])
    )
    assert result.status_code in {401, 409}, result.text
    with company["factory"]() as session:
        assert not session.scalar(
            select(m.BusinessRecord.id).where(m.BusinessRecord.kind == "delivery_release")
        )


async def test_fixture_cannot_release_and_concurrent_release_is_single(http, company, requirement):
    _, package, _, _ = await release_fixture(http, company, requirement, live_shape=False)
    assert (
        http.post(
            f"/delivery-packages/{package['id']}/release-decision",
            json=exact(package, decision="approve", reason="Fixture must remain blocked for clients."),
        ).status_code
        == 409
    )


async def test_concurrent_release_and_interrupted_response_recovery(http, company, requirement):
    _, package, _, _ = await release_fixture(http, company, requirement)
    approval = approve(http, package)
    body = exact(package, approval_id=approval["id"])
    path = f"/delivery-packages/{package['id']}/release"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: http.post(path, json=body), range(2)))
    assert [row.status_code for row in results] == [200, 200]
    assert results[0].json() == results[1].json()
    company["factory"].kw["bind"].dispose()
    assert http.post(path, json=body).json() == results[0].json()
    assert (
        http.post(path, json=exact(package, approval_id=approval["id"])).json()["release_id"]
        == results[0].json()["release_id"]
    )
    with company["factory"]() as session:
        assert (
            len(
                list(
                    session.scalars(
                        select(m.BusinessRecord).where(m.BusinessRecord.kind == "delivery_release")
                    )
                )
            )
            == 1
        )


@pytest.mark.parametrize("decision", ["reject", "request_changes"])
async def test_owner_reconsideration_updates_current_delivery_stage(http, company, requirement, decision):
    project, package, _, _ = await release_fixture(http, company, requirement)
    result = http.post(
        f"/delivery-packages/{package['id']}/release-decision",
        json=exact(package, decision=decision, reason="Owner requires a revised immutable delivery package."),
    )
    assert result.status_code == 200, result.text
    assert http.get(f"/projects/{project['id']}/delivery-state").json()["stage"] == "changes_requested"
    assert (
        http.post(
            f"/delivery-packages/{package['id']}/release-decision",
            json=exact(package, decision="approve", reason="Previous rejected version cannot be released."),
        ).status_code
        == 409
    )


async def test_invitation_expiry_revocation_and_project_isolation(http, company, requirement):
    project, package, invitation, client = await release_fixture(http, company, requirement)
    approval = approve(http, package)
    publish(http, package, approval)
    other_invitation, other = invite_client(http, project, "read-only-client@test", False)
    owner_token = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + other["access_token"]
    assert http.get("/client/projects").json()[0]["can_respond"] is False
    assert http.get(f"/client/deliveries/{package['id']}").status_code == 404  # Not an intended recipient.
    assert http.get("/state").status_code == 403
    http.headers["Authorization"] = owner_token
    revoke = {"request_id": str(uuid4()), "reason": "Access revoked after fixture verification."}
    result = http.post(f"/client-invitations/{invitation['invitation']['id']}/revoke", json=revoke)
    assert result.status_code == 200
    assert (
        http.post(f"/client-invitations/{invitation['invitation']['id']}/revoke", json=revoke).json()
        == result.json()
    )
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    assert http.get("/client/projects").json() == []
    assert http.get(f"/client/deliveries/{package['id']}").status_code == 404
    http.headers["Authorization"] = owner_token
    response = http.post(
        f"/projects/{project['id']}/client-invitations",
        json={"request_id": str(uuid4()), "email": "expired@test"},
    )
    with company["factory"]() as session:
        session.get(m.ClientInvitation, response.json()["invitation"]["id"]).expires_at = now() - 1
        session.commit()
    assert (
        http.post(
            "/auth/redeem-invitation",
            json={
                "token": response.json()["token"],
                "email": "expired@test",
                "password": "private-fixture-client-password",
            },
        ).status_code
        == 403
    )
