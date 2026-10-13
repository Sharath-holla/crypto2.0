import sqlite3

import pytest
from company_os.database_transfer import (
    TransferRejected,
    check_schema,
    inventory,
    normalize,
    readonly_engine,
    source_snapshot,
    transfer,
    validate_records,
)
from sqlalchemy import create_engine, text

from tests.test_migration_upgrade import migrate


def test_snapshot_preserves_source_and_blocks_writers(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE records(id INTEGER PRIMARY KEY, content TEXT)")
        connection.execute("INSERT INTO records VALUES(1, 'preserved')")
    with source_snapshot(source, tmp_path / "backups", freeze=True) as backup:
        with sqlite3.connect(backup) as connection:
            assert connection.execute("SELECT content FROM records").fetchone()[0] == "preserved"
        with sqlite3.connect(source, timeout=0.01) as connection:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                connection.execute("INSERT INTO records VALUES(2, 'racing writer')")
    with sqlite3.connect(source) as connection:
        connection.execute("INSERT INTO records VALUES(2, 'released lock')")
    assert backup.is_file()  # Retained for recovery, never removed on completion.


def test_snapshot_refuses_broken_foreign_keys(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.executescript(
            "CREATE TABLE parent(id INTEGER PRIMARY KEY);"
            "CREATE TABLE child(parent_id INTEGER REFERENCES parent(id));"
            "INSERT INTO child VALUES(99);"
        )
    with pytest.raises(TransferRejected, match="foreign keys"):
        with source_snapshot(source, tmp_path / "backups", freeze=False):
            pass
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_missing_source_never_creates_empty_database(tmp_path):
    source = tmp_path / "absent.db"
    with pytest.raises(TransferRejected, match="does not exist"):
        with source_snapshot(source, tmp_path / "backups", freeze=False):
            pass
    assert not source.exists()


def test_schema_version_and_extra_tables_rejected(tmp_path):
    source = tmp_path / "source.db"
    migrate(source, "head")
    engine = readonly_engine(source)
    with engine.connect() as connection:
        check_schema(connection)
        assert len(inventory(connection)) == 56
    engine.dispose()
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE alembic_version SET version_num='stale'")
    engine = readonly_engine(source)
    with engine.connect() as connection, pytest.raises(TransferRejected, match="Alembic head"):
        check_schema(connection)
    engine.dispose()
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unknown_records(id TEXT)")
    engine = readonly_engine(source)
    with engine.connect() as connection, pytest.raises(TransferRejected, match="tables differ"):
        check_schema(connection)
    engine.dispose()


def test_readonly_engine_cannot_mutate_source(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE records(id INTEGER)")
    engine = readonly_engine(source)
    with engine.connect() as connection, pytest.raises(Exception, match="readonly"):
        connection.execute(text("INSERT INTO records VALUES(1)"))
    engine.dispose()


def test_transfer_requires_postgres_and_explicit_offline_confirmation(tmp_path):
    engine = create_engine("sqlite://")
    with pytest.raises(TransferRejected, match="confirm offline"):
        transfer(tmp_path / "absent.db", engine, tmp_path / "backups", apply=True)
    with pytest.raises(TransferRejected, match="must be PostgreSQL"):
        transfer(tmp_path / "absent.db", engine, tmp_path / "backups")
    engine.dispose()


def test_vector_digest_uses_pgvector_precision_and_rejects_invalid_vectors():
    result = normalize([0.123456789] * 384, vector=True)
    assert result[0] != 0.123456789
    assert normalize(result, vector=True) == result
    for value in ([1.0], [float("nan")] * 384, [float("inf")] * 384):
        with pytest.raises(TransferRejected, match="Invalid semantic vector"):
            normalize(value, vector=True)


def test_migration_fixture_validates_vault_audit_and_all_tables(tmp_path, monkeypatch):
    import base64
    import os

    from company_os.config import settings
    from company_os.models import MemoryChunk
    from sqlalchemy import select

    from scripts.verify_database_transfer import fixture

    # Keep the shared fixture's ephemeral vault key out of subsequent tests.
    monkeypatch.setattr(settings(), "provider_secret_key", settings().provider_secret_key)
    path = tmp_path / "fixture.db"
    fixture(path)
    engine = readonly_engine(path)
    with engine.connect() as connection:
        check_schema(connection)
        validate_records(connection)
        rows = inventory(connection)
        assert rows["conversation_turns"]["rows"] == 1
        assert rows["workflows"]["rows"] == 1
        assert rows["provider_credentials"]["rows"] == 1
        vectors = connection.scalars(select(MemoryChunk.embedding)).all()
        assert sum(vector is not None for vector in vectors) == 1
        assert any(vector is None for vector in vectors)  # Unindexed automatic captures coexist.
        settings().provider_secret_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
        with pytest.raises(TransferRejected, match="Vault key"):
            validate_records(connection)
    engine.dispose()
    with sqlite3.connect(path) as connection:
        # Deliberate corruption in a disposable fixture; production triggers stay enabled.
        connection.execute("UPDATE organizations SET audit_head='corrupted'")
    engine = readonly_engine(path)
    with engine.connect() as connection, pytest.raises(TransferRejected, match="audit chain"):
        validate_records(connection)
    engine.dispose()


def test_cli_does_not_disclose_driver_errors_or_destination_url(monkeypatch, capsys):
    import sys

    from scripts import migrate_sqlite_postgres

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-private-password SQL parameters ciphertext")

    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", "postgresql+psycopg://private:synthetic-private-password@localhost/private"
    )
    monkeypatch.setattr(sys, "argv", ["migrate_sqlite_postgres.py"])
    monkeypatch.setattr(migrate_sqlite_postgres, "create_engine", fail)
    with pytest.raises(SystemExit) as error:
        migrate_sqlite_postgres.main()
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "Database transfer failed" in output
    assert "synthetic-private-password" not in output
    assert "ciphertext" not in output


def test_cutover_backend_fence_prevents_silent_sqlite_startup():
    from types import SimpleNamespace

    from company_os.db import make_application_engine

    config = SimpleNamespace(database_url="sqlite://", required_database_backend="postgresql")
    with pytest.raises(ValueError, match="startup refused"):
        make_application_engine(config)
    config.required_database_backend = "sqlite"
    engine = make_application_engine(config)
    assert engine.dialect.name == "sqlite"
    engine.dispose()


def test_database_inspection_requires_owner_and_reports_actual_binding(http, company):
    from company_os.models import User
    from company_os.security import token_for

    response = http.get("/operations/database")
    assert response.status_code == 200
    facts = response.json()
    assert facts["backend"] == "sqlite"
    assert facts["connected"] and not facts["schema_current"]
    assert facts["pgvector_version"] is None and not facts["vector_index_available"]
    assert "password" not in response.text and "url" not in response.text
    with company["factory"]() as session:
        user = User(
            org_id=company["org"].id,
            role="client",
            client_id=company["client"].id,
            email="storage-client@test",
        )
        session.add(user)
        session.flush()
        token = token_for(user, session)
        session.commit()
    http.headers["Authorization"] = "Bearer " + token
    assert http.get("/operations/database").status_code == 403
    http.headers.pop("Authorization")
    assert http.get("/operations/database").status_code == 401
