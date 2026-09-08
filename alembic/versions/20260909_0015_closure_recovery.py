"""Append-only owner-authorized closure recovery audit, preserving failure snapshots."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0015"
down_revision = "20260908_0014"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "closure_recovery_records",
        sa.Column("record_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("run_id", "kind"),
    )
    op.create_index("ix_closure_recovery_records_run_id", "closure_recovery_records", ["run_id"])
    op.execute("""CREATE FUNCTION reject_closure_audit_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'closure recovery history is immutable'; END;
        $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER closure_audit_immutable BEFORE UPDATE OR DELETE
        ON closure_recovery_records FOR EACH ROW
        EXECUTE FUNCTION reject_closure_audit_mutation()""")


def downgrade():
    raise RuntimeError("Recovery history must not be discarded")
