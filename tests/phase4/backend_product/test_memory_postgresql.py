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


async def incremental_pair(database, status="RELEASED", base="RUN-A"):
    repo, sessions = database
    original = await repo.materialize(*pair())
    async with sessions() as session, session.begin():
        session.add(
            ResearchRunAggregateRow(
                run_id="RUN-R2",
                object_id="OBJ-A",
                status=status,
                payload={"run": {"base_run_id": base, "base_research_view_version": "RVV-RUN-A"}},
                updated_at=datetime.now(UTC),
            )
        )
    obj, view = pair("RUN-R2")
    return original, (
        obj.model_copy(update={"object_version": 2}),
        view.model_copy(update={"research_object_version": 2, "research_view_version": 2}),
    )


async def test_incremental_atomic_v2_and_exact_v1_remains(database):
    repo, sessions = database
    original, v2 = await incremental_pair(database)
    results = await asyncio.gather(
        *(repo.materialize(*v2, expected_base=("RUN-A", "RVV-RUN-A")) for _ in range(5))
    )
    assert all(r.latest_released_run_id == "RUN-R2" for r in results)
    assert await counts(sessions) == [2, 2, 1]
    assert (await repo.read("OBJ-A")).latest_research_view_version == 2
    assert await repo.historical_snapshot("OBJ-A", "RUN-A", "RVV-RUN-A") == original
    async with sessions() as session:
        assert (await session.get(ResearchRunAggregateRow, "RUN-A")).payload == {"immutable": True}


@pytest.mark.parametrize("stage", ["object", "view", "pointer"])
async def test_incremental_v2_rollback_keeps_v1(database, stage):
    repo, sessions = database
    original, v2 = await incremental_pair(database)

    def fail(at):
        if at == stage:
            raise RuntimeError("injected v2 rollback")

    with pytest.raises(RuntimeError):
        await repo.materialize(*v2, expected_base=("RUN-A", "RVV-RUN-A"), checkpoint=fail)
    assert await repo.read("OBJ-A") == original
    assert await counts(sessions) == [1, 1, 1]


@pytest.mark.parametrize(
    "status,base,expected",
    [
        ("FAILED", "RUN-A", ("RUN-A", "RVV-RUN-A")),
        ("RUNNING", "RUN-A", ("RUN-A", "RVV-RUN-A")),
        ("RELEASED", "RUN-OLD", ("RUN-A", "RVV-RUN-A")),
        ("RELEASED", "RUN-A", ("RUN-OLD", "RVV-RUN-A")),
        ("RELEASED", "RUN-A", ("RUN-A", "RVV-FOREIGN")),
    ],
)
async def test_incremental_failed_or_stale_authority_never_advances(
    database, status, base, expected
):
    repo, sessions = database
    original, v2 = await incremental_pair(database, status, base)
    with pytest.raises(ProductError):
        await repo.materialize(*v2, expected_base=expected)
    assert await repo.read("OBJ-A") == original
    assert await counts(sessions) == [1, 1, 1]


@pytest.mark.parametrize(
    "obj,run,view",
    [
        ("OBJ-B", "RUN-A", "RVV-RUN-A"),
        ("OBJ-A", "RUN-OLD", "RVV-RUN-A"),
        ("OBJ-A", "RUN-A", "RVV-FOREIGN"),
        ("OBJ-A", "RUN-BAD", "RVV-RUN-A"),
    ],
)
async def test_exact_base_lookup_rejects_fallback(database, obj, run, view):
    repo, _ = database
    await repo.materialize(*pair())
    with pytest.raises(ProductError):
        await repo.read_exact(obj, run, view)


async def test_incremental_prepare_confirm_persists_exact_new_run_and_replay(database):
    from datetime import date

    from src.agentic.llm_integration import (
        PlannerProviderResearchLeadPlanner,
        PlannerProviderSchemeGenerator,
    )
    from src.application.service import ResearchApplicationService
    from src.domain.research_object import ResearchObject
    from src.infrastructure.database.base import Base
    from src.phase4_product.contracts import (
        ConfirmResearchRunRequestV1,
        PrepareResearchRunRequestV1,
    )
    from src.phase4_product.incremental import build_incremental_context
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend
    from tests.unit.llm.test_agentic_llm_integration import FakeProvider, valid_graph, valid_scheme

    repo, sessions = database
    original = await repo.materialize(*pair())
    async with sessions() as session, session.begin():
        connection = await session.connection()
        await connection.run_sync(Base.metadata.create_all)
        row = await session.get(ResearchObjectRow, "OBJ-A")
        row.payload = ResearchObject(
            object_id="OBJ-A", symbol="NVDA", company_name="NVIDIA", exchange="NASDAQ"
        ).model_dump(mode="json")
    context = build_incremental_context(
        original.current_view,
        object_id="OBJ-A",
        base_run_id="RUN-A",
        base_view_id="RVV-RUN-A",
        target_as_of=date(2026, 9, 7),
    )
    proposal = valid_scheme()
    proposal["incremental_decisions"] = [dict(source_identity=d.source_identity,
        decision=d.decision, reason=d.reason) for d in context.decisions]
    provider = FakeProvider([proposal, valid_graph()])
    from src.agentic.composition import build_research_agent_registry

    registry = build_research_agent_registry(provider, None)
    backend = PostgreSQLPhase4ProductBackend(
        sessions=sessions,
        service=ResearchApplicationService(agent_registry=registry),
        incremental_scheme_generator=PlannerProviderSchemeGenerator(provider),
        incremental_planner=PlannerProviderResearchLeadPlanner(provider),
    )
    request = PrepareResearchRunRequestV1(
        research_object_id="OBJ-A",
        research_goal="Update current fundamentals",
        as_of=date(2026, 9, 7),
        base_run_id="RUN-A",
        base_research_view_version="RVV-RUN-A",
    )
    draft = await backend.prepare_run(request, idempotency_key="p5b-prepare", request_id=None)
    assert draft.scheme_snapshot.incremental_context.base_run_id == "RUN-A"
    assert (
        await backend.prepare_run(request, idempotency_key="p5b-prepare", request_id=None) == draft
    )
    confirm = ConfirmResearchRunRequestV1(
        draft_id=draft.draft_id,
        draft_version=draft.draft_version,
        draft_hash=draft.draft_hash,
        research_object_id="OBJ-A",
        confirm_scheme=True,
    )
    response = await backend.confirm_run(confirm, idempotency_key="p5b-confirm", request_id=None)
    replay = await backend.confirm_run(confirm, idempotency_key="p5b-confirm", request_id=None)
    run_id = response.admission.run_id
    assert replay.admission.run_id == run_id != "RUN-A"
    async with sessions() as session:
        row = await session.get(ResearchRunAggregateRow, run_id)
        assert row.payload["run"]["base_run_id"] == "RUN-A"
        assert row.payload["run"]["base_research_view_version"] == "RVV-RUN-A"
        assert all(
            t["run_id"] == run_id and not t["task_input_evidence_ids"]
            for t in row.payload["runtime"]["planned_graph"]["tasks"]
        )
    assert len(provider.calls) == 2
    assert await repo.read("OBJ-A") == original
