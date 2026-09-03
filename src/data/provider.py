from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from src.domain.base import DomainModel, JsonObject


class ProviderRequest(DomainModel):
    """Provider-neutral request used at the data boundary."""

    symbol: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    as_of: date
    expected_period: str | None = None
    fields: tuple[str, ...] = ()
    limit: int = Field(default=20, ge=1, le=500)


class RawProviderSnapshot(DomainModel):
    """Quarantined provider output; not a downstream reasoning contract."""

    provider: str
    source_locator: str
    retrieved_at: datetime
    raw_artifact_ref: str
    snapshot_hash: str
    raw_payload: JsonObject | list[Any]
    records: list[JsonObject]


@runtime_checkable
class Provider(Protocol):
    name: str

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot: ...
