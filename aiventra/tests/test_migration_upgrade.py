import os
import sqlite3
import subprocess
import sys

from company_os.db import uid
from company_os.health import heartbeat
from sqlalchemy import text


def migrate(path, revision):
    environment = dict(os.environ)
    environment["DATABASE_URL"] = "sqlite:///" + str(path)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_upgrade_preserves_preexisting_workflow_and_backfills_wait_context(company):
    path = company["root"] / "previous-schema.db"
    migrate(path, "b411d790aa01")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO organizations(id,created_at,name,paused,deployments_paused,version,audit_head) VALUES('preserved',1,'Preserved owner data',0,1,1,'head')"
        )
        connection.execute(
            "INSERT INTO workflows(id,org_id,created_at,kind,mode,revision,status,step,attempts,max_attempts,deadline_at,lease_until,lease_token,last_error) VALUES('workflow','preserved',1,'consulting','live',1,'queued',2,0,3,9999999999,0,'','')"
        )
    migrate(path, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT step,wait_context FROM workflows WHERE id='workflow'"
        ).fetchone() == (2, "{}")
        assert (
            connection.execute("SELECT name FROM organizations WHERE id='preserved'").fetchone()[0]
            == "Preserved owner data"
        )


def test_money_upgrade_preserves_large_sqlite_balances_and_audit_triggers(company):
    path = company["root"] / "money-upgrade.db"
    migrate(path, "e9c9f1ed55a6")
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO organizations(id,created_at,name,paused,deployments_paused,version,audit_head) VALUES('money-org',1,'Retained data',0,1,1,'head')"
        )
        connection.execute(
            "INSERT INTO budgets(id,org_id,created_at,scope,limit_micro,spent_micro,reserved_micro,version) VALUES('money','money-org',1,'retained',1000000000000,4000000000,3000000000,1)"
        )
    migrate(path, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT limit_micro,spent_micro,reserved_micro FROM budgets WHERE id='money'"
        ).fetchone() == (1_000_000_000_000, 4_000_000_000, 3_000_000_000)
        assert (
            connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name IN ('audit_no_update','audit_no_delete')"
            ).fetchone()[0]
            == 2
        )


def test_readiness_checks_worker_and_schema_revision(http, company):
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    with company["factory"]() as session:
        session.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        session.execute(text("INSERT INTO alembic_version VALUES(:head)"), {"head": head})
        session.commit()
    assert http.get("/health/ready").status_code == 503
    with company["factory"]() as session:
        heartbeat(session, uid())
    assert http.get("/health/ready").status_code == 200
    with company["factory"]() as session:
        session.execute(text("UPDATE alembic_version SET version_num='stale'"))
        session.commit()
    assert http.get("/health/ready").status_code == 503
