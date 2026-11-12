"""Simulated DevOps extension of the actual restricted-Docker Task API journey."""

from uuid import uuid4

from test_deployments import complete, evidence


async def verify_deployment(http, company, project, package):
    assert http.post("/controls", json={"action": "resume_deployments"}).status_code == 200
    response = http.post(
        f"/projects/{project['id']}/deployment-targets",
        json={
            "request_id": str(uuid4()),
            "name": "Task API disposable staging simulation",
            "environment": "staging",
        },
    )
    assert response.status_code == 201, response.text
    fixture = {"project": project, "package": package, "target": response.json()}
    _, _, receipt = await complete(http, company, fixture)
    assert receipt["data"]["body"]["artifact_hash"] == package["manifest_hash"]
    assert not receipt["data"]["body"]["live_verified"]
    await complete(http, company, fixture, scenario="health_failure")
    incident = evidence(http, fixture)["incidents"][0]
    _, _, recovered = await complete(
        http, company, fixture, rollback_receipt_id=receipt["id"], incident_id=incident["id"]
    )
    assert evidence(http, fixture)["incidents"][0]["status"] == "resolved"
    return {
        "classification": "SIMULATED_NONPRODUCTION",
        "receipt_id": receipt["id"],
        "integrity_valid": receipt["integrity_valid"],
        "failed_health_incident": incident["id"],
        "verified_rollback_receipt": recovered["id"],
    }
