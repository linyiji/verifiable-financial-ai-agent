"""Real PostgreSQL proof in an isolated temporary schema; no provider calls."""

import asyncio
import importlib.util
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import ResearchObjectRow, ResearchRunAggregateRow
from src.infrastructure.database.research_memory import (
    ResearchMemoryPointerRow,
    ResearchMemoryRepository,
    ResearchObjectVersionRow,
    ResearchViewVersionRow,
)
from src.phase4_product.errors import ProductError
from src.phase4_product.memory_contracts import ResearchObjectVersion, ResearchViewVersion

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="requires PostgreSQL"
)


def pair(run="RUN-A", obj="OBJ-A"):
    identity = dict(
        research_object_id=obj,
        source_run_id=run,
        source_released_result_id="RESULT-" + run,
        source_report_id="REPORT-" + run,
        source_canonical_record_id="CER-" + run,
        created_at=datetime.now(UTC),
    )
    return (
        ResearchObjectVersion(**identity, object_version=1, object_version_id="ROV-" + run),
        ResearchViewVersion(
            **identity,
            research_object_version=1,
            research_view_version=1,
            research_view_version_id="RVV-" + run,
            as_of="2026-09-06",
            summary=None,
            items=(),
        ),
    )


@pytest.fixture
async def database():
    url = os.environ["TEST_POSTGRESQL_URL"]
    schema = "p5a_test_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    def migrate(conn):
        ResearchObjectRow.__table__.create(conn)
        ResearchRunAggregateRow.__table__.create(conn)
        spec = importlib.util.spec_from_file_location(
            "memory_migration", Path("alembic/versions/20260907_0009_research_memory.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

    try:
        async with engine.begin() as conn:
            await conn.run_sync(migrate)
        async with sessions() as session, session.begin():
            for obj in ("OBJ-A", "OBJ-B"):
                session.add(
                    ResearchObjectRow(object_id=obj, payload={}, created_at=datetime.now(UTC))
                )
            for run, status in (
                ("RUN-A", "RELEASED"),
                ("RUN-OLD", "RELEASED"),
                ("RUN-BAD", "FAILED"),
            ):
                session.add(
                    ResearchRunAggregateRow(
                        run_id=run,
                        object_id="OBJ-A",
                        status=status,
                        payload={"immutable": True},
                        updated_at=datetime.now(UTC),
                    )
                )
        yield ResearchMemoryRepository(sessions), sessions
    finally:
        await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def counts(sessions):
    async with sessions() as session:
        return [
            await session.scalar(select(func.count()).select_from(row))
            for row in (ResearchObjectVersionRow, ResearchViewVersionRow, ResearchMemoryPointerRow)
        ]


async def test_concurrent_idempotent_reopen_and_history(database):
    repo, sessions = database
    results = await asyncio.gather(*(repo.materialize(*pair()) for _ in range(5)))
    assert len({r.current_view.research_view_version_id for r in results}) == 1
    assert await counts(sessions) == [1, 1, 1]
    assert await ResearchMemoryRepository(sessions).read("OBJ-A") == results[0]
    async with sessions() as session:
        assert (await session.get(ResearchRunAggregateRow, "RUN-A")).payload == {"immutable": True}


@pytest.mark.parametrize("stage", ["object", "view", "pointer"])
async def test_atomic_rollback(database, stage):
    repo, sessions = database

    def fail(at):
        if at == stage:
            raise RuntimeError("injected rollback")

    with pytest.raises(RuntimeError):
        await repo.materialize(*pair(), checkpoint=fail)
    assert await counts(sessions) == [0, 0, 0]


@pytest.mark.parametrize("table", ["research_object_versions", "research_view_versions"])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
async def test_database_append_only(database, table, operation):
    repo, sessions = database
    await repo.materialize(*pair())
    sql = f"UPDATE {table} SET payload=payload" if operation == "UPDATE" else f"DELETE FROM {table}"
    with pytest.raises(DBAPIError):
        async with sessions() as session, session.begin():
            await session.execute(text(sql))
    assert await counts(sessions) == [1, 1, 1]


async def test_stale_write_never_replaces_current(database):
    repo, sessions = database
    original = await repo.materialize(*pair())
    with pytest.raises(ProductError, match="current memory is bound"):
        await repo.materialize(*pair("RUN-OLD"))
    assert await repo.read("OBJ-A") == original
    assert await counts(sessions) == [1, 1, 1]


@pytest.mark.parametrize("run,obj", [("RUN-BAD", "OBJ-A"), ("RUN-A", "OBJ-B")])
async def test_release_and_object_gate(database, run, obj):
    repo, sessions = database
    with pytest.raises(ProductError):
        await repo.materialize(*pair(run, obj))
    assert await counts(sessions) == [0, 0, 0]
