"""Add append-only Phase 5A assets and explicit pointers, without historical rewrites."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "20260907_0009"
down_revision = "20260905_0008"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "research_object_versions",
        sa.Column(
            "object_id",
            sa.String(128),
            sa.ForeignKey("research_objects.object_id"),
            primary_key=True,
        ),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column(
            "source_run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), nullable=False
        ),
        sa.Column("payload", JSONB(), nullable=False),
        sa.UniqueConstraint("object_id", "source_run_id"),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_table(
        "research_view_versions",
        sa.Column("object_id", sa.String(128), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("object_version", sa.Integer(), nullable=False),
        sa.Column(
            "source_run_id", sa.String(128), sa.ForeignKey("research_runs.run_id"), nullable=False
        ),
        sa.Column("payload", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "object_version"],
            ["research_object_versions.object_id", "research_object_versions.version"],
        ),
        sa.UniqueConstraint("object_id", "source_run_id"),
        sa.UniqueConstraint("object_id", "object_version"),
        sa.CheckConstraint("version >= 1"),
    )
    op.create_table(
        "research_object_memory_pointers",
        sa.Column(
            "object_id",
            sa.String(128),
            sa.ForeignKey("research_objects.object_id"),
            primary_key=True,
        ),
        sa.Column(
            "latest_released_run_id",
            sa.String(128),
            sa.ForeignKey("research_runs.run_id"),
            nullable=False,
        ),
        sa.Column("latest_research_object_version", sa.Integer(), nullable=False),
        sa.Column("latest_research_view_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["object_id", "latest_research_object_version"],
            ["research_object_versions.object_id", "research_object_versions.version"],
        ),
        sa.ForeignKeyConstraint(
            ["object_id", "latest_research_view_version"],
            ["research_view_versions.object_id", "research_view_versions.version"],
        ),
    )
    op.execute("""CREATE FUNCTION phase5a_reject_asset_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'research asset versions are append-only'; END $$""")
    for table in ("research_object_versions", "research_view_versions"):
        op.execute(
            f"CREATE TRIGGER phase5a_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION phase5a_reject_asset_mutation()"
        )


def downgrade():
    # Explicit migration rollback removes only newly introduced Phase 5A assets.
    for table in (
        "research_object_memory_pointers",
        "research_view_versions",
        "research_object_versions",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION phase5a_reject_asset_mutation()")
