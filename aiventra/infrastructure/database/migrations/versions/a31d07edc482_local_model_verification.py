"""Persist local model verification without altering existing records."""

import sqlalchemy as sa
from alembic import op

revision = "a31d07edc482"
down_revision = "8c922fd4eecf"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_model_verifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("model_id", sa.String(36), sa.ForeignKey("model_configs.id"), nullable=False, unique=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("checked_at", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence_digest", sa.String(64), nullable=False),
    )
    op.create_index("ix_local_model_verifications_org_id", "local_model_verifications", ["org_id"])


def downgrade():
    op.drop_table("local_model_verifications")
