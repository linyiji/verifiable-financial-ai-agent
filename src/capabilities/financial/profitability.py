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
from src.domain.enums import CalculationStatus, CapabilityBackend, FinancialUnit
from src.domain.evidence import EvidenceRecord
from src.domain.financial_semantics import evidence_unit_class


def calculate_ebitda_margin(ebitda: Decimal, revenue: Decimal) -> Decimal:
    if revenue == 0:
        raise ZeroDenominatorError("revenue must not be zero")
    return ebitda / revenue


class EbitdaMarginCapability:
    definition = CapabilityDefinition(
        capability_id="ebitda_margin",
        version="1.0.0",
        name="EBITDA Margin",
        category="financial_calculation",
        backend=CapabilityBackend.NATIVE,
        input_schema={"ebitda": "EvidenceRecord", "revenue": "EvidenceRecord"},
        output_schema={"calculation": "CalculationRecord"},
        deterministic=True,
        proof_eligible=True,
        implementation_ref="src.capabilities.financial.profitability:EbitdaMarginCapability",
    )

    async def execute(self, inputs: JsonObject, context: CapabilityContext) -> CalculationRecord:
        ebitda = require_accepted(inputs["ebitda"])
        revenue = require_accepted(inputs["revenue"])
        if not isinstance(ebitda, EvidenceRecord) or not isinstance(revenue, EvidenceRecord):
            raise TypeError("ebitda and revenue inputs must be EvidenceRecord")
        if ebitda.normalized_field != "ebitda" or revenue.normalized_field != "revenue":
            raise ValueError("ebitda_margin requires EBITDA and revenue evidence")
        if ebitda.run_id != revenue.run_id or ebitda.object_id != revenue.object_id:
            raise ValueError("ebitda_margin requires one run and research object")
        if ebitda.period != revenue.period:
            raise PeriodMismatchError("EBITDA and revenue periods must match")
        if ebitda.period_basis is not revenue.period_basis:
            raise PeriodMismatchError("EBITDA and revenue period basis must match")
        if ebitda.actuality is not revenue.actuality:
            raise ValueError("EBITDA and revenue actual/estimate basis must match")
        if ebitda.as_of != revenue.as_of or ebitda.statement_cohort != revenue.statement_cohort:
            raise ValueError("EBITDA and revenue statement cohort must match")
        if (
            evidence_unit_class(ebitda.unit, ebitda.currency) is not FinancialUnit.CURRENCY
            or evidence_unit_class(revenue.unit, revenue.currency) is not FinancialUnit.CURRENCY
        ):
            raise ValueError("ebitda_margin requires CURRENCY evidence")
        if not ebitda.currency or ebitda.currency != revenue.currency:
            raise ValueError("EBITDA and revenue currency must match")
        value = calculate_ebitda_margin(
            decimal_value(ebitda.normalized_value), decimal_value(revenue.normalized_value)
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
            formula_id="ebitda_margin_v1",
            input_evidence_ids=[ebitda.evidence_id, revenue.evidence_id],
            input_values_snapshot={
                "ebitda": str(ebitda.normalized_value),
                "revenue": str(revenue.normalized_value),
                "currency": revenue.currency,
                "period": revenue.period,
                "period_basis": revenue.period_basis.value if revenue.period_basis else None,
                "actuality": revenue.actuality.value,
                "statement_cohort": revenue.statement_cohort,
            },
            output_value=value,
            output_unit="ratio",
            status=CalculationStatus.PASS,
            implementation_hash=provenance.code_hash,
            code_hash=provenance.code_hash,
            source_ref=provenance.source_ref,
            runtime_version=provenance.runtime_version,
        )
