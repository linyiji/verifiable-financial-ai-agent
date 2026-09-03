from datetime import datetime

from pydantic import Field

from src.domain.base import TimestampedModel
from src.domain.enums import CorrectionStatus


class CorrectionRecord(TimestampedModel):
    correction_id: str
    run_id: str
    task_id: str
    problem_code: str
    detected_by: str
    attempt: int = Field(ge=1)
    action: str
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    status: CorrectionStatus
    resolved_at: datetime | None = None

