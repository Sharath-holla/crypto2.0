"""Client legal statements and revision contracts; explicitly controlled fixtures."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from company_os import models as m
from sqlalchemy import select
from test_client_delivery import approve, exact, publish, release_fixture


@pytest.mark.parametrize("kind", ["accept", "request_changes", "reject", "report_defect", "request_support"])
async def test_client_statements_exact_scope_immutable_history(http, company, requirement, kind):
    project, package, _, client = await release_fixture(http, company, requirement)
    publish(http, package, approve(http, package))
    owner_token = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    path = f"/client/deliveries/{package['id']}/responses"
    body = exact(
        package,
        kind=kind,
        reason="Explicit controlled fixture client statement.",
        affected_criteria=[0],
        attachments=[{"name": "fixture.txt", "content": "Harmless supporting fixture text"}],
    )
    assert http.post(path, json={**body, "version": 999}).status_code == 409
    assert http.post(path, json={**body, "affected_criteria": [999]}).status_code == 409
    response = http.post(path, json=body)
    assert response.status_code == 201, response.text
    assert http.post(path, json=body).json() == response.json()
    history = http.get("/client/history").json()
    assert len(history) == 1 and history[0]["manifest_hash"] == package["manifest_hash"]
    if kind in {"accept", "reject", "request_changes"}:
        assert http.post(path, json={**body, "request_id": str(uuid4()), "kind": "accept"}).status_code == 409
    assert len(http.get("/client/cases").json()) == (0 if kind == "accept" else 1)
    if kind != "accept":
        case = http.get("/client/cases").json()[0]
        file = case["attachments"][0]
        download = http.get(f"/client/cases/{case['id']}/attachments/{file['sha256']}")
        assert download.status_code == 200 and download.text == "Harmless supporting fixture text"
        assert "no-store" in download.headers["cache-control"]
        assert http.get(f"/client/cases/{case['id']}/attachments/{'0' * 64}").status_code == 409
    http.headers["Authorization"] = owner_token
    withdrawn = http.post(
        f"/delivery-packages/{package['id']}/withdraw",
        json=exact(package, reason="Owner withdrew files, retaining legal statements."),
    )
    assert withdrawn.status_code == 200, withdrawn.text
    company["factory"].kw["bind"].dispose()
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    assert http.get(f"/client/deliveries/{package['id']}").status_code == 404
    assert http.get("/client/history").json() == history
    with company["factory"]() as session:
        lifecycle = session.scalar(
            select(m.BusinessRecord).where(m.BusinessRecord.kind == "delivery_lifecycle")
        )
        assert lifecycle.project_id == project["id"]
        assert session.get(m.DeliveryResponse, response.json()["id"]).evidence["attachments"][0]["sha256"]


async def test_concurrent_client_decisions_and_readonly_grant(http, company, requirement):
    _, package, _, client = await release_fixture(http, company, requirement)
    publish(http, package, approve(http, package))
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    path = f"/client/deliveries/{package['id']}/responses"
    body = exact(package, kind="accept", reason="Exact version accepted in a controlled fixture.")
    with company["factory"]() as session:
        session.scalar(select(m.ClientAccessGrant)).can_respond = False
        session.commit()
    assert http.post(path, json=body).status_code == 409
    with company["factory"]() as session:
        session.scalar(select(m.ClientAccessGrant)).can_respond = True
        session.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: http.post(path, json={**body, "request_id": str(uuid4())}), range(2))
        )
    assert sorted(row.status_code for row in results) == [201, 409]
    assert len(http.get("/client/history").json()) == 1
