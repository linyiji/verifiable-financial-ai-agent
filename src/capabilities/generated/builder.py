from __future__ import annotations

import hashlib
import json
from time import perf_counter

from src.adapters.llm.provider import LLMMessage, LLMProvider
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    CodeBuilderOutput,
    CodeBuilderProviderOutput,
    GeneratedCapabilityCandidate,
)
from src.capabilities.generated.telemetry import GeneratedCapabilityTrace


class CodeBuilderOutputMismatch(ValueError):
    """The response is structurally valid but exceeds or changes its approved spec."""


class TeamoRouterCodeBuilder:
    """Generate a candidate through the owned structured-output provider boundary.

    This client does not execute, import, compile, or persist generated source.
    Validation and materialization belong to the injected U2/U3 ports.
    """

    builder_id = "teamorouter-code-builder-v1"
    schema_name = "generated_capability_candidate_v1"

    def __init__(
        self,
        provider: LLMProvider,
        *,
        trace: GeneratedCapabilityTrace | None = None,
    ) -> None:
        if getattr(provider, "provider_name", None) != "teamorouter":
            raise ValueError("Code Builder requires the configured TeamoRouter provider")
        self._provider = provider
        self._trace = trace or GeneratedCapabilityTrace()

    async def generate(self, request: CapabilityBuildRequest) -> GeneratedCapabilityCandidate:
        requirement = request.gap.requirement
        started = perf_counter()
        async with self._trace.generation(
            run_id=request.gap.run_id,
            task_id=request.gap.task_id,
            build_id=request.build_id,
            capability_id=requirement.capability_id,
            attempt=request.attempt,
        ) as generation:
            try:
                response = await self._provider.complete_structured(
                    messages=_messages(request),
                    response_model=CodeBuilderProviderOutput,
                    schema_name=self.schema_name,
                )
                output = response.output.to_domain()
                _validate_output_against_requirement(output, request)
                implementation_hash = _source_hash(output.source_code)
            except Exception as exc:
                await self._trace.complete_generation(
                    generation,
                    requested_model=_optional_text(getattr(exc, "requested_model", None)),
                    actual_model=None,
                    provider="teamorouter",
                    latency_ms=(perf_counter() - started) * 1000,
                    input_tokens=None,
                    output_tokens=None,
                    implementation_hash=None,
                    result_status="error",
                    error_type=type(exc).__name__,
                )
                raise

            latency_ms = (perf_counter() - started) * 1000
            await self._trace.complete_generation(
                generation,
                requested_model=response.requested_model,
                actual_model=response.actual_model,
                provider=response.provider,
                latency_ms=latency_ms,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                implementation_hash=implementation_hash,
                result_status="success",
            )
            return GeneratedCapabilityCandidate(
                build_id=request.build_id,
                output=output,
                implementation_hash=implementation_hash,
                provider=response.provider,
                requested_model=response.requested_model,
                actual_model=response.actual_model,
                attempted_models=response.attempted_models,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=latency_ms,
            )


def _messages(request: CapabilityBuildRequest) -> list[LLMMessage]:
    requirement = request.gap.requirement
    approved_spec = {
        "capability_id": requirement.capability_id,
        "purpose": requirement.purpose,
        "input_schema": requirement.input_schema,
        "output_schema": requirement.output_schema,
        "formula_id": requirement.formula_id,
        "deterministic": requirement.deterministic,
        "allowed_imports": requirement.allowed_imports,
        "financial_invariants": requirement.financial_invariants,
        "attempt": request.attempt,
    }
    return [
        LLMMessage(
            role="system",
            content=(
                "Return only the requested structured generated-capability candidate. "
                "Encode input_schema and output_schema as arrays of objects with exactly "
                "name and type fields, preserving every approved schema entry. "
                "Copy capability_id, purpose, formula_id, input_schema, output_schema, "
                "allowed_imports, and financial_invariants from the approved spec exactly. "
                "Implement deterministic pure Python for the approved formula. Do not use "
                "network, filesystem, process, environment, dynamic-import, eval, exec, or "
                "secret access. Source must expose execute(inputs), where inputs is one mapping "
                "whose values are decimal-compatible strings. It must return exactly a mapping "
                "with value as a decimal-compatible string and unit copied exactly from the "
                "approved output schema. Unit tests must expose run_tests(execute, fixture), call "
                "execute(fixture), and return True or None. The owned validator invokes run_tests "
                "repeatedly with different valid primary, edge, and live fixtures, including zero "
                "and negative results, so derive the expected result from the current fixture "
                "using the approved formula; never hard-code one fixture-specific result. Source "
                "and tests share one restricted namespace. Use only approved imports and basic "
                "built-ins; do not use pytest, unittest, or another test framework. Provide "
                "explicit financial invariants. "
                "Do not include reasoning or hidden chain-of-thought."
            ),
        ),
        LLMMessage(
            role="user",
            content=json.dumps(approved_spec, sort_keys=True, separators=(",", ":")),
        ),
    ]


def _validate_output_against_requirement(
    output: CodeBuilderOutput,
    request: CapabilityBuildRequest,
) -> None:
    requirement = request.gap.requirement
    mismatches: list[str] = []
    if output.capability_id != requirement.capability_id:
        mismatches.append("capability_id")
    if output.purpose != requirement.purpose:
        mismatches.append("purpose")
    if output.formula_id != requirement.formula_id:
        mismatches.append("formula_id")
    if output.input_schema != requirement.input_schema:
        mismatches.append("input_schema")
    if output.output_schema != requirement.output_schema:
        mismatches.append("output_schema")
    if not set(output.allowed_imports).issubset(requirement.allowed_imports):
        mismatches.append("allowed_imports")
    if not set(requirement.financial_invariants).issubset(output.financial_invariants):
        mismatches.append("financial_invariants")
    if not requirement.deterministic:
        mismatches.append("deterministic_requirement")
    if mismatches:
        raise CodeBuilderOutputMismatch(
            "generated output changed approved fields: " + ", ".join(mismatches)
        )


def _source_hash(source: str) -> str:
    normalized = source.replace("\r\n", "\n").replace("\r", "\n").rstrip() + "\n"
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
