import base64
import json
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from company_os import models as m
from company_os.agent_runtime import transition
from company_os.config import settings
from company_os.credentials import VaultUnavailable, save_secret, secret_for
from company_os.db import uid
from company_os.gateway import execute
from company_os.organization import agent_for
from company_os.provider_catalog import discover
from company_os.providers import HTTPAdapter, ProviderError, ProviderUnavailable, Response
from company_os.schemas import DocumentResult
from company_os.workflows import tick
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("contract_inference")


def live_model(session, company, kind="openai"):
    provider = m.Provider(
        id=uid(),
        org_id=company["org"].id,
        name="Controlled contract only",
        kind=kind,
        base_url="https://api.openai.com/v1",
        credential_env="AGENT_CONTRACT_API_KEY",
    )
    session.add(provider)
    session.flush()
    model = m.ModelConfig(
        id=uid(),
        org_id=provider.org_id,
        provider_id=provider.id,
        identifier="controlled-model",
        capabilities=["structured", "reasoning", "coding"],
        quality=95,
        sensitivity="confidential",
        input_price_micro_per_million=1000000,
        output_price_micro_per_million=1000000,
        price_source="https://example.test/contract",
    )
    session.add(model)
    session.commit()
    return provider, model


async def approved_project(http, company, requirement):
    for _ in range(7):
        await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    response = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": proposal["version"],
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    )
    assert response.status_code == 200, response.text
    for _ in range(30):
        if not await tick(company["factory"]):
            break
    return response.json()


def test_encrypted_credentials_rotation_isolation_and_no_readback(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"v" * 32).decode())
    with company["factory"]() as session:
        provider, model = live_model(session, company)
    provider_id = provider.id
    key = "controlled-provider-secret-never-display"
    response = http.post(f"/providers/{provider_id}/credentials", json={"secret": key})
    assert response.status_code == 200 and response.json()["credential_source"] == "vault"
    with company["factory"]() as session:
        provider = session.get(m.Provider, provider_id)
        assert secret_for(provider) == key
        record = session.scalar(select(m.ProviderCredential))
        ciphertext, version = record.ciphertext, record.version
        assert key not in ciphertext
        other = m.Provider(
            id=uid(),
            org_id=provider.org_id,
            name="Other",
            kind="openai",
            base_url=provider.base_url,
            credential_env="OTHER_API_KEY",
        )
        session.add(other)
        session.flush()
        copied = m.ProviderCredential(
            org_id=provider.org_id, provider_id=other.id, ciphertext=ciphertext, version=version
        )
        session.add(copied)
        session.flush()
        with pytest.raises(VaultUnavailable):
            secret_for(other)
        session.rollback()
    assert key not in json.dumps(http.get("/state").json())
    assert ciphertext not in json.dumps(http.get("/state").json())
    assert (
        http.post(f"/providers/{provider_id}/credentials", json={"secret": key + "-rotated"}).status_code
        == 200
    )
    with company["factory"]() as session:
        record = session.scalar(select(m.ProviderCredential))
        assert record.version == 2 and record.ciphertext != ciphertext
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-environment-fallback")
    response = http.post(f"/providers/{provider_id}/credentials/revoke")
    assert response.json()["credential_source"] == "environment"
    monkeypatch.setattr(settings(), "provider_secret_key", "")
    assert http.post(f"/providers/{provider_id}/credentials", json={"secret": key}).status_code == 409
    assert key not in http.post(f"/providers/{provider_id}/credentials", json={"secret": "bad key"}).text


