"""Retain immutable generated capability source and test artifact bindings.

Revision ID: 20260904_0006
Revises: 20260904_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260904_0006"
down_revision: str | None = "20260904_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "generated_capability_artifact_records",
        sa.Column(
            "build_id",
            sa.String(128),
            sa.ForeignKey("capability_build_records.build_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("research_runs.run_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "generated_capability_id",
            sa.String(128),
            sa.ForeignKey(
                "generated_capability_records.generated_capability_id",
                ondelete="RESTRICT",
            ),
            nullable=False,
            unique=True,
        ),
        sa.Column("capability_id", sa.String(256), nullable=False),
        sa.Column("capability_version", sa.String(128), nullable=False),
        sa.Column("source_artifact_id", sa.String(80), nullable=False),
        sa.Column("source_artifact_ref", sa.String(2048), nullable=False),
        sa.Column("source_sha256", sa.String(80), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("test_artifact_id", sa.String(80), nullable=False),
        sa.Column("test_artifact_ref", sa.String(2048), nullable=False),
        sa.Column("test_sha256", sa.String(80), nullable=False),
        sa.Column("test_size_bytes", sa.Integer(), nullable=False),
        sa.Column("implementation_hash", sa.String(80), nullable=False),
        sa.Column("runtime_image_identity", sa.String(512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source_size_bytes > 0",
            name="ck_generated_source_size_positive",
        ),
        sa.CheckConstraint(
            "test_size_bytes > 0",
            name="ck_generated_test_size_positive",
        ),
        sa.CheckConstraint(
            "source_artifact_id = source_sha256",
            name="ck_generated_source_content_addressed",
        ),
        sa.CheckConstraint(
            "test_artifact_id = test_sha256",
            name="ck_generated_test_content_addressed",
        ),
        sa.CheckConstraint(
            "implementation_hash = source_sha256",
            name="ck_generated_implementation_binding",
        ),
    )
    op.create_index(
        "ix_generated_capability_artifact_records_run_id",
        "generated_capability_artifact_records",
        ["run_id"],
    )


def downgrade() -> None:
    raise RuntimeError("20260904_0006 is a forward-only audit-retention migration")
