"""Real persisted follow-up scheduling with explicitly deterministic model adapters."""

from uuid import uuid4

import pytest
from company_os import models as m
from company_os.db import now
from company_os.workflows import tick
from sqlalchemy import select
from test_client_delivery import approve, exact, publish, release_fixture


def case_exact(case, **extra):
    return {"request_id": str(uuid4()), "version": case["version"], "case_hash": case["case_hash"], **extra}


async def submitted_case(http, company, requirement, kind):
    project, package, _, client = await release_fixture(http, company, requirement)
    publish(http, package, approve(http, package))
    owner = http.headers["Authorization"]
    http.headers["Authorization"] = "Bearer " + client["access_token"]
    result = http.post(
        f"/client/deliveries/{package['id']}/responses",
        json=exact(
            package, kind=kind, reason="Controlled fixture follow-up requiring bounded authorized work."
        ),
    )
    assert result.status_code == 201, result.text
    http.headers["Authorization"] = owner
    with company["factory"]() as session:
        provider = m.Provider(
            org_id=company["org"].id, name="Explicit follow-up fixture", kind="mock", base_url="mock://local"
        )
        session.add(provider)
        session.flush()
        session.add(
            m.ModelConfig(
                org_id=company["org"].id,
                provider_id=provider.id,
                identifier="fixture-follow-up",
                capabilities=["structured", "reasoning", "coding", "tools"],
                quality=95,
                sensitivity="confidential",
            )
        )
        session.commit()
    return project, package, result.json()["case_id"]


def saved_case(http, project, case_id):
    return next(
        row for row in http.get(f"/projects/{project['id']}/delivery-cases").json() if row["id"] == case_id
    )


async def analyzed_scope(http, company, project, case_id):
    case = saved_case(http, project, case_id)
    path = f"/delivery-cases/{case_id}"
    body = case_exact(case, mode="mock", budget_micro=0)
    result = http.post(path + "/analyze", json=body)
    assert result.status_code == 200, result.text
    assert http.post(path + "/analyze", json=body).json() == result.json()
    assert http.post(path + "/analyze", json=case_exact(case, mode="mock", budget_micro=0)).status_code == 409
    assert await tick(company["factory"])
    company["factory"].kw["bind"].dispose()
    with company["factory"]() as session:
        task = session.get(m.Task, result.json()["task_id"])
        assert task.status == "completed"
        artifact_hash = task.evidence["sha256"]
        message = session.scalar(
            select(m.Message).where(
                m.Message.task_id == task.id, m.Message.type == "delivery_case_assignment"
            )
        )
        assert message.status == "acknowledged" and message.acknowledged_at
    case = saved_case(http, project, case_id)
    impact = {
        "summary": "Controlled impact with exactly bounded follow-up scope.",
        "components": ["documentation"],
        "acceptance": ["Provide verifiable follow-up evidence"],
        "budget_micro": 0,
    }
    scope = http.post(
        path + "/approve-scope", json=case_exact(case, impact=impact, analysis_sha256=artifact_hash)
    )
    assert scope.status_code == 200, scope.text
    assert scope.json()["fixture"] is True
    return saved_case(http, project, case_id)


