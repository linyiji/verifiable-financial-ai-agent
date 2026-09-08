"""Idempotent empty research identity; never seed research, evidence or memory."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.application.persistence import ResearchObjectRow
from src.domain.research_object import ResearchObject


async def bootstrap_default_object(sessions) -> str:
    async with sessions() as session, session.begin():
        rows = (await session.scalars(select(ResearchObjectRow))).all()
        for row in rows:
            if row.payload.get("symbol", "").upper() == "NVDA":
                return row.object_id
        entity = ResearchObject(
            object_id="OBJ-NVDA",
            symbol="NVDA",
            company_name="NVIDIA Corporation",
            exchange="NASDAQ",
        )
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        statement = insert(ResearchObjectRow).values(
            object_id=entity.object_id,
            created_at=entity.created_at,
            payload=entity.model_dump(mode="json"),
        )
        await session.execute(statement.on_conflict_do_nothing(index_elements=["object_id"]))
        return entity.object_id
