from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from src.adapters.fmp import (
    FinancialProviderMode,
    FMPAccessError,
    FMPAccessStatus,
    FMPEndpoint,
    FMPProvider,
    HttpxFMPTransport,
    select_financial_provider,
)
from src.adapters.fmp.models import FMPResponseEnvelope
from src.adapters.fmp.provider import classify_access, endpoint_for
from src.data.artifacts import LocalRawArtifactStore
from src.data.fixtures import FixtureProvider
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository
from src.infrastructure.config.settings import FMPSettings

RETRIEVED_AT = datetime(2026, 9, 4, tzinfo=UTC)


class EndpointTransport:
    def __init__(
        self,
        payloads: dict[FMPEndpoint, Any],
        status: FMPAccessStatus = FMPAccessStatus.AVAILABLE,
    ) -> None:
        self.payloads = payloads
        self.status = status
        self.calls: list[tuple[FMPEndpoint, str, dict[str, str | int]]] = []

    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        self.calls.append((endpoint, path, params))
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=self.status,
            http_status=200,
            retrieved_at=RETRIEVED_AT,
            payload=self.payloads.get(endpoint, []),
            error_code=(
                "PAYLOAD_ENTITLEMENT" if self.status is FMPAccessStatus.ENTITLEMENT_DENIED else None
            ),
        )


class PaginatedHistoryTransport:
    def __init__(self, *, fail_first: bool = False, fail_after: int | None = None) -> None:
        self.fail_first = fail_first
        self.fail_after = fail_after
        self.calls = 0

    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        del path
        self.calls += 1
        if (self.fail_first and self.calls == 1) or (
            self.fail_after is not None and self.calls >= self.fail_after
        ):
            return FMPResponseEnvelope(
                endpoint=endpoint,
                status=FMPAccessStatus.PROVIDER_ERROR,
                http_status=503,
                retrieved_at=RETRIEVED_AT,
                payload=None,
                error_code="TRANSIENT",
            )
        start = date.fromisoformat(str(params["from"]))
        end = date.fromisoformat(str(params["to"]))
        payload = []
        observed = end
        while observed >= start:
            payload.append(
                {
                    "symbol": "NVDA",
                    "date": observed.isoformat(),
                    "close": 100.0,
                    "volume": 1_000,
                }
            )
            observed -= timedelta(days=1)
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=FMPAccessStatus.AVAILABLE,
            http_status=200,
            retrieved_at=RETRIEVED_AT,
            payload=payload,
        )


def _request(dataset: str, **updates: object) -> ProviderRequest:
    values: dict[str, object] = {
        "symbol": "NVDA",
        "dataset": dataset,
        "as_of": date(2026, 9, 4),
        "limit": 5,
    }
    values.update(updates)
    return ProviderRequest(**values)


def _payloads() -> dict[FMPEndpoint, Any]:
    return {
        FMPEndpoint.PROFILE: [
            {
                "symbol": "NVDA",
                "companyName": "NVIDIA Corporation",
                "currency": "USD",
                "sector": "Technology",
                "price": 190.0,
                "beta": 1.5,
            }
        ],
        FMPEndpoint.INCOME: [
            {
                "symbol": "NVDA",
                "date": "2026-01-25",
                "reportedCurrency": "USD",
                "fiscalYear": "2026",
                "period": "FY",
                "revenue": 215900000000,
                "ebitda": 142500000000,
                "grossProfitRatio": 0.7,
            }
        ],
        FMPEndpoint.BALANCE: [
            {
                "date": "2026-01-25",
                "reportedCurrency": "USD",
                "fiscalYear": "2026",
                "period": "FY",
                "totalAssets": 200000000000,
            }
        ],
        FMPEndpoint.CASHFLOW: [
            {
                "date": "2026-01-25",
                "reportedCurrency": "USD",
                "fiscalYear": "2026",
                "period": "FY",
                "operatingCashFlow": 120000000000,
                "freeCashFlow": 100000000000,
            }
        ],
        FMPEndpoint.PEERS: [{"symbol": "NVDA", "peersList": ["AMD", "AVGO"]}],
        FMPEndpoint.QUOTE: [{"symbol": "NVDA", "name": "NVIDIA", "price": 190.0, "pe": 45.0}],
        FMPEndpoint.HISTORICAL: [
            {"symbol": "NVDA", "date": "2026-09-03", "close": 189.0, "volume": 1000}
        ],
        FMPEndpoint.ANALYST: [
            {
                "symbol": "NVDA",
                "date": "2026-09-01",
                "strongBuy": 20,
                "buy": 40,
                "hold": 5,
                "sell": 1,
                "strongSell": 0,
            }
        ],
        FMPEndpoint.NEWS: [
            {
                "symbol": "NVDA",
                "publishedDate": "2026-09-03 10:00:00",
                "title": "NVIDIA update",
                "publisher": "Example Wire",
            }
        ],
        FMPEndpoint.TRANSCRIPT: [
            {
                "symbol": "NVDA",
                "date": "2026-08-27",
                "year": 2026,
                "quarter": 2,
                "content": "Operator: Welcome. Management: Thank you.",
            }
        ],
    }