async def test_change_analysis_approval_new_tasks_and_fixture_verification(http, company, requirement):
    project, package, case_id = await submitted_case(http, company, requirement, "request_changes")
    case = await analyzed_scope(http, company, project, case_id)
    path = f"/delivery-cases/{case_id}"
    body = case_exact(case, tasks=[{"kind": "document", "component": "documentation", "budget_micro": 0}])
    out_of_scope = http.post(
        path + "/create-work",
        json={**body, "tasks": [{"kind": "document", "component": "other", "budget_micro": 0}]},
    )
    assert out_of_scope.status_code == 409
    created = http.post(path + "/create-work", json=body)
    assert created.status_code == 200, created.text
    assert http.post(path + "/create-work", json=body).json() == created.json()
    assert await tick(company["factory"])
    case = saved_case(http, project, case_id)
    resolved = http.post(
        path + "/resolve",
        json=case_exact(
            case, public_resolution="Controlled deterministic document verified; no live completion claimed."
        ),
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "fixture_verified"
    assert not http.get(f"/projects/{project['id']}/closure-readiness").json()["ready"]
    with company["factory"]() as session:
        assert session.get(m.DeliveryPackage, package["id"]).manifest_hash == package["manifest_hash"]
        task = session.get(m.Task, created.json()["task_ids"][0])
        assert task.payload["delivery_case_id"] == case_id
        assert session.scalar(select(m.Workflow).where(m.Workflow.task_id == task.id)).status == "completed"


async def test_defect_requires_engineering_approval_and_real_qa(http, company, requirement):
    project, _, case_id = await submitted_case(http, company, requirement, "report_defect")
    case = await analyzed_scope(http, company, project, case_id)
    path = f"/delivery-cases/{case_id}"
    assert (
        http.post(
            path + "/create-work",
            json=case_exact(
                case, tasks=[{"kind": "document", "component": "documentation", "budget_micro": 0}]
            ),
        ).status_code
        == 409
    )
    with company["factory"]() as session:
        repository = m.Repository(
            org_id=company["org"].id,
            project_id=project["id"],
            name="Controlled fixture repository",
            path=str(company["root"] / "repositories" / "fixture"),
            report={},
            baseline_commit="a" * 40,
        )
        session.add(repository)
        session.commit()
    created = http.post(
        path + "/create-work",
        json=case_exact(
            case,
            tasks=[
                {
                    "kind": "coding",
                    "component": "documentation",
                    "budget_micro": 0,
                    "repository_id": repository.id,
                }
            ],
        ),
    )
    assert created.status_code == 200, created.text
    with company["factory"]() as session:
        task = session.get(m.Task, created.json()["task_ids"][0])
        assert task.status == "awaiting_approval"
        assert task.payload["repair_limit"] == 1 and task.payload["review_count"] == 2
        assert not session.scalar(select(m.Workflow.id).where(m.Workflow.task_id == task.id))
    case = saved_case(http, project, case_id)
    assert (
        http.post(
            path + "/resolve",
            json=case_exact(
                case, public_resolution="Must refuse resolution without actual restricted engineering and QA."
            ),
        ).status_code
        == 409
    )


@pytest.mark.parametrize("fault", ["expiry", "analysis_tamper"])
async def test_scope_expiry_tamper_and_reanalysis_history(http, company, requirement, fault):
    project, package, case_id = await submitted_case(http, company, requirement, "request_changes")
    case = await analyzed_scope(http, company, project, case_id)
    with company["factory"]() as session:
        if fault == "expiry":
            session.get(m.Approval, case["data"]["scope_approval_id"]).expires_at = now() - 1
        else:
            session.get(m.Artifact, case["data"]["scope"]["analysis"]["artifact_id"]).content += " tampered"
        session.commit()
    path = f"/delivery-cases/{case_id}"
    assert (
        http.post(
            path + "/create-work",
            json=case_exact(
                case, tasks=[{"kind": "document", "component": "documentation", "budget_micro": 0}]
            ),
        ).status_code
        == 409
    )
    revised = http.post(
        path + "/revise",
        json=case_exact(
            case, reason="Owner requested fresh analysis while preserving the previous approval history."
        ),
    )
    assert revised.status_code == 200, revised.text
    saved = saved_case(http, project, case_id)
    assert saved["status"] == "submitted" and saved["version"] == case["version"] + 1
    assert len(saved["data"]["scope_history"]) == 1
    assert saved["data"]["scope_history"][0]["approval_id"] == case["data"]["scope_approval_id"]
    with company["factory"]() as session:
        assert session.get(m.DeliveryPackage, package["id"]).manifest_hash == package["manifest_hash"]