@pytest.mark.parametrize(
    "kind,path,header",
    [
        ("openai", "/v1/models", "authorization"),
        ("anthropic", "/v1/models", "x-api-key"),
        ("gemini", "/v1/models", "x-goog-api-key"),
        ("ollama", "/v1/api/tags", None),
        ("xai", "/v1/models", "authorization"),
        ("compatible", "/v1/models", "authorization"),
    ],
)
async def test_catalog_contracts_use_account_ids_and_bound_pagination(
    company, monkeypatch, kind, path, header
):
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "catalog-contract-secret")
    calls = []

    def transport(request):
        calls.append(request)
        assert request.url.path == path
        assert "catalog-contract-secret" not in str(request.url)
        if header:
            assert "catalog-contract-secret" in request.headers[header]
        if kind == "gemini":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {"name": "models/account-model", "supportedGenerationMethods": ["generateContent"]}
                    ],
                    **({"nextPageToken": "page2"} if len(calls) == 1 else {}),
                },
            )
        if kind == "anthropic":
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "account-model"}],
                    "has_more": len(calls) == 1,
                    "last_id": "account-model",
                },
            )
        if kind == "ollama":
            return httpx.Response(200, json={"models": [{"name": "local-installed-model:tag"}]})
        return httpx.Response(200, json={"data": [{"id": "account-model"}]})

    with company["factory"]() as session:
        provider, _ = live_model(session, company, kind)
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            catalog = await discover(provider, client)
    assert catalog[0]["identifier"] == ("local-installed-model:tag" if kind == "ollama" else "account-model")
    assert len(calls) == (2 if kind in {"anthropic", "gemini"} else 1)
    assert "capabilities" not in catalog[0] and "quality" not in catalog[0]
    if len(calls) == 2:
        assert calls[1].url.params.get("pageToken" if kind == "gemini" else "after_id")


async def test_xai_inference_contract_redacts_vault_secret(company, monkeypatch):
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"x" * 32).decode())
    key = "opaque-xai-contract-credential"

    def transport(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {key}"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": json.dumps({"content": key})}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )

    with company["factory"]() as session:
        provider, model = live_model(session, company, "xai")
        save_secret(session, provider, key)
        session.commit()
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            result = await HTTPAdapter(client).request(
                provider, model, "system", "prompt", {"type": "object"}
            )
        assert result.data["content"] == "[REDACTED]" and result.input_tokens == 5


async def test_message_is_durable_idempotent_acknowledged_only_after_execution(http, company, requirement):
    project = await approved_project(http, company, requirement)
    agents = http.get("/state").json()["agents"]
    sender = next(a for a in agents if a["role"] == "CTO")
    recipient = next(a for a in agents if a["role"] == "Business Analyst")
    payload = {
        "request_id": uid(),
        "project_id": project["id"],
        "sender_id": sender["id"],
        "recipient_id": recipient["id"],
        "body": "Assess project acceptance evidence and missing constraints",
        "mode": "mock",
    }
    queued = http.post("/agent-messages", json=payload)
    assert queued.status_code == 201, queued.text
    work = queued.json()["work"]
    assert http.post("/agent-messages", json=payload).json()["work"]["id"] == work["id"]
    assert (
        http.post("/agent-messages", json={**payload, "body": "A different task objective"}).status_code
        == 409
    )
    assert http.post(f"/messages/{work['subject_id']}/ack").status_code == 409
    assert await tick(company["factory"])
    # The dashboard defaults to the latest 30 events across all workflows.
    # Requirement/project setup can exceed that window, including same-second events.
    state = http.get("/state", params={"history_limit": 300}).json()
    workflow = next(w for w in state["workflows"] if w["id"] == work["workflow_id"])
    assert workflow["status"] == "completed" and workflow["step"] == 1
    message = next(row for row in state["messages"] if row["id"] == work["subject_id"])
    assert message["status"] == "acknowledged" and message["acknowledged_at"]
    completed = next(row for row in state["agent_work"] if row["id"] == work["id"])
    assert (
        next(a for a in state["artifacts"] if a["id"] == completed["result"]["artifact_id"])["project_id"]
        == project["id"]
    )
    events = [
        row["state"]
        for row in sorted(state["agent_state_events"], key=lambda e: e["sequence"])
        if row["execution_id"]
        == next(e["id"] for e in state["agent_executions"] if e["workflow_id"] == workflow["id"])
    ]
    assert events == ["REGISTERED", "ASSIGNED", "RUNNING", "COMPLETED"]
    with company["factory"]() as session:
        execution_id = next(e["id"] for e in state["agent_executions"] if e["workflow_id"] == workflow["id"])
        persisted = session.scalars(
            select(m.AgentStateEvent)
            .where(m.AgentStateEvent.execution_id == execution_id)
            .order_by(m.AgentStateEvent.sequence)
        ).all()
        assert [row.state for row in persisted] == events
        assert [row.sequence for row in persisted] == [1, 2, 3, 4]
    assert not await tick(company["factory"])  # Completion messages do not recursively spawn work.


