from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from src.application.phase3_financial import (
    FCF_MARGIN_CAPABILITY_ID,
    FCF_MARGIN_FORMULA_ID,
    FreeCashFlowMarginValidationPlanProvider,
    Phase3FinancialCapabilityExtension,
    Phase3ResearchLeadCapabilityAuthority,
    free_cash_flow_margin_requirement,
)
from src.capabilities.generated.models import (
    CapabilityOrchestrationResult,
    CodeBuilderOutput,
    GeneratedCapabilityCandidate,
    SpecialistCapabilityRequest,
)
from src.domain.calculation import CalculationRecord
from src.domain.capability import (
    CapabilityBuildRecord,
    CapabilityContext,
    CapabilityDefinition,
    CapabilityGapRecord,
    CapabilityValidationRecord,
    GeneratedCapabilityRecord,
    SandboxExecutionRecord,
    ScopedCapabilityRegistration,
)
from src.domain.enums import (
    CalculationStatus,
    CapabilityBackend,
    CapabilityLifecycle,
    CapabilityScope,
    EvidenceCategory,
    EvidenceStatus,
    TaskOrigin,
    TaskStatus,
)
from src.domain.evidence import EvidenceRecord
from src.domain.task import PlannedTaskGraph, Task
from src.runtime.events import InMemoryRuntimeEventStore
from src.runtime.state import RuntimeState


class GeneratedFCFMarginCapability:
    definition = CapabilityDefinition(
        capability_id=FCF_MARGIN_CAPABILITY_ID,
        version="1.0.0-generated",
        name="Generated free cash flow margin",
        category="financial_calculation",
        backend=CapabilityBackend.GENERATED,
        input_schema={
            "operating_cash_flow": "decimal",
            "capital_expenditure": "decimal",
            "revenue": "decimal",
        },
        output_schema={"value": "decimal", "unit": "RATIO"},
        deterministic=True,
        implementation_ref="generated://BUILD-1/source.py",
    )

    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, object], CapabilityContext]] = []

    async def execute(self, inputs, context):
        self.calls.append((inputs, context))
        value = (
            Decimal(str(inputs["operating_cash_flow"]))
            + Decimal(str(inputs["capital_expenditure"]))
        ) / Decimal(str(inputs["revenue"]))
        return CalculationRecord(
            calculation_id=str(inputs["calculation_id"]),
            run_id=context.run_id,
            task_id=context.task_id,
            capability_id=FCF_MARGIN_CAPABILITY_ID,
            capability_version="1.0.0-generated",
            formula_id=FCF_MARGIN_FORMULA_ID,
            input_evidence_ids=list(context.accepted_evidence_ids),
            input_values_snapshot={
                "operating_cash_flow": str(inputs["operating_cash_flow"]),
                "capital_expenditure": str(inputs["capital_expenditure"]),
                "revenue": str(inputs["revenue"]),
            },
            output_value=value,
            output_unit="RATIO",
            status=CalculationStatus.PASS,
            implementation_hash="sha256:generated",
            source_ref="generated://BUILD-1/source.py",
            runtime_version="Python 3.11.test",
        )


class FakeGeneratedOrchestrator:
    def __init__(self, result: CapabilityOrchestrationResult) -> None:
        self.result = result
        self.requests: list[SpecialistCapabilityRequest] = []

    async def lookup_or_build(self, *, state, request):
        assert state.task(request.task_id).status is TaskStatus.RUNNING
        self.requests.append(request)
        return self.result


def _task() -> Task:
    return Task(
        task_id="RUN-1:fundamentals",
        run_id="RUN-1",
        task_type="fundamental_analysis",
        goal="Calculate accepted-evidence financial results",
        assigned_agent="fundamental_analyst",
        skill_id="fundamental_analysis_v1",
        origin=TaskOrigin.PLAN,
        status=TaskStatus.RUNNING,
    )


def _state(task: Task) -> RuntimeState:
    graph = PlannedTaskGraph(graph_id="GRAPH-1", run_id=task.run_id, tasks=[task])
    state = RuntimeState.create(run_id=task.run_id, planned_graph=graph)
    state.task(task.task_id).status = TaskStatus.RUNNING
    return state


def _record(
    *,
    evidence_id: str,
    field: str,
    value: object,
    period: str,
    as_of: date,
    category: EvidenceCategory,
    purpose: str,
    unit: str,
    currency: str | None,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id="RUN-1",
        object_id="OBJ-NVDA",
        provider="fmp",
        source_endpoint="test",
        evidence_purpose=purpose,
        evidence_category=category,
        retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
        period=period,
        as_of=as_of,
        raw_artifact_ref=f"memory://{evidence_id}",
        normalized_field=field,
        normalized_value=value,
        unit=unit,
        currency=currency,
        snapshot_hash=f"sha256:{evidence_id}",
        status=EvidenceStatus.ACCEPTED,
    )


