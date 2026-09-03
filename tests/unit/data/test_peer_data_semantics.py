from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from src.adapters.fmp.models import (
    FMPAccessStatus,
    FMPEndpoint,
    FMPResponseEnvelope,
)
from src.adapters.fmp.provider import FMPProvider
from src.data.ingestion import EvidenceIngestionService
from src.data.peers import (
    PeerCompanyFacts,
    PeerSelectionService,
    StockPeersCandidateSource,
)
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository
from src.domain.enums import EvidenceStatus

RETRIEVED_AT = datetime(2026, 9, 4, 16, 0, tzinfo=UTC)


class _Transport:
    def __init__(self, payloads: dict[FMPEndpoint, Any]) -> None:
        self._payloads = payloads

    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        del path, params
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=FMPAccessStatus.AVAILABLE,
            http_status=200,
            retrieved_at=RETRIEVED_AT,
            payload=self._payloads[endpoint],
        )


def _request(dataset: str, *, limit: int = 10) -> ProviderRequest:
    return ProviderRequest(
        symbol="NVDA",
        dataset=dataset,
        as_of=date(2026, 9, 4),
        limit=limit,
    )


@pytest.mark.asyncio
async def test_profile_and_quote_units_follow_field_semantics() -> None:
    provider = FMPProvider(
        _Transport(
            {
                FMPEndpoint.PROFILE: [
                    {
                        "symbol": "NVDA",
                        "companyName": "NVIDIA Corporation",
                        "currency": "USD",
                        "price": 190.0,
                        "beta": 1.5,
                        "marketCap": 4_500_000_000_000,
                        "fullTimeEmployees": "29600",
                    }
                ],
                FMPEndpoint.QUOTE: [
                    {
                        "symbol": "NVDA",
                        "price": 190.0,
                        "volume": "31000000",
                        "avgVolume": 42_000_000,
                        "marketCap": 4_500_000_000_000,
                        "pe": 45.0,
                    }
                ],
            }
        )
    )

    profile = await provider.fetch(_request("company_profile", limit=1))
    quote = await provider.fetch(_request("market_price", limit=1))
    profile_units = {record["field"]: record["unit"] for record in profile.records}
    quote_units = {record["field"]: record["unit"] for record in quote.records}

    assert profile_units["fullTimeEmployees"] == "COUNT"
    assert profile_units["companyName"] == "TEXT"
    assert profile_units["symbol"] == "SYMBOL"
    assert profile_units["price"] == "USD"
    assert profile_units["provider_reference_beta"] == "RATIO"
    assert profile_units["provider_reference_market_cap"] == "USD"
    assert quote_units["volume"] == "COUNT"
    assert quote_units["avgVolume"] == "COUNT"
    assert quote_units["provider_reference_pe"] == "RATIO"

    result = await EvidenceIngestionService(repository=InMemoryEvidenceRepository()).ingest(
        provider=provider,
        request=_request("company_profile", limit=1),
        run_id="RUN-UNIT",
        object_id="OBJ-NVDA",
    )
    employees = next(
        record
        for record in result.accepted.records
        if record.normalized_field == "full_time_employees"
    )
    assert employees.normalized_value == "29600"
    assert employees.unit == "COUNT"


@pytest.mark.asyncio
async def test_current_observation_and_provider_timestamps_are_not_date_conflated() -> None:
    first_observation = datetime(2026, 9, 4, 14, 30, tzinfo=UTC)
    second_observation = datetime(2026, 9, 4, 15, 45, tzinfo=UTC)
    provider = FMPProvider(
        _Transport(
            {
                FMPEndpoint.PROFILE: [
                    {"symbol": "NVDA", "companyName": "NVIDIA", "currency": "USD"}
                ],
                FMPEndpoint.QUOTE: [
                    {
                        "symbol": "NVDA",
                        "price": 189.0,
                        "timestamp": int(first_observation.timestamp()),
                    },
                    {
                        "symbol": "NVDA",
                        "price": 190.0,
                        "timestamp": int(second_observation.timestamp()),
                    },
                ],
            }
        )
    )

    profile_result = await EvidenceIngestionService(repository=InMemoryEvidenceRepository()).ingest(
        provider=provider,
        request=_request("company_profile", limit=1),
        run_id="RUN-PROFILE",
        object_id="OBJ-NVDA",
    )
    assert profile_result.accepted.records
    assert {record.observed_at for record in profile_result.accepted.records} == {RETRIEVED_AT}
    assert {record.provider_timestamp for record in profile_result.accepted.records} == {None}
    assert {record.source_endpoint for record in profile_result.accepted.records} == {"profile"}

    quote_result = await EvidenceIngestionService(repository=InMemoryEvidenceRepository()).ingest(
        provider=provider,
        request=_request("market_price", limit=2),
        run_id="RUN-QUOTE",
        object_id="OBJ-NVDA",
    )
    price_records = [
        record
        for record in quote_result.accepted.records
        if record.normalized_field.startswith("price")
    ]
    assert {record.as_of for record in price_records} == {date(2026, 9, 4)}
    assert {record.observed_at for record in price_records} == {
        first_observation,
        second_observation,
    }
    assert {record.provider_timestamp for record in price_records} == {
        first_observation,
        second_observation,
    }
    assert all(record.retrieved_at == RETRIEVED_AT for record in price_records)
    assert all(record.source_endpoint == "quote" for record in price_records)


