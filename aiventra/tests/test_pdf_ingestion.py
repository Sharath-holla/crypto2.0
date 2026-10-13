import hashlib
import io

import pytest
from company_os import models as m
from company_os.config import settings
from company_os.document_imports import parse_document
from company_os.draft_documents import pdf_source
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

from tests.test_document_imports import docx
from tests.test_project_setup import command, create


def pdf(*texts, action=False, compress=False):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 200 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream.flate_encode() if compress else stream)
    if action:
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
            {NameObject("/S"): NameObject("/JavaScript")}
        )
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


async def test_actual_limited_pdf_process_text_pages_and_compression(company):
    raw = pdf("First page requirements", "Second page architecture", compress=True)
    content, metadata = await parse_document("requirements.pdf", raw, "application/pdf")
    assert "[Page 1]" in content and "Second page architecture" in content
    assert metadata["page_count"] == 2 and metadata["pages"] == [
        {"page": 1, "has_text": True},
        {"page": 2, "has_text": True},
    ]
    assert metadata["source_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "malformed",
        "extension",
        "mime",
        "active",
        "decompression",
        "too_many_pages",
        "size",
        "unsafe_name",
    ],
)
async def test_pdf_rejects_unsafe_resource_and_input_cases(company, monkeypatch, case):
    from fastapi import HTTPException

    name, raw, mime = "brief.pdf", pdf("Safe requirements"), "application/pdf"
    if case == "empty":
        raw = pdf("")
    if case == "malformed":
        raw = b"%PDF-1.7\nmalformed\n%%EOF"
    if case == "extension":
        name = "brief.txt"
    if case == "mime":
        mime = "image/png"
    if case == "active":
        raw = pdf("Safe looking", action=True)
    if case == "decompression":
        raw = pdf("x" * 270000, compress=True)
    if case == "too_many_pages":
        monkeypatch.setattr(settings(), "pdf_page_limit", 1)
        raw = pdf("A", "B")
    if case == "size":
        monkeypatch.setattr(settings(), "pdf_upload_limit", 1024)
        raw += b" " * 1024
    if case == "unsafe_name":
        name = "../brief.pdf"
    with pytest.raises(HTTPException) as failure:
        await parse_document(name, raw, mime)
    assert failure.value.status_code in {413, 422}


def test_pdf_lifecycle_mixed_documents_memory_tombstones_and_recovery(http, company):
    row = create(http, company, text="")
    raw = pdf("Version one project requirements", "Validation on page two")
    response = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data=command(row),
        files={"file": ("brief.pdf", raw, "application/pdf")},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    original = row["data"]["attachments"][0]
    assert original["document_version"] == 1 and original["page_count"] == 2
    assert pdf_source(company["org"].id, original["source_sha256"]).read_bytes() == raw
    body = command(row)
    path = f"/project-drafts/{row['id']}/attachments/{original['id']}/reprocess"
    response = http.post(path, json=body)
    assert response.status_code == 200, response.text
    assert http.post(path, json=body).json()["version"] == response.json()["version"]
    row = response.json()
    current = row["data"]["attachments"][0]
    assert current["document_version"] == 2
    with company["factory"]() as session:
        entry = session.scalar(
            select(m.MemoryEntry).where(m.MemoryEntry.source_key == f"artifacts:{original['id']}")
        )
        assert entry.deleted and not session.scalar(
            select(m.MemoryChunk.id).where(m.MemoryChunk.entry_id == entry.id)
        )
    response = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data={**command(row), "replace_id": current["id"]},
        files={"file": ("brief.pdf", pdf("Version three replacement"), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    row = response.json()
    latest = row["data"]["attachments"][0]
    assert latest["document_version"] == 3
    row = http.post(
        f"/project-drafts/{row['id']}/attachments", data=command(row), files={"file": ("other.docx", docx())}
    ).json()
    assert len(row["data"]["attachments"]) == 2
    assert (
        http.get(f"/project-drafts/{row['id']}").json()["data"]["attachments"] == row["data"]["attachments"]
    )
    other = create(http, company)
    denied = http.post(
        f"/project-drafts/{other['id']}/attachments/{latest['id']}/reprocess", json=command(other)
    )
    assert denied.status_code == 404
    row = http.post(
        f"/project-drafts/{row['id']}/attachments/{latest['id']}/remove", json=command(row)
    ).json()
    assert len(row["data"]["attachments"]) == 1
    with company["factory"]() as session:
        entry = session.scalar(
            select(m.MemoryEntry).where(m.MemoryEntry.source_key == f"artifacts:{latest['id']}")
        )
        assert entry.deleted


async def test_pdf_timeout_kills_parser_and_does_not_break_docx(company, monkeypatch):
    import subprocess

    from company_os import pdf_ingestion
    from fastapi import HTTPException

    original = subprocess.Popen.communicate

    def timeout_once(self, *args, **kwargs):
        raise subprocess.TimeoutExpired(self.args, 1)

    monkeypatch.setattr(pdf_ingestion.subprocess.Popen, "communicate", timeout_once)
    with pytest.raises(HTTPException):
        await parse_document("brief.pdf", pdf("Safe requirements"))
    monkeypatch.setattr(pdf_ingestion.subprocess.Popen, "communicate", original)
    text, _ = await parse_document("other.docx", docx())
    assert "Imported requirements" in text
    import threading

    monkeypatch.setattr(pdf_ingestion, "_parse_slots", threading.BoundedSemaphore(0))
    with pytest.raises(HTTPException) as saturated:
        await parse_document("brief.pdf", pdf("Safe requirements"))
    assert saturated.value.status_code == 429
