from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def _reset_isolated_database(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
            for table_name in sorted(result.scalars()):
                if not table_name.replace("_", "").isalnum():
                    raise RuntimeError("unexpected test table name")
                await connection.execute(
                    text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE')
                )
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def isolated_postgresql_state():
    url = os.environ.get("TEST_POSTGRESQL_URL")
    if url:
        asyncio.run(_reset_isolated_database(url))
    yield
