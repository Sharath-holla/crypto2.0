"""Audit-confirmed legacy browser registry quarantine. No record deletion or secret readback.

Default is a reviewable dry run. --apply first creates a SQLite online backup,
then appends protected provenance and audit records. Existing references survive.
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

from company_os import models as m
from company_os.config import settings
from company_os.db import SessionLocal
from company_os.registry_provenance import classify, facts
from company_os.security import audit
from company_os.staffing import lock_org
from sqlalchemy import select
from sqlalchemy.engine import make_url

CONTRACTS = (
    (
        r"Browser vault contract (\d{13})",
        "BROWSER_VAULT_TEST_API_KEY",
        "openai",
        "https://api.openai.com/v1",
        None,
    ),
    (
        r"Unreachable local catalog (\d{13})",
        "BROWSER_LOCAL_TEST_API_KEY",
        "ollama",
        "http://127.0.0.1:9",
        None,
    ),
    (
        r"Native browser contracts (\d{13})",
        "NATIVE_BROWSER_UNCONFIGURED_API_KEY",
        "openai",
        "https://api.openai.com/v1",
        "https://example.test/browser-contract",
    ),
    (
        r"Policy fixture (\d{13})",
        "ZERO_COST_BROWSER_UNCONFIGURED_API_KEY",
        "openai",
        "https://api.openai.com/v1",
        "https://example.test/unverified-free-claim",
    ),
)


def evidence(session, provider):
    for pattern, reference, kind, endpoint, price in CONTRACTS:
        match = re.fullmatch(pattern, provider.name)
        if not match or (provider.credential_env, provider.kind, provider.base_url) != (
            reference,
            kind,
            endpoint,
        ):
            continue
        stamp = int(match[1]) // 1000
        events = list(
            session.scalars(
                select(m.AuditEvent).where(
                    m.AuditEvent.org_id == provider.org_id, m.AuditEvent.subject == provider.id
                )
            )
        )
        registered = next(
            (e for e in events if e.action == "provider.registered" and abs(e.created_at - stamp) <= 2), None
        )
        if not registered or session.scalar(
            select(m.ProviderCredential.id).where(m.ProviderCredential.provider_id == provider.id)
        ):
            return None
        import os

        if os.environ.get(reference):
            return None  # A credential reference in use requires owner review.
        models = list(session.scalars(select(m.ModelConfig).where(m.ModelConfig.provider_id == provider.id)))
        if price:
            if len(models) != 1 or models[0].price_source != price:
                return None
            model = models[0]
            if kind == "openai" and reference.startswith("NATIVE_") and model.identifier != provider.name:
                return None
            if reference.startswith("ZERO_") and not re.fullmatch(r"claimed-free-\d{13}", model.identifier):
                return None
            proof = session.scalar(
                select(m.AuditEvent.id).where(
                    m.AuditEvent.org_id == provider.org_id,
                    m.AuditEvent.subject == model.id,
                    m.AuditEvent.action == "model.registered",
                    m.AuditEvent.created_at >= stamp,
                    m.AuditEvent.created_at <= stamp + 10,
                )
            )
            if not proof:
                return None
        elif models:
            return None
        elif reference.startswith("BROWSER_VAULT") and not any(
            e.action == "provider.credential_revoked" for e in events
        ):
            return None
        return {
            "registration_audit_id": registered.id,
            "contract_reference": reference,
            "source_files": [
                "apps/web/tests/agent-work.spec.ts"
                if reference.startswith("BROWSER_")
                else "apps/web/tests/native-execution.spec.ts"
                if reference.startswith("NATIVE_")
                else "apps/web/tests/zero-cost.spec.ts"
            ],
            "model_ids": [r.id for r in models],
        }
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    url = make_url(settings().database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("This workstation quarantine tool requires SQLite")
    path = Path(url.database).resolve(strict=True)
    backup = None
    if args.apply:
        backup = Path("data/backups") / ("registry-before-quarantine-" + str(uuid4()) + ".db")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with (
            sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source,
            sqlite3.connect(backup) as target,
        ):
            source.backup(target)
            assert target.execute("pragma integrity_check").fetchone()[0] == "ok"
            assert not target.execute("pragma foreign_key_check").fetchall()
    report = {
        "database": str(path),
        "backup": str(backup) if backup else None,
        "action": "quarantine" if args.apply else "dry_run",
        "providers": [],
    }
    with SessionLocal() as session:
        for org in session.scalars(select(m.Organization)):
            if args.apply:
                lock_org(session, org.id)
            for provider in session.scalars(select(m.Provider).where(m.Provider.org_id == org.id)):
                proof = evidence(session, provider)
                if not proof or facts(session, provider)["source"] == "test_fixture":
                    continue
                report["providers"].append({"id": provider.id, "org_id": provider.org_id, "evidence": proof})
                if args.apply:
                    classify(session, provider, "test_fixture", proof)
                    audit(
                        session,
                        provider.org_id,
                        "registry-repair",
                        "registry.fixture_quarantined",
                        provider.id,
                        {
                            "registration_audit_id": proof["registration_audit_id"],
                            "backup": str(backup),
                            "records_deleted": 0,
                        },
                    )
        if args.apply:
            session.commit()
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as source:
        report["integrity"] = source.execute("pragma integrity_check").fetchone()[0]
        report["foreign_key_violations"] = len(source.execute("pragma foreign_key_check").fetchall())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
