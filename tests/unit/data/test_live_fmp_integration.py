from __future__ import annotations

import inspect
from datetime import UTC, date, datetime
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
                "PAYLOAD_ENTITLEMENT"
                if self.status is FMPAccessStatus.ENTITLEMENT_DENIED
                else None
            ),
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
        FMPEndpoint.QUOTE: [
            {"symbol": "NVDA", "name": "NVIDIA", "price": 190.0, "pe": 45.0}
        ],
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
    provider = FMPProvider(
        EndpointTransport({}, status=FMPAccessStatus.ENTITLEMENT_DENIED)
    )

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
    assert "unit-test-token" not in repr(transport)
    assert "unit-test-token" not in repr(envelope)


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
