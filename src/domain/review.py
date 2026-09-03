from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.enums import ReviewStatus


class ReviewRecord(TimestampedModel):
    review_id: str
    run_id: str
    status: ReviewStatus
    deterministic_findings: list[JsonObject] = Field(default_factory=list)
    semantic_findings: list[JsonObject] = Field(default_factory=list)
    reviewer: str = "deterministic-review-v1"

