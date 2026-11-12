"""Controlled intake-to-candidate journey; model outputs are explicit test fixtures.

CI can replace only the runner fixture with actual restricted Docker execution.
Sample source is stored as .txt and is never imported/executed on the test host.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from company_os import gateway
from company_os import models as m
from company_os.config import settings
from company_os.providers import Response
from company_os.security import digest
from company_os.workflows import tick
from sqlalchemy import select
from test_agent_planning import draft_project
from test_agent_planning import start as start_planning
from test_delivery import start as start_review
from test_packages import package_input
from test_staffing import approve


@pytest.mark.parametrize("reviewed_scope", [False, True], ids=["legacy", "phase7"])
async def test_controlled_engineering_repair_qa_and_delivery_gate(http, company, monkeypatch, reviewed_scope):
    config = settings()
    real_runner = os.environ.get("PHASE6_REAL_RUNNER") == "true"
    if real_runner:
        assert os.environ.get("CI") == "true", "Actual runner verification is CI-only"
        monkeypatch.setattr(config, "execution_enabled", True)
        monkeypatch.setattr(config, "runner_url", "http://127.0.0.1:8090")
    fixtures = Path(__file__).parent / "fixtures/phase6"
    patch_files = [
        {"path": name + ".py", "content": (fixtures / (name + ".txt")).read_text()}
        for name in ("task_api", "test_task_api")
    ]
    original_fixture = gateway.fixture
    patch_count = 0
    design_binding = None

    def model_fixture(schema, context):
        nonlocal patch_count
        if (
            reviewed_scope
            and design_binding
            and schema in {"DocumentResult", "ProjectPlanResult", "PatchResult", "ReviewResult"}
        ):
            assert context["owner_selected_architecture"] == design_binding
        if schema == "DocumentResult":
            return Response(
                {
                    "title": context["objective"][:150],
                    "content": "DETERMINISTIC DOCUMENT FIXTURE; no live analysis.\n\nObjective: "
                    + context["objective"]
                    + (
                        "\n\nOwner-selected design: "
                        + design_binding["selection"]
                        + "\n\nSaved design manifest: "
                        + design_binding["manifest_hash"]
                        if design_binding
                        else "\n\nControlled Task API: CRUD, SQLite persistence, input validation and unit tests."
                    )
                    + "\n\nComplete inputs remain in their original versioned artifacts. This short fixture tests handoff binding only.",
                    "acceptance_checks": [
                        "Saved source handoff checked",
                        "No deployment or live analysis claimed",
                    ],
                },
                0,
                0,
            )
        if schema == "ProjectPlanResult":
            return Response(
                {
                    "title": "Controlled Task API plan",
                    "summary": "Explicit fixture plan for a small persistent Task API; no live AI.",
                    "risks": ["Fixture-only planning and review"],
                    "tasks": [
                        {
                            "key": "task_api",
                            "role": "Backend Developer",
                            "kind": "coding",
                            "objective": "Implement a persistent Task API with CRUD, validation and unit tests",
                            "acceptance": [
                                "CRUD and input validation pass",
                                "Tasks survive a new API instance",
                            ],
                            "depends_on": [],
                            "required_tools": ["propose_patch"],
                            "workstream": "backend",
                        }
                    ],
                },
                0,
                0,
            )
        if schema == "PatchResult":
            patch_count += 1
            return Response(
                {
                    "summary": "DETERMINISTIC PATCH FIXTURE; no live code generation",
                    "files": [{"path": "task_api.py", "content": "def invalid(:\n"}]
                    if patch_count == 1
                    else patch_files,
                    "tests": "python-unittest",
                },
                0,
                0,
            )
        if schema == "ReviewResult":
            return Response(
                {
                    "approved": True,
                    "findings": ["DETERMINISTIC REVIEW FIXTURE; not live QA certification"],
                    "acceptance_assessment": ["Exercise the actual restricted tests separately"],
                },
                0,
                0,
            )
        if schema == "QualityAssessment":
            return Response(
                {
                    "verdict": "PASS",
                    "summary": "DETERMINISTIC QA ASSESSMENT; actual tool outcomes remain authoritative.",
                    "checked_cases": [case["id"] for case in context["cases"]],
                    "findings": [],
                },
                0,
                0,
            )
        return original_fixture(schema, context)

    monkeypatch.setattr(gateway, "fixture", model_fixture)
    actual_results = []
    from company_os.engineering import run_tests as actual_runner

    async def runner(workspace, suite, timeout=120, job_id=None):
        if real_runner:
            value = await actual_runner(workspace, suite, timeout, job_id)
            assert value["policy"]["network"] == "none" and value["policy"]["user"] == "10001:10001"
            assert "dedicated Docker" in value["environment"]
        else:
            broken = (workspace / "task_api.py").exists() and (
                workspace / "task_api.py"
            ).read_text().startswith("def invalid")
            value = {
                "job_id": job_id,
                "command": ["python", "-m", "unittest"],
                "environment": "DETERMINISTIC_RUNNER_FIXTURE; not Docker evidence",
                "exit_code": 1 if broken else 0,
                "logs": "SyntaxError: controlled failure" if broken else "Ran 10 tests\nOK",
                "build": {
                    "exit_code": 1 if broken else 0,
                    "logs": "Controlled syntax error" if broken else "Fixture build",
                },
            }
        actual_results.append(value)
        return value

    monkeypatch.setattr("company_os.engineering.run_tests", runner)
    if reviewed_scope:
        from company_os.architecture_design import selected_context
        from test_architecture_design import proposed

        _row, proposal_id, body = await proposed(http, company)
        with company["factory"]() as session:
            manifest = session.get(m.Proposal, proposal_id).content["architecture_manifest"]
            body["selection"] = manifest["design"]["options"][1]["name"]
        response = http.post(f"/proposals/{proposal_id}/approve", json=body)
        assert response.status_code == 200, response.text
        project = response.json()
        with company["factory"]() as session:
            design_binding = selected_context(
                session.get(m.Proposal, proposal_id), session.get(m.Project, project["id"])
            )
            for task in session.scalars(select(m.Task).where(m.Task.project_id == project["id"])):
                task.status = "paused"
            session.commit()
        plan = http.get(f"/projects/{project['id']}/staffing").json()
    else:
        requirement = http.post(
            "/requirements",
            json={
                "client_id": company["client"].id,
                "title": "NONPRODUCTION controlled Task API",
                "text": "Build a small task-management API with persistent tasks, CRUD validation and automated tests. This is an explicit deterministic integration fixture.",
                "mode": "mock",
            },
        )
        assert requirement.status_code == 201
        project, plan = await draft_project(http, company, requirement.json())
    planning = start_planning(http, project, plan)
    assert planning.status_code == 201
    for _ in range(3):
        assert await tick(company["factory"])
        company["factory"].kw["bind"].dispose()
    planned = http.get(f"/projects/{project['id']}/staffing").json()
    assert planned["status"] == "draft" and not planned["tasks"]
    active = approve(http, planned)
    task = next(row for row in active["tasks"] if row["kind"] == "coding")
    with company["factory"]() as session:
        for row in session.scalars(
            select(m.Task).where(m.Task.project_id == project["id"], m.Task.status == "paused")
        ):
            row.status = "ready"
        session.commit()
    for _ in range(20):
        await tick(company["factory"])
    root = config.repository_root / "task-api"
    root.mkdir(parents=True)
    (root / "README.md").write_text("NONPRODUCTION controlled Task API fixture\n")
    (root / "test_baseline.py").write_text(
        "import unittest\n\n\nclass Baseline(unittest.TestCase):\n    def test_baseline(self):\n        self.assertTrue(True)\n"
    )
    for args in (
        ["init"],
        ["config", "user.email", "fixture@local.invalid"],
        ["config", "user.name", "Phase 6 Fixture"],
        ["add", "."],
        ["commit", "-m", "Controlled baseline"],
    ):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, timeout=20)
    imported = http.post(
        "/repositories",
        json={"project_id": project["id"], "name": "Controlled Task API", "relative_path": "task-api"},
    )
    assert imported.status_code == 201, imported.text
    bound = http.post(
        f"/tasks/{task['id']}/coding-scope",
        json={"repository_id": imported.json()["id"], "test_suite": "python-unittest", "repair_limit": 1},
    )
    assert bound.status_code == 200, bound.text
    assert http.post(f"/tasks/{task['id']}/approve", json={"content_hash": "a" * 64}).status_code == 409
    assert (
        http.post(
            f"/tasks/{task['id']}/approve", json={"content_hash": bound.json()["approval_hash"]}
        ).status_code
        == 200
    )
    for _ in range(20):
        await tick(company["factory"])
    with company["factory"]() as session:
        finished = session.get(m.Task, task["id"])
        assert finished.status == "completed", finished.evidence
        assert finished.evidence["repair_round"] == 1 and patch_count == 2
        assert (
            finished.evidence["reviewer_approved"]
            and finished.evidence["qa_agent_id"] != finished.assigned_agent_id
        )
        draft = session.scalar(
            select(m.BusinessRecord).where(
                m.BusinessRecord.project_id == project["id"], m.BusinessRecord.kind == "pull_request_draft"
            )
        )
        assert draft and draft.data["publication"] == "prepared_not_published"
        assert draft.data["head_commit"] != draft.data["base_commit"]
        diff = session.scalar(
            select(m.Artifact)
            .where(m.Artifact.task_id == task["id"], m.Artifact.kind == "code_diff")
            .order_by(m.Artifact.created_at.desc(), m.Artifact.id.desc())
        )
        assert diff
        candidate = draft.data["head_commit"]
        assert not (root / "task_api.py").exists()
    assert len(actual_results) == 3 and actual_results[1]["build"]["exit_code"] != 0
    assert actual_results[-1]["exit_code"] == actual_results[-1]["build"]["exit_code"] == 0
    if real_runner:
        assert "Ran 10 tests" in actual_results[-1]["logs"]
    if real_runner and reviewed_scope:
        from quality_journey import verify_quality_repair

        await verify_quality_repair(http, company, project, task, patch_files)
    evidence = http.get(f"/projects/{project['id']}/delivery-readiness?mode=mock").json()
    package_receipt = {"status": "blocked: actual dedicated Docker QA required"}
    deployment_receipt = {"status": "not attempted: actual dedicated Docker QA required"}
    if real_runner:
        assert evidence["ready"], evidence["blockers"]
        assert any(
            source.get("classification") == "fixture_nonproduction"
            for source in evidence["manifest"]["sources"]
        )
        review = start_review(http, project, evidence)
        assert review.status_code == 201, review.text
        for _ in range(5):
            assert await tick(company["factory"])
        document_sources = [source for source in evidence["manifest"]["sources"] if source.get("artifact_id")]
        assert document_sources
        body = {
            **package_input({**evidence, "manifest": {"sources": document_sources}}, review.json()["review"]),
            "include_source_patches": True,
        }
        response = http.post(f"/projects/{project['id']}/delivery-packages", json=body)
        assert response.status_code == 201, response.text
        for _ in range(2):
            assert await tick(company["factory"])
        saved = http.get(f"/delivery-packages/{response.json()['id']}").json()
        assert saved["status"] == "package_ready" and saved["classification"] == "fixture_nonproduction"
        assert saved["integrity_valid"] and saved["manifest_hash"] == digest(saved["manifest"])
        from company_os import publication, release

        with company["factory"]() as session:
            with pytest.raises(PermissionError, match="never be released"):
                release.release_readiness(session, session.get(m.DeliveryPackage, saved["id"]))
            with pytest.raises(publication.PublicationError):
                publication.candidate(session, session.get(m.Task, task["id"]))
        package_receipt = {
            "status": saved["status"],
            "classification": saved["classification"],
            "manifest_hash": saved["manifest_hash"],
        }
        from deployment_journey import verify_deployment

        deployment_receipt = await verify_deployment(http, company, project, saved)
    else:
        assert not evidence["ready"]  # Runner contract fixture cannot certify packaging.
    assert not http.get(f"/projects/{project['id']}/delivery-readiness").json()["ready"]
    receipts = http.get(f"/projects/{project['id']}/execution-evidence").json()
    assert all(
        run["verification"] == "FIXTURE_TESTED" for flow in receipts["workflows"] for run in flow["runs"]
    )
    assert http.get("/ai-readiness").json()["live_verified_models"] == 0
    print(
        json.dumps(
            {
                "classification": "FIXTURE_TESTED",
                "phase7_reviewed_scope": reviewed_scope,
                "runner": "actual restricted Docker" if real_runner else "DETERMINISTIC_RUNNER_FIXTURE",
                "executions": len(actual_results),
                "bounded_repairs": 1,
                "candidate_commit": candidate,
                "nonproduction_package": package_receipt,
                "deployment": deployment_receipt,
                "published": False,
                "live_ai": False,
            }
        )
    )
