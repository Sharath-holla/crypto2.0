"""Bounded data extraction; never evaluate macros, links or embedded code."""

import asyncio
import hashlib
import io
import re
import zipfile
import zlib
from xml.etree import ElementTree

from fastapi import HTTPException

from .uploads import parse_text

MAX_UPLOAD = 1024 * 1024


def extract(name, raw):
    if not name.lower().endswith(".docx"):
        return parse_text(name, raw, strict_json=True), []
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,150}\.docx", name, re.I) or re.search(
        r"(secret|password|wallet|private.?key|seed.?phrase)", name, re.I
    ):
        raise HTTPException(422, "Use a safe DOCX document name")
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "DOCX exceeds 1 MB")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 128 or sum(item.file_size for item in entries) > 262144:
                raise ValueError()
            names = [item.filename.lower() for item in entries]
            if len(set(names)) != len(names) or any(
                item.flag_bits & 1
                or item.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
                or item.file_size > 100 * max(1, item.compress_size)
                or ".." in item.filename.split("/")
                or item.filename.startswith(("/", "\\"))
                for item in entries
            ):
                raise ValueError()
            if any("vbaproject" in name or "/embeddings/" in name or name.endswith(".bin") for name in names):
                raise ValueError()
            xml = archive.read("word/document.xml").decode("utf-8")
            if "\x00" in xml or re.search(r"<!\s*(DOCTYPE|ENTITY)", xml, re.I):
                raise ValueError()
            root = ElementTree.fromstring(xml)
            word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            text = "\n".join(
                "".join(node.text or "" for node in p.iter(word + "t")) for p in root.iter(word + "p")
            )
            if not text.strip() or len(text.encode()) > 65536 or "\x00" in text:
                raise ValueError()
    except (
        ValueError,
        KeyError,
        RuntimeError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
        zlib.error,
    ):
        raise HTTPException(
            422, "DOCX is invalid, empty, oversized or contains unsafe embedded content"
        ) from None
    return text, [
        "Main document text only; formatting, images, headers, links and embedded objects are not imported"
    ]


async def parse_document(name, raw, mime=None):
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, "Document exceeds 1 MB")
    extra = {}
    if name.lower().endswith(".pdf"):
        from .config import settings
        from .pdf_ingestion import parse_pdf

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,150}\.pdf", name, re.I) or re.search(
            r"(\.env|secret|password|wallet|private.?key|seed.?phrase)", name, re.I
        ):
            raise HTTPException(422, "Use a safe PDF document name")
        if mime not in {None, "application/pdf", "application/octet-stream"}:
            raise HTTPException(422, "PDF MIME type does not match the document")
        if len(raw) > settings().pdf_upload_limit:
            raise HTTPException(413, "PDF upload limit exceeded")
        result = await parse_pdf(raw)
        content, extra = result.pop("content"), result
        warnings = [
            "Text only; PDF metadata, actions, external links, embedded files and OCR are not imported"
        ]
    elif raw.startswith(b"%PDF-"):
        raise HTTPException(422, "PDF content requires a .pdf filename")
    else:
        try:
            content, warnings = await asyncio.wait_for(asyncio.to_thread(extract, name, raw), timeout=2)
        except TimeoutError:
            raise HTTPException(422, "Document extraction exceeded its time limit") from None
    return content, {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        **extra,
        "format": name.rsplit(".", 1)[-1].lower(),
        "extractor": "bounded-document-v1",
        "warnings": warnings,
        "trust": "untrusted data; no execution authority",
        "retrieval": "private owner draft; assigned-project knowledge after submission",
    }
