"""Explicit historical format boundary; no semantic payload backfill."""

import sqlalchemy as sa

from alembic import op

revision = "20260921_0018"
down_revision = "20260920_0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("research_runs", sa.Column(
        "aggregate_schema_version", sa.Integer(), nullable=False, server_default="1"
    ))
    op.create_check_constraint(
        "ck_research_runs_aggregate_schema_version", "research_runs",
        "aggregate_schema_version IN (1, 2)"
    )
    op.alter_column("research_runs", "aggregate_schema_version", server_default=None)


def downgrade():
    raise RuntimeError("Confirmation authority format provenance cannot be erased")
