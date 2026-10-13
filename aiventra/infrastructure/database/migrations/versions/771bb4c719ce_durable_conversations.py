"""Persist conversation scope, turns, attachments and worker dispatch."""

import sqlalchemy as sa
from alembic import op

revision = "771bb4c719ce"
down_revision = "f20b34705a81"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("budget_micro", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_conversations_org_id", "conversations", ["org_id"])
    op.create_index("ix_conversations_updated_at", "conversations", ["updated_at"])
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("requirement_id", sa.String(36), sa.ForeignKey("requirements.id")),
        sa.UniqueConstraint("conversation_id", "request_id"),
        sa.UniqueConstraint("conversation_id", "position"),
    )
    op.create_index("ix_conversation_turns_org_id", "conversation_turns", ["org_id"])
    op.create_index("ix_conversation_turns_conversation_id", "conversation_turns", ["conversation_id"])
    if op.get_bind().dialect.name == "sqlite":
        # Nullable inline REFERENCES are supported by SQLite ADD COLUMN. No table
        # rebuild is required, preserving existing child rows and audit triggers.
        op.execute(
            "ALTER TABLE workflows ADD COLUMN conversation_turn_id VARCHAR(36) REFERENCES conversation_turns(id)"
        )
        op.execute(
            "ALTER TABLE artifacts ADD COLUMN conversation_id VARCHAR(36) REFERENCES conversations(id)"
        )
    else:
        op.add_column(
            "workflows",
            sa.Column("conversation_turn_id", sa.String(36), sa.ForeignKey("conversation_turns.id")),
        )
        op.add_column(
            "artifacts", sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id"))
        )
    op.create_index("uq_workflows_conversation_turn", "workflows", ["conversation_turn_id"], unique=True)
    op.create_index("ix_artifacts_conversation_id", "artifacts", ["conversation_id"])


def downgrade():
    op.drop_index("ix_artifacts_conversation_id", table_name="artifacts")
    op.drop_index("uq_workflows_conversation_turn", table_name="workflows")
    op.drop_column("artifacts", "conversation_id")
    op.drop_column("workflows", "conversation_turn_id")
    op.drop_table("conversation_turns")
    op.drop_table("conversations")
