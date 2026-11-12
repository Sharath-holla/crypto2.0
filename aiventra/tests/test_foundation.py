from concurrent.futures import ThreadPoolExecutor

from company_os.authentication import count_attempt
from company_os.config import settings
from company_os.db import now, uid
from company_os.health import heartbeat, workers
from company_os.models import AuthSession, LoginThrottle
from sqlalchemy import select


def test_logout_revokes_persisted_session_without_revoking_other_session(http, company):
    original = http.headers["Authorization"]
    login = http.post(
        "/auth/login", json={"email": company["owner"].email, "password": settings().owner_password}
    )
    assert login.status_code == 200
    second = "Bearer " + login.json()["access_token"]
    assert http.post("/auth/logout").status_code == 200
    assert http.get("/auth/me").status_code == 401
    http.headers["Authorization"] = second
    assert http.get("/auth/me").status_code == 200
    with company["factory"]() as session:
        records = list(session.scalars(select(AuthSession)))
        assert len(records) == 2 and sum(row.revoked_at is not None for row in records) == 1
    http.headers["Authorization"] = original
    assert http.get("/state").status_code == 401  # New dependency/session reads retained revocation.


def test_expired_server_session_is_rejected(http, company):
    with company["factory"]() as session:
        record = session.scalar(select(AuthSession))
        record.expires_at = now() - 1
        session.commit()
    assert http.get("/auth/me").status_code == 401


def test_login_throttle_persists_and_resets_atomically(http, company, monkeypatch):
    monkeypatch.setattr(settings(), "login_account_limit", 2)
    body = {"email": "unknown@example.test", "password": "invalid-test-password"}
    assert http.post("/auth/login", json=body).status_code == 401
    assert http.post("/auth/login", json=body).status_code == 401
    assert http.post("/auth/login", json=body).status_code == 429
    with company["factory"]() as session:
        rows = list(session.scalars(select(LoginThrottle)))
        assert len(rows) == 2 and all("unknown" not in row.key_hash for row in rows)
        for row in rows:
            row.resets_at = now() - 1
        session.commit()
    assert http.post("/auth/login", json=body).status_code == 401


def test_concurrent_login_counter_cannot_drop_attempts(company):
    def increment(_):
        with company["factory"]() as session:
            count = count_attempt(session, "non-secret-concurrent-test-key")
            session.commit()
            return count

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sorted(pool.map(increment, range(8))) == list(range(1, 9))


def test_worker_heartbeat_and_request_correlation(http, company, monkeypatch):
    with company["factory"]() as session:
        assert workers(session)["status"] == "unavailable"
        heartbeat(session, uid())
        assert workers(session)["status"] == "ready"
        monkeypatch.setattr("company_os.health.now", lambda: now() + 100)
        assert workers(session)["status"] == "unavailable"
    response = http.get("/health/live", headers={"X-Request-ID": "foundation-test-123"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "foundation-test-123"
    assert http.get("/health/ready").status_code == 503  # Isolated metadata-only DB has no migration head.
    assert "worker" in http.get("/state").json()["runtime"]
