from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, runtime_checkable

from src.domain.base import JsonObject


@runtime_checkable
class TraceAdapter(Protocol):
    def span(
        self, name: str, *, attributes: JsonObject | None = None
    ) -> AbstractAsyncContextManager[Any]: ...

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None: ...

    def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> AbstractAsyncContextManager[Any]: ...

    async def complete_generation(
        self,
        generation: Any,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> None: ...
