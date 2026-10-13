"""Enforce append-only audit records at the database boundary."""

from alembic import op

revision = "b411d790aa01"
down_revision = "96a913864372"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit append only'); END"
        )
        op.execute(
            "CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit append only'); END"
        )
    else:
        op.execute(
            "CREATE FUNCTION audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'audit append only'; END; $$"
        )
        op.execute(
            "CREATE TRIGGER audit_no_mutation BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION audit_append_only()"
        )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TRIGGER audit_no_update")
        op.execute("DROP TRIGGER audit_no_delete")
    else:
        op.execute("DROP TRIGGER audit_no_mutation ON audit_events")
        op.execute("DROP FUNCTION audit_append_only()")
