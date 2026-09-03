"""Create durable research schema and atomic runtime event sequencing.

Revision ID: 20260904_0001
Revises: None
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260904_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _payload() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _create_payload_table(
    name: str,
    id_column: str,
    *,
    unique_run: bool = False,
) -> None:
    table_items = [
        sa.Column(id_column, sa.String(256 if id_column == "task_id" else 128), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(128),
            sa.ForeignKey("research_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("payload", _payload(), nullable=False),
    ]
    if unique_run:
        table_items.append(sa.UniqueConstraint("run_id", name=f"uq_{name}_run"))
    op.create_table(name, *table_items)
    op.create_index(f"ix_{name}_run_id", name, ["run_id"])


def upgrade() -> None:
    op.create_table(
        "research_objects",
        sa.Column("object_id", sa.String(128), primary_key=True),
        sa.Column("payload", _payload(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "research_run_drafts",
        sa.Column("draft_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("payload", _payload(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["research_objects.object_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_run_drafts_object_id", "research_run_drafts", ["object_id"])
    op.create_table(
        "research_goals",
        sa.Column("goal_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("payload", _payload(), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["research_objects.object_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_research_goals_object_id", "research_goals", ["object_id"])
    op.create_table(
        "research_scheme_snapshots",
        sa.Column("scheme_id", sa.String(128), primary_key=True),
        sa.Column("goal_id", sa.String(128), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", _payload(), nullable=False),
        sa.ForeignKeyConstraint(["goal_id"], ["research_goals.goal_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_research_scheme_snapshots_goal_id", "research_scheme_snapshots", ["goal_id"]
    )
    op.create_table(
        "research_runs",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", _payload(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["object_id"], ["research_objects.object_id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_research_runs_object_id", "research_runs", ["object_id"])
    op.create_index("ix_research_runs_status", "research_runs", ["status"])

    _create_payload_table("tasks", "task_id")
    op.create_table(
        "runtime_event_counters",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("last_sequence > 0", name="ck_runtime_event_counter_positive"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "runtime_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", _payload(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_runtime_events_positive_sequence"),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_runtime_events_run_sequence"),
    )
    op.create_index("ix_runtime_events_run_id", "runtime_events", ["run_id"])

    op.create_table(
        "evidence_records",
        sa.Column("evidence_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("object_id", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(128), nullable=False),
        sa.Column("source_locator", sa.String(2048)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period", sa.String(64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("raw_artifact_ref", sa.String(2048), nullable=False),
        sa.Column("normalized_field", sa.String(256), nullable=False),
        sa.Column("normalized_value", _payload(), nullable=False),
        sa.Column("unit", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(8)),
        sa.Column("snapshot_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["object_id"], ["research_objects.object_id"], ondelete="RESTRICT"),
    )
    for column in ("run_id", "object_id", "snapshot_hash", "status"):
        op.create_index(f"ix_evidence_records_{column}", "evidence_records", [column])

    for name, id_column in (
        ("calculation_records", "calculation_id"),
        ("correction_records", "correction_id"),
        ("replan_records", "replan_id"),
        ("review_records", "review_id"),
    ):
        _create_payload_table(name, id_column)
    _create_payload_table("canonical_execution_records", "record_id", unique_run=True)
    _create_payload_table("released_research_results", "result_id", unique_run=True)
    op.create_table(
        "runtime_checkpoints",
        sa.Column("checkpoint_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", _payload(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["research_runs.run_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "checkpoint_id"),
    )
    op.create_index("ix_runtime_checkpoints_run_id", "runtime_checkpoints", ["run_id"])
    op.create_index("ix_runtime_checkpoints_created_at", "runtime_checkpoints", ["created_at"])

    op.execute(
        """
        CREATE FUNCTION allocate_runtime_event_sequence()
        RETURNS trigger AS $$
        DECLARE allocated_sequence integer;
        BEGIN
            IF NEW.sequence IS NULL THEN
                INSERT INTO runtime_event_counters (run_id, last_sequence)
                VALUES (NEW.run_id, 1)
                ON CONFLICT (run_id) DO UPDATE
                SET last_sequence = runtime_event_counters.last_sequence + 1
                RETURNING last_sequence INTO allocated_sequence;
                NEW.sequence := allocated_sequence;
                RETURN NEW;
            END IF;
            IF NEW.sequence = 1 THEN
                INSERT INTO runtime_event_counters (run_id, last_sequence)
                VALUES (NEW.run_id, 1)
                ON CONFLICT (run_id) DO NOTHING
                RETURNING last_sequence INTO allocated_sequence;
            ELSE
                UPDATE runtime_event_counters
                SET last_sequence = NEW.sequence
                WHERE run_id = NEW.run_id AND last_sequence = NEW.sequence - 1
                RETURNING last_sequence INTO allocated_sequence;
            END IF;
            IF allocated_sequence IS NULL THEN
                RAISE EXCEPTION 'runtime event sequence is not the next per-run value'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER runtime_events_allocate_sequence
        BEFORE INSERT ON runtime_events
        FOR EACH ROW EXECUTE FUNCTION allocate_runtime_event_sequence();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS runtime_events_allocate_sequence ON runtime_events")
    op.execute("DROP FUNCTION IF EXISTS allocate_runtime_event_sequence()")
    for table in (
        "runtime_checkpoints",
        "released_research_results",
        "canonical_execution_records",
        "review_records",
        "replan_records",
        "correction_records",
        "calculation_records",
        "evidence_records",
        "runtime_events",
        "runtime_event_counters",
        "tasks",
        "research_runs",
        "research_scheme_snapshots",
        "research_goals",
        "research_run_drafts",
        "research_objects",
    ):
        op.drop_table(table)
