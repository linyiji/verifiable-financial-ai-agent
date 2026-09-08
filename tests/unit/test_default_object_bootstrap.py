import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.bootstrap import bootstrap_default_object
from src.application.persistence import ResearchObjectRow, ResearchRunAggregateRow
from src.domain.research_object import ResearchObject
from src.infrastructure.database.base import Base


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_empty_default_nvda_bootstrap_is_idempotent_and_preserves_user_object(
    tmp_path, existing
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    if existing:
        entity = ResearchObject(
            object_id="OBJ-NVDA", symbol="NVDA", company_name="User named NVIDIA", exchange="NASDAQ"
        )
        async with sessions() as session, session.begin():
            session.add(
                ResearchObjectRow(
                    object_id=entity.object_id,
                    payload=entity.model_dump(mode="json"),
                    created_at=entity.created_at,
                )
            )
    assert await bootstrap_default_object(sessions) == "OBJ-NVDA"
    assert await bootstrap_default_object(sessions) == "OBJ-NVDA"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(ResearchObjectRow)) == 1
        assert await session.scalar(select(func.count()).select_from(ResearchRunAggregateRow)) == 0
        row = await session.get(ResearchObjectRow, "OBJ-NVDA")
        assert row.payload["company_name"] == (
            "User named NVIDIA" if existing else "NVIDIA Corporation"
        )
    await engine.dispose()
