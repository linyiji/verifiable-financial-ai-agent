from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from src.adapters.finrobot.technical import (
    MACD12269Capability,
    RSI14Capability,
    SMA50Capability,
    SMA200Capability,
    TechnicalIndicatorJudgmentService,
    VolumeRatio20Capability,
)
from src.application.extensions import TaskCalculationExtensionResult
from src.capabilities.generated.models import (
    CapabilityOrchestrationResult,
    GeneratedCapabilityCandidate,
    ResearchLeadCapabilityApproval,
    SpecialistCapabilityRequest,
)
from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
from src.capabilities.generated.validation import (
    CallableFinancialValidationPolicy,
    CapabilityValidationPlan,
)
from src.capabilities.registry import CapabilityRegistry
from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import (
    CapabilityContext,
    CapabilityGapRecord,
    CapabilityRequirement,
    CapabilityValidationRecord,
    GeneratedCapabilityRecord,
)
from src.domain.enums import (
    CapabilityBackend,
    CapabilityScope,
    EvidenceCategory,
    EvidenceStatus,
)
from src.domain.evidence import EvidenceRecord
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.observability.instrumentation import RuntimeInstrumentation
from src.runtime.events import RuntimeEventStore
from src.runtime.state import RuntimeState
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime

FCF_MARGIN_CAPABILITY_ID = "free_cash_flow_margin"
FCF_MARGIN_FORMULA_ID = "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1"


class Phase3ResearchLeadCapabilityAuthority:
    """Bounded, auditable Research Lead policy for the Phase 3 demonstration gap."""

    lead_agent_id = "research_lead"

    async def approve_spec(self, gap: CapabilityGapRecord) -> ResearchLeadCapabilityApproval:
        approved = _is_approved_fcf_margin_requirement(gap.requirement)
        return _approval(
            gap,
            phase="SPEC",
            approved=approved,
            reason_code=(
                "APPROVED_BOUNDED_DETERMINISTIC_FINANCIAL_FORMULA"
                if approved
                else "REJECTED_OUTSIDE_PHASE3_CAPABILITY_POLICY"
            ),
        )

    async def approve_activation(
        self,
        gap: CapabilityGapRecord,
        generated: GeneratedCapabilityRecord,
        validation: CapabilityValidationRecord,
    ) -> ResearchLeadCapabilityApproval:
        approved = (
            _is_approved_fcf_margin_requirement(gap.requirement)
            and generated.capability_id == FCF_MARGIN_CAPABILITY_ID
            and generated.formula_id == FCF_MARGIN_FORMULA_ID
            and generated.implementation_hash == validation.implementation_hash
            and validation.financial_validation_passed
            and validation.deterministic_double_run_passed
        )
        return _approval(
            gap,
            phase="ACTIVATION",
            approved=approved,
            reason_code=(
                "APPROVED_VALIDATED_TASK_SCOPED_CAPABILITY"
                if approved
                else "REJECTED_VALIDATION_OR_IDENTITY_MISMATCH"
            ),
        )


class FreeCashFlowMarginValidationPlanProvider:
    """Owned test fixtures and financial oracle; generated code cannot alter them."""

    def plan_for(self, candidate: GeneratedCapabilityCandidate) -> CapabilityValidationPlan:
        if (
            candidate.output.capability_id != FCF_MARGIN_CAPABILITY_ID
            or candidate.output.formula_id != FCF_MARGIN_FORMULA_ID
        ):
            raise ValueError("no approved validation plan for generated capability")
        return CapabilityValidationPlan(
            primary_fixture={
                "operating_cash_flow": "120",
                "capital_expenditure": "-20",
                "revenue": "200",
            },
            edge_case_fixtures=(
                {
                    "operating_cash_flow": "0",
                    "capital_expenditure": "0",
                    "revenue": "100",
                },
                {
                    "operating_cash_flow": "10",
                    "capital_expenditure": "-20",
                    "revenue": "100",
                },
            ),
            financial_policy=CallableFinancialValidationPolicy(
                callback=_validate_free_cash_flow_margin_output
            ),
            schema_version="free-cash-flow-margin-input/v1",
        )


