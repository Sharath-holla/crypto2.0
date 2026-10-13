import json

import httpx
import pytest
from company_os.db import now, uid
from company_os.gateway import eligible_models, execute
from company_os.models import Agent, ModelConfig, ModelRun, Provider, Workflow
from company_os.providers import HTTPAdapter, ProviderError
from company_os.schemas import Analysis
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("contract_inference")

ANALYSIS = {
    "project_type": "migration",
    "objectives": ["Lower cost"],
    "requirements": ["Compare services"],
    "questions": ["Inventory?"],
    "assumptions": ["No changes authorized"],
    "acceptance_criteria": ["Evidence reviewed"],
}


@pytest.mark.parametrize(
    "kind,base,response,path",
    [
        (
            "openai",
            "https://api.openai.com/v1",
            {
                "output": [{"content": [{"type": "output_text", "text": json.dumps(ANALYSIS)}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
            "/v1/responses",
        ),
        (
            "anthropic",
            "https://api.anthropic.com/v1",
            {
                "content": [{"type": "text", "text": json.dumps(ANALYSIS)}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
            "/v1/messages",
        ),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta",
            {
                "candidates": [{"content": {"parts": [{"text": json.dumps(ANALYSIS)}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 20},
            },
            "/v1beta/models/configured-model:generateContent",
        ),
        (
            "ollama",
            "http://localhost:11434",
            {"response": json.dumps(ANALYSIS), "prompt_eval_count": 10, "eval_count": 20},
            "/api/generate",
        ),
        (
            "compatible",
            "https://api.x.ai/v1",
            {
                "choices": [{"message": {"content": json.dumps(ANALYSIS)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
            "/v1/chat/completions",
        ),
    ],
)
async def test_official_adapter_contracts(kind, base, response, path, monkeypatch):
    monkeypatch.setenv("CONTRACT_API_KEY", "non-live-test-secret")

    def handle(request):
        assert request.url.path == path
        body = json.loads(request.content)
        assert "configured-model" in request.url.path or body["model"] == "configured-model"
        assert "non-live-test-secret" not in request.content.decode()
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await HTTPAdapter(client).request(
            Provider(kind=kind, base_url=base, credential_env="CONTRACT_API_KEY"),
            ModelConfig(identifier="configured-model"),
            "server policy",
            "untrusted requirement",
            Analysis.model_json_schema(),
        )
    assert Analysis.model_validate(result.data).objectives == ["Lower cost"]
    assert result.input_tokens == 10 and result.output_tokens == 20


def live_setup(session, company, requirement):
    provider = Provider(
        id=uid(),
        org_id=company["org"].id,
        name="Contract provider",
        kind="openai",
        base_url="https://api.openai.com/v1",
        credential_env="CONTRACT_API_KEY",
    )
    session.add(provider)
    session.flush()
    models = []
    for identifier, price, quality in [("cheap-configured", 1000000, 80), ("strong-configured", 2000000, 95)]:
        model = ModelConfig(
            id=uid(),
            org_id=company["org"].id,
            provider_id=provider.id,
            identifier=identifier,
            capabilities=["structured", "reasoning"],
            quality=quality,
            sensitivity="internal",
            input_price_micro_per_million=price,
            output_price_micro_per_million=price,
            price_source="https://example.test/test-fixture",
        )
        session.add(model)
        models.append(model)
    workflow = session.get(Workflow, requirement["workflow_id"])
    workflow.mode = "live"
    session.commit()
    agent = session.scalar(select(Agent).where(Agent.role == "Business Analyst"))
    return workflow, agent, models


async def test_d_economy_routing_usage_and_quality_escalation(company, requirement, monkeypatch):
    monkeypatch.setenv("CONTRACT_API_KEY", "non-live-test-secret")
    calls = []

    def handle(request):
        body = json.loads(request.content)
        calls.append(body["model"])
        data = {} if body["model"] == "cheap-configured" else ANALYSIS
        return httpx.Response(
            200,
            json={
                "output": [{"content": [{"type": "output_text", "text": json.dumps(data)}]}],
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
        )

    with company["factory"]() as session:
        workflow, agent, models = live_setup(session, company, requirement)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await execute(
                session,
                workflow,
                agent,
                "route-test",
                Analysis,
                {"text": "requirement"},
                adapter=HTTPAdapter(client),
            )
        assert result.project_type == "migration"
        runs = session.scalars(select(ModelRun).order_by(ModelRun.attempt)).all()
        assert calls == ["cheap-configured", "strong-configured"]
        assert [run.status for run in runs] == ["quality_failed", "succeeded"]
        assert sum(run.cost_micro for run in runs) == 450
        assert all("minimum_quality" in run.routing_reason for run in runs)


async def test_e_safe_provider_rejection_falls_back(company, requirement, monkeypatch):
    monkeypatch.setenv("CONTRACT_API_KEY", "non-live-test-secret")

    def handle(request):
        if json.loads(request.content)["model"] == "cheap-configured":
            return httpx.Response(429, json={"error": "rate limit"})
        return httpx.Response(
            200,
            json={
                "output": [{"content": [{"type": "output_text", "text": json.dumps(ANALYSIS)}]}],
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        )

    with company["factory"]() as session:
        workflow, agent, _ = live_setup(session, company, requirement)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            await execute(session, workflow, agent, "failure-test", Analysis, {}, adapter=HTTPAdapter(client))
        runs = session.scalars(select(ModelRun).order_by(ModelRun.attempt)).all()
        assert [run.status for run in runs] == ["failed", "succeeded"]
        assert runs[0].cost_micro == 0


async def test_uncertain_request_is_never_blindly_repeated(company, requirement, monkeypatch):
    monkeypatch.setenv("CONTRACT_API_KEY", "non-live-test-secret")
    calls = []

    def handle(request):
        calls.append(1)
        raise httpx.ReadTimeout("timeout", request=request)

    with company["factory"]() as session:
        workflow, agent, _ = live_setup(session, company, requirement)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(ProviderError):
                await execute(
                    session, workflow, agent, "uncertain-test", Analysis, {}, adapter=HTTPAdapter(client)
                )
            with pytest.raises(ProviderError):
                await execute(
                    session, workflow, agent, "uncertain-test", Analysis, {}, adapter=HTTPAdapter(client)
                )
        assert len(calls) == 1
        run = session.scalar(select(ModelRun))
        assert run.status == "uncertain"
        assert run.reserved_micro > 0


def test_security_quality_context_and_freshness_filters(company, requirement):
    with company["factory"]() as session:
        _, _, models = live_setup(session, company, requirement)
        assert (
            len(
                eligible_models(
                    session, company["org"].id, "live", {"structured"}, 70, "internal", 1000, "economy"
                )
            )
            == 2
        )
        assert not eligible_models(
            session, company["org"].id, "live", {"coding"}, 70, "internal", 1000, "economy"
        )
        assert not eligible_models(
            session, company["org"].id, "live", {"structured"}, 70, "confidential", 1000, "economy"
        )
        assert not eligible_models(
            session, company["org"].id, "live", {"structured"}, 70, "internal", 10**7, "economy"
        )
        for model in models:
            model.price_checked_at = now() - 2592001
        session.commit()
        assert not eligible_models(
            session, company["org"].id, "live", {"structured"}, 70, "internal", 1000, "economy"
        )
