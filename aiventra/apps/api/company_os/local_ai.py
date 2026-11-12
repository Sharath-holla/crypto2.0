"""Read-only loopback diagnostics and host-memory admission; no installation or inference."""

import ctypes
import os
from pathlib import Path

import httpx

from .config import settings
from .db import now
from .models import ModelConfig
from .spending import assess, bounded_json


def available_memory_mb():
    if os.name == "nt":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong)
                for name in (
                    "total",
                    "available",
                    "page_total",
                    "page_available",
                    "virtual",
                    "virtual_available",
                    "extended",
                )
            ]

        value = MemoryStatus()
        value.length = ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            return value.available // 1_048_576
    else:
        try:
            fields = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            return int(fields["MemAvailable"].split()[0]) // 1024
        except (OSError, ValueError, KeyError):
            pass
    return None


def memory_blocker():
    minimum = settings().ollama_min_available_memory_mb
    if not minimum:
        return ""
    available = available_memory_mb()
    if minimum and (available is None or available < minimum):
        return f"Local inference needs at least {minimum} MiB available RAM; observed {available if available is not None else 'unknown'}. Free memory and resume."
    return ""


async def diagnostics(provider, client=None):
    policy = assess(
        provider,
        ModelConfig(
            identifier="local-diagnostics", input_price_micro_per_million=0, output_price_micro_per_million=0
        ),
    )
    if provider.kind != "ollama" or not policy.local_candidate:
        raise PermissionError(
            "Local diagnostics require an authorized credential-free loopback Ollama provider"
        )
    result = {
        "provider_id": provider.id,
        "checked_at": now(),
        "reachable": False,
        "version": None,
        "installed_models": [],
        "loaded_models": [],
        "available_memory_mb": available_memory_mb(),
        "minimum_available_memory_mb": settings().ollama_min_available_memory_mb,
        "resource_warning": memory_blocker(),
        "context_limit": settings().ollama_context_tokens,
        "keep_alive_seconds": settings().ollama_keep_alive_seconds,
        "thinking": settings().ollama_thinking,
        "check_invokes_inference": False,
        "error": "",
    }
    own = client is None
    client = client or httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False)
    try:
        base = provider.base_url.rstrip("/")
        version = await bounded_json(client, "GET", base + "/api/version")
        if not isinstance(version.get("version"), str) or len(version["version"]) > 100:
            raise ValueError("Invalid local version")
        result["version"] = version["version"]
        for endpoint, key in (("tags", "installed_models"), ("ps", "loaded_models")):
            data = await bounded_json(client, "GET", base + "/api/" + endpoint)
            rows = data.get("models")
            if not isinstance(rows, list) or len(rows) > 2000:
                raise ValueError("Invalid local model list")
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("name"), str)
                    or len(row["name"]) > 200
                ):
                    raise ValueError("Invalid local model metadata")
                safe = {"name": row["name"]}
                for name in ("model", "digest", "expires_at"):
                    if isinstance(row.get(name), str) and len(row[name]) <= 200:
                        safe[name] = row[name]
                for name in ("size", "size_vram", "context_length"):
                    if type(row.get(name)) is int and row[name] >= 0:
                        safe[name] = row[name]
                result[key].append(safe)
        result["reachable"] = True
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        result["installed_models"], result["loaded_models"] = [], []
        result["error"] = "Local Ollama diagnostics unavailable; no inference was sent"
    finally:
        if own:
            await client.aclose()
    return result
