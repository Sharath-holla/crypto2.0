"""Real vault/API/SQLite/catalog integration with non-inference HTTP fixtures."""

import asyncio
import base64
import json
from uuid import uuid4

import httpx
import pytest
from company_os import models as m
from company_os import spending
from company_os.config import settings
from company_os.credentials import stored_credential
from company_os.db import now
from company_os.gateway import eligible_models
from company_os.model_catalog import record
from company_os.provider_catalog import discover
from company_os.security import token_for, verify_audit
from company_os.workflows import tick
from sqlalchemy import func, select


@pytest.fixture
def provider(http, company, monkeypatch):
    monkeypatch.setattr(
        settings(), "provider_allowed_hosts", settings().provider_allowed_hosts + ",api.deepseek.com"
    )
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"m" * 32).decode())
    response = http.post(
        "/providers",
        json={
            "name": "Catalog integration fixture",
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "credential_env": "CATALOG_FIXTURE_API_KEY",
        },
    )
    assert response.status_code == 201
    identity = response.json()["id"]
    assert (
        http.post(
            f"/providers/{identity}/credentials", json={"secret": "opaque-catalog-contract-only"}
        ).status_code
        == 200
    )
    return identity


def transport_fixture(monkeypatch, response):
    requests = []

    async def controlled(provider):
        def handle(request):
            requests.append(request)
            assert request.method == "GET" and request.url.path.endswith("/models")
            assert request.headers["authorization"] == "Bearer opaque-catalog-contract-only"
            if isinstance(response, Exception):
                raise response
            return httpx.Response(response[0], json=response[1])

        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            return await discover(provider, client)

    monkeypatch.setattr("company_os.routes.provider_operations.discover", controlled)
    return requests


def model_for(http, provider):
    return next(row for row in http.get("/model-catalog").json()["models"] if row["provider_id"] == provider)


@pytest.mark.parametrize(
    "kind,endpoint",
    [
        ("openai", "https://api.openai.com/v1"),
        ("xai", "https://api.x.ai/v1"),
        ("compatible", "https://api.deepseek.com"),
    ],
)
def test_vault_discovery_registers_unknown_metadata_and_is_idempotent(
    http, company, provider, monkeypatch, kind, endpoint
):
    with company["factory"]() as session:
        p = session.get(m.Provider, provider)
        p.kind, p.base_url = kind, endpoint
        before = stored_credential(p, session).ciphertext
        session.commit()
    requests = transport_fixture(
        monkeypatch, (200, {"data": [{"id": "catalog-contract-model"}, {"id": "catalog-contract-model"}]})
    )
    initial = http.get("/model-catalog").json()
    assert not initial["models"]
    assert next(p for p in initial["providers"] if p["id"] == provider)["configured"]
    for _ in range(2):
        response = http.post(f"/providers/{provider}/discover")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "catalog_verified"
    model = model_for(http, provider)
    assert not model["eligibility"]["allowed"] and model["capabilities"] == []
    assert model["context_tokens"] == 0 and model["configured_quality"] == 0
    assert model["pricing_status"] == "unknown" and model["registration"] == "discovered"
    assert not model["live_inference_at"]
    assert (
        http.get("/project-creation-options").json()["models"] == http.get("/model-catalog").json()["models"]
    )
    with company["factory"]() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(m.ModelConfig).where(m.ModelConfig.provider_id == provider)
            )
            == 1
        )
        assert stored_credential(session.get(m.Provider, provider), session).ciphertext == before
        assert verify_audit(session, company["org"].id)["valid"]
    assert len(requests) == 2
    assert "opaque-catalog-contract-only" not in json.dumps(http.get("/model-catalog").json())


@pytest.mark.parametrize(
    "status,code",
    [
        (401, "catalog_http_401"),
        (403, "catalog_http_403"),
        (404, "catalog_http_404"),
        (429, "catalog_http_429"),
        (500, "catalog_http_500"),
    ],
)
def test_provider_errors_retain_last_success_and_show_stale_catalog(
    http, provider, monkeypatch, status, code
):
    transport_fixture(monkeypatch, (200, {"data": [{"id": "retained-contract-model"}]}))
    assert http.post(f"/providers/{provider}/discover").json()["status"] == "catalog_verified"
    transport_fixture(monkeypatch, (status, {"error": "opaque-catalog-contract-only"}))
    result = http.post(f"/providers/{provider}/discover")
    assert result.json()["error_code"] == code and result.json()["models"]
    catalog = http.get("/model-catalog").json()
    p = next(p for p in catalog["providers"] if p["id"] == provider)
    assert p["stale"] and p["last_success_at"] and p["error_code"] == code
    assert model_for(http, provider)["present"]
    assert "opaque-catalog-contract-only" not in result.text + json.dumps(catalog)


