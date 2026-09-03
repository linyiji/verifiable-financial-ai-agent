from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from src.data.provider import RawProviderSnapshot


class FMPEndpoint(StrEnum):
    PROFILE = "profile"
    INCOME = "income"
    BALANCE = "balance"
    CASHFLOW = "cashflow"
    PEERS = "peers"
    QUOTE = "quote"
    HISTORICAL = "historical"
    ANALYST = "analyst"
    NEWS = "news"
    TRANSCRIPT = "transcript"


class FMPAccessStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_DATA = "NO_DATA"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    ENTITLEMENT_DENIED = "ENTITLEMENT_DENIED"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    PROVIDER_ERROR = "PROVIDER_ERROR"


@dataclass(frozen=True, slots=True)
class FMPEndpointSpec:
    endpoint: FMPEndpoint
    path: str
    dataset: str


@dataclass(frozen=True, slots=True)
class FMPResponseEnvelope:
    endpoint: FMPEndpoint
    status: FMPAccessStatus
    http_status: int
    retrieved_at: datetime
    payload: Any
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class FMPFetchResult:
    endpoint: FMPEndpoint
    status: FMPAccessStatus
    http_status: int
    snapshot: RawProviderSnapshot | None
    mapped_record_count: int
    error_code: str | None = None


class FMPAccessError(RuntimeError):
    def __init__(self, result: FMPFetchResult) -> None:
        self.endpoint = result.endpoint
        self.status = result.status
        self.http_status = result.http_status
        self.error_code = result.error_code
        super().__init__(
            f"FMP endpoint {result.endpoint.value} unavailable: "
            f"{result.status.value} ({result.error_code or 'UNCLASSIFIED'})"
        )
