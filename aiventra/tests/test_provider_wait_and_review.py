import pytest
from company_os.db import now, uid
from company_os.gateway import execute
from company_os.models import Agent, Budget, ModelConfig, ModelRun, Provider, Workflow
from company_os.providers import ProviderUnavailable, Response
from company_os.schemas import ReviewResult
from company_os.workflows import tick
from sqlalchemy import select

pytestmark = pytest.mark.usefixtures("contract_inference")

ANALYSIS = {
    "project_type": "migration",
    "objectives": ["Reduce cost"],
    "requirements": ["Compare services"],
    "questions": ["Inventory?"],
    "assumptions": ["No execution approved"],
    "acceptance_criteria": ["Evidence reviewed"],
}


def provider_model(session, company, host, identifier, price=1000000):
    provider = Provider(
        id=uid(),
        org_id=company["org"].id,
        name="Controlled adapter test",
        kind="openai" if host == "api.openai.com" else "anthropic",
        base_url=f"https://{host}/v1",
        credential_env="WAIT_REVIEW_TEST_KEY",
    )
    session.add(provider)
    session.flush()
    model = ModelConfig(
        id=uid(),
        org_id=provider.org_id,
        provider_id=provider.id,
        identifier=identifier,
        capabilities=["structured", "coding", "reasoning"],
        quality=95,
        sensitivity="confidential",
        input_price_micro_per_million=price,
        output_price_micro_per_million=price,
        price_source="https://example.test/synthetic-contract-rates",
    )
    session.add(model)
    session.commit()
    return provider, model


async def test_live_workflow_waits_without_spending_then_resumes_once(http, company, monkeypatch):
    response = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Live waiting test",
            "text": "Compare migration alternatives using evidence and assumptions",
            "mode": "live",
        },
    )
    assert response.status_code == 201
    workflow_id = response.json()["workflow_id"]
    assert await tick(company["factory"])
    assert not await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(Workflow, workflow_id)
        assert workflow.status == "waiting_for_free_provider" and workflow.attempts == workflow.step == 0
        assert session.scalar(select(ModelRun)) is None
        assert all(row.reserved_micro == row.spent_micro == 0 for row in session.scalars(select(Budget)))
        provider_model(session, company, "api.openai.com", "controlled-contract-model")
    assert not await tick(company["factory"])  # Model exists, but credential is absent.
    monkeypatch.setenv("WAIT_REVIEW_TEST_KEY", "controlled-non-live-test-key")
    calls = []

    async def contract(*args, **kwargs):
        calls.append(1)
        return Response(ANALYSIS, 10, 10)

    monkeypatch.setattr("company_os.providers.HTTPAdapter.request", contract)
    assert http.post(f"/workflows/{workflow_id}/resume-free").status_code == 200
    assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(Workflow, workflow_id)
        assert workflow.step == 1 and workflow.attempts == 0
        assert len(session.scalars(select(ModelRun)).all()) == len(calls) == 1


@pytest.mark.parametrize("policy", ["prefer_provider", "require_provider"])
async def test_review_uses_another_service_and_persists_reason(company, requirement, monkeypatch, policy):
    monkeypatch.setenv("WAIT_REVIEW_TEST_KEY", "controlled-non-live-test-key")
    seen = []

    class ContractAdapter:
        async def request(self, provider, model, *_args):
            seen.append(provider.base_url)
            return Response(
                {"approved": True, "findings": [], "acceptance_assessment": ["Contract only"]}, 10, 10
            )

    with company["factory"]() as session:
        _, author = provider_model(session, company, "api.openai.com", "configured-author", 1000000)
        _, reviewer = provider_model(session, company, "api.anthropic.com", "configured-reviewer", 2000000)
        workflow = session.get(Workflow, requirement["workflow_id"])
        workflow.mode = "live"
        session.commit()
        agent = session.scalar(select(Agent).where(Agent.role == "Code Reviewer"))
        await execute(
            session,
            workflow,
            agent,
            "review",
            ReviewResult,
            {"actual_diff": "controlled diff"},
            quality=85,
            capabilities={"structured", "coding"},
            adapter=ContractAdapter(),
            review_against=[author.id],
            review_policy=policy,
        )
        run = session.scalar(select(ModelRun))
        assert run.model_id == reviewer.id and "provider_diverse=True" in run.routing_reason
        assert seen == ["https://api.anthropic.com/v1"]


@pytest.mark.parametrize("policy", ["require_provider", "require_model"])
async def test_duplicate_provider_rows_cannot_fabricate_review_diversity(
    company, requirement, monkeypatch, policy
):
    monkeypatch.setenv("WAIT_REVIEW_TEST_KEY", "controlled-non-live-test-key")
    with company["factory"]() as session:
        _, author = provider_model(session, company, "api.openai.com", "same-real-model")
        provider_model(session, company, "api.openai.com", "same-real-model")
        workflow = session.get(Workflow, requirement["workflow_id"])
        workflow.mode = "live"
        session.commit()
        agent = session.scalar(select(Agent).where(Agent.role == "Code Reviewer"))
        with pytest.raises(ProviderUnavailable):
            await execute(
                session,
                workflow,
                agent,
                "review",
                ReviewResult,
                {},
                quality=85,
                capabilities={"structured", "coding"},
                review_against=[author.id],
                review_policy=policy,
            )
        assert session.scalar(select(ModelRun)) is None


async def test_waiting_deadline_escalates_without_invoking_model(company, http):
    row = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Wait expiration",
            "text": "Analyze migration feasibility before any changes",
            "mode": "live",
        },
    ).json()
    await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.get(Workflow, row["workflow_id"])
        workflow.deadline_at = now() - 1
        session.commit()
    assert not await tick(company["factory"])
    with company["factory"]() as session:
        assert session.get(Workflow, row["workflow_id"]).status == "needs_attention"
        assert session.scalar(select(ModelRun)) is None
