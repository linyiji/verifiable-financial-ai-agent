"""Add opt-in recoverable execution ledger; never backfill historical Runs."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0016"
down_revision = "20260909_0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "execution_intents_v1",
        sa.Column("intent_id", sa.String(128), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )


def downgrade():
    raise RuntimeError("V1 rollback disables admission; durable ledgers must be retained")
