from decimal import Decimal

import pytest

from src.domain.calculation import CalculationRecord
from src.domain.enums import CalculationStatus
from src.output.calculation_taxonomy import (
    FUNDAMENTAL_FORMULAS,
    TECHNICAL_FORMULAS,
    partition_material_calculation_refs,
)
from src.output.financial_metrics import MATERIAL_FORMULAS


def _calculation(formula_id: str, index: int) -> CalculationRecord:
    return CalculationRecord(
        calculation_id=f"CALC-{index}",
        run_id="RUN-1",
        task_id="TASK-1",
        capability_id=f"capability-{index}",
        capability_version="1.0.0",
        formula_id=formula_id,
        input_evidence_ids=[f"EVD-{index}"],
        output_value=Decimal(index),
        output_unit="RATIO",
        status=CalculationStatus.PASS,
    )


def test_owned_material_calculation_taxonomy_is_complete_disjoint_and_ordered() -> None:
    calculations = [
        _calculation(formula_id, index)
        for index, formula_id in reversed(list(enumerate(MATERIAL_FORMULAS, start=1)))
    ]
    fundamental_refs, technical_refs = partition_material_calculation_refs(calculations)
    assert FUNDAMENTAL_FORMULAS + TECHNICAL_FORMULAS == MATERIAL_FORMULAS
    assert fundamental_refs == ["CALC-1", "CALC-2", "CALC-3"]
    assert technical_refs == [f"CALC-{index}" for index in range(4, 11)]
    assert set(fundamental_refs).isdisjoint(technical_refs)
    assert set(fundamental_refs) | set(technical_refs) == {
        calculation.calculation_id for calculation in calculations
    }


def test_owned_material_calculation_taxonomy_rejects_duplicate_or_unclassified_formula() -> None:
    calculations = [
        _calculation(formula_id, index)
        for index, formula_id in enumerate(MATERIAL_FORMULAS, start=1)
    ]
    with pytest.raises(ValueError, match="unique"):
        partition_material_calculation_refs([*calculations[:-1], calculations[0]])
    with pytest.raises(ValueError, match="exact owned formula set"):
        partition_material_calculation_refs(calculations[:-1])
