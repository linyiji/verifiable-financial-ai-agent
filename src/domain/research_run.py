from datetime import date, datetime

from src.domain.base import TimestampedModel
from src.domain.enums import RunStatus


class ResearchRun(TimestampedModel):
    run_id: str
    research_object_id: str
    goal_id: str
    scheme_id: str
    status: RunStatus = RunStatus.DRAFT
    as_of: date
    planned_graph_id: str | None = None
    actual_graph_id: str | None = None
    execution_target: str = "SERVER_SANDBOX"
    started_at: datetime | None = None
    completed_at: datetime | None = None
