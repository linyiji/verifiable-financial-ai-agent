from decimal import Decimal, localcontext

from src.capabilities.financial.common import (
    PeriodMismatchError,
    ZeroDenominatorError,
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


def calculate_revenue_growth(prior_revenue: Decimal, current_revenue: Decimal) -> Decimal:
    if prior_revenue == 0:
        raise ZeroDenominatorError("prior revenue must not be zero")
    with localcontext() as context:
        context.prec = 28
        return (current_revenue - prior_revenue) / abs(prior_revenue)


class RevenueGrowthCapability:
    definition = CapabilityDefinition(
        capability_id="revenue_growth",
        version="1.0.0",
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
        value = calculate_revenue_growth(
            decimal_value(prior.normalized_value), decimal_value(current.normalized_value)
        )
        provenance = calculation_source_provenance(
            __file__, source_ref=self.definition.implementation_ref
        )
        return CalculationRecord(
            calculation_id=str(inputs["calculation_id"]),
            run_id=context.run_id,
            task_id=context.task_id,
            capability_id=self.definition.capability_id,
            capability_version=self.definition.version,
            formula_id="revenue_growth_v1",
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
            output_value=value,
            output_unit="ratio",
            status=CalculationStatus.PASS,
            implementation_hash=provenance.code_hash,
            code_hash=provenance.code_hash,
            source_ref=provenance.source_ref,
            runtime_version=provenance.runtime_version,
        )
