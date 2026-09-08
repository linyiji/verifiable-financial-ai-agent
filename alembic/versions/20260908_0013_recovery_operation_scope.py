"""Separate owned recovery operations without rewriting immutable evidence."""

from alembic import op

revision = "20260908_0013"
down_revision = "20260908_0012"
branch_labels = depends_on = None


def upgrade():
    op.drop_index("phase6_recovery_single_entry", table_name="phase6_recovery_evidence")
    op.execute("""CREATE UNIQUE INDEX phase6_recovery_single_entry
    ON phase6_recovery_evidence(run_id, task_id,
      (coalesce(payload->'scope'->>'operation_id', 'specialist')))
    WHERE payload->>'kind'='ATTEMPT_STARTED' AND payload->>'attempt_number'='1'
    AND payload->>'capability_check'='false'""")


def downgrade():
    # A downgrade that loses operation identity cannot safely admit new attempts.
    raise RuntimeError("Recovery operation identity migration is forward-only")
