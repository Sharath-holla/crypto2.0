"""Persisted package/worker/integrity tests. All model evidence here is deterministic."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os import models as m
from company_os import packages
from company_os.db import uid
from company_os.security import digest, token_for
from company_os.workflows import tick
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from test_delivery import ready_project, start

from tests.test_migration_upgrade import migrate


async def reviewed_project(http, company, requirement):
    project, evidence = await ready_project(http, company, requirement)
    review = start(http, project, evidence).json()["review"]
    for _ in range(5):
        assert await tick(company["factory"])
    return project, evidence, review


def package_input(evidence, review, complete=True):
    artifact_id = evidence["manifest"]["sources"][0]["artifact_id"]
    return {
        "request_id": str(uuid4()),
        "review_id": review["id"],
        "source_hash": evidence["source_hash"],
        "summary": "Explicit deterministic package fixture; no live software delivery.",
        "release_notes": "Controlled fixture documents for package integrity verification only.",
        "test_summary": "Five deterministic role reviews; no live model quality or deployment verified.",
        "limitations": ["Deterministic test fixture; never release to a client."],
        "documents": [
            {"purpose": purpose, "artifact_id": artifact_id, "client_visible": False}
            for purpose in packages.DOCUMENT_PURPOSES
        ]
        if complete
        else [],
    }


async def prepare_package(http, company, requirement, complete=True):
    project, evidence, review = await reviewed_project(http, company, requirement)
    body = package_input(evidence, review, complete)
    response = http.post(f"/projects/{project['id']}/delivery-packages", json=body)
    assert response.status_code == 201, response.text
    return project, evidence, review, body, response.json()


async def test_frozen_files_checkpoints_idempotency_and_new_versions(http, company, requirement):
    project, evidence, review, body, package = await prepare_package(http, company, requirement)
    path = f"/projects/{project['id']}/delivery-packages"
    assert http.post(path, json=body).json()["id"] == package["id"]
    assert (
        http.post(
            path, json={**body, "summary": "A different request cannot reuse the same UUID."}
        ).status_code
        == 409
    )
    assert http.post(path, json={**body, "request_id": str(uuid4())}).status_code == 409
    assert await tick(company["factory"])
    workflow_id = package["workflow"]["id"]
    assert http.post(f"/workflows/{workflow_id}/control", json={"action": "pause"}).status_code == 200
    assert not await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    assert http.post(f"/workflows/{workflow_id}/control", json={"action": "resume"}).status_code == 200
    assert await tick(company["factory"])
    saved = http.get(f"/delivery-packages/{package['id']}").json()
    assert saved["status"] == "package_ready" and saved["classification"] == "fixture_nonproduction"
    assert saved["integrity_valid"] and saved["workflow"]["step"] == 2
    assert saved["manifest_hash"] == digest(saved["manifest"])
    assert saved["manifest"]["deployment"] == {"status": "not_verified", "url": None}
    assert len(saved["manifest"]["reviews"]) == 5 and len(saved["manifest"]["files"]) == 10
    for file in saved["manifest"]["files"]:
        response = http.get(f"/delivery-packages/{package['id']}/files/{file['id']}")
        assert response.status_code == 200
        assert hashlib.sha256(response.content).hexdigest() == file["sha256"]
        assert "no-store" in response.headers["cache-control"]
    newer = http.post(path, json=package_input(evidence, review)).json()
    assert newer["version"] == 2 and newer["supersedes_id"] == saved["id"]
    assert http.get(f"/delivery-packages/{saved['id']}").json()["manifest_hash"] == saved["manifest_hash"]


async def test_missing_required_documents_are_persisted_blockers(http, company, requirement):
    _, _, _, _, package = await prepare_package(http, company, requirement, complete=False)
    for _ in range(2):
        await tick(company["factory"])
    saved = http.get(f"/delivery-packages/{package['id']}").json()
    assert saved["status"] == "package_blocked" and saved["integrity_valid"]
    assert len(saved["manifest"]["blockers"]) == 6
    assert saved["manifest"]["status_at_freeze"] == "package_blocked"


@pytest.mark.parametrize("fault", ["file", "manifest", "source", "review", "run"])
async def test_tamper_and_source_changes_are_rejected(http, company, requirement, fault):
    project, evidence, review, body, package = await prepare_package(http, company, requirement)
    for _ in range(2):
        await tick(company["factory"])
    with company["factory"]() as session:
        row = session.get(m.DeliveryPackage, package["id"])
        if fault == "file":
            packages.blob_path(row.org_id, row.manifest["files"][0]["sha256"]).write_bytes(b"replaced")
        elif fault == "manifest":
            # Disposable Base.create_all fixture lacks migration triggers. Real
            # migrated databases additionally reject this write at the DB boundary.
            row.manifest = {**row.manifest, "summary": "tampered"}
        elif fault == "source":
            artifact = session.get(m.Artifact, evidence["manifest"]["sources"][0]["artifact_id"])
            artifact.content += " Changed source"
        elif fault == "review":
            record = session.get(m.BusinessRecord, review["id"])
            record.data = {**record.data, "reviews": record.data["reviews"][:4]}
        else:
            record = session.get(m.BusinessRecord, review["id"])
            session.get(m.ModelRun, record.data["reviews"][0]["run_id"]).response = {"approved": True}
        session.commit()
        if fault in {"source", "review", "run"}:
            with pytest.raises(PermissionError):
                packages.integrity(session, row, current=True)
        else:
            with pytest.raises(PermissionError):
                packages.integrity(session, row)
    if fault in {"file", "manifest"}:
        assert not http.get(f"/delivery-packages/{package['id']}").json()["integrity_valid"]
        assert http.get(f"/delivery-packages/{package['id']}/files/0").status_code == 409
    else:
        assert (
            http.post(
                f"/projects/{project['id']}/delivery-packages", json={**body, "request_id": str(uuid4())}
            ).status_code
            == 409
        )


async def test_cancel_and_expired_worker_cannot_freeze(http, company, requirement):
    project, _, _, body, package = await prepare_package(http, company, requirement)
    assert await tick(company["factory"])
    assert http.post(f"/delivery-packages/{package['id']}/cancel").status_code == 200
    assert http.post(f"/delivery-packages/{package['id']}/cancel").status_code == 200
    company["factory"].kw["bind"].dispose()
    assert not await tick(company["factory"])
    saved = http.get(f"/delivery-packages/{package['id']}").json()
    assert saved["status"] == "cancelled" and saved["manifest"] == {} and saved["workflow"]["step"] == 1
    newer = http.post(
        f"/projects/{project['id']}/delivery-packages", json={**body, "request_id": str(uuid4())}
    )
    assert newer.status_code == 201 and newer.json()["version"] == 2


async def test_serialized_concurrent_preparation_and_owner_scope(http, company, requirement):
    project, evidence, review = await reviewed_project(http, company, requirement)
    path = f"/projects/{project['id']}/delivery-packages"
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: http.post(path, json=package_input(evidence, review)), range(2)))
    assert sorted(response.status_code for response in responses) == [201, 409]
    package = next(response.json() for response in responses if response.status_code == 201)
    with company["factory"]() as session:
        client = m.User(
            id=uid(),
            org_id=company["org"].id,
            role="client",
            email="package-client@test",
            client_id=company["client"].id,
        )
        session.add(client)
        session.flush()
        token = token_for(client, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get(path).status_code == 403
    assert http.get(f"/delivery-packages/{package['id']}").status_code == 403
    assert http.get(f"/delivery-packages/{package['id']}/files/0").status_code == 403


def test_content_addressed_storage_rejects_links_paths_and_overwrite(company):
    org_id = company["org"].id
    content_hash, _ = packages.store_blob(org_id, "Harmless immutable text")
    assert packages.store_blob(org_id, "Harmless immutable text")[0] == content_hash
    with pytest.raises(PermissionError):
        packages.blob_path(org_id, "../outside")
    with pytest.raises(PermissionError):
        packages.blob_path("../../outside", content_hash)
    packages.blob_path(org_id, content_hash).write_text("tampered", encoding="utf-8")
    with pytest.raises(PermissionError):
        packages.store_blob(org_id, "Harmless immutable text")


async def test_additive_migration_retains_records_and_db_freezes_finalized_versions(
    http, company, requirement
):
    # Only this disposable Base.create_all fixture is reduced to its previous
    # schema. No private application data or existing delivery row is removed.
    engine = company["factory"].kw["bind"]
    with engine.begin() as connection:
        m.DeliveryResponse.__table__.drop(connection)
        m.ClientAccessGrant.__table__.drop(connection)
        m.ClientInvitation.__table__.drop(connection)
        m.DeliveryPackage.__table__.drop(connection)
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('a31d07edc482')"))
    migrate(company["root"] / "test.db", "head")
    with company["factory"]() as session:
        assert session.get(m.Requirement, requirement["id"]).text == requirement["text"]
        assert session.get(m.User, company["owner"].id).email == company["owner"].email
    _, _, _, _, package = await prepare_package(http, company, requirement)
    for _ in range(2):
        await tick(company["factory"])
    with company["factory"]() as session:
        for column, value in [
            ("manifest_hash", "0" * 64),
            ("manifest", {"tampered": True}),
            ("input", {}),
            ("finalized_at", None),
            ("client_id", "changed"),
        ]:
            with pytest.raises(IntegrityError, match="immutable"):
                session.execute(
                    update(m.DeliveryPackage)
                    .where(m.DeliveryPackage.id == package["id"])
                    .values(**{column: value})
                )
                session.commit()
            session.rollback()
        with pytest.raises(IntegrityError, match="retained"):
            session.execute(text("DELETE FROM delivery_packages WHERE id=:id"), {"id": package["id"]})
            session.commit()
        session.rollback()
        session.execute(
            update(m.DeliveryPackage).where(m.DeliveryPackage.id == package["id"]).values(status="withdrawn")
        )
        session.commit()
        assert packages.integrity(session, session.get(m.DeliveryPackage, package["id"]))


async def test_source_patch_receipt_and_saved_pr_reference_serialization(
    http, company, requirement, monkeypatch
):
    # Narrow serialization fixture, not live review/Git/Docker evidence.
    project, evidence, _, _, saved = await prepare_package(http, company, requirement)
    with company["factory"]() as session:
        package = session.get(m.DeliveryPackage, saved["id"])
        qa = session.scalar(select(m.Agent).where(m.Agent.role == "QA Director"))
        task = m.Task(
            id=uid(),
            org_id=package.org_id,
            project_id=project["id"],
            assigned_agent_id=qa.id,
            objective="Controlled source receipt serialization fixture",
            kind="coding",
            status="completed",
            payload={"repository_id": "fixture", "test_suite": "python-unittest"},
        )
        session.add(task)
        session.flush()
        execution = m.Execution(
            id=uid(),
            org_id=package.org_id,
            task_id=task.id,
            agent_id=qa.id,
            workspace="fixture metadata only",
            command=["fixture"],
            environment="controlled test fixture",
            status="completed",
            exit_code=0,
        )
        session.add(execution)
        session.flush()
        task.evidence = {
            "pull_request": {"head_commit": "a" * 40},
            "candidate_tree": "b" * 40,
            "execution_id": execution.id,
            "build_exit_code": 0,
        }
        publication = m.BusinessRecord(
            id=uid(),
            org_id=package.org_id,
            project_id=project["id"],
            kind="github_publication",
            title="Controlled protocol fixture",
            status="published",
            data={
                "manifest": {"task_id": task.id, "head_commit": "c" * 40},
                "manifest_hash": "d" * 64,
                "number": 7,
                "url": "https://github.com/fixture-owner/fixture-repo/pull/7",
            },
        )
        session.add(publication)
        session.flush()
        source = {
            **evidence["manifest"],
            "tasks": [*evidence["manifest"]["tasks"], {"id": task.id, "kind": "coding"}],
            "sources": [
                *evidence["manifest"]["sources"],
                {"task_id": task.id, "diff": "Explicit harmless patch fixture\n"},
            ],
        }
        monkeypatch.setattr(packages, "review_evidence", lambda *args: source)
        package.source_hash = digest(source)
        package.input = {**package.input, "include_source_patches": True}
        manifest = packages.assemble(session, package)
        assert manifest["repositories"][0]["source_commit"] == "a" * 40
        assert manifest["repositories"][0]["pull_requests"][0]["pull_request"]["number"] == 7
        assert manifest["repositories"][0]["pull_requests"][0]["pull_request"]["remote_commit"] == "c" * 40
        assert manifest["build_artifacts"][0]["deployable_binary_exported"] is False
        assert manifest["build_artifacts"][0]["source_commit"] == "a" * 40
        patch = next(row for row in manifest["files"] if row["purpose"] == "source_patch")
        assert packages.read_blob(package, patch) == b"Explicit harmless patch fixture\n"
        assert patch["client_visible"] and not manifest["blockers"]
