from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.adapters.llm.provider import LLMStructuredResponse
from src.capabilities.generated.builder import (
    CodeBuilderOutputMismatch,
    TeamoRouterCodeBuilder,
)
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    CodeBuilderProviderOutput,
    ResearchLeadCapabilityApproval,
)
from src.capabilities.generated.telemetry import GeneratedCapabilityTrace
from src.domain.capability import CapabilityGapRecord, CapabilityRequirement
from src.domain.enums import CapabilityLifecycle


def requirement() -> CapabilityRequirement:
    return CapabilityRequirement(
        requirement_id="REQ-1",
        capability_id="gross_margin",
        purpose="Calculate gross margin from accepted evidence.",
        input_schema={"gross_profit": "decimal", "revenue": "decimal"},
        output_schema={"value": "decimal", "unit": "ratio"},
        formula_id="gross_margin_v1",
        allowed_imports=["decimal"],
        financial_invariants=["revenue_non_zero", "result_is_finite"],
    )


def build_request() -> CapabilityBuildRequest:
    gap = CapabilityGapRecord(
        gap_id="GAP-1",
        run_id="RUN-1",
        task_id="TASK-1",
        requirement=requirement(),
        requested_by="fundamental_analyst",
        lifecycle=CapabilityLifecycle.GAP_DETECTED,
    )
    approval = ResearchLeadCapabilityApproval(
        decision_id="DEC-1",
        run_id="RUN-1",
        task_id="TASK-1",
        gap_id="GAP-1",
        phase="SPEC",
        approved=True,
        approved_by="research_lead",
        reason_code="DETERMINISTIC_GAP",
        summary="Approved for task-scoped generation.",
    )
    return CapabilityBuildRequest(
        build_id="BUILD-1",
        gap=gap,
        approval=approval,
        attempt=1,
        max_attempts=2,
    )


def builder_output(**updates: object) -> dict[str, object]:
    output: dict[str, object] = {
        "capability_id": "gross_margin",
        "version": "1.0.0-generated",
        "purpose": "Calculate gross margin from accepted evidence.",
        "input_schema": {"gross_profit": "decimal", "revenue": "decimal"},
        "output_schema": {"value": "decimal", "unit": "ratio"},
        "formula_id": "gross_margin_v1",
        "formula_description": "gross_profit / revenue",
        "source_code": (
            "from decimal import Decimal\n\n"
            "def execute(inputs):\n"
            "    gross_profit = Decimal(str(inputs['gross_profit']))\n"
            "    revenue = Decimal(str(inputs['revenue']))\n"
            "    return {'value': str(gross_profit / revenue), 'unit': 'ratio'}\n"
        ),
        "unit_tests": (
            "def run_tests(execute, fixture):\n"
            "    result = execute(fixture)\n"
            "    expected = Decimal(str(fixture['gross_profit'])) / "
            "Decimal(str(fixture['revenue']))\n"
            "    assert Decimal(str(result['value'])) == expected\n"
            "    assert result['unit'] == 'ratio'\n"
            "    return True\n"
        ),
        "financial_invariants": ["revenue_non_zero", "result_is_finite"],
        "allowed_imports": ["decimal"],
    }
    output.update(updates)
    return output


class FakeTeamoRouterProvider:
    provider_name = "teamorouter"

    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls: list[dict[str, object]] = []

    async def complete_structured(self, **kwargs: object) -> LLMStructuredResponse:
        self.calls.append(kwargs)
        model = kwargs["response_model"]
        assert model is CodeBuilderProviderOutput
        wire_output = dict(self.output)
        for field in ("input_schema", "output_schema"):
            mapping = wire_output[field]
            assert isinstance(mapping, dict)
            wire_output[field] = [{"name": name, "type": value} for name, value in mapping.items()]
        return LLMStructuredResponse(
            output=model.model_validate(wire_output),
            provider="teamorouter",
            requested_model="gpt-5.6-sol",
            actual_model="gpt-5.6-luna",
            attempted_models=("gpt-5.6-sol", "gpt-5.6-luna"),
            input_tokens=101,
            output_tokens=53,
        )


class FakeMimoProvider(FakeTeamoRouterProvider):
    provider_name = "mimo"

    async def complete_structured(self, **kwargs: object) -> LLMStructuredResponse:
        response = await super().complete_structured(**kwargs)
        return LLMStructuredResponse(
            output=response.output,
            provider="mimo",
            requested_model="mimo-v2.5",
            actual_model="mimo-v2.5",
            attempted_models=("mimo-v2.5",),
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )


