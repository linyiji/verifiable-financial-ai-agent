from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass

from src.runtime.events import RuntimeEventStore
from src.runtime.sse import (
    RuntimeEventStreamPreflight,
    preflight_runtime_event_stream,
    runtime_event_stream,
)


@dataclass(frozen=True, slots=True)
class PreparedCompletedRunEventStream:
    """A preflighted stream whose cursor errors occurred before response creation."""

    body: AsyncIterator[str]
    response_headers: Mapping[str, str]
    preflight: RuntimeEventStreamPreflight


async def prepare_completed_run_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None,
    heartbeat_seconds: float = 15.0,
) -> PreparedCompletedRunEventStream:
    """Prepare an exact-Run SSE response, including terminal-at-cursor closure."""

    preflight = await preflight_runtime_event_stream(
        store=store,
        run_id=run_id,
        last_event_id=last_event_id,
    )
    body = completed_run_event_stream(
        store=store,
        run_id=run_id,
        last_event_id=last_event_id,
        heartbeat_seconds=heartbeat_seconds,
        preflight=preflight,
    )
    return PreparedCompletedRunEventStream(
        body=body,
        response_headers=preflight.response_headers,
        preflight=preflight,
    )


async def completed_run_event_stream(
    *,
    store: RuntimeEventStore,
    run_id: str,
    last_event_id: str | None,
    heartbeat_seconds: float = 15.0,
    preflight: RuntimeEventStreamPreflight | None = None,
) -> AsyncIterator[str]:
    """Replay/live SSE stream that closes after the durable terminal run event."""

    async for frame in runtime_event_stream(
        store=store,
        run_id=run_id,
        last_event_id=last_event_id,
        heartbeat_seconds=heartbeat_seconds,
        preflight=preflight,
        close_on_terminal=True,
    ):
        yield frame
