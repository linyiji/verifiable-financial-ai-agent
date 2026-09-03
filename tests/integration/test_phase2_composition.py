from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.adapters.fmp import (
    FMPAccessStatus,
    FMPEndpoint,
    FMPProvider,
    FMPResponseEnvelope,
)
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.service import ResearchApplicationService
from src.data.repository import InMemoryEvidenceRepository
from src.domain.enums import RunStatus


class Phase2Transport:
    async def request(self, *, endpoint, path, params) -> FMPResponseEnvelope:
        del path, params
        payload = []
        status = FMPAccessStatus.NO_DATA
        if endpoint is FMPEndpoint.INCOME:
            status = FMPAccessStatus.AVAILABLE
            payload = [
                {
                    "symbol": "NVDA",
                    "date": "2026-01-25",
                    "reportedCurrency": "USD",
                    "fiscalYear": "2026",
                    "period": "FY",
                    "revenue": 215_900_000_000,
                    "ebitda": 142_500_000_000,
                },
                {
                    "symbol": "NVDA",
                    "date": "2025-01-26",
                    "reportedCurrency": "USD",
                    "fiscalYear": "2025",
                    "period": "FY",
                    "revenue": 130_500_000_000,
                    "ebitda": 85_000_000_000,
                },
            ]
        return FMPResponseEnvelope(
            endpoint=endpoint,
            status=status,
            http_status=200,
            retrieved_at=datetime(2026, 9, 4, tzinfo=UTC),
            payload=payload,
        )


@pytest.mark.asyncio
async def test_phase2_live_collector_composes_with_full_runtime() -> None:
    repository = InMemoryEvidenceRepository()
    collector = LiveFMPEvidenceCollector(
        provider=FMPProvider(Phase2Transport()),
        repository=repository,
    )
    service = ResearchApplicationService(
        evidence_repository=repository,
        evidence_collector=collector,
    )
    research_object = await service.create_object(
        symbol="NVDA",
        company_name="NVIDIA Corporation",
        exchange="NASDAQ",
    )
    draft = await service.prepare_run(
        research_object_id=research_object.object_id,
        research_goal="Validate the Phase-2 composition root",
        as_of=date(2026, 9, 4),
        preferences={},
    )
    aggregate = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    aggregate = await service.execute_run(aggregate.run.run_id)

    assert aggregate.run.status is RunStatus.RELEASED
    assert len(collector.endpoint_statuses) == 10
    assert len(aggregate.artifacts.calculations) == 2
    results = {item.capability_id: item.output_value for item in aggregate.artifacts.calculations}
    assert results["revenue_growth"] == Decimal("0.6544061302681992337164750958")
    assert results["ebitda_margin"] == Decimal("0.6600277906438165817508105604")
    assert all(item.provider == "fmp" for item in aggregate.artifacts.evidence)
