"""Real production guard; no contract_inference bypass fixture in this module."""

import json

import httpx
import pytest
from company_os import models as m
from company_os import spending
from company_os.config import Settings
from company_os.db import now, uid
from company_os.native import NativeAdapter
from company_os.providers import HTTPAdapter
from company_os.schemas import Analysis
from company_os.workflows import tick
from pydantic import ValidationError
from sqlalchemy import select

ANALYSIS = {
    "project_type": "migration",
    "objectives": ["Reduce costs"],
    "requirements": ["Compare services"],
    "questions": ["Inventory?"],
    "assumptions": ["Fixture local metadata"],
    "acceptance_criteria": ["Review evidence"],
}
TAGS = {"models": [{"name": "local-test:latest", "size": 100000, "digest": "a" * 64}]}
DETAIL = {"details": {"format": "gguf"}, "model_info": {"general.architecture": "test"}}


def register(session, company, kind="openai", identifier="unknown-model", price=0):
    provider = m.Provider(
        org_id=company["org"].id,
        name="Zero-cost policy test",
        kind=kind,
        base_url="http://127.0.0.1:11434" if kind == "ollama" else "https://api.openai.com/v1",
        credential_env="" if kind == "ollama" else "ZERO_COST_TEST_KEY",
    )
    session.add(provider)
    session.flush()
    model = m.ModelConfig(
        org_id=provider.org_id,
        provider_id=provider.id,
        identifier=identifier,
        capabilities=["structured", "reasoning", "coding", "tools", "streaming"],
        quality=95,
        sensitivity="confidential",
        context_tokens=200000,
        input_price_micro_per_million=price,
        output_price_micro_per_million=price,
        price_source="owner claimed free; not trusted billing evidence",
    )
    session.add(model)
    session.commit()
    return provider, model


def test_configuration_cannot_enable_paid_mode():
    with pytest.raises(ValidationError):
        Settings(ai_spending_mode="PAID_ALLOWED")


@pytest.mark.parametrize("kind", ["openai", "anthropic", "gemini", "xai", "compatible", "deepseek", "ollama"])
@pytest.mark.parametrize("adapter", [HTTPAdapter, NativeAdapter])
async def test_remote_inference_never_reaches_transport_even_with_keys_and_zero_rates(
    kind, adapter, monkeypatch
):
    monkeypatch.setenv("ZERO_COST_TEST_KEY", "synthetic-test-only-value")
    provider = m.Provider(
        kind=kind, base_url="https://api.openai.com/v1", credential_env="ZERO_COST_TEST_KEY"
    )
    model = m.ModelConfig(
        identifier="claimed-free", input_price_micro_per_million=0, output_price_micro_per_million=0
    )
    calls = []
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        with pytest.raises(spending.InferenceBlocked):
            await adapter(client).request(provider, model, "policy", "test", Analysis.model_json_schema())
    assert calls == []


@pytest.mark.parametrize("change", ["cloud_alias", "credential", "query", "remote", "price"])
async def test_local_alias_and_endpoint_cannot_hide_remote_billing(company, change):
    with company["factory"]() as session:
        provider, model = register(session, company, "ollama", "local-test")
        if change == "cloud_alias":
            model.identifier = "gpt:cloud"
        if change == "credential":
            provider.credential_env = "ZERO_COST_TEST_KEY"
        if change == "query":
            provider.base_url += "?proxy=remote"
        if change == "remote":
            provider.base_url = "http://example.test:11434"
        if change == "price":
            model.input_price_micro_per_million = 1
        assert not spending.assess(provider, model).local_candidate
        with pytest.raises(spending.InferenceBlocked):
            await spending.authorize(provider, model)


@pytest.mark.parametrize(
    "detail",
    [{}, {**DETAIL, "remote_host": "remote.test"}, {**DETAIL, "model_info": {"target": "model-cloud"}}],
)
def test_cloud_or_missing_manifest_cannot_attest_local(detail):
    with pytest.raises(spending.InferenceBlocked):
        spending.installed_manifest(TAGS, detail, "local-test")


def local_transport(monkeypatch, calls):
    original = httpx.AsyncClient

    def handle(request):
        calls.append(request.url.path)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=DETAIL)
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                content=json.dumps(
                    {
                        "message": {"content": json.dumps(ANALYSIS)},
                        "done": True,
                        "prompt_eval_count": 10,
                        "eval_count": 20,
                    }
                )
                + "\n",
            )
        raise AssertionError("Unexpected inference/metadata endpoint")

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )


