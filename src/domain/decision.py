from pydantic import Field

from src.domain.base import TimestampedModel


class StructuredAgentDecision(TimestampedModel):
    decision_id: str
    run_id: str
    task_id: str | None = None
    decision_type: str
    reason_code: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    selected_skill: str | None = None
    selected_capability: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_review: bool = False

