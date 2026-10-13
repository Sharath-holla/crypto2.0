"""Versioned document references; removed/replaced sources cannot remain searchable."""

import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import delete, select

from . import models as m
from .artifacts import save_artifact
from .config import settings
from .document_imports import MAX_UPLOAD


def pdf_source(org_id, sha):
    if not re.fullmatch(r"[a-f0-9]{64}", sha):
        raise ValueError("Invalid PDF source identity")
    root = settings().artifact_root.resolve()
    path = root / "document-sources" / org_id / (sha + ".pdf")
    if not path.resolve().is_relative_to(root) or any(
        parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent
    ):
        raise ValueError("Unsafe document storage")
    return path


def retire(session, artifact):
    if not artifact:
        return
    entry = session.scalar(
        select(m.MemoryEntry).where(
            m.MemoryEntry.org_id == artifact.org_id, m.MemoryEntry.source_key == f"artifacts:{artifact.id}"
        )
    )
    if entry:
        entry.deleted, entry.index_status = True, "deleted"
        session.execute(delete(m.MemoryChunk).where(m.MemoryChunk.entry_id == entry.id))
        session.execute(delete(m.MemoryGrant).where(m.MemoryGrant.entry_id == entry.id))
    # Preserve the private artifact/version audit, but exclude it from direct retrieval too.
    artifact.kind = "retired_requirement_attachment"


def attach(session, user, row, name, raw, content, metadata, replace_id):
    if row.status != "draft":
        raise HTTPException(
            409, "Attachments cannot change after submission; use a new approved requirement revision"
        )
    previous = next((item for item in row.data["attachments"] if item["id"] == replace_id), None)
    if replace_id and not previous:
        raise HTTPException(404, "Attachment is outside this draft")
    attachments = [item for item in row.data["attachments"] if item["id"] != replace_id]
    if len(attachments) >= 6 or sum(item["bytes"] for item in attachments) + len(raw) > 2 * MAX_UPLOAD:
        raise HTTPException(413, "Draft supports six documents and 2 MB total")
    if metadata["format"] == "pdf":
        path = pdf_source(user.org_id, metadata["source_sha256"])
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as output:
                output.write(raw)
            path.chmod(0o600)
        except FileExistsError:
            if hashlib.sha256(path.read_bytes()).hexdigest() != metadata["source_sha256"]:
                raise ValueError("Stored PDF source integrity failed") from None
    artifact = save_artifact(session, user.org_id, name, content, kind="project_requirement_attachment")
    previous_artifact = session.get(m.Artifact, previous["id"]) if previous else None
    form = row.data["form"]
    if not form["text"].strip() or (previous_artifact and form["text"] == previous_artifact.content[:30000]):
        form = {**form, "text": artifact.content[:30000]}
    retire(session, previous_artifact)
    row.data = {
        **row.data,
        "form": form,
        "attachments": [
            *attachments,
            {
                "id": artifact.id,
                "name": name,
                "sha256": artifact.sha256,
                "bytes": len(raw),
                "redacted": content != artifact.content,
                "parsed": True,
                **metadata,
                "document_version": previous.get("document_version", 1) + 1 if previous else 1,
                "replaces": replace_id,
            },
        ],
    }
    row.version += 1