@pytest.mark.asyncio
async def test_all_required_endpoints_have_mappers_and_safe_source_locators() -> None:
    provider = FMPProvider(EndpointTransport(_payloads()))
    datasets = {
        "company_profile": FMPEndpoint.PROFILE,
        "annual_financials": FMPEndpoint.INCOME,
        "balance_sheet": FMPEndpoint.BALANCE,
        "cash_flow": FMPEndpoint.CASHFLOW,
        "peer_multiples": FMPEndpoint.PEERS,
        "market_price": FMPEndpoint.QUOTE,
        "historical_prices": FMPEndpoint.HISTORICAL,
        "analyst_recommendations": FMPEndpoint.ANALYST,
        "news": FMPEndpoint.NEWS,
        "transcript": FMPEndpoint.TRANSCRIPT,
    }

    for dataset, endpoint in datasets.items():
        updates = {"expected_period": "Q2FY2026"} if dataset == "transcript" else {}
        result = await provider.probe(_request(dataset, **updates))
        assert result.endpoint is endpoint
        assert result.status is FMPAccessStatus.AVAILABLE
        assert result.snapshot is not None
        assert result.mapped_record_count > 0
        assert "apikey" not in result.snapshot.source_locator.lower()


def test_endpoint_specs_use_stable_paths() -> None:
    for dataset in (
        "company_profile",
        "annual_financials",
        "balance_sheet",
        "cash_flow",
        "peer_multiples",
        "market_price",
        "historical_prices",
        "analyst_recommendations",
        "news",
        "transcript",
    ):
        assert endpoint_for(dataset).path.startswith("/stable/")
    assert endpoint_for("analyst_recommendations").path == "/stable/grades-consensus"


@pytest.mark.asyncio
async def test_historical_request_uses_explicit_window_for_long_indicator_history() -> None:
    transport = EndpointTransport(_payloads())
    provider = FMPProvider(transport)

    await provider.probe(_request("historical_prices", limit=250))

    endpoint, _, _ = transport.calls[-1]
    assert endpoint is FMPEndpoint.HISTORICAL
    assert transport.calls[0][2] == {
        "symbol": "NVDA",
        "limit": 250,
        "from": "2026-08-04",
        "to": "2026-09-04",
    }
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_long_history_retries_first_transient_window_failure() -> None:
    transport = PaginatedHistoryTransport(fail_first=True)
    result = await FMPProvider(transport).probe(_request("historical_prices", limit=250))

    assert result.status is FMPAccessStatus.AVAILABLE
    assert result.mapped_record_count >= 250
    assert transport.calls >= 9


@pytest.mark.asyncio
async def test_long_history_keeps_completed_pages_after_late_transient_failure() -> None:
    transport = PaginatedHistoryTransport(fail_after=3)
    result = await FMPProvider(transport).probe(_request("historical_prices", limit=250))

    assert result.status is FMPAccessStatus.AVAILABLE
    assert result.mapped_record_count >= 60
    assert transport.calls == 4


@pytest.mark.asyncio
async def test_income_retries_transient_access_failure_then_maps_two_annual_periods() -> None:
    payload = _payloads()[FMPEndpoint.INCOME]
    assert isinstance(payload, list)
    payload = [
        *payload,
        {
            "symbol": "NVDA",
            "date": "2025-01-26",
            "reportedCurrency": "USD",
            "fiscalYear": "2025",
            "period": "FY",
            "revenue": 130500000000,
            "ebitda": 85000000000,
        },
    ]

    class TransientIncomeTransport:
        def __init__(self) -> None:
            self.calls = 0

        async def request(self, *, endpoint, path, params) -> FMPResponseEnvelope:
            del path, params
            self.calls += 1
            if self.calls == 1:
                return FMPResponseEnvelope(
                    endpoint=endpoint,
                    status=FMPAccessStatus.RATE_LIMITED,
                    http_status=429,
                    retrieved_at=RETRIEVED_AT,
                    payload=None,
                    error_code="HTTP_RATE_LIMIT",
                )
            return FMPResponseEnvelope(
                endpoint=endpoint,
                status=FMPAccessStatus.AVAILABLE,
                http_status=200,
                retrieved_at=RETRIEVED_AT,
                payload=payload,
            )

    transport = TransientIncomeTransport()
    result = await FMPProvider(transport, transient_retry_delays=(0,)).probe(
        _request("annual_financials", fields=("revenue", "ebitda"))
    )

    assert transport.calls == 2
    assert result.status is FMPAccessStatus.AVAILABLE
    assert result.mapped_record_count == 4
    assert result.snapshot is not None
    assert {record["period"] for record in result.snapshot.records} == {"FY2025", "FY2026"}


