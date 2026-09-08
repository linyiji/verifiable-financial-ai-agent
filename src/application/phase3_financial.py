from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from src.adapters.finrobot.technical import (
    MACD12269Capability,
    RSI14Capability,
    SMA50Capability,
    SMA200Capability,
    TechnicalIndicatorJudgmentService,
    VolumeRatio20Capability,
)
from src.application.extensions import TaskCalculationExtensionResult
from src.capabilities.financial.common import PeriodMismatchError
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
    CashFlowSignConvention,
    EvidenceCategory,
    EvidenceStatus,
    FinancialActuality,
    FinancialPeriodBasis,
    FinancialUnit,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_branch import BranchRequirement, BranchStatus, FinancialBranchResult
from src.domain.financial_semantics import evidence_unit_class
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task
from src.observability.instrumentation import RuntimeInstrumentation
from src.runtime.diagnostics import InsufficientTechnicalHistoryError
from src.runtime.events import RuntimeEventStore
from src.runtime.financial_branches import FinancialBranch, execute_financial_branches
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
                {
                    "operating_cash_flow": "37.12345678901234567890123456",
                    "capital_expenditure": "-11.00000000000000000000000001",
                    "revenue": "97.33333333333333333333333333",
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

    async def execute(self, *, task, state, evidence, context):
        return await self.execute_incremental(
            task=task, state=state, evidence=evidence, context=context
        )

    async def execute_incremental(
        self, *, task, state, evidence, context, commit=None, publish=None, requirements=None
    ):
        _validate_extension_evidence(task, evidence, context)
        history = _ordered_historical_evidence(evidence, minimum=0)
        grouped = {}
        for item in history:
            grouped.setdefault(item.as_of, set()).add(
                "close" if item.normalized_field == "adjusted_close" else item.normalized_field
            )
        available = sum({"close", "volume"} <= fields for fields in grouped.values())
        requirements = requirements or {}
        parts = {}
        outcomes = []
        thresholds = {
            FCF_MARGIN_CAPABILITY_ID: 3,
            "technical_sma_50": 50,
            "technical_sma_200": 200,
            "technical_rsi_14": 15,
            "technical_macd_12_26_9": 34,
            "technical_volume_ratio_20": 20,
        }

        async def record(outcome):
            outcomes.append(outcome)
            await self._event_store.emit(
                run_id=task.run_id,
                task_id=task.task_id,
                event_type=RuntimeEventType.TASK_PROGRESS,
                payload={
                    "progress": 0.5,
                    "stage": (
                        f"{outcome.calculation_type}:{outcome.status.value}:"
                        f"{outcome.available_inputs}/{outcome.required_inputs}"
                    ),
                    "message_code": (
                        f"FINANCIAL_BRANCH:{outcome.calculation_type}:{outcome.status.value}:"
                        f"{outcome.available_inputs}/{outcome.required_inputs}:"
                        f"{outcome.reason_code or 'NONE'}"
                    ),
                    "financial_branch": outcome.model_dump(mode="json"),
                },
            )
            if publish is not None:
                await publish(outcome)

        def make_branch(capability_id, minimum):
            alignment_error = None
            required = requirements.get(capability_id, BranchRequirement.SUPPORTING)
            if capability_id == FCF_MARGIN_CAPABILITY_ID:
                required = requirements.get(capability_id, BranchRequirement.REQUIRED)
                try:
                    _select_fcf_margin_inputs(evidence)
                    count = 3
                except LookupError:
                    count = 0
                except PeriodMismatchError as error:
                    count, alignment_error = 3, error
            else:
                count = available
            identity = FinancialBranchResult(
                branch_id=f"BRANCH-{task.task_id}-{capability_id}",
                run_id=task.run_id,
                task_id=task.task_id,
                calculation_type=capability_id,
                requirement=required,
                status=BranchStatus.NOT_APPLICABLE,
                required_inputs=minimum,
                available_inputs=count,
            )

            async def execute():
                if alignment_error is not None:
                    await self._event_store.emit(
                        run_id=task.run_id,
                        task_id=task.task_id,
                        event_type=RuntimeEventType.TASK_SELF_CORRECTING,
                        payload={"problem_code": "PERIOD_MISMATCH", "error": "PeriodMismatchError"},
                    )
                    # All accepted candidates were searched. No aligned replacement:
                    # leave correction unresolved and require corrected evidence.
                    raise alignment_error
                if count < minimum:
                    return identity.model_copy(
                        update={
                            "status": BranchStatus.INSUFFICIENT_DATA,
                            "reason_code": (
                                "INSUFFICIENT_FINANCIAL_INPUTS"
                                if capability_id == FCF_MARGIN_CAPABILITY_ID
                                else "INSUFFICIENT_TECHNICAL_HISTORY"
                            ),
                            "diagnostic_id": f"DIAG-{identity.branch_id}",
                        }
                    )
                if capability_id == FCF_MARGIN_CAPABILITY_ID:
                    part = await self._execute_fcf(
                        task=task, state=state, evidence=evidence, context=context
                    )
                else:
                    part = await self._execute_technical(
                        task=task, capability_id=capability_id, history=history
                    )
                # A sibling is not permitted to delay persistence of this validated result.
                if commit is not None:
                    await commit(part)
                parts[capability_id] = part
                return identity.model_copy(
                    update={
                        "status": BranchStatus.COMPLETED,
                        "calculation_ids": [item.calculation_id for item in part.calculations],
                    }
                )

            return FinancialBranch(identity=identity, execute=execute)

        ordered = await execute_financial_branches(
            [make_branch(key, minimum) for key, minimum in thresholds.items()],
            publish=record,
            concurrency=3,
        )
        result = TaskCalculationExtensionResult(branch_results=ordered)
        for key in thresholds:
            if key not in parts:
                continue
            part = parts[key]
            result.calculations.extend(part.calculations)
            result.generated_capability_refs.extend(part.generated_capability_refs)
            result.judgments.extend(part.judgments)
            result.task_output.update(part.task_output)
        result.task_output["financial_branches"] = [
            item.model_dump(mode="json") for item in ordered
        ]
        return result

    async def _execute_technical(self, *, task, capability_id, history):
        await self._calculation_started(task, capability_id)
        calculation_id = f"CALC-{task.run_id}-{capability_id.upper()}"
        context = CapabilityContext(
            run_id=task.run_id,
            task_id=task.task_id,
            accepted_evidence_ids=[item.evidence_id for item in history],
        )
        value = await self._execute_capability(
            task=task,
            capability_id=capability_id,
            backend="finrobot_owned_native_port",
            calculation_id=calculation_id,
            execute=lambda: self._technical_runtime.execute(
                capability_id, {"history": history, "calculation_id": calculation_id}, context
            ),
        )
        records = list(value) if isinstance(value, tuple) else [value]
        if not all(isinstance(item, CalculationRecord) for item in records):
            raise TypeError("technical capability must return CalculationRecord values")
        judgments = []
        if capability_id == "technical_rsi_14":
            judgments.append(
                self._judgments.rsi(records[0], skill_version=task.skill_id).model_dump(mode="json")
            )
        if capability_id == "technical_macd_12_26_9":
            judgments.append(
                self._judgments.macd(
                    records[0], records[1], skill_version=task.skill_id
                ).model_dump(mode="json")
            )
        return TaskCalculationExtensionResult(calculations=records, judgments=judgments)

    async def _execute_fcf(
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
            expected_implementation_hash = resolved.generated.implementation_hash
            expected_source_ref = resolved.generated.source_ref
            expected_tests_hash = resolved.validation.tests_hash
        else:
            generated_capability = resolved
            generated_refs = []
            expected_implementation_hash = getattr(
                generated_capability, "implementation_hash", None
            )
            expected_source_ref = getattr(generated_capability, "source_ref", None)
            expected_tests_hash = getattr(generated_capability, "tests_hash", None)
        if not expected_implementation_hash or not expected_source_ref:
            raise ValueError("generated capability lacks immutable source identity")

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
        generated_calculation = _validate_live_fcf_calculation(
            generated_calculation,
            operating_cash_flow=operating_cash_flow,
            capital_expenditure=capital_expenditure,
            revenue=revenue,
            expected_implementation_hash=str(expected_implementation_hash),
            expected_source_ref=str(expected_source_ref),
            expected_tests_hash=(
                str(expected_tests_hash) if expected_tests_hash is not None else None
            ),
        )

        return TaskCalculationExtensionResult(
            calculations=[generated_calculation],
            generated_capability_refs=generated_refs,
            task_output={"free_cash_flow_margin": str(generated_calculation.output_value)},
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
            if record.normalized_field == "operating_cash_flow"
            and record.period_basis is FinancialPeriodBasis.FY
            and record.actuality in {FinancialActuality.ACTUAL, FinancialActuality.ESTIMATE}
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
                and record.object_id == operating_cash_flow.object_id
                and record.as_of == operating_cash_flow.as_of
                and record.period_basis is operating_cash_flow.period_basis
                and record.actuality is operating_cash_flow.actuality
                and record.statement_cohort == operating_cash_flow.statement_cohort
                and record.cash_flow_sign_convention is CashFlowSignConvention.OUTFLOW_NEGATIVE
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
                and record.object_id == operating_cash_flow.object_id
                and record.as_of == operating_cash_flow.as_of
                and record.period_basis is operating_cash_flow.period_basis
                and record.actuality is operating_cash_flow.actuality
                and record.statement_cohort == operating_cash_flow.statement_cohort
            ),
            key=lambda record: (record.as_of, record.evidence_id),
            reverse=True,
        )
        if (
            capital_expenditures
            and revenues
            and all(
                evidence_unit_class(record.unit, record.currency) is FinancialUnit.CURRENCY
                for record in (operating_cash_flow, capital_expenditures[0], revenues[0])
            )
            and Decimal(str(capital_expenditures[0].normalized_value)) <= 0
        ):
            return operating_cash_flow, capital_expenditures[0], revenues[0]
    fields = {record.normalized_field for record in accepted}
    if {"operating_cash_flow", "capital_expenditure", "revenue"}.issubset(fields):
        periods = [
            {(e.period, e.period_basis) for e in accepted if e.normalized_field == field}
            for field in ("operating_cash_flow", "capital_expenditure", "revenue")
        ]
        if not set.intersection(*periods):
            raise PeriodMismatchError("Financial periods require correction and revalidation")
        raise ValueError("Financial cohort/currency/authority/sign integrity mismatch")
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
    *,
    minimum: int = 200,
) -> list[EvidenceRecord]:
    field_order = {"adjusted_close": 0, "close": 1, "volume": 2}
    candidates = sorted(
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
    grouped: dict[object, dict[str, EvidenceRecord]] = {}
    for record in candidates:
        fields = grouped.setdefault(record.as_of, {})
        if record.normalized_field == "adjusted_close":
            fields["close"] = record
        elif record.normalized_field == "close":
            fields.setdefault("close", record)
        else:
            fields["volume"] = record
    history = [
        record
        for observed in sorted(grouped)
        for key in ("close", "volume")
        if (record := grouped[observed].get(key)) is not None
    ]
    paired_days = sum("close" in fields and "volume" in fields for fields in grouped.values())
    if paired_days < minimum:
        raise InsufficientTechnicalHistoryError(paired_days)
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
        }
    )