async def test_meeting_first_round_is_independent_and_second_round_is_bounded(
    http, company, requirement, monkeypatch
):
    project = await approved_project(http, company, requirement)
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-meeting-secret")
    with company["factory"]() as session:
        _, model = live_model(session, company)
        participants = [
            agent_for(session, company["org"].id, role).id for role in ["CTO", "Business Analyst"]
        ]
    captured = []

    async def contract(_self, _provider, _model, _system, prompt, schema, *_args):
        context = json.loads(prompt)
        captured.append(context)
        if "contributions" in context:
            return Response(
                {
                    "summary": "Controlled synthesis contract",
                    "decisions": ["Assess acceptance evidence"],
                    "unresolved": ["No real inference in this test"],
                    "followups": [
                        {
                            "agent_id": participants[1],
                            "objective": "Document unresolved project acceptance evidence",
                        }
                    ],
                },
                10,
                10,
            )
        if "role" in context:
            return Response(
                {
                    "summary": "Controlled specialist contribution",
                    "evidence": [],
                    "risks": [],
                    "alternatives": [],
                    "actions": [],
                },
                10,
                10,
            )
        return Response(
            {
                "title": "Follow-up",
                "content": "Controlled document output",
                "acceptance_checks": ["Controlled test evidence"],
            },
            10,
            10,
        )

    monkeypatch.setattr(HTTPAdapter, "request", contract)
    payload = {
        "request_id": uid(),
        "project_id": project["id"],
        "participant_ids": participants,
        "agenda": "Discuss risks and produce read-only follow-up evidence",
        "rounds": 2,
        "create_followups": True,
        "model_override": model.id,
        "budget_micro": 500000,
    }
    response = http.post("/agent-meetings", json=payload)
    assert response.status_code == 201, response.text
    assert http.post("/agent-meetings", json=payload).json()["work"]["id"] == payload["request_id"]
    for _ in range(5):
        assert await tick(company["factory"])
    assert len(captured) == 5
    assert all("prior_round" not in context for context in captured[:2])
    assert captured[0]["memory"] == captured[1]["memory"]
    assert all(len(context["prior_round"]) == 2 for context in captured[2:4])
    state = http.get("/state").json()
    work = next(w for w in state["agent_work"] if w["id"] == payload["request_id"])
    assert len(work["result"]["task_ids"]) == 1
    assert await tick(company["factory"])
    with company["factory"]() as session:
        budget = session.scalar(select(m.Budget).where(m.Budget.scope == f"job:{work['id']}"))
        runs = session.scalars(
            select(m.ModelRun).where(m.ModelRun.project_id == project["id"], m.ModelRun.cost_micro > 0)
        ).all()
        assert (
            len(runs) == 6
            and budget.spent_micro == sum(r.cost_micro for r in runs)
            and budget.reserved_micro == 0
        )
    assert not await tick(company["factory"])


