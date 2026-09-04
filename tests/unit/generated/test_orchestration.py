from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from src.capabilities.generated.models import (
    CapabilityBuildRequest,
    GeneratedCapabilityCandidate,
    ResearchLeadCapabilityApproval,
    SpecialistCapabilityRequest,
    ValidationHandoff,
)
from src.capabilities.generated.orchestration import (
    CapabilityBuildFailedError,
    GeneratedCapabilityOrchestrator,
)
from src.domain.base import JsonObject
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityGapRecord,
    CapabilityRequirement,
    CapabilityValidationRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.domain.enums import (
    CapabilityBackend,
    CapabilityLifecycle,
    CapabilityScope,
    TaskOrigin,
    TaskStatus,
)
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.state import RuntimeState


class GeneratedMarginCapability:
    definition = CapabilityDefinition(
        capability_id="gross_margin",
        version="1.0.0-generated",
        name="Generated Gross Margin",
        category="financial_calculation",
        backend=CapabilityBackend.GENERATED,
        input_schema={"gross_profit": "decimal", "revenue": "decimal"},
        output_schema={"value": "decimal", "unit": "ratio"},
        deterministic=True,
        implementation_ref="generated://BUILD/source.py",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> object:
        del inputs, context
        return {"value": "0.5", "unit": "ratio"}


def make_state() -> RuntimeState:
    task = Task(
        task_id="TASK-1",
        run_id="RUN-1",
        task_type="fundamental_analysis",
        goal="Calculate missing deterministic margin.",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        origin=TaskOrigin.PLAN,
        status=TaskStatus.RUNNING,
    )
    graph = PlannedTaskGraph(graph_id="GRAPH-1", run_id="RUN-1", tasks=[task])
    return RuntimeState.create(run_id="RUN-1", planned_graph=graph)


def make_request(**updates: object) -> SpecialistCapabilityRequest:
    values: dict[str, object] = {
        "run_id": "RUN-1",
        "task_id": "TASK-1",
        "skill_id": "fundamental_analysis_v1",
        "requested_by": "fundamental_analyst",
        "requirement": CapabilityRequirement(
            requirement_id="REQ-1",
            capability_id="gross_margin",
            purpose="Calculate gross margin.",
            input_schema={"gross_profit": "decimal", "revenue": "decimal"},
            output_schema={"value": "decimal", "unit": "ratio"},
            formula_id="gross_margin_v1",
            allowed_imports=["decimal"],
            financial_invariants=["revenue_non_zero"],
        ),
    }
    values.update(updates)
    return SpecialistCapabilityRequest.model_validate(values)


class FakeRegistry:
    def __init__(self, existing: object | None = None) -> None:
        self._capability = existing
        self.registrations: list[ScopedCapabilityRegistration] = []

    async def lookup(self, capability_id: str, **scope: object):
        del capability_id, scope
        return self._capability

    async def register(self, registration, capability):
        assert registration.lifecycle is CapabilityLifecycle.TASK_APPROVED
        assert registration.scope is not None
        self._capability = capability
        active = registration.model_copy(update={"lifecycle": CapabilityLifecycle.ACTIVE_FOR_SCOPE})
        self.registrations.append(active)
        return active


class FakeResearchLead:
    lead_agent_id = "research_lead"

    def __init__(self, *, approve_spec: bool = True, approve_activation: bool = True) -> None:
        self.spec_decision = approve_spec
        self.activation_decision = approve_activation
        self.spec_calls = 0
        self.activation_calls = 0

    async def approve_spec(self, gap: CapabilityGapRecord) -> ResearchLeadCapabilityApproval:
        self.spec_calls += 1
        return _approval(gap, phase="SPEC", approved=self.spec_decision)

    async def approve_activation(
        self,
        gap: CapabilityGapRecord,
        generated: GeneratedCapabilityRecord,
        validation: CapabilityValidationRecord,
    ) -> ResearchLeadCapabilityApproval:
        del generated, validation
        self.activation_calls += 1
        return _approval(gap, phase="ACTIVATION", approved=self.activation_decision)


def _approval(
    gap: CapabilityGapRecord,
    *,
    phase: str,
    approved: bool,
) -> ResearchLeadCapabilityApproval:
    return ResearchLeadCapabilityApproval(
        decision_id=f"DEC-{phase}",
        run_id=gap.run_id,
        task_id=gap.task_id,
        gap_id=gap.gap_id,
        phase=phase,
        approved=approved,
        approved_by="research_lead",
        reason_code="POLICY_DECISION",
        summary="Explicit Research Lead decision.",
    )


class FakeBuilder:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.calls: list[CapabilityBuildRequest] = []

    async def generate(self, request: CapabilityBuildRequest) -> GeneratedCapabilityCandidate:
        self.calls.append(request)
        if len(self.calls) <= self.failures:
            raise RuntimeError("generation unavailable")
        return GeneratedCapabilityCandidate(
            build_id=request.build_id,
            output=_candidate_output(),
            implementation_hash="sha256:generated-source",
            provider="teamorouter",
            requested_model="gpt-5.6-sol",
            actual_model="gpt-5.6-luna",
            attempted_models=("gpt-5.6-sol", "gpt-5.6-luna"),
            input_tokens=10,
            output_tokens=20,
            latency_ms=12.5,
        )


def _candidate_output():
    from src.capabilities.generated.models import CodeBuilderOutput

    return CodeBuilderOutput(
        capability_id="gross_margin",
        version="1.0.0-generated",
        purpose="Calculate gross margin.",
        input_schema={"gross_profit": "decimal", "revenue": "decimal"},
        output_schema={"value": "decimal", "unit": "ratio"},
        formula_id="gross_margin_v1",
        formula_description="gross_profit / revenue",
        source_code="def calculate(gross_profit, revenue): return gross_profit / revenue\n",
        unit_tests="def test_calculate(): assert calculate(1, 2) == 0.5\n",
        financial_invariants=["revenue_non_zero"],
        allowed_imports=["decimal"],
    )


class FakeValidator:
    async def validate(self, candidate, *, progress) -> ValidationHandoff:
        await progress.static_validated(candidate.implementation_hash)
        await progress.sandbox_started(candidate.implementation_hash)
        await progress.tests_passed(candidate.implementation_hash)
        await progress.financial_validated(candidate.implementation_hash)
        validation = CapabilityValidationRecord(
            validation_id="VAL-1",
            build_id=candidate.build_id,
            implementation_hash=candidate.implementation_hash,
            static_validation_passed=True,
            syntax_compile_passed=True,
            unit_tests_passed=True,
            edge_cases_passed=True,
            financial_invariants_passed=True,
            deterministic_double_run_passed=True,
            output_schema_passed=True,
            unit_validation_passed=True,
            financial_validation_passed=True,
            lifecycle=CapabilityLifecycle.FINANCIAL_VALIDATED,
        )
        sandbox = SandboxExecutionRecord(
            execution_id="SBX-1",
            build_id=candidate.build_id,
            backend="docker",
            implementation_hash=candidate.implementation_hash,
            runtime_version="Python 3.11",
            input_fixture_hash="sha256:fixture",
            network_disabled=True,
            read_only_root=True,
            non_root_user=True,
            resource_limits={"memory": "128m", "pids": 32},
            exit_code=0,
            output_hash="sha256:output",
            passed=True,
        )
        return ValidationHandoff(
            validation=validation,
            sandbox_execution=sandbox,
            capability=GeneratedMarginCapability(),
        )


class RejectFirstValidator(FakeValidator):
    def __init__(self) -> None:
        self.calls = 0

    async def validate(self, candidate, *, progress) -> ValidationHandoff:
        self.calls += 1
        if self.calls == 1:
            await progress.static_validated(candidate.implementation_hash)
            raise ValueError("precision fixture rejected generated output")
        return await super().validate(candidate, progress=progress)


@dataclass
class MemoryRecorder:
    gaps: list[CapabilityGapRecord]
    builds: list[CapabilityBuildRecord]
    generated: list[GeneratedCapabilityRecord]
    validations: list[CapabilityValidationRecord]
    registrations: list[ScopedCapabilityRegistration]

    def __init__(self) -> None:
        self.gaps = []
        self.builds = []
        self.generated = []
        self.validations = []
        self.registrations = []

    async def record_gap(self, gap):
        self.gaps.append(gap)

    async def record_build(self, build):
        self.builds.append(build)

    async def record_generated(self, generated):
        self.generated.append(generated)

    async def record_validation(self, validation, sandbox_execution):
        del sandbox_execution
        self.validations.append(validation)

    async def record_registration(self, registration):
        self.registrations.append(registration)


def orchestrator(
    *, registry=None, lead=None, builder=None, validator=None, recorder=None, max_attempts=2
):
    events = InMemoryRuntimeEventStore()
    service = GeneratedCapabilityOrchestrator(
        registry=registry or FakeRegistry(),
        research_lead=lead or FakeResearchLead(),
        code_builder=builder or FakeBuilder(),
        validator=validator or FakeValidator(),
        event_store=events,
        recorder=recorder,
        max_attempts=max_attempts,
    )
    return service, events


@pytest.mark.asyncio
async def test_full_governed_path_scopes_and_resumes_same_task_without_graph_mutation() -> None:
    state = make_state()
    initial_task_ids = [task.task_id for task in state.actual_graph.tasks]
    initial_graph_version = state.actual_graph.version
    registry = FakeRegistry()
    recorder = MemoryRecorder()
    service, events = orchestrator(registry=registry, recorder=recorder)

    result = await service.lookup_or_build(state=state, request=make_request())

    assert result.registration.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE
    assert result.registration.scope is CapabilityScope.TASK
    assert result.registration.task_id == "TASK-1"
    assert result.registration.approved_by == "research_lead"
    assert state.task("TASK-1").status is TaskStatus.RUNNING
    assert [task.task_id for task in state.actual_graph.tasks] == initial_task_ids
    assert state.actual_graph.version == initial_graph_version
    assert len(state.actual_graph.tasks) == 1  # Capability Build is not a Research Task.
    assert recorder.gaps and recorder.generated and recorder.validations and recorder.registrations
    assert result.generated.runtime_version == result.sandbox_execution.runtime_version
    assert recorder.generated[-1].runtime_version == result.sandbox_execution.runtime_version

    event_types = [event.type for event in await events.replay("RUN-1")]
    assert event_types == [
        RuntimeEventType.CAPABILITY_GAP_DETECTED,
        RuntimeEventType.TASK_WAITING_FOR_CAPABILITY,
        RuntimeEventType.CAPABILITY_BUILD_REQUESTED,
        RuntimeEventType.CAPABILITY_BUILD_STARTED,
        RuntimeEventType.CAPABILITY_GENERATED,
        RuntimeEventType.CAPABILITY_STATIC_VALIDATED,
        RuntimeEventType.CAPABILITY_SANDBOX_STARTED,
        RuntimeEventType.CAPABILITY_TEST_PASSED,
        RuntimeEventType.CAPABILITY_FINANCIAL_VALIDATED,
        RuntimeEventType.CAPABILITY_APPROVED,
        RuntimeEventType.CAPABILITY_REGISTERED,
        RuntimeEventType.TASK_RESUMED,
    ]
    payload_dump = str([event.payload for event in await events.replay("RUN-1")])
    assert "source_code" not in payload_dump
    assert "unit_tests" not in payload_dump


@pytest.mark.asyncio
async def test_existing_capability_bypasses_gap_and_builder() -> None:
    capability = GeneratedMarginCapability()
    registry = FakeRegistry(existing=capability)
    builder = FakeBuilder()
    service, events = orchestrator(registry=registry, builder=builder)
    state = make_state()

    result = await service.lookup_or_build(state=state, request=make_request())

    assert result is capability
    assert builder.calls == []
    assert await events.replay("RUN-1") == []
    assert state.task("TASK-1").status is TaskStatus.RUNNING


@pytest.mark.asyncio
async def test_rejected_generated_attempt_is_retained_as_build_failed() -> None:
    recorder = MemoryRecorder()
    service, _ = orchestrator(validator=RejectFirstValidator(), recorder=recorder)

    result = await service.lookup_or_build(state=make_state(), request=make_request())

    latest_by_id = {item.generated_capability_id: item for item in recorder.generated}
    assert len(latest_by_id) == 2
    assert sorted(item.lifecycle.value for item in latest_by_id.values()) == [
        "ACTIVE_FOR_SCOPE",
        "BUILD_FAILED",
    ]
    assert result.generated.lifecycle is CapabilityLifecycle.ACTIVE_FOR_SCOPE


@pytest.mark.asyncio
async def test_generation_failures_are_bounded_and_explicit() -> None:
    builder = FakeBuilder(failures=99)
    service, events = orchestrator(builder=builder, max_attempts=2)
    state = make_state()

    with pytest.raises(CapabilityBuildFailedError) as raised:
        await service.lookup_or_build(state=state, request=make_request())

    assert len(builder.calls) == 2
    assert state.task("TASK-1").status is TaskStatus.CAPABILITY_BUILD_FAILED
    assert len(raised.value.build_records) == 2
    assert all(
        build.lifecycle is CapabilityLifecycle.BUILD_FAILED for build in raised.value.build_records
    )
    failures = [
        event
        for event in await events.replay("RUN-1")
        if event.type is RuntimeEventType.CAPABILITY_BUILD_FAILED
    ]
    assert [event.payload["terminal"] for event in failures] == [False, True]


@pytest.mark.asyncio
async def test_research_lead_must_approve_before_builder_runs() -> None:
    lead = FakeResearchLead(approve_spec=False)
    builder = FakeBuilder()
    service, events = orchestrator(lead=lead, builder=builder)
    state = make_state()

    with pytest.raises(CapabilityBuildFailedError, match="did not approve"):
        await service.lookup_or_build(state=state, request=make_request())

    assert builder.calls == []
    assert state.task("TASK-1").status is TaskStatus.CAPABILITY_BUILD_FAILED
    assert (await events.replay("RUN-1"))[-1].type is RuntimeEventType.CAPABILITY_BUILD_FAILED


def test_specialist_request_cannot_smuggle_approval_or_registration_authority() -> None:
    request = make_request()
    payload = request.model_dump(mode="json")
    payload["approved_by"] = "fundamental_analyst"
    payload["register_globally"] = True

    with pytest.raises(ValidationError):
        SpecialistCapabilityRequest.model_validate(payload)


@pytest.mark.asyncio
async def test_request_must_come_through_the_task_assigned_skill() -> None:
    service, events = orchestrator()
    state = make_state()

    with pytest.raises(ValueError, match="assigned Skill"):
        await service.lookup_or_build(
            state=state,
            request=make_request(skill_id="unrelated_skill"),
        )

    assert await events.replay("RUN-1") == []
    assert state.task("TASK-1").status is TaskStatus.RUNNING
