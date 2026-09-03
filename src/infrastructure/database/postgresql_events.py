from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

from src.application.persistence import RuntimeEventRow
from src.domain.base import utc_now
from src.domain.runtime_event import RuntimeEvent, RuntimeEventType
from src.runtime.events import EventSequenceError

POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION allocate_runtime_event_sequence()
RETURNS trigger AS $$
DECLARE
    allocated_sequence integer;
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

POSTGRES_EVENT_SEQUENCE_TRIGGER_SQL = """
CREATE TRIGGER runtime_events_allocate_sequence
BEFORE INSERT ON runtime_events
FOR EACH ROW EXECUTE FUNCTION allocate_runtime_event_sequence();
"""


async def install_postgresql_runtime_event_sequence(connection: AsyncConnection) -> None:
    """Install the DB-enforced per-run allocator after tables exist."""

    if connection.dialect.name != "postgresql":
        raise ValueError("runtime event sequence trigger requires PostgreSQL")
    await connection.execute(text(POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL))
    await connection.execute(
        text("DROP TRIGGER IF EXISTS runtime_events_allocate_sequence ON runtime_events")
    )
    await connection.execute(text(POSTGRES_EVENT_SEQUENCE_TRIGGER_SQL))


class PostgresRuntimeEventStore:
    """Durable RuntimeEventStore using an atomic PostgreSQL trigger allocator."""

    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self._sessions = sessions
        self._poll_interval_seconds = poll_interval_seconds

    async def append(self, event: RuntimeEvent) -> None:
        await self._insert_event(event=event, requested_sequence=event.sequence)

    async def emit(
        self,
        *,
        run_id: str,
        event_type: RuntimeEventType,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> RuntimeEvent:
        occurred_at = timestamp or utc_now()
        event_id = f"EVT-{uuid4()}"
        partial_payload = {
            "event_id": event_id,
            "run_id": run_id,
            "task_id": task_id,
            "type": event_type.value,
            "timestamp": occurred_at.isoformat(),
            "payload": payload or {},
        }
        try:
            async with self._sessions() as session, session.begin():
                self._require_postgresql(session)
                statement = (
                    insert(RuntimeEventRow)
                    .values(
                        event_id=event_id,
                        run_id=run_id,
                        sequence=None,
                        payload=partial_payload,
                    )
                    .returning(RuntimeEventRow.sequence)
                )
                sequence = await session.scalar(statement)
                if sequence is None:
                    raise RuntimeError("PostgreSQL did not allocate an event sequence")
                event = RuntimeEvent(
                    event_id=event_id,
                    run_id=run_id,
                    task_id=task_id,
                    type=event_type,
                    timestamp=occurred_at,
                    sequence=sequence,
                    payload=payload or {},
                )
                await session.execute(
                    update(RuntimeEventRow)
                    .where(RuntimeEventRow.event_id == event_id)
                    .values(payload=event.model_dump(mode="json"))
                )
            return event
        except (IntegrityError, DBAPIError) as exc:
            raise EventSequenceError("database rejected runtime event sequence") from exc

    async def replay(self, run_id: str, *, after_sequence: int = 0) -> list[RuntimeEvent]:
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        async with self._sessions() as session:
            self._require_postgresql(session)
            statement = (
                select(RuntimeEventRow)
                .where(
                    RuntimeEventRow.run_id == run_id,
                    RuntimeEventRow.sequence > after_sequence,
                )
                .order_by(RuntimeEventRow.sequence)
            )
            rows = (await session.scalars(statement)).all()
        return [RuntimeEvent.model_validate(row.payload) for row in rows]

    async def wait_for_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        timeout_seconds: float,
    ) -> Sequence[RuntimeEvent]:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        deadline = monotonic() + timeout_seconds
        while True:
            events = await self.replay(run_id, after_sequence=after_sequence)
            if events:
                return events
            remaining = deadline - monotonic()
            if remaining <= 0:
                return []
            await asyncio.sleep(min(self._poll_interval_seconds, remaining))

    async def resolve_resume_sequence(self, run_id: str, last_event_id: str | None) -> int:
        if not last_event_id:
            return 0
        try:
            sequence = int(last_event_id)
        except ValueError:
            async with self._sessions() as session:
                self._require_postgresql(session)
                statement = select(RuntimeEventRow.sequence).where(
                    RuntimeEventRow.run_id == run_id,
                    RuntimeEventRow.event_id == last_event_id,
                )
                sequence = await session.scalar(statement)
            if sequence is None:
                raise KeyError(f"event id not found for run {run_id}: {last_event_id}") from None
            return sequence
        if sequence < 0:
            raise ValueError("Last-Event-ID sequence cannot be negative")
        return sequence

    async def _insert_event(self, *, event: RuntimeEvent, requested_sequence: int) -> None:
        try:
            async with self._sessions() as session, session.begin():
                self._require_postgresql(session)
                await session.execute(
                    insert(RuntimeEventRow).values(
                        event_id=event.event_id,
                        run_id=event.run_id,
                        sequence=requested_sequence,
                        payload=event.model_dump(mode="json"),
                    )
                )
        except (IntegrityError, DBAPIError) as exc:
            raise EventSequenceError("database rejected runtime event sequence") from exc

    @staticmethod
    def _require_postgresql(session: AsyncSession) -> None:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql":
            raise RuntimeError("PostgresRuntimeEventStore requires a PostgreSQL session")
