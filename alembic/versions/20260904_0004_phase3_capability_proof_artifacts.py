"""Add Phase 3 capability, proof, and report artifact records.

Revision ID: 20260904_0004
Revises: 20260904_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260904_0004"
down_revision: str | None = "20260904_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _payload() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _create_payload_table(name: str, id_column: str) -> None:
    op.create_table(
        name,
        sa.Column(id_column, sa.String(128), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", _payload(), nullable=False),
    )
    op.create_index(f"ix_{name}_run_id", name, ["run_id"])


def upgrade() -> None:
    for name, id_column in (
        ("capability_gap_records", "gap_id"),
        ("capability_build_records", "build_id"),
        ("generated_capability_records", "generated_capability_id"),
        ("sandbox_execution_records", "execution_id"),
        ("capability_validation_records", "validation_id"),
        ("scoped_capability_registrations", "registration_id"),
        ("proof_policy_decisions", "decision_id"),
        ("proof_input_commitments", "commitment_id"),
        ("proof_records", "proof_id"),
        ("proof_artifact_references", "artifact_id"),
        ("proof_verification_records", "verification_id"),
        ("report_artifact_records", "artifact_id"),
    ):
        _create_payload_table(name, id_column)


def downgrade() -> None:
    for name in reversed(
        (
            "capability_gap_records",
            "capability_build_records",
            "generated_capability_records",
            "sandbox_execution_records",
            "capability_validation_records",
            "scoped_capability_registrations",
            "proof_policy_decisions",
            "proof_input_commitments",
            "proof_records",
            "proof_artifact_references",
            "proof_verification_records",
            "report_artifact_records",
        )
    ):
        op.drop_table(name)
