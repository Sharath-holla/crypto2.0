import math
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os import models as m
from company_os.config import settings
from company_os.db import uid
from company_os.embeddings import EmbeddingUnavailable, embed, fingerprint
from company_os.organization import agent_for
from company_os.semantic_memory import automatic_context, backfill, index_pending, put, search
from company_os.workflows import tick
from sqlalchemy import select


async def approved_project(http, company):
    response = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Memory test fixture",
            "text": "Document payment recovery requirements and architecture for this test fixture.",
            "mode": "mock",
        },
    )
    assert response.status_code == 201
    for _ in range(32):
        await tick(company["factory"])
        with company["factory"]() as session:
            if session.scalar(select(m.Proposal).where(m.Proposal.requirement_id == response.json()["id"])):
                break
    proposal = next(
        p for p in http.get("/state").json()["proposals"] if p["requirement_id"] == response.json()["id"]
    )
    result = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": proposal["version"],
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert result.status_code == 200
    return result.json()


@pytest.fixture
def test_embeddings(monkeypatch):
    monkeypatch.setattr(settings(), "embedding_provider", "deterministic_test")
    monkeypatch.setattr(settings(), "app_env", "test")


async def test_version_history_scope_index_and_purge(http, company, test_embeddings):
    project = await approved_project(http, company)
    body = {
        "title": "Payment architecture",
        "content": "Retry payment transactions after gateway timeout",
        "kind": "architecture_decision",
        "project_id": project["id"],
        "visibility": "project",
    }
    created = http.post("/semantic-memory", json=body)
    assert created.status_code == 201, created.text
    entry = created.json()
    index = http.post("/semantic-memory/index", json={})
    assert index.status_code == 200
    result = http.get(
        "/semantic-memory", params={"project_id": project["id"], "query": "payment timeout"}
    ).json()
    # Fixture embeddings are visibly labeled; this is not real semantic-model evidence.
    assert result["mode"] == "deterministic_test"
    assert result["results"][0]["id"] == entry["id"]
    updated = http.patch(
        f"/semantic-memory/{entry['id']}",
        json={**body, "version": 1, "content": "Resolved duplicate payments using idempotency keys"},
    )
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert http.patch(f"/semantic-memory/{entry['id']}", json={**body, "version": 1}).status_code == 409
    versions = http.get(f"/semantic-memory/{entry['id']}/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    assert versions[1]["content"] == body["content"]
    assert versions[0]["provenance"]["source_key"] == entry["source_key"]
    assert http.post(f"/semantic-memory/{entry['id']}/delete", json={"version": 2}).status_code == 200
    with company["factory"]() as session:
        backfill(session, company["org"].id)
        assert session.get(m.MemoryEntry, entry["id"]).deleted
        assert not session.scalar(select(m.MemoryVersion).where(m.MemoryVersion.entry_id == entry["id"]))
        assert not session.scalar(select(m.MemoryChunk).where(m.MemoryChunk.entry_id == entry["id"]))


async def test_permissions_filtered_before_ranking_and_context(http, company, test_embeddings):
    first = await approved_project(http, company)
    second = await approved_project(http, company)
    with company["factory"]() as session:
        agent = agent_for(session, company["org"].id, "CTO")
        peer = agent_for(session, company["org"].id, "CFO")
        project = session.get(m.Project, first["id"])
        visible = put(
            session,
            agent.org_id,
            "manual:visible",
            "Shared evidence",
            "knowledge",
            "recovery approved",
            project_id=project.id,
            visibility="project",
        )
        allowed_id = visible.id
        private = put(
            session,
            agent.org_id,
            "manual:private",
            "CFO private",
            "working_memory",
            "recovery secret",
            project_id=project.id,
            agent_id=peer.id,
            visibility="agent",
        )
        selected = put(
            session,
            agent.org_id,
            "manual:selected",
            "Selected CTO",
            "knowledge",
            "recovery plan",
            project_id=project.id,
            visibility="selected",
            grant_ids=[agent.id],
        )
        selected_id = selected.id
        put(
            session,
            agent.org_id,
            "manual:foreign-project",
            "Other project",
            "knowledge",
            "recovery",
            project_id=second["id"],
            visibility="project",
        )
        session.add(m.Organization(id=uid(), name="Other tenant"))
        session.flush()
        foreign_org = session.scalar(select(m.Organization).where(m.Organization.name == "Other tenant"))
        put(
            session,
            foreign_org.id,
            "manual:foreign-tenant",
            "Foreign tenant",
            "knowledge",
            "recovery",
            visibility="organization",
        )
        session.commit()
        for _ in range(10):
            index_pending(session, limit=32)
        results = search(session, agent.org_id, "recovery", project_id=project.id, agent=agent, limit=100)[
            "results"
        ]
        result_ids = {r["id"] for r in results}
        assert allowed_id in result_ids and selected_id in result_ids and private.id not in result_ids
        assert not any(r["title"] in {"Other project", "Foreign tenant"} for r in results)
        put(
            session,
            agent.org_id,
            "manual:selected",
            "Selected CTO",
            "knowledge",
            "recovery plan",
            project_id=project.id,
            visibility="selected",
            grant_ids=[peer.id],
        )
        session.commit()
        assert selected_id not in {
            r["id"]
            for r in search(session, agent.org_id, "recovery", project_id=project.id, agent=agent)["results"]
        }
        task = session.scalar(
            select(m.Task).where(m.Task.project_id == project.id, m.Task.assigned_agent_id == agent.id)
        )
        workflow = session.scalar(select(m.Workflow).where(m.Workflow.task_id == task.id))
        assert workflow
        context = automatic_context(session, workflow, agent, project, "recovery")
        assert allowed_id in {r["id"] for r in context["results"]}
        assert (
            automatic_context(session, workflow, agent, project, "recovery", char_budget=0)["results"] == []
        )


def test_source_capture_versions_and_durable_sessions(http, company, test_embeddings):
    record = http.post(
        "/records",
        json={
            "kind": "knowledge",
            "title": "Organization policy",
            "data": {"body": "Recover from errors safely"},
        },
    ).json()
    with company["factory"]() as session:
        entry = session.scalar(
            select(m.MemoryEntry).where(m.MemoryEntry.source_key == "business_records:" + record["id"])
        )
        assert entry and entry.visibility == "organization"
        entry_id = entry.id
        index_pending(session)
    assert (
        http.patch(f"/records/{record['id']}", json={"version": 1, "status": "resolved"}).status_code == 200
    )
    with company["factory"]() as session:
        entry = session.get(m.MemoryEntry, entry_id)
        assert entry.version == 2
        index_pending(session)
    with company["factory"]() as restarted:
        result = search(restarted, company["org"].id, "Recover")
        assert result["results"][0]["id"] == entry_id
        assert result["results"][0]["version"] == 2
        assert result["results"][0]["provenance"]["provenance"]["source_id"] == record["id"]


def test_missing_local_model_falls_back_without_paid_calls(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "embedding_provider", "disabled")
    record = http.post(
        "/semantic-memory",
        json={"title": "Recovery notes", "content": "Restart worker safely", "visibility": "organization"},
    )
    assert record.status_code == 201
    response = http.post("/semantic-memory/index", json={})
    assert response.status_code == 200 and response.json()["indexed"] == 0
    data = http.get("/semantic-memory", params={"query": "worker"}).json()
    assert data["mode"] == "keyword" and data["results"][0]["id"] == record.json()["id"]
    with company["factory"]() as session:
        assert not session.scalar(select(m.ModelRun))
        assert session.get(m.MemoryEntry, record.json()["id"]).index_status == "waiting_for_local_model"


def test_embedding_validation_and_test_adapter_production_rejection(monkeypatch):
    monkeypatch.setattr(settings(), "embedding_provider", "deterministic_test")
    monkeypatch.setattr(settings(), "app_env", "production")
    with pytest.raises(EmbeddingUnavailable):
        embed(["This must not become a fake live embedding"])
    monkeypatch.setattr(settings(), "app_env", "test")
    result = embed(["Deterministic adapter test"])[0]
    assert len(result) == 384 and math.isclose(sum(n * n for n in result), 1)
    before = fingerprint()
    monkeypatch.setattr(settings(), "embedding_model", "different model")
    assert fingerprint() != before


def test_concurrent_memory_revisions_preserve_history(company):
    with company["factory"]() as session:
        entry = put(
            session,
            company["org"].id,
            "manual:concurrent",
            "Concurrent notes",
            "knowledge",
            "initial",
            visibility="organization",
        )
        entry_id = entry.id
        session.commit()

    def revise(text):
        with company["factory"]() as session:
            put(
                session,
                company["org"].id,
                "manual:concurrent",
                "Concurrent notes",
                "knowledge",
                text,
                visibility="organization",
            )
            session.commit()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(revise, ["revision A", "revision B"]))
    with company["factory"]() as session:
        assert session.get(m.MemoryEntry, entry_id).version == 3
        assert (
            len(list(session.scalars(select(m.MemoryVersion).where(m.MemoryVersion.entry_id == entry_id))))
            == 3
        )


def test_recovery_digest_accepts_pgvector_list_and_array():
    from array import array

    from scripts.verify_semantic_memory import row_payload

    vector = [1.0] + [0.0] * 383
    row = m.MemoryChunk(embedding=vector)
    expected = row_payload(row)
    row.embedding = array("f", vector)
    assert row_payload(row) == expected
    assert expected["embedding"] == vector


def test_foreign_memory_apis_reject_access(http):
    assert http.get(f"/semantic-memory/{uuid4()}/versions").status_code == 404
    assert (
        http.post(
            "/semantic-memory",
            json={
                "title": "bad",
                "content": "unauthorized grant",
                "visibility": "selected",
                "grant_ids": [str(uuid4())],
            },
        ).status_code
        == 404
    )