@pytest.mark.parametrize(
    "payload",
    [
        {"data": "invalid"},
        {"data": [{"id": "invalid model"}]},
        {"data": [{"id": "opaque-catalog-contract-only"}]},
        {"data": [None]},
        [],
    ],
)
def test_invalid_catalog_does_not_register_partial_models(http, provider, monkeypatch, payload):
    transport_fixture(monkeypatch, (200, payload))
    response = http.post(f"/providers/{provider}/discover")
    assert response.json()["status"] == "catalog_failed"
    assert response.json()["error_code"] == "catalog_invalid"
    assert not http.get("/model-catalog").json()["models"]


def test_timeout_empty_removal_restore_and_owner_configuration(http, company, provider, monkeypatch):
    transport_fixture(monkeypatch, (200, {"data": [{"id": "retained-owner-model"}]}))
    http.post(f"/providers/{provider}/discover")
    model = model_for(http, provider)
    configuration = {
        "provider_id": provider,
        "identifier": model["identifier"],
        "capabilities": ["structured", "reasoning", "coding"],
        "quality": 88,
        "context_tokens": 32768,
        "input_price_micro_per_million": 1000000,
        "output_price_micro_per_million": 2000000,
        "price_source": "Controlled owner metadata fixture",
    }
    assert http.patch(f"/models/{model['id']}", json=configuration).status_code == 200
    assert http.patch(f"/models/{model['id']}/enabled", json={"enabled": False}).status_code == 200
    http.post(f"/providers/{provider}/discover")
    repeated = model_for(http, provider)
    assert repeated["id"] == model["id"] and repeated["configured_quality"] == 88
    assert repeated["capabilities"] == configuration["capabilities"] and not repeated["model_enabled"]
    transport_fixture(monkeypatch, httpx.ReadTimeout("opaque-catalog-contract-only"))
    assert http.post(f"/providers/{provider}/discover").json()["error_code"] == "catalog_timeout"
    transport_fixture(monkeypatch, (200, {"data": []}))
    assert http.post(f"/providers/{provider}/discover").json()["status"] == "catalog_verified"
    assert not model_for(http, provider)["present"]
    with company["factory"]() as session:
        entity = session.get(m.ModelConfig, model["id"])
        assert not spending.assess(session.get(m.Provider, provider), entity).allowed
        assert not eligible_models(
            session, company["org"].id, "live", {"structured"}, 0, "public", 1, "economy"
        )
    transport_fixture(monkeypatch, (200, {"data": [{"id": "retained-owner-model"}]}))
    http.post(f"/providers/{provider}/discover")
    assert model_for(http, provider)["present"] and not model_for(http, provider)["model_enabled"]


async def test_blocked_preferences_survive_connections_and_never_authorize_inference(
    http, company, provider, monkeypatch
):
    transport_fixture(monkeypatch, (200, {"data": [{"id": "preferred-contract-model"}]}))
    http.post(f"/providers/{provider}/discover")
    model = model_for(http, provider)
    form = {
        "client_id": company["client"].id,
        "title": "Catalog preference fixture",
        "text": "Build a durable project tracker with independent tests and approval gates.",
        "lead_model_id": model["id"],
        "worker_mode": "manual",
        "worker_model_ids": [model["id"]],
        "overrides": {"role:Business Analyst": model["id"]},
    }
    created = http.post("/project-drafts", json={"request_id": str(uuid4()), "form": form})
    assert created.status_code == 201, created.text
    row = created.json()
    submitted = http.post(
        f"/project-drafts/{row['id']}/submit", json={"request_id": str(uuid4()), "version": row["version"]}
    )
    assert submitted.status_code == 200, submitted.text
    assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    saved = http.get(f"/project-drafts/{row['id']}").json()
    assert saved["data"]["form"]["lead_model_id"] == model["id"]
    assert saved["data"]["form"]["worker_model_ids"] == [model["id"]]
    assert saved["data"]["form"]["overrides"] == form["overrides"]
    assert saved["workflow"]["status"] == "waiting_for_free_provider"
    with company["factory"]() as session:
        assert not session.scalar(select(m.ModelRun))
        assert all(b.spent_micro == b.reserved_micro == 0 for b in session.scalars(select(m.Budget)))
    unknown = http.post(
        "/project-drafts", json={"request_id": str(uuid4()), "form": {**form, "lead_model_id": str(uuid4())}}
    )
    assert unknown.status_code == 403


