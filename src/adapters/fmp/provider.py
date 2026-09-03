from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Protocol, runtime_checkable

import httpx

from src.adapters.fmp.models import (
    FMPAccessError,
    FMPAccessStatus,
    FMPEndpoint,
    FMPEndpointSpec,
    FMPFetchResult,
    FMPResponseEnvelope,
)
from src.data.hashing import snapshot_hash
from src.data.normalization import normalize_field
from src.data.provider import ProviderRequest, RawProviderSnapshot
from src.domain.base import JsonObject
from src.infrastructure.config.settings import FMPSettings


@runtime_checkable
class FMPTransport(Protocol):
    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope: ...


class LegacyFMPTransport(Protocol):
    async def get_json(self, path: str, params: dict[str, str | int]) -> Any: ...


class HttpxFMPTransport:
    """Secret-safe FMP HTTP transport configured only through dependency injection."""

    def __init__(
        self,
        settings: FMPSettings,
        *,
        timeout_seconds: float = 20.0,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not settings.enabled or settings.api_key is None:
            raise ValueError("FMP credentials are not configured")
        self._api_key = settings.api_key
        self._base_url = settings.base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._http_transport = http_transport

    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        request_params = {**params, "apikey": self._api_key.get_secret_value()}
        retrieved_at = datetime.now(UTC)
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                transport=self._http_transport,
            ) as client:
                response = await client.get(path, params=request_params)
        except httpx.TimeoutException:
            return FMPResponseEnvelope(
                endpoint=endpoint,
                status=FMPAccessStatus.PROVIDER_ERROR,
                http_status=0,
                retrieved_at=retrieved_at,
                payload=None,
                error_code="TIMEOUT",
            )
        except httpx.RequestError:
            return FMPResponseEnvelope(
                endpoint=endpoint,
                status=FMPAccessStatus.PROVIDER_ERROR,
                http_status=0,
                retrieved_at=retrieved_at,
                payload=None,
                error_code="NETWORK_ERROR",
            )

        payload = _json_or_none(response)
        status, error_code = classify_access(response.status_code, payload)
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=status,
            http_status=response.status_code,
            retrieved_at=retrieved_at,
            payload=payload,
            error_code=error_code,
        )


_SPECS: dict[str, FMPEndpointSpec] = {}


def _register(spec: FMPEndpointSpec, *aliases: str) -> None:
    for name in (spec.dataset, *aliases):
        _SPECS[name] = spec


_register(FMPEndpointSpec(FMPEndpoint.PROFILE, "/stable/profile", "company_profile"), "profile")
_register(
    FMPEndpointSpec(FMPEndpoint.INCOME, "/stable/income-statement", "annual_financials"),
    "income",
    "income_statement",
)
_register(FMPEndpointSpec(FMPEndpoint.INCOME, "/stable/income-statement", "quarterly_financials"))
_register(
    FMPEndpointSpec(FMPEndpoint.BALANCE, "/stable/balance-sheet-statement", "balance_sheet"),
    "balance",
)
_register(
    FMPEndpointSpec(FMPEndpoint.CASHFLOW, "/stable/cash-flow-statement", "cash_flow"),
    "cashflow",
)
_register(FMPEndpointSpec(FMPEndpoint.PEERS, "/stable/stock-peers", "peer_multiples"), "peers")
_register(FMPEndpointSpec(FMPEndpoint.QUOTE, "/stable/quote", "market_price"), "quote")
_register(
    FMPEndpointSpec(
        FMPEndpoint.HISTORICAL,
        "/stable/historical-price-eod/full",
        "historical_prices",
    ),
    "historical",
)
_register(
    FMPEndpointSpec(
        FMPEndpoint.ANALYST,
        "/stable/grades-consensus",
        "analyst_recommendations",
    ),
    "analyst",
)
_register(FMPEndpointSpec(FMPEndpoint.NEWS, "/stable/news/stock-latest", "news"))
_register(
    FMPEndpointSpec(
        FMPEndpoint.TRANSCRIPT,
        "/stable/earning-call-transcript",
        "transcript",
    )
)


