"""Persist queryable planned and actual task dependency edges.

Revision ID: 20260904_0003
Revises: 20260904_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260904_0003"
down_revision: str | None = "20260904_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_dependencies",
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("graph_kind", sa.String(16), nullable=False),
        sa.Column("task_id", sa.String(256), nullable=False),
        sa.Column("dependency_task_id", sa.String(256), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "graph_kind IN ('PLANNED', 'ACTUAL')",
            name="ck_task_dependencies_graph_kind",
        ),
        sa.CheckConstraint("position >= 0", name="ck_task_dependencies_position"),
        sa.CheckConstraint(
            "task_id <> dependency_task_id",
            name="ck_task_dependencies_not_self",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["research_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dependency_task_id"],
            ["tasks.task_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "run_id",
            "graph_kind",
            "task_id",
            "dependency_task_id",
        ),
        sa.UniqueConstraint(
            "run_id",
            "graph_kind",
            "task_id",
            "position",
            name="uq_task_dependencies_position",
        ),
    )
    op.create_index(
        "ix_task_dependencies_run_graph",
        "task_dependencies",
        ["run_id", "graph_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_dependencies_run_graph", table_name="task_dependencies")
    op.drop_table("task_dependencies")
