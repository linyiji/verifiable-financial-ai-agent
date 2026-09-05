from __future__ import annotations

from collections.abc import Sequence

from src.domain.calculation import CalculationRecord
from src.output.financial_metrics import MATERIAL_FORMULAS

FUNDAMENTAL_FORMULAS = (
    "revenue_growth_v1",
    "ebitda_margin_v1",
    "operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",
)

TECHNICAL_FORMULAS = (
    "sma_close_50_v1",
    "sma_close_200_v1",
    "rsi_close_14_simple_average_v1",
    "macd_line_close_12_26_adjust_false_v1",
    "macd_signal_close_12_26_9_adjust_false_v1",
    "macd_histogram_close_12_26_9_adjust_false_v1",
    "latest_volume_to_average_volume_20_v1",
)


def partition_material_calculation_refs(
    calculations: Sequence[CalculationRecord],
) -> tuple[list[str], list[str]]:
    """Partition the owned material calculation set without inspecting runtime text."""

    expected = FUNDAMENTAL_FORMULAS + TECHNICAL_FORMULAS
    if expected != MATERIAL_FORMULAS:
        raise RuntimeError("owned material calculation taxonomy is out of sync")
    formula_ids = [calculation.formula_id for calculation in calculations]
    if len(formula_ids) != len(set(formula_ids)):
        raise ValueError("material calculation formulas must be unique")
    if set(formula_ids) != set(expected):
        raise ValueError("material calculation taxonomy requires the exact owned formula set")
    calculation_id_by_formula = {
        calculation.formula_id: calculation.calculation_id for calculation in calculations
    }
    fundamental_refs = [
        calculation_id_by_formula[formula_id] for formula_id in FUNDAMENTAL_FORMULAS
    ]
    technical_refs = [calculation_id_by_formula[formula_id] for formula_id in TECHNICAL_FORMULAS]
    if set(fundamental_refs) & set(technical_refs):
        raise ValueError("fundamental and technical calculation refs must be disjoint")
    return fundamental_refs, technical_refs
