from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, use_enum_values=False)


class TimestampedModel(DomainModel):
    created_at: datetime = Field(default_factory=utc_now)


JsonObject = dict[str, Any]

