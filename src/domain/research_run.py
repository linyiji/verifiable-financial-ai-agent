from datetime import date, datetime

from pydantic import Field, model_validator

from src.domain.base import TimestampedModel, utc_now
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
    updated_at: datetime = Field(default_factory=utc_now)
    base_run_id: str | None = Field(default=None, exclude_if=lambda v: v is None)
    base_research_view_version: str | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def incremental_base(self):
        if (self.base_run_id is None) != (self.base_research_view_version is None):
            raise ValueError("incremental base identities must be paired")
        if self.base_run_id == self.run_id:
            raise ValueError("incremental Run must be independent")
        return self
