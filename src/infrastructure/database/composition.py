from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.application.persistence import (
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.infrastructure.config.settings import DatabaseSettings
from src.infrastructure.database.artifacts import SQLAlchemyRunRecordRepository
from src.infrastructure.database.checkpoints import SQLAlchemyCheckpointStore
from src.infrastructure.database.phase3_records import SQLAlchemyPhase3RecordRepository
from src.infrastructure.database.phase4_product import PostgreSQLProductUnitOfWorkFactory
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore


@dataclass(slots=True, repr=False)
class PostgreSQLPersistence:
    """Coordinator-owned PostgreSQL adapters sharing one engine/session factory."""

    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    application_repository: SQLAlchemyApplicationRepository
    evidence_repository: SessionFactoryEvidenceRepository
    event_store: PostgresRuntimeEventStore
    checkpoint_store: SQLAlchemyCheckpointStore
    run_record_repository: SQLAlchemyRunRecordRepository
    phase3_record_repository: SQLAlchemyPhase3RecordRepository
    product_uow_factory: PostgreSQLProductUnitOfWorkFactory

    async def close(self) -> None:
        await self.engine.dispose()

    def __repr__(self) -> str:
        return "PostgreSQLPersistence(backend='postgresql', adapters=ready)"


def create_postgresql_persistence(
    settings: DatabaseSettings,
    *,
    event_poll_interval_seconds: float = 0.05,
) -> PostgreSQLPersistence:
    """Build adapters only; schema lifecycle remains an explicit migration step."""

    url = make_url(settings.url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL persistence requires a PostgreSQL database URL")
    if not url.drivername.endswith("+asyncpg"):
        raise ValueError("PostgreSQL persistence requires the asyncpg SQLAlchemy driver")
    engine = create_async_engine(settings.url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    return PostgreSQLPersistence(
        engine=engine,
        sessions=sessions,
        application_repository=SQLAlchemyApplicationRepository(sessions),
        evidence_repository=SessionFactoryEvidenceRepository(sessions),
        event_store=PostgresRuntimeEventStore(
            sessions,
            poll_interval_seconds=event_poll_interval_seconds,
        ),
        checkpoint_store=SQLAlchemyCheckpointStore(sessions),
        run_record_repository=SQLAlchemyRunRecordRepository(sessions),
        phase3_record_repository=SQLAlchemyPhase3RecordRepository(sessions),
        product_uow_factory=PostgreSQLProductUnitOfWorkFactory(sessions),
    )
