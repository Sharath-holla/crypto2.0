"""Real API/worker process recovery in UUID-private SQLite; deterministic AI only."""

import argparse
import asyncio
import base64
import hashlib
import json
import os
import site
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4


def deny_network():
    import httpx

    def deny(*_args, **_kwargs):
        raise AssertionError("Requirements recovery fixture prohibits outbound transports")

    async def deny_async(*args, **kwargs):
        deny(*args, **kwargs)

    httpx.HTTPTransport.handle_request = deny
    httpx.AsyncHTTPTransport.handle_async_request = deny_async


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=int)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--crash-after-claim", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    sys.path.insert(0, str(root / "apps/api"))
    if args.serve or args.worker or args.crash_after_claim:
        from company_os.config import settings

        config = settings()
        assert config.isolated_test_environment and config.required_database_backend == "sqlite"
        assert "requirements-restart-" in config.database_url
        config.validate_startup()
        deny_network()
        if args.serve:
            import uvicorn

            uvicorn.run("company_os.api:app", host="127.0.0.1", port=args.serve, log_level="warning")
        else:
            from company_os.db import SessionLocal, now
            from company_os.workflows import claim, tick

            if args.crash_after_claim:
                with SessionLocal() as session:
                    workflow = claim(session)
                    assert workflow and workflow.step == 1
                    # Disposable fixture lease expires promptly. Production remains 180s.
                    workflow.lease_until = now() + 1
                    session.commit()
                os._exit(0)  # Deliberate abrupt exit, before provider invocation/checkpoint.
            assert asyncio.run(tick(SessionLocal))
        return

    import httpx

    private = root / "data/pytest-temp" / ("requirements-restart-" + str(uuid4()))
    private.mkdir(parents=True)
    environment = {
        **os.environ,
        "DATABASE_URL": "sqlite:///" + (private / "fixture.db").as_posix(),
        "REQUIRED_DATABASE_BACKEND": "sqlite",
        "APP_ENV": "test",
        "ISOLATED_TEST_ENVIRONMENT": "true",
        "FIXTURE_CATALOG_ENABLED": "true",
        "AI_SPENDING_MODE": "ZERO_COST_ONLY",
        "MOCK_ENABLED": "true",
        "JWT_SECRET": "requirements-restart-test-only-auth-secret-32chars",
        "PROVIDER_SECRET_KEY": base64.urlsafe_b64encode(b"r" * 32).decode(),
        "OWNER_EMAIL": "requirements-restart@fixture.test",
        "OWNER_PASSWORD": "requirements-restart-test-password",
        "ARTIFACT_ROOT": str(private / "artifacts"),
        "REPOSITORY_ROOT": str(private / "repositories"),
        "EMBEDDING_PROVIDER": "deterministic_test",
        "SCHEDULER_CONCURRENCY": "4",
        "EXECUTION_ENABLED": "false",
        "OIDC_ISSUER": "",
        "S3_BUCKET": "",
        "GITHUB_PUBLICATION_REPOSITORIES": "",
        "GITHUB_PUBLICATION_TOKEN_ENV": "FIXTURE_DISABLED_GITHUB_TOKEN",
        "PYTHONPATH": os.pathsep.join([str(root / "apps/api"), *site.getsitepackages()]),
    }
    for key in list(environment):
        if key.endswith("_API_KEY") or key in {"GH_TOKEN", "GITHUB_TOKEN", "AIVENTRA_GITHUB_TOKEN"}:
            environment[key] = ""
    os.environ.update(environment)
    from alembic import command
    from alembic.config import Config
    from company_os import models as m
    from company_os.db import SessionLocal, engine
    from company_os.organization import seed
    from sqlalchemy import select, text

    command.upgrade(Config(str(root / "alembic.ini")), "head")
    with SessionLocal() as session:
        seed(session)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    script = str(Path(__file__).resolve())
    executable = sys._base_executable
    record_id = None
    before_restart = None
    signed = None
    design = None
    project_id = None

    with (private / "processes.log").open("ab") as logs:

        def worker(flag="--worker"):
            subprocess.run(
                [executable, script, flag],
                cwd=root,
                env=environment,
                stdout=logs,
                stderr=logs,
                timeout=90,
                check=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        def state(client):
            response = client.get(f"/project-drafts/{record_id}/requirements-review")
            response.raise_for_status()
            return response.json()

        for iteration in range(5):
            process = subprocess.Popen(
                [executable, script, "--serve", str(port)],
                cwd=root,
                env=environment,
                stdout=logs,
                stderr=logs,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=15) as client:
                    deadline = time.monotonic() + 60
                    while True:
                        try:
                            if client.get("/health/live").status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        if time.monotonic() >= deadline or process.poll() is not None:
                            raise RuntimeError(
                                f"Private API did not start; inspect {private / 'processes.log'}"
                            )
                        time.sleep(0.25)
                    response = client.post(
                        "/auth/login",
                        json={"email": environment["OWNER_EMAIL"], "password": environment["OWNER_PASSWORD"]},
                    )
                    response.raise_for_status()
                    client.headers["Authorization"] = "Bearer " + response.json()["access_token"]
                    if iteration == 0:
                        clients = client.get("/state").json()["clients"]
                        response = client.post(
                            "/project-drafts",
                            json={
                                "request_id": str(uuid4()),
                                "form": {
                                    "client_id": clients[0]["id"],
                                    "title": "Disposable Task Management recovery",
                                    "text": "Create, view, update, complete and delete tasks with SQLite persistence and bounded API input validation.",
                                    "review_before_planning": True,
                                },
                            },
                        )
                        response.raise_for_status()
                        draft = response.json()
                        record_id = draft["id"]
                        response = client.post(
                            f"/project-drafts/{record_id}/submit",
                            json={"request_id": str(uuid4()), "version": draft["version"]},
                        )
                        response.raise_for_status()
                        with SessionLocal() as session:
                            row = session.get(m.BusinessRecord, record_id)
                            model = session.scalar(
                                select(m.ModelConfig)
                                .join(m.Provider)
                                .where(m.Provider.kind == "mock")
                                .order_by(m.ModelConfig.quality.desc())
                            )
                            row.data = {**row.data, "form": {**row.data["form"], "lead_model_id": model.id}}
                            session.get(m.Workflow, row.data["workflow_id"]).mode = "mock"
                            session.get(m.Requirement, row.data["requirement_id"]).mode = "mock"
                            session.commit()
                        worker()
                        assert len(state(client)["current"]["reviews"]) == 1
                        worker("--crash-after-claim")
                        before_restart = state(client)
                    elif iteration == 1:
                        assert state(client) == before_restart
                        time.sleep(1.2)
                        worker()
                        reviewed = state(client)
                        assert len(reviewed["current"]["reviews"]) == 2 and not reviewed["approved"]
                        scope = reviewed["current"]["scope"]
                        scope["acceptance_criteria"] = [
                            "CRUD persists across restart",
                            "Invalid input preserves stored records",
                        ]
                        response = client.post(
                            f"/project-drafts/{record_id}/requirements-revision",
                            json={
                                "request_id": str(uuid4()),
                                "version": reviewed["draft_version"],
                                "scope": scope,
                                "decisions": {
                                    item["id"]: {
                                        "action": "reject",
                                        "reason": "Owner keeps original disposable sample scope",
                                    }
                                    for item in reviewed["improvements"]
                                },
                                "answers": {
                                    item[
                                        "id"
                                    ]: "Single owner, local disposable target and zero external costs"
                                    for item in reviewed["questions"]
                                },
                            },
                        )
                        response.raise_for_status()
                        revised = state(client)
                        # Pause only this private fixture company so architecture cannot advance during restart.
                        with SessionLocal() as session:
                            org = session.scalar(select(m.Organization))
                            org.paused = True
                            session.commit()
                        response = client.post(
                            f"/project-drafts/{record_id}/requirements-approve",
                            json={
                                "request_id": str(uuid4()),
                                "version": revised["draft_version"],
                                "scope_hash": revised["current"]["scope_hash"],
                                "owner_authored": True,
                            },
                        )
                        response.raise_for_status()
                        signed = state(client)
                        assert signed["approved"]
                    elif iteration == 2:
                        assert state(client) == signed
                        with SessionLocal() as session:
                            runs = list(session.scalars(select(m.ModelRun)))
                            assert len(runs) == 2 and {run.step_name for run in runs} == {
                                "lead_intake",
                                "Business Analyst",
                            }
                            assert len(list(session.scalars(select(m.Approval)))) == 1
                            assert not session.scalar(select(m.Project.id))
                            assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
                            assert not session.execute(text("PRAGMA foreign_key_check")).all()
                            assert session.execute(text("PRAGMA journal_mode")).scalar() == "wal"
                            session.scalar(select(m.Organization)).paused = False
                            row = session.get(m.BusinessRecord, record_id)
                            session.get(m.Workflow, row.data["workflow_id"]).mode = "mock"
                            session.commit()
                        worker()
                        with SessionLocal() as session:
                            design = session.get(m.BusinessRecord, record_id).data["architecture_design"]
                            assert len(design["documents"]) == 2 and design["basis"] == "FIXTURE_TESTED"
                    elif iteration == 3:
                        with SessionLocal() as session:
                            row = session.get(m.BusinessRecord, record_id)
                            assert row.data["architecture_design"] == design
                            assert len(list(session.scalars(select(m.ModelRun)))) == 3
                        for _ in range(3):
                            worker()
                        with SessionLocal() as session:
                            proposal = session.scalar(select(m.Proposal))
                            assert proposal.content["architecture_manifest"] == design
                            body = {
                                "version": proposal.version,
                                "content_hash": proposal.content_hash,
                                "selection": design["design"]["options"][1]["name"],
                            }
                        response = client.post(f"/proposals/{proposal.id}/approve", json=body)
                        response.raise_for_status()
                        project_id = response.json()["id"]
                        retry = client.post(f"/proposals/{proposal.id}/approve", json=body)
                        retry.raise_for_status()
                        assert retry.json()["id"] == project_id
                    else:
                        from company_os.workflows import project_authority

                        with SessionLocal() as session:
                            project = session.get(m.Project, project_id)
                            project_authority(session, project)
                            assert project.selected_alternative == design["design"]["options"][1]["name"]
                            assert len(list(session.scalars(select(m.Approval)))) == 3
                            assert len(list(session.scalars(select(m.Project)))) == 1
                            assert len(list(session.scalars(select(m.ModelRun)))) == 6
                            assert session.execute(text("PRAGMA integrity_check")).scalar() == "ok"
                            assert not session.execute(text("PRAGMA foreign_key_check")).all()
            finally:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
    engine.dispose()
    print(
        json.dumps(
            {
                "evidence": "Actual five API processes, abrupt claimed-worker exit, resumed review/design workers and saved owner selection; deterministic model adapters only",
                "sqlite": "integrity/FKs/WAL verified",
                "scope_sha256": hashlib.sha256(json.dumps(signed, sort_keys=True).encode()).hexdigest(),
                "reviews": 2,
                "approvals": 3,
                "architecture_documents": 2,
                "architecture_manifest_sha256": design["manifest_hash"],
                "duplicate_model_runs": 0,
                "projects_created": 1,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
