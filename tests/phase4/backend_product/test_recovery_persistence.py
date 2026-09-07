import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from apps.api.routes import recovery_execution_record
from src.agentic.research_agent import ResearchAgentInvocationError
from src.infrastructure.database.recovery import RecoveryEvidenceStore, capability_provenance
from tests.phase4.backend_product.test_memory_postgresql import database  # noqa: F401
from tests.unit.agentic.test_adaptive_recovery import agent, context, setup, task


@pytest.fixture
async def store(database):  # noqa: F811
    _, sessions = database

    def migrate(conn):
        spec = importlib.util.spec_from_file_location(
            "recovery_migration", Path("alembic/versions/20260908_0012_runtime_recovery.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

    async with sessions.kw["bind"].begin() as conn:
        await conn.run_sync(migrate)
    return RecoveryEvidenceStore(sessions)


def local_context():
    return context(task().model_copy(update={"run_id": "RUN-A", "task_id": "RUN-A:fundamentals"}))


@pytest.mark.asyncio
async def test_durable_attempts_decisions_projection_and_immutability(store, tmp_path):
    recovery, clients, _ = setup()
    recovery.store = store
    await agent(tmp_path, recovery, clients).execute(local_context())
    records = await store.records("RUN-A")
    assert len([r for r in records if r.kind == "ATTEMPT_COMPLETED"]) == 4
    assert len([r for r in records if r.kind == "DECISION"]) == 3
    assert await store.records("RUN-OLD") == []

    class Backend:
        sessions = store.sessions

        async def get_run(self, run_id):
            assert run_id == "RUN-A"

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(phase4_product_backend=Backend()))
    )
    assert await recovery_execution_record("RUN-A", request) == records
    serialized = "".join(r.model_dump_json() for r in records)
    assert "SENTINEL_SECRET" not in serialized and "messages" not in serialized
    async with store.sessions() as session:
        with pytest.raises(Exception, match="immutable"):
            await session.execute(text("UPDATE phase6_recovery_evidence SET payload=payload"))
        await session.rollback()
    # An unlinked PASS cannot certify a route, even if its fields look valid.
    completed = next(r for r in records if r.kind == "ATTEMPT_COMPLETED" and r.outcome == "PASS")
    assert capability_provenance([completed], completed.scope, recovery.detector.routes) == {}


@pytest.mark.asyncio
async def test_concurrent_entry_cannot_double_provider_budget(store, tmp_path):
    recovery, clients, _ = setup()
    recovery.store = store
    researcher = agent(tmp_path, recovery, clients)
    results = await asyncio.gather(
        researcher.execute(local_context()),
        researcher.execute(local_context()),
        return_exceptions=True,
    )
    assert sum(not isinstance(r, Exception) for r in results) == 1
    assert [clients[k].calls for k in clients] == [1, 1, 2]


@pytest.mark.asyncio
async def test_restart_refuses_budget_reset(store, tmp_path):
    recovery, clients, _ = setup()
    recovery.store = store
    await agent(tmp_path, recovery, clients).execute(local_context())
    fresh, fresh_clients, _ = setup()
    fresh.store = store
    with pytest.raises(ResearchAgentInvocationError):
        await agent(tmp_path / "restart", fresh, fresh_clients).execute(local_context())
    assert sum(c.calls for c in fresh_clients.values()) == 0
