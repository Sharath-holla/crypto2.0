"""Read-only digest of the developer registry before/after isolated browser tests."""

import hashlib
import json
import sqlite3
from pathlib import Path

from company_os.config import settings
from sqlalchemy.engine import make_url

url = make_url(settings().database_url)
if url.get_backend_name() != "sqlite":
    print(json.dumps({"backend": "postgresql", "check": "separate compatibility CI environment"}))
else:
    path = Path(url.database).resolve()
    if not path.exists():
        print(json.dumps({"backend": "sqlite", "present": False}))
    else:
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            output = {"backend": "sqlite", "present": True}
            for table in ("providers", "model_configs", "provider_credentials"):
                rows = connection.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
                output[table] = {
                    "count": len(rows),
                    "digest": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                }
            print(json.dumps(output, sort_keys=True))
