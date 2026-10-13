"""Phase 6 readiness and authoritative requested/actual-model evidence; no live AI."""

from uuid import uuid4

from company_os import models as m
from company_os.db import uid
from company_os.security import token_for
from company_os.workflows import tick
from sqlalchemy import func, select
from test_project_setup import command, create


def test_empty_readiness_is_read_only_and_has_no_fixture_catalog(http, company):
    with company["factory"]() as session:
        count = session.scalar(select(func.count()).select_from(m.BusinessRecord))
    for _ in range(2):
        result = http.get("/ai-readiness")
        assert result.status_code == 200
        data = result.json()
        assert data["state"] == "WAITING_FOR_ELIGIBLE_MODEL"
        assert data["registered_models"] == data["eligible_models"] == data["live_verified_models"] == 0
        assert not data["check_invokes_inference"]
        assert data["providers"] == [] and data["spending_mode"] == "ZERO_COST_ONLY"
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(m.BusinessRecord)) == count
        assert not session.scalar(select(m.ModelRun))


async def test_real_intake_wait_and_selection_survive_new_connections(http, company):
    row = create(http, company)
    result = http.post(f"/project-drafts/{row['id']}/submit", json=command(row))
    assert result.status_code == 200
    await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    evidence = http.get(f"/project-drafts/{row['id']}/execution-evidence").json()
    assert evidence["preferred_lead"] == "GPT-6.1 Sol" and evidence["selected_lead_id"] is None
    assert evidence["selection_history"][0]["selected_at"] > 0
    workflow = evidence["workflows"][0]
    assert workflow["status"] == "waiting_for_free_provider" and workflow["runs"] == []
    assert workflow["waiting"]["requested_model_id"] is None
    assert "Configure an approved model and resume" in workflow["message"]
    with company["factory"]() as session:
        assert not session.scalar(select(m.ModelRun))
        assert not session.scalar(
            select(m.BusinessRecord).where(m.BusinessRecord.kind == "invocation_receipt")
        )
        assert all(b.reserved_micro == b.spent_micro == 0 for b in session.scalars(select(m.Budget)))
    assert http.get(f"/project-drafts/{uuid4()}/execution-evidence").status_code == 404


async def test_exact_lead_and_worker_pool_reach_gateway_receipts(http, company):
    row = create(http, company)
    submitted = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    with company["factory"]() as session:
        provider = session.scalar(select(m.Provider).where(m.Provider.kind == "mock"))
        models = []
        for name in ("fixture-lead", "fixture-worker"):
            model = m.ModelConfig(
                id=uid(),
                org_id=provider.org_id,
                provider_id=provider.id,
                identifier=name,
                capabilities=["structured", "reasoning", "coding"],
                context_tokens=131072,
                quality=95,
                sensitivity="confidential",
            )
            session.add(model)
            models.append(model)
        session.flush()
        lead, worker = [model.id for model in models]
        draft = session.get(m.BusinessRecord, row["id"])
        # Explicit disposable test adapter; production wizard rejects mock choices.
        draft.data = {
            **draft.data,
            "form": {
                **draft.data["form"],
                "lead_model_id": lead,
                "worker_mode": "hybrid",
                "worker_model_ids": [worker],
                "overrides": {"role:Business Analyst": worker},
            },
        }
        session.get(m.Workflow, submitted["data"]["workflow_id"]).mode = "mock"
        session.get(m.Requirement, submitted["data"]["requirement_id"]).mode = "mock"
        session.commit()
    for _ in range(6):
        assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    result = http.get(f"/project-drafts/{row['id']}/execution-evidence").json()
    runs = result["workflows"][0]["runs"]
    assert len(runs) == 6
    for run in runs:
        assert run["verification"] == "FIXTURE_TESTED" and run["status"] == "succeeded"
        assert run["accepted"] and run["result_sha256"]
        assert run["context_policy"]["authorized_memory"]
        if run["step"] in {"lead_intake", "proposal"}:
            assert run["requested_model_id"] == run["actual_model_id"] == lead
        else:
            assert run["actual_model_id"] == worker
            assert run["worker_pool"] == [worker]
    assert http.get("/ai-readiness").json()["live_verified_models"] == 0
    assert not any(row["kind"] == "invocation_receipt" for row in http.get("/state").json()["records"])
    with company["factory"]() as session:
        receipt = session.scalar(
            select(m.BusinessRecord).where(m.BusinessRecord.kind == "invocation_receipt")
        )
        receipt_id = receipt.id
    assert http.patch(f"/records/{receipt_id}", json={"version": 1, "status": "reviewed"}).status_code == 409
    assert (
        http.post("/records", json={"kind": "invocation_receipt", "title": "Forged live proof"}).status_code
        == 422
    )


