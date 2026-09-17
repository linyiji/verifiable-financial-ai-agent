"""Two separate Python processes; disposable PostgreSQL is the only shared state."""

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import SQLAlchemyApplicationRepository
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.same_node_recovery.test_durable import configured


async def main():
    url, schema, directory, phase = sys.argv[1:]
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        assert (
            await session.scalar(text("SELECT current_database()"))
        ) == "vefin_recovery_disposable"
        assert "vefin-fundamentals-same-node-recovery-fix/work/postgres-recovery/data" in (
            await session.scalar(text("SHOW data_directory"))
        )
    repository = SQLAlchemyApplicationRepository(sessions)
    store = RecoveryEvidenceStore(sessions)
    service, value, collector, clients = await configured(
        Path(directory),
        repository=repository,
        store=store,
        sessions=sessions,
        persist=phase == "A",
    )
    native_calls = []
    native_execute = service.tool_runtime.execute

    async def counted_native(tool_id, *args, **kwargs):
        native_calls.append(tool_id)
        return await native_execute(tool_id, *args, **kwargs)

    service.tool_runtime.execute = counted_native
    before = await repository.get_run_fresh(value.run.run_id)
    comparison = None
    if phase == "A":
        result = await service.execute_run(value.run.run_id)
    else:
        from src.application.execution_profiles import frozen_profile, runtime_configuration
        from src.domain.node_binding import canonical_value
        from src.phase4_product.hashing import canonical_json_sha256
        from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

        target = before.runtime.actual_graph.tasks[1]
        frozen = frozen_profile(before, target).runtime_configuration
        current = canonical_value(runtime_configuration(service, target, None))
        differences = []

        def compare(a, b, path=""):
            if isinstance(a, dict) and isinstance(b, dict):
                for key in a.keys() | b.keys():
                    compare(a.get(key), b.get(key), path + "/" + key)
            elif isinstance(a, list) and isinstance(b, list):
                assert len(a) == len(b)
                for i, (x, y) in enumerate(zip(a, b, strict=True)):
                    compare(x, y, path + "/" + str(i))
            elif a != b:
                differences.append(path)

        compare(frozen, current)
        assert differences and all(path.endswith("/created_at") for path in differences)
        comparison = {
            "frozen": canonical_json_sha256(frozen),
            "current": canonical_json_sha256(current),
            "differences": differences,
        }
        assert await repository.recovery_pending_run_ids() == [value.run.run_id]
        backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
        completed = asyncio.Event()
        execute = backend._execute_started_run

        async def observed(*args, **kwargs):
            try:
                await execute(*args, **kwargs)
            finally:
                completed.set()

        backend._execute_started_run = observed
        loop = asyncio.create_task(backend._scheduler_loop())
        try:
            await asyncio.wait_for(completed.wait(), timeout=15)
        finally:
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)
        result = await repository.get_run_fresh(value.run.run_id)
        assert await repository.recovery_pending_run_ids() == []
    root = result.node_binding
    records = await store.records(value.run.run_id)
    async with sessions() as session:
        from sqlalchemy import func, select

        from src.application.persistence import CalculationRecordRow, ResearchRunAggregateRow

        assert await session.scalar(select(func.count()).select_from(ResearchRunAggregateRow)) == 1
        calculations = {
            row.calculation_id: row.payload
            for row in await session.scalars(select(CalculationRecordRow))
        }
    receipt = {
        "native_calls": native_calls,
        "saved_calculations": calculations,
        "profile_comparison": comparison,
        "phase": phase,
        "run_id": result.run.run_id,
        "root": root.model_dump(mode="json"),
        "upstream_calls_in_process": collector.calls,
        "provider_calls_in_process": {k: c.calls for k, c in clients.items()},
        "records": [v.model_dump(mode="json") for v in records],
        "before_graph": before.node_binding.frozen_graph.model_dump(mode="json"),
        "after_graph": root.frozen_graph.model_dump(mode="json"),
    }
    await asyncio.to_thread(
        Path(directory, f"process-{phase}.json").write_text, json.dumps(receipt, indent=2)
    )
    if phase == "A":
        assert root.lifecycle == "RECOVERY_PENDING" and collector.calls == 1
    else:
        assert len(root.current_results) == 2 and collector.calls == 0
        assert clients["teamorouter-sol"].calls == 0
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
