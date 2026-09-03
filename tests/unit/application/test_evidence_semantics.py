from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from src.adapters.fmp import (
    FMPAccessStatus,
    FMPEndpoint,
    FMPProvider,
    FMPResponseEnvelope,
)
from src.application.evidence_collection import (
    EvidenceAcquisitionScope,
    LiveFMPEvidenceCollector,
    evidence_request_plans,
)
from src.application.evidence_routing import EvidenceTaskRouter, RunEvidenceStore
from src.data.repository import InMemoryEvidenceRepository
from src.domain.enums import EvidenceAcquisitionStatus, EvidenceCategory
from src.domain.runtime_event import RuntimeEventType
from src.domain.task import Task

AS_OF = date(2026, 9, 4)
RETRIEVED_AT = datetime(2026, 9, 4, 12, tzinfo=UTC)
RUN_ID = "RUN-EVIDENCE-SEMANTICS"


class SemanticFMPTransport:
    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        del path, params
        if endpoint in {FMPEndpoint.NEWS, FMPEndpoint.TRANSCRIPT}:
            return FMPResponseEnvelope(
                endpoint=endpoint,
                status=FMPAccessStatus.ENTITLEMENT_DENIED,
                http_status=402,
                retrieved_at=RETRIEVED_AT,
                payload=None,
                error_code="HTTP_ENTITLEMENT",
            )
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=FMPAccessStatus.AVAILABLE,
            http_status=200,
            retrieved_at=RETRIEVED_AT,
            payload=_payloads()[endpoint],
        )