class Phase3FinancialCapabilityExtension:
    """Run the Phase 3 generated margin and controlled FinRobot technical ports.

    This extension never fetches data. It consumes only accepted EvidenceRecords
    already routed to the running fundamental-analysis task.
    """

    def __init__(
        self,
        *,
        generated: GeneratedCapabilityOrchestrator,
        event_store: RuntimeEventStore,
        technical_runtime: ToolRuntime | None = None,
        instrumentation: RuntimeInstrumentation | None = None,
    ) -> None:
        self._generated = generated
        self._event_store = event_store
        self._technical_runtime = technical_runtime or _technical_runtime()
        self._instrumentation = instrumentation
        self._judgments = TechnicalIndicatorJudgmentService()

    async def execute(
        self,
        *,
        task: Task,
        state: RuntimeState,
        evidence: list[EvidenceRecord],
        context: CapabilityContext,
    ) -> TaskCalculationExtensionResult:
        _validate_extension_evidence(task, evidence, context)
        operating_cash_flow, capital_expenditure, revenue = _select_fcf_margin_inputs(evidence)
        requirement = free_cash_flow_margin_requirement(task)
        request = SpecialistCapabilityRequest(
            run_id=task.run_id,
            task_id=task.task_id,
            skill_id=task.skill_id,
            requested_by=task.assigned_agent,
            requirement=requirement,
            scope=CapabilityScope.TASK,
        )
        resolved = await self._generated.lookup_or_build(state=state, request=request)
        if isinstance(resolved, CapabilityOrchestrationResult):
            generated_capability = resolved.capability
            generated_refs = [resolved.generated.generated_capability_id]
        else:
            generated_capability = resolved
            generated_refs = []

        generated_context = CapabilityContext(
            run_id=task.run_id,
            task_id=task.task_id,
            accepted_evidence_ids=[
                operating_cash_flow.evidence_id,
                capital_expenditure.evidence_id,
                revenue.evidence_id,
            ],
        )
        await self._calculation_started(task, FCF_MARGIN_CAPABILITY_ID)
        generated_inputs = {
            "operating_cash_flow": str(operating_cash_flow.normalized_value),
            "capital_expenditure": str(capital_expenditure.normalized_value),
            "revenue": str(revenue.normalized_value),
            "calculation_id": f"CALC-{task.run_id}-FCF-MARGIN-GENERATED",
        }
        generated_calculation = await self._execute_capability(
            task=task,
            capability_id=FCF_MARGIN_CAPABILITY_ID,
            backend="generated_docker_sandbox",
            calculation_id=str(generated_inputs["calculation_id"]),
            execute=lambda: generated_capability.execute(
                generated_inputs,
                generated_context,
            ),
        )
        if not isinstance(generated_calculation, CalculationRecord):
            raise TypeError("generated financial capability must return CalculationRecord")

        history = _ordered_historical_evidence(evidence)
        technical_context = CapabilityContext(
            run_id=task.run_id,
            task_id=task.task_id,
            accepted_evidence_ids=[record.evidence_id for record in history],
        )
        technical: list[CalculationRecord] = []
        by_capability: dict[str, list[CalculationRecord]] = {}
        for capability_id in (
            "technical_sma_50",
            "technical_sma_200",
            "technical_rsi_14",
            "technical_macd_12_26_9",
            "technical_volume_ratio_20",
        ):
            await self._calculation_started(task, capability_id)
            calculation_id = f"CALC-{task.run_id}-{capability_id.upper()}"
            value = await self._execute_capability(
                task=task,
                capability_id=capability_id,
                backend="finrobot_owned_native_port",
                calculation_id=calculation_id,
                execute=lambda capability_id=capability_id, calculation_id=calculation_id: (
                    self._technical_runtime.execute(
                        capability_id,
                        {
                            "history": history,
                            "calculation_id": calculation_id,
                        },
                        technical_context,
                    )
                ),
            )
            records = list(value) if isinstance(value, tuple) else [value]
            if not all(isinstance(item, CalculationRecord) for item in records):
                raise TypeError("technical capability must return CalculationRecord values")
            typed_records = cast(list[CalculationRecord], records)
            by_capability[capability_id] = typed_records
            technical.extend(typed_records)

        rsi = by_capability["technical_rsi_14"][0]
        macd = by_capability["technical_macd_12_26_9"]
        judgments: list[JsonObject] = [
            self._judgments.rsi(rsi, skill_version=task.skill_id).model_dump(mode="json"),
            self._judgments.macd(macd[0], macd[1], skill_version=task.skill_id).model_dump(
                mode="json"
            ),
        ]
        calculations = [generated_calculation, *technical]
        return TaskCalculationExtensionResult(
            calculations=calculations,
            generated_capability_refs=generated_refs,
            judgments=judgments,
            task_output={
                "free_cash_flow_margin": str(generated_calculation.output_value),
                "technical_calculation_refs": [
                    calculation.calculation_id for calculation in technical
                ],
                "technical_judgment_refs": [str(judgment["judgment_id"]) for judgment in judgments],
            },
        )

    async def _calculation_started(self, task: Task, capability_id: str) -> None:
        await self._event_store.emit(
            run_id=task.run_id,
            task_id=task.task_id,
            event_type=RuntimeEventType.CALCULATION_STARTED,
            payload={"capability_id": capability_id},
        )

    async def _execute_capability(
        self,
        *,
        task: Task,
        capability_id: str,
        backend: str,
        calculation_id: str,
        execute: Callable[[], Awaitable[Any]],
    ) -> Any:
        if self._instrumentation is None:
            return await execute()
        async with self._instrumentation.calculation(
            run_id=task.run_id,
            task_id=task.task_id,
            attributes={
                "calculation_id": calculation_id,
                "capability": capability_id,
                "phase": "phase3",
            },
        ):
            async with self._instrumentation.tool(
                run_id=task.run_id,
                task_id=task.task_id,
                attributes={"tool_name": backend, "capability": capability_id},
            ):
                return await execute()


