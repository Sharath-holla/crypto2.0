"""Scoped owner invitations/grants and append-only exact-package client responses."""

import sqlalchemy as sa
from alembic import op

revision = "d45f80a6ce12"
down_revision = "c72e51d9af04"
branch_labels = None
depends_on = None


def common():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("org_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
    ]


def fk(name, table, nullable=False):
    return sa.Column(name, sa.String(36), sa.ForeignKey(table + ".id"), nullable=nullable)


def upgrade():
    op.create_table(
        "client_invitations",
        *common(),
        fk("project_id", "projects"),
        fk("client_id", "clients"),
        fk("owner_id", "users"),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("redeemed_at", sa.Integer()),
        fk("redeemed_by", "users", True),
        sa.Column("revoked_at", sa.Integer()),
        sa.Column("can_respond", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("org_id", "request_id"),
    )
    op.create_table(
        "client_access_grants",
        *common(),
        fk("project_id", "projects"),
        fk("client_id", "clients"),
        fk("user_id", "users"),
        fk("invitation_id", "client_invitations"),
        sa.Column("can_respond", sa.Boolean(), nullable=False),
        sa.Column("revoked_at", sa.Integer()),
        sa.UniqueConstraint("org_id", "user_id", "project_id"),
    )
    op.create_table(
        "delivery_responses",
        *common(),
        fk("package_id", "delivery_packages"),
        fk("project_id", "projects"),
        fk("client_id", "clients"),
        fk("user_id", "users"),
        sa.Column("workflow_id", sa.String(36), sa.ForeignKey("workflows.id"), nullable=False, unique=True),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.UniqueConstraint("org_id", "request_id"),
    )
    for table, columns in {
        "client_invitations": ["org_id", "project_id"],
        "client_access_grants": ["org_id", "project_id", "user_id"],
        "delivery_responses": ["org_id", "project_id", "package_id"],
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "uq_delivery_package_acceptance",
        "delivery_responses",
        ["org_id", "package_id"],
        unique=True,
        sqlite_where=sa.text("kind = 'accept'"),
        postgresql_where=sa.text("kind = 'accept'"),
    )
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER delivery_response_no_{action.lower()} BEFORE {action} ON delivery_responses "
                "BEGIN SELECT RAISE(ABORT, 'client response append only'); END"
            )
    else:
        op.execute(
            "CREATE FUNCTION delivery_response_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
            "RAISE EXCEPTION 'client response append only'; END; $$"
        )
        op.execute(
            "CREATE TRIGGER delivery_response_no_mutation BEFORE UPDATE OR DELETE ON delivery_responses "
            "FOR EACH ROW EXECUTE FUNCTION delivery_response_guard()"
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER delivery_response_no_update")
        op.execute("DROP TRIGGER delivery_response_no_delete")
    else:
        op.execute("DROP TRIGGER delivery_response_no_mutation ON delivery_responses")
        op.execute("DROP FUNCTION delivery_response_guard()")
    op.drop_table("delivery_responses")
    op.drop_table("client_access_grants")
    op.drop_table("client_invitations")
