"""Add Phase 2.1 evidence ownership and observation semantics.

Revision ID: 20260904_0002
Revises: 20260904_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904_0002"
down_revision: str | None = "20260904_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_records", sa.Column("producer_task_id", sa.String(256)))
    op.add_column("evidence_records", sa.Column("source_endpoint", sa.String(128)))
    op.add_column("evidence_records", sa.Column("evidence_purpose", sa.String(256)))
    op.add_column(
        "evidence_records",
        sa.Column(
            "evidence_category",
            sa.String(32),
            nullable=False,
            server_default="OTHER",
        ),
    )
    op.add_column("evidence_records", sa.Column("observed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "evidence_records",
        sa.Column("provider_timestamp", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_evidence_records_producer_task_id",
        "evidence_records",
        ["producer_task_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_records_producer_task_id", table_name="evidence_records")
    for column in (
        "provider_timestamp",
        "observed_at",
        "evidence_category",
        "evidence_purpose",
        "source_endpoint",
        "producer_task_id",
    ):
        op.drop_column("evidence_records", column)
