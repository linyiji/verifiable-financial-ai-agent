"""Capability fallback through the production collector, PostgreSQL and task DTO."""

from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from src.adapters.bocha import BochaDiscovery
from src.adapters.fmp import FMPProvider
from src.application.evidence_collection import EvidenceAcquisitionScope, LiveFMPEvidenceCollector
from src.application.evidence_routing import RunEvidenceStore
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.data.capability_policy import DataOutcome, data_policy
from src.data.provider import ProviderRequest
from src.domain.enums import TaskOrigin
from src.domain.task import Task
from src.infrastructure.database.base import Base
from src.phase4_product.projections import project_task
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401
from tests.unit.application.test_evidence_semantics import SemanticFMPTransport


def bocha_transport(code=200, *, original_code=200, duplicate=False):
    def response(request):
        if request.method == "POST":
            page = {
                "url": "https://investor.nvidia.com/news/result",
                "datePublished": "2026-09-04T10:00:00+08:00",
                "snippet": "untrusted summary claiming revenue = 999",
            }
            return httpx.Response(
                code, json={"data": {"webPages": {"value": [page, page] if duplicate else [page]}}}
            )
        assert "authorization" not in request.headers
        return httpx.Response(
            original_code,
            headers={"content-type": "text/html"},
            text="<html><body>NVIDIA official company release. "
            + "Verified source context. " * 30
            + "</body></html>",
        )

    return httpx.MockTransport(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [200, 401, 403, 429, 500])
async def test_real_collector_source_locality_and_durable_dto(database, tmp_path, code):  # noqa: F811
    _, sessions = database
    async with sessions.kw["bind"].begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    repository = SessionFactoryEvidenceRepository(sessions)
    collector = LiveFMPEvidenceCollector.with_local_artifacts(
        provider=FMPProvider(SemanticFMPTransport()),
        repository=repository,
        artifact_root=tmp_path / "raw",
        discovery=BochaDiscovery(
            SecretStr("offline"), transport=bocha_transport(code, duplicate=True)
        ),
    )
    service = ResearchApplicationService(repository=SQLAlchemyApplicationRepository(sessions))
    obj = await service.create_object(symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ")
    draft = await service.prepare_run(
        research_object_id=obj.object_id,
        research_goal="Source verification",
        as_of=date(2026, 9, 4),
        preferences={},
    )
    admitted = await service.confirm_run(draft_id=draft.draft_id, confirm_scheme=True)
    run = admitted.run.run_id
    company = await collector.collect_scope(
        task_id=run + ":company",
        scope=EvidenceAcquisitionScope.COMPANY,
        symbol="NVDA",
        run_id=run,
        object_id="OBJ-NVDA",
        as_of=date(2026, 9, 4),
    )
    assert any(e.normalized_field == "revenue" for e in company.ingestion.accepted.records)
    news = await collector.collect_scope(
        task_id=run + ":news",
        scope=EvidenceAcquisitionScope.RESEARCH_NEWS,
        symbol="NVDA",
        run_id=run,
        object_id="OBJ-NVDA",
        as_of=date(2026, 9, 4),
    )
    task = Task(
        task_id=run + ":news",
        run_id=run,
        task_type="research_news_analysis",
        goal="Company news",
        origin=TaskOrigin.PLAN,
        assigned_agent="research_news_analyst",
        skill_id="research_news_analysis_v1",
    )
    routed = RunEvidenceStore(run).register_acquisition(news)
    routed.apply_to(task)
    dto = project_task(task, expected_run_id=run)
    status = dto.evidence_source_coverage["news"]["capability_execution"]
    assert status["preferred_provider"] == "fmp"
    assert status["fmp_status"] == "ENTITLEMENT_DENIED"
    if code == 200:
        assert status["actual_provider"] == "bocha"
        assert status["bocha_status"] == "AVAILABLE"
        records = news.ingestion.accepted.records
        assert len({e.evidence_id for e in records}) == len(records)
        assert all(e.normalized_field == "official_document_text" for e in records)
        assert all(e.document_authority is not None for e in records)
        assert not any("999" in e.normalized_value for e in records)
        for e in records:
            assert (await repository.get(e.evidence_id)).document_authority == e.document_authority
        assert news.endpoint_statuses[1].capability_execution["bocha_status"] == "PARTIAL"
    else:
        assert not news.ingestion.accepted.records
        assert status["actual_provider"] is None


@pytest.mark.asyncio
async def test_snippet_without_original_never_becomes_evidence():
    provider = BochaDiscovery(SecretStr("offline"), transport=bocha_transport(original_code=403))
    snapshots, outcome, _ = await provider.acquire(
        ProviderRequest(symbol="NVDA", dataset="news", as_of=date(2026, 9, 4)), "company_news"
    )
    assert not snapshots
    assert outcome is DataOutcome.INSUFFICIENT_DATA


def test_finite_data_modes_do_not_authorize_structured_web_numbers():
    assert data_policy("company_news", fuse=True).mode == "FUSE"
    assert data_policy("earnings_transcript").mode == "FALLBACK"
    assert data_policy("financial_statements").candidates == ("fmp",)
    with pytest.raises(ValueError):
        data_policy("financial_statements", fuse=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[], {"data": None}, {"data": {"webPages": []}}])
async def test_malformed_discovery_is_a_local_source_failure(body):
    provider = BochaDiscovery(
        SecretStr("offline"),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    snapshots, outcome, code = await provider.acquire(
        ProviderRequest(symbol="NVDA", dataset="news", as_of=date(2026, 9, 4)), "company_news"
    )
    assert snapshots == ()
    assert outcome is DataOutcome.FAILED
    assert code == "INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_fuse_real_collector_has_deduplicated_originals_and_separate_provider_evidence():
    from src.adapters.fmp import FMPAccessStatus, FMPEndpoint, FMPResponseEnvelope
    from src.data.repository import InMemoryEvidenceRepository
    from tests.unit.application.test_evidence_semantics import RETRIEVED_AT

    class NewsTransport(SemanticFMPTransport):
        async def request(self, *, endpoint, path, params):
            if endpoint is FMPEndpoint.NEWS:
                return FMPResponseEnvelope(
                    endpoint=endpoint,
                    status=FMPAccessStatus.AVAILABLE,
                    http_status=200,
                    retrieved_at=RETRIEVED_AT,
                    payload=[
                        {
                            "title": "NVIDIA earnings news",
                            "publisher": "Financial provider",
                            "publishedDate": "2026-09-04",
                        }
                    ],
                )
            return await super().request(endpoint=endpoint, path=path, params=params)

    collector = LiveFMPEvidenceCollector(
        provider=FMPProvider(NewsTransport()),
        repository=InMemoryEvidenceRepository(),
        fuse_news=True,
        discovery=BochaDiscovery(SecretStr("offline"), transport=bocha_transport(duplicate=True)),
    )
    result = await collector.collect_scope(
        task_id="RUN-FUSE:news",
        scope=EvidenceAcquisitionScope.RESEARCH_NEWS,
        symbol="NVDA",
        run_id="RUN-FUSE",
        object_id="OBJ-NVDA",
        as_of=date(2026, 9, 4),
    )
    news = result.endpoint_statuses[0].capability_execution
    assert news["mode"] == "FUSE"
    assert news["actual_provider"] == "fmp+bocha"
    assert {e.provider for e in result.ingestion.accepted.records} == {"fmp", "bocha"}
    originals = [
        e
        for e in result.ingestion.accepted.records
        if e.evidence_purpose == "research_news" and e.provider == "bocha"
    ]
    assert len(originals) == 1
    assert originals[0].document_authority.authority == "OFFICIAL"
