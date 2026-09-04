"""Persist typed Phase 3 financial evidence semantics.

Revision ID: 20260904_0005
Revises: 20260904_0004
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904_0005"
down_revision: str | None = "20260904_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("evidence_records", sa.Column("period_basis", sa.String(16)))
    op.add_column(
        "evidence_records",
        sa.Column(
            "actuality",
            sa.String(16),
            nullable=False,
            server_default="UNKNOWN",
        ),
    )
    op.add_column("evidence_records", sa.Column("statement_series", sa.String(512)))
    op.add_column("evidence_records", sa.Column("statement_cohort", sa.String(768)))
    op.add_column("evidence_records", sa.Column("technical_price_basis", sa.String(32)))
    op.add_column("evidence_records", sa.Column("corporate_action_status", sa.String(32)))
    op.add_column("evidence_records", sa.Column("cash_flow_sign_convention", sa.String(32)))
    op.add_column(
        "evidence_records",
        sa.Column(
            "cash_flow_normalization_applied",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    for column in (
        "cash_flow_normalization_applied",
        "cash_flow_sign_convention",
        "corporate_action_status",
        "technical_price_basis",
        "statement_cohort",
        "statement_series",
        "actuality",
        "period_basis",
    ):
        op.drop_column("evidence_records", column)
