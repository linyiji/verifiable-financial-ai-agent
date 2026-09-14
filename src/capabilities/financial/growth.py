from decimal import Decimal, localcontext

from src.capabilities.financial.common import (
    NonPositivePriorRevenueError,
    PeriodMismatchError,
    decimal_value,
    require_accepted,
)
from src.capabilities.provenance import calculation_source_provenance
from src.domain.base import JsonObject
from src.domain.calculation import CalculationRecord
from src.domain.capability import CapabilityContext, CapabilityDefinition
from src.domain.enums import (
    CalculationStatus,
    CapabilityBackend,
    FinancialPeriodBasis,
    FinancialUnit,
)
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import adjacent_financial_periods, evidence_unit_class
from src.domain.financial_validation import (
    REVENUE_GROWTH_FORMULA_EXPRESSION,
    REVENUE_GROWTH_FORMULA_ID,
    REVENUE_GROWTH_PRECONDITION,
    REVENUE_GROWTH_VALIDATION_REASON,
)



# Ephemeral observation only. A ContextVar handle carries no process-wide result.
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar

from src.domain.financial_validation import (
    MethodDenied, WP04_FLAGS_SCHEMA, validate_decimal_observation, wp04_flags,
)


class _GrowthObservation:
    def __init__(self, identity):
        self.owner = asyncio.current_task()
        if self.owner is None:
            raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
        self.identity = tuple(identity)
        self.closed = False
        self.armed = False
        self.invalid = False
        self.count = 0
        self.flags = None

    def check(self):
        # Inherited child contexts must not mutate their parent's collector.
        if asyncio.current_task() is not self.owner or self.closed:
            raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')

    def arm(self, context, inputs):
        self.check()
        prior, current = inputs['prior'], inputs['current']
        observed = (context.run_id, context.task_id, str(inputs['calculation_id']),
                    prior.evidence_id, current.evidence_id,
                    str(prior.normalized_value), str(current.normalized_value))
        if self.armed or observed != self.identity[:7]:
            self.invalid = True
            raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
        self.armed = True

    def capture(self, prior, current, context):
        self.check()
        if (not self.armed or (str(prior), str(current)) != self.identity[5:7]):
            self.invalid = True
            raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
        self.count += 1
        if self.count == 1:
            self.flags = wp04_flags(context)

    def seal(self):
        self.check()
        self.closed = True
        if self.invalid:
            raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
        receipt = {'schema_version': WP04_FLAGS_SCHEMA, 'capture_count': self.count,
                   'flags': dict(self.flags) if self.flags is not None else None}
        validate_decimal_observation(receipt)
        return receipt


_growth_observer = ContextVar('wp04_growth_observer', default=None)


@contextmanager
def capture_revenue_growth_decimal_observation(identity):
    previous = _growth_observer.get()
    if previous is not None:
        previous.check()
        previous.invalid = True
        raise MethodDenied('DECIMAL_FLAGS_OBSERVATION_ERROR', 'SUPPORTED', 'FAILED')
    collector = _GrowthObservation(identity)
    token = _growth_observer.set(collector)
    try:
        yield collector
    finally:
        collector.closed = True
        _growth_observer.reset(token)


def calculate_revenue_growth(prior_revenue: Decimal, current_revenue: Decimal) -> Decimal:
    if prior_revenue <= 0:
        raise NonPositivePriorRevenueError(REVENUE_GROWTH_VALIDATION_REASON)
    with localcontext() as context:
        context.prec = 28
        result = (current_revenue - prior_revenue) / prior_revenue
        observer = _growth_observer.get()
        if observer is not None:
            observer.capture(prior_revenue, current_revenue, context)
        return result


class RevenueGrowthCapability:
    definition = CapabilityDefinition(
        capability_id="revenue_growth",
        version="1.1.0",
        name="Revenue Growth",
        category="financial_calculation",
        backend=CapabilityBackend.NATIVE,
        input_schema={"prior": "EvidenceRecord", "current": "EvidenceRecord"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        proof_eligible=True,
        implementation_ref="src.capabilities.financial.growth:RevenueGrowthCapability",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        prior = require_accepted(inputs["prior"])
        current = require_accepted(inputs["current"])
        if not isinstance(prior, EvidenceRecord) or not isinstance(current, EvidenceRecord):
            raise TypeError("prior and current inputs must be EvidenceRecord")
        if prior.normalized_field != "revenue" or current.normalized_field != "revenue":
            raise ValueError("revenue_growth requires revenue evidence")
        if prior.run_id != current.run_id or prior.object_id != current.object_id:
            raise ValueError("revenue_growth requires one run and research object")
        if (
            prior.period_basis is not FinancialPeriodBasis.FY
            or current.period_basis is not FinancialPeriodBasis.FY
        ):
            raise PeriodMismatchError("revenue_growth YoY requires two fiscal-year periods")
        if not adjacent_financial_periods(prior.period, current.period):
            raise PeriodMismatchError("revenue_growth YoY requires adjacent fiscal years")
        if prior.actuality is not current.actuality:
            raise ValueError("revenue_growth requires compatible actual/estimate basis")
        if not prior.statement_series or prior.statement_series != current.statement_series:
            raise ValueError("revenue_growth requires one comparable statement series")
        if (
            evidence_unit_class(prior.unit, prior.currency) is not FinancialUnit.CURRENCY
            or evidence_unit_class(current.unit, current.currency) is not FinancialUnit.CURRENCY
        ):
            raise ValueError("revenue_growth requires CURRENCY evidence")
        if not prior.currency or prior.currency != current.currency:
            raise ValueError("revenue_growth requires one explicit, consistent currency")
        observer = _growth_observer.get()
        if observer is not None:
            observer.arm(context, inputs)
        try:
            value = calculate_revenue_growth(
                decimal_value(prior.normalized_value), decimal_value(current.normalized_value)
            )
        finally:
            if observer is not None:
                observer.check()
                observer.armed = False
        provenance = calculation_source_provenance(
            __file__, source_ref=self.definition.implementation_ref
        )
        return CalculationRecord(
            calculation_id=str(inputs["calculation_id"]),
            run_id=context.run_id,
            task_id=context.task_id,
            capability_id=self.definition.capability_id,
            capability_version=self.definition.version,
            formula_id=REVENUE_GROWTH_FORMULA_ID,
            input_evidence_ids=[prior.evidence_id, current.evidence_id],
            input_values_snapshot={
                "prior_revenue": str(prior.normalized_value),
                "current_revenue": str(current.normalized_value),
                "currency": prior.currency,
                "prior_period": prior.period,
                "current_period": current.period,
                "period_basis": current.period_basis.value,
                "actuality": current.actuality.value,
                "statement_series": current.statement_series,
            },
            parameters={
                "formula_expression": REVENUE_GROWTH_FORMULA_EXPRESSION,
                "semantic_precondition": REVENUE_GROWTH_PRECONDITION,
                "financial_validation_reason": REVENUE_GROWTH_VALIDATION_REASON,
            },
            output_value=value,
            output_unit="ratio",
            status=CalculationStatus.PASS,
            implementation_hash=provenance.code_hash,
            code_hash=provenance.code_hash,
            source_ref=provenance.source_ref,
            runtime_version=provenance.runtime_version,
        )
