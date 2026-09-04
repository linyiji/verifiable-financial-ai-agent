from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateResearchObjectRequest(ApiModel):
    symbol: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    exchange: str
    sector: str | None = None
    currency: str = "USD"


class PrepareResearchRunRequest(ApiModel):
    research_object_id: str
    research_goal: str = Field(min_length=1)
    as_of: date
    preferences: dict[str, object] = Field(default_factory=dict)


class ConfirmResearchRunRequest(ApiModel):
    draft_id: str
    confirm_scheme: bool


class ErrorDetail(ApiModel):
    code: str
    message: str
    details: dict[str, object] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(ApiModel):
    error: ErrorDetail
