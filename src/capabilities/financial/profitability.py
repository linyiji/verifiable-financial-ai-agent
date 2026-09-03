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
        if ebitda.period != revenue.period:
            raise PeriodMismatchError("EBITDA and revenue periods must match")
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
            },
            output_value=value,
            output_unit="ratio",
            status=CalculationStatus.PASS,
            code_hash=provenance.code_hash,
            source_ref=provenance.source_ref,
            runtime_version=provenance.runtime_version,
        )
