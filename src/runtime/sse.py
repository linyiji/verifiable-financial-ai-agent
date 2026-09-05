from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.domain.runtime_event import (
    EVENT_CONTRACT_VERSION,
    RuntimeEvent,
    normalize_runtime_event_v1,
)
from src.runtime.events import (
    CursorPreflight,
    EventApplyDisposition,
    EventReconciliationRequired,
    EventRecoveryReason,
    RuntimeEventCursor,
    RuntimeEventStore,
)

CORE_CONTRACT_VERSION = "phase4-core/v1"


class UnsupportedRuntimeEventError(ValueError):
    """Safe failure raised when a stored event cannot enter the frozen public stream."""

    code = "UNSUPPORTED_EVENT"
    recovery = "SNAPSHOT_RELOAD"
    retryable = False
    status_code = 409

    def __init__(self, event: RuntimeEvent) -> None:
        self.run_id = event.run_id
        self.sequence = event.sequence
        super().__init__("runtime event is incompatible with the Phase 4 event contract")


@dataclass(frozen=True, slots=True)
class RuntimeEventStreamPreflight:
    """Validated stream admission data safe to use when constructing a response."""

    cursor: CursorPreflight
    response_headers: Mapping[str, str]

    @property
    def terminal_at_cursor(self) -> bool:
        return self.cursor.terminal_at_cursor


def encode_sse_event(event: RuntimeEvent) -> str:
    try:
        normalized = normalize_runtime_event_v1(event)
    except (KeyError, TypeError, ValueError) as exc:
        raise UnsupportedRuntimeEventError(event) from exc
    data = json.dumps(normalized.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return f"id: {event.sequence}\nevent: {event.type.value}\ndata: {data}\n\n"


def encode_sse_heartbeat() -> str:
    return ": heartbeat\n\n"


async def preflight_runtime_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None = None,
) -> RuntimeEventStreamPreflight:
    """Validate the exact-Run cursor before a caller commits SSE headers."""

    cursor = await store.preflight_cursor(run_id, last_event_id)
    if cursor.terminal_at_cursor:
        if cursor.terminal_event is None:
            raise EventReconciliationRequired(
                EventRecoveryReason.PERSISTED_EVENT_MISMATCH,
                run_id=run_id,
                committed_sequence=cursor.sequence,
            )
        # Terminal-at-cursor emits no business frame, so validate the terminal
        # envelope explicitly before its success headers can be committed.
        encode_sse_event(cursor.terminal_event)
    headers = {
        "Cache-Control": "no-cache",
        "X-Phase4-Contract-Version": CORE_CONTRACT_VERSION,
        "X-Phase4-Event-Contract-Version": EVENT_CONTRACT_VERSION,
    }
    if cursor.terminal_at_cursor:
        headers["X-Run-Terminal"] = "true"
        headers["X-Terminal-Sequence"] = str(cursor.terminal_sequence)
    return RuntimeEventStreamPreflight(
        cursor=cursor,
        response_headers=MappingProxyType(headers),
    )


async def runtime_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None = None,
    heartbeat_seconds: float = 15.0,
    preflight: RuntimeEventStreamPreflight | None = None,
    close_on_terminal: bool = True,
) -> AsyncIterator[str]:
    """Replay persisted events, then wait for live events with heartbeat comments."""

    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")
    admitted = preflight or await preflight_runtime_event_stream(
        store=store,
        run_id=run_id,
        last_event_id=last_event_id,
    )
    if admitted.cursor.run_id != run_id:
        raise EventReconciliationRequired(
            EventRecoveryReason.WRONG_RUN,
            run_id=run_id,
            committed_sequence=admitted.cursor.sequence,
        )
    if admitted.terminal_at_cursor:
        return

    cursor = RuntimeEventCursor(
        run_id=run_id,
        committed_sequence=admitted.cursor.sequence,
    )
    while True:
        events = await store.wait_for_events(
            run_id,
            after_sequence=cursor.committed_sequence,
            timeout_seconds=heartbeat_seconds,
        )
        if not events:
            yield encode_sse_heartbeat()
            continue
        accepted: list[tuple[RuntimeEvent, str]] = []
        for index, event in enumerate(events):
            disposition = cursor.accept(event)
            if disposition is EventApplyDisposition.DUPLICATE_IGNORED:
                continue
            if cursor.terminal_sequence is not None and index != len(events) - 1:
                raise EventReconciliationRequired(
                    EventRecoveryReason.POST_TERMINAL_EVENT,
                    run_id=run_id,
                    committed_sequence=cursor.committed_sequence,
                    received_sequence=events[index + 1].sequence,
                )
            accepted.append((event, encode_sse_event(event)))
        for event, frame in accepted:
            yield frame
            if close_on_terminal and cursor.terminal_sequence == event.sequence:
                return