async def test_blocked_workflow_is_durable_unspent_requires_owner_resume_and_rechecks_local_model(
    http, company, monkeypatch
):
    monkeypatch.setenv("ZERO_COST_TEST_KEY", "synthetic-test-only-value")
    with company["factory"]() as session:
        _, remote = register(session, company)
    response = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Zero cost durable test",
            "text": "Analyze migration options and preserve this requirement",
            "mode": "live",
        },
    )
    assert response.status_code == 201
    workflow_id = response.json()["workflow_id"]
    assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, workflow_id)
        assert workflow.status == "waiting_for_free_provider" and workflow.step == workflow.attempts == 0
        assert (
            workflow.wait_context["agent_id"] and workflow.wait_context["spending_mode"] == "ZERO_COST_ONLY"
        )
        assert session.scalar(select(m.ModelRun)) is None
        assert all(b.reserved_micro == b.spent_micro == 0 for b in session.scalars(select(m.Budget)))
        assert session.scalar(
            select(m.AuditEvent).where(m.AuditEvent.action == "workflow.waiting_for_free_provider")
        )
        assert session.scalar(select(m.Notification).where(m.Notification.subject_id == workflow_id))
    assert http.post(f"/workflows/{workflow_id}/resume-free").status_code == 409
    calls = []
    local_transport(monkeypatch, calls)
    with company["factory"]() as session:
        _, local = register(session, company, "ollama", "local-test")
    verified = http.post(f"/models/{local.id}/verify-local")
    assert verified.status_code == 200 and verified.json()["state"] == "LOCAL_AVAILABLE"
    assert "/api/chat" not in calls
    assert not await tick(company["factory"])  # Installing/configuring alone is not owner authorization.
    state = http.get("/state").json()
    assert state["runtime"]["ai_spending_mode"] == "ZERO_COST_ONLY"
    facts = {r["model_id"]: r for r in state["runtime"]["inference_eligibility"]}
    assert facts[remote.id]["state"] == "UNKNOWN_COST_BLOCKED" and facts[local.id]["allowed"]
    with company["factory"]() as session:
        proof = session.scalar(select(m.LocalModelVerification))
        assert proof.evidence_digest and proof.checked_at <= now()
    assert http.post(f"/workflows/{workflow_id}/resume-free").status_code == 200
    assert http.post(f"/workflows/{workflow_id}/resume-free").status_code == 409
    assert await tick(company["factory"])
    with company["factory"]() as session:
        assert session.get(m.Workflow, workflow_id).step == 1
        run = session.scalar(select(m.ModelRun))
        assert run.status == "succeeded" and run.cost_micro == run.reserved_micro == 0
        assert (
            run.cost_basis == "local_no_provider_charge"
            and "spending_mode=ZERO_COST_ONLY" in run.routing_reason
        )
    assert calls.count("/api/chat") == 1 and calls.count("/api/show") >= 4


async def test_verification_expires_and_configuration_changes_invalidate_evidence(http, company, monkeypatch):
    local_transport(monkeypatch, [])
    with company["factory"]() as session:
        provider, model = register(session, company, "ollama", "local-test")
    assert http.post(f"/models/{model.id}/verify-local").json()["allowed"]
    with company["factory"]() as session:
        model = session.get(m.ModelConfig, model.id)
        provider = session.get(m.Provider, provider.id)
        proof = session.scalar(select(m.LocalModelVerification))
        proof.checked_at = now() - 301
        assert not spending.status(session, provider, model)["allowed"]
        proof.checked_at = now()
        provider.base_url += "?changed=true"
        assert not spending.status(session, provider, model)["allowed"]


async def test_unavailable_local_verification_never_infers_or_discards_work(http, company, monkeypatch):
    original = httpx.AsyncClient
    calls = []

    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(503)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    with company["factory"]() as session:
        _, model = register(session, company, "ollama", "local-test")
    result = http.post(f"/models/{model.id}/verify-local").json()
    assert result["state"] == "PROVIDER_UNAVAILABLE" and not result["allowed"]
    assert calls == ["/api/tags"]


def test_embedding_cloud_alias_is_blocked_before_any_transport():
    calls = []
    with httpx.Client(transport=httpx.MockTransport(lambda request: calls.append(request))) as client:
        with pytest.raises(spending.InferenceBlocked):
            spending.authorize_embedding(client, "http://127.0.0.1:11434", "embed:cloud")
    assert calls == []


