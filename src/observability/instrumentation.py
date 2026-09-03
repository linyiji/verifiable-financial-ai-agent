from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from src.domain.base import JsonObject
from src.observability.noop import TraceRuntimeStatus
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
    SCHEME_GENERATION = "scheme_generation"
    PLANNER_GENERATION = "planner_generation"
    EVIDENCE = "evidence"
    CORRECTION = "correction"
    RELEASE = "release"


@dataclass(slots=True)
class ResearchRunTrace:
    """Coordinator-facing handle whose observations stay below one active run root."""

    _instrumentation: RuntimeInstrumentation
    run_id: str
    trace_id: str | None
    root_observation_id: str | None

    def observe(
        self,
        stage: ObservationStage,
        *,
        task_id: str | None = None,
        attributes: JsonObject | None = None,
    ):
        if stage is ObservationStage.RUN:
            raise ValueError("a research run trace already owns the root observation")
        return self._instrumentation.observe(
            stage,
            run_id=self.run_id,
            task_id=task_id,
            attributes=attributes,
        )

    def scheme_generation(
        self,
        *,
        requested_model: str | None = None,
        actual_model: str | None = None,
        provider: str | None = None,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        attributes: JsonObject | None = None,
    ):
        return self._instrumentation.generation(
            ObservationStage.SCHEME_GENERATION,
            run_id=self.run_id,
            requested_model=requested_model,
            actual_model=actual_model,
            provider=provider,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            attributes=attributes,
        )

    def planner_generation(
        self,
        *,
        requested_model: str | None = None,
        actual_model: str | None = None,
        provider: str | None = None,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        attributes: JsonObject | None = None,
    ):
        return self._instrumentation.generation(
            ObservationStage.PLANNER_GENERATION,
            run_id=self.run_id,
            requested_model=requested_model,
            actual_model=actual_model,
            provider=provider,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            attributes=attributes,
        )

    def task(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.TASK, task_id=task_id, attributes=attributes)

    def evidence_batch(
        self,
        *,
        task_id: str,
        evidence_count: int,
        providers: list[str],
        periods: list[str],
        normalized_fields: list[str],
        status_counts: dict[str, int],
    ):
        """Emit one metadata-only summary per task/batch, never one span per fact."""

        return self.observe(
            ObservationStage.EVIDENCE,
            task_id=task_id,
            attributes={
                "evidence_count": evidence_count,
                "providers": providers,
                "periods": periods,
                "normalized_fields": normalized_fields,
                "status_counts": status_counts,
            },
        )

    def agent(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.AGENT, task_id=task_id, attributes=attributes)

    def skill(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.SKILL, task_id=task_id, attributes=attributes)

    def tool(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.TOOL, task_id=task_id, attributes=attributes)

    def calculation(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.CALCULATION, task_id=task_id, attributes=attributes)

    def correction(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.CORRECTION, task_id=task_id, attributes=attributes)

    def replan(self, *, task_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.REPLAN, task_id=task_id, attributes=attributes)

    def review(self, *, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.REVIEW, attributes=attributes)

    def release(self, *, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.RELEASE, attributes=attributes)

    async def complete_generation(
        self,
        generation: Any,
        *,
        requested_model: str | None,
        actual_model: str | None,
        provider: str | None,
        latency_ms: float | None,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        cost_usd: float | None = None,
        attributes: JsonObject | None = None,
    ) -> None:
        await self._instrumentation.complete_generation(
            generation,
            requested_model=requested_model,
            actual_model=actual_model,
            provider=provider,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            attributes=attributes,
        )


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
        self._reference_degraded = False

    @property
    def status(self) -> TraceRuntimeStatus:
        adapter_status = getattr(self._adapter, "status", TraceRuntimeStatus.TRACE_HEALTHY)
        if self._reference_degraded or adapter_status == TraceRuntimeStatus.TRACE_DEGRADED:
            return TraceRuntimeStatus.TRACE_DEGRADED
        return TraceRuntimeStatus.TRACE_HEALTHY

    @asynccontextmanager
    async def research_run(
        self,
        *,
        run_id: str,
        attributes: JsonObject | None = None,
    ) -> AsyncIterator[ResearchRunTrace]:
        """Keep every run observation nested beneath one active root trace."""

        async with self.run(run_id=run_id, attributes=attributes) as root:
            yield ResearchRunTrace(
                _instrumentation=self,
                run_id=run_id,
                trace_id=_identifier(root, "trace_id"),
                root_observation_id=_identifier(root, "span_id"),
            )

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

    @asynccontextmanager
    async def generation(
        self,
        stage: ObservationStage,
        *,
        run_id: str,
        task_id: str | None = None,
        requested_model: str | None = None,
        actual_model: str | None = None,
        provider: str | None = None,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        cost_usd: float | None = None,
        attributes: JsonObject | None = None,
    ) -> AsyncIterator[Any]:
        if stage not in {
            ObservationStage.SCHEME_GENERATION,
            ObservationStage.PLANNER_GENERATION,
        }:
            raise ValueError(f"{stage.value} is not an LLM generation stage")
        metadata = sanitize_trace_attributes(
            {
                "run_id": run_id,
                "task_id": task_id,
                "stage": stage.value,
                "requested_model": requested_model,
                "actual_model": actual_model,
                "provider": provider,
                "latency_ms": latency_ms,
                **(attributes or {}),
            }
        )
        usage_details = _without_none(
            {"input": input_tokens, "output": output_tokens, "total": total_tokens}
        )
        cost_details = _without_none({"total": cost_usd})
        async with self._adapter.generation(
            f"vfas.{stage.value}",
            model=actual_model or requested_model,
            attributes=metadata,
            usage_details=usage_details or None,
            cost_details=cost_details or None,
        ) as generation:
            yield generation
        await self._persist_reference_fail_open(
            span=generation,
            stage=stage,
            run_id=run_id,
            task_id=task_id,
        )

    async def complete_generation(
        self,
        generation: Any,
        *,
        requested_model: str | None,
        actual_model: str | None,
        provider: str | None,
        latency_ms: float | None,
        input_tokens: int | None,
        output_tokens: int | None,
        total_tokens: int | None,
        cost_usd: float | None = None,
        attributes: JsonObject | None = None,
    ) -> None:
        metadata = sanitize_trace_attributes(
            {
                "requested_model": requested_model,
                "actual_model": actual_model,
                "provider": provider,
                "latency_ms": latency_ms,
                **(attributes or {}),
            }
        )
        usage_details = _without_none(
            {"input": input_tokens, "output": output_tokens, "total": total_tokens}
        )
        cost_details = _without_none({"total": cost_usd})
        await self._adapter.complete_generation(
            generation,
            model=actual_model or requested_model,
            attributes=metadata,
            usage_details=usage_details or None,
            cost_details=cost_details or None,
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

    def release(self, *, run_id: str, attributes: JsonObject | None = None):
        return self.observe(ObservationStage.RELEASE, run_id=run_id, attributes=attributes)

    async def flush(self) -> None:
        flush = getattr(self._adapter, "flush", None)
        if callable(flush):
            await flush()

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
        except Exception as exc:
            self._reference_degraded = True
            mark_degraded = getattr(self._adapter, "mark_degraded", None)
            if callable(mark_degraded):
                mark_degraded("trace_reference_persistence", exc)


def _identifier(span: Any, name: str) -> str | None:
    if span is None:
        return None
    value = getattr(span, name, None)
    return value if isinstance(value, str) and value else None


def _without_none(values: dict[str, Any]) -> JsonObject:
    return {key: value for key, value in values.items() if value is not None}
