from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPProvider
from src.adapters.fmp.models import FMPResponseEnvelope
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository
from src.domain.capability import CapabilityContext


class IncomeTransport:
    async def request(
        self,
        *,
        endpoint: FMPEndpoint,
        path: str,
        params: dict[str, str | int],
    ) -> FMPResponseEnvelope:
        assert endpoint is FMPEndpoint.INCOME
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=FMPAccessStatus.AVAILABLE,
            http_status=200,
            retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
            payload=[
                {
                    "symbol": "NVDA",
                    "date": "2026-01-25",
                    "reportedCurrency": "USD",
                    "fiscalYear": "2026",
                    "period": "FY",
                    "revenue": 215900000000,
                    "ebitda": 142500000000,
                },
                {
                    "symbol": "NVDA",
                    "date": "2025-01-26",
                    "reportedCurrency": "USD",
                    "fiscalYear": "2025",
                    "period": "FY",
                    "revenue": 130500000000,
                    "ebitda": 85000000000,
                },
            ],
        )


@pytest.mark.asyncio
async def test_nvda_fmp_evidence_to_native_calculations() -> None:
    service = EvidenceIngestionService(
        repository=InMemoryEvidenceRepository(),
        freshness_policy=FreshnessPolicy(max_age_days=800),
    )
    result = await service.ingest(
        provider=FMPProvider(IncomeTransport()),
        request=ProviderRequest(
            symbol="NVDA",
            dataset="annual_financials",
            as_of=date(2026, 9, 4),
            fields=("revenue", "ebitda"),
            limit=5,
        ),
        run_id="RUN-PHASE2-NVDA",
        object_id="OBJ-NVDA",
    )
    evidence = result.accepted.records
    revenues = sorted(
        (record for record in evidence if record.normalized_field == "revenue"),
        key=lambda record: record.as_of,
    )
    current_revenue = revenues[-1]
    prior_revenue = revenues[-2]
    current_ebitda = next(
        record
        for record in evidence
        if record.normalized_field == "ebitda" and record.period == current_revenue.period
    )
    context = CapabilityContext(
        run_id="RUN-PHASE2-NVDA",
        task_id="TASK-FUNDAMENTALS",
        accepted_evidence_ids=[record.evidence_id for record in evidence],
    )

    growth = await RevenueGrowthCapability().execute(
        {
            "calculation_id": "CALC-NVDA-REVENUE-GROWTH",
            "prior": prior_revenue,
            "current": current_revenue,
        },
        context,
    )
    margin = await EbitdaMarginCapability().execute(
        {
            "calculation_id": "CALC-NVDA-EBITDA-MARGIN",
            "ebitda": current_ebitda,
            "revenue": current_revenue,
        },
        context,
    )

    assert growth.output_value == Decimal("0.6544061302681992337164750958")
    assert margin.output_value == Decimal("0.6600277906438165817508105604")
    assert set(growth.input_evidence_ids) == {
        prior_revenue.evidence_id,
        current_revenue.evidence_id,
    }
    assert set(margin.input_evidence_ids) == {
        current_ebitda.evidence_id,
        current_revenue.evidence_id,
    }
