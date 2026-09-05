from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from src.domain.runtime_event import RuntimeEvent, RuntimeEventType


class EventSequenceError(ValueError):
    pass


MAX_RESUME_SEQUENCE = (2**63) - 1
_CANONICAL_NUMERIC_CURSOR = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SIGNED_OR_NONCANONICAL_NUMERIC_CURSOR = re.compile(r"[+-]?[0-9]+\Z")
_OPAQUE_EVENT_CURSOR = re.compile(r"[A-Za-z0-9._:-]{1,256}\Z")
_TERMINAL_EVENT_TYPES = frozenset({RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED})


class CursorErrorCode(StrEnum):
    INVALID_CURSOR = "INVALID_CURSOR"
    CURSOR_AHEAD = "CURSOR_AHEAD"


class CursorPreflightError(ValueError):
    """Safe, pre-header cursor rejection for the public SSE adapter."""

    recovery = "SNAPSHOT_RELOAD"
    retryable = False

    def __init__(self, code: CursorErrorCode) -> None:
        self.code = code
        self.status_code = 400 if code is CursorErrorCode.INVALID_CURSOR else 409
        message = (
            "runtime event cursor is invalid"
            if code is CursorErrorCode.INVALID_CURSOR
            else "runtime event cursor is ahead of the durable Run tail"
        )
        super().__init__(message)


class EventRecoveryReason(StrEnum):
    WRONG_RUN = "WRONG_RUN"
    MALFORMED_EVENT = "MALFORMED_EVENT"
    PERSISTED_EVENT_MISMATCH = "PERSISTED_EVENT_MISMATCH"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    STALE_EVENT = "STALE_EVENT"
    DUPLICATE_SEQUENCE = "DUPLICATE_SEQUENCE"
    CONFLICTING_DUPLICATE = "CONFLICTING_DUPLICATE"
    DUPLICATE_EVENT_ID = "DUPLICATE_EVENT_ID"
    POST_TERMINAL_EVENT = "POST_TERMINAL_EVENT"


class EventReconciliationRequired(RuntimeError):
    """Signals that reduction must stop until an exact-Run snapshot is reloaded."""

    code = "INTEGRITY_FAILURE"
    recovery = "SNAPSHOT_RELOAD"
    retryable = False
    status_code = 500

    def __init__(
        self,
        reason: EventRecoveryReason,
        *,
        run_id: str,
        committed_sequence: int,
        received_sequence: int | None = None,
    ) -> None:
        self.reason = reason
        self.run_id = run_id
        self.committed_sequence = committed_sequence
        self.received_sequence = received_sequence
        super().__init__(f"runtime event reconciliation required: {reason.value}")


class EventApplyDisposition(StrEnum):
    APPLIED = "APPLIED"
    DUPLICATE_IGNORED = "DUPLICATE_IGNORED"


TerminalOutcome = Literal["SUCCESS", "FAILURE", "CANCELLED"]


@dataclass(frozen=True, slots=True)
class CursorPreflight:
    """An exact-Run resume point validated before SSE response headers."""

    run_id: str
    sequence: int
    tail_sequence: int
    terminal_sequence: int | None = None
    terminal_event_id: str | None = None
    terminal_outcome: TerminalOutcome | None = None
    terminal_event: RuntimeEvent | None = field(default=None, repr=False, compare=False)

    @property
    def terminal_at_cursor(self) -> bool:
        return self.terminal_sequence is not None and self.sequence == self.terminal_sequence


@dataclass(slots=True)
class RuntimeEventCursor:
    """Fail-closed, same-Run cursor used by stream consumers.

    The cursor advances only after an exact next event is accepted. Exact canonical
    duplicates observed by this cursor are idempotent; all other stale, conflicting,
    foreign, gapped, or post-terminal events require snapshot reconciliation.
    """

    run_id: str
    committed_sequence: int = 0
    terminal_sequence: int | None = None
    _by_sequence: dict[int, tuple[str, str]] = field(default_factory=dict, repr=False)
    _sequence_by_event_id: dict[str, int] = field(default_factory=dict, repr=False)

    def accept(self, event: RuntimeEvent) -> EventApplyDisposition:
        fingerprint = _event_fingerprint(event)

        if event.run_id != self.run_id:
            raise self._recovery(EventRecoveryReason.WRONG_RUN, event.sequence)

        if not event.event_id:
            raise self._recovery(EventRecoveryReason.MALFORMED_EVENT, event.sequence)

        known = self._by_sequence.get(event.sequence)
        if known is not None:
            if known == (event.event_id, fingerprint):
                return EventApplyDisposition.DUPLICATE_IGNORED
            raise self._recovery(EventRecoveryReason.CONFLICTING_DUPLICATE, event.sequence)

        known_sequence = self._sequence_by_event_id.get(event.event_id)
        if known_sequence is not None:
            raise self._recovery(EventRecoveryReason.DUPLICATE_EVENT_ID, event.sequence)

        if self.terminal_sequence is not None:
            raise self._recovery(EventRecoveryReason.POST_TERMINAL_EVENT, event.sequence)

        expected = self.committed_sequence + 1
        if event.sequence < expected:
            raise self._recovery(EventRecoveryReason.STALE_EVENT, event.sequence)
        if event.sequence > expected:
            raise self._recovery(EventRecoveryReason.SEQUENCE_GAP, event.sequence)

        self._by_sequence[event.sequence] = (event.event_id, fingerprint)
        self._sequence_by_event_id[event.event_id] = event.sequence
        self.committed_sequence = event.sequence
        if event.type in _TERMINAL_EVENT_TYPES:
            self.terminal_sequence = event.sequence
        return EventApplyDisposition.APPLIED

    def _recovery(
        self, reason: EventRecoveryReason, received_sequence: int | None
    ) -> EventReconciliationRequired:
        return EventReconciliationRequired(
            reason,
            run_id=self.run_id,
            committed_sequence=self.committed_sequence,
            received_sequence=received_sequence,
        )


