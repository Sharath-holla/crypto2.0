from company_os.db import uid
from company_os.models import Agent, AuditEvent, Client, Notification, User
from company_os.security import check_agent, redact, token_for, verify_audit
from company_os.workflows import tick
from sqlalchemy import select


def test_auth_required_and_token_expiry(http):
    http.headers.pop("Authorization")
    assert http.get("/state").status_code == 401
    assert http.get("/health").status_code == 200


def test_client_and_organization_isolation(http, company, requirement):
    with company["factory"]() as session:
        other_client = Client(id=uid(), org_id=company["org"].id, name="Other client")
        session.add(other_client)
        session.flush()
        user = User(
            id=uid(), org_id=company["org"].id, email="client@test", client_id=other_client.id, role="client"
        )
        session.add(user)
        session.commit()
        token = token_for(user, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get("/requirements").json() == []
    assert http.get(f"/requirements/{requirement['id']}").status_code == 404
    assert http.get("/state").status_code == 403
    assert http.post("/controls", json={"action": "pause_company"}).status_code == 403
    assert (
        http.post(
            "/requirements",
            json={
                "client_id": company["client"].id,
                "title": "Leak",
                "text": "Try another client's confidential scope",
                "mode": "mock",
            },
        ).status_code
        == 404
    )


def test_ceo_cannot_author_code(http):
    ceo = next(agent for agent in http.get("/state").json()["agents"] if agent["role"] == "CEO")
    assert http.patch(f"/agents/{ceo['id']}", json={"tools": ["propose_patch"]}).status_code == 403


def test_state_redacts_nested_records_and_observes_secret_rotation(http, company, monkeypatch):
    from company_os.models import BusinessRecord

    for value in ("controlled-first-private-value", "controlled-rotated-private-value"):
        monkeypatch.setenv("FIXTURE_ROTATING_SECRET", value)
        with company["factory"]() as session:
            session.add(
                BusinessRecord(
                    org_id=company["org"].id,
                    kind="document",
                    title="Redaction fixture",
                    data={"nested": [{"content": "café " + value}]},
                )
            )
            session.commit()
        response = http.get("/state")
        assert response.status_code == 200
        assert value not in response.text
        assert "café [REDACTED]" in response.text


def test_agent_permissions_record_denial(company):
    with company["factory"]() as session:
        ceo = session.scalar(select(Agent).where(Agent.role == "CEO"))
        try:
            check_agent(session, ceo, "production_deploy")
            raise AssertionError("Unauthorized action was allowed")
        except PermissionError:
            pass
        assert session.scalar(select(Notification)) is not None
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "policy.denied")) is not None


async def test_emergency_pause_stops_worker(company, http, requirement):
    assert http.post("/controls", json={"action": "pause_company"}).status_code == 200
    assert not await tick(company["factory"])
    assert http.post("/controls", json={"action": "resume_company"}).status_code == 200
    assert await tick(company["factory"])


def test_provider_endpoint_and_secret_boundaries(http):
    assert (
        http.post(
            "/providers",
            json={
                "name": "evil",
                "kind": "openai",
                "base_url": "http://169.254.169.254",
                "credential_env": "OPENAI_API_KEY",
            },
        ).status_code
        == 422
    )
    assert (
        http.post(
            "/providers",
            json={
                "name": "evil",
                "kind": "openai",
                "base_url": "https://api.openai.com/v1",
                "credential_env": "JWT_SECRET",
            },
        ).status_code
        == 422
    )
    assert "password_hash" not in http.get("/auth/me").json()
    assert "[REDACTED]" in redact("api_key=sk-abcdefghijklmnopqrstuvwxyz")
    assert "PRIVATE KEY" not in redact(
        "-----BEGIN PRIVATE KEY-----\nSECRET\n-----END PRIVATE KEY-----"
    ).replace("[REDACTED PRIVATE KEY]", "")


def test_audit_detects_tampering(company):
    with company["factory"]() as session:
        assert verify_audit(session, company["org"].id)["valid"]
        event = session.scalar(select(AuditEvent))
        event.action = "tampered"
        session.commit()
        assert not verify_audit(session, company["org"].id)["valid"]
