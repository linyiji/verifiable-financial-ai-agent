from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from src.domain.base import JsonObject


class NoopTraceAdapter:
    @asynccontextmanager
    async def span(
        self, name: str, *, attributes: JsonObject | None = None
    ) -> AsyncIterator[None]:
        del name, attributes
        yield None

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None:
        del name, attributes


class FailOpenTraceAdapter:
    """Decorator guaranteeing that observability failures never fail a Research Run."""

    def __init__(self, delegate: Any):
        self._delegate = delegate

    @asynccontextmanager
    async def span(
        self, name: str, *, attributes: JsonObject | None = None
    ) -> AsyncIterator[Any]:
        manager = None
        try:
            manager = self._delegate.span(name, attributes=attributes)
            value = await manager.__aenter__()
        except Exception:
            yield None
            return
        try:
            yield value
        except Exception as exc:
            try:
                await manager.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception:
                pass
            raise
        else:
            try:
                await manager.__aexit__(None, None, None)
            except Exception:
                pass

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None:
        try:
            await self._delegate.event(name, attributes=attributes)
        except Exception:
            return

