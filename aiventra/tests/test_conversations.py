import asyncio
from concurrent.futures import ThreadPoolExecutor

import jwt
import pytest
from company_os.config import settings
from company_os.conversations import CEOAnswer
from company_os.db import now, uid
from company_os.models import (
    AuthSession,
    Budget,
    Conversation,
    ConversationTurn,
    ModelConfig,
    ModelRun,
    Project,
    Requirement,
    User,
    Workflow,
)
from company_os.routes.conversations import TurnInput, events, send_turn
from company_os.security import token_for
from company_os.workflows import tick
from sqlalchemy import func, select
from starlette.requests import Request


def test_stream_authentication_rejects_tokens_without_expiry(http):
    original = http.headers["Authorization"].removeprefix("Bearer ")
    claims = jwt.decode(original, settings().jwt_secret, algorithms=["HS256"], audience="company-web")
    claims.pop("exp")
    http.headers["Authorization"] = "Bearer " + jwt.encode(claims, settings().jwt_secret, algorithm="HS256")
    assert http.get("/conversations").status_code == 401


def test_worker_admission_and_cancellation_share_lock_order(company):
    from scripts.verify_postgres import verify_chat_contention

    verify_chat_contention(company["factory"], company["owner"].id, company["client"].id)


def create(http, company, mode="live", **extra):
    response = http.post(
        "/conversations", json={"id": uid(), "client_id": company["client"].id, "mode": mode, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def send(http, conversation, **extra):
    response = http.post(
        f"/conversations/{conversation['id']}/turns",
        json={
            "request_id": uid(),
            "version": conversation["version"],
            "text": "Analyze this project before recommending implementation.",
            **extra,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_live_chat_waits_without_fabricated_answer_or_charge_and_cancels(http, company):
    conversation = create(http, company)
    turn = send(http, conversation)
    assert await tick(company["factory"])
    result = http.get(f"/conversations/{conversation['id']}").json()["turns"][0]
    assert result["workflow"]["status"] == "waiting_for_free_provider"
    assert not result["response"] and not result["runs"]
    with company["factory"]() as session:
        assert all(row.spent_micro == row.reserved_micro == 0 for row in session.scalars(select(Budget)))
    assert (
        http.post(f"/conversations/{conversation['id']}/turns/{turn['id']}/cancel").json()["workflow"][
            "status"
        ]
        == "cancelled"
    )
    assert not await tick(company["factory"])


async def test_fixture_answer_and_history_persist_across_sessions_and_are_idempotent(http, company):
    conversation = create(http, company, "mock")
    request_id = uid()
    turn = send(http, conversation, request_id=request_id)
    duplicate = send(http, conversation, request_id=request_id)
    assert duplicate["id"] == turn["id"]
    assert await tick(company["factory"])
    assert not await tick(company["factory"])
    result = http.get(f"/conversations/{conversation['id']}").json()
    assert result["turns"][0]["workflow"]["status"] == "completed"
    assert "Local fixture" in result["turns"][0]["response"]
    assert len(result["turns"][0]["runs"]) == 1
    assert http.get("/conversations").json()["items"][0]["id"] == conversation["id"]
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(ConversationTurn)) == 1
        assert session.get(Conversation, conversation["id"]).version == 2


def test_same_request_key_cannot_change_input_or_bypass_pending_turn(http, company):
    conversation = create(http, company)
    request_id = uid()
    send(http, conversation, request_id=request_id)
    path = f"/conversations/{conversation['id']}/turns"
    assert (
        http.post(
            path, json={"request_id": request_id, "version": 1, "text": "Different request"}
        ).status_code
        == 409
    )
    assert (
        http.post(
            path, json={"request_id": uid(), "version": 2, "text": "Another pending request"}
        ).status_code
        == 409
    )
    assert http.get(f"/conversations/{conversation['id']}").json()["conversation"]["version"] == 2


def test_concurrent_duplicate_dispatch_creates_one_turn_and_workflow(http, company):
    conversation = create(http, company)
    data = TurnInput(request_id=uid(), version=1, text="Concurrent duplicate question")

    def attempt(_):
        with company["factory"]() as session:
            return send_turn(conversation["id"], data, company["owner"], session)["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(attempt, range(2)))) == 1
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(ConversationTurn)) == 1
        assert session.scalar(select(func.count()).select_from(Workflow)) == 1


async def test_consultation_dispatch_links_existing_approval_flow_and_uploaded_evidence(http, company):
    conversation = create(http, company, "mock")
    upload = http.post(
        f"/conversations/{conversation['id']}/attachments",
        files={"file": ("brief.md", b"# Existing project\nPreserve current API contracts.")},
    )
    assert upload.status_code == 201 and "content" not in upload.json()
    send(http, conversation, intent="consult", attachment_ids=[upload.json()["id"]])
    for _ in range(8):
        assert await tick(company["factory"])
    result = http.get(f"/conversations/{conversation['id']}").json()["turns"][0]
    assert result["consultation"]["requirement"]["status"] == "awaiting_approval"
    assert len(result["consultation"]["proposals"]) == 1
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(Project)) == 0
        assert session.scalar(select(func.count()).select_from(Requirement)) == 1


@pytest.mark.parametrize(
    "name,content,status",
    [
        (".env", b"unsafe", 422),
        ("wallet-secret.txt", b"unsafe", 422),
        ("binary.txt", b"\xff\x00", 422),
        ("large.md", b"a" * 16385, 413),
    ],
)
def test_attachment_validation_rejects_unsafe_names_binary_and_oversize(http, company, name, content, status):
    conversation = create(http, company)
    assert (
        http.post(
            f"/conversations/{conversation['id']}/attachments", files={"file": (name, content)}
        ).status_code
        == status
    )


def test_cross_conversation_attachments_are_not_accepted(http, company):
    first, second = create(http, company), create(http, company)
    artifact = http.post(
        f"/conversations/{first['id']}/attachments", files={"file": ("notes.txt", b"Safe project context")}
    ).json()
    assert (
        http.post(
            f"/conversations/{second['id']}/turns",
            json={
                "request_id": uid(),
                "version": 1,
                "text": "Read context",
                "attachment_ids": [artifact["id"]],
            },
        ).status_code
        == 404
    )


def test_client_cannot_access_owner_conversation_or_its_artifact(http, company):
    conversation = create(http, company)
    artifact = http.post(
        f"/conversations/{conversation['id']}/attachments",
        files={"file": ("notes.txt", b"Owner-only context")},
    ).json()
    with company["factory"]() as session:
        client = User(
            org_id=company["org"].id,
            email="conversation-client@example.test",
            role="client",
            client_id=company["client"].id,
        )
        session.add(client)
        session.flush()
        token = token_for(client, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get(f"/conversations/{conversation['id']}").status_code == 403
    assert http.get(f"/artifacts/{artifact['id']}").status_code == 404


async def test_conversation_budget_blocks_paid_reservation_before_call(http, company):
    conversation = create(http, company, "mock", budget_micro=0)
    with company["factory"]() as session:
        for model in session.scalars(select(ModelConfig)):
            model.input_price_micro_per_million = model.output_price_micro_per_million = 1000000
        session.commit()
    send(http, conversation)
    assert await tick(company["factory"])
    result = http.get(f"/conversations/{conversation['id']}").json()["turns"][0]
    assert result["workflow"]["status"] == "needs_attention" and not result["response"]
    with company["factory"]() as session:
        assert not session.scalar(select(ModelRun))


async def test_cancellation_during_controlled_inference_does_not_publish_late_answer(
    http, company, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def controlled(*args, **kwargs):
        entered.set()
        await release.wait()
        return CEOAnswer(answer="Late controlled response")

    monkeypatch.setattr("company_os.conversations.execute", controlled)
    conversation = create(http, company, "mock")
    turn = send(http, conversation)
    pending = asyncio.create_task(tick(company["factory"]))
    await asyncio.wait_for(entered.wait(), 3)
    assert http.post(f"/conversations/{conversation['id']}/turns/{turn['id']}/cancel").status_code == 200
    release.set()
    await pending
    result = http.get(f"/conversations/{conversation['id']}").json()["turns"][0]
    assert result["workflow"]["status"] == "cancelled" and not result["response"]


async def test_event_stream_reads_fresh_database_state_and_stops_after_revocation(http, company):
    conversation = create(http, company)
    with company["factory"]() as session:
        auth = session.scalar(select(AuthSession))

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(
            {
                "type": "http",
                "method": "GET",
                "headers": [],
                "state": {"auth_session_id": auth.id, "auth_expires_at": now() + 3600},
            },
            receive,
        )
        response = events(conversation["id"], request, company["owner"], session)
        stream = response.body_iterator
        assert "event: snapshot" in await anext(stream)
        auth.revoked_at = now()
        session.commit()
        with pytest.raises(StopAsyncIteration):
            await anext(stream)
