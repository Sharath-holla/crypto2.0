"""Registry origin, live-execution boundaries and disposable database fencing."""

import base64
from pathlib import Path

import pytest
from company_os import models as m
from company_os import spending
from company_os.config import Settings, settings
from company_os.credentials import credential_facts, secret_for
from company_os.db import make_application_engine
from company_os.registry_provenance import classify
from company_os.security import verify_audit
from sqlalchemy import func, select


def registered(http, name="Browser vault contract owner-named real account"):
    provider = http.post(
        "/providers",
        json={
            "name": name,
            "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "credential_env": "OWNER_REAL_API_KEY",
        },
    ).json()
    model = http.post(
        "/models",
        json={
            "provider_id": provider["id"],
            "identifier": "owner-registered-id",
            "capabilities": ["structured", "reasoning"],
            "price_source": "https://example.test/owner-documented",
            "input_price_micro_per_million": 1,
            "output_price_micro_per_million": 0,
            "context_tokens": 32768,
            "quality": 80,
        },
    ).json()
    return provider, model


def test_name_is_not_provenance_and_fixture_cannot_execute_or_be_selected(http, company):
    provider, model = registered(http)
    catalog = http.get("/model-catalog").json()
    assert any(
        row["id"] == model["id"] and row["provenance"] == "owner_registered" for row in catalog["models"]
    )
    with company["factory"]() as session:
        p = session.get(m.Provider, provider["id"])
        classify(session, p, "test_fixture", {"contract": "explicit_test"})
        session.commit()
        saved = session.get(m.ModelConfig, model["id"])
        assert not spending.assess(p, saved).allowed
        p.kind, p.credential_env = "ollama", ""
        saved.input_price_micro_per_million = 0
        assert not spending.assess(p, saved).local_candidate
    assert not http.get("/model-catalog").json()["models"]
    assert not any(row["id"] == model["id"] for row in http.get("/state").json()["models"])
    assert http.post(f"/providers/{provider['id']}/discover").status_code == 409
    assert (
        http.post(
            f"/model-policies/provider/{provider['id']}", json={"preferred_model_id": model["id"]}
        ).status_code
        == 422
    )
    with company["factory"]() as session:
        assert session.get(m.ModelConfig, model["id"])
        assert verify_audit(session, company["org"].id)["valid"]


@pytest.mark.parametrize(
    "url,env,isolated,visible",
    [
        ("sqlite:///data/company.db", "test", True, True),
        ("sqlite:///data/pytest-temp/fixture.db", "test", True, True),
        ("sqlite:///data/pytest-temp/guard/fixture.db", "development", True, True),
        ("sqlite:///data/pytest-temp/guard/fixture.db", "test", False, True),
        ("postgresql+psycopg://localhost/test", "test", True, True),
    ],
)
def test_server_refuses_unsafe_fixture_database(url, env, isolated, visible):
    config = Settings(
        database_url=url,
        app_env=env,
        isolated_test_environment=isolated,
        fixture_catalog_enabled=visible,
        required_database_backend=None,
    )
    with pytest.raises(ValueError, match="Isolated tests require"):
        make_application_engine(config)


def test_vault_persists_across_connections_and_corruption_is_safe(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"v" * 32).decode())
    provider, _ = registered(http)
    secret = "opaque-isolation-test-only"
    assert http.post(f"/providers/{provider['id']}/credentials", json={"secret": secret}).status_code == 200
    with company["factory"]() as session:
        p = session.get(m.Provider, provider["id"])
        assert secret_for(p, session) == secret
        assert credential_facts(p, session)["credential_configured"]
    monkeypatch.setattr(settings(), "provider_secret_key", base64.urlsafe_b64encode(b"w" * 32).decode())
    catalog = http.get("/model-catalog").json()
    row = next(p for p in catalog["providers"] if p["id"] == provider["id"])
    assert not row["configured"] and row["credential_error"] == "vault_unavailable"
    assert secret not in http.get("/state").text
    assert (
        http.post(
            f"/providers/{provider['id']}/credentials", json={"secret": "replacement-contract-key"}
        ).status_code
        == 200
    )
    with company["factory"]() as session:
        assert session.scalar(select(func.count()).select_from(m.ProviderCredential)) == 1
        assert secret_for(session.get(m.Provider, provider["id"]), session) == "replacement-contract-key"


def test_quarantine_requires_independent_evidence_and_keeps_owner_named_record(http, company):
    from scripts.quarantine_browser_registry import evidence

    provider, _ = registered(http, "Browser vault contract 1791483886084")
    with company["factory"]() as session:
        assert evidence(session, session.get(m.Provider, provider["id"])) is None


def test_private_fixture_database_guard_accepts_unique_path():
    root = Path(__file__).resolve().parents[1] / "data/pytest-temp/guard-isolation"
    root.mkdir(parents=True, exist_ok=True)
    config = Settings(
        database_url="sqlite:///" + (root / "fixture.db").as_posix(),
        app_env="test",
        isolated_test_environment=True,
    )
    engine = make_application_engine(config)
    engine.dispose()


@pytest.mark.parametrize(
    "ci,name,host",
    [
        ("false", "browser_ci_123_1", "database"),
        ("true", "company", "database"),
        ("true", "browser_ci_123_1", "localhost"),
    ],
)
def test_postgres_browser_fence_refuses_unproven_database(monkeypatch, ci, name, host):
    monkeypatch.setenv("CI", ci)
    monkeypatch.setenv("BROWSER_CI_DATABASE", name)
    config = Settings(
        database_url=f"postgresql+psycopg://company@{host}/{name}",
        required_database_backend="postgresql",
        app_env="test",
        isolated_test_environment=True,
        isolated_postgres_ci=True,
    )
    with pytest.raises(ValueError, match="dedicated disposable CI database"):
        make_application_engine(config)


def test_postgres_browser_fence_accepts_only_exact_ci_identity(monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("BROWSER_CI_DATABASE", "browser_ci_123_1")
    config = Settings(
        database_url="postgresql+psycopg://company@database/browser_ci_123_1",
        app_env="test",
        isolated_test_environment=True,
        isolated_postgres_ci=True,
        required_database_backend="postgresql",
    )
    engine = make_application_engine(config)
    assert engine.dialect.name == "postgresql"
    engine.dispose()
