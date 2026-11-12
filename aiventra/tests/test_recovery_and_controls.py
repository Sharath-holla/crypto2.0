import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from company_os.db import uid
from company_os.models import ModelRun, Organization, Proposal, User, Workflow
from company_os.security import token_for
from company_os.workflows import claim
from sqlalchemy import select


def test_j_actual_worker_process_restarts(company, requirement):
    environment = dict(os.environ)
    environment.update(
        {
            "DATABASE_URL": str(company["factory"].kw["bind"].url),
            "ARTIFACT_ROOT": str(company["root"] / "artifacts"),
            "REPOSITORY_ROOT": str(company["root"] / "repositories"),
            "MOCK_ENABLED": "true",
        }
    )
    for _ in range(7):
        result = subprocess.run(
            [sys.executable, "-m", "company_os.cli", "worker-once"],
            env=environment,
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0, result.stderr
    with company["factory"]() as session:
        assert len(session.scalars(select(ModelRun)).all()) == 7
        assert len(session.scalars(select(Proposal)).all()) == 1
        assert session.scalar(select(Workflow)).status == "completed"


def test_concurrent_worker_claim_is_exclusive(company, requirement):
    def take():
        with company["factory"]() as session:
            row = claim(session)
            return row.id if row else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: take(), range(2)))
    assert sum(value is not None for value in results) == 1


def test_owner_from_another_organization_cannot_read_requirements(http, company, requirement):
    with company["factory"]() as session:
        org = Organization(id=uid(), name="Other organization")
        session.add(org)
        session.flush()
        user = User(id=uid(), org_id=org.id, email="other-owner@test", role="owner")
        session.add(user)
        session.commit()
        token = token_for(user, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get(f"/requirements/{requirement['id']}").status_code == 404
    assert http.get("/state").json()["requirements"] == []


async def test_g_deployment_denied_audited_and_alerted(http, company, requirement):
    from company_os.workflows import tick

    for _ in range(7):
        await tick(company["factory"])
    proposal = http.get("/state").json()["proposals"][0]
    project = http.post(
        f"/proposals/{proposal['id']}/approve",
        json={
            "version": 1,
            "content_hash": proposal["content_hash"],
            "selection": proposal["content"]["recommendation"],
        },
    ).json()
    response = http.post(f"/projects/{project['id']}/deploy")
    assert response.status_code == 403
    state = http.get("/state").json()
    assert any(event["action"] == "deployment.denied" for event in state["audit"])
    assert any("Deployment blocked" in alert["title"] for alert in state["notifications"])


async def test_f_missing_models_retry_is_bounded(http, company, requirement):
    from company_os.models import ModelConfig
    from company_os.workflows import tick

    with company["factory"]() as session:
        for model in session.scalars(select(ModelConfig)).all():
            model.enabled = False
        session.commit()
    for _ in range(3):
        assert await tick(company["factory"])
    with company["factory"]() as session:
        workflow = session.scalar(select(Workflow))
        assert workflow.attempts == 3
        assert workflow.status == "needs_attention"
        assert session.scalar(select(ModelRun)) is None
    assert not await tick(company["factory"])
