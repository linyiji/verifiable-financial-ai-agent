"""Add one-shot execution authorization; no Run backfill or historical rewrites."""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0011"
down_revision = "20260907_0010"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "reexecution_authorizations",
        sa.Column("authorization_id", sa.String(128), primary_key=True),
        sa.Column(
            "prior_run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), nullable=False
        ),
        sa.Column("key_digest", sa.String(128), unique=True, nullable=False),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "consumed_by_run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), unique=True
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("admission_key_digest", sa.String(128), unique=True),
        sa.Column("admission_response", sa.JSON()),
        sa.CheckConstraint(
            "(consumed_by_run_id IS NULL AND consumed_at IS NULL AND admission_key_digest IS NULL "
            "AND admission_response IS NULL) OR (consumed_by_run_id IS NOT NULL AND consumed_at "
            "IS NOT NULL AND admission_key_digest IS NOT NULL AND admission_response IS NOT NULL)",
            name="ck_reexecution_consumption_atomic",
        ),
    )
    op.create_index(
        "ix_reexecution_authorizations_prior_run_id", "reexecution_authorizations", ["prior_run_id"]
    )
    op.execute("""CREATE FUNCTION protect_reexecution_authorization() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'authorization is durable'; END IF;
        IF OLD.payload::jsonb IS DISTINCT FROM NEW.payload::jsonb
          OR OLD.authorization_id <> NEW.authorization_id OR OLD.prior_run_id <> NEW.prior_run_id
          OR OLD.key_digest <> NEW.key_digest OR OLD.request_hash <> NEW.request_hash
          OR OLD.consumed_by_run_id IS NOT NULL
        THEN RAISE EXCEPTION 'authorization identity and consumption are immutable'; END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER reexecution_authorization_immutable BEFORE UPDATE OR DELETE
      ON reexecution_authorizations FOR EACH ROW
      EXECUTE FUNCTION protect_reexecution_authorization()""")
    op.execute("""CREATE FUNCTION protect_run_reexecution_lineage() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.payload::jsonb #> '{run,reexecution_of_run_id}' IS DISTINCT FROM
           NEW.payload::jsonb #> '{run,reexecution_of_run_id}'
        THEN RAISE EXCEPTION 'Run execution lineage is immutable'; END IF;
        IF OLD.payload::jsonb #>> '{run,reexecution_of_run_id}' IS NOT NULL AND (
          OLD.payload::jsonb -> 'scheme' IS DISTINCT FROM NEW.payload::jsonb -> 'scheme'
          OR OLD.payload::jsonb -> 'goal' IS DISTINCT FROM NEW.payload::jsonb -> 'goal'
          OR OLD.payload::jsonb #> '{run,base_run_id}' IS DISTINCT FROM
             NEW.payload::jsonb #> '{run,base_run_id}'
          OR OLD.payload::jsonb #> '{run,base_research_view_version}' IS DISTINCT FROM
             NEW.payload::jsonb #> '{run,base_research_view_version}')
        THEN RAISE EXCEPTION 're-execution research intent is immutable'; END IF;
        RETURN NEW;
      END $$""")
    op.execute("""CREATE TRIGGER run_reexecution_lineage_immutable BEFORE UPDATE
      ON research_runs FOR EACH ROW EXECUTE FUNCTION protect_run_reexecution_lineage()""")


def downgrade():
    op.execute("DROP TRIGGER run_reexecution_lineage_immutable ON research_runs")
    op.execute("DROP FUNCTION protect_run_reexecution_lineage()")
    op.drop_table("reexecution_authorizations")
    op.execute("DROP FUNCTION protect_reexecution_authorization()")
