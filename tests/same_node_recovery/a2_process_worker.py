"""Fresh-process A2 proof against an explicitly disposable PostgreSQL cluster."""

import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.node_binding import BindingDenied
from src.domain.recovery import RecoveryEvidence
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.same_node_recovery.test_a1_admission import pending_case
from tests.same_node_recovery.test_durable import configured


def unrelated(terminal, case):
    if case == "lineage":
        updates = {"node_reservation_id": str(uuid4())}
    elif case == "exact":
        updates = {}
    else:
        field, value = {
            "context": ("context_hash", "sha256:" + "0" * 64),
            "contract": ("contract_hash", "sha256:" + "0" * 64),
            "task": ("task_id", terminal.scope.run_id + ":other"),
            "operation": ("operation_id", "other"),
        }[case]
        updates = {"scope": terminal.scope.model_copy(update={field: value})}
    return RecoveryEvidence.model_validate(terminal.model_copy(update=updates).model_dump())


async def main():
    url, schema, directory, phase, case = sys.argv[1:]
    folder = Path(directory)
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            database_name = await session.scalar(text("SELECT current_database()"))
            assert database_name == "vefin_recovery_disposable"
            assert "postgres-recovery/data" in await session.scalar(text("SHOW data_directory"))
        if phase == "A":
            _, pending, target, store, terminal = await pending_case(folder, sessions)
            await store.append(unrelated(terminal, case))
            result = pending
            entries, calls, denied = [], {}, False
        else:
            repo = SQLAlchemyApplicationRepository(sessions)
            store = RecoveryEvidenceStore(sessions)
            first = json.loads((folder / "A.json").read_text())
            service, _, _, clients = await configured(
                folder, repository=repo, store=store, sessions=sessions, persist=False,
            )
            entries = []
            original = repo.enter_node_execution

            async def enter(admission):
                entries.append(admission.attempt_reservation_id)
                return await original(admission)

            repo.enter_node_execution = enter
            denied = False
            try:
                await service.execute_run(first["run_id"])
            except BindingDenied:
                denied = True
            result = await repo.get_run_fresh(first["run_id"])
            target = result.runtime.task(first["task_id"])
            calls = {key: client.calls for key, client in clients.items()}
        async with sessions() as session:
            assert await session.scalar(text("SELECT count(*) FROM research_runs")) == 1
        receipt = dict(
            phase=phase, case=case, run_id=result.run.run_id, task_id=target.task_id,
            root=result.node_binding.model_dump(mode="json"), entries=entries,
            calls=calls, denied=denied,
            records=[r.model_dump(mode="json") for r in await store.records(result.run.run_id)],
        )
        (folder / f"{phase}.json").write_text(json.dumps(receipt, indent=2))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
