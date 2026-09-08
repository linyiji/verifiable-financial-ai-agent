"""Real producer + PostgreSQL + public HTTP DTO, fake external data only."""

import asyncio
import importlib.util
import json
import os
import subprocess
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.main import create_app
from src.adapters.fmp import FMPProvider
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.infrastructure.database.base import Base
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from tests.unit.application.test_evidence_semantics import SemanticFMPTransport

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="PostgreSQL required"
)
FRONTEND_DECODER = Path("apps/web/src/types/domain.ts").resolve().as_uri()


@pytest.fixture
async def database():
    schema = "output_roundtrip_" + uuid4().hex
    admin = create_async_engine(os.environ["TEST_POSTGRESQL_URL"])
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        os.environ["TEST_POSTGRESQL_URL"], connect_args={"server_settings": {"search_path": schema}}
    )

    def migrate(conn):
        with Operations.context(MigrationContext.configure(conn)):
            for path in sorted(Path("alembic/versions").glob("*.py")):
                spec = importlib.util.spec_from_file_location("migration_" + path.stem, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
        yield engine, async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_real_source_producer_durable_projection_http(database, tmp_path):  # noqa: F811
    _, sessions = database
    async with sessions.kw["bind"].begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    evidence = SessionFactoryEvidenceRepository(sessions)
    repository = SQLAlchemyApplicationRepository(sessions)
    from src.agentic.composition import build_research_agent_registry
    from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
    from tests.unit.agentic.test_adaptive_recovery import Client

    narrative_inputs = []

    class NarrativeClient(Client):
        async def complete_structured(self, **kwargs):
            narrative_inputs.append(json.loads(kwargs["messages"][-1].content))
            return await super().complete_structured(**kwargs)

    registry = build_research_agent_registry(
        NarrativeClient("teamorouter", "gpt-5.6-sol"),
        ResearchAgentOutputArtifactStore(tmp_path / "agents"),
    )
    from src.adapters.fmp import FMPEndpoint

    class IncidentTransport(SemanticFMPTransport):
        async def request(self, **kwargs):
            result = await super().request(**kwargs)
            if kwargs["endpoint"] is FMPEndpoint.HISTORICAL:
                return replace(
                    result,
                    payload=[
                        {
                            "symbol": "NVDA",
                            "date": (date(2026, 9, 3) - timedelta(days=i)).isoformat(),
                            "close": 150 + i,
                            "volume": 100000000 + i,
                        }
                        for i in range(20)
                    ],
                )
            return result

    service = ResearchApplicationService(
        agent_registry=registry,
        repository=repository,
        evidence_repository=evidence,
        event_store=PostgresRuntimeEventStore(sessions),
        evidence_collector=LiveFMPEvidenceCollector(
            provider=FMPProvider(IncidentTransport()), repository=evidence
        ),
    )
    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    from src.agentic.recovery_composition import build_adaptive_recovery
    from src.application.phase3_financial import (
        FreeCashFlowMarginValidationPlanProvider,
        Phase3FinancialCapabilityExtension,
        Phase3ResearchLeadCapabilityAuthority,
    )
    from src.capabilities.generated.artifacts import GeneratedCapabilityArtifactStore
    from src.capabilities.generated.governed_builder import GovernedCodeBuilder
    from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
    from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
    from src.capabilities.generated.validation import GeneratedCapabilityValidator
    from src.domain.recovery import RecoveryBudget
    from src.infrastructure.config.settings import Settings
    from src.infrastructure.database.generated_workflow import PostgreSQLCapabilityWorkflowRecorder
    from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository
    from src.tooling.generated_sandbox import DockerSandboxBackend

    recovery = await build_adaptive_recovery(
        Settings(
            _env_file=None,
            teamorouter_api_key="OFFLINE_SENTINEL",
            mimo_api_key=None,
            mimo_authority_file=None,
            artifact_root=str(tmp_path),
            vfa_credential_mode="byok",
        ),
        sessions,
    )
    recovery.budget = RecoveryBudget(max_total_attempts_per_task=1)

    def unavailable(request):
        raise httpx.ReadTimeout("offline generation timeout")

    fake_http = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
    for provider in recovery.clients.values():
        provider._client = fake_http

    generated = GeneratedCapabilityOrchestrator(
        registry=ScopedCapabilityRegistry(service.capability_registry),
        research_lead=Phase3ResearchLeadCapabilityAuthority(),
        code_builder=GovernedCodeBuilder(recovery, repository),
        validator=GeneratedCapabilityValidator(
            sandbox=DockerSandboxBackend(), plans=FreeCashFlowMarginValidationPlanProvider()
        ),
        event_store=service.event_store,
        recorder=PostgreSQLCapabilityWorkflowRecorder(
            SQLAlchemyPhase3RecordRepository(sessions),
            artifact_store=GeneratedCapabilityArtifactStore(tmp_path / "generated"),
        ),
    )
    service.add_calculation_extension(
        Phase3FinancialCapabilityExtension(
            generated=generated,
            event_store=service.event_store,
            instrumentation=service.instrumentation,
        )
    )
    obj = await service.create_object(symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ")
    from src.phase4_product.contracts import (
        ConfirmResearchRunRequestV1,
        PrepareResearchRunRequestV1,
    )

    draft = await backend.prepare_run(
        PrepareResearchRunRequestV1(
            research_object_id=obj.object_id,
            research_goal="Offline real producer projection",
            as_of=date(2026, 9, 8),
            preferences={},
        ),
        idempotency_key="offline-prepare",
        request_id=None,
    )
    response = await backend.confirm_run(
        ConfirmResearchRunRequestV1(
            draft_id=draft.draft_id,
            draft_version=draft.draft_version,
            draft_hash=draft.draft_hash,
            research_object_id=obj.object_id,
            confirm_scheme=True,
        ),
        idempotency_key="offline-confirm",
        request_id=None,
    )
    aggregate = await repository.get_run(response.admission.run_id)
    with pytest.raises(ValueError, match="material calculation set mismatch"):
        await service.execute_run(aggregate.run.run_id)
    await fake_http.aclose()
    aggregate = await repository.get_run(aggregate.run.run_id)
    assert aggregate.artifacts.released_result is None
    assert aggregate.artifacts.partial_research
    assert {c.capability_id for c in aggregate.artifacts.calculations} >= {
        "revenue_growth",
        "ebitda_margin",
        "technical_rsi_14",
        "technical_volume_ratio_20",
    }
    fcf = next(
        b
        for b in aggregate.artifacts.financial_branches
        if b.calculation_type == "free_cash_flow_margin"
    )
    assert fcf.status.value == "FAILED" and fcf.reason_code == "CAPABILITY_BUILD_FAILED"
    assert fcf.failure_stage == "CAPABILITY_BUILD" and len(fcf.build_record_ids) == 1
    assert fcf.diagnostic_id
    synthesis = next(item for item in narrative_inputs if item["task_type"] == "report_synthesis")
    assert "CAPABILITY_BUILD_FAILED" in json.dumps(synthesis["authoritative_inputs"])
    assert "INSUFFICIENT_DATA" in json.dumps(synthesis["authoritative_inputs"])
    assert "free_cash_flow_margin" not in {
        c.capability_id for c in aggregate.artifacts.calculations
    }
    assert all(
        t.status.value == "COMPLETED"
        for t in aggregate.runtime.actual_graph.tasks
        if t.task_type in {"valuation_analysis", "risk_analysis", "report_synthesis"}
    )
    projection = await backend.get_projection(aggregate.run.run_id)
    assert projection.run.run_id == aggregate.run.run_id
    app = create_app(service=service)
    app.state.phase4_product_backend = backend
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://offline") as client:
        response = await client.get(
            f"/api/research-runs/{aggregate.run.run_id}/projection",
            headers={"X-Phase4-Contract-Version": "phase4-core/v1"},
        )
        assert response.status_code == 200, response.text
        decoded = await asyncio.to_thread(
            subprocess.run,
            [
                "node",
                "--experimental-transform-types",
                "--input-type=module",
                "-e",
                f"import {{ decodeRunProjection }} from {json.dumps(FRONTEND_DECODER)}; "
                'import {readFileSync} from "node:fs"; '
                'const wire = JSON.parse(readFileSync(0, "utf8")); '
                "decodeRunProjection(wire, wire.run.run_id, wire.object.object_id);",
            ],
            input=response.text,
            text=True,
            capture_output=True,
            timeout=20,
        )
        assert decoded.returncode == 0, decoded.stderr
        tasks = response.json()["actual_graph"]["tasks"]
        coverage = [
            t["evidence_source_coverage"] for t in tasks if t.get("evidence_source_coverage")
        ]
        assert coverage
        assert set().union(*(set(value) for value in coverage)) == {
            "profile",
            "income",
            "balance",
            "cashflow",
            "peers",
            "quote",
            "historical",
            "analyst",
            "news",
            "transcript",
        }
