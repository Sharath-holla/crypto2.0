import os
import sqlite3
import subprocess
import sys

from company_os.workflows import tick


async def project_fixture(http, company):
    for _ in range(7):
        await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    response = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": 1,
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_department_specialist_executes_scoped_artifact(http, company, requirement):
    project = await project_fixture(http, company)
    agent = next(row for row in http.get("/state").json()["agents"] if row["role"] == "HR Manager")
    response = http.post(
        f"/projects/{project['id']}/tasks",
        json={
            "agent_id": agent["id"],
            "objective": "Assess workforce capability gaps against this project plan",
            "acceptance": ["Recorded scope and artifact"],
            "mode": "mock",
        },
    )
    assert response.status_code == 201, response.text
    task = response.json()
    for _ in range(5):
        await tick(company["factory"])
    state = http.get("/state").json()
    completed = next(row for row in state["tasks"] if row["id"] == task["id"])
    assert completed["status"] == "completed"
    assert any(row["task_id"] == task["id"] and row["agent_id"] == agent["id"] for row in state["artifacts"])


async def test_project_memory_and_crm_are_actual_scoped_records(http, company, requirement):
    project = await project_fixture(http, company)
    created = http.post(
        "/records",
        json={
            "kind": "knowledge",
            "title": "Regression baseline",
            "project_id": project["id"],
            "data": {"body": "Use testnet and preserve baseline feature behavior"},
        },
    )
    assert created.status_code == 201
    result = http.get("/memory/search", params={"project_id": project["id"], "query": "testnet"})
    assert len(result.json()) == 1
    assert result.json()[0]["id"] == created.json()["id"]
    opportunity = http.post(
        "/records",
        json={
            "kind": "opportunity",
            "title": "New inbound request",
            "client_id": company["client"].id,
            "data": {"source": "owner-submitted"},
        },
    ).json()
    assert (
        http.patch(f"/records/{opportunity['id']}", json={"version": 1, "status": "qualified"}).status_code
        == 200
    )
    assert (
        http.patch(f"/records/{opportunity['id']}", json={"version": 1, "status": "won"}).status_code == 409
    )


def test_real_migrations_and_append_only_database_guard(company):
    path = company["root"] / "migrated.db"
    environment = dict(os.environ)
    environment["DATABASE_URL"] = "sqlite:///" + str(path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] >= 25
        connection.execute(
            "INSERT INTO organizations(id,created_at,name,paused,deployments_paused,version,audit_head) VALUES('org',1,'Test',0,1,1,'head')"
        )
        connection.execute(
            "INSERT INTO audit_events(id,org_id,created_at,actor,action,subject,authorization,detail,previous_hash,event_hash) VALUES('event','org',1,'owner','test','id','test','{}','previous','hash')"
        )
        connection.commit()
        try:
            connection.execute("UPDATE audit_events SET action='tampered'")
            raise AssertionError("Audit mutation was allowed")
        except sqlite3.IntegrityError as exc:
            assert "append only" in str(exc)
    finally:
        connection.close()
