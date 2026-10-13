"""Fail-closed inference authorization, independent of routing preferences and budgets.

No remote service currently has verifiable provider-enforced zero billing evidence.
Local Ollama must attest an installed GGUF model before *each* inference. The local
administrator/daemon is a trust boundary; a malicious localhost proxy is out of scope.
"""

import hashlib
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import now


@dataclass(frozen=True)
class Decision:
    allowed: bool
    state: str
    reason: str
    local_candidate: bool = False
    evidence_digest: str = ""
    capabilities: tuple[str, ...] = ()

    def public(self):
        return asdict(self)


class InferenceBlocked(Exception):
    def __init__(self, decision):
        self.decision = decision
        super().__init__(decision.reason)


def fingerprint(provider, model):
    return hashlib.sha256(
        repr(
            (
                provider.kind,
                provider.base_url,
                model.identifier,
                provider.credential_env,
                model.input_price_micro_per_million,
                model.output_price_micro_per_million,
                provider.enabled,
                model.enabled,
            )
        ).encode()
    ).hexdigest()


def assess(provider, model):
    from .model_catalog import available
    from .registry_provenance import inference_fixture

    if provider.kind != "mock" and inference_fixture(model):
        return Decision(
            False, "UNKNOWN_COST_BLOCKED", "Test fixture registry entries cannot authorize live inference"
        )

    if not available(model):
        return Decision(
            False, "PROVIDER_UNAVAILABLE", "Model disappeared from the last successful provider catalog"
        )
    if settings().ai_spending_mode != "ZERO_COST_ONLY":
        return Decision(False, "UNKNOWN_COST_BLOCKED", "Unsupported spending policy")
    if provider.enabled is False or model.enabled is False:
        return Decision(False, "PROVIDER_UNAVAILABLE", "Provider or model disabled")
    if provider.kind == "mock" and settings().mock_enabled:
        return Decision(True, "DETERMINISTIC_TEST", "Explicit deterministic fixture; no AI inference")
    if any((model.input_price_micro_per_million or 0, model.output_price_micro_per_million or 0)):
        return Decision(False, "PAID_BLOCKED", "Registered token charges are prohibited by ZERO_COST_ONLY")
    if provider.kind != "ollama":
        return Decision(
            False,
            "UNKNOWN_COST_BLOCKED",
            "No provider-enforced zero billing proof; credentials, zero prices, credits and subscriptions are insufficient",
        )
    endpoint = urlsplit(provider.base_url)
    if (
        endpoint.scheme != "http"
        or endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
        or provider.credential_env
        or "cloud" in model.identifier.lower()
    ):
        return Decision(
            False,
            "UNKNOWN_COST_BLOCKED",
            "Only credential-free loopback Ollama with a local model is eligible",
        )
    return Decision(
        False, "UNKNOWN_COST_BLOCKED", "Installed local model has not been verified for this request", True
    )


def installed_manifest(tags, detail, identifier):
    """Reject cloud aliases, missing files and malformed metadata without inference."""

    def remote(value):
        if isinstance(value, dict):
            return any(
                (str(k).lower().startswith("remote") and bool(v)) or remote(v) for k, v in value.items()
            )
        if isinstance(value, list):
            return any(remote(v) for v in value)
        return isinstance(value, str) and "cloud" in value.lower()

    names = {identifier, identifier + ":latest"} if ":" not in identifier else {identifier}
    row = next((r for r in tags.get("models", []) if r.get("name") in names), None)
    if (
        not row
        or not isinstance(row.get("size"), int)
        or row["size"] <= 0
        or not isinstance(row.get("digest"), str)
        or len(row["digest"]) < 32
        or detail.get("details", {}).get("format") != "gguf"
        or not detail.get("model_info")
        or remote(row)
        or remote(detail)
    ):
        raise InferenceBlocked(
            Decision(
                False,
                "UNKNOWN_COST_BLOCKED",
                "Local installed-model proof missing or remote/cloud model rejected",
            )
        )
    return Decision(
        True,
        "LOCAL_AVAILABLE",
        "No provider token charges — local computing resources consumed",
        True,
        hashlib.sha256(repr((row, detail)).encode()).hexdigest(),
        tuple(c for c in detail.get("capabilities", []) if isinstance(c, str)),
    )