def _validate_free_cash_flow_margin_output(
    candidate: GeneratedCapabilityCandidate,
    inputs: JsonObject,
    output: Any,
) -> JsonObject:
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
    return {"value": str(expected), "unit": "RATIO"}


def _validate_live_fcf_calculation(
    calculation: CalculationRecord,
    *,
    operating_cash_flow: EvidenceRecord,
    capital_expenditure: EvidenceRecord,
    revenue: EvidenceRecord,
    expected_implementation_hash: str,
    expected_source_ref: str,
    expected_tests_hash: str | None,
) -> CalculationRecord:
    if (
        calculation.capability_id != FCF_MARGIN_CAPABILITY_ID
        or calculation.formula_id != FCF_MARGIN_FORMULA_ID
        or calculation.output_unit.upper() != "RATIO"
        or calculation.implementation_hash != expected_implementation_hash
        or calculation.source_ref != expected_source_ref
    ):
        raise ValueError("generated FCF calculation identity is not release eligible")
    if (
        expected_tests_hash is not None
        and calculation.parameters.get("generated_tests_hash") != expected_tests_hash
    ):
        raise ValueError("generated FCF tests hash differs from approved validation")
    expected_evidence_ids = [
        operating_cash_flow.evidence_id,
        capital_expenditure.evidence_id,
        revenue.evidence_id,
    ]
    if calculation.input_evidence_ids != expected_evidence_ids:
        raise ValueError("generated FCF calculation evidence lineage differs from live inputs")
    try:
        operating = Decimal(str(operating_cash_flow.normalized_value))
        capex = Decimal(str(capital_expenditure.normalized_value))
        denominator = Decimal(str(revenue.normalized_value))
        actual = Decimal(str(calculation.output_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("generated FCF live values must be decimal-compatible") from exc
    if denominator == 0:
        raise ValueError("generated FCF revenue must not be zero")
    expected = (operating + capex) / denominator
    if actual != expected:
        raise ValueError("generated FCF runtime output failed the owned live oracle")
    parameters = {
        **calculation.parameters,
        "validation_scope": "LIVE_RUNTIME",
        "owned_oracle_result": {"value": str(expected), "unit": "RATIO"},
        "runtime_result": {"value": str(actual), "unit": "RATIO"},
        "financial_validation_result": "PASS",
        "capital_expenditure_sign_convention": CashFlowSignConvention.OUTFLOW_NEGATIVE.value,
        "statement_cohort": revenue.statement_cohort,
        "period": revenue.period,
        "period_basis": revenue.period_basis.value if revenue.period_basis else None,
        "actuality": revenue.actuality.value,
        "as_of": revenue.as_of.isoformat(),
        "currency": revenue.currency,
    }
    return calculation.model_copy(update={"parameters": parameters})


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
