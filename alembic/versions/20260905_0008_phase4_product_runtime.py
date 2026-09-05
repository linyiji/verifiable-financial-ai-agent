"""Add the Phase 4 Product transaction and durable scheduler authority.

Revision ID: 20260905_0008
Revises: 20260905_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260905_0008"
down_revision: str | None = "20260905_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "research_runs",
        sa.Column("projection_revision", sa.BigInteger(), nullable=False, server_default="1"),
    )
    op.add_column(
        "research_runs",
        sa.Column("projection_sequence", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_research_runs_projection_revision_positive",
        "research_runs",
        "projection_revision >= 1",
    )
    op.create_check_constraint(
        "ck_research_runs_projection_sequence_nonnegative",
        "research_runs",
        "projection_sequence >= 0",
    )

    for column in (
        sa.Column("draft_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("draft_hash", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_admission_id", sa.String(128), nullable=True),
        sa.Column("consumed_run_id", sa.String(128), nullable=True),
    ):
        op.add_column("research_run_drafts", column)
    op.create_check_constraint(
        "ck_research_run_drafts_consumption_all_or_none",
        "research_run_drafts",
        "(consumed_at IS NULL AND consumed_admission_id IS NULL AND consumed_run_id IS NULL) OR "
        "(consumed_at IS NOT NULL AND consumed_admission_id IS NOT NULL AND "
        "consumed_run_id IS NOT NULL)",
    )

    op.create_table(
        "phase4_idempotency_outcomes",
        sa.Column("outcome_id", sa.String(128), primary_key=True),
        sa.Column("access_scope", sa.String(64), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("route_template", sa.String(256), nullable=False),
        sa.Column("key_digest", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=True),
        sa.Column("draft_id", sa.String(128), nullable=True),
        sa.Column("run_id", sa.String(128), nullable=True),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "access_scope", "method", "route_template", "key_digest",
            name="uq_phase4_idempotency_scope_route_key",
        ),
    )

    op.create_table(
        "phase4_scheduler_admissions",
        sa.Column("admission_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("outcome_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("delivery_attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_delivery_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_generation", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("start_committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_started_event_id", sa.String(128), nullable=True),
        sa.Column("run_started_sequence", sa.BigInteger(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(128), nullable=True),
        sa.Column("policy_version", sa.String(128), nullable=False),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["outcome_id"], ["phase4_idempotency_outcomes.outcome_id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", name="uq_phase4_scheduler_run"),
        sa.UniqueConstraint("outcome_id", name="uq_phase4_scheduler_outcome"),
        sa.CheckConstraint("delivery_attempt_count >= 0", name="ck_phase4_scheduler_attempts"),
        sa.CheckConstraint("lease_generation >= 0", name="ck_phase4_scheduler_generation"),
        sa.CheckConstraint(
            "(start_committed_at IS NULL AND run_started_event_id IS NULL AND "
            "run_started_sequence IS NULL) OR "
            "(start_committed_at IS NOT NULL AND run_started_event_id IS NOT NULL AND "
            "run_started_sequence IS NOT NULL)",
            name="ck_phase4_scheduler_start_all_or_none",
        ),
    )
    op.create_index(
        "ix_phase4_scheduler_due",
        "phase4_scheduler_admissions",
        ["state", "next_attempt_at", "admission_id"],
    )

    op.create_table(
        "phase4_run_projections",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.CheckConstraint("revision >= 1", name="ck_phase4_projection_revision"),
        sa.CheckConstraint("sequence >= 0", name="ck_phase4_projection_sequence"),
    )
    op.create_index("ix_phase4_run_projections_object", "phase4_run_projections", ["object_id"])

    for table_name, id_name in (
        ("phase4_planned_graphs", "graph_id"),
        ("phase4_actual_graphs", "graph_id"),
        ("phase4_terminal_facts", "terminal_id"),
        ("phase4_review_check_identities", "check_id"),
        ("phase4_artifact_slots", "slot_id"),
        ("phase4_artifact_attempts", "attempt_id"),
        ("phase4_anchor_manifests", "manifest_id"),
        ("phase4_release_validations", "validation_id"),
    ):
        op.create_table(
            table_name,
            sa.Column(id_name, sa.String(128), primary_key=True),
            sa.Column("run_id", sa.String(128), nullable=False),
            sa.Column("payload", _jsonb(), nullable=False),
            sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        )
        op.create_index(f"ix_{table_name}_run", table_name, ["run_id"])
    op.create_unique_constraint(
        "uq_phase4_terminal_fact_run", "phase4_terminal_facts", ["run_id"]
    )
    op.create_unique_constraint(
        "uq_phase4_release_validation_run", "phase4_release_validations", ["run_id"]
    )


def downgrade() -> None:
    raise RuntimeError("20260905_0008 is a forward-only Phase 4 Product migration")