def free_cash_flow_margin_requirement(task: Task) -> CapabilityRequirement:
    return CapabilityRequirement(
        requirement_id=f"REQ-{task.run_id}-FCF-MARGIN",
        capability_id=FCF_MARGIN_CAPABILITY_ID,
        purpose=(
            "Calculate free cash flow margin from accepted annual operating cash flow plus "
            "signed capital expenditure, divided by accepted period-aligned annual revenue. "
            "Return a ratio, not a percentage."
        ),
        input_schema={
            "operating_cash_flow": "decimal",
            "capital_expenditure": "decimal",
            "revenue": "decimal",
        },
        output_schema={"value": "decimal", "unit": "RATIO"},
        formula_id=FCF_MARGIN_FORMULA_ID,
        deterministic=True,
        allowed_imports=["decimal"],
        financial_invariants=[
            "revenue_non_zero",
            "result_is_finite",
            "result_between_minus_one_and_one",
        ],
    )


def _technical_runtime() -> ToolRuntime:
    registry = CapabilityRegistry()
    for capability in (
        SMA50Capability(),
        SMA200Capability(),
        RSI14Capability(),
        MACD12269Capability(),
        VolumeRatio20Capability(),
    ):
        registry.register(capability)
    return ToolRuntime(
        registry,
        {CapabilityBackend.NATIVE: NativeToolBackend(registry)},
    )


def _select_fcf_margin_inputs(
    evidence: Sequence[EvidenceRecord],
) -> tuple[EvidenceRecord, EvidenceRecord, EvidenceRecord]:
    accepted = [record for record in evidence if record.status is EvidenceStatus.ACCEPTED]
    operating_cash_flows = sorted(
        (
            record
            for record in accepted
            if record.normalized_field == "operating_cash_flow" and record.period.startswith("FY")
        ),
        key=lambda record: (record.as_of, record.period, record.evidence_id),
        reverse=True,
    )
    for operating_cash_flow in operating_cash_flows:
        capital_expenditures = sorted(
            (
                record
                for record in accepted
                if record.normalized_field == "capital_expenditure"
                and record.period == operating_cash_flow.period
                and record.currency == operating_cash_flow.currency
            ),
            key=lambda record: (record.as_of, record.evidence_id),
            reverse=True,
        )
        revenues = sorted(
            (
                record
                for record in accepted
                if record.normalized_field == "revenue"
                and record.period == operating_cash_flow.period
                and record.currency == operating_cash_flow.currency
            ),
            key=lambda record: (record.as_of, record.evidence_id),
            reverse=True,
        )
        if capital_expenditures and revenues:
            return operating_cash_flow, capital_expenditures[0], revenues[0]
    raise LookupError(
        "accepted period-aligned annual operating cash flow, capital expenditure, "
        "and revenue are required"
    )


