from uuid import uuid4

from company_os import models as m
from company_os.security import audit

from tests.test_conversations import create
from tests.test_staffing import project_plan


async def test_project_history_stable_cursor_new_events_and_restart(http, company, requirement):
    project, _ = await project_plan(http, company, requirement)
    with company["factory"]() as session:
        for i in range(57):
            audit(
                session,
                company["org"].id,
                company["owner"].id,
                "fixture.history",
                str(i),
                {"fixture": True},
                project_id=project["id"],
            )
        session.commit()
    path = f"/projects/{project['id']}/history"
    first = http.get(path).json()
    assert len(first["items"]) == 20 and first["next_cursor"]
    assert [r["detail"]["_history_position"] for r in first["items"]] == sorted(
        [r["detail"]["_history_position"] for r in first["items"]], reverse=True
    )
    with company["factory"]() as session:
        audit(
            session,
            company["org"].id,
            company["owner"].id,
            "fixture.concurrent_new",
            "new",
            {},
            project_id=project["id"],
        )
        session.commit()
    company["factory"].kw["bind"].dispose()
    seen = {r["id"] for r in first["items"]}
    cursor = first["next_cursor"]
    while cursor:
        page = http.get(path, params={"before": cursor}).json()
        assert not seen.intersection(r["id"] for r in page["items"])
        assert not any(r["action"] == "fixture.concurrent_new" for r in page["items"])
        seen.update(r["id"] for r in page["items"])
        cursor = page["next_cursor"]
    assert len(seen) >= 57
    assert http.get(path, params={"before": first["next_cursor"] + "bad"}).status_code == 422
    assert http.get(path, params={"limit": 51}).status_code == 422
    assert http.get("/projects/foreign/history").status_code == 404
    assert http.get("/state").json()["runtime"]["history_limit"] == 30
    assert len(http.get("/state", params={"history_limit": 5}).json()["audit"]) <= 5
    with company["factory"]() as session:
        from sqlalchemy import select

        task = session.scalar(select(m.Task).where(m.Task.project_id == project["id"]))
        task_id = task.id
        for index in range(25):
            audit(
                session,
                company["org"].id,
                company["owner"].id,
                "fixture.task_history",
                task_id,
                {"index": index},
                project_id=project["id"],
                task_id=task_id,
            )
        session.commit()
    task_page = http.get(f"/tasks/{task_id}/history").json()
    assert len(task_page["items"]) == 20 and all(row["task_id"] == task_id for row in task_page["items"])
    assert http.get(f"/tasks/{task_id}/history", params={"before": first["next_cursor"]}).status_code == 422
    assert http.get("/tasks/foreign/history").status_code == 404


def test_conversation_list_cursor_survives_cursor_record_activity(http, company):
    with company["factory"]() as session:
        for index in range(54):
            session.add(
                m.Conversation(
                    org_id=company["org"].id,
                    owner_id=company["owner"].id,
                    client_id=company["client"].id,
                    title=f"fixture history {index}",
                    updated_at=100 + index,
                )
            )
        session.commit()
    first = http.get("/conversations").json()
    assert len(first["items"]) == 50 and first["next_cursor"]
    with company["factory"]() as session:
        session.get(m.Conversation, first["items"][-1]["id"]).updated_at = 9999
        session.commit()
    older = http.get("/conversations", params={"before": first["next_cursor"]}).json()
    assert len(older["items"]) == 4
    assert not {row["id"] for row in first["items"]}.intersection(row["id"] for row in older["items"])
    assert (
        http.get("/conversations", params={"before": first["next_cursor"], "search": "different"}).status_code
        == 422
    )


def test_chat_history_pages_references_isolation_and_new_turns(http, company):
    row = create(http, company)
    other = create(http, company)
    with company["factory"]() as session:
        for position in range(1, 44):
            session.add(
                m.ConversationTurn(
                    org_id=company["org"].id,
                    conversation_id=row["id"],
                    request_id=str(uuid4()),
                    request_hash="fixture",
                    position=position,
                    content=f"fixture question {position}",
                    response=f"fixture response {position}",
                )
            )
        session.commit()
    path = f"/conversations/{row['id']}"
    first = http.get(path).json()
    assert [r["position"] for r in first["turns"]] == list(range(24, 44)) and first["total_turns"] == 43
    with company["factory"]() as session:
        session.add(
            m.ConversationTurn(
                org_id=company["org"].id,
                conversation_id=row["id"],
                request_id=str(uuid4()),
                request_hash="fixture",
                position=44,
                content="fixture new turn",
            )
        )
        session.commit()
    company["factory"].kw["bind"].dispose()
    second = http.get(path + "/history", params={"before": first["next_cursor"]}).json()
    last = http.get(path + "/history", params={"before": second["next_cursor"]}).json()
    assert [r["position"] for r in last["turns"] + second["turns"] + first["turns"]] == list(range(1, 44))
    assert last["next_cursor"] is None
    assert not http.get(f"/conversations/{other['id']}/history?before=24").json()["turns"]
    assert http.get("/conversations/foreign/history?before=24").status_code == 404
    assert http.get(path + "/history?before=0").status_code == 422
