from datetime import datetime

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel
from src.domain.incremental import IncrementalResearchContext


class ResearchSchemeSnapshot(TimestampedModel):
    scheme_id: str
    research_object_id: str
    goal_id: str
    research_scope: list[str] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    agent_requirements: list[str] = Field(default_factory=list)
    skill_requirements: list[str] = Field(default_factory=list)
    calculation_requirements: list[str] = Field(default_factory=list)
    assurance_requirements: JsonObject = Field(default_factory=dict)
    report_requirements: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    generated_by: str
    generated_model: str | None = None
    confirmed_at: datetime | None = None
    incremental_context: IncrementalResearchContext | None = Field(
        default=None, exclude_if=lambda v: v is None
    )
