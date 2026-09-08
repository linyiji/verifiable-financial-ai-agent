"""Optional original-document authority; existing evidence and hashes are unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "20260908_0014"
down_revision = "20260908_0013"
branch_labels = depends_on = None


def upgrade():
    op.add_column("evidence_records", sa.Column("document_authority", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Document provenance must not be destructively discarded")