async def test_missing_provider_wait_records_runtime_and_probe_never_falls_back(http, company, monkeypatch):
    monkeypatch.delenv("AGENT_CONTRACT_API_KEY", raising=False)
    with company["factory"]() as session:
        provider, model = live_model(session, company)
    payload = {"request_id": uid(), "model_id": model.id}
    response = http.post(f"/providers/{provider.id}/inference-probe", json=payload)
    assert response.status_code == 201, response.text
    assert http.post(f"/providers/{provider.id}/inference-probe", json=payload).status_code == 201
    assert await tick(company["factory"])
    state = http.get("/state").json()
    workflow = next(w for w in state["workflows"] if w["id"] == response.json()["workflow"]["id"])
    assert workflow["status"] == "waiting_for_free_provider" and workflow["attempts"] == 0
    assert not state["runs"] and not state["provider_probes"]
    runtime = next(
        r for r in state["agent_runtime"] if r["agent_id"] == response.json()["work"]["participants"][0]
    )
    assert runtime["state"] == "WAITING_FOR_FREE_PROVIDER"
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-probe-test")
    calls = []

    async def contract(_self, _provider, selected, *_args):
        calls.append(selected.id)
        return Response({"value": "aiventra_probe_ok"}, 5, 5)

    monkeypatch.setattr(HTTPAdapter, "request", contract)
    assert http.post(f"/workflows/{workflow['id']}/resume-free").status_code == 200
    assert await tick(company["factory"])
    state = http.get("/state").json()
    assert calls == [model.id] and state["provider_probes"][0]["inference_model_id"] == model.id
    assert (
        state["provider_probes"][0]["status"] == "unverified"
    )  # Inference does not claim catalog verification.


async def test_policy_preferences_cannot_bypass_quality_and_scoped_allowlists(http, company, monkeypatch):
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-routing-test")
    with company["factory"]() as session:
        _, model = live_model(session, company)
        agent = agent_for(session, company["org"].id, "CEO")
        low = m.ModelConfig(
            org_id=model.org_id,
            provider_id=model.provider_id,
            identifier="ineligible-low-quality",
            quality=10,
            capabilities=["structured"],
            price_source=model.price_source,
        )
        session.add(low)
        session.commit()
    policy = http.post(
        f"/model-policies/agent/{agent.id}",
        json={"preferred_model_id": low.id, "allowed_model_ids": [model.id]},
    )
    assert policy.status_code == 200
    assert (
        http.post(
            f"/model-policies/agent/{agent.id}", json={"preferred_model_id": model.id, "version": 0}
        ).status_code
        == 409
    )
    seen = []

    class Adapter:
        async def request(self, _provider, selected, *_args):
            seen.append(selected.id)
            return Response(
                {
                    "title": "Routing",
                    "content": "Controlled routing result",
                    "acceptance_checks": ["Controlled test evidence"],
                },
                10,
                10,
            )

    with company["factory"]() as session:
        agent = session.get(m.Agent, agent.id)
        workflow = m.Workflow(org_id=agent.org_id, kind="document", mode="live")
        session.add(workflow)
        session.commit()
        await execute(
            session,
            workflow,
            agent,
            "policy",
            DocumentResult,
            {"objective": "Controlled test"},
            adapter=Adapter(),
        )
        assert seen == [model.id]
        run = session.scalar(select(m.ModelRun).where(m.ModelRun.workflow_id == workflow.id))
        evaluated = http.post(
            f"/model-runs/{run.id}/evaluate",
            json={"score": 10, "task_class": "document", "note": "Controlled human evaluation test"},
        )
        assert evaluated.status_code == 201
        assert (
            http.post(
                f"/model-runs/{run.id}/evaluate", json={"score": 90, "task_class": "document"}
            ).status_code
            == 409
        )
        next_workflow = m.Workflow(org_id=agent.org_id, kind="document", mode="live")
        session.add(next_workflow)
        session.commit()
        with pytest.raises(ProviderUnavailable):
            await execute(
                session, next_workflow, agent, "below_evaluation", DocumentResult, {}, adapter=Adapter()
            )
    assert seen == [model.id]


