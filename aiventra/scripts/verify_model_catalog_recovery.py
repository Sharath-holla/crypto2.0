"""Read-only persisted catalog/preferences digests across actual service restarts."""

import json

from company_os import models as m
from company_os.api_common import serialize
from company_os.db import SessionLocal, engine
from company_os.security import digest
from sqlalchemy import func, select

with SessionLocal() as session:
    models = [serialize(row) for row in session.scalars(select(m.ModelConfig).order_by(m.ModelConfig.id))]
    catalogs = [
        serialize(row)
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(m.BusinessRecord.kind == "provider_catalog")
            .order_by(m.BusinessRecord.id)
        )
    ]
    preferences = [
        {"id": row.id, "version": row.version, "status": row.status, "form": row.data["form"]}
        for row in session.scalars(
            select(m.BusinessRecord)
            .where(m.BusinessRecord.kind == "project_setup")
            .order_by(m.BusinessRecord.id)
        )
    ]
    print(
        json.dumps(
            {
                "backend": engine.dialect.name,
                "models": len(models),
                "catalogs": len(catalogs),
                "preferences": len(preferences),
                "models_digest": digest(models),
                "catalogs_digest": digest(catalogs),
                "preferences_digest": digest(preferences),
                "vault_records": session.scalar(select(func.count()).select_from(m.ProviderCredential)),
            },
            sort_keys=True,
        )
    )
