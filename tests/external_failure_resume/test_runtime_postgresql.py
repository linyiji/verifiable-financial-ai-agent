"""Migrated disposable PostgreSQL, real root/event transactions, synthetic providers."""

import asyncio
import json
import os
import sys
from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from src.application.external_failure_resume import control, legacy_snapshot
from src.application.persistence import (
    ResearchRunAggregateRow,
    RuntimeEventRow,
    SessionFactoryEvidenceRepository,
    SQLAlchemyApplicationRepository,
)
from src.domain.node_binding import BindingDenied
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
from src.infrastructure.database.recovery import RecoveryEvidenceStore
from tests.external_failure_resume.runtime_fixture import exhaust, legal_fixture, request_for
from tests.phase4.backend_product.test_real_output_projection import database  # noqa: F401

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRESQL_URL"), reason="disposable PostgreSQL required"
)


async def test_postgresql_atomic_resume_rollback_race_fresh_process(
    database,  # noqa: F811
    tmp_path,
    monkeypatch,
    record_property,  # noqa: F811
):
    _, sessions = database
    service, value, clients = await legal_fixture(
        tmp_path,
        repository=SQLAlchemyApplicationRepository(sessions),
        evidence=SessionFactoryEvidenceRepository(sessions),
        store=RecoveryEvidenceStore(sessions),
        event_store=PostgresRuntimeEventStore(sessions),
    )
    failed = await exhaust(service, value)
    request = await request_for(service, failed)
    old_rows = await service.recovery_evidence_store.records(failed.run.run_id)
    old_root = legacy_snapshot(failed)

    async def snapshot():
        async with sessions() as session:
            root = await session.get(ResearchRunAggregateRow, failed.run.run_id)
            events = list(
                await session.scalars(
                    select(RuntimeEventRow)
                    .where(RuntimeEventRow.run_id == failed.run.run_id)
                    .order_by(RuntimeEventRow.sequence)
                )
            )
            return deepcopy(
                (
                    root.payload,
                    root.projection_sequence,
                    root.projection_revision,
                    [row.payload for row in events],
                )
            )

    before = await snapshot()
    persist = service.repository._persist_resume_events

    async def fail_after_events(*args):
        await persist(*args)
        raise RuntimeError("synthetic rollback after event insertion")

    monkeypatch.setattr(service.repository, "_persist_resume_events", fail_after_events)
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        await service.repository.resume_external_failure(request, actor=request.actor)
    assert await snapshot() == before
    assert legacy_snapshot(await service.repository.get_run_fresh(failed.run.run_id)) == old_root
    monkeypatch.setattr(service.repository, "_persist_resume_events", persist)
    children = service.repository._persist_children

    async def fail_after_children(*args):
        await children(*args)
        raise RuntimeError("synthetic rollback after root and child writes")

    monkeypatch.setattr(service.repository, "_persist_children", fail_after_children)
    with pytest.raises(RuntimeError, match="root and child writes"):
        await service.repository.resume_external_failure(request, actor=request.actor)
    assert await snapshot() == before
    monkeypatch.setattr(service.repository, "_persist_children", children)
    # Competing SQL roots independently load and lock the same row.
    repos = [SQLAlchemyApplicationRepository(sessions) for _ in range(2)]
    receipts = await asyncio.gather(
        *(repo.resume_external_failure(request, actor=request.actor) for repo in repos)
    )
    assert receipts[0] == receipts[1]
    committed = await snapshot()
    assert committed[1] > before[1]
    assert committed[2] == before[2] + 1
    assert committed[3][-1]["event_id"] == receipts[0].event_id
    assert [e["type"] for e in committed[3][len(before[3]) :]] == [
        "external_failure.closed",
        "external_failure.resume_authorized",
    ]
    assert await repos[0].resume_external_failure(request, actor=request.actor) == receipts[0]
    assert await snapshot() == committed
    async with sessions() as session:
        schema = await session.scalar(text("SELECT current_schema()"))
    code = """
import asyncio,json,sys,os
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from src.application.persistence import SQLAlchemyApplicationRepository
from src.domain.external_failure_resume import ResumeExternalFailure
from src.infrastructure.database.postgresql_events import PostgresRuntimeEventStore
async def main():
 engine=create_async_engine(sys.argv[1],connect_args={"server_settings":{"search_path":sys.argv[2]}})
 sessions=async_sessionmaker(engine,expire_on_commit=False)
 repo=SQLAlchemyApplicationRepository(sessions)
 request=ResumeExternalFailure.model_validate_json(sys.argv[3])
 receipt=await repo.resume_external_failure(request,actor=request.actor)
 value=await repo.get_run_fresh(request.run_id)
 events=await PostgresRuntimeEventStore(sessions).replay(request.run_id)
 print(json.dumps({"pid":os.getpid(),"receipt":receipt.model_dump(mode="json"),
  "control":value.node_binding.external_failure_resume,
  "pending":await repo.external_resume_pending_run_ids(),"event_count":len(events)}))
 await engine.dispose()
asyncio.run(main())
"""
    child = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        code,
        os.environ["TEST_POSTGRESQL_URL"],
        schema,
        request.model_dump_json(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await child.communicate()
    assert child.returncode == 0, err.decode()
    fresh = json.loads(out)
    assert fresh["pid"] != os.getpid()
    assert fresh["receipt"] == receipts[0].model_dump(mode="json")
    assert fresh["control"] == committed[0]["node_binding"]["external_failure_resume"]
    assert fresh["pending"] == [failed.run.run_id]
    assert fresh["event_count"] == len(committed[3])
    record_property("fresh_process", json.dumps(fresh))
    owners = await asyncio.gather(
        *(repo.claim_execution(failed.run.run_id) for repo in repos), return_exceptions=True
    )
    assert sum(isinstance(v, BindingDenied) for v in owners) == 1
    assert await repos[0].external_resume_pending_run_ids() == []
    owner = next(v for v in owners if not isinstance(v, Exception))
    pending = await service.execute_run(failed.run.run_id, execution_owner=owner)
    assert pending.node_binding.lifecycle == "RECOVERY_PENDING"
    again = await exhaust(service, pending)
    assert again.node_binding.lifecycle == "EXTERNAL_FAILURE_PAUSED"
    assert len(control(again).failures) == 2
    assert (await service.recovery_evidence_store.records(failed.run.run_id))[
        : len(old_rows)
    ] == old_rows
    # The old provider cannot append even a new immutable record after its owner is fenced.
    old = next(r for r in old_rows if r.scope.task_profile == "risk_analysis")
    with pytest.raises(BindingDenied):
        await service.recovery_evidence_store.append(
            old.model_copy(update={"record_id": str(uuid4())})
        )
    # Exercise the actual product scheduler loop without any HTTP/SSE/UI surface.
    from src.application.resume_runtime import current_risk_success
    from src.phase4_product.postgresql_backend import PostgreSQLPhase4ProductBackend

    backend = PostgreSQLPhase4ProductBackend(sessions=sessions, service=service)
    calls_before = {key: client.calls for key, client in clients.items()}
    backend._worker = asyncio.create_task(backend._scheduler_loop())
    try:
        await asyncio.sleep(0.6)
        assert {key: client.calls for key, client in clients.items()} == calls_before
        assert (
            await service.repository.get_run_fresh(failed.run.run_id)
        ).node_binding.lifecycle == ("EXTERNAL_FAILURE_PAUSED")
        second_request = await request_for(service, again, "second-explicit-resume")
        clients["teamorouter-sol"].fail_risk = False
        await service.repository.resume_external_failure(second_request, actor=second_request.actor)
        async with asyncio.timeout(60):
            while True:
                final = await service.repository.get_run_fresh(failed.run.run_id)
                if (
                    current_risk_success(final)
                    and any(
                        task.task_type == "report_synthesis" and task.status.value == "COMPLETED"
                        for task in final.runtime.actual_graph.tasks
                    )
                    and not backend._executions
                ):
                    break
                await asyncio.sleep(0.1)
        assert final.node_binding.frozen_graph == failed.node_binding.frozen_graph
        assert final.node_binding.execution_snapshot == failed.node_binding.execution_snapshot
        risk = next(
            task for task in final.runtime.actual_graph.tasks if task.task_type == "risk_analysis"
        )
        assert final.node_binding.attempts[risk.task_id].generation == 5
        assert control(final).envelopes[-1].cycle_ordinal == 2
        assert clients["teamorouter-sol"].calls == calls_before["teamorouter-sol"] + 2
        assert clients["teamorouter-terra"].calls == calls_before["teamorouter-terra"]
        assert clients["teamorouter-luna"].calls == clients["mimo-direct"].calls == 0
    finally:
        await backend.close()
