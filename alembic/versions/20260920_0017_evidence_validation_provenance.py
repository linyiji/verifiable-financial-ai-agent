"""Retain original evidence validation policy; no historical backfill or enrollment."""

import sqlalchemy as sa

from alembic import op

revision = "20260920_0017"
down_revision = "20260909_0016"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "evidence_records", sa.Column("validation_provenance", sa.JSON(), nullable=True)
    )


def downgrade():
    raise RuntimeError("Evidence validation provenance is retained immutable evidence")
