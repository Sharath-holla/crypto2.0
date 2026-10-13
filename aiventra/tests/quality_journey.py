"""Real restricted-Docker QA journey; fixtures author source, never run it on this host."""

import json
from pathlib import Path
from uuid import uuid4

from company_os import models as m
from company_os.security import digest
from company_os.workflows import tick
from sqlalchemy import select


def plan_body(source):
    from company_os.quality import AUTOMATIC, CHECKS

    fixtures = Path(__file__).parent / "fixtures/phase7qa"
    files, cases = {}, []
    checks = {
        1: {"unit", "integration", "api", "validation", "database", "errors"},
        2: {"functional", "e2e", "negative", "persistence", "regression", "errors"},
        3: {
            "security",
            "authorization",
            "performance",
            "migration",
            "recovery",
            "rollback",
            "environment",
            "documentation",
        },
    }
    for stage in (1, 2, 3):
        path = f"aiventra_qa/round_{stage}/test_independent.py"
        files[path] = (fixtures / f"round_{stage}.txt").read_text()
        methods = (
            ["test_implementation"]
            if stage == 1
            else ["test_journey", "test_unknown_fields"]
            if stage == 2
            else ["test_security_and_recovery"]
        )
        for method in methods:
            cases.append(
                {
                    "id": f"aiventra_qa.round_{stage}.test_independent.Independent.{method}",
                    "stage": stage,
                    "requirements": list(range(len(source["source"]["criteria"]))),
                    "checks": sorted(checks[stage]),
                }
            )
    exceptions = []
    for stage in CHECKS:
        for check in CHECKS[stage] - checks[stage] - AUTOMATIC[stage]:
            exceptions.append(
                {
                    "stage": stage,
                    "check": check,
                    "reason": "NONPRODUCTION stdlib-only Task API fixture has no network identity, third-party packages or deployment target. No production readiness or vulnerability database verification is claimed.",
                }
            )
    return {
        "source_hash": source["source_hash"],
        "files": files,
        "cases": cases,
        "exceptions": exceptions,
        "independence": "role",
        "repair_limit": 3,
    }


def start(http, task_id, body=None):
    source = http.get(f"/tasks/{task_id}/quality-source")
    assert source.status_code == 200, source.text
    body = {**(body or plan_body(source.json())), "source_hash": source.json()["source_hash"]}
    response = http.post(f"/tasks/{task_id}/quality-plans", json=body)
    assert response.status_code == 201, response.text
    plan = response.json()
    approved = http.post(
        f"/quality-plans/{plan['id']}/approve",
        json={"version": plan["version"], "content_hash": plan["data"]["plan_hash"]},
    )
    assert approved.status_code == 200, approved.text
    response = http.post(
        f"/quality-plans/{plan['id']}/run",
        json={"request_id": str(uuid4()), "mode": "mock", "plan_hash": plan["data"]["plan_hash"]},
    )
    assert response.status_code == 201, response.text
    return plan, body


async def verify_quality_repair(http, company, project, task, patch_files):
    async def checkpoint():
        advanced = await tick(company["factory"])
        evidence = http.get(f"/projects/{project['id']}/quality").json()
        with company["factory"]() as session:
            # Include actual persisted tool failures in CI; never silently skip a stage.
            diagnostic = {
                "blockers": evidence["readiness"]["blockers"],
                "reports": [
                    {"stage": row["data"]["body"]["stage"], "verdict": row["status"]}
                    for row in evidence["reports"]
                ],
                "jobs": evidence["jobs"],
                "executions": [
                    {"status": row.status, "logs": row.logs}
                    for row in session.scalars(
                        select(m.Execution).join(m.Task).where(m.Task.project_id == project["id"])
                    )
                ],
            }
        assert advanced, diagnostic
        company["factory"].kw["bind"].dispose()

    plan, body = start(http, task["id"])
    for _ in range(2):
        await checkpoint()
    evidence = http.get(f"/projects/{project['id']}/quality").json()
    assert {row["data"]["body"]["stage"]: row["status"] for row in evidence["reports"]} == {
        1: "PASS",
        2: "FAIL",
    }, evidence
    assert not evidence["readiness"]["ready"]
    defect = next(d for d in evidence["defects"] if d["data"]["case_id"].endswith("test_unknown_fields"))
    assert defect["data"]["severity"] == "high"
    repair = http.post(
        f"/quality-defects/{defect['id']}/repair",
        json={
            "request_id": str(uuid4()),
            "objective": "Reject unknown create fields atomically and add a regression test for the independent QA defect",
        },
    )
    assert repair.status_code == 201, repair.text
    repair = repair.json()
    assert repair["status"] == "awaiting_approval"
    assert not await tick(company["factory"]), "Repair must not execute before exact owner approval"
    patch_files[0]["content"] = patch_files[0]["content"].replace(
        'if method == "POST" and len(parts) == 1:\n',
        'if method == "POST" and len(parts) == 1:\n                if set(body) - {"title"}:\n                    return 400, {"error": "invalid fields"}\n',
    )
    patch_files[1]["content"] += (
        '\n    def test_unknown_create_fields(self):\n        self.assertEqual(\n            self.call("POST", body={"title": "Valid", "unknown": True})[0], 400\n        )\n        self.assertEqual(self.call("GET")[1], [])\n'
    )
    response = http.post(f"/tasks/{repair['id']}/approve", json={"content_hash": digest(repair["payload"])})
    assert response.status_code == 200, response.text
    for _ in range(7):
        await tick(company["factory"])
    with company["factory"]() as session:
        repaired = session.get(m.Task, repair["id"])
        assert repaired.status == "completed", repaired.evidence
        assert repaired.evidence["pull_request"]["head_commit"] != plan["data"]["source"]["commit"]
    fresh, _ = start(http, repair["id"], body)
    for _ in range(3):
        await checkpoint()
    evidence = http.get(f"/projects/{project['id']}/quality").json()
    assert [
        row["status"] for row in sorted(evidence["reports"], key=lambda r: r["data"]["body"]["position"])
    ][-3:] == ["PASS"] * 3, evidence
    current = next(d for d in evidence["defects"] if d["id"] == defect["id"])
    closed = http.post(
        f"/quality-defects/{defect['id']}/commands",
        json={
            "version": current["version"],
            "action": "verify_close",
            "resolution": "New source rejects unknown fields; unchanged independent regression passed in all three restricted Docker rounds",
        },
    )
    assert closed.status_code == 200, closed.text
    evidence = http.get(f"/projects/{project['id']}/quality").json()
    assert evidence["readiness"]["ready"], evidence["readiness"]["blockers"]
    assert evidence["readiness"]["manifest"]["owner_release_approval"] == "still_required"
    frozen = http.post(f"/projects/{project['id']}/quality-readiness")
    assert frozen.status_code == 201 and frozen.json()["status"] == "ready"
    with company["factory"]() as session:
        executions = list(session.scalars(select(m.Execution).where(m.Execution.task_id == repair["id"])))
        assert all("dedicated Docker" in row.environment for row in executions)
    print(
        json.dumps(
            {
                "quality_classification": "FIXTURE_TESTED",
                "tools": "actual restricted Docker",
                "initial_plan": plan["id"],
                "fresh_plan": fresh["id"],
                "defect": defect["id"],
                "repair_task": repair["id"],
                "round_reports": len(evidence["reports"]),
                "ready_hash": evidence["readiness"]["manifest_hash"],
                "released": False,
                "deployed": False,
            }
        )
    )