_STATEMENT_METADATA = {
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
_EXTERNAL_CALCULATED_FIELDS = {
    "beta",
    "change",
    "changesPercentage",
    "changePercentage",
    "dayLow",
    "dayHigh",
    "dcf",
    "dcfDiff",
    "eps",
    "freeCashFlow",
    "marketCap",
    "mktCap",
    "pe",
    "priceAvg50",
    "priceAvg200",
    "yearHigh",
    "yearLow",
}
_PROFILE_FIELDS = {
    "symbol",
    "companyName",
    "currency",
    "exchange",
    "exchangeShortName",
    "industry",
    "sector",
    "country",
    "description",
    "price",
    "beta",
    "mktCap",
    "marketCap",
    "fullTimeEmployees",
}
_QUOTE_FIELDS = {
    "symbol",
    "name",
    "price",
    "volume",
    "avgVolume",
    "marketCap",
    "pe",
    "eps",
    "open",
    "previousClose",
    "dayLow",
    "dayHigh",
    "yearLow",
    "yearHigh",
    "priceAvg50",
    "priceAvg200",
}


class FMPProvider:
    """FMP capability source whose only consumer-facing output is normalized evidence."""

    name = "fmp"

    def __init__(self, transport: FMPTransport | LegacyFMPTransport) -> None:
        self._transport = transport

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        result = await self.probe(request)
        if result.snapshot is None:
            raise FMPAccessError(result)
        return result.snapshot

    async def probe(self, request: ProviderRequest) -> FMPFetchResult:
        spec = endpoint_for(request.dataset)
        params = _params_for(spec, request)
        envelope = await self._request(spec, params)
        if envelope.status not in {FMPAccessStatus.AVAILABLE, FMPAccessStatus.NO_DATA}:
            return FMPFetchResult(
                endpoint=spec.endpoint,
                status=envelope.status,
                http_status=envelope.http_status,
                snapshot=None,
                mapped_record_count=0,
                error_code=envelope.error_code,
            )

        payload = envelope.payload if envelope.payload is not None else []
        records = map_payload(spec, payload, request, envelope.retrieved_at)
        raw_envelope = {
            "endpoint": spec.endpoint.value,
            "http_status": envelope.http_status,
            "retrieved_at": envelope.retrieved_at.isoformat(),
            "payload": payload,
        }
        digest = snapshot_hash(raw_envelope)
        source_name = spec.path.rsplit("/", maxsplit=1)[-1]
        snapshot = RawProviderSnapshot(
            provider=self.name,
            source_locator=f"fmp://{source_name}?symbol={request.symbol.upper()}",
            retrieved_at=envelope.retrieved_at,
            raw_artifact_ref=f"fmp://raw/{digest}",
            snapshot_hash=digest,
            raw_payload=raw_envelope,
            records=records,
        )
        return FMPFetchResult(
            endpoint=spec.endpoint,
            status=envelope.status,
            http_status=envelope.http_status,
            snapshot=snapshot,
            mapped_record_count=len(records),
            error_code=envelope.error_code,
        )

    async def _request(
        self,
        spec: FMPEndpointSpec,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        request_method = getattr(self._transport, "request", None)
        if request_method is not None:
            return await request_method(endpoint=spec.endpoint, path=spec.path, params=params)

        # Phase-1 test doubles used get_json; preserve that contract during migration.
        legacy_params = dict(params)
        if legacy_params.get("period") == "annual":
            legacy_params.pop("period")
        payload = await self._transport.get_json(spec.path.removeprefix("/stable/"), legacy_params)
        status = FMPAccessStatus.NO_DATA if _is_empty(payload) else FMPAccessStatus.AVAILABLE
        return FMPResponseEnvelope(
            endpoint=spec.endpoint,
            status=status,
            http_status=200,
            retrieved_at=datetime.now(UTC),
            payload=payload,
        )


def endpoint_for(dataset: str) -> FMPEndpointSpec:
    try:
        return _SPECS[dataset]
    except KeyError as exc:
        raise ValueError(f"unsupported FMP dataset: {dataset}") from exc


def classify_access(http_status: int, payload: Any) -> tuple[FMPAccessStatus, str | None]:
    if http_status == 401:
        return FMPAccessStatus.AUTHENTICATION_FAILED, "HTTP_AUTHENTICATION"
    if http_status in {402, 403}:
        return FMPAccessStatus.ENTITLEMENT_DENIED, "HTTP_ENTITLEMENT"
    if http_status == 404:
        return FMPAccessStatus.NOT_FOUND, "HTTP_NOT_FOUND"
    if http_status == 429:
        return FMPAccessStatus.RATE_LIMITED, "HTTP_RATE_LIMIT"
    if http_status >= 500 or http_status == 0:
        return FMPAccessStatus.PROVIDER_ERROR, "HTTP_PROVIDER_ERROR"
    if http_status >= 400:
        return FMPAccessStatus.PROVIDER_ERROR, "HTTP_CLIENT_ERROR"

    message = _error_message(payload).lower()
    if message:
        if any(token in message for token in ("invalid api", "invalid key", "unauthorized")):
            return FMPAccessStatus.AUTHENTICATION_FAILED, "PAYLOAD_AUTHENTICATION"
        if any(
            token in message
            for token in ("subscription", "upgrade", "premium", "not available", "plan")
        ):
            return FMPAccessStatus.ENTITLEMENT_DENIED, "PAYLOAD_ENTITLEMENT"
        if any(token in message for token in ("rate limit", "limit reached", "too many")):
            return FMPAccessStatus.RATE_LIMITED, "PAYLOAD_RATE_LIMIT"
        return FMPAccessStatus.PROVIDER_ERROR, "PAYLOAD_PROVIDER_ERROR"
    if _is_empty(payload):
        return FMPAccessStatus.NO_DATA, None
    return FMPAccessStatus.AVAILABLE, None


def map_payload(
    spec: FMPEndpointSpec,
    payload: Any,
    request: ProviderRequest,
    retrieved_at: datetime,
) -> list[JsonObject]:
    if spec.endpoint in {FMPEndpoint.INCOME, FMPEndpoint.BALANCE, FMPEndpoint.CASHFLOW}:
        return _map_statements(_object_list(payload), set(request.fields))
    if spec.endpoint is FMPEndpoint.PROFILE:
        return _map_objects(
            _object_list(payload),
            request,
            retrieved_at,
            endpoint=spec.endpoint,
            curated_fields=_PROFILE_FIELDS,
        )
    if spec.endpoint is FMPEndpoint.QUOTE:
        return _map_objects(
            _object_list(payload),
            request,
            retrieved_at,
            endpoint=spec.endpoint,
            curated_fields=_QUOTE_FIELDS,
        )
    if spec.endpoint is FMPEndpoint.HISTORICAL:
        return _map_historical(payload, request, retrieved_at)
    if spec.endpoint is FMPEndpoint.PEERS:
        return _map_peers(payload, request, retrieved_at)
    if spec.endpoint is FMPEndpoint.ANALYST:
        return _map_analyst(_object_list(payload), request, retrieved_at)
    if spec.endpoint is FMPEndpoint.NEWS:
        return _map_news(_object_list(payload), request, retrieved_at)
    if spec.endpoint is FMPEndpoint.TRANSCRIPT:
        return _map_transcript(_object_list(payload), request, retrieved_at)
    raise AssertionError(f"unhandled endpoint: {spec.endpoint}")


def _map_statements(
    statements: list[dict[str, Any]], requested_fields: set[str]
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for statement in statements:
        period = _period(statement)
        as_of = statement.get("date")
        currency = str(statement.get("reportedCurrency", "USD")).upper()
        for field, value in statement.items():
            if field in _STATEMENT_METADATA or value is None or isinstance(value, bool):
                continue
            canonical = normalize_field(field)
            if (
                requested_fields
                and field not in requested_fields
                and canonical not in requested_fields
            ):
                continue
            if not isinstance(value, (int, float)):
                continue
            output_field = _reference_field(field) if _is_external_calculation(field) else field
            unit = _numeric_unit(field, currency)
            records.append(
                {
                    "field": output_field,
                    "period": period,
                    "as_of": as_of,
                    "value": value,
                    "unit": unit,
                    "currency": currency if unit == currency else None,
                }
            )
    return records


def _map_objects(
    objects: list[dict[str, Any]],
    request: ProviderRequest,
    retrieved_at: datetime,
    *,
    endpoint: FMPEndpoint,
    curated_fields: set[str],
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for item_index, item in enumerate(objects[: request.limit]):
        currency = str(item.get("currency", "USD")).upper()
        provider_timestamp = _provider_timestamp(item)
        observed_at = provider_timestamp or retrieved_at
        as_of = observed_at.date().isoformat()
        fields = set(request.fields) if request.fields else curated_fields
        for field in fields:
            if field not in item or item[field] is None:
                continue
            value = item[field]
            output_field = _reference_field(field) if _is_external_calculation(field) else field
            if item_index:
                output_field = f"{output_field}_{item_index}"
            unit, normalized_currency = _unit_for(field, value, currency)
            if unit is None:
                continue
            records.append(
                {
                    "field": output_field,
                    "period": "CURRENT",
                    "as_of": as_of,
                    "value": value,
                    "unit": unit,
                    "currency": normalized_currency,
                    "source_endpoint": endpoint.value,
                    "observed_at": observed_at.isoformat(),
                    "provider_timestamp": (
                        provider_timestamp.isoformat() if provider_timestamp is not None else None
                    ),
                }
            )
    return records


def _map_historical(
    payload: Any, request: ProviderRequest, retrieved_at: datetime
) -> list[JsonObject]:
    objects = payload.get("historical", []) if isinstance(payload, dict) else payload
    records: list[JsonObject] = []
    fields = set(request.fields) if request.fields else {"open", "high", "low", "close", "volume"}
    for item in _object_list(objects)[: request.limit]:
        as_of = item.get("date") or request.as_of.isoformat()
        currency = str(item.get("currency", "USD")).upper()
        for field in fields:
            if field not in item or item[field] is None:
                continue
            unit, normalized_currency = _unit_for(field, item[field], currency)
            if unit is None:
                continue
            records.append(
                {
                    "field": field,
                    "period": "DAILY",
                    "as_of": as_of,
                    "value": item[field],
                    "unit": unit,
                    "currency": normalized_currency,
                }
            )
    return records


def _map_peers(payload: Any, request: ProviderRequest, retrieved_at: datetime) -> list[JsonObject]:
    peer_symbols: list[str] = []
    items = [payload] if isinstance(payload, dict) else payload
    if isinstance(items, list):
        for item in items:
            if isinstance(item, str):
                peer_symbols.append(item)
            elif isinstance(item, dict):
                peers = item.get("peersList")
                if isinstance(peers, list):
                    peer_symbols.extend(str(peer) for peer in peers)
                elif item.get("symbol") and str(item["symbol"]).upper() != request.symbol.upper():
                    peer_symbols.append(str(item["symbol"]))
    as_of = retrieved_at.date().isoformat()
    return [
        {
            "field": f"peer_symbol_{index}",
            "period": "CURRENT",
            "as_of": as_of,
            "value": symbol,
            "unit": "SYMBOL",
            "source_endpoint": FMPEndpoint.PEERS.value,
            "observed_at": retrieved_at.isoformat(),
            "provider_timestamp": None,
        }
        for index, symbol in enumerate(dict.fromkeys(peer_symbols[: request.limit]))
    ]


def _map_analyst(
    objects: list[dict[str, Any]], request: ProviderRequest, retrieved_at: datetime
) -> list[JsonObject]:
    allowed = (
        set(request.fields)
        if request.fields
        else {
            "strongBuy",
            "buy",
            "hold",
            "sell",
            "strongSell",
        }
    )
    records: list[JsonObject] = []
    for item in objects[: request.limit]:
        as_of = item.get("date") or _safe_as_of(item, request, retrieved_at)
        for field in allowed:
            value = item.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            records.append(
                {
                    "field": field,
                    "period": "CURRENT",
                    "as_of": as_of,
                    "value": value,
                    "unit": "COUNT",
                }
            )
    return records


def _map_news(
    objects: list[dict[str, Any]], request: ProviderRequest, retrieved_at: datetime
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for index, item in enumerate(objects[: request.limit]):
        published = item.get("publishedDate") or item.get("publishedAt")
        as_of = str(published)[:10] if published else _safe_as_of(item, request, retrieved_at)
        for source_field, output_prefix in (("title", "headline"), ("publisher", "publisher")):
            value = item.get(source_field) or (
                item.get("site") if source_field == "publisher" else None
            )
            if not isinstance(value, str) or not value.strip():
                continue
            records.append(
                {
                    "field": f"{output_prefix}_{index}",
                    "period": "DAILY",
                    "as_of": as_of,
                    "value": value,
                    "unit": "TEXT",
                }
            )
    return records


def _map_transcript(
    objects: list[dict[str, Any]], request: ProviderRequest, retrieved_at: datetime
) -> list[JsonObject]:
    records: list[JsonObject] = []
    for index, item in enumerate(objects[: request.limit]):
        content = item.get("content") or item.get("text") or item.get("transcript")
        if not isinstance(content, str) or not content.strip():
            continue
        year = item.get("year")
        quarter = item.get("quarter")
        period = (
            f"Q{quarter}FY{year}" if year and quarter else (request.expected_period or "CURRENT")
        )
        as_of = item.get("date") or _safe_as_of(item, request, retrieved_at)
        records.extend(
            (
                {
                    "field": f"transcript_available_{index}",
                    "period": period,
                    "as_of": as_of,
                    "value": True,
                    "unit": "BOOLEAN",
                },
                {
                    "field": f"transcript_character_count_{index}",
                    "period": period,
                    "as_of": as_of,
                    "value": len(content),
                    "unit": "COUNT",
                },
            )
        )
    return records


def _params_for(spec: FMPEndpointSpec, request: ProviderRequest) -> dict[str, str | int]:
    params: dict[str, str | int] = {"symbol": request.symbol.upper()}
    if spec.endpoint in {
        FMPEndpoint.INCOME,
        FMPEndpoint.BALANCE,
        FMPEndpoint.CASHFLOW,
        FMPEndpoint.HISTORICAL,
    }:
        params["limit"] = request.limit
    if request.dataset == "quarterly_financials":
        params["period"] = "quarter"
    elif spec.endpoint in {FMPEndpoint.INCOME, FMPEndpoint.BALANCE, FMPEndpoint.CASHFLOW}:
        params["period"] = "annual"
    if spec.endpoint is FMPEndpoint.NEWS:
        params = {"symbols": request.symbol.upper(), "limit": request.limit, "page": 0}
    if spec.endpoint is FMPEndpoint.TRANSCRIPT:
        parsed = _parse_quarter(request.expected_period)
        if parsed:
            params.update({"quarter": parsed[0], "year": parsed[1]})
    return params


def _parse_quarter(period: str | None) -> tuple[int, int] | None:
    if not period:
        return None
    normalized = period.upper()
    if not normalized.startswith("Q") or "FY" not in normalized:
        return None
    quarter_text, year_text = normalized.removeprefix("Q").split("FY", maxsplit=1)
    if not quarter_text.isdigit() or not year_text.isdigit():
        return None
    quarter = int(quarter_text)
    if quarter not in {1, 2, 3, 4}:
        return None
    return quarter, int(year_text)


def _numeric_unit(field: str, currency: str) -> str:
    canonical = normalize_field(field)
    if "share" in canonical and "per_share" not in canonical:
        return "SHARES"
    if canonical.endswith("ratio") or "margin" in canonical or canonical in {"beta", "pe"}:
        return "RATIO"
    if "volume" in canonical or "employee" in canonical:
        return "COUNT"
    return currency


def _unit_for(field: str, value: Any, currency: str) -> tuple[str | None, str | None]:
    canonical = normalize_field(field)
    if canonical in {
        "full_time_employees",
        "volume",
        "avg_volume",
    }:
        return "COUNT", None
    if isinstance(value, bool):
        return "BOOLEAN", None
    if isinstance(value, str):
        return ("SYMBOL", None) if canonical == "symbol" else ("TEXT", None)
    if isinstance(value, (int, float)):
        unit = _numeric_unit(field, currency)
        return unit, currency if unit == currency else None
    return None, None


def _is_external_calculation(field: str) -> bool:
    canonical = normalize_field(field)
    return field in _EXTERNAL_CALCULATED_FIELDS or canonical.endswith("ratio")


def _reference_field(field: str) -> str:
    return f"provider_reference_{normalize_field(field)}"


def _period(statement: dict[str, Any]) -> str:
    fiscal_year = statement.get("fiscalYear") or statement.get("calendarYear")
    period = str(statement.get("period", "FY")).upper()
    if fiscal_year is None:
        return period
    if period == "FY":
        return f"FY{fiscal_year}"
    return f"{period}FY{fiscal_year}"


def _safe_as_of(item: dict[str, Any], request: ProviderRequest, retrieved_at: datetime) -> str:
    candidate = item.get("date")
    if isinstance(candidate, str) and len(candidate) >= 10:
        try:
            return date.fromisoformat(candidate[:10]).isoformat()
        except ValueError:
            pass
    return min(request.as_of, retrieved_at.date()).isoformat()


def _provider_timestamp(item: dict[str, Any]) -> datetime | None:
    for field in ("timestamp", "lastUpdated", "lastUpdate", "updatedAt"):
        value = item.get(field)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            seconds = float(value)
            if seconds > 10_000_000_000:
                seconds /= 1000
            try:
                return datetime.fromtimestamp(seconds, tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            if stripped.isdigit():
                try:
                    return datetime.fromtimestamp(int(stripped), tz=UTC)
                except (OverflowError, OSError, ValueError):
                    continue
            try:
                parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
    return None


def _object_list(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        if payload in (None, [], {}):
            return []
        raise ValueError("FMP response payload must be a list of objects")
    return payload


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("Error Message", "error", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def _is_empty(payload: Any) -> bool:
    return payload in (None, [], {})
