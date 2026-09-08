from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPFetchResult, FMPProvider
from src.data.artifacts import LocalRawArtifactStore, RawArtifactStore
from src.data.fixtures import FixtureProvider
from src.data.freshness import FreshnessPolicy
from src.data.ingestion import (
    EvidenceIngestionResult,
    EvidenceIngestionService,
    EvidenceProvenance,
)
from src.data.provider import ProviderRequest, RawProviderSnapshot
from src.data.repository import EvidenceRepository
from src.domain.enums import EvidenceAcquisitionStatus, EvidenceCategory
from src.domain.evidence import AcceptedEvidenceBundle, EvidenceRecord
from src.observability.performance import observe


class EvidenceAcquisitionScope(StrEnum):
    COMPANY = "COMPANY"
    PEER = "PEER"
    RESEARCH_NEWS = "RESEARCH_NEWS"


@dataclass(frozen=True, slots=True)
class EvidenceRequestPlan:
    scope: EvidenceAcquisitionScope
    request: ProviderRequest
    category: EvidenceCategory
    purpose: str


@dataclass(frozen=True, slots=True)
class EndpointCollectionStatus:
    endpoint: FMPEndpoint
    status: FMPAccessStatus
    http_status: int
    mapped_record_count: int
    accepted_count: int
    non_accepted_count: int
    error_code: str | None
    capability_execution: dict | None = None


