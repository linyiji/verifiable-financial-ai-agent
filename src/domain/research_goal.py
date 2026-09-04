from datetime import date

from pydantic import Field

from src.domain.base import JsonObject, TimestampedModel


class ResearchGoal(TimestampedModel):
    goal_id: str
    research_object_id: str
    goal_type: str = "comprehensive_equity_research"
    goal_text: str = Field(min_length=1)
    as_of: date
    preferences: JsonObject = Field(default_factory=dict)
