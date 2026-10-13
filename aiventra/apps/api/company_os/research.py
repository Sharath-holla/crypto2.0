import re

import httpx

from .config import settings
from .db import now
from .security import redact, validate_endpoint


async def fetch_source(url: str) -> dict:
    url = validate_endpoint(url, settings().research_allowed_hosts)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            if "text/" not in response.headers.get("content-type", ""):
                raise ValueError("Only published text sources supported")
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 1000000:
                    raise ValueError("Source exceeds retrieval limit")
                chunks.append(chunk)
    html = b"".join(chunks).decode(errors="replace")
    html = re.sub(r"<(script|style)[\s\S]*?</\1>", "", html, flags=re.I)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))[:20000]
    return {
        "source_url": url,
        "retrieved_at": now(),
        "excerpt": redact(text),
        "trust": "untrusted retrieved content",
        "pricing_verified": False,
        "limitations": "Retrieval is evidence collection; region, units, availability and rates require validation.",
    }
