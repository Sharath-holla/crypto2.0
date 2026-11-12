"""Read-only provider catalogs; discovery never certifies inference or capabilities."""

import re

import httpx

from .config import settings
from .credentials import VaultUnavailable, secret_for
from .models import Provider
from .providers import ProviderError
from .security import validate_endpoint


async def discover(provider: Provider, client: httpx.AsyncClient | None = None) -> list[dict]:
    if provider.kind not in {"openai", "xai", "compatible", "gemini", "anthropic", "ollama"}:
        raise ProviderError("catalog_unsupported")
    base = validate_endpoint(
        provider.base_url, settings().provider_allowed_hosts, local_allowed=provider.kind == "ollama"
    )
    try:
        secret = secret_for(provider)
    except VaultUnavailable:
        raise ProviderError("vault_unavailable") from None
    if provider.kind != "ollama" and not secret:
        raise ProviderError("missing_credentials")
    if provider.kind == "anthropic":
        path, headers = "/models", {"x-api-key": secret, "anthropic-version": "2023-06-01"}
    elif provider.kind == "gemini":
        path, headers = "/models", {"x-goog-api-key": secret}
    elif provider.kind == "ollama":
        path, headers = "/api/tags", {}
    else:
        path, headers = "/models", {"Authorization": f"Bearer {secret}"}
    own = client is None
    client = client or httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)
    models, params, seen = {}, {}, set()
    try:
        for _ in range(10):
            # Stream with a bound so a catalog cannot consume arbitrary server memory.
            async with client.stream("GET", base + path, headers=headers, params=params) as response:
                if response.status_code != 200:
                    raise ProviderError(f"catalog_http_{response.status_code}")
                chunks, length = [], 0
                async for chunk in response.aiter_bytes():
                    length += len(chunk)
                    if length > 2_000_000:
                        raise ProviderError("catalog_too_large")
                    chunks.append(chunk)
                import json

                data = json.loads(b"".join(chunks))
            field = "models" if provider.kind in {"gemini", "ollama"} else "data"
            if not isinstance(data, dict) or field not in data:
                raise ProviderError("catalog_invalid")
            rows = data[field]
            if not isinstance(rows, list):
                raise ProviderError("catalog_invalid")
            for row in rows:
                identifier = row.get("name", row.get("model")) if provider.kind == "ollama" else row.get("id")
                if provider.kind == "gemini":
                    identifier = str(row.get("name", "")).removeprefix("models/")
                if not isinstance(identifier, str) or not identifier or len(identifier) > 200:
                    raise ProviderError("catalog_invalid")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", identifier):
                    raise ProviderError("catalog_invalid")
                if secret and secret in identifier:
                    raise ProviderError("catalog_invalid")
                methods = row.get("supportedGenerationMethods", []) if provider.kind == "gemini" else []
                if not isinstance(methods, list) or any(
                    not isinstance(method, str) or len(method) > 100 or (secret and secret in method)
                    for method in methods
                ):
                    raise ProviderError("catalog_invalid")
                models[identifier] = {"identifier": identifier, "generation_methods": methods[:20]}
                if provider.kind == "ollama":
                    local = {}
                    if isinstance(row.get("digest"), str) and re.fullmatch(
                        r"[a-fA-F0-9]{32,128}", row["digest"]
                    ):
                        local["digest"] = row["digest"]
                    if type(row.get("size")) is int and row["size"] > 0:
                        local["size_bytes"] = row["size"]
                    for key in ("format", "parameter_size", "quantization_level"):
                        value = (
                            row.get("details", {}).get(key)
                            if isinstance(row.get("details", {}), dict)
                            else None
                        )
                        if isinstance(value, str) and len(value) <= 100:
                            local[key] = value
                    if local:
                        models[identifier]["local_metadata"] = local
                if len(models) > 2000:
                    raise ProviderError("catalog_too_large")
            cursor = (
                data.get("nextPageToken")
                if provider.kind == "gemini"
                else (data.get("last_id") if provider.kind == "anthropic" and data.get("has_more") else None)
            )
            if not cursor:
                return sorted(models.values(), key=lambda row: row["identifier"])
            if not isinstance(cursor, str) or len(cursor) > 500 or (secret and secret in cursor):
                raise ProviderError("catalog_pagination_invalid")
            if cursor in seen:
                raise ProviderError("catalog_pagination_invalid")
            seen.add(cursor)
            params = {"pageToken" if provider.kind == "gemini" else "after_id": cursor}
        raise ProviderError("catalog_page_limit")
    except httpx.TimeoutException:
        raise ProviderError("catalog_timeout") from None
    except httpx.HTTPError:
        raise ProviderError("catalog_network_failure") from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProviderError("catalog_invalid") from None
    finally:
        if own:
            await client.aclose()
