"""Offline, additive SQLite -> PostgreSQL transfer. Never selects the active DB.

Only a new or migrated-but-empty public schema is accepted. PostgreSQL DDL and
all copied rows share one transaction; no constraints or audit guards are disabled.
"""

import base64
import hashlib
import json
import math
import os
import sqlite3
import struct
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.orm import Session

from .credentials import vault_key
from .db import Base, uid
from .models import Organization, ProviderCredential
from .security import verify_audit


class TransferRejected(ValueError):
    """Safe operator-facing error: never include URLs, SQL parameters or records."""


def migration_config(connection=None) -> Config:
    config = Config("alembic.ini")
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def head() -> str:
    return ScriptDirectory.from_config(migration_config()).get_current_head()


def readonly_engine(path: Path):
    uri = path.resolve().as_uri() + "?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))


@contextmanager
def source_snapshot(source: Path, backup_root: Path, *, freeze: bool):
    if not source.is_file():
        raise TransferRejected("Source SQLite file does not exist")
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = backup_root / ("sqlite-transfer-" + uid() + ".db")
    descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    locker = None
    try:
        if freeze:
            locker = sqlite3.connect(source.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
            # Block other writers throughout backup, import and validation. This
            # is not a substitute for stopping API/worker before a later cutover.
            locker.execute("BEGIN IMMEDIATE")
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
            with sqlite3.connect(backup) as candidate:
                original.backup(candidate)
                if candidate.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise TransferRejected("SQLite integrity check failed")
                if candidate.execute("PRAGMA foreign_key_check").fetchone():
                    raise TransferRejected("SQLite contains broken foreign keys")
        yield backup
    finally:
        if locker is not None:
            locker.rollback()
            locker.close()


def check_schema(connection):
    inspector = inspect(connection)
    expected = set(Base.metadata.tables) | {"alembic_version"}
    if set(inspector.get_table_names()) != expected:
        raise TransferRejected("Database tables differ from the current application schema")
    if connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all() != [head()]:
        raise TransferRejected("Database must be migrated to the current Alembic head")
    for table in Base.metadata.sorted_tables:
        if {c["name"] for c in inspector.get_columns(table.name)} != set(table.columns.keys()):
            raise TransferRejected("Database columns differ from the current application schema")
        if inspector.get_pk_constraint(table.name)["constrained_columns"] != list(
            table.primary_key.columns.keys()
        ):
            raise TransferRejected("Database primary keys differ from the application schema")
        expected_fks = {
            (
                tuple(c.parent.name for c in constraint.elements),
                constraint.elements[0].column.table.name,
                tuple(c.column.name for c in constraint.elements),
            )
            for constraint in table.foreign_key_constraints
        }
        stored_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
            for fk in inspector.get_foreign_keys(table.name)
        }
        if expected_fks != stored_fks:
            raise TransferRejected("Database foreign keys differ from the application schema")


def normalize(value, *, vector=False):
    if vector and value is not None:
        # pgvector stores IEEE float32; compare the exact representable values.
        result = [struct.unpack("!f", struct.pack("!f", float(v)))[0] for v in value]
        if len(result) != 384 or not all(math.isfinite(v) for v in result):
            raise TransferRejected("Invalid semantic vector")
        return result
    return value


