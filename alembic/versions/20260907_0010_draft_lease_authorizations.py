"""Separate append-only authorization time from immutable draft content."""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0010"
down_revision = "20260907_0009"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "draft_lease_authorizations",
        sa.Column("lease_id", sa.String(128), primary_key=True),
        sa.Column(
            "draft_id",
            sa.String(128),
            sa.ForeignKey("research_run_drafts.draft_id"),
            nullable=False,
        ),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_draft_lease_authorizations_draft_id", "draft_lease_authorizations", ["draft_id"]
    )
    op.execute("""CREATE FUNCTION reject_draft_lease_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'draft lease authorizations are append-only'; END $$""")
    op.execute("""CREATE TRIGGER draft_lease_append_only BEFORE UPDATE OR DELETE
        ON draft_lease_authorizations FOR EACH ROW
        EXECUTE FUNCTION reject_draft_lease_mutation()""")


def downgrade():
    op.drop_table("draft_lease_authorizations")
    op.execute("DROP FUNCTION reject_draft_lease_mutation()")