@pytest.mark.asyncio
async def test_income_does_not_retry_terminal_access_denial() -> None:
    transport = EndpointTransport({}, status=FMPAccessStatus.ENTITLEMENT_DENIED)

    result = await FMPProvider(transport, transient_retry_delays=(0, 0)).probe(
        _request("annual_financials", fields=("revenue", "ebitda"))
    )

    assert result.status is FMPAccessStatus.ENTITLEMENT_DENIED
    assert result.snapshot is None
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_income_transient_retry_exhaustion_remains_fail_closed() -> None:
    transport = EndpointTransport({}, status=FMPAccessStatus.PROVIDER_ERROR)

    result = await FMPProvider(transport, transient_retry_delays=(0, 0)).probe(
        _request("annual_financials", fields=("revenue", "ebitda"))
    )

    assert result.status is FMPAccessStatus.PROVIDER_ERROR
    assert result.snapshot is None
    assert len(transport.calls) == 3


@pytest.mark.parametrize(
    ("http_status", "payload", "expected"),
    [
        (401, {}, FMPAccessStatus.AUTHENTICATION_FAILED),
        (403, {}, FMPAccessStatus.ENTITLEMENT_DENIED),
        (429, {}, FMPAccessStatus.RATE_LIMITED),
        (
            200,
            {"Error Message": "Endpoint not available with your subscription"},
            FMPAccessStatus.ENTITLEMENT_DENIED,
        ),
        (200, [], FMPAccessStatus.NO_DATA),
        (200, [{"symbol": "NVDA"}], FMPAccessStatus.AVAILABLE),
    ],
)
def test_entitlement_and_access_classification(
    http_status: int, payload: Any, expected: FMPAccessStatus
) -> None:
    status, _ = classify_access(http_status, payload)
    assert status is expected


@pytest.mark.asyncio
async def test_entitlement_denial_raises_typed_error_without_provider_message() -> None:
    provider = FMPProvider(EndpointTransport({}, status=FMPAccessStatus.ENTITLEMENT_DENIED))

    with pytest.raises(FMPAccessError) as raised:
        await provider.fetch(_request("company_profile"))

    assert raised.value.status is FMPAccessStatus.ENTITLEMENT_DENIED
    assert "subscription" not in str(raised.value).lower()


@pytest.mark.asyncio
async def test_http_transport_injects_key_but_envelope_and_repr_do_not_expose_it() -> None:
    observed_key_presence = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_key_presence
        observed_key_presence = request.url.params.get("apikey") == "unit-test-token"
        return httpx.Response(200, json=[{"symbol": "NVDA"}])

    settings = FMPSettings(
        api_key=SecretStr("unit-test-token"),
        base_url="https://example.invalid",
    )
    transport = HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler))
    envelope = await transport.request(
        endpoint=FMPEndpoint.PROFILE,
        path="/stable/profile",
        params={"symbol": "NVDA"},
    )

    assert observed_key_presence is True
    assert envelope.status is FMPAccessStatus.AVAILABLE
    assert transport.safe_pool_status()["selected_key_slot"] == "KEY_1"
    assert transport.safe_pool_status()["rotation_occurred"] is False
    assert "unit-test-token" not in repr(transport)
    assert "unit-test-token" not in repr(envelope)


@pytest.mark.asyncio
async def test_http_transport_rotates_to_next_pool_slot_only_after_429() -> None:
    observed_slots: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        slot = request.url.params["apikey"]
        observed_slots.append(slot)
        if slot == "rate-limited-token":
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=[{"symbol": "NVDA"}])

    settings = FMPSettings(
        api_keys=(SecretStr("rate-limited-token"), SecretStr("usable-token")),
        base_url="https://example.invalid",
    )
    transport = HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler))

    envelope = await transport.request(
        endpoint=FMPEndpoint.QUOTE,
        path="/stable/quote",
        params={"symbol": "NVDA"},
    )

    assert envelope.status is FMPAccessStatus.AVAILABLE
    assert observed_slots == ["rate-limited-token", "usable-token"]
    assert transport.safe_pool_status() == {
        "provider": "FMP",
        "configured_keys": 2,
        "rate_limited_keys": 1,
        "invalid_keys": 0,
        "attempt_count": 2,
        "selected_key_slot": "KEY_2",
        "status_classification": "AVAILABLE",
        "rotation_occurred": True,
        "rotation_reason": "RATE_LIMIT_429",
        "pool_exhausted": False,
    }
    assert "rate-limited-token" not in repr(transport.safe_pool_status())
    assert "usable-token" not in repr(transport.safe_pool_status())