def test_catalog_scope_missing_credentials_staleness_and_interruption(http, company, provider, monkeypatch):
    transport_fixture(monkeypatch, (200, {"data": [{"id": "scope-contract-model"}]}))
    http.post(f"/providers/{provider}/discover")
    with company["factory"]() as session:
        p = session.get(m.Provider, provider)
        state = record(session, p)
        state.data = {
            **state.data,
            "last_success_at": now() - 4000,
            "status": "discovering",
            "checked_at": now() - 60,
        }
        outsider = m.Organization(name="Separate catalog tenant")
        session.add(outsider)
        session.flush()
        owner = m.User(org_id=outsider.id, email="other-catalog-owner@example.test", role="owner")
        session.add(owner)
        session.flush()
        outsider_token = token_for(owner, session)
        session.commit()
    p = next(p for p in http.get("/model-catalog").json()["providers"] if p["id"] == provider)
    assert p["stale"] and p["discovery_interrupted"]
    own_token = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + outsider_token
    assert not http.get("/model-catalog").json()["models"]
    assert http.post(f"/providers/{provider}/discover").status_code == 404
    assert (
        http.patch(f"/models/{model_for_id(company, provider)}/enabled", json={"enabled": False}).status_code
        == 404
    )
    http.headers["Authorization"] = own_token
    http.post(f"/providers/{provider}/credentials/revoke")
    monkeypatch.setattr("company_os.routes.provider_operations.discover", discover)
    result = http.post(f"/providers/{provider}/discover")
    assert result.json()["error_code"] == "missing_credentials"
    assert model_for(http, provider)["stale"]


def model_for_id(company, provider):
    with company["factory"]() as session:
        return session.scalar(select(m.ModelConfig.id).where(m.ModelConfig.provider_id == provider))


def test_shared_catalog_storage_probe_on_sqlite(company):
    from scripts.verify_postgres import verify_catalog_sync

    verify_catalog_sync(company["factory"], company["org"].id)


def test_availability_rechecks_other_connection_removal_instead_of_cached_record(
    http, company, provider, monkeypatch
):
    from company_os.model_catalog import available, synchronize

    transport_fixture(monkeypatch, (200, {"data": [{"id": "current-availability-contract"}]}))
    http.post(f"/providers/{provider}/discover")
    with company["factory"]() as reader:
        p = reader.get(m.Provider, provider)
        cached = record(reader, p)
        model = reader.scalar(select(m.ModelConfig).where(m.ModelConfig.provider_id == provider))
        assert available(model)
        reader.commit()
        with company["factory"]() as writer:
            current = writer.get(m.Provider, provider)
            synchronize(writer, current, record(writer, current), [])
            writer.commit()
        assert cached.data["items"][model.identifier]["present"]  # Deliberately stale ORM object.
        assert not available(model)
        assert spending.assess(p, model).state == "PROVIDER_UNAVAILABLE"


async def test_overlapping_discovery_only_latest_response_can_update_registry(
    company, http, provider, monkeypatch
):
    from company_os.routes.provider_operations import test_provider as discover_route
    from fastapi import HTTPException

    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def controlled(_):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
            return [{"identifier": "older-contract-response"}]
        return [{"identifier": "latest-contract-response"}]

    monkeypatch.setattr("company_os.routes.provider_operations.discover", controlled)
    with company["factory"]() as first, company["factory"]() as second:
        pending = asyncio.create_task(discover_route(provider, first.get(m.User, company["owner"].id), first))
        await entered.wait()
        await discover_route(provider, second.get(m.User, company["owner"].id), second)
        release.set()
        with pytest.raises(HTTPException) as caught:
            await pending
        assert caught.value.status_code == 409
    assert model_for(http, provider)["identifier"] == "latest-contract-response"
    assert len(http.get("/model-catalog").json()["models"]) == 1


async def test_revoked_owner_and_secret_shaped_failures_are_not_published(
    company, http, provider, monkeypatch
):
    from company_os.providers import ProviderError
    from company_os.routes.provider_operations import test_provider as discover_route
    from fastapi import HTTPException

    async def failure(_):
        raise ProviderError("opaque-catalog-contract-only")

    monkeypatch.setattr("company_os.routes.provider_operations.discover", failure)
    result = http.post(f"/providers/{provider}/discover")
    assert result.json()["error_code"] == "catalog_failed"
    assert "opaque-catalog-contract-only" not in result.text

    async def revoke(_):
        with company["factory"]() as session:
            session.get(m.User, company["owner"].id).enabled = False
            session.commit()
        return [{"identifier": "must-not-register"}]

    monkeypatch.setattr("company_os.routes.provider_operations.discover", revoke)
    with company["factory"]() as session:
        with pytest.raises(HTTPException) as caught:
            await discover_route(provider, session.get(m.User, company["owner"].id), session)
        assert caught.value.status_code == 403
    with company["factory"]() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(m.ModelConfig).where(m.ModelConfig.provider_id == provider)
            )
            == 0
        )


def test_unsupported_discovery_and_legacy_wrong_shape_are_explicit(http, company, provider, monkeypatch):
    with company["factory"]() as session:
        session.get(m.Provider, provider).kind = "unsupported_contract"
        session.commit()
    response = http.post(f"/providers/{provider}/discover")
    assert response.json()["error_code"] == "catalog_unsupported"
    with company["factory"]() as session:
        session.get(m.Provider, provider).kind = "openai"
        session.commit()
    transport_fixture(monkeypatch, (200, {"unexpected": []}))
    assert http.post(f"/providers/{provider}/discover").json()["error_code"] == "catalog_invalid"
