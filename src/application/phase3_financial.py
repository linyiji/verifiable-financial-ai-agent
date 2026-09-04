from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

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
    ResearchLeadCapabilityApproval,
    SpecialistCapabilityRequest,
)
from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
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
from src.runtime.events import RuntimeEventStore
from src.runtime.state import RuntimeState
from src.tooling.native import NativeToolBackend
from src.tooling.runtime import ToolRuntime

FCF_MARGIN_CAPABILITY_ID = "free_cash_flow_margin"
FCF_MARGIN_FORMULA_ID = "free_cash_flow_divided_by_revenue_v1"
TECHNICAL_SKILL_VERSION = "finrobot-technical-owned-port@1.0.0"


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
    ) -> None:
        self._generated = generated
        self._event_store = event_store
        self._technical_runtime = technical_runtime or _technical_runtime()
        self._judgments = TechnicalIndicatorJudgmentService()

    async def execute(
        self,
        *,
        task: Task,
        state: RuntimeState,
        evidence: list[EvidenceRecord],
        context: CapabilityContext,
    ) -> TaskCalculationExtensionResult:
        del context
        free_cash_flow, revenue = _select_fcf_margin_inputs(evidence)
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
            accepted_evidence_ids=[free_cash_flow.evidence_id, revenue.evidence_id],
        )
        await self._calculation_started(task, FCF_MARGIN_CAPABILITY_ID)
        generated_calculation = await generated_capability.execute(
            {
                "free_cash_flow": str(free_cash_flow.normalized_value),
                "revenue": str(revenue.normalized_value),
                "calculation_id": f"CALC-{task.run_id}-FCF-MARGIN-GENERATED",
            },
            generated_context,
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
            value = await self._technical_runtime.execute(
                capability_id,
                {
                    "history": history,
                    "calculation_id": f"CALC-{task.run_id}-{capability_id.upper()}",
                },
                technical_context,
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
            self._judgments.rsi(rsi, skill_version=TECHNICAL_SKILL_VERSION).model_dump(mode="json"),
            self._judgments.macd(
                macd[0], macd[1], skill_version=TECHNICAL_SKILL_VERSION
            ).model_dump(mode="json"),
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


def free_cash_flow_margin_requirement(task: Task) -> CapabilityRequirement:
    return CapabilityRequirement(
        requirement_id=f"REQ-{task.run_id}-FCF-MARGIN",
        capability_id=FCF_MARGIN_CAPABILITY_ID,
        purpose=(
            "Calculate free cash flow margin as accepted annual free cash flow divided "
            "by accepted period-aligned annual revenue. Return a ratio, not a percentage."
        ),
        input_schema={"free_cash_flow": "decimal", "revenue": "decimal"},
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
) -> tuple[EvidenceRecord, EvidenceRecord]:
    accepted = [record for record in evidence if record.status is EvidenceStatus.ACCEPTED]
    cash_flows = sorted(
        (
            record
            for record in accepted
            if record.normalized_field == "provider_reference_free_cash_flow"
            and record.period.startswith("FY")
        ),
        key=lambda record: (record.as_of, record.period, record.evidence_id),
        reverse=True,
    )
    for free_cash_flow in cash_flows:
        revenues = sorted(
            (
                record
                for record in accepted
                if record.normalized_field == "revenue"
                and record.period == free_cash_flow.period
                and record.currency == free_cash_flow.currency
            ),
            key=lambda record: (record.as_of, record.evidence_id),
            reverse=True,
        )
        if revenues:
            return free_cash_flow, revenues[0]
    raise LookupError("accepted period-aligned annual free cash flow and revenue are required")


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
        and requirement.input_schema == {"free_cash_flow": "decimal", "revenue": "decimal"}
        and requirement.output_schema == {"value": "decimal", "unit": "RATIO"}
        and set(requirement.allowed_imports).issubset({"decimal"})
        and set(requirement.financial_invariants)
        == {
            "revenue_non_zero",
            "result_is_finite",
            "result_between_minus_one_and_one",
        }
    )


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
