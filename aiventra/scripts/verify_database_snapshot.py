"""Read-only whole-database recovery digest; never emits rows or connection URLs."""

import argparse
import hashlib
import json
import os

from company_os.config import settings
from company_os.database_transfer import check_schema, inventory, validate_records
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restored-database")
    args = parser.parse_args()
    url = make_url(settings().database_url)
    if args.restored_database:
        if os.environ.get("CI") != "true" or args.restored_database != "recovery_fixture":
            raise RuntimeError("Restoration comparison is restricted to the disposable CI database")
        url = url.set(database=args.restored_database)
    engine = create_engine(url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
            with connection.begin():
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                check_schema(connection)
                validate_records(connection)
                tables = inventory(connection)
                print(
                    json.dumps(
                        {
                            "tables": tables,
                            "sha256": hashlib.sha256(json.dumps(tables, sort_keys=True).encode()).hexdigest(),
                        },
                        sort_keys=True,
                    )
                )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