def _evidence() -> list[EvidenceRecord]:
    records = [
        _record(
            evidence_id="E-OCF",
            field="operating_cash_flow",
            value="50",
            period="FY2026",
            as_of=date(2026, 1, 25),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="cash_flow_statement",
            unit="USD",
            currency="USD",
        ),
        _record(
            evidence_id="E-CAPEX",
            field="capital_expenditure",
            value="-10",
            period="FY2026",
            as_of=date(2026, 1, 25),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="cash_flow_statement",
            unit="USD",
            currency="USD",
        ),
        _record(
            evidence_id="E-REV",
            field="revenue",
            value="100",
            period="FY2026",
            as_of=date(2026, 1, 25),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="income_statement",
            unit="USD",
            currency="USD",
        ),
    ]
    first = date(2025, 1, 1)
    for index in range(200):
        observed = first + timedelta(days=index)
        records.extend(
            [
                _record(
                    evidence_id=f"E-CLOSE-{index:03d}",
                    field="close",
                    value=str(100 + index),
                    period="DAILY",
                    as_of=observed,
                    category=EvidenceCategory.MARKET,
                    purpose="historical_market_context",
                    unit="CURRENCY",
                    currency="USD",
                ),
                _record(
                    evidence_id=f"E-VOLUME-{index:03d}",
                    field="volume",
                    value=str(1_000_000 + index),
                    period="DAILY",
                    as_of=observed,
                    category=EvidenceCategory.MARKET,
                    purpose="historical_market_context",
                    unit="COUNT",
                    currency=None,
                ),
            ]
        )
    return list(reversed(records))


def _orchestration_result(capability) -> CapabilityOrchestrationResult:
    generated = GeneratedCapabilityRecord(
        generated_capability_id="GEN-1",
        run_id="RUN-1",
        task_id="RUN-1:fundamentals",
        gap_id="GAP-1",
        capability_id=FCF_MARGIN_CAPABILITY_ID,
        capability_version="1.0.0-generated",
        formula_id=FCF_MARGIN_FORMULA_ID,
        purpose="FCF margin",
        input_schema={
            "operating_cash_flow": "decimal",
            "capital_expenditure": "decimal",
            "revenue": "decimal",
        },
        output_schema={"value": "decimal", "unit": "RATIO"},
        formula_description="(operating_cash_flow + capital_expenditure) / revenue",
        implementation_hash="sha256:generated",
        source_ref="generated://BUILD-1/source.py",
        unit_test_ref="generated://BUILD-1/tests.py",
        allowed_imports=["decimal"],
        financial_invariants=["revenue_non_zero"],
        runtime_version="Python 3.11.test",
        lifecycle=CapabilityLifecycle.ACTIVE_FOR_SCOPE,
    )
    gap = CapabilityGapRecord(
        gap_id="GAP-1",
        run_id="RUN-1",
        task_id="RUN-1:fundamentals",
        requirement=free_cash_flow_margin_requirement(_task()),
        requested_by="fundamental_analyst",
    )
    build = CapabilityBuildRecord(
        build_id="BUILD-1",
        gap_id=gap.gap_id,
        run_id=gap.run_id,
        task_id=gap.task_id,
        requested_by=gap.requested_by,
        lifecycle=CapabilityLifecycle.ACTIVE_FOR_SCOPE,
    )
    validation = CapabilityValidationRecord(
        validation_id="VAL-1",
        build_id=build.build_id,
        implementation_hash="sha256:generated",
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
        build_id=build.build_id,
        backend="docker",
        implementation_hash="sha256:generated",
        runtime_version="Python 3.11.test",
        input_fixture_hash="sha256:fixture",
        network_disabled=True,
        read_only_root=True,
        non_root_user=True,
        resource_limits={"memory": "64m"},
        exit_code=0,
        output_hash="sha256:result",
        passed=True,
    )
    registration = ScopedCapabilityRegistration(
        registration_id="REG-1",
        generated_capability_ref=generated.generated_capability_id,
        capability_id=generated.capability_id,
        capability_version=generated.capability_version,
        scope=CapabilityScope.TASK,
        run_id=gap.run_id,
        task_id=gap.task_id,
        approved_by="research_lead",
        lifecycle=CapabilityLifecycle.ACTIVE_FOR_SCOPE,
    )
    return CapabilityOrchestrationResult(
        gap=gap,
        build_records=(build,),
        generated=generated,
        validation=validation,
        sandbox_execution=sandbox,
        registration=registration,
        capability=capability,
    )


