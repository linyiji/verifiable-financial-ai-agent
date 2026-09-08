from pydantic import Field, model_validator

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import ReviewStatus


class ReviewCheck(TimestampedModel):
    code: str
    status: ReviewStatus
    subject_refs: list[str] = Field(default_factory=list)
    expected: JsonObject = Field(default_factory=dict)
    actual: JsonObject = Field(default_factory=dict)
    detail: str | None = None


class ReviewRecord(TimestampedModel):
    review_id: str
    run_id: str
    status: ReviewStatus
    deterministic_findings: list[JsonObject] = Field(default_factory=list)
    semantic_findings: list[JsonObject] = Field(default_factory=list)
    reviewed_evidence_refs: list[str] = Field(default_factory=list)
    reviewed_calculation_refs: list[str] = Field(default_factory=list)
    reviewed_metric_refs: list[str] = Field(default_factory=list)
    reviewed_claim_refs: list[str] = Field(default_factory=list)
    reviewed_judgment_refs: list[str] = Field(default_factory=list)
    required_proof_calculation_refs: list[str] = Field(default_factory=list)
    checks: list[ReviewCheck] = Field(default_factory=list)
    input_snapshot_hash: str | None = None
    requirement_context: JsonObject | None = None
    reviewer: str = "deterministic-review-v1"

    @model_validator(mode="after")
    def reject_contradictory_status(self) -> "ReviewRecord":
        check_statuses = {check.status for check in self.checks}
        if ReviewStatus.BLOCK in check_statuses and self.status is not ReviewStatus.BLOCK:
            raise ValueError("a blocking review check requires BLOCK status")
        if (
            ReviewStatus.REVIEW in check_statuses
            and ReviewStatus.BLOCK not in check_statuses
            and self.status is ReviewStatus.PASS
        ):
            raise ValueError("a review check cannot produce PASS status")
        if (
            self.checks
            and self.status is ReviewStatus.PASS
            and check_statuses != {ReviewStatus.PASS}
        ):
            raise ValueError("PASS requires every review check to pass")
        if self.reviewer == "independent-financial-review-v2":
            if not self.checks or not self.input_snapshot_hash:
                raise ValueError("independent financial review requires checks and input hash")
            if self.status is ReviewStatus.PASS and (
                not self.reviewed_calculation_refs or not self.reviewed_claim_refs
            ):
                raise ValueError("independent financial review requires calculation and claim refs")
        return self