async def test_agent_work_scope_disabled_permissions_and_budget_block(
    http, company, requirement, monkeypatch
):
    project = await approved_project(http, company, requirement)
    state = http.get("/state").json()
    sender = next(a for a in state["agents"] if a["role"] == "CTO")
    recipient = next(a for a in state["agents"] if a["role"] == "Business Analyst")
    payload = {
        "request_id": uid(),
        "project_id": project["id"],
        "sender_id": sender["id"],
        "recipient_id": recipient["id"],
        "body": "A real scoped read-only document task",
    }
    with company["factory"]() as session:
        other_org = m.Organization(name="Other organization")
        session.add(other_org)
        session.flush()
        foreign_agent = m.Agent(
            org_id=other_org.id,
            department_id=recipient["department_id"],
            name="Foreign",
            role="Foreign",
            reports_to="owner",
        )
        session.add(foreign_agent)
        session.commit()
    assert http.post("/agent-messages", json={**payload, "recipient_id": foreign_agent.id}).status_code == 404
    assert http.patch(f"/agents/{recipient['id']}", json={"enabled": False}).status_code == 200
    assert http.post("/agent-messages", json=payload).status_code == 403
    http.patch(f"/agents/{recipient['id']}", json={"enabled": True})
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-budget-test")
    with company["factory"]() as session:
        live_model(session, company)
    response = http.post("/agent-messages", json={**payload, "budget_micro": 1000})
    assert response.status_code == 201
    assert await tick(company["factory"])
    state = http.get("/state").json()
    workflow = next(w for w in state["workflows"] if w["id"] == response.json()["workflow"]["id"])
    assert workflow["status"] == "needs_attention" and "budget" in workflow["last_error"].lower()
    assert not [r for r in state["runs"] if r["workflow_id"] == workflow["id"]]
    assert all(
        b["spent_micro"] == b["reserved_micro"] == 0
        for b in state["budgets"]
        if b["scope"] == f"job:{payload['request_id']}"
    )


def test_catalog_failures_are_recorded_and_rotation_invalidates_in_flight_checks(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"r" * 32).decode())
    with company["factory"]() as session:
        provider, _ = live_model(session, company)
        provider_id = provider.id
        save_secret(session, provider, "controlled-original-credential")
        session.commit()

    async def failure(_provider):
        raise ProviderError("catalog_http_401")

    monkeypatch.setattr("company_os.routes.provider_operations.discover", failure)
    result = http.post(f"/providers/{provider_id}/test")
    assert result.status_code == 200 and result.json()["status"] == "catalog_failed"
    assert not result.json()["inference_at"]

    async def rotation(_provider):
        with company["factory"]() as session:
            save_secret(session, session.get(m.Provider, provider_id), "controlled-replacement-credential")
            session.commit()
        return [{"identifier": "old-credential-catalog", "generation_methods": []}]

    monkeypatch.setattr("company_os.routes.provider_operations.discover", rotation)
    assert http.post(f"/providers/{provider_id}/discover").status_code == 409
    state = http.get("/state").json()
    probe = next(p for p in state["provider_probes"] if p["provider_id"] == provider_id)
    assert probe["status"] == "catalog_failed" and not probe["models"]
    assert "controlled-replacement-credential" not in json.dumps(state)


def test_concurrent_duplicate_probe_requests_create_one_durable_job(http, company):
    with company["factory"]() as session:
        provider, model = live_model(session, company)
    payload = {"request_id": uid(), "model_id": model.id}

    def submit(_index):
        response = http.post(f"/providers/{provider.id}/inference-probe", json=payload)
        assert response.status_code == 201, response.text
        return response.json()["workflow"]["id"]

    with ThreadPoolExecutor(max_workers=3) as pool:
        workflows = list(pool.map(submit, range(3)))
    assert len(set(workflows)) == 1
    with company["factory"]() as session:
        assert len(session.scalars(select(m.AgentWork)).all()) == 1
        assert len(session.scalars(select(m.Workflow)).all()) == 1


