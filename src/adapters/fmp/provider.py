from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from src.data.hashing import snapshot_hash
from src.data.provider import ProviderRequest, RawProviderSnapshot
from src.domain.base import JsonObject


class FMPTransport(Protocol):
    async def get_json(self, path: str, params: dict[str, str | int]) -> Any: ...


class HttpxFMPTransport:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://financialmodelingprep.com/stable",
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("FMP api_key must not be empty")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    async def get_json(self, path: str, params: dict[str, str | int]) -> Any:
        safe_params = {**params, "apikey": self._api_key}
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        ) as client:
            response = await client.get(path, params=safe_params)
            response.raise_for_status()
            return response.json()


_DATASET_PATHS = {
    "annual_financials": "income-statement",
    "quarterly_financials": "income-statement",
    "balance_sheet": "balance-sheet-statement",
    "cash_flow": "cash-flow-statement",
}
_METADATA_FIELDS = {
    "symbol",
    "date",
    "reportedCurrency",
    "cik",
    "filingDate",
    "acceptedDate",
    "fiscalYear",
    "calendarYear",
    "period",
    "link",
    "finalLink",
}


class FMPProvider:
    """FMP remains behind the provider boundary; no FMP JSON escapes to consumers."""

    name = "fmp"

    def __init__(self, transport: FMPTransport) -> None:
        self._transport = transport

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        try:
            path = _DATASET_PATHS[request.dataset]
        except KeyError as exc:
            raise ValueError(f"unsupported FMP dataset: {request.dataset}") from exc
        params: dict[str, str | int] = {"symbol": request.symbol, "limit": request.limit}
        if request.dataset == "quarterly_financials":
            params["period"] = "quarter"

        payload = await self._transport.get_json(path, params)
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("FMP response must be a list of objects")
        digest = snapshot_hash(payload)
        records = _map_statements(payload, requested_fields=set(request.fields))
        return RawProviderSnapshot(
            provider=self.name,
            source_locator=f"fmp://{path}?symbol={request.symbol.upper()}",
            retrieved_at=datetime.now(UTC),
            raw_artifact_ref=f"fmp://raw/{digest}",
            snapshot_hash=digest,
            raw_payload=payload,
            records=records,
        )


def _map_statements(
    statements: list[dict[str, Any]], requested_fields: set[str]
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for statement in statements:
        period = _period(statement)
        as_of = statement.get("date")
        currency = str(statement.get("reportedCurrency", "USD")).upper()
        for field, value in statement.items():
            if field in _METADATA_FIELDS or value is None or isinstance(value, bool):
                continue
            if requested_fields and field not in requested_fields:
                continue
            if not isinstance(value, (int, float)):
                continue
            records.append(
                {
                    "field": field,
                    "period": period,
                    "as_of": as_of,
                    "value": value,
                    "unit": currency,
                    "currency": currency,
                }
            )
    return records


def _period(statement: dict[str, Any]) -> str:
    fiscal_year = statement.get("fiscalYear") or statement.get("calendarYear")
    period = str(statement.get("period", "FY")).upper()
    if fiscal_year is None:
        return period
    if period == "FY":
        return f"FY{fiscal_year}"
    return f"{period}FY{fiscal_year}"