@pytest.mark.asyncio
async def test_extension_executes_generated_gap_and_finrobot_technical_runtime() -> None:
    task = _task()
    state = _state(task)
    capability = GeneratedFCFMarginCapability()
    generated = FakeGeneratedOrchestrator(_orchestration_result(capability))
    events = InMemoryRuntimeEventStore()
    extension = Phase3FinancialCapabilityExtension(
        generated=generated,  # type: ignore[arg-type]
        event_store=events,
    )

    evidence = _evidence()
    result = await extension.execute(
        task=state.task(task.task_id),
        state=state,
        evidence=evidence,
        context=CapabilityContext(
            run_id="RUN-1",
            task_id=task.task_id,
            accepted_evidence_ids=[record.evidence_id for record in evidence],
        ),
    )

    assert len(result.calculations) == 8
    assert result.generated_capability_refs == ["GEN-1"]
    assert result.calculations[0].output_value == Decimal("0.4")
    assert result.calculations[0].input_evidence_ids == ["E-OCF", "E-CAPEX", "E-REV"]
    assert {item.capability_id for item in result.calculations[1:]} == {
        "technical_sma_50",
        "technical_sma_200",
        "technical_rsi_14",
        "technical_macd_12_26_9",
        "technical_volume_ratio_20",
    }
    assert len(result.judgments) == 2
    assert all(item["requires_review"] is True for item in result.judgments)
    assert generated.requests[0].scope is CapabilityScope.TASK
    assert generated.requests[0].requirement.capability_id == FCF_MARGIN_CAPABILITY_ID
    assert len(capability.calls) == 1
    emitted = await events.replay("RUN-1")
    started = [event for event in emitted if event.type.value == "calculation.started"]
    assert len(started) == 6


@pytest.mark.asyncio
async def test_research_lead_authority_rejects_mutated_spec() -> None:
    task = _task()
    valid = free_cash_flow_margin_requirement(task)
    gap = CapabilityGapRecord(
        gap_id="GAP-1",
        run_id=task.run_id,
        task_id=task.task_id,
        requirement=valid.model_copy(update={"formula_id": "unapproved_formula"}),
        requested_by=task.assigned_agent,
    )

    decision = await Phase3ResearchLeadCapabilityAuthority().approve_spec(gap)

    assert decision.approved is False
    assert decision.authority_role == "RESEARCH_LEAD"


@pytest.mark.asyncio
async def test_extension_rejects_evidence_outside_task_context_before_build() -> None:
    task = _task()
    state = _state(task)
    generated = FakeGeneratedOrchestrator(_orchestration_result(GeneratedFCFMarginCapability()))
    evidence = _evidence()
    extension = Phase3FinancialCapabilityExtension(
        generated=generated,  # type: ignore[arg-type]
        event_store=InMemoryRuntimeEventStore(),
    )

    with pytest.raises(ValueError, match="allowlist"):
        await extension.execute(
            task=state.task(task.task_id),
            state=state,
            evidence=evidence,
            context=CapabilityContext(
                run_id="RUN-1",
                task_id=task.task_id,
                accepted_evidence_ids=[record.evidence_id for record in evidence[:-1]],
            ),
        )

    assert generated.requests == []


def test_owned_validation_plan_checks_exact_financial_formula() -> None:
    candidate = GeneratedCapabilityCandidate(
        build_id="BUILD-1",
        output=CodeBuilderOutput(
            capability_id=FCF_MARGIN_CAPABILITY_ID,
            version="1.0.0-generated",
            purpose="FCF margin",
            input_schema={
                "operating_cash_flow": "decimal",
                "capital_expenditure": "decimal",
                "revenue": "decimal",
            },
            output_schema={"value": "decimal", "unit": "RATIO"},
            formula_id=FCF_MARGIN_FORMULA_ID,
            formula_description="(operating cash flow + signed capex) / revenue",
            source_code="def execute(inputs): return {'value': '0.5', 'unit': 'RATIO'}",
            unit_tests="def run_tests(execute, inputs): return None",
            financial_invariants=[
                "revenue_non_zero",
                "result_is_finite",
                "result_between_minus_one_and_one",
            ],
            allowed_imports=[],
        ),
        implementation_hash="sha256:source",
        provider="teamorouter",
        requested_model="model-a",
        actual_model="model-a",
        attempted_models=("model-a",),
        input_tokens=1,
        output_tokens=1,
        latency_ms=1,
    )
    plan = FreeCashFlowMarginValidationPlanProvider().plan_for(candidate)

    plan.financial_policy.validate(
        candidate,
        plan.primary_fixture,
        {"value": "0.5", "unit": "RATIO"},
    )
    with pytest.raises(ValueError, match="owned free cash flow margin oracle"):
        plan.financial_policy.validate(
            candidate,
            plan.primary_fixture,
            {"value": "0.6", "unit": "RATIO"},
        )
