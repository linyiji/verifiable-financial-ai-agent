from datetime import date
from typing import Any

import pytest

from src.adapters.fmp import FMPProvider
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest
from src.data.repository import InMemoryEvidenceRepository


class StubTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    async def get_json(self, path: str, params: dict[str, str | int]) -> Any:
        self.calls.append((path, params))
        return [
            {
                "symbol": "NVDA",
                "date": "2026-01-25",
                "reportedCurrency": "USD",
                "fiscalYear": "2026",
                "period": "FY",
                "revenue": 215900000000,
                "grossProfit": 161000000000,
                "link": "https://example.invalid/filing",
            }
        ]


@pytest.mark.asyncio
async def test_fmp_adapter_maps_only_requested_fields_into_evidence_boundary() -> None:
    transport = StubTransport()
    provider = FMPProvider(transport)
    request = ProviderRequest(
        symbol="NVDA",
        dataset="annual_financials",
        as_of=date(2026, 9, 3),
        expected_period="FY2026",
        fields=("revenue",),
    )
    service = EvidenceIngestionService(
        repository=InMemoryEvidenceRepository(),
        freshness_policy=FreshnessPolicy(max_age_days=550),
    )

    result = await service.ingest(
        provider=provider,
        request=request,
        run_id="RUN-FMP",
        object_id="OBJ-NVDA",
    )

    assert transport.calls == [("income-statement", {"symbol": "NVDA", "limit": 20})]
    assert len(result.accepted.records) == 1
    evidence = result.accepted.records[0]
    assert evidence.normalized_field == "revenue"
    assert evidence.normalized_value == "215900000000"
    assert evidence.provider == "fmp"
    assert evidence.source_locator == "fmp://income-statement?symbol=NVDA"
    assert not isinstance(evidence.normalized_value, dict)
