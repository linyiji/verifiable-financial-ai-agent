from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.routes import router
from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.adapters.fmp import FinancialProviderMode, FMPProvider, select_financial_provider
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.adapters.risc0 import RiscZeroProofAdapter
from src.agentic import AgentRegistry
from src.agentic.research_agent import LLMResearchAgent
from src.agentic.research_output_artifacts import ResearchAgentOutputArtifactStore
from src.application.errors import ApplicationError
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.phase3_financial import (
    FreeCashFlowMarginValidationPlanProvider,
    Phase3FinancialCapabilityExtension,
    Phase3ResearchLeadCapabilityAuthority,
)
from src.application.phase3_proof import RevenueGrowthRiscZeroProofWorkflow
from src.application.service import ResearchApplicationService
from src.capabilities.generated.artifacts import GeneratedCapabilityArtifactStore
from src.capabilities.generated.builder import PlannerProviderCodeBuilder
from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
from src.capabilities.generated.validation import GeneratedCapabilityValidator
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.base import Base
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.database.generated_workflow import PostgreSQLCapabilityWorkflowRecorder
from src.phase4_product.api import install_phase4_error_handlers
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from src.tooling.generated_sandbox import DockerSandboxBackend

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def create_app(service: ResearchApplicationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            app.state.research_service = service
            yield
            return
        settings = get_settings()
        if settings.database_url.startswith("postgresql"):
            selection = select_financial_provider(
                mode=FinancialProviderMode.FMP,
                fmp_settings=settings.fmp,
                fixture_path=Path("tests/fixtures/nvda_financials.json"),
            )
            if not isinstance(selection.provider, FMPProvider) or not selection.live:
                raise RuntimeError("Phase 4 production composition requires live FMP evidence")
            persistence = create_postgresql_persistence(settings.database)
            evidence_collector = LiveFMPEvidenceCollector.with_local_artifacts(
                provider=selection.provider,
                repository=persistence.evidence_repository,
                artifact_root=Path(settings.artifact_root) / "phase4-raw",
            )
            model_provider = TeamoRouterClient(settings.llm)
            forbidden_values = tuple(
                secret.get_secret_value()
                for secret in (*settings.fmp.credentials, settings.llm.api_key)
                if secret is not None
            )
            research_output_artifacts = ResearchAgentOutputArtifactStore(
                Path(settings.artifact_root) / "phase4-agent-outputs",
                forbidden_values=forbidden_values,
            )
            research_agents = AgentRegistry()
            for agent_id, task_types in (
                ("fundamental_analyst", frozenset({"fundamental_analysis"})),
                ("peer_analyst", frozenset({"peer_analysis"})),
                (
                    "research_news_analyst",
                    frozenset({"research_news_analysis"}),
                ),
                ("valuation_analyst", frozenset({"valuation_analysis"})),
                ("risk_analyst", frozenset({"risk_analysis", "risk_follow_up"})),
                ("research_lead", frozenset({"report_synthesis"})),
            ):
                research_agents.register(
                    LLMResearchAgent(
                        agent_id=agent_id,
                        supported_task_types=task_types,
                        provider=model_provider,
                        artifacts=research_output_artifacts,
                    )
                )
            app.state.postgresql_persistence = persistence
            research_service = ResearchApplicationService(
                repository=persistence.application_repository,
                evidence_repository=persistence.evidence_repository,
                evidence_collector=evidence_collector,
                event_store=persistence.event_store,
                checkpoint_store=persistence.checkpoint_store,
                agent_registry=research_agents,
                report_publisher=ProfessionalReportPublisher(
                    ControlledArtifactStore(Path(settings.artifact_root) / "phase4-report")
                ),
            )
            proof_root = Path(settings.artifact_root) / "phase4-proof"
            research_service.proof_workflow = RevenueGrowthRiscZeroProofWorkflow(
                adapter=RiscZeroProofAdapter(
                    host_binary=(
                        REPOSITORY_ROOT
                        / "zk/revenue_growth/target/release/revenue-growth-proof-host"
                    ),
                    artifact_dir=proof_root,
                ),
                artifact_dir=proof_root,
                event_store=research_service.event_store,
                repository=persistence.phase3_record_repository,
            )
            app.state.research_service = research_service
            app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
                sessions=persistence.sessions,
                service=research_service,
            )
            generated = GeneratedCapabilityOrchestrator(
                registry=ScopedCapabilityRegistry(research_service.capability_registry),
                research_lead=Phase3ResearchLeadCapabilityAuthority(),
                code_builder=PlannerProviderCodeBuilder(model_provider),
                validator=GeneratedCapabilityValidator(
                    sandbox=DockerSandboxBackend(),
                    plans=FreeCashFlowMarginValidationPlanProvider(),
                ),
                event_store=research_service.event_store,
                recorder=PostgreSQLCapabilityWorkflowRecorder(
                    persistence.phase3_record_repository,
                    artifact_store=GeneratedCapabilityArtifactStore(
                        Path(settings.artifact_root) / "phase4-generated",
                        forbidden_values=forbidden_values,
                    ),
                ),
                max_attempts=2,
            )
            research_service.add_calculation_extension(
                Phase3FinancialCapabilityExtension(
                    generated=generated,
                    event_store=research_service.event_store,
                )
            )
            await app.state.phase4_product_backend.start()
            try:
                yield
            finally:
                await app.state.phase4_product_backend.close()
                await persistence.close()
            return
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        app.state.research_service = ResearchApplicationService(
            repository=SQLAlchemyApplicationRepository(sessions),
            evidence_repository=SessionFactoryEvidenceRepository(sessions),
        )
        yield
        await engine.dispose()

    app = FastAPI(
        title="Verifiable Financial Agent System",
        version="0.1.0",
        description="Phase 1 evidence-gated financial research API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^http://127\.0\.0\.1:(?:4173|4174)$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Accept",
            "Content-Type",
            "Idempotency-Key",
            "Last-Event-ID",
            "X-Phase4-Contract-Version",
            "X-Phase4-Event-Contract-Version",
        ],
        expose_headers=[
            "ETag",
            "X-Phase4-Contract-Version",
            "X-Phase4-Event-Contract-Version",
            "X-Run-Terminal",
            "X-Terminal-Sequence",
        ],
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.middleware("http")
    async def issue_request_id(request: Request, call_next):
        request.state.request_id = f"REQ-{uuid4()}"
        return await call_next(request)

    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request.headers.get("X-Request-ID"),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "request validation failed",
                    "details": {"errors": exc.errors()},
                    "request_id": request.headers.get("X-Request-ID"),
                }
            },
        )

    app.include_router(router)
    install_phase4_error_handlers(app)

    return app


app = create_app()
