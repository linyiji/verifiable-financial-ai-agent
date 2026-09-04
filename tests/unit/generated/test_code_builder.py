from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from src.adapters.llm.execution import ProviderExecutionPolicyV1
from src.adapters.llm.provider import LLMStructuredResponse
from src.capabilities.generated.builder import (
    GeneratedCapabilityDeadlineExceededError,
    TeamoRouterCodeBuilder,
)
from src.capabilities.generated.contract import (
    GeneratedCapabilityBundleV1,
    GeneratedCapabilityBundleValidationError,
)
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
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


def bundle_output(**updates: object) -> dict[str, object]:
    output: dict[str, object] = {
        "schema_version": "generated-capability-bundle/v1",
        "capability_id": "gross_margin",
        "formula_id": "gross_margin_v1",
        "entrypoint": "execute",
        "source": (
            "from decimal import Decimal\n\n"
            "def execute(inputs):\n"
            "    gross_profit = Decimal(str(inputs['gross_profit']))\n"
            "    revenue = Decimal(str(inputs['revenue']))\n"
            "    return {'value': str(gross_profit / revenue), 'unit': 'ratio'}\n"
        ),
        "tests": (
            "def run_tests(execute, fixture):\n"
            "    result = execute(fixture)\n"
            "    expected = Decimal(str(fixture['gross_profit'])) / "
            "Decimal(str(fixture['revenue']))\n"
            "    assert Decimal(str(result['value'])) == expected\n"
            "    assert result['unit'] == 'ratio'\n"
            "    return True\n"
        ),
        "input_schema": [
            {"name": "gross_profit", "type": "decimal"},
            {"name": "revenue", "type": "decimal"},
        ],
        "output_schema": [
            {"name": "value", "type": "decimal"},
            {"name": "unit", "type": "ratio"},
        ],
        "methodology": "gross_profit / revenue using Decimal",
        "declared_dependencies": ["decimal"],
    }
    output.update(updates)
    return output


class FakeProvider:
    provider_name = "teamorouter"

    def __init__(
        self,
        outputs: list[dict[str, object]],
        *,
        model: str = "gpt-5.6-sol",
        delay: float = 0.0,
        policy: ProviderExecutionPolicyV1 | None = None,
    ) -> None:
        self.outputs = list(outputs)
        self.model_name = model
        self.delay = delay
        self.execution_policy = policy or ProviderExecutionPolicyV1(bounded_backoff_seconds=(0.0,))
        self.calls: list[dict[str, object]] = []
        self.locked_models: list[str] = []

    def lock_to_model(self, model_name: str) -> FakeProvider:
        self.locked_models.append(model_name)
        assert model_name == self.model_name
        return self

    async def complete_structured(self, **kwargs: object) -> LLMStructuredResponse:
        self.calls.append(kwargs)
        assert kwargs["response_model"] is GeneratedCapabilityBundleV1
        if self.delay:
            await asyncio.sleep(self.delay)
        output = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        return LLMStructuredResponse(
            output=GeneratedCapabilityBundleV1.model_validate(output),
            provider=self.provider_name,
            requested_model=self.model_name,
            actual_model=self.model_name,
            attempted_models=(self.model_name,),
            input_tokens=101,
            output_tokens=53,
        )


