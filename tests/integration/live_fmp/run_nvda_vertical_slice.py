"""Run the credentialed WS-I NVDA slice and emit only a sanitized summary."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.adapters.fmp import (
    FinancialProviderMode,
    FMPProvider,
    select_financial_provider,
)
from src.capabilities.financial.growth import RevenueGrowthCapability
from src.capabilities.financial.profitability import EbitdaMarginCapability
from src.data.artifacts import LocalRawArtifactStore
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionService
from src.data.provider import ProviderRequest, RawProviderSnapshot
from src.data.repository import InMemoryEvidenceRepository
from src.domain.capability import CapabilityContext
from src.domain.enums import EvidenceStatus
from src.infrastructure.config import Settings

ARTIFACT_ROOT = Path("artifacts/phase2/live_fmp")


class SnapshotProvider:
    name = "fmp"

    def __init__(self, snapshot: RawProviderSnapshot) -> None:
        self._snapshot = snapshot

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        return self._snapshot


def _requests(as_of) -> list[ProviderRequest]:
    return [
        ProviderRequest(symbol="NVDA", dataset="company_profile", as_of=as_of, limit=1),
        ProviderRequest(
            symbol="NVDA",
            dataset="annual_financials",
            as_of=as_of,
            fields=("revenue", "ebitda"),
            limit=5,
        ),
        ProviderRequest(
            symbol="NVDA",
            dataset="balance_sheet",
            as_of=as_of,
            fields=("totalAssets", "totalDebt", "totalStockholdersEquity"),
            limit=2,
        ),
        ProviderRequest(
            symbol="NVDA",
            dataset="cash_flow",
            as_of=as_of,
            fields=("operatingCashFlow", "capitalExpenditure", "freeCashFlow"),
            limit=2,
        ),
        ProviderRequest(symbol="NVDA", dataset="peer_multiples", as_of=as_of, limit=10),
        ProviderRequest(
            symbol="NVDA",
            dataset="market_price",
            as_of=as_of,
            fields=("price", "volume", "marketCap", "pe"),
            limit=1,
        ),
        ProviderRequest(
            symbol="NVDA",
            dataset="historical_prices",
            as_of=as_of,
            fields=("close", "volume"),
            limit=5,
        ),
        ProviderRequest(
            symbol="NVDA",
            dataset="analyst_recommendations",
            as_of=as_of,
            limit=5,
        ),
        ProviderRequest(symbol="NVDA", dataset="news", as_of=as_of, limit=5),
        ProviderRequest(
            symbol="NVDA",
            dataset="transcript",
            as_of=as_of,
            expected_period="Q2FY2026",
            limit=1,
        ),
    ]


async def run() -> dict[str, Any]:
    settings = Settings()
    selection = select_financial_provider(
        mode=FinancialProviderMode.FMP,
        fmp_settings=settings.fmp,
        fixture_path=Path("tests/fixtures/nvda_financials.json"),
    )
    if not isinstance(selection.provider, FMPProvider):
        raise RuntimeError("live FMP provider was not selected")

    provider = selection.provider
    repository = InMemoryEvidenceRepository()
    artifact_store = LocalRawArtifactStore(ARTIFACT_ROOT)
    now = datetime.now(UTC)
    base_run_id = f"RUN-PHASE2-LIVE-FMP-{now.strftime('%Y%m%dT%H%M%SZ')}"
    endpoint_summary: dict[str, Any] = {}
    income_evidence = []

    for request in _requests(now.date()):
        probe = await provider.probe(request)
        summary: dict[str, Any] = {
            "status": probe.status.value,
            "http_status": probe.http_status,
            "mapped_record_count": probe.mapped_record_count,
            "error_code": probe.error_code,
            "accepted_count": 0,
            "non_accepted_count": 0,
            "artifact_count": 0,
        }
        if probe.snapshot is not None:
            policy = (
                FreshnessPolicy(max_age_days=800)
                if request.dataset == "annual_financials"
                else None
            )
            ingestion = EvidenceIngestionService(
                repository=repository,
                artifact_store=artifact_store,
                freshness_policy=policy,
            )
            result = await ingestion.ingest(
                provider=SnapshotProvider(probe.snapshot),
                request=request,
                run_id=f"{base_run_id}-{probe.endpoint.value.upper()}",
                object_id="OBJ-NVDA",
            )
            summary.update(
                {
                    "accepted_count": len(result.accepted.records),
                    "non_accepted_count": len(result.records) - len(result.accepted.records),
                    "artifact_count": len(
                        {record.raw_artifact_ref for record in result.records}
                    )
                    or 1,
                    "accepted_evidence_ids": [
                        record.evidence_id for record in result.accepted.records
                    ],
                }
            )
            if request.dataset == "annual_financials":
                income_evidence = result.accepted.records
        endpoint_summary[probe.endpoint.value] = summary

    calculations = await _calculate(base_run_id, income_evidence)
    return {
        "run_id": base_run_id,
        "symbol": "NVDA",
        "provider": "fmp",
        "generated_at": now.isoformat(),
        "endpoint_status": endpoint_summary,
        "accepted_evidence_count": len(
            [
                record
                for record in await repository.list()
                if record.status is EvidenceStatus.ACCEPTED
            ]
        ),
        "calculations": calculations,
        "secret_values_included": False,
    }


async def _calculate(run_id: str, evidence: list[Any]) -> list[dict[str, Any]]:
    revenues = sorted(
        (record for record in evidence if record.normalized_field == "revenue"),
        key=lambda record: record.as_of,
    )
    if len(revenues) < 2:
        return []
    prior_revenue, current_revenue = revenues[-2:]
    current_ebitda = next(
        (
            record
            for record in evidence
            if record.normalized_field == "ebitda" and record.period == current_revenue.period
        ),
        None,
    )
    if current_ebitda is None:
        return []
    context = CapabilityContext(
        run_id=run_id,
        task_id="TASK-PHASE2-LIVE-FUNDAMENTALS",
        accepted_evidence_ids=[record.evidence_id for record in evidence],
    )
    growth = await RevenueGrowthCapability().execute(
        {
            "calculation_id": "CALC-PHASE2-NVDA-REVENUE-GROWTH",
            "prior": prior_revenue,
            "current": current_revenue,
        },
        context,
    )
    margin = await EbitdaMarginCapability().execute(
        {
            "calculation_id": "CALC-PHASE2-NVDA-EBITDA-MARGIN",
            "ebitda": current_ebitda,
            "revenue": current_revenue,
        },
        context,
    )
    return [
        {
            "calculation_id": calculation.calculation_id,
            "capability_id": calculation.capability_id,
            "input_evidence_ids": calculation.input_evidence_ids,
            "output_value": str(calculation.output_value),
            "output_unit": calculation.output_unit,
        }
        for calculation in (growth, margin)
    ]


def main() -> None:
    summary = asyncio.run(run())
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    target = ARTIFACT_ROOT / "latest_summary.json"
    target.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
