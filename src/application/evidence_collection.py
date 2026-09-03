from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPFetchResult, FMPProvider
from src.data.artifacts import LocalRawArtifactStore, RawArtifactStore
from src.data.fixtures import FixtureProvider
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import EvidenceIngestionResult, EvidenceIngestionService
from src.data.provider import ProviderRequest, RawProviderSnapshot
from src.data.repository import EvidenceRepository
from src.domain.evidence import AcceptedEvidenceBundle


class EvidenceCollector(Protocol):
    async def collect(
        self,
        *,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceIngestionResult: ...


class FixtureEvidenceCollector:
    def __init__(self, *, repository: EvidenceRepository, fixture_path: Path) -> None:
        self._repository = repository
        self._fixture_path = fixture_path

    async def collect(
        self,
        *,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceIngestionResult:
        service = EvidenceIngestionService(
            repository=self._repository,
            freshness_policy=FreshnessPolicy(max_age_days=800),
        )
        return await service.ingest(
            provider=FixtureProvider(self._fixture_path),
            request=ProviderRequest(
                symbol=symbol,
                dataset="annual_financials",
                as_of=as_of,
                fields=("revenue", "ebitda"),
            ),
            run_id=run_id,
            object_id=object_id,
        )


@dataclass(frozen=True, slots=True)
class EndpointCollectionStatus:
    endpoint: FMPEndpoint
    status: FMPAccessStatus
    http_status: int
    mapped_record_count: int
    accepted_count: int
    non_accepted_count: int
    error_code: str | None


class _SnapshotProvider:
    name = "fmp"

    def __init__(self, snapshot: RawProviderSnapshot) -> None:
        self._snapshot = snapshot

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        del request
        return self._snapshot


class LiveFMPEvidenceCollector:
    """Collect the Phase-2 endpoint set while preserving the Evidence Gate."""

    def __init__(
        self,
        *,
        provider: FMPProvider,
        repository: EvidenceRepository,
        artifact_store: RawArtifactStore | None = None,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._artifact_store = artifact_store
        self.endpoint_statuses: list[EndpointCollectionStatus] = []

    @classmethod
    def with_local_artifacts(
        cls,
        *,
        provider: FMPProvider,
        repository: EvidenceRepository,
        artifact_root: Path,
    ) -> LiveFMPEvidenceCollector:
        return cls(
            provider=provider,
            repository=repository,
            artifact_store=LocalRawArtifactStore(artifact_root),
        )

    async def collect(
        self,
        *,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceIngestionResult:
        self.endpoint_statuses.clear()
        results: list[EvidenceIngestionResult] = []
        for request in phase2_fmp_requests(symbol=symbol, as_of=as_of):
            probe = await self._provider.probe(request)
            result = await self._ingest_probe(
                probe=probe,
                request=request,
                run_id=run_id,
                object_id=object_id,
            )
            accepted_count = len(result.accepted.records) if result is not None else 0
            record_count = len(result.records) if result is not None else 0
            self.endpoint_statuses.append(
                EndpointCollectionStatus(
                    endpoint=probe.endpoint,
                    status=probe.status,
                    http_status=probe.http_status,
                    mapped_record_count=probe.mapped_record_count,
                    accepted_count=accepted_count,
                    non_accepted_count=record_count - accepted_count,
                    error_code=probe.error_code,
                )
            )
            if result is not None:
                results.append(result)

        accepted = [record for result in results for record in result.accepted.records]
        records = tuple(record for result in results for record in result.records)
        diagnostics = tuple(item for result in results for item in result.diagnostics)
        if not _has_core_financial_evidence(accepted):
            raise RuntimeError(
                "live FMP collection did not produce the required financial evidence"
            )
        return EvidenceIngestionResult(
            accepted=AcceptedEvidenceBundle(run_id=run_id, records=accepted),
            records=records,
            diagnostics=diagnostics,
        )

    async def _ingest_probe(
        self,
        *,
        probe: FMPFetchResult,
        request: ProviderRequest,
        run_id: str,
        object_id: str,
    ) -> EvidenceIngestionResult | None:
        if probe.snapshot is None:
            return None
        policy = (
            FreshnessPolicy(max_age_days=800) if request.dataset == "annual_financials" else None
        )
        service = EvidenceIngestionService(
            repository=self._repository,
            artifact_store=self._artifact_store,
            freshness_policy=policy,
        )
        return await service.ingest(
            provider=_SnapshotProvider(probe.snapshot),
            request=request,
            run_id=run_id,
            object_id=object_id,
        )


def phase2_fmp_requests(*, symbol: str, as_of: date) -> tuple[ProviderRequest, ...]:
    return (
        ProviderRequest(symbol=symbol, dataset="company_profile", as_of=as_of, limit=1),
        ProviderRequest(
            symbol=symbol,
            dataset="annual_financials",
            as_of=as_of,
            fields=("revenue", "ebitda"),
            limit=5,
        ),
        ProviderRequest(
            symbol=symbol,
            dataset="balance_sheet",
            as_of=as_of,
            fields=("totalAssets", "totalDebt", "totalStockholdersEquity"),
            limit=2,
        ),
        ProviderRequest(
            symbol=symbol,
            dataset="cash_flow",
            as_of=as_of,
            fields=("operatingCashFlow", "capitalExpenditure", "freeCashFlow"),
            limit=2,
        ),
        ProviderRequest(symbol=symbol, dataset="peer_multiples", as_of=as_of, limit=10),
        ProviderRequest(
            symbol=symbol,
            dataset="market_price",
            as_of=as_of,
            fields=("price", "volume", "marketCap", "pe"),
            limit=1,
        ),
        ProviderRequest(
            symbol=symbol,
            dataset="historical_prices",
            as_of=as_of,
            fields=("close", "volume"),
            limit=5,
        ),
        ProviderRequest(symbol=symbol, dataset="analyst_recommendations", as_of=as_of, limit=5),
        ProviderRequest(symbol=symbol, dataset="news", as_of=as_of, limit=5),
        ProviderRequest(
            symbol=symbol,
            dataset="transcript",
            as_of=as_of,
            expected_period="Q2FY2026",
            limit=1,
        ),
    )


def _has_core_financial_evidence(records: list) -> bool:
    revenues = [record for record in records if record.normalized_field == "revenue"]
    ebitda_periods = {record.period for record in records if record.normalized_field == "ebitda"}
    return len(revenues) >= 2 and any(record.period in ebitda_periods for record in revenues)
