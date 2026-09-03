from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from src.domain.runtime_event import RuntimeEvent, RuntimeEventType


class EventSequenceError(ValueError):
    pass


@runtime_checkable
class RuntimeEventStore(Protocol):
    async def append(self, event: RuntimeEvent) -> None: ...

    async def emit(
        self,
        *,
        run_id: str,
        event_type: RuntimeEventType,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> RuntimeEvent: ...

    async def replay(self, run_id: str, *, after_sequence: int = 0) -> Sequence[RuntimeEvent]: ...

    async def wait_for_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        timeout_seconds: float,
    ) -> Sequence[RuntimeEvent]: ...

    async def resolve_resume_sequence(self, run_id: str, last_event_id: str | None) -> int: ...


class InMemoryRuntimeEventStore:
    """Concurrency-safe event log with per-run monotonic sequences.

    This is the Foundation persistence baseline. The protocol intentionally keeps
    scheduler and SSE code independent from the future SQL-backed implementation.
    """

    def __init__(self) -> None:
        self._events: dict[str, list[RuntimeEvent]] = defaultdict(list)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._conditions: dict[str, asyncio.Condition] = defaultdict(asyncio.Condition)

    async def append(self, event: RuntimeEvent) -> None:
        async with self._locks[event.run_id]:
            current = self._events[event.run_id]
            expected = current[-1].sequence + 1 if current else 1
            if event.sequence != expected:
                raise EventSequenceError(
                    f"run {event.run_id} expected sequence {expected}, got {event.sequence}"
                )
            if any(existing.event_id == event.event_id for existing in current):
                raise EventSequenceError(f"duplicate event id: {event.event_id}")
            current.append(event.model_copy(deep=True))
        await self._notify(event.run_id)

    async def emit(
        self,
        *,
        run_id: str,
        event_type: RuntimeEventType,
        task_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: datetime | None = None,
    ) -> RuntimeEvent:
        async with self._locks[run_id]:
            current = self._events[run_id]
            event_data: dict[str, Any] = {
                "event_id": f"EVT-{uuid4()}",
                "run_id": run_id,
                "task_id": task_id,
                "type": event_type,
                "sequence": len(current) + 1,
                "payload": payload or {},
            }
            if timestamp is not None:
                event_data["timestamp"] = timestamp
            event = RuntimeEvent(**event_data)
            current.append(event.model_copy(deep=True))
        await self._notify(run_id)
        return event

    async def replay(self, run_id: str, *, after_sequence: int = 0) -> list[RuntimeEvent]:
        if after_sequence < 0:
            raise ValueError("after_sequence cannot be negative")
        async with self._locks[run_id]:
            return [
                event.model_copy(deep=True)
                for event in self._events[run_id]
                if event.sequence > after_sequence
            ]

    async def wait_for_events(
        self,
        run_id: str,
        *,
        after_sequence: int,
        timeout_seconds: float,
    ) -> list[RuntimeEvent]:
        events = await self.replay(run_id, after_sequence=after_sequence)
        if events:
            return events

        condition = self._conditions[run_id]
        try:
            async with condition:
                # Re-check after acquiring the condition to close the replay/wait race.
                events = await self.replay(run_id, after_sequence=after_sequence)
                if events:
                    return events
                await asyncio.wait_for(condition.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return []
        return await self.replay(run_id, after_sequence=after_sequence)

    async def resolve_resume_sequence(self, run_id: str, last_event_id: str | None) -> int:
        if not last_event_id:
            return 0
        try:
            sequence = int(last_event_id)
        except ValueError:
            async with self._locks[run_id]:
                for event in self._events[run_id]:
                    if event.event_id == last_event_id:
                        return event.sequence
            raise KeyError(f"event id not found for run {run_id}: {last_event_id}") from None
        if sequence < 0:
            raise ValueError("Last-Event-ID sequence cannot be negative")
        return sequence

    async def _notify(self, run_id: str) -> None:
        async with self._conditions[run_id]:
            self._conditions[run_id].notify_all()
