from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

from src.domain.base import JsonObject
from src.observability.noop import FailOpenTraceAdapter, NoopTraceAdapter


class LangfuseClientBoundary(Protocol):
    def start_span(self, *, name: str, attributes: JsonObject) -> Any: ...

    def create_event(self, *, name: str, attributes: JsonObject) -> Any: ...


class LangfuseTraceAdapter:
    """Small SDK boundary; wrapped fail-open by `build_trace_adapter`."""

    def __init__(self, client: LangfuseClientBoundary):
        self._client = client

    @asynccontextmanager
    async def span(
        self, name: str, *, attributes: JsonObject | None = None
    ) -> AsyncIterator[Any]:
        span = self._client.start_span(name=name, attributes=attributes or {})
        try:
            yield span
        finally:
            end = getattr(span, "end", None)
            if callable(end):
                end()

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None:
        self._client.create_event(name=name, attributes=attributes or {})


def build_trace_adapter(client: LangfuseClientBoundary | None = None) -> Any:
    if client is None:
        return NoopTraceAdapter()
    return FailOpenTraceAdapter(LangfuseTraceAdapter(client))

