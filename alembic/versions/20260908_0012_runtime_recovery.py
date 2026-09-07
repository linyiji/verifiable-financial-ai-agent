"""Append-only Phase 6 evidence; no historical backfill."""

import sqlalchemy as sa

from alembic import op

revision = "20260908_0012"
down_revision = "20260907_0011"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "phase6_recovery_evidence",
        sa.Column("record_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), nullable=False),
        sa.Column("task_id", sa.String(256), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_phase6_recovery_evidence_run_id", "phase6_recovery_evidence", ["run_id"])
    op.create_index("ix_phase6_recovery_evidence_task_id", "phase6_recovery_evidence", ["task_id"])
    op.execute("""CREATE UNIQUE INDEX phase6_recovery_single_entry
    ON phase6_recovery_evidence(run_id,task_id)
    WHERE payload->>'kind'='ATTEMPT_STARTED' AND payload->>'attempt_number'='1'
    AND payload->>'capability_check'='false'""")
    op.execute("""CREATE FUNCTION phase6_recovery_immutable() RETURNS trigger AS $$
    BEGIN RAISE EXCEPTION 'recovery evidence is immutable'; END; $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER phase6_recovery_immutable BEFORE UPDATE OR DELETE
    ON phase6_recovery_evidence FOR EACH ROW EXECUTE FUNCTION phase6_recovery_immutable()""")


def downgrade():
    op.drop_table("phase6_recovery_evidence")
    op.execute("DROP FUNCTION phase6_recovery_immutable()")
