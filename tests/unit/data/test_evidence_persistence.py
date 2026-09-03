from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.data.persistence import EvidenceRecordRow, SQLAlchemyEvidenceRepository
from src.domain.enums import EvidenceStatus
from src.domain.evidence import EvidenceRecord
from src.infrastructure.database.base import Base


@pytest.mark.asyncio
async def test_sqlalchemy_repository_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[EvidenceRecordRow.__table__])

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    created_at = datetime(2026, 1, 25, tzinfo=UTC)
    evidence = EvidenceRecord(
        evidence_id="EVD-1",
        run_id="RUN-1",
        object_id="OBJ-NVDA",
        provider="fixture",
        source_locator="fixture.json",
        retrieved_at=created_at,
        period="FY2026",
        as_of=date(2026, 1, 25),
        raw_artifact_ref="artifact.json",
        normalized_field="revenue",
        normalized_value="215900000000",
        unit="CURRENCY",
        currency="USD",
        snapshot_hash="abc123",
        status=EvidenceStatus.ACCEPTED,
        created_at=created_at,
    )

    async with session_factory() as session:
        repository = SQLAlchemyEvidenceRepository(session)
        await repository.add(evidence)
        await session.commit()
        loaded = await repository.get("EVD-1")
        by_run = await repository.list_by_run("RUN-1")

    await engine.dispose()
    assert loaded is not None
    assert loaded.model_dump(exclude={"retrieved_at", "created_at"}) == evidence.model_dump(
        exclude={"retrieved_at", "created_at"}
    )
    assert [record.evidence_id for record in by_run] == ["EVD-1"]