@pytest.mark.asyncio
async def test_http_transport_rotates_across_two_429_slots_then_retains_third() -> None:
    observed_slots: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        slot = request.url.params["apikey"]
        observed_slots.append(slot)
        if slot in {"limited-one", "limited-two"}:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(200, json=[{"symbol": "NVDA"}])

    settings = FMPSettings(
        api_keys=(
            SecretStr("limited-one"),
            SecretStr("limited-two"),
            SecretStr("usable-three"),
        ),
        base_url="https://example.invalid",
    )
    transport = HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler))

    first = await transport.request(
        endpoint=FMPEndpoint.QUOTE,
        path="/stable/quote",
        params={"symbol": "NVDA"},
    )
    second = await transport.request(
        endpoint=FMPEndpoint.PROFILE,
        path="/stable/profile",
        params={"symbol": "NVDA"},
    )

    assert first.status is FMPAccessStatus.AVAILABLE
    assert second.status is FMPAccessStatus.AVAILABLE
    assert observed_slots == ["limited-one", "limited-two", "usable-three", "usable-three"]
    assert transport.safe_pool_status()["selected_key_slot"] == "KEY_3"
    assert transport.safe_pool_status()["rate_limited_keys"] == 2


@pytest.mark.asyncio
async def test_http_transport_exhausts_rate_limited_pool_without_retry_loop() -> None:
    request_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        assert request.url.params.get("apikey") in {"limited-a", "limited-b"}
        request_count += 1
        return httpx.Response(429, json={"error": "rate limited"})

    settings = FMPSettings(
        api_keys=(SecretStr("limited-a"), SecretStr("limited-b")),
        base_url="https://example.invalid",
    )
    transport = HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler))
    provider = FMPProvider(transport, transient_retry_delays=(0, 0))

    result = await provider.probe(_request("market_price"))

    assert result.status is FMPAccessStatus.RATE_LIMITED
    assert result.error_code == "FMP_KEY_POOL_EXHAUSTED"
    assert request_count == 2
    assert transport.rate_limited_key_count == 2
    assert transport.pool_exhausted is True


@pytest.mark.parametrize("credential_status", [401, 403])
@pytest.mark.asyncio
async def test_http_transport_skips_http_credential_failure(credential_status: int) -> None:
    invalid_calls: list[str] = []

    async def invalid_handler(request: httpx.Request) -> httpx.Response:
        slot = request.url.params["apikey"]
        invalid_calls.append(slot)
        if slot == "invalid-token":
            return httpx.Response(credential_status, json={"error": "credential rejected"})
        return httpx.Response(200, json=[{"symbol": "NVDA"}])

    settings = FMPSettings(
        api_keys=(SecretStr("invalid-token"), SecretStr("usable-token")),
        base_url="https://example.invalid",
    )
    invalid_transport = HttpxFMPTransport(
        settings, http_transport=httpx.MockTransport(invalid_handler)
    )
    recovered = await invalid_transport.request(
        endpoint=FMPEndpoint.QUOTE,
        path="/stable/quote",
        params={"symbol": "NVDA"},
    )
    assert recovered.status is FMPAccessStatus.AVAILABLE
    assert invalid_calls == ["invalid-token", "usable-token"]
    assert invalid_transport.invalid_key_count == 1


@pytest.mark.asyncio
async def test_http_transport_does_not_rotate_on_unrelated_provider_error() -> None:
    settings = FMPSettings(
        api_keys=(SecretStr("first-token"), SecretStr("unused-token")),
        base_url="https://example.invalid",
    )

    provider_error_calls = 0

    async def provider_error_handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_error_calls
        del request
        provider_error_calls += 1
        return httpx.Response(503, json={"error": "provider unavailable"})

    provider_error_transport = HttpxFMPTransport(
        settings, http_transport=httpx.MockTransport(provider_error_handler)
    )
    failed = await provider_error_transport.request(
        endpoint=FMPEndpoint.QUOTE,
        path="/stable/quote",
        params={"symbol": "NVDA"},
    )
    assert failed.status is FMPAccessStatus.PROVIDER_ERROR
    assert provider_error_calls == 1
    assert provider_error_transport.rate_limited_key_count == 0
    assert provider_error_transport.invalid_key_count == 0


