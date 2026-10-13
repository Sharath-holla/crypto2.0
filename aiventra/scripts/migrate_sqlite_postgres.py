"""Explicit offline transfer; destination URL is read privately from an env reference."""

import argparse
import json
import os
from pathlib import Path

from company_os.database_transfer import TransferRejected, transfer, verify_candidate
from sqlalchemy import create_engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("data/company.db"))
    parser.add_argument("--destination-env", default="MIGRATION_DATABASE_URL")
    parser.add_argument("--backup-root", type=Path, default=Path("data/backups"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-services-stopped", action="store_true")
    parser.add_argument("--verify-backup", type=Path)
    args = parser.parse_args()
    url = os.environ.get(args.destination_env, "")
    if not url:
        parser.exit(2, "Destination environment reference is not configured; no data changed.\n")
    engine = None
    try:
        engine = create_engine(url, pool_pre_ping=True, hide_parameters=True)
        if engine.dialect.name != "postgresql":
            raise TransferRejected("Destination must be PostgreSQL")
        if args.verify_backup:
            if args.apply:
                raise TransferRejected("Verification cannot be combined with apply")
            report = verify_candidate(args.verify_backup, engine)
        else:
            report = transfer(
                args.source,
                engine,
                args.backup_root,
                apply=args.apply,
                offline_confirmed=args.confirm_services_stopped,
            )
        print(json.dumps(report, sort_keys=True))
    except TransferRejected as error:
        parser.exit(2, str(error) + ". Active database configuration was not changed.\n")
    except Exception:
        # SQLAlchemy/driver exceptions can contain URL, ciphertext and SQL data.
        parser.exit(
            2,
            "Database transfer failed; check private connectivity, permissions, schema and vault configuration. Active database configuration was not changed.\n",
        )
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