def test_legacy_local_cost_basis_cannot_establish_live_verification(http, company):
    with company["factory"]() as session:
        provider = m.Provider(
            org_id=company["org"].id,
            name="Unverified local registry",
            kind="ollama",
            base_url="http://localhost:11434",
            credential_env="",
        )
        session.add(provider)
        session.flush()
        model = m.ModelConfig(
            org_id=provider.org_id,
            provider_id=provider.id,
            identifier="unverified-local",
            capabilities=["structured"],
        )
        workflow = m.Workflow(org_id=provider.org_id, mode="live", status="completed")
        session.add_all([model, workflow])
        session.flush()
        agent = session.scalar(select(m.Agent).where(m.Agent.org_id == provider.org_id))
        session.add(
            m.ModelRun(
                org_id=provider.org_id,
                workflow_id=workflow.id,
                model_id=model.id,
                agent_id=agent.id,
                step_name="legacy",
                attempt=1,
                status="succeeded",
                routing_reason="legacy",
                cost_basis="local_no_provider_charge",
            )
        )
        session.commit()
    catalog = http.get("/model-catalog").json()
    assert catalog["models"][0]["live_inference_at"] is None
    assert http.get("/ai-readiness").json()["live_verified_models"] == 0


def test_readiness_is_owner_only(http, company):
    draft = create(http, company)
    with company["factory"]() as session:
        user = m.User(
            org_id=company["org"].id,
            client_id=company["client"].id,
            email="readiness-client@fixture.test",
            role="client",
            password_hash="",
        )
        session.add(user)
        session.flush()
        token = token_for(user, session)
        session.commit()
    assert http.get("/ai-readiness", headers={"Authorization": "Bearer " + token}).status_code == 403
    assert (
        http.get(
            f"/project-drafts/{draft['id']}/execution-evidence", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 403
    )
    assert (
        http.get(
            f"/projects/{uuid4()}/execution-evidence", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 403
    )


def test_execution_evidence_hides_other_owner_and_tenant_drafts(http, company):
    draft = create(http, company)
    with company["factory"]() as session:
        other_org = m.Organization(name="Other evidence tenant")
        session.add(other_org)
        session.flush()
        for org_id in (company["org"].id, other_org.id):
            user = m.User(org_id=org_id, email=f"{uuid4()}@fixture.test", role="owner")
            session.add(user)
            session.flush()
            token = token_for(user, session)
            session.commit()
            response = http.get(
                f"/project-drafts/{draft['id']}/execution-evidence",
                headers={"Authorization": "Bearer " + token},
            )
            assert response.status_code == 404 and "selection_history" not in response.text


def test_selection_history_changes_only_for_model_preferences(http, company):
    from company_os.security import digest
    from test_project_setup import form

    draft = create(http, company)
    first = http.get(f"/project-drafts/{draft['id']}/execution-evidence").json()["selection_history"]
    assert len(first) == 1
    renamed = http.patch(
        f"/project-drafts/{draft['id']}",
        json=command(draft, form=form(company, title="Renamed without model changes")),
    ).json()
    assert http.get(f"/project-drafts/{draft['id']}/execution-evidence").json()["selection_history"] == first
    change = command(renamed, form=form(company, title="Renamed without model changes", worker_mode="hybrid"))
    assert http.patch(f"/project-drafts/{draft['id']}", json=change).status_code == 200
    assert http.patch(f"/project-drafts/{draft['id']}", json=change).status_code == 200
    company["factory"].kw["bind"].dispose()
    history = http.get(f"/project-drafts/{draft['id']}/execution-evidence").json()["selection_history"]
    assert len(history) == 2 and history[:1] == first
    assert history[-1]["choices"]["worker_mode"] == "hybrid"
    assert history[-1]["selection_hash"] == digest(history[-1]["choices"])
    assert history[-1]["selected_by"] == company["owner"].id
