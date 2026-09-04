from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from time import perf_counter
from typing import Any

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMMessage, LLMProvider
from src.adapters.llm.router import SUPPORTED_PLANNER_PROVIDERS
from src.capabilities.generated.artifacts import generated_text_sha256
from src.capabilities.generated.contract import (
    GCValidationFinding,
    GeneratedCapabilityBundleV1,
    GeneratedCapabilityBundleValidationError,
    GeneratedCapabilityBundleValidator,
    GeneratedCapabilityRequestV1,
)
from src.capabilities.generated.models import CapabilityBuildRequest, GeneratedCapabilityCandidate
from src.capabilities.generated.telemetry import GeneratedCapabilityTrace


class CodeBuilderOutputMismatch(GeneratedCapabilityBundleValidationError):
    """Backward-compatible name for a deterministic bundle mismatch."""


class GeneratedCapabilityDeadlineExceededError(TimeoutError):
    """The one absolute generation/validation/repair deadline was exhausted."""


class PlannerProviderCodeBuilder:
    """Generate, validate, and if needed repair one provider-neutral bundle.

    Rejected drafts remain local and transient. Only a bundle that passes the
    complete deterministic contract can become a ``GeneratedCapabilityCandidate``.
    """

    schema_name = "generated_capability_bundle_v1"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        trace: GeneratedCapabilityTrace | None = None,
        validator: GeneratedCapabilityBundleValidator | None = None,
    ) -> None:
        provider_name = getattr(provider, "provider_name", None)
        if provider_name not in SUPPORTED_PLANNER_PROVIDERS:
            raise ValueError("Code Builder requires a registered planner provider")
        self._provider = provider
        self._provider_name = provider_name
        self.builder_id = f"{provider_name}-code-builder-v2"
        self._trace = trace or GeneratedCapabilityTrace()
        self._validator = validator or GeneratedCapabilityBundleValidator()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return str(getattr(self._provider, "model_name", ""))

    @property
    def execution_policy(self) -> ProviderExecutionPolicyV1 | None:
        policy = getattr(self._provider, "execution_policy", None)
        return policy if isinstance(policy, ProviderExecutionPolicyV1) else None

    async def generate(self, request: CapabilityBuildRequest) -> GeneratedCapabilityCandidate:
        owned_request = GeneratedCapabilityRequestV1.from_build_request(request)
        policy = self.execution_policy or ProviderExecutionPolicyV1()
        started = perf_counter()
        loop = asyncio.get_running_loop()
        absolute_deadline = loop.time() + policy.overall_workload_deadline_seconds
        previous_bundle: GeneratedCapabilityBundleV1 | None = None
        previous_findings: tuple[GCValidationFinding, ...] = ()
        locked_provider: LLMProvider = self._provider
        locked_model: str | None = None
        responses: list[Any] = []

        async with self._trace.generation(
            run_id=request.gap.run_id,
            task_id=request.gap.task_id,
            build_id=request.build_id,
            capability_id=owned_request.capability_id,
            attempt=request.attempt,
            provider=self.provider_name,
            model=self.model_name,
            workload_type="GENERATED_CAPABILITY",
        ) as generation:
            try:
                for generation_attempt in range(1, policy.max_attempts + 1):
                    attempt_started = perf_counter()
                    remaining = absolute_deadline - loop.time()
                    if remaining <= 0:
                        raise GeneratedCapabilityDeadlineExceededError(
                            "generated-capability absolute deadline exceeded"
                        )
                    messages = (
                        _initial_messages(owned_request)
                        if previous_bundle is None
                        else _repair_messages(owned_request, previous_bundle, previous_findings)
                    )
                    bundle: GeneratedCapabilityBundleV1 | None = None
                    try:
                        async with asyncio.timeout(remaining):
                            response = await locked_provider.complete_structured(
                                messages=messages,
                                response_model=GeneratedCapabilityBundleV1,
                                schema_name=self.schema_name,
                                workload_type="GENERATED_CAPABILITY",
                            )
                        responses.append(response)
                        if response.provider != self.provider_name:
                            raise GeneratedCapabilityBundleValidationError(
                                [
                                    GCValidationFinding(
                                        "GC_SECURITY_PROVIDER_DRIFT",
                                        "provider",
                                        "same selected provider",
                                    )
                                ]
                            )
                        if locked_model is None:
                            locked_model = response.actual_model
                            locked_provider = _lock_to_actual_model(self._provider, locked_model)
                        elif response.actual_model != locked_model:
                            raise GeneratedCapabilityBundleValidationError(
                                [
                                    GCValidationFinding(
                                        "GC_SECURITY_PROVIDER_MODEL_DRIFT",
                                        "model",
                                        "same selected model",
                                    )
                                ]
                            )
                        if not isinstance(response.output, GeneratedCapabilityBundleV1):
                            raise GeneratedCapabilityBundleValidationError(
                                [
                                    GCValidationFinding(
                                        "GC_SCHEMA_INVALID",
                                        "bundle",
                                        "GeneratedCapabilityBundleV1",
                                    )
                                ]
                            )
                        bundle = response.output
                        output = self._validator.validate(owned_request, bundle)
                    except TimeoutError as exc:
                        raise GeneratedCapabilityDeadlineExceededError(
                            "generated-capability absolute deadline exceeded"
                        ) from exc
                    except GeneratedCapabilityBundleValidationError as exc:
                        await self._attempt_event(
                            request,
                            generation_attempt,
                            locked_model or self.model_name,
                            "validation_failed",
                            exc.codes,
                            attempt_started,
                        )
                        if generation_attempt >= policy.max_attempts or bundle is None:
                            raise
                        previous_bundle = bundle
                        previous_findings = exc.findings
                        backoff = min(
                            policy.backoff_seconds(generation_attempt),
                            max(0.0, absolute_deadline - loop.time()),
                        )
                        if backoff:
                            await asyncio.sleep(backoff)
                        continue
                    except Exception as exc:
                        await self._attempt_event(
                            request,
                            generation_attempt,
                            _optional_text(getattr(exc, "model", None)) or self.model_name,
                            "provider_error",
                            (),
                            attempt_started,
                            failure_class=_optional_text(
                                getattr(
                                    getattr(exc, "failure_classification", None),
                                    "value",
                                    None,
                                )
                            ),
                        )
                        raise

                    await self._attempt_event(
                        request,
                        generation_attempt,
                        response.actual_model,
                        "accepted",
                        (),
                        attempt_started,
                    )
                    implementation_hash = _source_hash(output.source_code)
                    latency_ms = (perf_counter() - started) * 1000
                    input_tokens = _sum_optional(response.input_tokens for response in responses)
                    output_tokens = _sum_optional(response.output_tokens for response in responses)
                    attempted_models = _ordered_unique(
                        model for item in responses for model in item.attempted_models
                    )
                    await self._trace.complete_generation(
                        generation,
                        requested_model=responses[0].requested_model,
                        actual_model=response.actual_model,
                        provider=response.provider,
                        latency_ms=latency_ms,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        implementation_hash=implementation_hash,
                        result_status="success",
                        workload_type="GENERATED_CAPABILITY",
                        attempt_number=generation_attempt,
                    )
                    return GeneratedCapabilityCandidate(
                        build_id=request.build_id,
                        output=output,
                        implementation_hash=implementation_hash,
                        provider=response.provider,
                        requested_model=responses[0].requested_model,
                        actual_model=response.actual_model,
                        attempted_models=attempted_models,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                    )
                raise AssertionError("generated capability attempt loop exited unexpectedly")
            except asyncio.CancelledError:
                await self._complete_error(generation, request, started, "cancelled", None)
                raise
            except Exception as exc:
                classification = (
                    "overall_deadline_exceeded"
                    if isinstance(exc, GeneratedCapabilityDeadlineExceededError)
                    else _optional_text(
                        getattr(getattr(exc, "failure_classification", None), "value", None)
                    )
                )
                await self._complete_error(
                    generation,
                    request,
                    started,
                    classification,
                    type(exc).__name__,
                )
                raise

    async def _attempt_event(
        self,
        request: CapabilityBuildRequest,
        attempt_number: int,
        model: str,
        result: str,
        codes: tuple[str, ...],
        started: float,
        failure_class: str | None = None,
    ) -> None:
        await self._trace.event(
            "capability_generation_attempt",
            run_id=request.gap.run_id,
            task_id=request.gap.task_id,
            attributes={
                "provider": self.provider_name,
                "model": model,
                "workload_type": "GENERATED_CAPABILITY",
                "attempt_number": attempt_number,
                "result": result,
                "validation_codes": ",".join(codes) or None,
                "failure_class": failure_class,
                "elapsed_ms": (perf_counter() - started) * 1000,
            },
        )

    async def _complete_error(
        self,
        generation: Any,
        request: CapabilityBuildRequest,
        started: float,
        failure_class: str | None,
        error_type: str | None,
    ) -> None:
        await self._trace.complete_generation(
            generation,
            requested_model=self.model_name or None,
            actual_model=None,
            provider=self._provider_name,
            latency_ms=(perf_counter() - started) * 1000,
            input_tokens=None,
            output_tokens=None,
            implementation_hash=None,
            result_status="error",
            error_type=error_type or "GeneratedCapabilityDeadlineExceededError",
            workload_type="GENERATED_CAPABILITY",
            attempt_number=request.attempt,
            failure_class=failure_class,
        )


