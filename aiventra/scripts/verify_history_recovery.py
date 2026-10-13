"""Read-only cursor/page identity digests across real SQLite/PostgreSQL service restarts."""

import json

from company_os import models as m
from company_os.db import SessionLocal
from company_os.history import project_events
from company_os.routes.conversations import snapshot
from company_os.security import digest, verify_audit
from sqlalchemy import select

with SessionLocal() as session:
    projects = list(session.scalars(select(m.Project).order_by(m.Project.id)))
    conversations = list(session.scalars(select(m.Conversation).order_by(m.Conversation.id)))
    assert projects and conversations, "Run browser journeys before the restart snapshot"
    pages = []
    for project in projects:
        first = project_events(session, project, None, 20)
        older = (
            project_events(session, project, first["next_cursor"], 20)
            if first["next_cursor"]
            else {"items": [], "next_cursor": None}
        )
        assert not {row["id"] for row in first["items"]}.intersection(row["id"] for row in older["items"])
        pages.append(
            {
                "project": project.id,
                "first": [row["id"] for row in first["items"]],
                "older": [row["id"] for row in older["items"]],
                "cursor": first["next_cursor"],
            }
        )
    turns = []
    for conversation in conversations:
        page = snapshot(session, conversation)
        assert len(page["turns"]) <= 20
        turns.append(
            {
                "conversation": conversation.id,
                "turns": [row["id"] for row in page["turns"]],
                "cursor": page["next_cursor"],
                "total": page["total_turns"],
            }
        )
    for identity in {project.org_id for project in projects}:
        assert verify_audit(session, identity)["valid"], "Append-only audit integrity failed"
    print(
        json.dumps(
            {
                "projects": len(projects),
                "conversations": len(conversations),
                "project_pages_digest": digest(pages),
                "chat_pages_digest": digest(turns),
            },
            sort_keys=True,
        )
    )
