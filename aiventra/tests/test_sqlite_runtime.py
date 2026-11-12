"""Real SQLite locking and abrupt process recovery; all files are disposable fixtures."""

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from company_os.db import make_engine
from sqlalchemy import text


def test_sqlite_wal_busy_timeout_serialized_writers_and_reopen(tmp_path):
    path = tmp_path / "concurrency.db"
    engine = make_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30000
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        conn.exec_driver_sql("CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)")
        conn.exec_driver_sql("INSERT INTO counter VALUES (1, 0)")

    def write(_):
        for _ in range(25):
            with engine.begin() as conn:
                conn.exec_driver_sql("UPDATE counter SET value=value+1 WHERE id=1")

    # A real WAL reader sees a stable snapshot while independent connections serialize writes.
    reader = sqlite3.connect(path)
    reader.execute("BEGIN")
    assert reader.execute("SELECT value FROM counter").fetchone()[0] == 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(8)))
    assert reader.execute("SELECT value FROM counter").fetchone()[0] == 0
    reader.rollback()
    reader.close()
    engine.dispose()
    recovered = make_engine(f"sqlite:///{path}")
    with recovered.connect() as conn:
        assert conn.execute(text("SELECT value FROM counter")).scalar() == 200
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    recovered.dispose()


def test_sqlite_process_death_rolls_back_uncommitted_write(tmp_path):
    path = tmp_path / "recovery.db"
    engine = make_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE records (id INTEGER PRIMARY KEY, value TEXT)")
        conn.exec_driver_sql("INSERT INTO records VALUES (1, 'durable')")
    engine.dispose()
    # Fixed test code, never repository/generated agent code; no API/worker execution involved.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sqlite3,sys,os; c=sqlite3.connect(sys.argv[1]); "
            "c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE records SET value='uncommitted'\"); os._exit(7)",
            str(path),
        ],
        check=False,
        timeout=10,
        capture_output=True,
    )
    assert child.returncode == 7
    recovered = make_engine(f"sqlite:///{path}")
    with recovered.connect() as conn:
        assert conn.exec_driver_sql("SELECT value FROM records").scalar() == "durable"
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    recovered.dispose()