# Backward-compatible import for Phase 2/early Phase 3 callers.
TeamoRouterCodeBuilder = PlannerProviderCodeBuilder


def _initial_messages(request: GeneratedCapabilityRequestV1) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Return only one strict GeneratedCapabilityBundleV1 JSON object. Copy "
                "identifiers, entrypoint, and schemas exactly from the owned request. "
                "Implement the exact formula using Decimal(str(input)) throughout, "
                "including signed capital expenditure. Never use float, round, quantize, "
                "network, filesystem, process, environment, dynamic import, eval, or exec. "
                "Source must define synchronous execute(inputs) and return exactly value as "
                "a decimal string and the requested unit. Tests must define synchronous "
                "run_tests(execute, fixture), derive the expected value from every supplied "
                "fixture, and assert formula value and unit without a framework. Declare only "
                "imports actually used and permitted by the request. Do not include reasoning "
                "or hidden chain-of-thought."
            ),
        ),
        LLMMessage(
            role="user",
            content=json.dumps(
                request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ),
        ),
    ]


def _repair_messages(
    request: GeneratedCapabilityRequestV1,
    previous_bundle: GeneratedCapabilityBundleV1,
    findings: tuple[GCValidationFinding, ...],
) -> list[LLMMessage]:
    repair = {
        "request": request.model_dump(mode="json"),
        "previous_bundle": previous_bundle.model_dump(mode="json"),
        "deterministic_validation_findings": [finding.as_dict() for finding in findings],
    }
    return [
        LLMMessage(
            role="system",
            content=(
                "Repair the prior generated-capability bundle using only the machine-readable "
                "corrective facts. Return one complete replacement GeneratedCapabilityBundleV1 "
                "JSON object, not a patch. Preserve exact request identifiers and schemas. Do "
                "not include reasoning or hidden chain-of-thought."
            ),
        ),
        LLMMessage(
            role="user",
            content=json.dumps(repair, sort_keys=True, separators=(",", ":")),
        ),
    ]


def _lock_to_actual_model(provider: LLMProvider, model: str) -> LLMProvider:
    if (
        getattr(provider, "model_name", None) == model
        and provider.__class__.__name__ == "LockedPlannerProvider"
    ):
        return provider
    lock_factory = getattr(provider, "lock_to_model", None)
    if callable(lock_factory):
        locked = lock_factory(model)
        if getattr(locked, "provider_name", None) != getattr(provider, "provider_name", None):
            raise ValueError("provider model lock changed provider identity")
        return locked
    return provider


def _source_hash(source: str) -> str:
    return generated_text_sha256(source)


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _sum_optional(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if isinstance(value, int)]
    return sum(present) if present else None


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
