"""Shared bounded text parser. Uploaded contents never grant execution authority."""

import json
import re

from fastapi import HTTPException


def parse_text(name, raw, limit=16384, strict_json=False):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,150}\.(txt|md|csv|json)", name, re.I) or re.search(
        r"(\.env|secret|password|wallet|private.?key|seed.?phrase)", name, re.I
    ):
        raise HTTPException(
            422, "Attach a safe UTF-8 .txt, .md, .csv or .json document; PDF/DOCX/images are unsupported"
        )
    if len(raw) > limit:
        raise HTTPException(413, f"Document exceeds {limit // 1024} KB")
    try:
        content = raw.decode("utf-8")
        if strict_json and name.lower().endswith(".json"):
            pending = [(json.loads(content), 0)]
            while pending:
                value, depth = pending.pop()
                if depth > 64:
                    raise ValueError("JSON nesting exceeds limits")
                if isinstance(value, (dict, list)):
                    pending.extend(
                        (child, depth + 1) for child in (value.values() if isinstance(value, dict) else value)
                    )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise HTTPException(
            422, "Document must contain valid UTF-8 text (and valid JSON for .json)"
        ) from None
    if not content.strip() or "\x00" in content:
        raise HTTPException(422, "Document is empty or binary")
    return content