@dataclass(frozen=True, slots=True)
class EvidenceTaskAcquisitionResult:
    task_id: str
    scope: EvidenceAcquisitionScope
    status: EvidenceAcquisitionStatus
    ingestion: EvidenceIngestionResult
    endpoint_statuses: tuple[EndpointCollectionStatus, ...]


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
        return await self._collect_for_task(
            task_id=f"{run_id}:evidence",
            symbol=symbol,
            run_id=run_id,
            object_id=object_id,
            as_of=as_of,
        )

    async def collect_scope(
        self,
        *,
        task_id: str,
        scope: EvidenceAcquisitionScope,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceTaskAcquisitionResult:
        if not task_id or not task_id.startswith(f"{run_id}:"):
            raise ValueError("producer task must belong to the evidence run")
        if scope is not EvidenceAcquisitionScope.COMPANY:
            return EvidenceTaskAcquisitionResult(
                task_id=task_id,
                scope=scope,
                status=EvidenceAcquisitionStatus.PARTIAL,
                ingestion=_empty_ingestion(run_id),
                endpoint_statuses=(),
            )
        ingestion = await self._collect_for_task(
            task_id=task_id,
            symbol=symbol,
            run_id=run_id,
            object_id=object_id,
            as_of=as_of,
        )
        return EvidenceTaskAcquisitionResult(
            task_id=task_id,
            scope=scope,
            status=(
                EvidenceAcquisitionStatus.COMPLETED
                if _has_core_financial_evidence(ingestion.accepted.records)
                else EvidenceAcquisitionStatus.FAILED
            ),
            ingestion=ingestion,
            endpoint_statuses=(),
        )

    async def _collect_for_task(
        self,
        *,
        task_id: str,
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
            provenance=EvidenceProvenance(
                producer_task_id=task_id,
                source_endpoint="fixture",
                evidence_purpose="fundamental_financials",
                evidence_category=EvidenceCategory.FINANCIAL_STATEMENT,
            ),
        )


class _SnapshotProvider:
    name = "fmp"

    def __init__(self, snapshot: RawProviderSnapshot) -> None:
        self._snapshot = snapshot

    async def fetch(self, request: ProviderRequest) -> RawProviderSnapshot:
        del request
        return self._snapshot


class LiveFMPEvidenceCollector:
    """Collect scoped live evidence while preserving the Phase-2 combined entry point."""

    def __init__(
        self,
        *,
        provider: FMPProvider,
        repository: EvidenceRepository,
        artifact_store: RawArtifactStore | None = None,
        discovery=None,
        fuse_news: bool = False,
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._artifact_store = artifact_store
        self._discovery = discovery
        self._fuse_news = fuse_news
        self.endpoint_statuses: list[EndpointCollectionStatus] = []
        self.scope_outcomes: dict[EvidenceAcquisitionScope, EvidenceAcquisitionStatus] = {}

    @classmethod
    def with_local_artifacts(
        cls,
        *,
        provider: FMPProvider,
        repository: EvidenceRepository,
        artifact_root: Path,
        discovery=None,
    ) -> LiveFMPEvidenceCollector:
        return cls(
            provider=provider,
            repository=repository,
            artifact_store=LocalRawArtifactStore(artifact_root),
            discovery=discovery,
        )

    async def collect(
        self,
        *,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceIngestionResult:
        """Backward-compatible combined collection; scoped ownership remains explicit."""

        self.endpoint_statuses.clear()
        self.scope_outcomes.clear()
        task_ids = {
            EvidenceAcquisitionScope.COMPANY: f"{run_id}:evidence",
            EvidenceAcquisitionScope.PEER: f"{run_id}:peers",
            EvidenceAcquisitionScope.RESEARCH_NEWS: f"{run_id}:research-news",
        }
        acquisitions = []
        for scope in EvidenceAcquisitionScope:
            acquisition = await self.collect_scope(
                task_id=task_ids[scope],
                scope=scope,
                symbol=symbol,
                run_id=run_id,
                object_id=object_id,
                as_of=as_of,
            )
            acquisitions.append(acquisition)

        company = next(
            item for item in acquisitions if item.scope is EvidenceAcquisitionScope.COMPANY
        )
        if company.status is EvidenceAcquisitionStatus.FAILED or not _has_core_financial_evidence(
            company.ingestion.accepted.records
        ):
            raise RuntimeError(
                "live FMP collection did not produce the required financial evidence"
            )
        return _merge_ingestion(run_id, [item.ingestion for item in acquisitions])

    async def collect_scope(
        self,
        *,
        task_id: str,
        scope: EvidenceAcquisitionScope,
        symbol: str,
        run_id: str,
        object_id: str,
        as_of: date,
    ) -> EvidenceTaskAcquisitionResult:
        if not task_id or not task_id.startswith(f"{run_id}:"):
            raise ValueError("producer task must belong to the evidence run")
        results: list[EvidenceIngestionResult] = []
        endpoint_statuses: list[EndpointCollectionStatus] = []
        for plan in evidence_request_plans(symbol=symbol, as_of=as_of, scope=scope):
            probe = await self._provider.probe(plan.request)
            result = await self._ingest_probe(
                probe=probe,
                plan=plan,
                producer_task_id=task_id,
                run_id=run_id,
                object_id=object_id,
            )
            accepted_count = len(result.accepted.records) if result is not None else 0
            record_count = len(result.records) if result is not None else 0
            capability_execution = None
            if plan.request.dataset in {"news", "transcript"}:
                from src.data.capability_policy import data_policy

                capability = (
                    "company_news" if plan.request.dataset == "news" else "earnings_transcript"
                )
                policy = data_policy(
                    capability, fuse=self._fuse_news and capability == "company_news"
                )
                capability_execution = {
                    "capability_id": capability,
                    "preferred_provider": "fmp",
                    "actual_provider": "fmp" if accepted_count else None,
                    "mode": policy.mode,
                    "fmp_status": probe.status.value,
                    "bocha_status": "NOT_ATTEMPTED",
                    "fallback_reason": None,
                    "discovery_only": False,
                }
                if self._discovery is not None and (not accepted_count or policy.mode == "FUSE"):
                    snapshots, outcome, reason = await self._discovery.acquire(
                        plan.request, capability
                    )
                    capability_execution.update(
                        bocha_status=outcome.value,
                        fallback_reason=probe.status.value
                        if not accepted_count
                        else "POLICY_FUSION",
                        discovery_only=capability == "earnings_transcript",
                    )
                    known_urls = {
                        r.source_locator for item in results for r in item.accepted.records
                    }
                    for snapshot in snapshots:
                        if snapshot.source_locator in known_urls:
                            continue
                        known_urls.add(snapshot.source_locator)
                        service = EvidenceIngestionService(
                            repository=self._repository,
                            artifact_store=self._artifact_store,
                            freshness_policy=FreshnessPolicy(
                                max_age_days=550 if capability == "earnings_transcript" else 7
                            ),
                        )
                        extra = await service.ingest(
                            provider=_SnapshotProvider(snapshot),
                            request=plan.request.model_copy(update={"expected_period": None}),
                            run_id=run_id,
                            object_id=object_id,
                            provenance=EvidenceProvenance(
                                producer_task_id=task_id,
                                source_endpoint="bocha_web_search",
                                evidence_purpose="transcript_discovery"
                                if capability == "earnings_transcript"
                                else "research_news",
                                evidence_category=EvidenceCategory.NEWS,
                            ),
                        )
                        results.append(extra)
                        if extra.accepted.records:
                            capability_execution["actual_provider"] = (
                                "fmp+bocha" if accepted_count else "bocha"
                            )
            endpoint_statuses.append(
                EndpointCollectionStatus(
                    endpoint=probe.endpoint,
                    status=probe.status,
                    http_status=probe.http_status,
                    mapped_record_count=probe.mapped_record_count,
                    accepted_count=accepted_count,
                    non_accepted_count=record_count - accepted_count,
                    error_code=probe.error_code,
                    capability_execution=capability_execution,
                )
            )
            if result is not None:
                results.append(result)

        ingestion = _merge_ingestion(run_id, results)
        status = _acquisition_status(
            scope=scope,
            statuses=endpoint_statuses,
            accepted=ingestion.accepted.records,
        )
        self.endpoint_statuses.extend(endpoint_statuses)
        self.scope_outcomes[scope] = status
        return EvidenceTaskAcquisitionResult(
            task_id=task_id,
            scope=scope,
            status=status,
            ingestion=ingestion,
            endpoint_statuses=tuple(endpoint_statuses),
        )

    @observe("data.ingest_probe", run="run_id")
    async def _ingest_probe(
        self,
        *,
        probe: FMPFetchResult,
        plan: EvidenceRequestPlan,
        producer_task_id: str,
        run_id: str,
        object_id: str,
    ) -> EvidenceIngestionResult | None:
        if probe.snapshot is None:
            return None
        if plan.request.dataset == "annual_financials":
            policy = FreshnessPolicy(max_age_days=800)
        elif plan.request.dataset == "historical_prices":
            # Historical observations are deliberately old; freshness here
            # means the requested bounded series, not a current quote.
            policy = FreshnessPolicy(max_age_days=max(365, plan.request.limit * 2))
        else:
            policy = None
        service = EvidenceIngestionService(
            repository=self._repository,
            artifact_store=self._artifact_store,
            freshness_policy=policy,
        )
        return await service.ingest(
            provider=_SnapshotProvider(probe.snapshot),
            request=plan.request,
            run_id=run_id,
            object_id=object_id,
            provenance=EvidenceProvenance(
                producer_task_id=producer_task_id,
                source_endpoint=probe.endpoint.value,
                evidence_purpose=plan.purpose,
                evidence_category=plan.category,
                observed_at=probe.snapshot.retrieved_at,
            ),
        )


def evidence_request_plans(
    *,
    symbol: str,
    as_of: date,
    scope: EvidenceAcquisitionScope | None = None,
) -> tuple[EvidenceRequestPlan, ...]:
    plans = (
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(symbol=symbol, dataset="company_profile", as_of=as_of, limit=1),
            category=EvidenceCategory.COMPANY_PROFILE,
            purpose="company_identity",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="annual_financials",
                as_of=as_of,
                fields=("revenue", "ebitda"),
                limit=5,
            ),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="fundamental_financials",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="balance_sheet",
                as_of=as_of,
                fields=("totalAssets", "totalDebt", "totalStockholdersEquity"),
                limit=2,
            ),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="balance_sheet_analysis",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="cash_flow",
                as_of=as_of,
                fields=("operatingCashFlow", "capitalExpenditure", "freeCashFlow"),
                limit=2,
            ),
            category=EvidenceCategory.FINANCIAL_STATEMENT,
            purpose="cash_flow_analysis",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.PEER,
            request=ProviderRequest(symbol=symbol, dataset="peer_multiples", as_of=as_of, limit=10),
            category=EvidenceCategory.PEER,
            purpose="peer_discovery",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="market_price",
                as_of=as_of,
                fields=("price", "volume", "marketCap", "pe"),
                limit=1,
            ),
            category=EvidenceCategory.MARKET,
            purpose="market_context",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="historical_prices",
                as_of=as_of,
                fields=("adjClose", "adjustedClose", "close", "volume"),
                # Phase 3 technical indicators require an accepted 200-day window.
                limit=250,
            ),
            category=EvidenceCategory.MARKET,
            purpose="historical_market_context",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.COMPANY,
            request=ProviderRequest(
                symbol=symbol,
                dataset="analyst_recommendations",
                as_of=as_of,
                limit=5,
            ),
            category=EvidenceCategory.ANALYST,
            purpose="analyst_consensus_context",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.RESEARCH_NEWS,
            request=ProviderRequest(symbol=symbol, dataset="news", as_of=as_of, limit=5),
            category=EvidenceCategory.NEWS,
            purpose="research_news",
        ),
        EvidenceRequestPlan(
            scope=EvidenceAcquisitionScope.RESEARCH_NEWS,
            request=ProviderRequest(
                symbol=symbol,
                dataset="transcript",
                as_of=as_of,
                expected_period="Q2FY2026",
                limit=1,
            ),
            category=EvidenceCategory.TRANSCRIPT,
            purpose="earnings_call_context",
        ),
    )
    if scope is None:
        return plans
    return tuple(plan for plan in plans if plan.scope is scope)