async def bounded_json(client, method, url, **kwargs):
    async with client.stream(method, url, **kwargs) as response:
        response.raise_for_status()
        payload = bytearray()
        async for chunk in response.aiter_bytes():
            payload.extend(chunk)
            if len(payload) > 2_000_000:
                raise ValueError("Local manifest exceeds limits")
    import json

    return json.loads(payload)


async def authorize(provider, model):
    decision = assess(provider, model)
    if decision.allowed:
        return decision
    if not decision.local_candidate:
        raise InferenceBlocked(decision)
    from .local_ai import memory_blocker

    if reason := memory_blocker():
        raise InferenceBlocked(Decision(False, "LOCAL_RESOURCES_BLOCKED", reason, True))
    try:
        async with httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as client:
            base = provider.base_url.rstrip("/")
            tags = await bounded_json(client, "GET", base + "/api/tags")
            detail = await bounded_json(client, "POST", base + "/api/show", json={"model": model.identifier})
        return installed_manifest(tags, detail, model.identifier)
    except InferenceBlocked:
        raise
    except (httpx.HTTPError, ValueError, TypeError, AttributeError, KeyError):
        raise InferenceBlocked(
            Decision(False, "PROVIDER_UNAVAILABLE", "Local model metadata unavailable; no inference sent")
        ) from None


def record_local(session, provider, model, decision):
    from .models import LocalModelVerification

    record = session.scalar(
        select(LocalModelVerification).where(
            LocalModelVerification.model_id == model.id, LocalModelVerification.org_id == provider.org_id
        )
    )
    if record is None:
        try:
            with session.begin_nested():
                record = LocalModelVerification(
                    org_id=provider.org_id,
                    model_id=model.id,
                    fingerprint=fingerprint(provider, model),
                    checked_at=now(),
                    state=decision.state,
                    reason=decision.reason,
                    evidence_digest=decision.evidence_digest,
                )
                session.add(record)
                session.flush()
        except IntegrityError:
            record = session.scalar(
                select(LocalModelVerification).where(
                    LocalModelVerification.model_id == model.id,
                    LocalModelVerification.org_id == provider.org_id,
                )
            )
            if record is None:
                raise
    record.fingerprint, record.checked_at = fingerprint(provider, model), now()
    record.state, record.reason, record.evidence_digest = (
        decision.state,
        decision.reason,
        decision.evidence_digest,
    )
    return record


def authorize_embedding(client, endpoint, identifier):
    import json
    from types import SimpleNamespace

    provider = SimpleNamespace(kind="ollama", base_url=endpoint, credential_env="", enabled=True)
    model = SimpleNamespace(
        identifier=identifier, enabled=True, input_price_micro_per_million=0, output_price_micro_per_million=0
    )
    decision = assess(provider, model)
    if not decision.local_candidate:
        raise InferenceBlocked(decision)
    documents = []
    for method, path, body in [("GET", "/api/tags", None), ("POST", "/api/show", {"model": identifier})]:
        with client.stream(method, endpoint.rstrip("/") + path, json=body) as response:
            response.raise_for_status()
            payload = bytearray()
            for chunk in response.iter_bytes():
                payload.extend(chunk)
                if len(payload) > 2_000_000:
                    raise ValueError("Local manifest exceeds limits")
        documents.append(json.loads(payload))
    return installed_manifest(*documents, identifier)


def status(session, provider, model):
    from .models import LocalModelVerification

    decision = assess(provider, model)
    if decision.local_candidate:
        from .local_ai import memory_blocker

        if reason := memory_blocker():
            return {
                "model_id": model.id,
                "provider_id": provider.id,
                **Decision(False, "LOCAL_RESOURCES_BLOCKED", reason, True).public(),
            }
        record = session.scalar(
            select(LocalModelVerification).where(
                LocalModelVerification.org_id == provider.org_id, LocalModelVerification.model_id == model.id
            )
        )
        if record and record.fingerprint == fingerprint(provider, model) and now() - record.checked_at < 300:
            decision = Decision(
                record.state == "LOCAL_AVAILABLE", record.state, record.reason, True, record.evidence_digest
            )
    return {"model_id": model.id, "provider_id": provider.id, **decision.public()}
