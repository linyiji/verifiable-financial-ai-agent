from enum import StrEnum

from src.domain.calculation import CalculationRecord


class ProofRequirement(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    MUST_PROVE = "MUST_PROVE"


class ProofPolicy:
    def __init__(self, *, require_material_calculations: bool = False):
        self._require_material_calculations = require_material_calculations

    def requirement_for(self, calculation: CalculationRecord) -> ProofRequirement:
        if self._require_material_calculations and calculation.formula_id in {
            "revenue_growth_v1",
            "numeric_consistency_v1",
        }:
            return ProofRequirement.MUST_PROVE
        return ProofRequirement.NOT_REQUIRED