@pytest.mark.asyncio
async def test_fmp_pool_secrets_are_absent_from_safe_errors_and_observability(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secrets = ("private-fmp-key-one", "private-fmp-key-two")

    async def handler(request: httpx.Request) -> httpx.Response:
        echoed_secret = request.url.params["apikey"]
        return httpx.Response(429, json={"error": echoed_secret})

    settings = FMPSettings(
        api_keys=tuple(SecretStr(value) for value in secrets),
        base_url="https://example.invalid",
    )
    transport = HttpxFMPTransport(settings, http_transport=httpx.MockTransport(handler))
    provider = FMPProvider(transport, transient_retry_delays=())

    with pytest.raises(FMPAccessError) as raised:
        await provider.fetch(_request("market_price"))

    public_surfaces = "\n".join(
        (
            repr(transport),
            repr(transport.safe_pool_status()),
            str(raised.value),
            repr(raised.value),
            caplog.text,
        )
    )
    assert raised.value.error_code == "FMP_KEY_POOL_EXHAUSTED"
    assert transport.safe_pool_status()["pool_exhausted"] is True
    assert all(secret not in public_surfaces for secret in secrets)


def test_adapter_has_no_direct_environment_reads() -> None:
    from src.adapters.fmp import provider, selection

    source = inspect.getsource(provider) + inspect.getsource(selection)
    assert "os.getenv" not in source
    assert "os.environ" not in source
    assert "load_dotenv" not in source


def test_provider_selection_preserves_fixture_and_selects_injected_fmp() -> None:
    fixture = Path("tests/fixtures/nvda_financials.json")
    disabled = FMPSettings(api_key=None, base_url="https://example.invalid")
    fixture_selection = select_financial_provider(
        mode=FinancialProviderMode.AUTO,
        fmp_settings=disabled,
        fixture_path=fixture,
    )
    enabled = FMPSettings(
        api_key=SecretStr("unit-test-token"),
        base_url="https://example.invalid",
    )
    transport = EndpointTransport(_payloads())
    fmp_selection = select_financial_provider(
        mode=FinancialProviderMode.AUTO,
        fmp_settings=enabled,
        fixture_path=fixture,
        transport=transport,
    )

    assert isinstance(fixture_selection.provider, FixtureProvider)
    assert fixture_selection.live is False
    assert isinstance(fmp_selection.provider, FMPProvider)
    assert fmp_selection.live is True


@pytest.mark.asyncio
async def test_raw_envelope_is_artifacted_before_normalized_evidence(
    tmp_path: Path,
) -> None:
    provider = FMPProvider(EndpointTransport(_payloads()))
    repository = InMemoryEvidenceRepository()
    service = EvidenceIngestionService(
        repository=repository,
        artifact_store=LocalRawArtifactStore(tmp_path),
        freshness_policy=FreshnessPolicy(max_age_days=365),
    )

    result = await service.ingest(
        provider=provider,
        request=_request("company_profile"),
        run_id="RUN-LIVE-FMP",
        object_id="OBJ-NVDA",
    )

    assert result.accepted.records
    artifact_refs = {record.raw_artifact_ref for record in result.records}
    assert len(artifact_refs) == 1
    artifact = Path(artifact_refs.pop())
    _assert_artifact_path(artifact, tmp_path)
    assert all(record.provider == "fmp" for record in result.accepted.records)


def _assert_artifact_path(artifact: Path, root: Path) -> None:
    assert artifact.is_file()
    assert artifact.is_relative_to(root)


@pytest.mark.asyncio
async def test_external_provider_metrics_are_reference_only() -> None:
    provider = FMPProvider(EndpointTransport(_payloads()))
    quote = await provider.fetch(_request("market_price"))
    income = await provider.fetch(_request("annual_financials"))
    cashflow = await provider.fetch(_request("cash_flow"))

    quote_fields = {record["field"] for record in quote.records}
    income_fields = {record["field"] for record in income.records}
    cashflow_fields = {record["field"] for record in cashflow.records}
    assert "provider_reference_pe" in quote_fields
    assert "pe" not in quote_fields
    assert "provider_reference_gross_profit_ratio" in income_fields
    assert "gross_profit_ratio" not in income_fields
    assert "provider_reference_free_cash_flow" in cashflow_fields
    assert "free_cash_flow" not in cashflow_fields
