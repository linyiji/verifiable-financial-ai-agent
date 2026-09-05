"""Widen Phase 4 runtime event sequences to signed 64-bit values.

Revision ID: 20260905_0007
Revises: 20260904_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260905_0007"
down_revision: str | None = "20260904_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "runtime_events",
        "sequence",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="sequence::bigint",
    )
    op.alter_column(
        "runtime_event_counters",
        "last_sequence",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=False,
        postgresql_using="last_sequence::bigint",
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION allocate_runtime_event_sequence()
        RETURNS trigger AS $$
        DECLARE allocated_sequence bigint;
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
                WHERE run_id = NEW.run_id
                  AND last_sequence = NEW.sequence - 1
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


def downgrade() -> None:
    raise RuntimeError("20260905_0007 is a forward-only sequence-width migration")
