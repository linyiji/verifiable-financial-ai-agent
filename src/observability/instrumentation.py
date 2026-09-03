from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from typing import Any

from src.domain.base import JsonObject
from src.observability.references import TraceReference, TraceReferenceRepository
from src.observability.safety import sanitize_trace_attributes
from src.observability.tracing import TraceAdapter


class ObservationStage(StrEnum):
    RUN = "run"
    PLANNING = "planning"
    SCHEME = "scheme"
    TASK = "task"
    AGENT = "agent"
    SKILL = "skill"
    TOOL = "tool"
    CALCULATION = "calculation"
    SELF_CORRECTION = "self_correction"
    REPLAN = "replan"
    REVIEW = "review"


class RuntimeInstrumentation:
    """Reusable hooks; Coordinator chooses where to compose them."""

    def __init__(
        self,
        adapter: TraceAdapter,
        *,
        reference_repository: TraceReferenceRepository | None = None,
    ) -> None:
        self._adapter = adapter
        self._reference_repository = reference_repository

    @asynccontextmanager
    async def observe(
        self,
        stage: ObservationStage,
        *,
        run_id: str,
        task_id: str | None = None,
        attributes: JsonObject | None = None,
    ) -> AsyncIterator[Any]:
        metadata = sanitize_trace_attributes(
            {
                "run_id": run_id,
                "task_id": task_id,
                "stage": stage.value,
                **(attributes or {}),
            }
        )
        async with self._adapter.span(f"vfas.{stage.value}", attributes=metadata) as span:
            yield span
        await self._persist_reference_fail_open(
            span=span,
            stage=stage,
            run_id=run_id,
            task_id=task_id,
        )

    async def emit(
        self,
        stage: ObservationStage,
        event: str,
        *,
        run_id: str,
        task_id: str | None = None,
        attributes: JsonObject | None = None,
    ) -> None:
        await self._adapter.event(
            f"vfas.{stage.value}.{event}",
            attributes=sanitize_trace_attributes(
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "stage": stage.value,
                    **(attributes or {}),
                }
            ),
        )

    def run(self, *, run_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.RUN, run_id=run_id, attributes=attributes)

    def planning(self, *, run_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.PLANNING, run_id=run_id, attributes=attributes)

    def scheme(self, *, run_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.SCHEME, run_id=run_id, attributes=attributes)

    def task(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.TASK,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def agent(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.AGENT,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def skill(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.SKILL,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def tool(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.TOOL,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def calculation(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.CALCULATION,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def self_correction(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.SELF_CORRECTION,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def replan(self, *, run_id: str, task_id: str, attributes: JsonObject | None = None):
        return self.observe(
            ObservationStage.REPLAN,
            run_id=run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def review(self, *, run_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.REVIEW, run_id=run_id, attributes=attributes)

    async def _persist_reference_fail_open(
        self,
        *,
        span: Any,
        stage: ObservationStage,
        run_id: str,
        task_id: str | None,
    ) -> None:
        if self._reference_repository is None or span is None:
            return
        trace_id = getattr(span, "trace_id", None)
        span_id = getattr(span, "span_id", None)
        if not isinstance(trace_id, str) or not trace_id:
            return
        try:
            await self._reference_repository.add(
                TraceReference.create(
                    run_id=run_id,
                    stage=stage.value,
                    trace_id=trace_id,
                    span_id=span_id if isinstance(span_id, str) else None,
                    task_id=task_id,
                )
            )
        except Exception:
            return
