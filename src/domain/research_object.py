from datetime import datetime

from pydantic import Field

from src.domain.base import TimestampedModel, utc_now


class ResearchObject(TimestampedModel):
    object_id: str
    object_type: str = "public_company"
    symbol: str = Field(min_length=1)
    company_name: str = Field(min_length=1)
    exchange: str
    sector: str | None = None
    currency: str = "USD"
    identity_version: int = 1
    updated_at: datetime = Field(default_factory=utc_now)
