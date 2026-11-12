"""Display catalog and durable discovery facts; visibility is never execution authority."""

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import object_session

from . import models as m
from .config import settings
from .credentials import credential_facts
from .db import now
from .registry_provenance import facts as origin_facts
from .registry_provenance import visible

KIND = "provider_catalog"


def record_id(provider):
    return str(uuid5(NAMESPACE_URL, f"aiventra:catalog:{provider.org_id}:{provider.id}"))


def record(session, provider, create=False):
    row = session.get(m.BusinessRecord, record_id(provider))
    if row and (row.org_id != provider.org_id or row.kind != KIND):
        raise ValueError("Catalog record scope conflict")
    if row is None and create:
        row = m.BusinessRecord(
            id=record_id(provider),
            org_id=provider.org_id,
            kind=KIND,
            title="Provider model discovery",
            data={"provider_id": provider.id, "items": {}},
        )
        session.add(row)
        session.flush()
    return row


def invalidate(session, provider):
    row = record(session, provider)
    if row:
        row.data = {**row.data, "status": "refresh_required", "error_code": "credential_changed"}


def available(model):
    """Consult persistent removal evidence even at the inference transport boundary."""
    if not isinstance(model, m.ModelConfig) or (session := object_session(model)) is None:
        return True  # Detached legacy contracts still face the independent spending guard.
    identity = str(uuid5(NAMESPACE_URL, f"aiventra:catalog:{model.org_id}:{model.provider_id}"))
    # Read columns, not the identity map: another session may have just removed this model.
    data = session.scalar(
        select(m.BusinessRecord.data).where(
            m.BusinessRecord.id == identity,
            m.BusinessRecord.org_id == model.org_id,
            m.BusinessRecord.kind == KIND,
        )
    )
    item = data.get("items", {}).get(model.identifier) if data else None
    return item is None or item.get("present", True)


def synchronize(session, provider, row, catalog):
    stamp = now()
    if len(set(row.data.get("items", {})) | {entry["identifier"] for entry in catalog}) > 4000:
        raise ValueError("Catalog retention limit reached; existing registry is preserved")
    existing = {
        model.identifier: model
        for model in session.scalars(
            select(m.ModelConfig).where(
                m.ModelConfig.provider_id == provider.id, m.ModelConfig.org_id == provider.org_id
            )
        )
    }
    items = {key: {**value, "present": False} for key, value in row.data.get("items", {}).items()}
    for entry in catalog:
        identity = entry["identifier"]
        model = existing.get(identity)
        if model is None:
            model = m.ModelConfig(
                org_id=provider.org_id,
                provider_id=provider.id,
                identifier=identity,
                capabilities=[],
                context_tokens=0,
                quality=0,
                reliability=0,
                price_source="",
                price_checked_at=0,
            )
            session.add(model)
            session.flush()
            existing[identity] = model
        previous = items.get(identity, {})
        items[identity] = {
            **previous,
            "model_id": model.id,
            "present": True,
            "first_seen_at": previous.get("first_seen_at", stamp),
            "last_seen_at": stamp,
            "source": "provider_catalog",
            "generation_methods": entry.get("generation_methods", []),
            "local_metadata": entry.get("local_metadata", {}),
        }
    # Removed identifiers are preserved, but bound total retained evidence.
    if len(items) > 4000:
        raise ValueError("Catalog retention limit reached; existing registry is preserved")
    row.data = {**row.data, "items": items, "last_success_at": stamp}


