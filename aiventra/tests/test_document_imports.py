import hashlib
import io
import zipfile

import pytest
from company_os import models as m

from tests.test_project_setup import command, create


def docx(text="Imported requirements for a safe persistent project", extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>',
        )
        for name, content in (extra or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def test_docx_provenance_atomic_replace_remove_and_retry(http, company):
    row = create(http, company, text="")
    raw = docx()
    uploaded = http.post(
        f"/project-drafts/{row['id']}/attachments", data=command(row), files={"file": ("brief.docx", raw)}
    )
    assert uploaded.status_code == 200, uploaded.text
    row = uploaded.json()
    original = row["data"]["attachments"][0]
    assert original["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert original["warnings"] and row["data"]["form"]["text"].startswith("Imported requirements")
    body = {**command(row), "replace_id": original["id"]}
    files = {"file": ("revised.md", b"Updated approved requirements with independent tests")}
    replacement = http.post(f"/project-drafts/{row['id']}/attachments", data=body, files=files)
    assert replacement.status_code == 200, replacement.text
    assert (
        http.post(f"/project-drafts/{row['id']}/attachments", data=body, files=files).json()["version"]
        == replacement.json()["version"]
    )
    row = replacement.json()
    assert (
        len(row["data"]["attachments"]) == 1 and row["data"]["attachments"][0]["replaces"] == original["id"]
    )
    assert row["data"]["form"]["text"].startswith("Updated approved")
    company["factory"].kw["bind"].dispose()
    assert http.get(f"/project-drafts/{row['id']}").json()["data"] == row["data"]
    attachment_id = row["data"]["attachments"][0]["id"]
    envelope = command(row)
    path = f"/project-drafts/{row['id']}/attachments/{attachment_id}/remove"
    removed = http.post(path, json=envelope)
    assert removed.status_code == 200, removed.text
    assert not removed.json()["data"]["attachments"] and not removed.json()["data"]["form"]["text"]
    assert http.post(path, json=envelope).json()["version"] == removed.json()["version"]
    with company["factory"]() as session:
        assert session.get(m.Artifact, original["id"]) is not None


@pytest.mark.parametrize(
    "raw",
    [
        b"invalid archive",
        docx(extra={"word/vbaProject.bin": b"macro"}),
        docx(extra={"word/embeddings/object": b"embedded"}),
        docx("<!DOCTYPE unsafe>"),
        docx(extra={"a" * 10: b"a" * 262145}),
    ],
    ids=["invalid_zip", "macro", "embedded", "invalid_xml", "expanded_size"],
)
def test_docx_unsafe_content_rejected_without_draft_changes(http, company, raw):
    row = create(http, company)
    response = http.post(
        f"/project-drafts/{row['id']}/attachments", data=command(row), files={"file": ("brief.docx", raw)}
    )
    assert response.status_code == 422, response.text
    assert http.get(f"/project-drafts/{row['id']}").json()["version"] == row["version"]


def test_attachment_project_scope_and_submitted_immutability(http, company):
    row, other = create(http, company), create(http, company)
    row = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data=command(row),
        files={"file": ("brief.md", b"Private requirements for this project only")},
    ).json()
    attachment = row["data"]["attachments"][0]["id"]
    assert (
        http.post(
            f"/project-drafts/{other['id']}/attachments/{attachment}/remove", json=command(other)
        ).status_code
        == 404
    )
    submitted = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    assert (
        http.post(
            f"/project-drafts/{row['id']}/attachments/{attachment}/remove", json=command(submitted)
        ).status_code
        == 409
    )


@pytest.mark.parametrize("format", ["markdown", "pdf"])
def test_exact_proposal_approval_grants_document_to_assigned_project(http, company, format):
    from sqlalchemy import select

    row = create(http, company, planning_mode="manual")
    if format == "pdf":
        from tests.test_pdf_ingestion import pdf

        file = (
            "knowledge.pdf",
            pdf("Project-specific PDF with explicit source provenance"),
            "application/pdf",
        )
    else:
        file = ("knowledge.md", b"Project-specific document with explicit source provenance")
    row = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data=command(row),
        files={"file": file},
    ).json()
    attachment_id = row["data"]["attachments"][0]["id"]
    row = http.post(f"/project-drafts/{row['id']}/submit", json=command(row)).json()
    planned = http.post(
        f"/project-drafts/{row['id']}/manual-plan",
        json=command(
            row,
            architecture="Owner-defined private architecture with durable source documents",
            milestones=["Planning", "Delivery"],
            criteria=["Source documents remain project-scoped"],
        ),
    )
    assert planned.status_code == 200, planned.text
    with company["factory"]() as session:
        proposal = session.scalar(
            select(m.Proposal).where(m.Proposal.requirement_id == row["data"]["requirement_id"])
        )
        assert session.get(m.Artifact, attachment_id).project_id is None
        response = http.post(
            f"/proposals/{proposal.id}/approve",
            json={
                "version": proposal.version,
                "content_hash": proposal.content_hash,
                "selection": proposal.content["recommendation"],
            },
        )
    assert response.status_code == 200, response.text
    with company["factory"]() as session:
        artifact = session.get(m.Artifact, attachment_id)
        assert artifact.project_id == response.json()["id"]
        memory = session.scalar(
            select(m.MemoryEntry).where(m.MemoryEntry.source_key == f"artifacts:{attachment_id}")
        )
        assert memory.project_id == artifact.project_id and memory.visibility == "project"


def test_deep_json_is_refused_as_validation_error(http, company):
    row = create(http, company)
    response = http.post(
        f"/project-drafts/{row['id']}/attachments",
        data=command(row),
        files={"file": ("deep.json", b"[" * 2000 + b"]" * 2000)},
    )
    assert response.status_code == 422
