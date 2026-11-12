import pytest
from company_os.api import app
from company_os.config import settings
from company_os.db import Base, make_engine, session_dependency
from company_os.models import Client, User
from company_os.organization import seed
from company_os.security import token_for
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def contract_inference(monkeypatch):
    """Legacy protocol/accounting fixtures, explicitly isolated from real networking.

    Production policy tests never request this fixture. There is no production
    configuration switch permitting remote inference in ZERO_COST_ONLY.
    """
    from company_os import spending

    def prohibit_network(*args, **kwargs):
        raise AssertionError("Contract inference fixture attempted real network access")

    async def prohibit_async(*args, **kwargs):
        prohibit_network()

    async def authorize(*args):
        return spending.Decision(True, "DETERMINISTIC_TEST", "Controlled adapter contract only")

    monkeypatch.setattr("httpx.AsyncHTTPTransport.handle_async_request", prohibit_async)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", prohibit_network)
    monkeypatch.setattr(
        spending,
        "assess",
        lambda *args: spending.Decision(True, "DETERMINISTIC_TEST", "Controlled adapter contract only"),
    )
    monkeypatch.setattr(spending, "authorize", authorize)


@pytest.fixture
def company(tmp_path, monkeypatch):
    config = settings()
    monkeypatch.setattr(config, "jwt_secret", "test-suite-auth-secret-32-characters-long")
    monkeypatch.setattr(config, "owner_password", "test-owner-password-long-enough")
    monkeypatch.setattr(config, "artifact_root", tmp_path / "artifacts")
    monkeypatch.setattr(config, "repository_root", tmp_path / "repositories")
    monkeypatch.setattr(config, "mock_enabled", True)
    # Contract plans use a known scheduler capacity, independent of the owner's
    # conservative local one-request configuration. Scheduling limits have their own tests.
    monkeypatch.setattr(config, "scheduler_concurrency", 4)
    monkeypatch.setattr(
        config, "ollama_min_available_memory_mb", 0
    )  # Host RAM is tested with explicit fixtures, never the developer's live workload.
    monkeypatch.setattr(config, "oidc_issuer", "")
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        org = seed(session)
        owner = session.scalar(select(User).where(User.role == "owner"))
        client = session.scalar(select(Client))
    yield {"factory": factory, "org": org, "owner": owner, "client": client, "root": tmp_path}
    engine.dispose()


@pytest.fixture
def http(company):
    def session_override():
        with company["factory"]() as session:
            yield session

    app.dependency_overrides[session_dependency] = session_override
    with TestClient(app) as client:
        with company["factory"]() as session:
            token = token_for(company["owner"], session)
            session.commit()
        client.headers["Authorization"] = "Bearer " + token
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def requirement(http, company):
    response = http.post(
        "/requirements",
        json={
            "client_id": company["client"].id,
            "title": "Cloud migration",
            "text": "Move Google Cloud workloads to Lightning AI after comparing feasibility and complete costs.",
            "mode": "mock",
            "budget_micro": 5000000,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
