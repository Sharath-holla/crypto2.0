"""Protected registry provenance; names never determine authorization or visibility."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import object_session

from . import models as m
from .config import settings

KIND = "registry_provenance"


def identity(provider):
    return str(uuid5(NAMESPACE_URL, f"aiventra:registry:{provider.org_id}:{provider.id}"))


def facts(session, provider):
    return session.scalar(
        select(m.BusinessRecord.data).where(
            m.BusinessRecord.id == identity(provider),
            m.BusinessRecord.org_id == provider.org_id,
            m.BusinessRecord.kind == KIND,
        )
    ) or {"source": "legacy_registration", "environment": "unknown"}


def classify(session, provider, source, evidence=None):
    row = session.get(m.BusinessRecord, identity(provider))
    if row and (row.org_id != provider.org_id or row.kind != KIND):
        raise ValueError("Registry provenance scope conflict")
    if row is None:
        row = m.BusinessRecord(
            id=identity(provider), org_id=provider.org_id, kind=KIND, title="Registry origin", data={}
        )
        session.add(row)
    row.data = {
        "provider_id": provider.id,
        "source": source,
        "environment": "isolated_test" if settings().isolated_test_environment else "workspace",
        "evidence": evidence or {},
    }
    session.flush()


def visible(session, provider):
    return facts(session, provider)["source"] not in {"test_fixture", "system_example"} or (
        settings().isolated_test_environment and settings().fixture_catalog_enabled
    )


def inference_fixture(model):
    session = object_session(model) if isinstance(model, m.ModelConfig) else None
    if session is None:
        return False
    provider = session.get(m.Provider, model.provider_id)
    return bool(provider and facts(session, provider)["source"] in {"test_fixture", "system_example"})