class TraceSpy:
    def __init__(self) -> None:
        self.generations: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        self.events: list[dict[str, object]] = []

    @asynccontextmanager
    async def generation(self, name: str, **kwargs: object):
        self.generations.append({"name": name, **kwargs})
        yield object()

    async def complete_generation(self, generation: object, **kwargs: object) -> None:
        del generation
        self.updates.append(kwargs)

    @asynccontextmanager
    async def span(self, name: str, **kwargs: object):
        del name, kwargs
        yield None

    async def event(self, name: str, **kwargs: object) -> None:
        self.events.append({"name": name, **kwargs})


@pytest.mark.asyncio
async def test_builder_uses_owned_provider_schema_and_records_only_metadata() -> None:
    provider = FakeTeamoRouterProvider(builder_output())
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(
        provider,
        trace=GeneratedCapabilityTrace(trace_spy),
    )

    candidate = await builder.generate(build_request())

    assert candidate.provider == "teamorouter"
    assert candidate.requested_model == "gpt-5.6-sol"
    assert candidate.actual_model == "gpt-5.6-luna"
    assert candidate.implementation_hash.startswith("sha256:")
    assert candidate.output.input_schema == requirement().input_schema
    assert candidate.output.output_schema == requirement().output_schema
    assert provider.calls[0]["schema_name"] == "generated_capability_candidate_v1"
    assert "Do not include reasoning" in provider.calls[0]["messages"][0].content
    assert "invokes run_tests repeatedly" in provider.calls[0]["messages"][0].content
    assert "never hard-code one fixture-specific result" in provider.calls[0]["messages"][0].content
    assert "including zero and negative results" in provider.calls[0]["messages"][0].content
    assert "do not use pytest, unittest" in provider.calls[0]["messages"][0].content

    trace_dump = str([trace_spy.generations, trace_spy.updates, trace_spy.events])
    assert "gross_profit / revenue" not in trace_dump
    assert "source_code" not in trace_dump
    assert "unit_tests" not in trace_dump
    assert "chain-of-thought" not in trace_dump.lower()
    assert candidate.implementation_hash in trace_dump
    assert trace_spy.updates[0]["usage_details"] == {"input": 101, "output": 53, "total": 154}


def test_provider_wire_schema_contains_no_free_form_objects() -> None:
    def object_schemas(value: object):
        if isinstance(value, dict):
            if value.get("type") == "object":
                yield value
            for child in value.values():
                yield from object_schemas(child)
        elif isinstance(value, list):
            for child in value:
                yield from object_schemas(child)

    schema = CodeBuilderProviderOutput.model_json_schema()
    objects = list(object_schemas(schema))
    assert objects
    assert all(item.get("additionalProperties") is False for item in objects)


@pytest.mark.asyncio
async def test_builder_rejects_structured_output_that_expands_approved_imports() -> None:
    provider = FakeTeamoRouterProvider(builder_output(allowed_imports=["decimal", "os"]))
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(
        provider,
        trace=GeneratedCapabilityTrace(trace_spy),
    )

    with pytest.raises(CodeBuilderOutputMismatch, match="allowed_imports"):
        await builder.generate(build_request())

    assert trace_spy.updates[0]["attributes"]["result_status"] == "error"
    assert trace_spy.updates[0]["attributes"]["error_type"] == "CodeBuilderOutputMismatch"


@pytest.mark.asyncio
async def test_builder_rejects_provider_purpose_drift() -> None:
    provider = FakeTeamoRouterProvider(builder_output(purpose="Different unapproved purpose."))
    builder = TeamoRouterCodeBuilder(provider)

    with pytest.raises(CodeBuilderOutputMismatch, match="purpose"):
        await builder.generate(build_request())


def test_builder_rejects_a_new_direct_provider_route() -> None:
    class DirectProvider(FakeTeamoRouterProvider):
        provider_name = "openai"

    with pytest.raises(ValueError, match="registered planner provider"):
        TeamoRouterCodeBuilder(DirectProvider(builder_output()))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_provider"),
    (
        (FakeTeamoRouterProvider(builder_output()), "teamorouter"),
        (FakeMimoProvider(builder_output()), "mimo"),
    ),
)
async def test_builder_accepts_each_registered_provider_truthfully(
    provider: FakeTeamoRouterProvider,
    expected_provider: str,
) -> None:
    candidate = await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert candidate.provider == expected_provider
