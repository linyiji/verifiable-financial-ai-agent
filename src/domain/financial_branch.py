"""Financial availability is distinct from computation failure and claim eligibility."""

from enum import StrEnum

from pydantic import Field, model_validator

from src.domain.base import DomainModel


class BranchStatus(StrEnum):
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    FAILED = "FAILED"
    BLOCKED_BY_RUNTIME = "BLOCKED_BY_RUNTIME"


class BranchRequirement(StrEnum):
    REQUIRED = "REQUIRED"
    CONDITIONAL = "CONDITIONAL"
    SUPPORTING = "SUPPORTING"


BRANCH_FORMULAS = {
    "free_cash_flow_margin": ("operating_cash_flow_plus_signed_capex_divided_by_revenue_v1",),
    "technical_sma_50": ("sma_close_50_v1",),
    "technical_sma_200": ("sma_close_200_v1",),
    "technical_rsi_14": ("rsi_close_14_simple_average_v1",),
    "technical_macd_12_26_9": (
        "macd_line_close_12_26_adjust_false_v1",
        "macd_signal_close_12_26_9_adjust_false_v1",
        "macd_histogram_close_12_26_9_adjust_false_v1",
    ),
    "technical_volume_ratio_20": ("latest_volume_to_average_volume_20_v1",),
}


class FinancialBranchResult(DomainModel):
    branch_id: str
    run_id: str
    task_id: str
    calculation_type: str
    status: BranchStatus
    requirement: BranchRequirement
    required_inputs: int = Field(ge=0)
    available_inputs: int = Field(ge=0)
    calculation_ids: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    reason_code: str | None = None
    diagnostic_id: str | None = None

    @model_validator(mode="after")
    def no_unavailable_numbers(self):
        if self.status is not BranchStatus.COMPLETED and self.calculation_ids:
            raise ValueError("unavailable financial branch cannot carry calculations")
        if self.status is BranchStatus.COMPLETED and not self.calculation_ids:
            raise ValueError("completed financial branch must identify deterministic calculations")
        return self


def claim_dependencies_available(
    required_branch_ids: list[str], results: list[FinancialBranchResult]
) -> bool:
    index = {result.branch_id: result for result in results}
    return bool(required_branch_ids) and all(
        branch in index and index[branch].status is BranchStatus.COMPLETED
        for branch in required_branch_ids
    )
