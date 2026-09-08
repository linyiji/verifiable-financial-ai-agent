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
from src.capabilities.generated.contract import GeneratedCapabilityRequestV1
from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    ResearchLeadCapabilityApproval,
)
from src.capabilities.generated.spec import (
    GeneratedCapabilitySpecV1,
    GeneratedCapabilitySpecValidationError,
    expected_spec,
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


def spec_output(**updates: object) -> dict[str, object]:
    owned = GeneratedCapabilityRequestV1.from_build_request(build_request())
    output = expected_spec(owned).model_dump(mode="json")
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
        assert kwargs["response_model"] is GeneratedCapabilitySpecV1
        if self.delay:
            await asyncio.sleep(self.delay)
        output = self.outputs[min(len(self.calls) - 1, len(self.outputs) - 1)]
        return LLMStructuredResponse(
            output=GeneratedCapabilitySpecV1.model_validate(output),
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


@pytest.mark.asyncio
async def test_exact_terra_builder_identity():
    from dataclasses import replace

    from src.capabilities.generated.builder import (
        CodeBuilderModelIdentityError,
        PlannerProviderCodeBuilder,
    )

    provider = FakeProvider([spec_output()], model="gpt-5.6-terra")
    candidate = await PlannerProviderCodeBuilder(provider, exact_model="gpt-5.6-terra").generate(
        build_request()
    )
    assert candidate.actual_model == "gpt-5.6-terra"
    assert provider.locked_models == ["gpt-5.6-terra"]

    class Substitution(FakeProvider):
        async def complete_structured(self, **kwargs):
            response = await super().complete_structured(**kwargs)
            return replace(response, actual_model="gpt-5.6-sol")

    substituted = Substitution([spec_output()], model="gpt-5.6-terra")
    with pytest.raises(CodeBuilderModelIdentityError):
        await PlannerProviderCodeBuilder(substituted, exact_model="gpt-5.6-terra").generate(
            build_request()
        )
    assert len(substituted.calls) == 1
    assert substituted.locked_models == []


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
    provider = FakeProvider([spec_output()])
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(provider, trace=GeneratedCapabilityTrace(trace_spy))

    candidate = await builder.generate(build_request())

    assert candidate.provider == "teamorouter"
    assert candidate.actual_model == "gpt-5.6-sol"
    assert candidate.implementation_hash.startswith("sha256:")
    assert candidate.output.purpose == requirement().purpose
    assert candidate.output.financial_invariants == requirement().financial_invariants
    assert provider.calls[0]["schema_name"] == "generated_capability_spec_v1"
    prompt = provider.calls[0]["messages"]
    assert "Do not include reasoning" in prompt[0].content
    assert json.loads(prompt[1].content)["owned_request"]["schema_version"] == (
        "generated-capability-request/v1"
    )
    assert candidate.spec_sha256 is not None
    assert candidate.compiler_version == "1"

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

    schema = GeneratedCapabilitySpecV1.model_json_schema()
    objects = list(object_schemas(schema))
    assert objects
    assert all(item.get("additionalProperties") is False for item in objects)
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_invalid_formula_gets_one_same_model_full_bundle_repair() -> None:
    invalid = spec_output()
    formula = list(invalid["formula"])
    formula[-1] = {**formula[-1], "operation": "SUBTRACT"}
    invalid["formula"] = formula
    provider = FakeProvider([invalid, spec_output()])
    trace_spy = TraceSpy()
    builder = TeamoRouterCodeBuilder(provider, trace=GeneratedCapabilityTrace(trace_spy))

    candidate = await builder.generate(build_request())

    assert candidate.actual_model == "gpt-5.6-sol"
    assert len(provider.calls) == 2
    assert provider.locked_models == ["gpt-5.6-sol"]
    repair = json.loads(provider.calls[1]["messages"][1].content)
    assert repair["previous_spec"]["formula"][-1]["operation"] == "SUBTRACT"
    assert repair["deterministic_validation_findings"] == [
        {
            "code": "GC_SPEC_FORMULA_MISMATCH",
            "description": "deterministic generated-capability requirement not satisfied",
            "field": "formula",
            "expected_rule": "exact owned closed formula IR",
        }
    ]
    trace_dump = str(trace_spy.events)
    assert "GC_SPEC_FORMULA_MISMATCH" in trace_dump
    assert "SUBTRACT" not in trace_dump
    assert candidate.input_tokens == 202
    assert candidate.output_tokens == 106


@pytest.mark.asyncio
async def test_final_invalid_spec_returns_machine_codes_without_provider_switch() -> None:
    bad = spec_output(allowed_dependencies=["decimal", "os"])
    provider = FakeProvider([bad, bad])

    with pytest.raises(GeneratedCapabilitySpecValidationError) as captured:
        await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert "GC_SPEC_DEPENDENCY_MISMATCH" in captured.value.codes
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
    provider = FakeProvider([spec_output()], delay=0.1, policy=policy)

    with pytest.raises(GeneratedCapabilityDeadlineExceededError):
        await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert len(provider.calls) == 1


def test_builder_rejects_a_new_direct_provider_route() -> None:
    class DirectProvider(FakeProvider):
        provider_name = "openai"

    with pytest.raises(ValueError, match="registered planner provider"):
        TeamoRouterCodeBuilder(DirectProvider([spec_output()]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "expected_provider"),
    (
        (FakeProvider([spec_output()]), "teamorouter"),
        (FakeMimoProvider([spec_output()]), "mimo"),
    ),
)
async def test_same_contract_accepts_each_registered_provider(
    provider: FakeProvider,
    expected_provider: str,
) -> None:
    candidate = await TeamoRouterCodeBuilder(provider).generate(build_request())

    assert candidate.provider == expected_provider
