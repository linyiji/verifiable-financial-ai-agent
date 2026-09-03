from collections.abc import AsyncIterator

from src.domain.runtime_event import RuntimeEventType
from src.runtime.events import RuntimeEventStore
from src.runtime.sse import encode_sse_event, encode_sse_heartbeat


async def completed_run_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None,
    heartbeat_seconds: float = 15.0,
) -> AsyncIterator[str]:
    """Replay/live SSE stream that closes after the durable terminal run event."""

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
            if event.type in {RuntimeEventType.RUN_COMPLETED, RuntimeEventType.RUN_FAILED}:
                return
