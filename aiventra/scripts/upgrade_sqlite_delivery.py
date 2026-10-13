"""Back up SQLite and apply the additive delivery migration without changing old rows."""

import argparse
import hashlib
import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from company_os.config import settings
from company_os.database_transfer import source_snapshot
from sqlalchemy import MetaData, create_engine, inspect, select, text
from sqlalchemy.engine import make_url


def inventory_existing(connection, names):
    metadata = MetaData()
    metadata.reflect(connection, only=names)
    result = {}
    for name in sorted(names):
        table = metadata.tables[name]
        rows = connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()
        hasher, count = hashlib.sha256(), 0
        for row in rows:
            hasher.update(json.dumps(dict(row), sort_keys=True, default=str).encode())
            hasher.update(b"\n")
            count += 1
        result[name] = {"rows": count, "sha256": hasher.hexdigest()}
    return result


def upgrade(url, backup_root):
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database or parsed.database == ":memory:":
        raise ValueError("This operator tool only upgrades an existing SQLite file")
    source = Path(parsed.database)
    with source_snapshot(source, backup_root, freeze=False) as backup:
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                names = [name for name in inspect(connection).get_table_names() if name != "alembic_version"]
                previous = inventory_existing(connection, names)
                revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision not in {"a31d07edc482", "c72e51d9af04", "d45f80a6ce12"}:
                    raise ValueError("Unexpected source revision; inspect pending migrations first")
                config = Config("alembic.ini")
                config.attributes["connection"] = connection
                command.upgrade(config, "d45f80a6ce12")
                if inventory_existing(connection, names) != previous:
                    raise ValueError("Existing application records changed during additive migration")
                if connection.scalar(text("PRAGMA integrity_check")) != "ok":
                    raise ValueError("SQLite integrity check failed")
                if connection.execute(text("PRAGMA foreign_key_check")).first():
                    raise ValueError("SQLite foreign-key verification failed")
                connection.commit()
                return {
                    "backup": str(backup),
                    "preserved_tables": len(previous),
                    "preserved_rows": sum(item["rows"] for item in previous.values()),
                    "previous_digest": hashlib.sha256(
                        json.dumps(previous, sort_keys=True).encode()
                    ).hexdigest(),
                    "revision": "d45f80a6ce12",
                    "integrity": "ok",
                    "foreign_key_violations": 0,
                }
        finally:
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-services-stopped", action="store_true", required=True)
    parser.parse_args()
    try:
        result = upgrade(settings().database_url, Path("data/backups"))
    except Exception:
        raise SystemExit(
            "Delivery schema upgrade refused; existing data/backup retained. Inspect privately."
        ) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
