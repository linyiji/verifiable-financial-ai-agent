from __future__ import annotations

from typing import Any

from src.domain.base import JsonObject
from src.observability.noop import FailOpenTraceAdapter, NoopTraceAdapter
from src.observability.safety import sanitize_trace_attributes
from src.observability.tracing import TraceAdapter


class GeneratedCapabilityTrace:
    """Metadata-only tracing below the existing active Research Run root.

    Callers should pass the same owned ``TraceAdapter`` used by
    ``RuntimeInstrumentation`` while its Research Run context is active.  Source,
    tests, prompts, provider bodies, environment values, and secrets are never
    accepted by this API.
    """

    def __init__(self, adapter: TraceAdapter | None = None) -> None:
        self._adapter = FailOpenTraceAdapter(adapter or NoopTraceAdapter())

    async def event(
        self,
        name: str,
        *,
        run_id: str,
        task_id: str,
        attributes: JsonObject | None = None,
    ) -> None:
        await self._adapter.event(
            f"vfas.{name}",
            attributes=sanitize_trace_attributes(
                {"run_id": run_id, "task_id": task_id, **(attributes or {})}
            ),
        )

    def generation(
        self,
        *,
        run_id: str,
        task_id: str,
        build_id: str,
        capability_id: str,
        attempt: int,
        provider: str | None = None,
        model: str | None = None,
        workload_type: str = "GENERATED_CAPABILITY",
    ):
        return self._adapter.generation(
            "vfas.capability_generation",
            attributes=sanitize_trace_attributes(
                {
                    "run_id": run_id,
                    "task_id": task_id,
                    "build_id": build_id,
                    "capability_id": capability_id,
                    "validation_attempt": attempt,
                    "attempt_id": attempt,
                    "provider": provider,
                    "model": model,
                    "workload_type": workload_type,
                }
            ),
        )

    async def complete_generation(
        self,
        generation: Any,
        *,
        requested_model: str | None,
        actual_model: str | None,
        provider: str,
        latency_ms: float,
        input_tokens: int | None,
        output_tokens: int | None,
        implementation_hash: str | None,
        result_status: str,
        error_type: str | None = None,
        workload_type: str = "GENERATED_CAPABILITY",
        attempt_number: int | None = None,
        failure_class: str | None = None,
    ) -> None:
        total_tokens = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        )
        usage: JsonObject | None = None
        if input_tokens is not None or output_tokens is not None or total_tokens is not None:
            usage = {
                key: value
                for key, value in {
                    "input": input_tokens,
                    "output": output_tokens,
                    "total": total_tokens,
                }.items()
                if value is not None
            }
        await self._adapter.complete_generation(
            generation,
            model=actual_model or requested_model,
            attributes=sanitize_trace_attributes(
                {
                    "requested_model": requested_model,
                    "actual_model": actual_model,
                    "provider": provider,
                    "latency_ms": latency_ms,
                    "implementation_hash": implementation_hash,
                    "result_status": result_status,
                    "error_type": error_type,
                    "workload_type": workload_type,
                    "attempt_number": attempt_number,
                    "attempt_id": attempt_number,
                    "failure_class": failure_class,
                }
            ),
            usage_details=usage,
        )
