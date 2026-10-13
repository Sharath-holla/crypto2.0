"""Add frozen versioned delivery evidence; preserve all existing records/backends."""

import sqlalchemy as sa
from alembic import op

revision = "c72e51d9af04"
down_revision = "a31d07edc482"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "delivery_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("client_id", sa.String(36), sa.ForeignKey("clients.id"), nullable=False),
        sa.Column("review_id", sa.String(36), sa.ForeignKey("business_records.id"), nullable=False),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("workflows.id"), nullable=False, unique=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("finalized_at", sa.Integer(), nullable=True),
        sa.Column("supersedes_id", sa.String(36), sa.ForeignKey("delivery_packages.id")),
        sa.UniqueConstraint("org_id", "project_id", "version"),
        sa.UniqueConstraint("org_id", "request_id"),
    )
    for column in ("org_id", "project_id", "client_id"):
        op.create_index(f"ix_delivery_packages_{column}", "delivery_packages", [column])
    columns = (
        "id",
        "created_at",
        "org_id",
        "project_id",
        "client_id",
        "review_id",
        "workflow_id",
        "owner_id",
        "version",
        "request_id",
        "request_hash",
        "source_hash",
        "classification",
        "input",
        "manifest",
        "manifest_hash",
        "finalized_at",
        "supersedes_id",
    )
    if op.get_bind().dialect.name == "sqlite":
        changed = " OR ".join(f'OLD."{column}" IS NOT NEW."{column}"' for column in columns)
        op.execute(
            f"CREATE TRIGGER delivery_frozen BEFORE UPDATE ON delivery_packages "
            f"WHEN OLD.finalized_at IS NOT NULL AND ({changed}) "
            "BEGIN SELECT RAISE(ABORT, 'delivery manifest immutable'); END"
        )
        op.execute(
            "CREATE TRIGGER delivery_retained BEFORE DELETE ON delivery_packages "
            "BEGIN SELECT RAISE(ABORT, 'delivery versions retained'); END"
        )
    else:
        changed = " OR ".join(
            f'OLD."{column}"::text IS DISTINCT FROM NEW."{column}"::text' for column in columns
        )
        op.execute(
            "CREATE FUNCTION delivery_frozen_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'delivery versions retained'; END IF; "
            f"IF OLD.finalized_at IS NOT NULL AND ({changed}) THEN "
            "RAISE EXCEPTION 'delivery manifest immutable'; END IF; RETURN NEW; END; $$"
        )
        op.execute(
            "CREATE TRIGGER delivery_frozen BEFORE UPDATE OR DELETE ON delivery_packages "
            "FOR EACH ROW EXECUTE FUNCTION delivery_frozen_guard()"
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER delivery_frozen")
        op.execute("DROP TRIGGER delivery_retained")
    else:
        op.execute("DROP TRIGGER delivery_frozen ON delivery_packages")
        op.execute("DROP FUNCTION delivery_frozen_guard()")
    op.drop_table("delivery_packages")
