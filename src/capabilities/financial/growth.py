from decimal import Decimal

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
from src.domain.enums import CalculationStatus, CapabilityBackend
from src.domain.evidence import EvidenceRecord


def calculate_revenue_growth(prior_revenue: Decimal, current_revenue: Decimal) -> Decimal:
    if prior_revenue == 0:
        raise ZeroDenominatorError("prior revenue must not be zero")
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
        if prior.period == current.period:
            raise PeriodMismatchError("prior and current revenue periods must differ")
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
            },
            output_value=value,
            output_unit="ratio",
            status=CalculationStatus.PASS,
            code_hash=provenance.code_hash,
            source_ref=provenance.source_ref,
            runtime_version=provenance.runtime_version,
        )
