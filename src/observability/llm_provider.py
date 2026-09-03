"""Content-free LLM provider instrumentation for native Langfuse generations."""

from __future__ import annotations

from time import perf_counter
from typing import TypeVar

from pydantic import BaseModel

from src.adapters.llm.provider import (
    LLMMessage,
    LLMProvider,
    LLMStructuredResponse,
)
from src.observability.instrumentation import ObservationStage, ResearchRunTrace

StructuredModel = TypeVar("StructuredModel", bound=BaseModel)


class InstrumentedLLMProvider:
    """Wrap an LLM provider without uploading prompts, responses, or request bodies."""

    def __init__(
        self,
        delegate: LLMProvider,
        *,
        trace: ResearchRunTrace,
        stage: ObservationStage,
    ) -> None:
        if stage not in {
            ObservationStage.SCHEME_GENERATION,
            ObservationStage.PLANNER_GENERATION,
        }:
            raise ValueError("LLM provider instrumentation requires a generation stage")
        self._delegate = delegate
        self._trace = trace
        self._stage = stage

    async def complete_structured(
        self,
        *,
        messages: list[LLMMessage],
        response_model: type[StructuredModel],
        schema_name: str,
        force_fallback: bool = False,
    ) -> LLMStructuredResponse[StructuredModel]:
        manager = (
            self._trace.scheme_generation
            if self._stage is ObservationStage.SCHEME_GENERATION
            else self._trace.planner_generation
        )
        started = perf_counter()
        async with manager(attributes={"schema_name": schema_name}) as generation:
            try:
                response = await self._delegate.complete_structured(
                    messages=messages,
                    response_model=response_model,
                    schema_name=schema_name,
                    force_fallback=force_fallback,
                )
            except Exception as exc:
                await self._trace.complete_generation(
                    generation,
                    requested_model=_optional_text(getattr(exc, "requested_model", None)),
                    actual_model=None,
                    provider=_optional_text(getattr(self._delegate, "provider_name", None)),
                    latency_ms=(perf_counter() - started) * 1000,
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    attributes={"result_status": "error", "error_type": type(exc).__name__},
                )
                raise
            total_tokens = (
                response.input_tokens + response.output_tokens
                if response.input_tokens is not None and response.output_tokens is not None
                else None
            )
            await self._trace.complete_generation(
                generation,
                requested_model=response.requested_model,
                actual_model=response.actual_model,
                provider=response.provider,
                latency_ms=(perf_counter() - started) * 1000,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                total_tokens=total_tokens,
                attributes={"result_status": "success"},
            )
            return response


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
