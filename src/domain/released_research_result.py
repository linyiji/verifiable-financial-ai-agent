from datetime import datetime

from pydantic import Field

from src.domain.base import DomainModel, JsonObject, utc_now


class ReleasedResearchResult(DomainModel):
    result_id: str
    run_id: str
    structured_financial_results: JsonObject = Field(default_factory=dict)
    released_claims: list[JsonObject] = Field(default_factory=list)
    judgments: list[JsonObject] = Field(default_factory=list)
    assumption_refs: list[str] = Field(default_factory=list)
    risk_output: JsonObject = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    released_at: datetime = Field(default_factory=utc_now)