async def test_cancelled_in_flight_message_records_usage_without_publishing_output(
    http, company, requirement, monkeypatch
):
    project = await approved_project(http, company, requirement)
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-cancellation-test")
    with company["factory"]() as session:
        live_model(session, company)
        sender = agent_for(session, company["org"].id, "CTO")
        recipient = agent_for(session, company["org"].id, "Business Analyst")
    response = http.post(
        "/agent-messages",
        json={
            "request_id": uid(),
            "project_id": project["id"],
            "sender_id": sender.id,
            "recipient_id": recipient.id,
            "body": "Assess missing project acceptance evidence",
        },
    )
    assert response.status_code == 201
    work = response.json()["work"]

    async def cancelled(_self, *_args):
        state = http.get("/state").json()
        runtime = next(r for r in state["agent_runtime"] if r["agent_id"] == recipient.id)
        assert runtime["state"] == "RUNNING" and runtime["mode"] == "live"
        assert http.post(f"/agent-work/{work['id']}/cancel").status_code == 200
        return Response(
            {
                "title": "Cancelled output",
                "content": "This late result must never be published",
                "acceptance_checks": ["Controlled cancellation test"],
            },
            10,
            10,
        )

    monkeypatch.setattr(HTTPAdapter, "request", cancelled)
    assert await tick(company["factory"])
    state = http.get("/state").json()
    assert next(w for w in state["workflows"] if w["id"] == work["workflow_id"])["status"] == "cancelled"
    run = next(r for r in state["runs"] if r["workflow_id"] == work["workflow_id"])
    assert run["cost_micro"] == 20 and run["status"] == "succeeded"
    assert (
        next(e for e in state["agent_executions"] if e["workflow_id"] == work["workflow_id"])["state"]
        == "BLOCKED"
    )
    assert not next(w for w in state["agent_work"] if w["id"] == work["id"])["result"]
    assert (
        next(message for message in state["messages"] if message["id"] == work["subject_id"])["status"]
        == "queued"
    )
    assert not any(a["name"] == "Cancelled output" for a in state["artifacts"])


async def test_unaffordable_preference_falls_back_to_a_cheaper_qualified_model(company, monkeypatch):
    monkeypatch.setenv("AGENT_CONTRACT_API_KEY", "controlled-affordability-test")
    with company["factory"]() as session:
        provider, affordable = live_model(session, company)
        agent = agent_for(session, provider.org_id, "CEO")
        expensive = m.ModelConfig(
            org_id=provider.org_id,
            provider_id=provider.id,
            identifier="expensive-controlled-model",
            capabilities=["structured"],
            quality=95,
            sensitivity="confidential",
            price_source=affordable.price_source,
            input_price_micro_per_million=1000000000,
            output_price_micro_per_million=1000000000,
        )
        session.add(expensive)
        session.flush()
        session.add(
            m.ModelPolicy(org_id=provider.org_id, scope=f"agent:{agent.id}", preferred_model_id=expensive.id)
        )
        workflow = m.Workflow(org_id=provider.org_id, kind="document", mode="live")
        session.add(workflow)
        session.commit()
        calls = []

        class Adapter:
            async def request(self, _provider, model, *_args):
                calls.append(model.id)
                return Response(
                    {
                        "title": "Affordable qualified result",
                        "content": "Controlled affordability evidence",
                        "acceptance_checks": ["Contract output validated"],
                    },
                    10,
                    10,
                )

        await execute(session, workflow, agent, "affordable", DocumentResult, {}, adapter=Adapter())
        assert calls == [affordable.id]
        assert not session.scalar(select(m.ModelRun).where(m.ModelRun.model_id == expensive.id))
        assert all(budget.reserved_micro == 0 for budget in session.scalars(select(m.Budget)))
        fresh = m.Workflow(org_id=provider.org_id, kind="document", mode="live")
        session.add(fresh)
        session.flush()
        with pytest.raises(ValueError, match="Invalid agent state transition"):
            transition(session, fresh, agent, "COMPLETED")
