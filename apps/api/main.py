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
from src.adapters.bocha import BochaDiscovery
from src.adapters.finrobot.professional_reporting import (
    ControlledArtifactStore,
    ProfessionalReportPublisher,
)
from src.adapters.fmp import FinancialProviderMode, FMPProvider, select_financial_provider
from src.adapters.llm.routes import configured_incremental_provider, configured_specialist_providers
from src.adapters.llm.teamorouter import TeamoRouterClient
from src.adapters.risc0 import EXPECTED_REVENUE_GROWTH_HOST_SHA256, RiscZeroProofAdapter
from src.agentic.composition import build_research_agent_registry
from src.agentic.llm_integration import (
    PlannerProviderResearchLeadPlanner,
    PlannerProviderSchemeGenerator,
)
from src.agentic.recovery_composition import build_adaptive_recovery
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
from src.capabilities.generated.governed_builder import GovernedCodeBuilder
from src.capabilities.generated.orchestration import GeneratedCapabilityOrchestrator
from src.capabilities.generated.scoped_registry import ScopedCapabilityRegistry
from src.capabilities.generated.validation import GeneratedCapabilityValidator
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.base import Base
from src.infrastructure.database.composition import create_postgresql_persistence
from src.infrastructure.database.generated_workflow import PostgreSQLCapabilityWorkflowRecorder
from src.observability.performance import configure_from_environment, flush
from src.phase4_product.api import install_phase4_error_handlers
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
from src.tooling.generated_sandbox import BrokerSandboxBackend, DockerSandboxBackend

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def create_app(service: ResearchApplicationService | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if service is not None:
            app.state.research_service = service
            yield
            return
        settings = get_settings()
        evaluator = settings.vfa_credential_mode == "evaluator"
        if evaluator and not settings.database_url.startswith("postgresql"):
            raise RuntimeError("Evaluator product requires PostgreSQL")
        if settings.database_url.startswith("postgresql"):
            if evaluator:
                from src.evaluator.client import EvaluatorGatewayFinancialData, active_session

                gateway_session = active_session()
                financial_provider = FMPProvider(EvaluatorGatewayFinancialData(gateway_session))
            else:
                selection = select_financial_provider(
                    mode=FinancialProviderMode.FMP,
                    fmp_settings=settings.fmp,
                    fixture_path=Path("tests/fixtures/nvda_financials.json"),
                )
                if not isinstance(selection.provider, FMPProvider) or not selection.live:
                    raise RuntimeError("Phase 4 production composition requires live FMP evidence")
                financial_provider = selection.provider
            persistence = create_postgresql_persistence(settings.database)
            evidence_collector = LiveFMPEvidenceCollector.with_local_artifacts(
                provider=financial_provider,
                repository=persistence.evidence_repository,
                artifact_root=Path(settings.artifact_root) / "phase4-raw",
                discovery=None if evaluator else BochaDiscovery(settings.bocha_api_key),
            )
            model_provider = (
                configured_incremental_provider(settings, route_id="teamorouter-sol")
                if evaluator
                else TeamoRouterClient(settings.llm)
            )
            incremental_provider = configured_incremental_provider(settings)
            specialist_providers = configured_specialist_providers(settings)
            forbidden_values = (
                (gateway_session._token.get_secret_value(),)
                if evaluator
                else tuple(
                    secret.get_secret_value()
                    for secret in (
                        *settings.fmp.credentials,
                        settings.bocha_api_key,
                        settings.llm.api_key,
                        incremental_provider._settings.api_key,
                        *(client._settings.api_key for client in specialist_providers.values()),
                    )
                    if secret is not None
                )
            )
            if evaluator:
                from src.observability.performance import configure

                configure(None)
            else:
                configure_from_environment(forbidden_values=forbidden_values)
            research_output_artifacts = ResearchAgentOutputArtifactStore(
                Path(settings.artifact_root) / "phase4-agent-outputs",
                forbidden_values=forbidden_values,
            )
            adaptive_recovery = await build_adaptive_recovery(
                settings, persistence.sessions, forbidden_values=forbidden_values
            )
            research_agents = build_research_agent_registry(
                model_provider,
                research_output_artifacts,
                profile_providers=specialist_providers,
                recovery=adaptive_recovery,
            )
            app.state.postgresql_persistence = persistence
            research_service = ResearchApplicationService(
                repository=persistence.application_repository,
                evidence_repository=persistence.evidence_repository,
                evidence_collector=evidence_collector,
                event_store=persistence.event_store,
                checkpoint_store=persistence.checkpoint_store,
                agent_registry=research_agents,
                recovery_evidence_store=adaptive_recovery.store,
                report_publisher=ProfessionalReportPublisher(
                    ControlledArtifactStore(Path(settings.artifact_root) / "phase4-report")
                ),
            )
            proof_root = Path(settings.artifact_root) / "phase4-proof"
            research_service.proof_workflow = RevenueGrowthRiscZeroProofWorkflow(
                adapter=RiscZeroProofAdapter(
                    host_binary=(
                        settings.risc0_host_binary
                        or REPOSITORY_ROOT
                        / "zk/revenue_growth/target/release/revenue-growth-proof-host"
                    ),
                    artifact_dir=proof_root,
                    expected_host_sha256=(
                        settings.risc0_expected_host_sha256
                        or EXPECTED_REVENUE_GROWTH_HOST_SHA256
                    ),
                ),
                artifact_dir=proof_root,
                event_store=research_service.event_store,
                repository=persistence.phase3_record_repository,
            )
            app.state.research_service = research_service
            app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
                sessions=persistence.sessions,
                service=research_service,
                incremental_scheme_generator=PlannerProviderSchemeGenerator(incremental_provider),
                incremental_planner=PlannerProviderResearchLeadPlanner(
                    incremental_provider,
                    max_validation_attempts=1,
                    fail_closed=True,
                    agent_registry=research_agents,
                ),
            )
            generated = GeneratedCapabilityOrchestrator(
                registry=ScopedCapabilityRegistry(research_service.capability_registry),
                research_lead=Phase3ResearchLeadCapabilityAuthority(),
                code_builder=GovernedCodeBuilder(adaptive_recovery, research_service.repository),
                validator=GeneratedCapabilityValidator(
                    sandbox=(
                        BrokerSandboxBackend(socket_path=settings.sandbox_broker_socket)
                        if settings.sandbox_broker_socket
                        else DockerSandboxBackend()
                    ),
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
                await flush()
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