def phase2_fmp_requests(*, symbol: str, as_of: date) -> tuple[ProviderRequest, ...]:
    return tuple(plan.request for plan in evidence_request_plans(symbol=symbol, as_of=as_of))


def _merge_ingestion(
    run_id: str, results: list[EvidenceIngestionResult]
) -> EvidenceIngestionResult:
    accepted = [record for result in results for record in result.accepted.records]
    records = tuple(record for result in results for record in result.records)
    diagnostics = tuple(item for result in results for item in result.diagnostics)
    created = tuple(record for result in results for record in result.created_records)
    return EvidenceIngestionResult(
        accepted=AcceptedEvidenceBundle(run_id=run_id, records=accepted),
        records=records,
        diagnostics=diagnostics,
        created_records=created,
    )


def _empty_ingestion(run_id: str) -> EvidenceIngestionResult:
    return EvidenceIngestionResult(
        accepted=AcceptedEvidenceBundle(run_id=run_id, records=[]),
        records=(),
        diagnostics=(),
    )


def _acquisition_status(
    *,
    scope: EvidenceAcquisitionScope,
    statuses: list[EndpointCollectionStatus],
    accepted: list[EvidenceRecord],
) -> EvidenceAcquisitionStatus:
    access = {item.status for item in statuses}
    if not accepted and FMPAccessStatus.ENTITLEMENT_DENIED in access:
        return EvidenceAcquisitionStatus.ENTITLEMENT_BLOCKED
    failures = access.intersection(
        {
            FMPAccessStatus.AUTHENTICATION_FAILED,
            FMPAccessStatus.RATE_LIMITED,
            FMPAccessStatus.NOT_FOUND,
            FMPAccessStatus.PROVIDER_ERROR,
        }
    )
    if not accepted and failures:
        return EvidenceAcquisitionStatus.FAILED
    if scope is EvidenceAcquisitionScope.COMPANY and not _has_core_financial_evidence(accepted):
        return EvidenceAcquisitionStatus.FAILED
    has_nonaccepted = any(item.non_accepted_count for item in statuses)
    has_unavailable = any(
        item.status not in {FMPAccessStatus.AVAILABLE, FMPAccessStatus.NO_DATA} for item in statuses
    )
    if not accepted or has_nonaccepted or has_unavailable:
        return EvidenceAcquisitionStatus.PARTIAL
    return EvidenceAcquisitionStatus.COMPLETED


def _has_core_financial_evidence(records: list[EvidenceRecord]) -> bool:
    revenues = [record for record in records if record.normalized_field == "revenue"]
    ebitda_periods = {record.period for record in records if record.normalized_field == "ebitda"}
    return len(revenues) >= 2 and any(record.period in ebitda_periods for record in revenues)
