from __future__ import annotations

import json
from collections.abc import AsyncIterator

from src.domain.runtime_event import RuntimeEvent
from src.runtime.events import RuntimeEventStore


def encode_sse_event(event: RuntimeEvent) -> str:
    data = json.dumps(event.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
    return f"id: {event.sequence}\nevent: {event.type.value}\ndata: {data}\n\n"


def encode_sse_heartbeat() -> str:
    return ": heartbeat\n\n"


async def runtime_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None = None,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Replay persisted events, then wait for live events with heartbeat comments."""

    if heartbeat_seconds <= 0:
        raise ValueError("heartbeat_seconds must be positive")
    sequence = await store.resolve_resume_sequence(run_id, last_event_id)
    while True:
        events = await store.wait_for_events(
            run_id,
            after_sequence=sequence,
            timeout_seconds=heartbeat_seconds,
        )
        if not events:
            yield encode_sse_heartbeat()
            continue
        for event in events:
            sequence = event.sequence
            yield encode_sse_event(event)