def parse_resume_cursor(cursor: str | None) -> tuple[Literal["numeric", "opaque"], int | str]:
    """Parse the two frozen cursor families without coercion or clamping."""

    if cursor is None:
        return "numeric", 0
    if _CANONICAL_NUMERIC_CURSOR.fullmatch(cursor):
        # Reject before ``int`` so an attacker-controlled, arbitrarily long
        # Last-Event-ID cannot escape the typed preflight error boundary (or
        # consume unbounded integer parsing work on runtimes without a digit
        # limit). ``MAX_RESUME_SEQUENCE`` has exactly 19 decimal digits.
        if len(cursor) > 19:
            raise CursorPreflightError(CursorErrorCode.INVALID_CURSOR)
        sequence = int(cursor)
        if sequence <= MAX_RESUME_SEQUENCE:
            return "numeric", sequence
        raise CursorPreflightError(CursorErrorCode.INVALID_CURSOR)
    if _SIGNED_OR_NONCANONICAL_NUMERIC_CURSOR.fullmatch(cursor):
        # Numeric-looking values never fall through to the opaque family.
        raise CursorPreflightError(CursorErrorCode.INVALID_CURSOR)
    if _OPAQUE_EVENT_CURSOR.fullmatch(cursor):
        return "opaque", cursor
    raise CursorPreflightError(CursorErrorCode.INVALID_CURSOR)


def _event_fingerprint(event: RuntimeEvent) -> str:
    canonical = json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(canonical).hexdigest()


def _terminal_outcome(event: RuntimeEvent) -> TerminalOutcome:
    if event.type is RuntimeEventType.RUN_COMPLETED:
        return "SUCCESS"
    if event.payload.get("status") == "CANCELLED":
        return "CANCELLED"
    return "FAILURE"


def validate_event_log(run_id: str, events: Sequence[RuntimeEvent]) -> RuntimeEvent | None:
    """Validate exact identity, contiguity, uniqueness, and terminal position."""

    cursor = RuntimeEventCursor(run_id=run_id)
    terminal: RuntimeEvent | None = None
    for event in events:
        disposition = cursor.accept(event)
        if disposition is EventApplyDisposition.DUPLICATE_IGNORED:
            raise EventReconciliationRequired(
                EventRecoveryReason.DUPLICATE_SEQUENCE,
                run_id=run_id,
                committed_sequence=cursor.committed_sequence,
                received_sequence=event.sequence,
            )
        if event.type in _TERMINAL_EVENT_TYPES:
            terminal = event
    return terminal


def build_cursor_preflight(
    *, run_id: str, last_event_id: str | None, events: Sequence[RuntimeEvent]
) -> CursorPreflight:
    """Resolve a cursor against one already-consistent exact-Run event-log view."""

    terminal = validate_event_log(run_id, events)
    family, value = parse_resume_cursor(last_event_id)
    tail_sequence = events[-1].sequence if events else 0
    if family == "numeric":
        sequence = int(value)
        if sequence > tail_sequence:
            raise CursorPreflightError(CursorErrorCode.CURSOR_AHEAD)
    else:
        sequence = next(
            (event.sequence for event in events if event.event_id == value),
            -1,
        )
        if sequence < 0:
            # Exact lookup is scoped to this Run. Unknown and foreign IDs are
            # intentionally indistinguishable at the public boundary.
            raise CursorPreflightError(CursorErrorCode.INVALID_CURSOR)
    return CursorPreflight(
        run_id=run_id,
        sequence=sequence,
        tail_sequence=tail_sequence,
        terminal_sequence=terminal.sequence if terminal is not None else None,
        terminal_event_id=terminal.event_id if terminal is not None else None,
        terminal_outcome=_terminal_outcome(terminal) if terminal is not None else None,
        terminal_event=terminal.model_copy(deep=True) if terminal is not None else None,
    )


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

    async def preflight_cursor(self, run_id: str, last_event_id: str | None) -> CursorPreflight: ...


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
            if current and current[-1].type in _TERMINAL_EVENT_TYPES:
                raise EventSequenceError(f"run {event.run_id} is already terminal")
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
            if current and current[-1].type in _TERMINAL_EVENT_TYPES:
                raise EventSequenceError(f"run {run_id} is already terminal")
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
        _validate_after_sequence(after_sequence)
        async with self._locks[run_id]:
            validate_event_log(run_id, self._events[run_id])
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
        return (await self.preflight_cursor(run_id, last_event_id)).sequence

    async def preflight_cursor(self, run_id: str, last_event_id: str | None) -> CursorPreflight:
        async with self._locks[run_id]:
            return build_cursor_preflight(
                run_id=run_id,
                last_event_id=last_event_id,
                events=self._events[run_id],
            )

    async def _notify(self, run_id: str) -> None:
        async with self._conditions[run_id]:
            self._conditions[run_id].notify_all()


def _validate_after_sequence(after_sequence: int) -> None:
    if isinstance(after_sequence, bool) or not isinstance(after_sequence, int):
        raise TypeError("after_sequence must be an integer")
    if after_sequence < 0:
        raise ValueError("after_sequence cannot be negative")
    if after_sequence > MAX_RESUME_SEQUENCE:
        raise ValueError("after_sequence exceeds the signed 64-bit cursor range")
