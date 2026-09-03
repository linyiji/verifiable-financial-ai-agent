from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from src.domain.base import TimestampedModel


class TraceReference(TimestampedModel):
    reference_id: str
    run_id: str
    stage: str
    trace_id: str
    span_id: str | None = None
    task_id: str | None = None
    tags: list[str] = Field(default_factory=list)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        stage: str,
        trace_id: str,
        span_id: str | None = None,
        task_id: str | None = None,
    ) -> TraceReference:
        key = f"{run_id}:{stage}:{trace_id}:{span_id or ''}:{task_id or ''}"
        return cls(
            reference_id=f"TRACE-REF-{uuid5(NAMESPACE_URL, key)}",
            run_id=run_id,
            stage=stage,
            trace_id=trace_id,
            span_id=span_id,
            task_id=task_id,
        )


@runtime_checkable
class TraceReferenceRepository(Protocol):
    async def add(self, reference: TraceReference) -> None: ...

    async def list_by_run(self, run_id: str) -> list[TraceReference]: ...


class InMemoryTraceReferenceRepository:
    """Business DB bridge stores identifiers only, never Langfuse trace content."""

    def __init__(self) -> None:
        self._references: dict[str, TraceReference] = {}

    async def add(self, reference: TraceReference) -> None:
        self._references.setdefault(reference.reference_id, reference.model_copy(deep=True))

    async def list_by_run(self, run_id: str) -> list[TraceReference]:
        return [
            reference.model_copy(deep=True)
            for reference in self._references.values()
            if reference.run_id == run_id
        ]
