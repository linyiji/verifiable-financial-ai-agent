from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from apps.api.routes import router
from src.adapters.fmp import FinancialProviderMode, FMPProvider, select_financial_provider
from src.application.errors import ApplicationError
from src.application.evidence_collection import LiveFMPEvidenceCollector
from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.application.service import ResearchApplicationService
from src.infrastructure.config.settings import get_settings
from src.infrastructure.database.base import Base
from src.infrastructure.database.composition import create_postgresql_persistence
from src.phase4_product.api import install_phase4_error_handlers
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend


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
            app.state.postgresql_persistence = persistence
            app.state.research_service = ResearchApplicationService(
                repository=persistence.application_repository,
                evidence_repository=persistence.evidence_repository,
                evidence_collector=evidence_collector,
                event_store=persistence.event_store,
                checkpoint_store=persistence.checkpoint_store,
            )
            app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
                sessions=persistence.sessions,
                service=app.state.research_service,
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
