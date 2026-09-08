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
from src.observability.performance import annotate, observe
from src.runtime.events import (
    CursorPreflight,
    EventReconciliationRequired,
    EventRecoveryReason,
    EventSequenceError,
    RuntimeEventCursor,
    _validate_after_sequence,
    build_cursor_preflight,
)

POSTGRES_EVENT_SEQUENCE_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION allocate_runtime_event_sequence()
RETURNS trigger AS $$
DECLARE
    allocated_sequence bigint;
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

POSTGRES_RUN_EVENT_WRITE_LOCK_SQL = """
SELECT pg_advisory_xact_lock(hashtextextended(:run_id, 0))
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

    @observe("event.durable_commit", run="run_id")
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
        annotate(event_id=event_id, task_id=task_id)
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
                await self._lock_run_event_writes(session, run_id)
                await self._reject_post_terminal_write(session, run_id)
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
                annotate(event_sequence=sequence)
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
        _validate_after_sequence(after_sequence)
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
            if rows and rows[0].payload.get("type") == "closure.recovery_started":
                # A suffix beginning at the recovery boundary must validate its
                # failed predecessor, rather than treating it as an unbound restart.
                full_rows = (
                    await session.scalars(
                        select(RuntimeEventRow)
                        .where(RuntimeEventRow.run_id == run_id)
                        .order_by(RuntimeEventRow.sequence)
                    )
                ).all()
                return [
                    event
                    for event in self._decode_rows(
                        run_id=run_id, rows=full_rows, committed_sequence=0
                    )
                    if event.sequence > after_sequence
                ]
        return self._decode_rows(
            run_id=run_id,
            rows=rows,
            committed_sequence=after_sequence,
        )

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
        return (await self.preflight_cursor(run_id, last_event_id)).sequence

    async def preflight_cursor(self, run_id: str, last_event_id: str | None) -> CursorPreflight:
        async with self._sessions() as session, session.begin():
            self._require_postgresql(session)
            statement = (
                select(RuntimeEventRow)
                .where(RuntimeEventRow.run_id == run_id)
                .order_by(RuntimeEventRow.sequence)
            )
            rows = (await session.scalars(statement)).all()
            events = self._decode_rows(run_id=run_id, rows=rows, committed_sequence=0)
            return build_cursor_preflight(
                run_id=run_id,
                last_event_id=last_event_id,
                events=events,
            )

    async def _insert_event(self, *, event: RuntimeEvent, requested_sequence: int) -> None:
        try:
            async with self._sessions() as session, session.begin():
                self._require_postgresql(session)
                await self._lock_run_event_writes(session, event.run_id)
                await self._reject_post_terminal_write(session, event.run_id)
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

    @staticmethod
    async def _lock_run_event_writes(session: AsyncSession, run_id: str) -> None:
        await session.execute(text(POSTGRES_RUN_EVENT_WRITE_LOCK_SQL), {"run_id": run_id})

    @staticmethod
    async def _reject_post_terminal_write(session: AsyncSession, run_id: str) -> None:
        statement = (
            select(RuntimeEventRow)
            .where(RuntimeEventRow.run_id == run_id)
            .order_by(RuntimeEventRow.sequence.desc())
            .limit(1)
        )
        row = (await session.scalars(statement)).first()
        if row is None:
            return
        event = PostgresRuntimeEventStore._decode_row(run_id, row)
        if event.type in {RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED}:
            raise EventSequenceError(f"run {run_id} is already terminal")

    @staticmethod
    def _decode_row(run_id: str, row: RuntimeEventRow) -> RuntimeEvent:
        try:
            event = RuntimeEvent.model_validate(row.payload)
        except (TypeError, ValueError) as exc:
            raise EventReconciliationRequired(
                EventRecoveryReason.MALFORMED_EVENT,
                run_id=run_id,
                committed_sequence=max(row.sequence - 1, 0),
                received_sequence=row.sequence,
            ) from exc
        if (
            row.run_id != run_id
            or event.run_id != run_id
            or event.event_id != row.event_id
            or event.sequence != row.sequence
        ):
            raise EventReconciliationRequired(
                EventRecoveryReason.PERSISTED_EVENT_MISMATCH,
                run_id=run_id,
                committed_sequence=max(row.sequence - 1, 0),
                received_sequence=row.sequence,
            )
        return event

    @classmethod
    def _decode_rows(
        cls,
        *,
        run_id: str,
        rows: Sequence[RuntimeEventRow],
        committed_sequence: int,
    ) -> list[RuntimeEvent]:
        cursor = RuntimeEventCursor(
            run_id=run_id,
            committed_sequence=committed_sequence,
        )
        events: list[RuntimeEvent] = []
        for row in rows:
            event = cls._decode_row(run_id, row)
            cursor.accept(event)
            events.append(event)
        return events
