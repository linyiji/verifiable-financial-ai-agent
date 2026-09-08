"""Real persisted product reads, with no providers/workers and all writes denied."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.service import ResearchApplicationService
from src.infrastructure.config.settings import Settings
from src.phase4_product.api import create_phase4_product_router, install_phase4_error_handlers
from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

settings = Settings()
engine = create_async_engine(settings.database_url)
app = FastAPI()
app.state.phase4_product_backend = PostgreSQLPhase4ProductBackend(
    sessions=async_sessionmaker(engine, expire_on_commit=False),
    service=ResearchApplicationService(),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4173"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "X-Phase4-Contract-Version", "X-Request-ID"],
    expose_headers=["X-Phase4-Contract-Version"],
)


@app.middleware("http")
async def read_only_firewall(request: Request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return JSONResponse({"error": "EXACT_DRAFT_REVIEW_READ_ONLY"}, status_code=403)
    return await call_next(request)


install_phase4_error_handlers(app)
app.include_router(create_phase4_product_router())
# Deliberately no backend.start(), model adapter, prepare, confirm, or scheduler.
