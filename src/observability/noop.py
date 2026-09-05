from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.domain.base import JsonObject


class NoopTraceAdapter:
    @asynccontextmanager
    async def span(self, name: str, *, attributes: JsonObject | None = None) -> AsyncIterator[None]:
        del name, attributes
        yield None

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> None:
        del name, attributes

    @asynccontextmanager
    async def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> AsyncIterator[None]:
        del name, model, attributes, usage_details, cost_details
        yield None

    async def complete_generation(
        self,
        generation: Any,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> None:
        del generation, model, attributes, usage_details, cost_details


class TraceRuntimeStatus(StrEnum):
    TRACE_HEALTHY = "TRACE_HEALTHY"
    TRACE_DEGRADED = "TRACE_DEGRADED"


@dataclass(frozen=True, slots=True)
class TraceDegradation:
    operation: str
    error_type: str


class FailOpenTraceAdapter:
    """Decorator guaranteeing that observability failures never fail a Research Run."""

    def __init__(self, delegate: Any):
        self._delegate = delegate
        self._degradations: list[TraceDegradation] = []

    @property
    def status(self) -> TraceRuntimeStatus:
        return (
            TraceRuntimeStatus.TRACE_DEGRADED
            if self._degradations
            else TraceRuntimeStatus.TRACE_HEALTHY
        )

    @property
    def degradations(self) -> tuple[TraceDegradation, ...]:
        return tuple(self._degradations)

    @asynccontextmanager
    async def span(self, name: str, *, attributes: JsonObject | None = None) -> AsyncIterator[Any]:
        manager = None
        try:
            manager = self._delegate.span(name, attributes=attributes)
            value = await manager.__aenter__()
        except Exception as exc:
            self._mark_degraded("span_start", exc)
            yield None
            return
        try:
            yield value
        except Exception as exc:
            try:
                await manager.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception as exit_exc:
                self._mark_degraded("span_end", exit_exc)
            raise
        else:
            try:
                await manager.__aexit__(None, None, None)
            except Exception as exc:
                self._mark_degraded("span_end", exc)

    async def event(self, name: str, *, attributes: JsonObject | None = None) -> Any:
        try:
            return await self._delegate.event(name, attributes=attributes)
        except Exception as exc:
            self._mark_degraded("event", exc)
            return None

    @asynccontextmanager
    async def generation(
        self,
        name: str,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> AsyncIterator[Any]:
        manager = None
        try:
            manager = self._delegate.generation(
                name,
                model=model,
                attributes=attributes,
                usage_details=usage_details,
                cost_details=cost_details,
            )
            value = await manager.__aenter__()
        except Exception as exc:
            self._mark_degraded("generation_start", exc)
            yield None
            return
        try:
            yield value
        except Exception as exc:
            try:
                await manager.__aexit__(type(exc), exc, exc.__traceback__)
            except Exception as exit_exc:
                self._mark_degraded("generation_end", exit_exc)
            raise
        else:
            try:
                await manager.__aexit__(None, None, None)
            except Exception as exc:
                self._mark_degraded("generation_end", exc)

    async def complete_generation(
        self,
        generation: Any,
        *,
        model: str | None = None,
        attributes: JsonObject | None = None,
        usage_details: JsonObject | None = None,
        cost_details: JsonObject | None = None,
    ) -> None:
        if generation is None:
            return
        try:
            await self._delegate.complete_generation(
                generation,
                model=model,
                attributes=attributes,
                usage_details=usage_details,
                cost_details=cost_details,
            )
        except Exception as exc:
            self._mark_degraded("generation_update", exc)

    async def flush(self) -> None:
        flush = getattr(self._delegate, "flush", None)
        if not callable(flush):
            return
        try:
            await flush()
        except Exception as exc:
            self._mark_degraded("flush", exc)

    def mark_degraded(self, operation: str, error: Exception) -> None:
        self._mark_degraded(operation, error)

    def _mark_degraded(self, operation: str, error: Exception) -> None:
        self._degradations.append(
            TraceDegradation(operation=operation, error_type=type(error).__name__)
        )