@pytest.mark.asyncio
async def test_current_snapshot_is_not_backdated_to_a_historical_request() -> None:
    provider = FMPProvider(
        _Transport(
            {FMPEndpoint.PROFILE: [{"symbol": "NVDA", "companyName": "NVIDIA", "currency": "USD"}]}
        )
    )
    historical_request = ProviderRequest(
        symbol="NVDA",
        dataset="company_profile",
        as_of=date(2026, 9, 3),
        limit=1,
    )

    result = await EvidenceIngestionService(repository=InMemoryEvidenceRepository()).ingest(
        provider=provider,
        request=historical_request,
        run_id="RUN-HISTORICAL",
        object_id="OBJ-NVDA",
    )

    assert result.accepted.records == []
    assert result.records
    assert all(record.status is EvidenceStatus.REJECTED for record in result.records)
    assert all(record.as_of == RETRIEVED_AT.date() for record in result.records)
    assert all(record.observed_at == RETRIEVED_AT for record in result.records)


@pytest.mark.asyncio
async def test_stock_peers_are_candidates_until_policy_selects_comparables() -> None:
    provider = FMPProvider(
        _Transport(
            {
                FMPEndpoint.PEERS: [
                    {
                        "symbol": "NVDA",
                        "peersList": ["AMD", "MSFT", "NO_DATA", "NVDA", "AMD"],
                    }
                ]
            }
        )
    )
    evidence_result = await EvidenceIngestionService(
        repository=InMemoryEvidenceRepository()
    ).ingest(
        provider=provider,
        request=_request("peer_multiples"),
        run_id="RUN-PEERS",
        object_id="OBJ-NVDA",
    )
    peer_evidence = evidence_result.accepted.records
    assert all(record.status is EvidenceStatus.ACCEPTED for record in peer_evidence)
    assert all(record.source_endpoint == "peers" for record in peer_evidence)
    unrelated_symbol_evidence = peer_evidence[0].model_copy(
        update={
            "evidence_id": "EVD-NOT-STOCK-PEERS",
            "source_endpoint": "quote",
            "normalized_value": "NOT_A_CANDIDATE",
        }
    )

    required_metrics = frozenset({"revenue", "ebitda", "pe"})
    subject = PeerCompanyFacts(
        symbol="NVDA",
        industry="Semiconductors",
        sector="Technology",
        market_cap=Decimal("1000000000000"),
    )
    facts = {
        "AMD": PeerCompanyFacts(
            symbol="AMD",
            industry="Semiconductors",
            sector="Technology",
            market_cap=Decimal("500000000000"),
            available_metrics=required_metrics,
            source_evidence_ids=("EVD-AMD-PROFILE", "EVD-AMD-METRICS"),
        ),
        "MSFT": PeerCompanyFacts(
            symbol="MSFT",
            industry="Software",
            sector="Technology",
            market_cap=Decimal("3000000000000"),
            available_metrics=required_metrics,
            source_evidence_ids=("EVD-MSFT-PROFILE", "EVD-MSFT-METRICS"),
        ),
    }

    result = PeerSelectionService(candidate_source=StockPeersCandidateSource()).select(
        subject=subject,
        stock_peer_evidence=[*peer_evidence, unrelated_symbol_evidence],
        facts_by_symbol=facts,
        business_relevance={"AMD": True, "MSFT": False, "NO_DATA": False},
        required_metrics=required_metrics,
    )

    assert [candidate.candidate_symbol for candidate in result.candidates] == [
        "AMD",
        "MSFT",
        "NO_DATA",
    ]
    assert [candidate.candidate_symbol for candidate in result.selected_comparables] == ["AMD"]
    assert {decision.candidate_symbol for decision in result.decisions} == {
        "AMD",
        "MSFT",
        "NO_DATA",
    }
    selected = next(decision for decision in result.decisions if decision.candidate_symbol == "AMD")
    assert selected.selected is True
    assert "classification=industry_match" in selected.reason_summary
    assert "business_relevant=true" in selected.reason_summary
    assert selected.selection_source == "fmp.stock_peers+deterministic_comparable_policy_v1"
    assert selected.source_evidence_ids
    rejected = {
        decision.candidate_symbol: decision
        for decision in result.decisions
        if not decision.selected
    }
    assert "failed_checks=business" in rejected["MSFT"].reason_summary
    assert "data" in rejected["NO_DATA"].reason_summary
    assert set(candidate.candidate_symbol for candidate in result.candidates) != set(
        candidate.candidate_symbol for candidate in result.selected_comparables
    )