def _payloads() -> dict[FMPEndpoint, Any]:
    company_profile = {
        "symbol": "NVDA",
        "companyName": "NVIDIA Corporation",
        "currency": "USD",
        "exchange": "NASDAQ",
        "industry": "Semiconductors",
        "sector": "Technology",
        "country": "US",
        "description": "Accelerated computing company",
        "price": 190.0,
        "beta": 1.5,
        "marketCap": 4_600_000_000_000,
        "fullTimeEmployees": 36_000,
    }
    statements = [
        {
            "symbol": "NVDA",
            "date": "2026-01-25",
            "reportedCurrency": "USD",
            "fiscalYear": "2026",
            "period": "FY",
            "revenue": 215_900_000_000,
            "ebitda": 142_500_000_000,
            "totalAssets": 206_000_000_000,
            "totalDebt": 12_000_000_000,
            "totalStockholdersEquity": 158_000_000_000,
            "operatingCashFlow": 125_000_000_000,
            "capitalExpenditure": -4_500_000_000,
            "freeCashFlow": 120_500_000_000,
        },
        {
            "symbol": "NVDA",
            "date": "2025-01-26",
            "reportedCurrency": "USD",
            "fiscalYear": "2025",
            "period": "FY",
            "revenue": 130_500_000_000,
            "ebitda": 85_000_000_000,
            "totalAssets": 111_000_000_000,
            "totalDebt": 10_000_000_000,
            "totalStockholdersEquity": 79_000_000_000,
            "operatingCashFlow": 64_000_000_000,
            "capitalExpenditure": -3_200_000_000,
            "freeCashFlow": 60_800_000_000,
        },
    ]
    return {
        FMPEndpoint.PROFILE: [company_profile],
        FMPEndpoint.INCOME: statements,
        FMPEndpoint.BALANCE: statements,
        FMPEndpoint.CASHFLOW: statements,
        FMPEndpoint.PEERS: [
            {
                "symbol": "NVDA",
                "peersList": [
                    "AMD",
                    "AVGO",
                    "INTC",
                    "QCOM",
                    "TSM",
                    "MU",
                    "MRVL",
                    "ARM",
                    "ADI",
                ],
            }
        ],
        FMPEndpoint.QUOTE: [
            {
                "symbol": "NVDA",
                "price": 190.0,
                "volume": 100_000_000,
                "marketCap": 4_600_000_000_000,
            }
        ],
        FMPEndpoint.HISTORICAL: [
            {
                "symbol": "NVDA",
                "date": observed,
                "close": 185.0 + index,
                "volume": 90_000_000 + index,
            }
            for index, observed in enumerate(
                ("2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04")
            )
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
    }


def _task(suffix: str, task_type: str) -> Task:
    return Task(
        task_id=f"{RUN_ID}:{suffix}",
        run_id=RUN_ID,
        task_type=task_type,
        goal=task_type,
        assigned_agent="test-agent",
        skill_id=f"{task_type}_v1",
    )


def test_request_plans_enforce_scoped_ownership() -> None:
    company = evidence_request_plans(
        symbol="NVDA", as_of=AS_OF, scope=EvidenceAcquisitionScope.COMPANY
    )
    peer = evidence_request_plans(
        symbol="NVDA", as_of=AS_OF, scope=EvidenceAcquisitionScope.PEER
    )
    research = evidence_request_plans(
        symbol="NVDA", as_of=AS_OF, scope=EvidenceAcquisitionScope.RESEARCH_NEWS
    )

    assert {plan.request.dataset for plan in company} == {
        "company_profile",
        "annual_financials",
        "balance_sheet",
        "cash_flow",
        "market_price",
        "historical_prices",
        "analyst_recommendations",
    }
    assert [(plan.request.dataset, plan.category) for plan in peer] == [
        ("peer_multiples", EvidenceCategory.PEER)
    ]
    assert {plan.request.dataset for plan in research} == {"news", "transcript"}
    assert {plan.category for plan in research} == {
        EvidenceCategory.NEWS,
        EvidenceCategory.TRANSCRIPT,
    }
    assert all(
        "revenue" not in plan.request.fields and "ebitda" not in plan.request.fields
        for plan in research
    )


@pytest.mark.asyncio
async def test_router_separates_global_evidence_from_task_refs_and_events() -> None:
    repository = InMemoryEvidenceRepository()
    collector = LiveFMPEvidenceCollector(
        provider=FMPProvider(SemanticFMPTransport()), repository=repository
    )
    store = RunEvidenceStore(RUN_ID)
    router = EvidenceTaskRouter(collector=collector, store=store)

    company_task = _task("evidence", "evidence_collection")
    peer_task = _task("peers", "peer_analysis")
    news_task = _task("research-news", "research_news_analysis")
    fundamental_task = _task("fundamentals", "fundamental_analysis")

    company = await router.route(
        company_task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF
    )
    peer = await router.route(
        peer_task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF
    )
    news = await router.route(
        news_task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF
    )
    fundamental = await router.route(
        fundamental_task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF
    )

    event_intents = company.event_intents + peer.event_intents + news.event_intents
    event_ids = [str(event.payload["evidence_id"]) for event in event_intents]
    assert len(store.select_ids()) == 49
    assert len(event_ids) == 49
    assert len(set(event_ids)) == 49
    assert all(event.type is RuntimeEventType.EVIDENCE_ACCEPTED for event in event_intents)

    assert company.acquisition_status is EvidenceAcquisitionStatus.PARTIAL
    assert len(company.output_evidence_ids) == 40
    assert company.input_evidence_ids == ()
    assert peer.acquisition_status is EvidenceAcquisitionStatus.COMPLETED
    assert len(peer.output_evidence_ids) == 9
    assert set(peer.input_evidence_ids).isdisjoint(peer.output_evidence_ids)
    assert news.acquisition_status is EvidenceAcquisitionStatus.ENTITLEMENT_BLOCKED
    assert news.output_evidence_ids == ()
    assert news.event_intents == ()
    assert fundamental.acquisition_status is None
    assert fundamental.output_evidence_ids == ()
    assert fundamental.event_intents == ()

    records = store.records
    assert {
        record.producer_task_id
        for record in records
        if record.evidence_category is EvidenceCategory.PEER
    } == {peer_task.task_id}
    assert not any(
        record.evidence_category in {EvidenceCategory.NEWS, EvidenceCategory.TRANSCRIPT}
        for record in records
    )
    news_refs = set(news.input_evidence_ids) | set(news.output_evidence_ids)
    assert not any(
        record.evidence_id in news_refs
        and record.normalized_field in {"revenue", "ebitda"}
        for record in records
    )

    company.apply_to(company_task)
    news.apply_to(news_task)
    assert company_task.task_output_evidence_ids == list(company.output_evidence_ids)
    assert news_task.evidence_acquisition_status is EvidenceAcquisitionStatus.ENTITLEMENT_BLOCKED

    revenue_id = next(
        record.evidence_id for record in records if record.normalized_field == "revenue"
    )
    lineage = store.lineage(revenue_id)
    assert lineage.producer_task_id == company_task.task_id
    assert lineage.source_endpoint == FMPEndpoint.INCOME.value
    assert lineage.evidence_purpose == "fundamental_financials"
    assert fundamental_task.task_id in lineage.referenced_by_task_ids


@pytest.mark.asyncio
async def test_repeated_acquisition_reuses_ids_without_duplicate_event_intents() -> None:
    repository = InMemoryEvidenceRepository()
    collector = LiveFMPEvidenceCollector(
        provider=FMPProvider(SemanticFMPTransport()), repository=repository
    )
    store = RunEvidenceStore(RUN_ID)
    router = EvidenceTaskRouter(collector=collector, store=store)
    task = _task("evidence", "evidence_collection")

    first = await router.route(task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF)
    second = await router.route(task, symbol="NVDA", object_id="OBJ-NVDA", as_of=AS_OF)

    assert len(first.event_intents) == 40
    assert second.event_intents == ()
    assert second.output_evidence_ids == first.output_evidence_ids
    assert len(await repository.list_by_run(RUN_ID)) == 46
