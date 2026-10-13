"""Actual PostgreSQL migration/rollback fixture. Creates isolated CI databases only."""

import base64
import json
import os
from pathlib import Path
from unittest.mock import patch

from alembic import command
from company_os import database_transfer as transfer
from company_os import models as m
from company_os.config import settings
from company_os.credentials import save_secret
from company_os.db import make_engine, uid
from company_os.organization import seed
from company_os.security import audit, verify_audit
from company_os.semantic_memory import put
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session


def fixture(path):
    engine = make_engine("sqlite:///" + str(path))
    with engine.begin() as connection:
        command.upgrade(transfer.migration_config(connection), "head")
    settings().provider_secret_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    with Session(engine) as session:
        org = seed(session)
        org_id = org.id
        owner = session.scalar(select(m.User).where(m.User.role == "owner"))
        client = session.scalar(select(m.Client).where(m.Client.org_id == org_id))
        conversation = m.Conversation(
            org_id=org_id, owner_id=owner.id, client_id=client.id, title="Transfer fixture"
        )
        session.add(conversation)
        session.flush()
        turn = m.ConversationTurn(
            org_id=org_id,
            conversation_id=conversation.id,
            request_id=uid(),
            request_hash="a" * 64,
            position=1,
            content="Preserve this conversation and free-provider wait",
        )
        session.add(turn)
        session.flush()
        workflow = m.Workflow(
            org_id=org_id,
            kind="conversation",
            mode="live",
            conversation_turn_id=turn.id,
            status="waiting_for_free_provider",
            wait_context={"revision": 1, "reason": "No local model"},
        )
        session.add(workflow)
        budget = session.scalar(select(m.Budget).where(m.Budget.org_id == org_id))
        budget.limit_micro, budget.spent_micro, budget.reserved_micro = 10**12, 4_000_000_000, 3_000_000_000
        provider = m.Provider(
            org_id=org_id, name="Encrypted fixture", kind="openai", base_url="https://api.openai.com/v1"
        )
        session.add(provider)
        session.flush()
        save_secret(session, provider, "synthetic-transfer-fixture-value")
        entry = put(
            session,
            org_id,
            "manual:transfer",
            "Recovery",
            "architecture_decision",
            "Preserve durable state",
            visibility="organization",
        )
        session.flush()
        version = session.scalar(select(m.MemoryVersion).where(m.MemoryVersion.entry_id == entry.id))
        chunk = session.scalar(select(m.MemoryChunk).where(m.MemoryChunk.version_id == version.id))
        chunk.fingerprint = "deterministic_transfer_fixture"
        chunk.embedding = [0.123456789] * 384
        audit(session, org_id, "fixture", "verification.transfer", conversation.id)
        session.commit()
        assert verify_audit(session, org_id)["valid"]
    engine.dispose()


def main():
    if os.environ.get("CI") != "true" or settings().app_env == "production":
        raise RuntimeError("Use only disposable CI infrastructure")
    admin = create_engine(settings().database_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    assert admin.dialect.name == "postgresql"
    root = Path("data/pytest-temp/transfer-" + uid())
    root.mkdir(parents=True)
    source = root / "source.db"
    fixture(source)
    database = "transfer_" + uid().replace("-", "")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    target = create_engine(admin.url.set(database=database), hide_parameters=True)
    try:
        dry = transfer.transfer(source, target, root / "backups")
        assert not dry["applied"] and not dry["active_database_changed"]
        assert inspect(target).get_table_names() == [], "Dry run changed destination"
        original_copy = transfer.copy_rows

        def interrupted(original, destination):
            original_copy(original, destination)
            raise RuntimeError("Injected interruption after copy, before commit")

        with patch.object(transfer, "copy_rows", interrupted):
            try:
                transfer.transfer(source, target, root / "backups", apply=True, offline_confirmed=True)
            except RuntimeError as error:
                assert "Injected interruption" in str(error)
            else:
                raise AssertionError("Injected failure was not propagated")
        assert inspect(target).get_table_names() == [], "Failed transfer did not roll back DDL/data"
        # Also cover an already migrated empty destination, without relaxing
        # normal FKs or the append-only audit trigger during import.
        with target.begin() as connection:
            command.upgrade(transfer.migration_config(connection), "head")
        report = transfer.transfer(source, target, root / "backups", apply=True, offline_confirmed=True)
        assert report["applied"] and not report["active_database_changed"]
        assert transfer.verify_candidate(Path(report["backup"]), target)["verified"]
        with target.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT embedding <=> embedding FROM memory_chunks WHERE embedding IS NOT NULL LIMIT 1"
                    )
                )
                < 0.00001
            )
        try:
            transfer.transfer(source, target, root / "backups", apply=True, offline_confirmed=True)
        except transfer.TransferRejected as error:
            assert "contains records" in str(error)
        else:
            raise AssertionError("Occupied destination was overwritten")
        assert transfer.verify_candidate(Path(report["backup"]), target)["verified"]
        wrong = settings().provider_secret_key
        settings().provider_secret_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        try:
            transfer.verify_candidate(Path(report["backup"]), target)
        except transfer.TransferRejected as error:
            assert "Vault key" in str(error)
        else:
            raise AssertionError("Wrong vault key accepted")
        finally:
            settings().provider_secret_key = wrong
        print(
            json.dumps(
                {
                    "verified_tables": len(report["source_tables"]),
                    "dry_run_rollback": True,
                    "failure_rollback": True,
                    "occupied_refused": True,
                    "vault_checked": True,
                    "audit_preserved": True,
                    "pgvector_preserved": True,
                    "source_retained": source.is_file(),
                }
            )
        )
    finally:
        target.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{database}" WITH (FORCE)'))
        admin.dispose()


if __name__ == "__main__":
    main()