class FakeMimoProvider(FakeProvider):
    provider_name = "mimo"

    def __init__(self, outputs: list[dict[str, object]]) -> None:
        super().__init__(outputs, model="mimo-v2.5")


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
async def test_builder_accepts_strict_owned_bundle_and_records_only_safe_metadata() -> None:
    provider = FakeProvider([bundle_output()])
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(provider, trace=GeneratedCapabilityTrace(trace_spy))

    candidate = await builder.generate(build_request())

    assert candidate.provider == "teamorouter"
    assert candidate.actual_model == "gpt-5.6-sol"
    assert candidate.implementation_hash.startswith("sha256:")
    assert candidate.output.purpose == requirement().purpose
    assert candidate.output.financial_invariants == requirement().financial_invariants
    assert provider.calls[0]["schema_name"] == "generated_capability_bundle_v1"
    prompt = provider.calls[0]["messages"]
    assert "Do not include reasoning" in prompt[0].content
    assert json.loads(prompt[1].content)["schema_version"] == "generated-capability-request/v1"

    trace_dump = str([trace_spy.generations, trace_spy.updates, trace_spy.events])
    assert "gross_profit / revenue" not in trace_dump
    assert "source" not in trace_dump
    assert "tests" not in trace_dump
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

    schema = GeneratedCapabilityBundleV1.model_json_schema()
    objects = list(object_schemas(schema))
    assert objects
    assert all(item.get("additionalProperties") is False for item in objects)
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_invalid_formula_gets_one_same_model_full_bundle_repair() -> None:
    invalid_source = str(bundle_output()["source"]).replace(
        "gross_profit / revenue", "gross_profit - revenue"
    )
    provider = FakeProvider([bundle_output(source=invalid_source), bundle_output()])
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(provider, trace=GeneratedCapabilityTrace(trace_spy))

    candidate = await builder.generate(build_request())

    assert candidate.actual_model == "gpt-5.6-sol"
    assert len(provider.calls) == 2
    assert provider.locked_models == ["gpt-5.6-sol"]
    repair = json.loads(provider.calls[1]["messages"][1].content)
    assert repair["previous_bundle"]["source"] == invalid_source
    assert repair["deterministic_validation_findings"] == [
        {
            "code": "GC_FINANCIAL_FORMULA_MISMATCH",
            "description": "deterministic generated-capability requirement not satisfied",
            "field": "source",
            "expected_rule": "exact owned formula semantics",
        }
    ]
    trace_dump = str(trace_spy.events)
    assert "GC_FINANCIAL_FORMULA_MISMATCH" in trace_dump
    assert invalid_source not in trace_dump
    assert candidate.input_tokens == 202
    assert candidate.output_tokens == 106


@pytest.mark.asyncio
async def test_final_invalid_bundle_returns_machine_codes_without_provider_switch() -> None:
    bad = bundle_output(declared_dependencies=["decimal", "os"])
    provider = FakeProvider([bad, bad])

    with pytest.raises(GeneratedCapabilityBundleValidationError) as captured:
        await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert "GC_SCHEMA_DEPENDENCY_FORBIDDEN" in captured.value.codes
    assert len(provider.calls) == 2
    assert provider.locked_models == ["gpt-5.6-sol"]


@pytest.mark.asyncio
async def test_absolute_deadline_covers_generation_and_prevents_repair_reset() -> None:
    policy = ProviderExecutionPolicyV1(
        connect_timeout_seconds=0.01,
        read_timeout_seconds=0.01,
        write_timeout_seconds=0.01,
        pool_timeout_seconds=0.01,
        max_attempts=2,
        bounded_backoff_seconds=(0.0,),
        per_attempt_deadline_seconds=0.02,
        overall_workload_deadline_seconds=0.03,
    )
    provider = FakeProvider([bundle_output()], delay=0.1, policy=policy)

    with pytest.raises(GeneratedCapabilityDeadlineExceededError):
        await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert len(provider.calls) == 1


def test_builder_rejects_a_new_direct_provider_route() -> None:
    class DirectProvider(FakeProvider):
        provider_name = "openai"

    with pytest.raises(ValueError, match="registered planner provider"):
        TeamoRouterCodeBuilder(DirectProvider([bundle_output()]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_provider"),
    (
        (FakeProvider([bundle_output()]), "teamorouter"),
        (FakeMimoProvider([bundle_output()]), "mimo"),
    ),
)
async def test_same_contract_accepts_each_registered_provider(
    provider: FakeProvider,
    expected_provider: str,
) -> None:
    candidate = await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert candidate.provider == expected_provider
