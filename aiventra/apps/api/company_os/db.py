import time
import uuid
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


def uid() -> str:
    return str(uuid.uuid4())


def now() -> int:
    return int(time.time())


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    args = {"check_same_thread": False, "timeout": 30} if url.startswith("sqlite") else {}
    result = create_engine(url, connect_args=args, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(result, "connect")
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return result


def make_application_engine(config):
    if (
        config.required_database_backend
        and make_url(config.database_url).get_backend_name() != config.required_database_backend
    ):
        raise ValueError(
            "Configured database backend does not match REQUIRED_DATABASE_BACKEND; startup refused"
        )
    if getattr(config, "isolated_postgres_ci", False):
        import os
        import re

        url = make_url(config.database_url)
        name = os.environ.get("BROWSER_CI_DATABASE", "")
        if not (
            config.isolated_test_environment
            and config.app_env == "test"
            and os.environ.get("CI") == "true"
            and re.fullmatch(r"browser_ci_\d+_\d+", name)
            and url.get_backend_name() == "postgresql"
            and url.host == "database"
            and url.database == name
        ):
            raise ValueError("PostgreSQL browser tests require the dedicated disposable CI database")
        return make_engine(config.database_url)
    if getattr(config, "isolated_test_environment", False) or getattr(
        config, "fixture_catalog_enabled", False
    ):
        from pathlib import Path

        url = make_url(config.database_url)
        root = Path(__file__).resolve().parents[3] / "data" / "pytest-temp"
        path = Path(url.database or "").resolve()
        if (
            not config.isolated_test_environment
            or config.app_env != "test"
            or url.get_backend_name() != "sqlite"
            or not path.is_relative_to(root.resolve())
            or path.name != "fixture.db"
            or path.parent == root.resolve()
        ):
            raise ValueError("Isolated tests require a private fixture.db under data/pytest-temp")
    return make_engine(config.database_url)


settings().artifact_root.mkdir(parents=True, exist_ok=True)
settings().repository_root.mkdir(parents=True, exist_ok=True)
engine = make_application_engine(settings())
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def session_dependency() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session