def inventory(connection) -> dict:
    result = {}
    for table in Base.metadata.sorted_tables:
        digest = hashlib.sha256()
        count = 0
        rows = connection.execute(select(table).order_by(*table.primary_key.columns))
        for row in rows.mappings():
            values = {
                column.name: normalize(
                    row[column.name], vector=table.name == "memory_chunks" and column.name == "embedding"
                )
                for column in table.columns
            }
            digest.update(json.dumps(values, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
            digest.update(b"\n")
            count += 1
        result[table.name] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def validate_records(connection):
    with Session(bind=connection) as session:
        for org_id in session.scalars(select(Organization.id)):
            if not verify_audit(session, org_id)["valid"]:
                raise TransferRejected("Append-only audit chain verification failed")
        credentials = session.scalars(select(ProviderCredential)).all()
        if credentials:
            key = vault_key()
            for record in credentials:
                payload = base64.urlsafe_b64decode(record.ciphertext)
                associated = (
                    f"aiventra-provider:{record.org_id}:{record.provider_id}:{record.version}".encode()
                )
                try:
                    AESGCM(key).decrypt(payload[:12], payload[12:], associated)
                except Exception:
                    raise TransferRejected("Vault key cannot decrypt existing credentials") from None


def prepare_destination(connection):
    if connection.dialect.name != "postgresql":
        raise TransferRejected("Destination must be PostgreSQL")
    if connection.scalar(text("SELECT current_schema()")) != "public":
        raise TransferRejected("Destination must use the public schema")
    if not connection.scalar(text("SELECT pg_try_advisory_xact_lock(73469481021)")):
        raise TransferRejected("Another database transfer is running")
    tables = inspect(connection).get_table_names()
    if tables:
        check_schema(connection)
        # Prevent a writer racing the empty check and import. Normal constraints
        # stay active. Existing records are never merged, deleted or replaced.
        names = ", ".join(connection.dialect.identifier_preparer.quote(n) for n in sorted(tables))
        connection.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE"))
        if any(connection.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables):
            raise TransferRejected("Destination contains records; use a new empty database")
    else:
        if not connection.scalar(text("SELECT count(*) FROM pg_available_extensions WHERE name='vector'")):
            raise TransferRejected("pgvector is not installed on the PostgreSQL server")
        command.upgrade(migration_config(connection), "head")
        check_schema(connection)
    if not connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='vector'")):
        raise TransferRejected("Destination pgvector extension is unavailable")


def copy_rows(source, destination):
    for table in Base.metadata.sorted_tables:
        result = source.execute(select(table).order_by(*table.primary_key.columns)).mappings()
        for batch in result.partitions(250):
            destination.execute(table.insert(), [dict(row) for row in batch])


def verify_candidate(backup: Path, destination) -> dict:
    if not backup.is_file():
        raise TransferRejected("Backup file does not exist")
    source = readonly_engine(backup)
    try:
        with source.connect() as original, destination.connect() as target:
            target = target.execution_options(isolation_level="REPEATABLE READ")
            check_schema(original)
            check_schema(target)
            before, after = inventory(original), inventory(target)
            if before != after:
                raise TransferRejected("Destination row counts or content digests differ")
            validate_records(target)
            return {"tables": before, "verified": True}
    finally:
        source.dispose()


def transfer(source: Path, destination, backup_root: Path, *, apply=False, offline_confirmed=False) -> dict:
    if apply and not offline_confirmed:
        raise TransferRejected("Stop API/worker and explicitly confirm offline transfer")
    if destination.dialect.name != "postgresql":
        raise TransferRejected("Destination must be PostgreSQL")
    with source_snapshot(source, backup_root, freeze=apply) as backup:
        snapshot = readonly_engine(backup)
        try:
            with snapshot.connect() as original:
                check_schema(original)
                validate_records(original)
                before = inventory(original)
                report = {
                    "format": 1,
                    "backup": str(backup.resolve()),
                    "revision": head(),
                    "source_tables": before,
                    "applied": False,
                    "active_database_changed": False,
                }
                # Even a dry run exercises migrations/permissions/empty checks,
                # then rolls back every destination change.
                with destination.connect() as target:
                    target = target.execution_options(isolation_level="SERIALIZABLE")
                    transaction = target.begin()
                    try:
                        target.execute(text("SET LOCAL lock_timeout = '5s'"))
                        target.execute(text("SET LOCAL statement_timeout = '120s'"))
                        prepare_destination(target)
                        if apply:
                            copy_rows(original, target)
                            if inventory(target) != before:
                                raise TransferRejected("Copied row counts or content digests differ")
                            validate_records(target)
                            transaction.commit()
                            report["applied"] = True
                        else:
                            transaction.rollback()
                    except Exception:
                        transaction.rollback()
                        raise
                return report
        finally:
            snapshot.dispose()