def view(session, org_id):
    from .spending import status

    providers = list(
        session.scalars(
            select(m.Provider)
            .where(m.Provider.org_id == org_id, m.Provider.kind != "mock")
            .order_by(m.Provider.name, m.Provider.id)
        )
    )
    states = {provider.id: record(session, provider) for provider in providers}
    providers = [provider for provider in providers if visible(session, provider)]
    probes = {
        probe.provider_id: probe
        for probe in session.scalars(select(m.ProviderProbe).where(m.ProviderProbe.org_id == org_id))
    }
    from .execution_evidence import live_results

    live_runs = live_results(session, org_id)
    provider_rows, model_rows = [], []
    for provider in providers:
        state = states[provider.id]
        data = state.data if state else {}
        probe = probes.get(provider.id)
        facts = credential_facts(provider, session)
        successful = data.get("last_success_at")
        stale = bool(
            successful
            and (now() - successful > 3600 or data.get("error_code") or data.get("status") == "discovering")
        )
        provider_rows.append(
            {
                "id": provider.id,
                "name": provider.name,
                "kind": provider.kind,
                "provenance": origin_facts(session, provider)["source"],
                "enabled": provider.enabled,
                "configured": facts["credential_configured"],
                "credential_error": facts["credential_error"],
                "connection_state": "disabled"
                if not provider.enabled
                else "credential_unavailable"
                if facts["credential_error"]
                else "configured"
                if facts["credential_configured"]
                else "not_configured",
                "status": data.get("status", probe.status if probe else "not_discovered"),
                "error_code": data.get("error_code", probe.error_code if probe else ""),
                "last_checked_at": data.get("checked_at", probe.checked_at if probe else None),
                "last_success_at": successful,
                "stale": stale,
                "discovery_interrupted": data.get("status") == "discovering"
                and now() - data.get("checked_at", 0) > 30,
                "registered_count": 0,
            }
        )
    lookup = {provider.id: provider for provider in providers}
    public = {row["id"]: row for row in provider_rows}
    for model in session.scalars(
        select(m.ModelConfig)
        .where(m.ModelConfig.org_id == org_id)
        .order_by(m.ModelConfig.identifier, m.ModelConfig.id)
    ):
        provider = lookup.get(model.provider_id)
        if not provider:
            continue
        public[provider.id]["registered_count"] += 1
        state = states[provider.id]
        metadata = state.data.get("items", {}).get(model.identifier, {}) if state else {}
        eligibility = status(session, provider, model)
        ready = bool(
            eligibility["allowed"]
            and "structured" in model.capabilities
            and public[provider.id]["configured"]
        )
        if eligibility["allowed"] and not ready:
            eligibility = {
                **eligibility,
                "allowed": False,
                "state": "UNSUPPORTED_CAPABILITY",
                "reason": "Documented structured-output capability is not configured",
            }
        # Only actual successful model runs establish live inference evidence.
        live_at = live_runs.get(model.id)
        model_rows.append(
            {
                "id": model.id,
                "provider_id": provider.id,
                "provider": provider.name,
                "kind": provider.kind,
                "identifier": model.identifier,
                "enabled": model.enabled and provider.enabled,
                "model_enabled": model.enabled,
                "configured": public[provider.id]["configured"],
                "capabilities": model.capabilities,
                "capability_source": "owner_configured" if model.capabilities else "unknown",
                "context_tokens": model.context_tokens,
                "effective_context_tokens": min(model.context_tokens, settings().ollama_context_tokens)
                if provider.kind == "ollama"
                else model.context_tokens,
                "local_metadata": metadata.get("local_metadata", {}),
                "configured_quality": model.quality,
                "registration": "discovered" if metadata else "owner_registered",
                "provenance": origin_facts(session, provider)["source"]
                if origin_facts(session, provider)["source"] in {"test_fixture", "system_example"}
                else "provider_discovery"
                if metadata
                else origin_facts(session, provider)["source"],
                "discovered_at": metadata.get("last_seen_at"),
                "present": metadata.get("present", True),
                "stale": public[provider.id]["stale"],
                "eligibility": eligibility,
                "pricing_status": "owner_configured" if model.price_source else "unknown",
                "live_inference_at": live_at,
                "discovery_source": metadata.get("source", "owner_registration"),
                "last_success_at": public[provider.id]["last_success_at"],
                "last_error": public[provider.id]["error_code"],
                "supports_streaming": True if "streaming" in model.capabilities else None,
                "supports_tools": True if "tools" in model.capabilities else None,
                "supports_structured": True if "structured" in model.capabilities else None,
            }
        )
    return {
        "providers": provider_rows,
        "models": model_rows,
        "spending_mode": "ZERO_COST_ONLY",
        "isolated_test_environment": settings().isolated_test_environment,
    }
