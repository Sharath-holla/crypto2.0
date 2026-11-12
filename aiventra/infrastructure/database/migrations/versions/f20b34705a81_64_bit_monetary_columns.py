"""Use PostgreSQL BIGINT for monetary quantities without rebuilding SQLite tables."""

import sqlalchemy as sa
from alembic import op

revision = "f20b34705a81"
down_revision = "e9c9f1ed55a6"
branch_labels = None
depends_on = None

MONETARY_COLUMNS = {
    "agents": ["max_cost_micro"],
    "model_configs": ["input_price_micro_per_million", "output_price_micro_per_million"],
    "requirements": ["budget_micro"],
    "projects": ["budget_micro"],
    "tasks": ["budget_micro"],
    "budgets": ["limit_micro", "spent_micro", "reserved_micro"],
    "model_runs": ["cost_micro", "reserved_micro"],
    "spending_transactions": ["amount_micro"],
}


def upgrade():
    if op.get_bind().dialect.name == "sqlite":
        return  # SQLite INTEGER already has the required range; retain tables/FKs/triggers.
    for table, columns in MONETARY_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column, existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=False
            )


def downgrade():
    if op.get_bind().dialect.name == "sqlite":
        return
    # PostgreSQL rejects this transaction if any large value cannot fit; never truncate.
    for table, columns in MONETARY_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table, column, existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=False
            )