@pytest.mark.parametrize(
    "kind,base",
    [
        ("openai", "https://api.openai.com/v1"),
        ("xai", "https://api.x.ai/v1"),
        ("compatible", "https://api.deepseek.com/v1"),
    ],
)
async def test_manual_model_override_benchmarks_and_retry_cannot_relax_policy(
    http, company, monkeypatch, kind, base
):
    monkeypatch.setenv("ZERO_COST_TEST_KEY", "synthetic-test-only-value")
    with company["factory"]() as session:
        provider, model = register(session, company, kind=kind, price=1000000)
        provider.base_url = base
        session.commit()
    response = http.post(
        f"/providers/{provider.id}/inference-probe", json={"request_id": uid(), "model_id": model.id}
    )
    assert response.status_code == 201
    workflow_id = response.json()["workflow"]["id"]
    assert await tick(company["factory"])
    assert http.post(f"/workflows/{workflow_id}/retry").status_code == 409
    assert http.post(f"/workflows/{workflow_id}/resume-free").status_code == 409
    with company["factory"]() as session:
        assert session.get(m.Workflow, workflow_id).status == "waiting_for_free_provider"
        assert session.scalar(select(m.ModelRun)) is None
        assert spending.status(session, provider, model)["state"] == "PAID_BLOCKED"
    benchmark = http.post("/model-benchmarks", json={"request_id": uid(), "model_id": model.id})
    assert benchmark.status_code == 201, benchmark.text
    assert await tick(company["factory"])
    with company["factory"]() as session:
        assert session.scalar(select(m.BenchmarkResult)) is None
        assert session.scalar(select(m.ModelRun)) is None


def test_verify_local_is_owner_only_and_tenant_scoped(http, company):
    with company["factory"]() as session:
        foreign = m.Organization(name="Foreign test tenant")
        session.add(foreign)
        session.flush()
        provider = m.Provider(
            org_id=foreign.id, name="Private", kind="ollama", base_url="http://127.0.0.1:11434"
        )
        session.add(provider)
        session.flush()
        model = m.ModelConfig(org_id=foreign.id, provider_id=provider.id, identifier="private")
        session.add(model)
        session.commit()
    assert http.post(f"/models/{model.id}/verify-local").status_code == 404
    http.headers.pop("Authorization")
    assert http.post(f"/models/{model.id}/verify-local").status_code == 401


async def test_revising_requirement_cancels_obsolete_free_wait(http, company):
    response = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Revise saved work",
            "text": "Analyze this requirement before any implementation",
            "mode": "live",
        },
    ).json()
    assert await tick(company["factory"])
    revised = http.post(
        f"/requirements/{response['id']}/clarify",
        json={"version": response["version"], "answers": {"scope": "Updated scope"}, "rates": []},
    )
    assert revised.status_code == 200, revised.text
    with company["factory"]() as session:
        workflow = session.get(m.Workflow, response["workflow_id"])
        assert workflow.status == "cancelled" and workflow.step == 0
    assert http.post(f"/workflows/{response['workflow_id']}/resume-free").status_code == 409


async def test_unavailable_local_model_falls_back_only_to_another_verified_local_model(
    company, requirement, monkeypatch
):
    from company_os.gateway import execute

    calls = []
    original = httpx.AsyncClient

    def handle(request):
        calls.append((request.url.port, request.url.path))
        if request.url.port == 11434:
            return httpx.Response(503)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=TAGS)
        if request.url.path == "/api/show":
            return httpx.Response(200, json=DETAIL)
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                content=json.dumps(
                    {
                        "message": {"content": json.dumps(ANALYSIS)},
                        "done": True,
                        "prompt_eval_count": 10,
                        "eval_count": 20,
                    }
                )
                + "\n",
            )
        raise AssertionError("Unexpected endpoint")

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs)
    )
    with company["factory"]() as session:
        _, unavailable = register(session, company, "ollama", "local-test")
        unavailable.quality = 96
        provider, available = register(session, company, "ollama", "local-test")
        provider.base_url = "http://127.0.0.1:11435"
        workflow = session.get(m.Workflow, requirement["workflow_id"])
        workflow.mode = "live"
        workflow.status = "running"
        session.commit()
        agent = session.scalar(
            select(m.Agent).where(m.Agent.org_id == workflow.org_id, m.Agent.role == "Business Analyst")
        )
        result = await execute(session, workflow, agent, "fallback", Analysis, {})
        assert result.objectives == ANALYSIS["objectives"]
        run = session.scalar(select(m.ModelRun))
        assert run.model_id == available.id and run.cost_micro == 0
    assert calls[0] == (11434, "/api/tags")
    assert (11434, "/api/chat") not in calls and calls.count((11435, "/api/chat")) == 1