def _validate_extension_evidence(
    task: Task,
    evidence: Sequence[EvidenceRecord],
    context: CapabilityContext,
) -> None:
    if context.run_id != task.run_id or context.task_id != task.task_id:
        raise ValueError("CapabilityContext does not belong to the executing task")
    if not evidence:
        raise LookupError("Phase 3 financial extension requires routed evidence")
    object_ids = {record.object_id for record in evidence}
    if any(record.run_id != task.run_id for record in evidence) or len(object_ids) != 1:
        raise ValueError("extension evidence must belong to one run and research object")
    allowed = set(context.accepted_evidence_ids)
    if any(record.evidence_id not in allowed for record in evidence):
        raise ValueError("extension evidence is outside CapabilityContext allowlist")


def _ordered_historical_evidence(
    evidence: Sequence[EvidenceRecord],
) -> list[EvidenceRecord]:
    field_order = {"close": 0, "volume": 1}
    history = sorted(
        (
            record
            for record in evidence
            if record.status is EvidenceStatus.ACCEPTED
            and record.evidence_category is EvidenceCategory.MARKET
            and record.evidence_purpose == "historical_market_context"
            and record.period == "DAILY"
            and record.normalized_field in field_order
        ),
        key=lambda record: (
            record.as_of,
            field_order[record.normalized_field],
            record.evidence_id,
        ),
    )
    days = {record.as_of for record in history}
    if len(days) < 200:
        raise LookupError("at least 200 accepted paired historical observations are required")
    return history


def _is_approved_fcf_margin_requirement(requirement: CapabilityRequirement) -> bool:
    return (
        requirement.capability_id == FCF_MARGIN_CAPABILITY_ID
        and requirement.formula_id == FCF_MARGIN_FORMULA_ID
        and requirement.deterministic
        and requirement.input_schema
        == {
            "operating_cash_flow": "decimal",
            "capital_expenditure": "decimal",
            "revenue": "decimal",
        }
        and requirement.output_schema == {"value": "decimal", "unit": "RATIO"}
        and set(requirement.allowed_imports).issubset({"decimal"})
        and set(requirement.financial_invariants)
        == {
            "revenue_non_zero",
            "result_is_finite",
            "result_between_minus_one_and_one",
        }
    )


def _validate_free_cash_flow_margin_output(
    candidate: GeneratedCapabilityCandidate,
    inputs: JsonObject,
    output: Any,
) -> None:
    if (
        candidate.output.capability_id != FCF_MARGIN_CAPABILITY_ID
        or candidate.output.formula_id != FCF_MARGIN_FORMULA_ID
    ):
        raise ValueError("generated capability identity is not approved")
    if not isinstance(output, dict) or output.get("unit") != "RATIO":
        raise ValueError("free cash flow margin output must have RATIO unit")
    try:
        operating_cash_flow = Decimal(str(inputs["operating_cash_flow"]))
        capital_expenditure = Decimal(str(inputs["capital_expenditure"]))
        revenue = Decimal(str(inputs["revenue"]))
        actual = Decimal(str(output["value"]))
    except (KeyError, InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("free cash flow margin inputs/output must be decimal-compatible") from exc
    if not all(
        value.is_finite() for value in (operating_cash_flow, capital_expenditure, revenue, actual)
    ):
        raise ValueError("free cash flow margin inputs/output must be finite")
    if revenue == 0:
        raise ValueError("revenue must not be zero")
    expected = (operating_cash_flow + capital_expenditure) / revenue
    if actual != expected:
        raise ValueError("output does not equal the owned free cash flow margin oracle")


def _approval(
    gap: CapabilityGapRecord,
    *,
    phase: Literal["SPEC", "ACTIVATION"],
    approved: bool,
    reason_code: str,
) -> ResearchLeadCapabilityApproval:
    return ResearchLeadCapabilityApproval(
        decision_id=f"DEC-{gap.gap_id}-{phase}",
        run_id=gap.run_id,
        task_id=gap.task_id,
        gap_id=gap.gap_id,
        phase=phase,
        approved=approved,
        approved_by="research_lead",
        reason_code=reason_code,
        summary=(
            "Research Lead approved the bounded Phase 3 generated capability."
            if approved
            else "Research Lead rejected a capability outside the bounded Phase 3 policy."
        ),
    )
